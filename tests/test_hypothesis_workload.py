"""Tests for hypothesis-based parity workloads."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given

from workloads.hypothesis import parity_props
from workloads.hypothesis.strategies import csv_floats, matrix_to_csv


class TestMatrixToCsv:
    def test_single_row(self) -> None:
        assert matrix_to_csv([[1.0, 2.0, 3.0]]) == b"1.0,2.0,3.0\n"

    def test_multiple_rows_join_with_newlines(self) -> None:
        result = matrix_to_csv([[1.0, 2.0], [3.0, 4.0]])
        assert result == b"1.0,2.0\n3.0,4.0\n"

    def test_returns_bytes(self) -> None:
        assert isinstance(matrix_to_csv([[0.0]]), bytes)

    def test_trailing_newline(self) -> None:
        assert matrix_to_csv([[1.0]]).endswith(b"\n")


class TestCsvFloatsStrategy:
    @given(rows=csv_floats)
    def test_rows_have_three_columns(self, rows: list[list[float]]) -> None:
        for row in rows:
            assert len(row) == 3

    @given(rows=csv_floats)
    def test_at_least_one_row(self, rows: list[list[float]]) -> None:
        assert 1 <= len(rows) <= 8


class TestParityPropertyHelper:
    """Verify _invoke wraps httpx with the right headers."""

    def test_invoke_uses_csv_content_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        class _R:
            def json(self) -> Any:
                return [[1.0, 2.0]]

            def raise_for_status(self) -> None:
                return None

        def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float) -> Any:
            captured["url"] = url
            captured["headers"] = headers
            return _R()

        monkeypatch.setattr(parity_props, "httpx_post", fake_post)
        out = parity_props._invoke("http://svc", b"1,2,3\n")
        assert out == [[1.0, 2.0]]
        assert captured["url"] == "http://svc/invocations"
        assert captured["headers"]["Content-Type"] == "text/csv"
        assert captured["headers"]["Accept"] == "application/json"

    def test_invoke_propagates_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _R:
            def json(self) -> Any:
                return None

            def raise_for_status(self) -> None:
                raise RuntimeError("502")

        monkeypatch.setattr(parity_props, "httpx_post", lambda *_a, **_k: _R())
        with pytest.raises(RuntimeError, match="502"):
            parity_props._invoke("http://svc", b"x")
