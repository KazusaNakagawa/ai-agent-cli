"""Tests for journal_store.derive_title."""

import time

from src.journal_store import derive_title


def test_strips_leading_and_trailing_markup():
    assert derive_title("## **You:**\n**Buy the dip?** :\n") == "Buy the dip?"


def test_skips_role_label_lines():
    assert derive_title("**AI:**\n\n> real first line #\n") == "real first line"


def test_keeps_inner_markup_characters():
    assert derive_title("a_b * c: d") == "a_b * c: d"


def test_trailing_whitespace_run_is_linear_time():
    # A long run of trailing-markup characters followed by one that is not
    # used to backtrack quadratically in the trailing-markup regex.
    line = "x" + "\t" * 50_000 + "y"
    started = time.perf_counter()
    assert derive_title(line).startswith("x")
    assert time.perf_counter() - started < 0.5
