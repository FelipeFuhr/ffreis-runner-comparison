"""Tests for the optional ghz gRPC load wrapper."""

from __future__ import annotations

from typing import Any

import pytest

from workloads.grpc import ghz_runner


class TestRunGhz:
    def test_builds_expected_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_call(cmd: list[str]) -> int:
            captured["cmd"] = cmd
            return 0

        monkeypatch.setattr(ghz_runner, "subprocess_call", fake_call)
        rc = ghz_runner.run_ghz("localhost:9000", "service.proto", duration_s=10)
        assert rc == 0
        cmd = captured["cmd"]
        assert cmd[0] == "ghz"
        assert "--proto" in cmd and "service.proto" in cmd
        assert "--duration" in cmd and "10s" in cmd
        assert cmd[-1] == "localhost:9000"

    def test_default_duration_is_30s(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            ghz_runner, "subprocess_call", lambda cmd: captured.setdefault("cmd", cmd) or 0
        )
        ghz_runner.run_ghz("localhost:9000", "service.proto")
        assert "30s" in captured["cmd"]

    def test_returns_subprocess_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ghz_runner, "subprocess_call", lambda cmd: 7)
        assert ghz_runner.run_ghz("localhost:9000", "service.proto") == 7
