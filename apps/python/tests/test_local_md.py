from datetime import date

import pytest

from src.notifier.local_md import save_briefing_md


class TestSaveBriefingMd:
    def test_writes_file_with_date_in_name(self, tmp_path):
        """Verifies: file is created as briefing_YYYY-MM-DD.md with the given text.
        Why: the consumer (operator browsing output/briefing/) relies on the
        date-stamped filename to find the right briefing.
        """
        path = save_briefing_md(
            "body", tmp_path, retention_days=7, today=date(2026, 5, 19)
        )
        assert path == tmp_path / "briefing_2026-05-19.md"
        assert path.read_text(encoding="utf-8") == "body"

    def test_creates_output_dir_if_missing(self, tmp_path):
        """Verifies: a missing output_dir is created on demand.
        Why: the function must work on a fresh checkout where the directory
        does not yet exist.
        """
        target = tmp_path / "nested" / "briefing"
        save_briefing_md("body", target, retention_days=7, today=date(2026, 5, 19))
        assert (target / "briefing_2026-05-19.md").exists()

    def test_overwrites_existing_same_day(self, tmp_path):
        """Verifies: running twice on the same day overwrites the file.
        Why: re-runs (manual or after a transient failure) must not raise or
        accumulate duplicates.
        """
        save_briefing_md("first", tmp_path, retention_days=7, today=date(2026, 5, 19))
        save_briefing_md("second", tmp_path, retention_days=7, today=date(2026, 5, 19))
        path = tmp_path / "briefing_2026-05-19.md"
        assert path.read_text(encoding="utf-8") == "second"
        assert len(list(tmp_path.glob("briefing_*.md"))) == 1

    def test_retention_keeps_newest_n(self, tmp_path):
        """Verifies: after writing 8 distinct days with retention=7, only the
        newest 7 remain on disk.
        Why: this is the core retention guarantee that prevents the output
        directory from growing unbounded.
        """
        for i in range(8):
            d = date(2026, 5, 12 + i)  # 5/12 .. 5/19
            save_briefing_md(f"day{i}", tmp_path, retention_days=7, today=d)

        remaining = sorted(p.name for p in tmp_path.glob("briefing_*.md"))
        assert remaining == [
            "briefing_2026-05-13.md",
            "briefing_2026-05-14.md",
            "briefing_2026-05-15.md",
            "briefing_2026-05-16.md",
            "briefing_2026-05-17.md",
            "briefing_2026-05-18.md",
            "briefing_2026-05-19.md",
        ]

    def test_does_not_touch_unrelated_files(self, tmp_path):
        """Verifies: files not matching the briefing_YYYY-MM-DD.md pattern are
        left alone even when retention is enforced.
        Why: the output dir may legitimately contain .gitkeep, README, or
        manually-saved notes. Deleting them would be data loss.
        """
        (tmp_path / ".gitkeep").write_text("")
        (tmp_path / "notes.md").write_text("manual notes")
        (tmp_path / "briefing_extra.md").write_text("non-date variant")

        for i in range(8):
            d = date(2026, 5, 12 + i)
            save_briefing_md(f"day{i}", tmp_path, retention_days=7, today=d)

        assert (tmp_path / ".gitkeep").exists()
        assert (tmp_path / "notes.md").exists()
        assert (tmp_path / "briefing_extra.md").exists()

    def test_retention_one_keeps_only_today(self, tmp_path):
        """Verifies: with retention_days=1 only the file just written remains.
        Why: boundary case — guards against an off-by-one where the loop
        keeps zero or two files.
        """
        save_briefing_md("old", tmp_path, retention_days=1, today=date(2026, 5, 18))
        save_briefing_md("new", tmp_path, retention_days=1, today=date(2026, 5, 19))
        remaining = sorted(p.name for p in tmp_path.glob("briefing_*.md"))
        assert remaining == ["briefing_2026-05-19.md"]

    def test_directory_with_matching_name_is_skipped(self, tmp_path):
        """Verifies: a directory whose name happens to match the
        briefing_YYYY-MM-DD.md pattern is not unlinked during pruning.
        Why: unlink() on a directory raises IsADirectoryError. The pruner
        should treat such entries as non-target and leave them alone.
        """
        (tmp_path / "briefing_2026-04-01.md").mkdir()  # directory, not file

        # Write 8 real files; without the is_file guard, the pruner would try
        # to unlink the oldest entry (the directory) and crash.
        for i in range(8):
            d = date(2026, 5, 12 + i)
            save_briefing_md(f"day{i}", tmp_path, retention_days=7, today=d)

        assert (tmp_path / "briefing_2026-04-01.md").is_dir()
        remaining_files = sorted(
            p.name for p in tmp_path.iterdir() if p.is_file()
        )
        assert remaining_files == [
            "briefing_2026-05-13.md",
            "briefing_2026-05-14.md",
            "briefing_2026-05-15.md",
            "briefing_2026-05-16.md",
            "briefing_2026-05-17.md",
            "briefing_2026-05-18.md",
            "briefing_2026-05-19.md",
        ]

    def test_invalid_retention_raises(self, tmp_path):
        """Verifies: retention_days < 1 raises ValueError before any file work.
        Why: zero or negative retention would delete the file we just wrote;
        fail loudly at the boundary.
        """
        with pytest.raises(ValueError, match="retention_days"):
            save_briefing_md("body", tmp_path, retention_days=0, today=date(2026, 5, 19))
        with pytest.raises(ValueError, match="retention_days"):
            save_briefing_md("body", tmp_path, retention_days=-1, today=date(2026, 5, 19))
