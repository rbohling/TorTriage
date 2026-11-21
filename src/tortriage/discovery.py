"""Locate a local Tor client's ports when the user does not specify them."""

from __future__ import annotations

import socket

# System Tor, then Tor Browser.
SOCKS_PORTS = (9050, 9150)
CONTROL_PORTS = (9051, 9151)
LOOPBACK_HOST = "127.0.0.1"


def probe_socks(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if a SOCKS5 server answers a no-auth greeting; no connection is requested."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(b"\x05\x01\x00")
            reply = connection.recv(2)
    except OSError:
        return False
    return len(reply) == 2 and reply[0] == 5


def discover_socks_proxy(host: str = LOOPBACK_HOST, ports: tuple[int, ...] = SOCKS_PORTS) -> str | None:
    for port in ports:
        if probe_socks(host, port):
            return socks_proxy_url(host, port)
    return None


def socks_proxy_url(host: str, port: int) -> str:
    bracketed = f"[{host}]" if ":" in host else host
    return f"socks5h://{bracketed}:{port}"
