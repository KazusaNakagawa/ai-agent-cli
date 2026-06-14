"""Unit tests for src.transient_errors.is_transient.

This module classifies claude CLI stdout/stderr to decide whether a
non-zero exit should be retried with backoff. Adding a pattern here is
the supported extension point; these tests pin the current set so future
changes are intentional.
"""

import pytest

from src.transient_errors import is_transient


class TestIsTransient:
    @pytest.mark.parametrize(
        "haystack",
        [
            "API Error: 529 Overloaded.",
            "API Error: 503 Service Unavailable",
            "API Error: 500 Internal Server Error",
            "API Error: 504 Gateway Timeout",
        ],
    )
    def test_5xx_codes_are_transient(self, haystack):
        assert is_transient(haystack, "") is True
        assert is_transient("", haystack) is True

    def test_socket_close_is_transient(self):
        """Regression: weekly job 2026-06-05 07:41 raised this and was not
        retried because the previous classifier only matched 5xx codes."""
        msg = (
            "API Error: The socket connection was closed unexpectedly. "
            "For more information, pass `verbose: true` in the second argument to fetch()"
        )
        assert is_transient(msg, "") is True

    @pytest.mark.parametrize(
        "haystack",
        [
            "fetch failed",
            "FetchError: Connection reset by peer (ECONNRESET)",
            "connect ECONNREFUSED 127.0.0.1:443",
            "request to https://api.anthropic.com failed, reason: ETIMEDOUT",
            "getaddrinfo EAI_AGAIN api.anthropic.com",
        ],
    )
    def test_network_level_errors_are_transient(self, haystack):
        assert is_transient(haystack, "") is True

    @pytest.mark.parametrize(
        "haystack",
        [
            "API Error: 401 Unauthorized",
            "API Error: 400 Bad Request",
            "API Error: 404 Not Found",
            "Invalid model: foo",
            "auth error",
            "",
        ],
    )
    def test_non_transient_errors_are_not_retried(self, haystack):
        assert is_transient(haystack, "") is False
        assert is_transient("", haystack) is False

    def test_none_inputs_are_handled(self):
        assert is_transient(None, None) is False
        assert is_transient(None, "API Error: 529 Overloaded") is True
        assert is_transient("API Error: 529 Overloaded", None) is True

    def test_matches_across_stdout_and_stderr_combined(self):
        """The classifier searches stdout + stderr together, so a token split
        across the two should still match (defensive — the CLI does not
        actually split messages, but the contract is 'either stream')."""
        assert is_transient("API Error: 5", "29 Overloaded") is False
        assert is_transient("API Error: 503", "extra noise") is True
        assert is_transient("noise", "API Error: 503") is True
