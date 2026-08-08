"""Tests for _run_scenario and main() -- the top-level orchestration in
orchestrator.main. ModeRunner/wait_http_ok/_prepare_scenario_model are
mocked; no real subprocess or HTTP call happens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator import main as main_mod
from orchestrator.main import _run_scenario, main


class FakeModeRunner:
    """Stand-in for orchestrator.startup.ModeRunner as a context manager."""

    last_instance: "FakeModeRunner | None" = None

    def __init__(self, *, hub_root: Path, mode: str, active_services: set[str] | None) -> None:
        self.hub_root = hub_root
        self.mode = mode
        self.active_services = active_services
        self.config = {
            "services": {
                "python": {"base_url": "http://python"},
                "rust": {"base_url": "http://rust"},
            }
        }
        FakeModeRunner.last_instance = self

    def __enter__(self) -> "FakeModeRunner":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class TestRunScenario:
    def _scenario(self, folder: Path) -> dict[str, object]:
        return {"id": "s1", "_folder": folder}

    def _patch_common(self, monkeypatch: pytest.MonkeyPatch, waited: list[str]) -> None:
        monkeypatch.setattr(main_mod, "ModeRunner", FakeModeRunner)
        monkeypatch.setattr(main_mod, "_prepare_scenario_model", lambda *_a, **_k: None)
        monkeypatch.setattr(main_mod, "wait_http_ok", lambda url: waited.append(url))
        monkeypatch.setattr(
            main_mod,
            "_parse_request_cfg",
            lambda *_a, **_k: ("/invocations", "/healthz", "text/csv", "application/json", b"x"),
        )

    def test_waits_on_every_active_service_health(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        waited: list[str] = []
        self._patch_common(monkeypatch, waited)
        monkeypatch.setattr(
            main_mod, "_run_scenario_checks", lambda **_k: {"scenario": "s1", "parity": "ok"}
        )
        _run_scenario(
            scenario=self._scenario(tmp_path),
            hub_root=tmp_path,
            mode="container",
            checks={"parity"},
        )
        assert sorted(waited) == ["http://python/healthz", "http://rust/healthz"]

    def test_active_services_filters_service_bases(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        waited: list[str] = []
        self._patch_common(monkeypatch, waited)
        captured: dict[str, Any] = {}

        def fake_checks(**kwargs: Any) -> dict[str, object]:
            captured.update(kwargs)
            return {"scenario": "s1"}

        monkeypatch.setattr(main_mod, "_run_scenario_checks", fake_checks)
        scenario = self._scenario(tmp_path)
        scenario["compare"] = {"active_services": ["rust"]}
        _run_scenario(scenario=scenario, hub_root=tmp_path, mode="native", checks={"parity"})
        assert waited == ["http://rust/healthz"]
        assert set(captured["service_bases"].keys()) == {"rust"}

    def test_result_passed_through_from_run_scenario_checks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        waited: list[str] = []
        self._patch_common(monkeypatch, waited)
        monkeypatch.setattr(
            main_mod, "_run_scenario_checks", lambda **_k: {"scenario": "s1", "parity": "ok"}
        )
        result = _run_scenario(
            scenario=self._scenario(tmp_path),
            hub_root=tmp_path,
            mode="container",
            checks={"parity"},
        )
        assert result == {"scenario": "s1", "parity": "ok"}

    def test_non_dict_compare_cfg_defaults_to_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        waited: list[str] = []
        self._patch_common(monkeypatch, waited)
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            main_mod,
            "_run_scenario_checks",
            lambda **k: captured.update(k) or {"scenario": "s1"},
        )
        scenario = self._scenario(tmp_path)
        scenario["compare"] = "not-a-dict"
        _run_scenario(scenario=scenario, hub_root=tmp_path, mode="container", checks={"parity"})
        assert captured["compare_cfg"] == {}


class TestMain:
    def test_writes_report_with_results(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # main() derives hub_root from __file__'s grandparents and passes it to
        # _load_scenarios/_run_scenario -- both mocked below, so the exact
        # hub_root value main() computes internally doesn't matter here.
        report_out = tmp_path / "report.json"
        monkeypatch.setattr(
            main_mod, "_load_scenarios", lambda root, selected: [{"id": "alpha", "_folder": root}]
        )
        monkeypatch.setattr(
            main_mod,
            "_run_scenario",
            lambda **_k: {"scenario": "alpha", "parity": "ok"},
        )
        monkeypatch.setattr(
            "sys.argv",
            [
                "prog",
                "--mode",
                "container",
                "--checks",
                "parity",
                "--scenario",
                "all",
                "--report-out",
                str(report_out),
            ],
        )
        main()
        written = json.loads(report_out.read_text(encoding="utf-8"))
        assert written["mode"] == "container"
        assert written["checks"] == ["parity"]
        assert written["results"] == [{"scenario": "alpha", "parity": "ok"}]

    def test_checks_arg_parsed_as_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report_out = tmp_path / "report.json"
        monkeypatch.setattr(main_mod, "_load_scenarios", lambda root, selected: [])
        captured: dict[str, Any] = {}

        def fake_run_scenario(**kwargs: Any) -> dict[str, object]:
            captured.update(kwargs)
            return {}

        monkeypatch.setattr(main_mod, "_run_scenario", fake_run_scenario)
        monkeypatch.setattr(
            "sys.argv",
            [
                "prog",
                "--mode",
                "native",
                "--checks",
                "parity, perf ,",
                "--report-out",
                str(report_out),
            ],
        )
        main()
        written = json.loads(report_out.read_text(encoding="utf-8"))
        assert written["checks"] == ["parity", "perf"]
