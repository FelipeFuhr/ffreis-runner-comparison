"""Tests for the Locust HTTP load profile.

`@task` doesn't wrap the underlying function, so `InferenceUser.invocations`
stays a plain, directly-callable function -- calling it with a fake `self`
exposing a mocked `.client` avoids needing a real Locust Environment/runner.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from workloads.locust.locustfile_http import InferenceUser


class _FakeUser:
    def __init__(self) -> None:
        self.client = MagicMock()


class TestInvocationsTask:
    def test_posts_expected_payload_and_headers(self) -> None:
        fake_self: Any = _FakeUser()
        InferenceUser.invocations(fake_self)
        fake_self.client.post.assert_called_once_with(
            "/invocations",
            data=b"1,2,3\n4,5,6\n",
            headers={"Content-Type": "text/csv", "Accept": "application/json"},
            name="POST /invocations",
        )

    def test_wait_time_configured(self) -> None:
        # between(0.05, 0.2) returns a callable bound as wait_time.
        assert callable(InferenceUser.wait_time)
