"""Tests for the parity-assertion core: _canonicalize_prediction."""

from __future__ import annotations

import math

import pytest

from orchestrator.main import _canonicalize_prediction


class TestCanonicalize:
    def test_float_rounds_to_6_decimals(self) -> None:
        assert _canonicalize_prediction(0.1234567891) == pytest.approx(0.123457)

    def test_int_is_passthrough(self) -> None:
        assert _canonicalize_prediction(42) == 42
        # No rounding applied to ints.
        assert isinstance(_canonicalize_prediction(42), int)

    def test_string_is_passthrough(self) -> None:
        assert _canonicalize_prediction("label") == "label"

    def test_bool_is_passthrough(self) -> None:
        assert _canonicalize_prediction(True) is True
        assert _canonicalize_prediction(False) is False

    def test_none_is_passthrough(self) -> None:
        assert _canonicalize_prediction(None) is None

    def test_flat_list_of_floats_rounded(self) -> None:
        assert _canonicalize_prediction([0.1234567891, 0.99999991]) == [
            pytest.approx(0.123457),
            pytest.approx(1.0),
        ]

    def test_dict_keys_sorted(self) -> None:
        out = _canonicalize_prediction({"b": 0.1, "a": 0.2, "c": 0.3})
        assert list(out.keys()) == ["a", "b", "c"]

    def test_nested_list_of_singletons_flattened(self) -> None:
        # Lists of length-1 lists are flattened to a single dimension.
        assert _canonicalize_prediction([[0.1], [0.2], [0.3]]) == [
            pytest.approx(0.1),
            pytest.approx(0.2),
            pytest.approx(0.3),
        ]

    def test_nested_list_of_non_singletons_kept(self) -> None:
        # 2-D inputs are preserved.
        assert _canonicalize_prediction([[0.1, 0.2], [0.3, 0.4]]) == [
            [pytest.approx(0.1), pytest.approx(0.2)],
            [pytest.approx(0.3), pytest.approx(0.4)],
        ]

    def test_mixed_singletons_and_non_singletons_kept(self) -> None:
        # If any item is not a length-1 list, no flattening.
        out = _canonicalize_prediction([[0.1], [0.2, 0.3]])
        assert out == [[pytest.approx(0.1)], [pytest.approx(0.2), pytest.approx(0.3)]]

    def test_empty_list(self) -> None:
        assert _canonicalize_prediction([]) == []

    def test_empty_dict(self) -> None:
        assert _canonicalize_prediction({}) == {}

    def test_deeply_nested_dict_in_list(self) -> None:
        payload = [{"score": 0.1234567891, "label": "cat"}]
        out = _canonicalize_prediction(payload)
        assert out == [{"label": "cat", "score": pytest.approx(0.123457)}]

    def test_nan_preserved_as_nan(self) -> None:
        # round(nan, 6) returns nan; canonicalize should keep that.
        out = _canonicalize_prediction(float("nan"))
        assert isinstance(out, float)
        assert math.isnan(out)

    def test_infinity_preserved(self) -> None:
        assert _canonicalize_prediction(float("inf")) == float("inf")

    def test_identical_payloads_canonicalize_identically(self) -> None:
        a = {"x": [0.1234567891, 0.99999991], "y": [[0.1], [0.2]]}
        b = {"y": [[0.1], [0.2]], "x": [0.1234567891, 0.99999991]}
        assert _canonicalize_prediction(a) == _canonicalize_prediction(b)

    def test_small_float_differences_canonicalize_equal(self) -> None:
        # The whole point: tiny numerical drift should not break parity.
        assert _canonicalize_prediction(0.1234567891) == _canonicalize_prediction(0.1234567892)
