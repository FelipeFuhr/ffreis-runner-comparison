"""Tests for the perf/parity check orchestration helpers in orchestrator.main.

Covers _parse_request_cfg, _collect_perf_stats, _compute_ratio_summary,
_run_perf_check, and _run_scenario_checks -- the pieces between scenario
loading (test_scenarios.py) and the top-level main()/_run_scenario
orchestration (test_run_scenario_main.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from orchestrator import main as main_mod
from orchestrator.main import (
    _collect_perf_stats,
    _compute_ratio_summary,
    _parse_request_cfg,
    _run_perf_check,
    _run_scenario_checks,
)


class TestParseRequestCfg:
    def test_extracts_all_fields(self, tmp_path: Path) -> None:
        (tmp_path / "payload.csv").write_bytes(b"1,2,3\n")
        scenario = {
            "_folder": tmp_path,
            "request": {
                "path": "/predict",
                "health_path": "/live",
                "content_type": "application/json",
                "accept": "text/plain",
                "payload_file": "payload.csv",
            },
        }
        path, health_path, content_type, accept, payload = _parse_request_cfg("s1", scenario)
        assert path == "/predict"
        assert health_path == "/live"
        assert content_type == "application/json"
        assert accept == "text/plain"
        assert payload == b"1,2,3\n"

    def test_defaults_applied_when_fields_omitted(self, tmp_path: Path) -> None:
        (tmp_path / "payload.csv").write_bytes(b"x")
        scenario = {"_folder": tmp_path, "request": {"payload_file": "payload.csv"}}
        path, health_path, content_type, accept, _ = _parse_request_cfg("s1", scenario)
        assert path == "/invocations"
        assert health_path == "/healthz"
        assert content_type == "text/csv"
        assert accept == "application/json"

    def test_non_dict_request_section_raises(self, tmp_path: Path) -> None:
        scenario = {"_folder": tmp_path, "request": "not-a-dict"}
        with pytest.raises(RuntimeError, match="Invalid request section"):
            _parse_request_cfg("s1", scenario)

    def test_missing_payload_file_raises(self, tmp_path: Path) -> None:
        scenario: dict[str, Any] = {"_folder": tmp_path, "request": {}}
        with pytest.raises(RuntimeError, match="must define request.payload_file"):
            _parse_request_cfg("s1", scenario)


class TestCollectPerfStats:
    def test_deterministic_http_runner_dispatches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []

        def fake_det(**kwargs: Any) -> dict[str, float]:
            calls.append(kwargs)
            return {"mean_ms": 1.0, "p95_ms": 2.0, "rps": 3.0}

        monkeypatch.setattr(main_mod, "_measure_latency_deterministic", fake_det)
        stats = _collect_perf_stats(
            scenario_id="s1",
            service_bases={"a": "http://a", "b": "http://b"},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
            perf_runner="deterministic_http",
            warmup_requests=1,
            measured_requests=1,
            rate_rps=10,
            duration_s=1,
        )
        assert set(stats.keys()) == {"a", "b"}
        assert len(calls) == 2

    def test_request_count_runner_dispatches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []

        def fake_measure(**kwargs: Any) -> dict[str, float]:
            calls.append(kwargs)
            return {"mean_ms": 1.0, "p95_ms": 2.0, "rps": 3.0}

        monkeypatch.setattr(main_mod, "_measure_latency", fake_measure)
        stats = _collect_perf_stats(
            scenario_id="s1",
            service_bases={"a": "http://a"},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
            perf_runner="request_count",
            warmup_requests=1,
            measured_requests=5,
            rate_rps=10,
            duration_s=1,
        )
        assert stats == {"a": {"mean_ms": 1.0, "p95_ms": 2.0, "rps": 3.0}}
        assert len(calls) == 1

    def test_unknown_perf_runner_raises(self) -> None:
        with pytest.raises(RuntimeError, match="unknown perf_runner"):
            _collect_perf_stats(
                scenario_id="s1",
                service_bases={"a": "http://a"},
                path="/invocations",
                payload=b"x",
                content_type="text/csv",
                accept="application/json",
                perf_runner="bogus",
                warmup_requests=1,
                measured_requests=1,
                rate_rps=10,
                duration_s=1,
            )


class TestComputeRatioSummary:
    PERF_STATS = {
        "baseline": {"mean_ms": 10.0, "p95_ms": 20.0, "rps": 5.0},
        "candidate": {"mean_ms": 15.0, "p95_ms": 25.0, "rps": 4.0},
    }

    def test_computes_ratios_excluding_baseline(self) -> None:
        summary = _compute_ratio_summary(
            scenario_id="s1",
            perf_stats=self.PERF_STATS,
            baseline_service="baseline",
            max_p95_ratio=10.0,
            max_mean_ratio=10.0,
        )
        assert "baseline" not in summary
        assert summary["candidate"]["ratio_mean"] == pytest.approx(1.5)
        assert summary["candidate"]["ratio_p95"] == pytest.approx(1.25)

    def test_p95_ratio_over_threshold_raises(self) -> None:
        with pytest.raises(RuntimeError, match="failed p95 ratio"):
            _compute_ratio_summary(
                scenario_id="s1",
                perf_stats=self.PERF_STATS,
                baseline_service="baseline",
                max_p95_ratio=1.1,
                max_mean_ratio=10.0,
            )

    def test_mean_ratio_over_threshold_raises(self) -> None:
        with pytest.raises(RuntimeError, match="failed mean ratio"):
            _compute_ratio_summary(
                scenario_id="s1",
                perf_stats=self.PERF_STATS,
                baseline_service="baseline",
                max_p95_ratio=10.0,
                max_mean_ratio=1.1,
            )

    def test_zero_baseline_defaults_ratio_to_one(self) -> None:
        stats = {
            "baseline": {"mean_ms": 0.0, "p95_ms": 0.0, "rps": 0.0},
            "candidate": {"mean_ms": 5.0, "p95_ms": 5.0, "rps": 1.0},
        }
        summary = _compute_ratio_summary(
            scenario_id="s1",
            perf_stats=stats,
            baseline_service="baseline",
            max_p95_ratio=10.0,
            max_mean_ratio=10.0,
        )
        assert summary["candidate"]["ratio_mean"] == pytest.approx(1.0)
        assert summary["candidate"]["ratio_p95"] == pytest.approx(1.0)


class TestRunPerfCheck:
    def test_happy_path_returns_expected_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            main_mod,
            "_collect_perf_stats",
            lambda **_k: {
                "a": {"mean_ms": 10.0, "p95_ms": 20.0, "rps": 5.0},
                "b": {"mean_ms": 12.0, "p95_ms": 22.0, "rps": 5.0},
            },
        )
        result = _run_perf_check(
            scenario_id="s1",
            service_bases={"a": "http://a", "b": "http://b"},
            compare_cfg={"baseline_service": "a"},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )
        assert result["runner"] == "request_count"
        assert result["baseline_service"] == "a"
        ratios = result["ratios"]
        assert isinstance(ratios, dict)
        assert "b" in ratios

    def test_baseline_service_defaults_to_min_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            main_mod,
            "_collect_perf_stats",
            lambda **_k: {
                "zeta": {"mean_ms": 10.0, "p95_ms": 20.0, "rps": 5.0},
                "alpha": {"mean_ms": 10.0, "p95_ms": 20.0, "rps": 5.0},
            },
        )
        result = _run_perf_check(
            scenario_id="s1",
            service_bases={"zeta": "http://z", "alpha": "http://a"},
            compare_cfg={},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )
        assert result["baseline_service"] == "alpha"

    def test_unconfigured_baseline_service_raises(self) -> None:
        with pytest.raises(RuntimeError, match="is not configured"):
            _run_perf_check(
                scenario_id="s1",
                service_bases={"a": "http://a"},
                compare_cfg={"baseline_service": "ghost"},
                path="/invocations",
                payload=b"x",
                content_type="text/csv",
                accept="application/json",
            )


class TestRunScenarioChecks:
    def test_parity_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(main_mod, "_run_parity", lambda **_k: calls.append("parity"))
        result = _run_scenario_checks(
            scenario_id="s1",
            checks={"parity"},
            service_bases={"a": "http://a"},
            compare_cfg={},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )
        assert calls == ["parity"]
        assert result == {"scenario": "s1", "parity": "ok"}

    def test_property_only_is_a_scaffold_noop(self) -> None:
        result = _run_scenario_checks(
            scenario_id="s1",
            checks={"property"},
            service_bases={"a": "http://a"},
            compare_cfg={},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )
        assert result == {"scenario": "s1", "property": "scaffold"}

    def test_perf_only_delegates_and_embeds_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main_mod, "_run_perf_check", lambda **_k: {"runner": "x"})
        result = _run_scenario_checks(
            scenario_id="s1",
            checks={"perf"},
            service_bases={"a": "http://a"},
            compare_cfg={},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )
        assert result == {"scenario": "s1", "perf": {"runner": "x"}}

    def test_all_checks_combine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(main_mod, "_run_parity", lambda **_k: None)
        monkeypatch.setattr(main_mod, "_run_perf_check", lambda **_k: {"runner": "x"})
        result = _run_scenario_checks(
            scenario_id="s1",
            checks={"parity", "property", "perf"},
            service_bases={"a": "http://a"},
            compare_cfg={},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )
        assert result["parity"] == "ok"
        assert result["property"] == "scaffold"
        assert result["perf"] == {"runner": "x"}

    def test_parity_services_list_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_parity(**kwargs: Any) -> None:
            captured.update(kwargs)

        monkeypatch.setattr(main_mod, "_run_parity", fake_parity)
        _run_scenario_checks(
            scenario_id="s1",
            checks={"parity"},
            service_bases={"a": "http://a", "b": "http://b"},
            compare_cfg={"parity_services": ["a", "b"]},
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )
        assert captured["parity_services"] == ["a", "b"]
