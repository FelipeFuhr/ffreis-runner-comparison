"""Readiness helpers."""

from __future__ import annotations

from time import sleep as time_sleep
from time import time as time_time

from httpx import get as httpx_get


def wait_http_ok(url: str, timeout_s: float = 60.0) -> None:
    deadline = time_time() + timeout_s
    last_error: Exception | None = None
    while time_time() < deadline:
        try:
            response = httpx_get(url, timeout=3.0)
            if response.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time_sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")
