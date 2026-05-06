"""Startup/teardown for container and native modes."""

from __future__ import annotations

from contextlib import AbstractContextManager
from os import environ as os_environ
from pathlib import Path
from subprocess import Popen as subprocess_Popen
from subprocess import TimeoutExpired as subprocess_TimeoutExpired
from subprocess import call as subprocess_call
from subprocess import check_call as subprocess_check_call

from yaml import safe_load as yaml_safe_load


class ModeRunner(AbstractContextManager["ModeRunner"]):
    def __init__(
        self,
        hub_root: Path,
        mode: str,
        *,
        active_services: set[str] | None = None,
    ) -> None:
        self.hub_root = hub_root
        self.mode = mode
        self.active_services = active_services
        self.processes: list[subprocess_Popen[bytes]] = []
        config_file = (
            hub_root / "benchmarks" / "onnx-runner-comparison" / "config" / "modes" / f"{mode}.yaml"
        )
        self.config = yaml_safe_load(config_file.read_text(encoding="utf-8"))

    def __enter__(self) -> "ModeRunner":
        if self.mode == "container":
            compose_file = self.config["compose_file"]
            subprocess_check_call(
                ["./scripts/compose.sh", "-f", compose_file, "up", "-d", "--build"],
                cwd=self.hub_root,
            )
            return self

        for step in self.config.get("setup", []):
            env = os_environ.copy()
            env.pop("VIRTUAL_ENV", None)
            env.update(step.get("env", {}))
            subprocess_check_call(step["cmd"], cwd=self.hub_root / step["cwd"], env=env)

        for proc in self.config.get("processes", []):
            service_name = proc.get("service")
            if (
                self.active_services is not None
                and isinstance(service_name, str)
                and service_name not in self.active_services
            ):
                continue
            env = os_environ.copy()
            env.pop("VIRTUAL_ENV", None)
            env.update(proc.get("env", {}))
            p = subprocess_Popen(proc["cmd"], cwd=self.hub_root / proc["cwd"], env=env)
            self.processes.append(p)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if self.mode == "container":
            compose_file = self.config["compose_file"]
            subprocess_call(
                ["./scripts/compose.sh", "-f", compose_file, "down", "--remove-orphans"],
                cwd=self.hub_root,
            )
            return None

        for p in self.processes:
            if p.poll() is None:
                p.terminate()
        for p in self.processes:
            try:
                p.wait(timeout=10)
            except subprocess_TimeoutExpired:
                p.kill()
        return None
