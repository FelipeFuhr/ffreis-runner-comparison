"""Shared fixtures and helpers for the runner-comparison test suite."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure the repo's source layout is on sys.path so `orchestrator` and
# `workloads` import cleanly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def hub_root(tmp_path: Path) -> Path:
    """A self-contained `hub_root` layout for scenario / mode tests.

    Creates:
        <root>/benchmarks/onnx-runner-comparison/scenarios/
        <root>/benchmarks/onnx-runner-comparison/config/modes/
    """
    bench = tmp_path / "benchmarks" / "onnx-runner-comparison"
    (bench / "scenarios").mkdir(parents=True)
    (bench / "config" / "modes").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def comparison_root(hub_root: Path) -> Path:
    return hub_root / "benchmarks" / "onnx-runner-comparison"


def write_scenario(
    root: Path,
    name: str,
    *,
    enabled: bool = True,
    payload: bytes | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Create a scenario directory with scenario.yaml and an optional payload.

    Returns the scenario folder path.
    """
    folder = root / "scenarios" / name
    folder.mkdir(parents=True, exist_ok=True)
    spec: dict[str, Any] = {
        "enabled": enabled,
        "request": {
            "path": "/invocations",
            "health_path": "/healthz",
            "content_type": "text/csv",
            "accept": "application/json",
            "payload_file": "payload.csv",
        },
    }
    if extra:
        spec.update(extra)
    (folder / "scenario.yaml").write_text(_dump_yaml(spec))
    if payload is not None:
        (folder / "payload.csv").write_bytes(payload)
    else:
        (folder / "payload.csv").write_bytes(b"a,b\n1,2\n")
    return folder


def _dump_yaml(data: Any) -> str:
    """Minimal YAML dump using PyYAML."""
    import yaml

    return yaml.safe_dump(data)


class FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, *, json_data: Any = None, status_code: int = 200) -> None:
        self._json = json_data
        self.status_code = status_code

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
