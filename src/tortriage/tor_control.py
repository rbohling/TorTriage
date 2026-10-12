from __future__ import annotations

from collections.abc import Sequence

from .models import CircuitInfo


def _nickname(fingerprint: str, fallback: str = "unknown") -> str:
    return fingerprint[:12] if fingerprint else fallback


def get_current_circuit(
    controller_host: str = "127.0.0.1",
    controller_port: int = 9051,
    password: str | None = None,
) -> CircuitInfo:
    try:
        from stem import CircStatus
        from stem.control import Controller
    except Exception:
        return CircuitInfo(source="stem-not-installed")

    try:
        with Controller.from_port(address=controller_host, port=controller_port) as controller:
            if password:
                controller.authenticate(**{"password": password})
            else:
                controller.authenticate()

            built = [c for c in controller.get_circuits() if c.status == CircStatus.BUILT]
            if not built:
                return CircuitInfo(source="no-built-circuit")

            selected = max(built, key=lambda c: c.created)
            path: Sequence[tuple[str, str]] = selected.path
            if len(path) < 3:
                return CircuitInfo(source="incomplete-circuit")

            entry_fp, entry_name = path[0]
            middle_fp, middle_name = path[1]
            exit_fp, exit_name = path[-1]
            return CircuitInfo(
                entry=f"{entry_name} ({_nickname(entry_fp)})",
                middle=f"{middle_name} ({_nickname(middle_fp)})",
                exit=f"{exit_name} ({_nickname(exit_fp)})",
                source="control-port",
            )
    except Exception:
        return CircuitInfo(source="control-port-unavailable")
