"""wait_http_ok readiness probe tests."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator import wait_ready as wait_ready_mod
from orchestrator.wait_ready import wait_http_ok


class _Response:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


@pytest.fixture
def fast_clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """Replace time.time and time.sleep so tests run instantly."""
    clock = {"now": 0.0}

    def fake_time() -> float:
        return clock["now"]

    def fake_sleep(seconds: float) -> None:
        clock["now"] += seconds

    monkeypatch.setattr(wait_ready_mod, "time_time", fake_time)
    monkeypatch.setattr(wait_ready_mod, "time_sleep", fake_sleep)
    return clock


class TestWaitHttpOk:
    def test_returns_on_first_200(
        self, fast_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(wait_ready_mod, "httpx_get", lambda *_a, **_k: _Response(200))
        # Should return without sleeping.
        wait_http_ok("http://x")
        assert fast_clock["now"] == pytest.approx(0.0)

    def test_retries_on_non_200_until_success(
        self, fast_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        responses = [_Response(503), _Response(503), _Response(200)]
        i = {"n": 0}

        def fake_get(*_a: Any, **_k: Any) -> _Response:
            r = responses[i["n"]]
            i["n"] += 1
            return r

        monkeypatch.setattr(wait_ready_mod, "httpx_get", fake_get)
        wait_http_ok("http://x")
        assert i["n"] == 3

    def test_retries_on_exception(
        self, fast_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        i = {"n": 0}

        def fake_get(*_a: Any, **_k: Any) -> _Response:
            i["n"] += 1
            if i["n"] < 3:
                raise ConnectionRefusedError("not ready")
            return _Response(200)

        monkeypatch.setattr(wait_ready_mod, "httpx_get", fake_get)
        wait_http_ok("http://x")
        assert i["n"] == 3

    def test_times_out_with_last_error_message(
        self, fast_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_get(*_a: Any, **_k: Any) -> _Response:
            raise ConnectionRefusedError("nope")

        monkeypatch.setattr(wait_ready_mod, "httpx_get", fake_get)
        with pytest.raises(RuntimeError, match="Timed out waiting for http://x"):
            wait_http_ok("http://x", timeout_s=1.0)
        # Last exception should appear in the error message.
        with pytest.raises(RuntimeError, match="nope"):
            wait_http_ok("http://x", timeout_s=1.0)

    def test_times_out_for_persistent_non_200(
        self, fast_clock: dict[str, float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(wait_ready_mod, "httpx_get", lambda *_a, **_k: _Response(500))
        with pytest.raises(RuntimeError, match="Timed out"):
            wait_http_ok("http://x", timeout_s=0.5)
