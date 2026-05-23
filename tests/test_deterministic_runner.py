"""Tests for the deterministic constant-rate HTTP workload."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workloads.http import deterministic_runner as runner_mod
from workloads.http.deterministic_runner import run_constant_rate


@pytest.fixture
def instant_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Patch time.sleep to a no-op and record its args. Tests stay fast."""
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(runner_mod, "time_sleep", fake_sleep)
    return sleeps


class TestRunConstantRate:
    def test_success_all(self, instant_sleep: list[float]) -> None:
        calls = {"n": 0}

        def send_once() -> None:
            calls["n"] += 1

        stats = run_constant_rate(send_once=send_once, rate_rps=5, duration_s=1, warmup_requests=2)
        # 2 warmup + 5 measured = 7 send calls.
        assert calls["n"] == 7
        assert stats["requests"] == pytest.approx(5.0)
        assert stats["successes"] == pytest.approx(5.0)
        assert stats["failures"] == pytest.approx(0.0)
        assert stats["error_rate"] == pytest.approx(0.0)
        assert stats["scheduled_rps"] == pytest.approx(5.0)
        assert stats["duration_s"] == pytest.approx(1.0)
        assert stats["rps"] > 0.0

    def test_all_failures(self, instant_sleep: list[float]) -> None:
        def send_once() -> None:
            raise RuntimeError("boom")

        stats = run_constant_rate(send_once=send_once, rate_rps=4, duration_s=1)
        assert stats["requests"] == pytest.approx(4.0)
        assert stats["successes"] == pytest.approx(0.0)
        assert stats["failures"] == pytest.approx(4.0)
        assert stats["error_rate"] == pytest.approx(1.0)
        assert stats["mean_ms"] == pytest.approx(0.0)
        assert stats["p95_ms"] == pytest.approx(0.0)

    def test_partial_failures(self, instant_sleep: list[float]) -> None:
        idx = {"n": 0}

        def send_once() -> None:
            idx["n"] += 1
            if idx["n"] % 2 == 0:
                raise RuntimeError("flap")

        stats = run_constant_rate(send_once=send_once, rate_rps=6, duration_s=1)
        assert stats["requests"] == pytest.approx(6.0)
        assert stats["successes"] == pytest.approx(3.0)
        assert stats["failures"] == pytest.approx(3.0)
        assert stats["error_rate"] == pytest.approx(0.5)

    @pytest.mark.parametrize("rate,duration", [(1, 1), (10, 2), (100, 1)])
    def test_total_requests_equals_rate_times_duration(
        self, instant_sleep: list[float], rate: int, duration: int
    ) -> None:
        calls = {"n": 0}

        def send_once() -> None:
            calls["n"] += 1

        stats = run_constant_rate(send_once=send_once, rate_rps=rate, duration_s=duration)
        assert calls["n"] == rate * duration
        assert stats["requests"] == pytest.approx(float(rate * duration))

    def test_zero_warmup(self, instant_sleep: list[float]) -> None:
        calls = {"n": 0}

        def send_once() -> None:
            calls["n"] += 1

        stats = run_constant_rate(send_once=send_once, rate_rps=3, duration_s=1)
        # Default warmup_requests=0.
        assert calls["n"] == 3
        assert stats["successes"] == pytest.approx(3.0)

    def test_invalid_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="rate_rps must be > 0"):
            run_constant_rate(send_once=lambda: None, rate_rps=0, duration_s=1)
        with pytest.raises(ValueError, match="rate_rps must be > 0"):
            run_constant_rate(send_once=lambda: None, rate_rps=-1, duration_s=1)

    def test_invalid_duration_raises(self) -> None:
        with pytest.raises(ValueError, match="duration_s must be > 0"):
            run_constant_rate(send_once=lambda: None, rate_rps=1, duration_s=0)
        with pytest.raises(ValueError, match="duration_s must be > 0"):
            run_constant_rate(send_once=lambda: None, rate_rps=1, duration_s=-1)

    def test_latency_capture(self, instant_sleep: list[float]) -> None:
        # Inject a perf_counter that increments per call so latency > 0.
        ticks = iter([float(i) * 0.001 for i in range(1000)])

        def fake_perf() -> float:
            return next(ticks)

        # Use the runner module's perf_counter binding.
        import contextlib

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                pytest.MonkeyPatch.context()  # type: ignore[attr-defined]
            )
            # Easier: patch directly via runner_mod attribute.
            orig = runner_mod.time_perf_counter
            runner_mod.time_perf_counter = fake_perf  # type: ignore[assignment]
            try:
                stats = run_constant_rate(send_once=lambda: None, rate_rps=2, duration_s=1)
            finally:
                runner_mod.time_perf_counter = orig  # type: ignore[assignment]

        assert stats["mean_ms"] >= 0.0
        assert stats["p95_ms"] >= 0.0

    def test_scheduling_uses_sleep_when_running_ahead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Make perf_counter advance very slowly so the scheduler will sleep.
        # Each call to perf_counter returns 0.0; sleep amounts should reflect
        # the period (1/rate).
        monkeypatch.setattr(runner_mod, "time_perf_counter", lambda: 0.0)

        sleeps: list[float] = []
        monkeypatch.setattr(runner_mod, "time_sleep", lambda s: sleeps.append(s))

        run_constant_rate(send_once=lambda: None, rate_rps=4, duration_s=1)
        # 4 requests at 0.25s spacing → at least one sleep should be ~0.25.
        # The scheduler sleeps `scheduled - now` = i * 0.25 each iteration.
        assert any(s > 0.0 for s in sleeps)
