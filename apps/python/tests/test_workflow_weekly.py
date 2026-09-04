"""The weekly recap workflow definition and its guard.

Behavior of the recap itself is covered by ``test_weekly_handler.py``, which
the migration leaves unmodified. What is asserted here is the shape of the
definition and the guard that replaces the ``date +%u`` branch that used to
live in ``bin/run.sh`` — the weekday rule is the whole reason the recap can be
reached from ``bin/workflow.sh`` at all.
"""
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src import weekly_handler, weekly_recap_state
from src.constants import WEEKLY_RECAP_WEEKDAY
from src.weekly_handler import recap_reason_to_skip, weekly_guard
from src.workflow import registry
from src.workflow.definitions.weekly import WEEKLY

PROJECT_ROOT = Path(__file__).parents[1]

# 2026-09-04 is a Friday, i.e. the configured recap weekday, and 2026-09-03 is
# the Thursday before it.
_FRIDAY = date(2026, 9, 4)
_THURSDAY = date(2026, 9, 3)
_THIS_WEEK = "2026-W36"  # the ISO week _FRIDAY belongs to
_LAST_WEEK = "2026-W35"


# --- definition -------------------------------------------------------------


def test_weekly_is_discoverable_by_id():
    assert registry.get("weekly") is WEEKLY


def test_step_order_puts_the_local_copy_before_the_notion_delivery():
    ids = [s.id for s in WEEKLY.steps]

    assert ids == ["preflight", "fetch", "summarize", "persist", "deliver_notion", "ingest_comments"]
    assert ids.index("persist") < ids.index("deliver_notion")


def test_preflight_is_the_only_preamble_step():
    assert [s.id for s in WEEKLY.steps if s.preamble] == ["preflight"]


@pytest.mark.parametrize("step_id", ["summarize", "persist", "deliver_notion", "ingest_comments"])
def test_steps_after_the_fetch_declare_a_skip_predicate(step_id):
    # A week with no briefing pages must deliver nothing rather than post an
    # empty recap — the 204 branch of the legacy handler.
    assert next(s for s in WEEKLY.steps if s.id == step_id).skip_if is not None


def test_the_summary_and_the_delivery_are_not_best_effort():
    for step_id in ("summarize", "deliver_notion"):
        assert next(s for s in WEEKLY.steps if s.id == step_id).best_effort is False


def test_the_workflow_declares_the_guard():
    assert WEEKLY.guard is not None


