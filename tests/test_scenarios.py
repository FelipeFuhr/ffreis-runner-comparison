"""Tests for _load_scenarios and _prepare_scenario_model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import write_scenario

from orchestrator.main import _load_scenarios, _prepare_scenario_model


class TestLoadScenarios:
    def test_discovers_all_scenarios(self, comparison_root: Path) -> None:
        write_scenario(comparison_root, "alpha")
        write_scenario(comparison_root, "beta")
        result = _load_scenarios(comparison_root, "all")
        ids = [s["id"] for s in result]
        assert ids == ["alpha", "beta"]

    def test_selective_picks_named_only(self, comparison_root: Path) -> None:
        write_scenario(comparison_root, "alpha")
        write_scenario(comparison_root, "beta")
        write_scenario(comparison_root, "gamma")
        result = _load_scenarios(comparison_root, "alpha,gamma")
        ids = [s["id"] for s in result]
        assert ids == ["alpha", "gamma"]

    def test_skips_disabled(self, comparison_root: Path) -> None:
        write_scenario(comparison_root, "alpha", enabled=False)
        write_scenario(comparison_root, "beta")
        result = _load_scenarios(comparison_root, "all")
        ids = [s["id"] for s in result]
        assert ids == ["beta"]

    def test_missing_id_raises(self, comparison_root: Path) -> None:
        write_scenario(comparison_root, "alpha")
        with pytest.raises(RuntimeError, match="Unknown scenario"):
            _load_scenarios(comparison_root, "ghost")

    def test_no_scenarios_raises(self, comparison_root: Path) -> None:
        with pytest.raises(RuntimeError, match="No scenarios found"):
            _load_scenarios(comparison_root, "all")

    def test_invalid_yaml_raises(self, comparison_root: Path) -> None:
        folder = comparison_root / "scenarios" / "bad"
        folder.mkdir(parents=True)
        # YAML that parses to a list, not a dict.
        (folder / "scenario.yaml").write_text("- item1\n- item2\n")
        with pytest.raises(RuntimeError, match="Invalid scenario.yaml"):
            _load_scenarios(comparison_root, "all")

    def test_scenario_metadata_attached(self, comparison_root: Path) -> None:
        write_scenario(comparison_root, "alpha")
        [scenario] = _load_scenarios(comparison_root, "all")
        assert scenario["id"] == "alpha"
        assert scenario["_folder"] == comparison_root / "scenarios" / "alpha"

    def test_strips_whitespace_in_selection(self, comparison_root: Path) -> None:
        write_scenario(comparison_root, "alpha")
        write_scenario(comparison_root, "beta")
        # Spaces and trailing commas should be tolerated.
        result = _load_scenarios(comparison_root, " alpha , beta , ")
        assert [s["id"] for s in result] == ["alpha", "beta"]

    def test_directory_without_scenario_yaml_ignored(self, comparison_root: Path) -> None:
        (comparison_root / "scenarios" / "alpha").mkdir(parents=True)
        (comparison_root / "scenarios" / "stray").mkdir(parents=True)
        write_scenario(comparison_root, "real")
        result = _load_scenarios(comparison_root, "all")
        # "alpha" had no scenario.yaml; "stray" also; "real" has both.
        # But write_scenario also created scenario.yaml for "alpha"? No: the
        # alpha mkdir above is bare. Verify only "real" loads.
        assert [s["id"] for s in result] == ["real"]


class TestPrepareScenarioModel:
    def test_no_model_section_is_noop(self, hub_root: Path) -> None:
        folder = hub_root / "scenarios" / "alpha"
        folder.mkdir(parents=True)
        scenario: dict[str, Any] = {"_folder": folder}
        # Should not raise.
        _prepare_scenario_model(hub_root, scenario)

    def test_non_dict_model_is_noop(self, hub_root: Path) -> None:
        folder = hub_root / "scenarios" / "alpha"
        folder.mkdir(parents=True)
        scenario: dict[str, Any] = {"_folder": folder, "model": "not-a-dict"}
        _prepare_scenario_model(hub_root, scenario)

    def test_source_copies_file_to_runtime_path(self, hub_root: Path) -> None:
        folder = hub_root / "scenarios" / "alpha"
        folder.mkdir(parents=True)
        (folder / "src.onnx").write_bytes(b"onnx-content")
        runtime_dir = hub_root / "runtime"
        scenario = {
            "_folder": folder,
            "model": {
                "source": "src.onnx",
                "runtime_path": str(runtime_dir / "model.onnx"),
            },
        }
        _prepare_scenario_model(hub_root, scenario)
        assert (runtime_dir / "model.onnx").read_bytes() == b"onnx-content"

    def test_prepare_runs_subprocess(self, hub_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_check_call(cmd: list[str], *, cwd: Path) -> int:
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            return 0

        monkeypatch.setattr("orchestrator.main.subprocess_check_call", fake_check_call)
        folder = hub_root / "scenarios" / "alpha"
        folder.mkdir(parents=True)
        scenario = {
            "_folder": folder,
            "model": {
                "prepare": {
                    "cmd": ["python", "build.py"],
                    "cwd": "scenarios/alpha",
                }
            },
        }
        _prepare_scenario_model(hub_root, scenario)
        assert captured["cmd"] == ["python", "build.py"]
        assert captured["cwd"] == hub_root / "scenarios/alpha"

    def test_prepare_with_invalid_cmd_raises(self, hub_root: Path) -> None:
        folder = hub_root / "scenarios" / "alpha"
        folder.mkdir(parents=True)
        scenario = {
            "_folder": folder,
            "model": {"prepare": {"cmd": "not-a-list", "cwd": "scenarios/alpha"}},
        }
        with pytest.raises(RuntimeError, match="Invalid model.prepare"):
            _prepare_scenario_model(hub_root, scenario)
