"""Attribute a measurement to the Tor circuit that actually carried it.

Each measurement uses unique SOCKS credentials. Tor isolates streams by SOCKS
auth and reports the credentials in STREAM events, so a stream can be tied to
one measurement. The stream's SUCCEEDED event names the circuit it ran on, and
CIRC events provide that circuit's path. Anything missing or ambiguous leaves
attribution unverified instead of guessing.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field

from stem import ControllerError, SocketError
from stem.connection import AuthenticationFailure
from stem.control import Controller, EventType, Listener, State

from .discovery import CONTROL_PORTS, LOOPBACK_HOST, socks_proxy_url
from .models import CircuitInfo, SocksCredentials

SOURCE_VERIFIED = "stream-event-correlation"
SOURCE_UNCORRELATED = "measurement-stream-not-correlated"
SOURCE_CONTROL_UNAVAILABLE = "control-port-unavailable"

Path = tuple[tuple[str, str | None], ...]


def get_current_circuit(
    controller_host: str = "127.0.0.1",
    controller_port: int = 9051,
    password: str | None = None,
) -> CircuitInfo:
    """Compatibility API: a circuit snapshot cannot identify a measurement's path.

    Do not query or select an arbitrary built circuit. Use CircuitAttributor,
    which correlates STREAM events to the measurement's own SOCKS connection.
    """
    return CircuitInfo(source=SOURCE_UNCORRELATED)


@dataclass
class MeasurementTrace:
    """Handle for one measurement; pass `credentials` to the SOCKS client."""

    credentials: SocksCredentials | None
    unavailable_reason: str | None = None
    loss_marker: int = 0
    stream_ids: set[str] = field(default_factory=set)
    # circuit id -> path snapshot taken when a matched stream succeeded on it
    succeeded: dict[str, Path | None] = field(default_factory=dict)


class CircuitAttributor:
    """Connects to a local control port with cookie (or no) authentication.

    The host is always loopback: the control port belongs to the Tor running on this
    machine, and its traffic and cookie must never cross a network.
    """

    def __init__(
        self,
        ports: int | Sequence[int] = CONTROL_PORTS,
        settle_seconds: float = 2.0,
    ) -> None:
        self._ports = (ports,) if isinstance(ports, int) else tuple(ports)
        self._settle_seconds = settle_seconds
        self._controller: Controller | None = None
        self._unavailable_reason: str | None = "Control connection not opened."
        self._cond = threading.Condition()
        self._built: dict[str, Path] = {}
        self._traces: dict[str, MeasurementTrace] = {}
        self._stream_owner: dict[str, MeasurementTrace] = {}
        self._loss_count = 0
        self.port: int | None = None
        self.socks_proxy: str | None = None
        self.auth_failed = False

    @property
    def available(self) -> bool:
        return self._controller is not None

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    def __enter__(self) -> CircuitAttributor:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        """Use the first candidate control port that accepts our authentication."""
        failures = []
        for port in self._ports:
            controller, failure = self._open(port)
            if controller is not None:
                self._controller = controller
                self._unavailable_reason = None
                self.port = port
                return
            failures.append(failure)
        self._unavailable_reason = "; ".join(failures) or "No control port configured."

    def _open(self, port: int) -> tuple[Controller | None, str]:
        try:
            controller = Controller.from_port(LOOPBACK_HOST, port)
        except (SocketError, ControllerError, OSError) as exc:
            return None, f"Tor control port {LOOPBACK_HOST}:{port} unavailable: {exc}"
        try:
            controller.authenticate()
            # Listen before seeding so no circuit event falls between the two.
            controller.add_event_listener(self._on_event, EventType.STREAM, EventType.CIRC)
            controller.add_status_listener(self._on_status)
            seeded = {
                str(circuit.id): _path(circuit.path)
                for circuit in controller.get_circuits([])
                if circuit.status == "BUILT" and circuit.path
            }
            socks_proxy = _loopback_socks_proxy(controller)
        except AuthenticationFailure as exc:
            self.auth_failed = True
            _close_quietly(controller)
            return None, f"Tor control port {LOOPBACK_HOST}:{port} authentication failed: {exc}"
        except (SocketError, ControllerError, OSError) as exc:
            _close_quietly(controller)
            return None, f"Tor control port {LOOPBACK_HOST}:{port} setup failed: {exc}"
        with self._cond:
            for circuit_id, path in seeded.items():
                self._built.setdefault(circuit_id, path)
        self.socks_proxy = socks_proxy
        return controller, ""
    def close(self) -> None:
        controller, self._controller = self._controller, None
        if controller is not None:
            _close_quietly(controller)

    def begin(self) -> MeasurementTrace:
        """Register a new measurement before it opens any connection."""
        if self._controller is None:
            return MeasurementTrace(credentials=None, unavailable_reason=self._unavailable_reason)
        credentials = SocksCredentials(
            username=f"tortriage-{secrets.token_hex(8)}", password=secrets.token_hex(8)
        )
        with self._cond:
            trace = MeasurementTrace(credentials=credentials, loss_marker=self._loss_count)
            self._traces[credentials.username] = trace
        return trace

    def resolve(self, trace: MeasurementTrace) -> CircuitInfo:
        if trace.credentials is None:
            return _unverified(trace.unavailable_reason or "Control port unavailable.", SOURCE_CONTROL_UNAVAILABLE)

        with self._cond:
            # Events arrive on a separate connection, so allow a short settling time.
            self._cond.wait_for(
                lambda: bool(trace.succeeded) or self._loss_count != trace.loss_marker,
                timeout=self._settle_seconds,
            )
            self._traces.pop(trace.credentials.username, None)
            for stream_id in trace.stream_ids:
                self._stream_owner.pop(stream_id, None)
            lost = self._loss_count != trace.loss_marker
            succeeded = {
                circuit_id: path or self._built.get(circuit_id)
                for circuit_id, path in trace.succeeded.items()
            }

        if lost:
            return _unverified("Control connection was lost during the measurement; events may be missing.")
        if not trace.stream_ids:
            return _unverified("No STREAM event carried this measurement's SOCKS credentials.")
        if not succeeded:
            return _unverified("No stream of this measurement reported successful attachment to a circuit.")
        if len(succeeded) > 1:
            return _unverified(
                "Streams of this measurement succeeded on multiple circuits: "
                + ", ".join(sorted(succeeded))
                + "."
            )

        circuit_id, path = next(iter(succeeded.items()))
        if path is None:
            path = self._query_path(circuit_id)
        if path is None:
            return _unverified(f"The path of circuit {circuit_id} could not be retrieved.", circuit_id=circuit_id)
        if len(path) != 3 or any(not fingerprint for fingerprint, _ in path):
            return _unverified(
                f"Circuit {circuit_id} does not have three identified hops; cannot assign entry/middle/exit.",
                circuit_id=circuit_id,
            )
        entry, middle, exit_ = (_format_hop(*hop) for hop in path)
        return CircuitInfo(
            entry=entry,
            middle=middle,
            exit=exit_,
            source=SOURCE_VERIFIED,
            attribution="verified",
            attribution_reason=(
                f"Stream with this measurement's SOCKS credentials succeeded on circuit {circuit_id}."
            ),
            circuit_id=circuit_id,
        )

    def _query_path(self, circuit_id: str) -> Path | None:
        controller = self._controller
        if controller is None:
            return None
        try:
            circuit = controller.get_circuit(int(circuit_id), None)
        except (ControllerError, SocketError, OSError, ValueError):
            return None
        if circuit is None or circuit.status != "BUILT" or not circuit.path:
            return None
        return _path(circuit.path)

    def _on_status(self, controller, state, timestamp) -> None:
        if state in (State.CLOSED, State.RESET):
            with self._cond:
                self._loss_count += 1
                self._cond.notify_all()

    def _on_event(self, event) -> None:
        with self._cond:
            if event.type == EventType.CIRC:
                self._on_circuit_event(event)
            elif event.type == EventType.STREAM:
                self._on_stream_event(event)
            self._cond.notify_all()

    def _on_circuit_event(self, event) -> None:
        circuit_id = str(event.id)
        if event.status == "BUILT" and event.path:
            self._built[circuit_id] = _path(event.path)
        else:
            self._built.pop(circuit_id, None)

    def _on_stream_event(self, event) -> None:
        stream_id = str(event.id)
        trace = self._stream_owner.get(stream_id)
        if trace is None:
            username = (getattr(event, "keyword_args", None) or {}).get("SOCKS_USERNAME")
            trace = self._traces.get(username)
            if trace is None:
                return
            self._stream_owner[stream_id] = trace
            trace.stream_ids.add(stream_id)
        # NEW and SENTCONNECT only show an attempt; SUCCEEDED confirms the circuit.
        if event.status == "SUCCEEDED" and event.circ_id:
            circuit_id = str(event.circ_id)
            trace.succeeded[circuit_id] = self._built.get(circuit_id)


def _loopback_socks_proxy(controller: Controller) -> str | None:
    """The SOCKS listener of the Tor instance behind this control port, if bound to loopback."""
    try:
        listeners = controller.get_listeners(Listener.SOCKS)
    except (ControllerError, SocketError, OSError):
        return None
    for address, port in listeners:
        if address in ("127.0.0.1", "::1"):
            return socks_proxy_url(address, port)
    return None


def _path(path) -> Path:
    return tuple((fingerprint, nickname) for fingerprint, nickname in path)


def _format_hop(fingerprint: str, nickname: str | None) -> str:
    return f"${fingerprint}~{nickname}" if nickname else f"${fingerprint}"


def _unverified(reason: str, source: str = SOURCE_UNCORRELATED, circuit_id: str | None = None) -> CircuitInfo:
    return CircuitInfo(source=source, attribution_reason=reason, circuit_id=circuit_id)


def _close_quietly(controller: Controller) -> None:
    try:
        controller.close()
    except Exception:
        pass
