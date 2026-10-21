from __future__ import annotations

from .models import CircuitInfo


def get_current_circuit(
    controller_host: str = "127.0.0.1",
    controller_port: int = 9051,
    password: str | None = None,
) -> CircuitInfo:
    """Compatibility API: a circuit snapshot cannot identify a measurement's path.

    Do not query or select an arbitrary built circuit. STREAM events can identify
    a stream's circuit, but only after correlating that stream to our actual
    SOCKS connection. The current HTTP transport does not provide that evidence.
    """
    return CircuitInfo(source="measurement-stream-not-correlated")