def test_discovery_does_not_import_the_weekly_handler():
    """Discovery must not depend on one workflow's runtime configuration.

    ``src.weekly_handler`` imports ``src.config``, whose ``CONFIG`` is read
    eagerly on first attribute access, so importing it during discovery would
    make ``workflow list`` fail on a machine with no ``config/briefing.json``.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys;"
            "from src.workflow import registry;"
            "found = registry.discover();"
            "assert 'weekly' in found, found;"
            "print('src.weekly_handler' in sys.modules)",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(PROJECT_ROOT)},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


# --- guard ------------------------------------------------------------------


class TestRecapReasonToSkip:
    """``posted_week`` is the ISO week of the last recap that reached Notion.

    ``None`` means none was ever recorded, which is the only case in which the
    local MD is consulted at all — see the bootstrap note on the function.
    """

    def test_runs_on_the_recap_weekday_with_no_recap_yet(self, tmp_path):
        assert recap_reason_to_skip(_FRIDAY, tmp_path, None) is None

    def test_skips_on_any_other_day(self, tmp_path):
        reason = recap_reason_to_skip(_THURSDAY, tmp_path, None)

        assert reason is not None
        assert "--force" in reason

    def test_skips_when_this_week_was_already_delivered(self, tmp_path):
        reason = recap_reason_to_skip(_FRIDAY, tmp_path, _THIS_WEEK)

        assert reason is not None
        assert _THIS_WEEK in reason

    def test_a_delivery_from_the_previous_week_does_not_block(self, tmp_path):
        assert recap_reason_to_skip(_FRIDAY, tmp_path, _LAST_WEEK) is None

    def test_a_persisted_but_undelivered_recap_does_not_block(self, tmp_path):
        """The regression Sourcery flagged on #463.

        ``step_persist`` writes the MD before the Notion post, so a local file
        with no matching delivery means the post failed — that week must be
        retried, not skipped, or the recap is lost until someone uses --force.
        """
        (tmp_path / "weekly-summary_2026-09-04.md").write_text("undelivered", encoding="utf-8")

        assert recap_reason_to_skip(_FRIDAY, tmp_path, _LAST_WEEK) is None

    def test_a_local_md_still_blocks_before_the_first_delivery_is_recorded(self, tmp_path):
        # Bootstrap: on a checkout that recapped before the state file existed,
        # the MD is the only evidence there is. It stops being consulted as
        # soon as one delivery is recorded.
        recap = tmp_path / "weekly-summary_2026-09-04.md"
        recap.write_text("summary", encoding="utf-8")

        reason = recap_reason_to_skip(_FRIDAY, tmp_path, None)

        assert reason is not None
        assert recap.name in reason

    def test_a_recap_from_the_previous_week_does_not_block(self, tmp_path):
        # Same ISO week membership, not "a file exists": last Friday's recap
        # must not suppress this Friday's.
        (tmp_path / "weekly-summary_2026-08-28.md").write_text("old", encoding="utf-8")

        assert recap_reason_to_skip(_FRIDAY, tmp_path, None) is None

    def test_a_recap_earlier_in_the_same_iso_week_blocks(self, tmp_path):
        # A forced Wednesday run still counts as this week's recap.
        (tmp_path / "weekly-summary_2026-09-02.md").write_text("mid-week", encoding="utf-8")

        assert recap_reason_to_skip(_FRIDAY, tmp_path, None) is not None

    def test_a_daily_briefing_md_is_not_mistaken_for_a_recap(self, tmp_path):
        (tmp_path / "briefing_2026-09-04.md").write_text("daily", encoding="utf-8")

        assert recap_reason_to_skip(_FRIDAY, tmp_path, None) is None

    def test_an_unparsable_filename_is_ignored(self, tmp_path):
        # Never let a stray file in the output dir suppress the recap.
        (tmp_path / "weekly-summary_draft.md").write_text("stray", encoding="utf-8")

        assert recap_reason_to_skip(_FRIDAY, tmp_path, None) is None

    def test_a_missing_output_dir_does_not_block(self, tmp_path):
        assert recap_reason_to_skip(_FRIDAY, tmp_path / "does-not-exist", None) is None

    def test_the_configured_weekday_is_the_one_enforced(self, tmp_path):
        # Pin the assertion to the constant rather than to Friday, so retuning
        # WEEKLY_RECAP_WEEKDAY does not need this test edited alongside it.
        monday = date(2026, 8, 31)
        configured = next(
            day
            for day in (monday + timedelta(days=offset) for offset in range(7))
            if day.isoweekday() == WEEKLY_RECAP_WEEKDAY
        )

        assert recap_reason_to_skip(configured, tmp_path, None) is None
        for offset in range(7):
            day = monday + timedelta(days=offset)
            if day != configured:
                assert recap_reason_to_skip(day, tmp_path, None) is not None


def test_weekly_guard_reads_today_the_output_dir_and_the_delivered_week(tmp_path):
    with (
        patch("src.weekly_handler.BRIEFING_OUTPUT_DIR", tmp_path),
        patch("src.weekly_handler.date") as mock_date,
    ):
        mock_date.today.return_value = _THURSDAY
        assert weekly_guard(None) is not None

        mock_date.today.return_value = _FRIDAY
        assert weekly_guard(None) is None

        weekly_recap_state.record_posted(_THIS_WEEK, "https://notion.so/w")
        assert weekly_guard(None) is not None


# --- the delivered-week marker ----------------------------------------------


class TestWeeklyRecapState:
    def test_week_key_uses_the_iso_year(self):
        # 2027-01-01 is a Friday in ISO week 2026-W53: a naive year-week label
        # would file it under 2027 and let that week be recapped twice.
        assert weekly_recap_state.week_key(date(2027, 1, 1)) == "2026-W53"
        assert weekly_recap_state.week_key(_FRIDAY) == _THIS_WEEK

    def test_no_state_file_reads_as_never_delivered(self):
        assert weekly_recap_state.read_posted_week() is None

    def test_round_trip(self):
        weekly_recap_state.record_posted(_THIS_WEEK, "https://notion.so/w")

        assert weekly_recap_state.read_posted_week() == _THIS_WEEK

    @pytest.mark.parametrize("content", ["not json", '["a", "list"]', '{"week": 36}'])
    def test_a_malformed_state_file_reads_as_never_delivered(self, content):
        # Fall back to running the recap: a duplicate page is a much smaller
        # problem than a week with no recap.
        weekly_recap_state.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        weekly_recap_state.STATE_FILE.write_text(content, encoding="utf-8")

        assert weekly_recap_state.read_posted_week() is None

    def test_recording_never_raises(self, tmp_path):
        with patch.object(weekly_recap_state, "STATE_FILE", tmp_path / "nope" / "x.json"):
            with patch("src.weekly_recap_state.os.replace", side_effect=OSError("disk full")):
                weekly_recap_state.record_posted(_THIS_WEEK, "https://notion.so/w")


class TestDeliveryRecordsTheWeek:
    def _ctx(self):
        return SimpleNamespace(results={"summarize": "サマリー"})

    def test_a_successful_post_records_the_week(self):
        with patch("src.weekly_handler.send_to_notion", return_value="https://notion.so/w"):
            weekly_handler.step_deliver_notion(self._ctx())

        assert weekly_recap_state.read_posted_week() == weekly_recap_state.week_key(date.today())

    def test_a_failed_post_records_nothing(self):
        with patch("src.weekly_handler.send_to_notion", return_value=""):
            weekly_handler.step_deliver_notion(self._ctx())

        assert weekly_recap_state.read_posted_week() is None
