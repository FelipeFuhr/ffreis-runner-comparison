"""Tests for _measure_latency and _measure_latency_deterministic."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import FakeResponse

from orchestrator import main as main_mod
from orchestrator.main import _measure_latency, _measure_latency_deterministic


def _patch_post(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float) -> Any:
        calls.append(url)
        return FakeResponse(json_data={"ok": True})

    monkeypatch.setattr(main_mod, "httpx_post", fake_post)


class TestMeasureLatency:
    def test_returns_required_stat_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        _patch_post(monkeypatch, calls)
        stats = _measure_latency(
            base_url="http://x",
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
            warmup_requests=2,
            measured_requests=3,
        )
        assert set(stats.keys()) >= {"mean_ms", "p95_ms", "rps"}
        # 2 warmup + 3 measured = 5 calls.
        assert len(calls) == 5

    def test_zero_warmup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        _patch_post(monkeypatch, calls)
        stats = _measure_latency(
            base_url="http://x",
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
            warmup_requests=0,
            measured_requests=2,
        )
        assert len(calls) == 2
        assert stats["mean_ms"] >= 0.0

    def test_propagates_http_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fail(*_a: Any, **_k: Any) -> Any:
            return FakeResponse(status_code=500)

        monkeypatch.setattr(main_mod, "httpx_post", fail)
        with pytest.raises(RuntimeError, match="HTTP 500"):
            _measure_latency(
                base_url="http://x",
                path="/invocations",
                payload=b"x",
                content_type="text/csv",
                accept="application/json",
                warmup_requests=0,
                measured_requests=1,
            )


class TestMeasureLatencyDeterministic:
    def test_returns_deterministic_stats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        _patch_post(monkeypatch, calls)
        # Patch sleep so the test runs instantly.
        from workloads.http import deterministic_runner

        monkeypatch.setattr(deterministic_runner, "time_sleep", lambda _s: None)

        stats = _measure_latency_deterministic(
            base_url="http://x",
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
            warmup_requests=1,
            rate_rps=2,
            duration_s=1,
        )
        assert "successes" in stats
        assert "failures" in stats
        assert stats["successes"] == pytest.approx(2.0)
        # 1 warmup + 2 measured = 3 calls.
        assert len(calls) == 3
