"""Deterministic constant-rate HTTP benchmarking."""

from __future__ import annotations

import time
from statistics import mean
from typing import Callable


def _p95_ms(latencies_ms: list[float]) -> float:
    ordered = sorted(latencies_ms)
    if not ordered:
        return 0.0
    idx = int(round(0.95 * (len(ordered) - 1)))
    return ordered[idx]


def run_constant_rate(
    *,
    send_once: Callable[[], None],
    rate_rps: int,
    duration_s: int,
    warmup_requests: int = 0,
) -> dict[str, float]:
    """Run constant-rate benchmark and return summary statistics."""
    if rate_rps <= 0:
        raise ValueError(f"rate_rps must be > 0, got {rate_rps}")
    if duration_s <= 0:
        raise ValueError(f"duration_s must be > 0, got {duration_s}")

    for _ in range(warmup_requests):
        send_once()

    total_requests = rate_rps * duration_s
    period_s = 1.0 / float(rate_rps)
    start_all = time.perf_counter()
    latencies_ms: list[float] = []
    failures = 0

    for idx in range(total_requests):
        scheduled = start_all + (idx * period_s)
        now = time.perf_counter()
        if scheduled > now:
            time.sleep(scheduled - now)

        req_start = time.perf_counter()
        try:
            send_once()
            latencies_ms.append((time.perf_counter() - req_start) * 1000.0)
        except Exception:
            failures += 1

    elapsed = max(time.perf_counter() - start_all, 1e-12)
    success_count = len(latencies_ms)
    return {
        "requests": float(total_requests),
        "successes": float(success_count),
        "failures": float(failures),
        "error_rate": (float(failures) / float(total_requests)),
        "mean_ms": mean(latencies_ms) if latencies_ms else 0.0,
        "p95_ms": _p95_ms(latencies_ms),
        "rps": float(success_count) / elapsed,
        "scheduled_rps": float(rate_rps),
        "duration_s": float(duration_s),
    }
