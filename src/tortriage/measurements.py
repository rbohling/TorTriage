from __future__ import annotations

import time

import requests

from .models import MeasurementResult


DEFAULT_TOR_PROXY = "socks5h://127.0.0.1:9050"


def run_measurement(
    sample_url: str,
    *,
    timeout_seconds: float = 15.0,
    tor_proxy: str = DEFAULT_TOR_PROXY,
    max_download_bytes: int = 512 * 1024,
) -> MeasurementResult:
    proxies = {"http": tor_proxy, "https": tor_proxy}
    start = time.perf_counter()
    first_byte: float | None = None
    bytes_downloaded = 0

    try:
        with requests.get(sample_url, stream=True, timeout=timeout_seconds, proxies=proxies) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                if first_byte is None:
                    first_byte = time.perf_counter()
                bytes_downloaded += len(chunk)
                if bytes_downloaded >= max_download_bytes:
                    break
    except Exception:
        return MeasurementResult(rtt_ms=None, throughput_mbps=None, sample_url=sample_url)

    end = time.perf_counter()
    rtt_ms = round((first_byte - start) * 1000, 2) if first_byte else None
    transfer_time = max(end - (first_byte or start), 1e-6)
    throughput_mbps = round((bytes_downloaded * 8) / transfer_time / 1_000_000, 4)
    return MeasurementResult(rtt_ms=rtt_ms, throughput_mbps=throughput_mbps, sample_url=sample_url)
