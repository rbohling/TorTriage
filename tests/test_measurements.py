import unittest
from unittest.mock import patch

from tortriage.measurements import run_measurement


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield b"a" * 8192
        yield b"b" * 8192


class _FakeSession:
    def __init__(self) -> None:
        self.trust_env = True
        self.proxies = {}
        self.last_get = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str, stream: bool, timeout: float):
        self.last_get = {"url": url, "stream": stream, "timeout": timeout}
        return _FakeResponse()


class MeasurementTests(unittest.TestCase):
    def test_fails_closed_for_non_tor_proxy_scheme(self) -> None:
        result = run_measurement("https://example.com", tor_proxy="http://127.0.0.1:9050")
        self.assertIsNone(result.rtt_ms)
        self.assertIsNone(result.throughput_mbps)

    def test_uses_session_without_env_fallback(self) -> None:
        fake_session = _FakeSession()
        with patch("tortriage.measurements.requests.Session", return_value=fake_session):
            result = run_measurement("https://example.com", timeout_seconds=2.0)

        self.assertFalse(fake_session.trust_env)
        self.assertEqual(fake_session.proxies["http"], "socks5h://127.0.0.1:9050")
        self.assertEqual(fake_session.proxies["https"], "socks5h://127.0.0.1:9050")
        self.assertEqual(fake_session.last_get, {"url": "https://example.com", "stream": True, "timeout": 2.0})
        self.assertIsNotNone(result.rtt_ms)
        self.assertIsNotNone(result.throughput_mbps)


if __name__ == "__main__":
    unittest.main()
