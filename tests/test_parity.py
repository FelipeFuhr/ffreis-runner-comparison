"""Tests for _run_parity with mocked HTTP transport."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import FakeResponse

from orchestrator import main as main_mod
from orchestrator.main import _p95_ms, _run_parity


def _install_post(monkeypatch: pytest.MonkeyPatch, responses: dict[str, Any]) -> list[str]:
    """Mock httpx.post used by _invoke. Returns the call URL log."""
    called: list[str] = []

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float) -> Any:
        called.append(url)
        for base, resp in responses.items():
            if url.startswith(base):
                return resp
        raise RuntimeError(f"Unexpected URL in test: {url}")

    monkeypatch.setattr(main_mod, "httpx_post", fake_post)
    return called


class TestRunParity:
    def test_all_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_post(
            monkeypatch,
            {
                "http://a": FakeResponse(json_data={"score": 0.1234567891}),
                "http://b": FakeResponse(json_data={"score": 0.1234567892}),
            },
        )
        _run_parity(
            service_bases={"a": "http://a", "b": "http://b"},
            parity_services=None,
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )

    def test_mismatch_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_post(
            monkeypatch,
            {
                "http://a": FakeResponse(json_data={"score": 0.1}),
                "http://b": FakeResponse(json_data={"score": 0.2}),
            },
        )
        with pytest.raises(RuntimeError, match="Parity mismatch"):
            _run_parity(
                service_bases={"a": "http://a", "b": "http://b"},
                parity_services=None,
                path="/invocations",
                payload=b"x",
                content_type="text/csv",
                accept="application/json",
            )

    def test_unknown_service_raises(self) -> None:
        with pytest.raises(RuntimeError, match="Unknown parity service"):
            _run_parity(
                service_bases={"a": "http://a"},
                parity_services=["a", "ghost"],
                path="/invocations",
                payload=b"x",
                content_type="text/csv",
                accept="application/json",
            )

    def test_no_services_raises(self) -> None:
        with pytest.raises(RuntimeError, match="No services configured"):
            _run_parity(
                service_bases={},
                parity_services=None,
                path="/invocations",
                payload=b"x",
                content_type="text/csv",
                accept="application/json",
            )

    def test_parity_subset_skips_unselected_services(self, monkeypatch: pytest.MonkeyPatch) -> None:
        log = _install_post(
            monkeypatch,
            {
                "http://a": FakeResponse(json_data={"score": 1.0}),
                "http://b": FakeResponse(json_data={"score": 1.0}),
                "http://c": FakeResponse(json_data={"score": 999.0}),  # mismatching
            },
        )
        # Only check a and b -- c's mismatch should be ignored.
        _run_parity(
            service_bases={"a": "http://a", "b": "http://b", "c": "http://c"},
            parity_services=["a", "b"],
            path="/invocations",
            payload=b"x",
            content_type="text/csv",
            accept="application/json",
        )
        # c should not have been invoked.
        assert not any(url.startswith("http://c") for url in log)

    def test_baseline_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_post(
            monkeypatch,
            {
                "http://a": FakeResponse(status_code=500),
                "http://b": FakeResponse(json_data={"score": 1.0}),
            },
        )
        with pytest.raises(RuntimeError, match="HTTP 500"):
            _run_parity(
                service_bases={"a": "http://a", "b": "http://b"},
                parity_services=None,
                path="/invocations",
                payload=b"x",
                content_type="text/csv",
                accept="application/json",
            )


class TestP95:
    def test_empty_list_returns_zero(self) -> None:
        assert _p95_ms([]) == pytest.approx(0.0)

    def test_single_value(self) -> None:
        assert _p95_ms([10.0]) == pytest.approx(10.0)

    def test_sorted_input(self) -> None:
        # 20 values [0..19]: 95th percentile index = round(0.95 * 19) = 18.
        latencies = [float(i) for i in range(20)]
        assert _p95_ms(latencies) == pytest.approx(18.0)

    def test_unsorted_input_sorts_before_indexing(self) -> None:
        latencies = [
            5.0,
            11.0,
            0.0,
            9.0,
            18.0,
            1.0,
            13.0,
            6.0,
            14.0,
            17.0,
            4.0,
            19.0,
            10.0,
            8.0,
            16.0,
            3.0,
            15.0,
            7.0,
            2.0,
            12.0,
        ]
        assert _p95_ms(latencies) == pytest.approx(18.0)

    def test_returns_max_for_small_lists(self) -> None:
        assert _p95_ms([1.0, 100.0]) == pytest.approx(100.0)
