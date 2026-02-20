import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workloads.http.deterministic_runner import run_constant_rate


def test_run_constant_rate_success() -> None:
    calls = 0

    def send_once() -> None:
        nonlocal calls
        calls += 1

    stats = run_constant_rate(send_once=send_once, rate_rps=5, duration_s=1, warmup_requests=2)
    assert calls == 7
    assert stats["requests"] == 5.0
    assert stats["successes"] == 5.0
    assert stats["failures"] == 0.0
    assert stats["error_rate"] == 0.0
    assert stats["rps"] > 0.0


def test_run_constant_rate_failures() -> None:
    calls = 0

    def send_once() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    stats = run_constant_rate(send_once=send_once, rate_rps=4, duration_s=1)
    assert calls == 4
    assert stats["requests"] == 4.0
    assert stats["successes"] == 0.0
    assert stats["failures"] == 4.0
    assert stats["error_rate"] == 1.0
