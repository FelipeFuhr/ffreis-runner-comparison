"""ModeRunner tests for container and native modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from orchestrator import startup as startup_mod
from orchestrator.startup import ModeRunner


def _write_mode_config(comparison_root: Path, mode: str, config: dict[str, Any]) -> Path:
    config_path = comparison_root / "config" / "modes" / f"{mode}.yaml"
    config_path.write_text(yaml.safe_dump(config))
    return config_path


class _FakeProcess:
    """Stand-in for subprocess.Popen."""

    def __init__(self, *, returncode: int | None = None, wait_raises: bool = False) -> None:
        self._returncode = returncode
        self.wait_raises = wait_raises
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        self._returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self._returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.wait_raises:
            raise startup_mod.subprocess_TimeoutExpired(cmd="x", timeout=timeout or 0)
        return self._returncode or 0


class TestContainerMode:
    def test_enter_runs_compose_up(
        self, hub_root: Path, comparison_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_mode_config(comparison_root, "container", {"compose_file": "docker-compose.yml"})
        calls: list[tuple[list[str], Path]] = []
        monkeypatch.setattr(
            startup_mod,
            "subprocess_check_call",
            lambda cmd, cwd=None: calls.append((cmd, cwd)),  # type: ignore[arg-type]
        )
        monkeypatch.setattr(
            startup_mod,
            "subprocess_call",
            lambda cmd, cwd=None: calls.append((cmd, cwd)),  # type: ignore[arg-type]
        )

        with ModeRunner(hub_root=hub_root, mode="container"):
            pass

        # First call: up; second call: down on exit.
        assert calls[0][0] == [
            "./scripts/compose.sh",
            "-f",
            "docker-compose.yml",
            "up",
            "-d",
            "--build",
        ]
        assert calls[1][0] == [
            "./scripts/compose.sh",
            "-f",
            "docker-compose.yml",
            "down",
            "--remove-orphans",
        ]


class TestNativeMode:
    def test_setup_steps_run_before_processes(
        self, hub_root: Path, comparison_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_mode_config(
            comparison_root,
            "native",
            {
                "setup": [
                    {"cmd": ["echo", "setup1"], "cwd": "."},
                ],
                "processes": [
                    {"cmd": ["echo", "proc1"], "cwd": ".", "service": "svc"},
                ],
                "services": {},
            },
        )
        setup_calls: list[list[str]] = []
        popen_calls: list[list[str]] = []

        monkeypatch.setattr(
            startup_mod,
            "subprocess_check_call",
            lambda cmd, cwd=None, env=None: setup_calls.append(cmd),  # type: ignore[arg-type]
        )

        fake_procs: list[_FakeProcess] = []

        def fake_popen(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> _FakeProcess:
            popen_calls.append(cmd)
            p = _FakeProcess()
            fake_procs.append(p)
            return p

        monkeypatch.setattr(startup_mod, "subprocess_Popen", fake_popen)

        with ModeRunner(hub_root=hub_root, mode="native"):
            pass

        assert setup_calls == [["echo", "setup1"]]
        assert popen_calls == [["echo", "proc1"]]
        # Process should have been cleaned up on exit.
        assert fake_procs[0].terminate_calls == 1
        assert fake_procs[0].wait_calls == 1

    def test_active_services_filter(
        self, hub_root: Path, comparison_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_mode_config(
            comparison_root,
            "native",
            {
                "setup": [],
                "processes": [
                    {"cmd": ["a"], "cwd": ".", "service": "python"},
                    {"cmd": ["b"], "cwd": ".", "service": "rust"},
                    {"cmd": ["c"], "cwd": ".", "service": "go"},
                ],
                "services": {},
            },
        )
        popen_cmds: list[list[str]] = []

        def fake_popen(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> _FakeProcess:
            popen_cmds.append(cmd)
            return _FakeProcess()

        monkeypatch.setattr(startup_mod, "subprocess_Popen", fake_popen)

        with ModeRunner(hub_root=hub_root, mode="native", active_services={"python", "rust"}):
            pass

        # "go" should be filtered out.
        assert popen_cmds == [["a"], ["b"]]

    def test_process_kill_on_timeout(
        self, hub_root: Path, comparison_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_mode_config(
            comparison_root,
            "native",
            {
                "setup": [],
                "processes": [
                    {"cmd": ["server"], "cwd": ".", "service": "python"},
                ],
                "services": {},
            },
        )
        proc = _FakeProcess(wait_raises=True)

        monkeypatch.setattr(startup_mod, "subprocess_Popen", lambda *_a, **_k: proc)

        with ModeRunner(hub_root=hub_root, mode="native"):
            pass

        # Wait timed out → kill() should have been called.
        assert proc.kill_calls == 1

    def test_already_exited_process_not_terminated(
        self, hub_root: Path, comparison_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_mode_config(
            comparison_root,
            "native",
            {
                "setup": [],
                "processes": [
                    {"cmd": ["server"], "cwd": ".", "service": "python"},
                ],
                "services": {},
            },
        )
        # returncode=0 means already exited.
        proc = _FakeProcess(returncode=0)
        monkeypatch.setattr(startup_mod, "subprocess_Popen", lambda *_a, **_k: proc)

        with ModeRunner(hub_root=hub_root, mode="native"):
            pass

        assert proc.terminate_calls == 0
        # wait() still called for cleanup.
        assert proc.wait_calls == 1

    def test_config_loaded_from_yaml(self, hub_root: Path, comparison_root: Path) -> None:
        _write_mode_config(
            comparison_root,
            "native",
            {
                "setup": [],
                "processes": [],
                "services": {"foo": {"base_url": "http://foo:8000"}},
            },
        )
        runner = ModeRunner(hub_root=hub_root, mode="native")
        assert runner.config["services"]["foo"]["base_url"] == "http://foo:8000"
