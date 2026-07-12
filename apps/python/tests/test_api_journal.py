"""Tests for /api/journal — per-entry Markdown journal (#271, #295).

Contract:
- ``POST /api/journal`` creates a new entry file; returns {id, date}.
- ``GET /api/journal`` returns newest-first list of {id, date, size}.
- ``GET /api/journal/{entry_id}`` returns {id, date, content} (raw markdown).
- Unknown / invalid id returns 404.
- Auth is required (Bearer) on all endpoints.
- Legacy day-based files (YYYY-MM-DD.md) remain listable and readable.
"""
from unittest.mock import patch

from src import journal_store


async def test_list_requires_auth(async_client, journal_dir):
    response = await async_client.get("/api/journal")
    assert response.status_code == 401


async def test_append_requires_auth(async_client, journal_dir):
    response = await async_client.post("/api/journal", json={"content": "hi"})
    assert response.status_code == 401


async def test_append_creates_file(authed_client, journal_dir):
    response = await authed_client.post(
        "/api/journal", json={"content": "First thought", "date": "2026-06-24"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-06-24"
    assert body["id"].startswith("2026-06-24")
    path = journal_dir / f"{body['id']}.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "# Journal 2026-06-24" in text
    assert "First thought" in text


async def test_append_twice_same_date_creates_two_entries(authed_client, journal_dir):
    r1 = await authed_client.post(
        "/api/journal", json={"content": "one", "date": "2026-06-24"}
    )
    r2 = await authed_client.post(
        "/api/journal", json={"content": "two", "date": "2026-06-24"}
    )
    id1, id2 = r1.json()["id"], r2.json()["id"]
    assert id1 != id2
    # Two separate files, each with its own content.
    files = list(journal_dir.glob("2026-06-24*.md"))
    assert len(files) == 2
    response = await authed_client.get("/api/journal")
    ids = [e["id"] for e in response.json()["entries"]]
    assert id1 in ids and id2 in ids


async def test_append_without_item_derives_title_from_content(authed_client, journal_dir):
    """Issue #380: a mid-chat new entry must not fall back to an empty item."""
    response = await authed_client.post(
        "/api/journal",
        json={"content": "**You:**\n\nWhat should I focus on next?\n\n**AI:**\n\nSome answer"},
    )
    assert response.status_code == 200
    entry_id = response.json()["id"]
    listed = await authed_client.get("/api/journal")
    entry = next(e for e in listed.json()["entries"] if e["id"] == entry_id)
    assert entry["item"] == "What should I focus"


async def test_append_without_item_derives_from_plain_content(authed_client, journal_dir):
    response = await authed_client.post("/api/journal", json={"content": "hello there"})
    entry_id = response.json()["id"]
    listed = await authed_client.get("/api/journal")
    entry = next(e for e in listed.json()["entries"] if e["id"] == entry_id)
    assert entry["item"] == "hello there"


async def test_append_explicit_item_is_not_overridden(authed_client, journal_dir):
    response = await authed_client.post(
        "/api/journal", json={"content": "some content", "item": "custom title"}
    )
    entry_id = response.json()["id"]
    listed = await authed_client.get("/api/journal")
    entry = next(e for e in listed.json()["entries"] if e["id"] == entry_id)
    assert entry["item"] == "custom title"


async def test_append_blank_item_falls_back_to_derived_title(authed_client, journal_dir):
    """An explicit but blank item (e.g. an image-only turn) still gets a title."""
    response = await authed_client.post(
        "/api/journal", json={"content": "some content", "item": "   "}
    )
    entry_id = response.json()["id"]
    listed = await authed_client.get("/api/journal")
    entry = next(e for e in listed.json()["entries"] if e["id"] == entry_id)
    assert entry["item"] == "some content"


async def test_append_defaults_to_today(authed_client, journal_dir):
    response = await authed_client.post("/api/journal", json={"content": "no date"})
    assert response.status_code == 200
    assert journal_store._DATE_RE.match(response.json()["date"])


async def test_append_empty_content_rejected(authed_client, journal_dir):
    response = await authed_client.post("/api/journal", json={"content": "   "})
    assert response.status_code == 400


async def test_append_blank_string_rejected_by_schema(authed_client, journal_dir):
    response = await authed_client.post("/api/journal", json={"content": ""})
    assert response.status_code == 422


async def test_append_invalid_date_rejected(authed_client, journal_dir):
    response = await authed_client.post(
        "/api/journal", json={"content": "x", "date": "not-a-date"}
    )
    assert response.status_code == 400


async def test_list_newest_first(authed_client, journal_dir):
    for date in ("2026-06-22", "2026-06-24", "2026-06-23"):
        await authed_client.post("/api/journal", json={"content": "x", "date": date})
    response = await authed_client.get("/api/journal")
    assert response.status_code == 200
    dates = [e["date"] for e in response.json()["entries"]]
    assert dates == ["2026-06-24", "2026-06-23", "2026-06-22"]


async def test_list_includes_size(authed_client, journal_dir):
    await authed_client.post("/api/journal", json={"content": "x", "date": "2026-06-24"})
    response = await authed_client.get("/api/journal")
    assert response.json()["entries"][0]["size"] > 0


async def test_list_empty_when_dir_missing(authed_client, journal_dir):
    response = await authed_client.get("/api/journal")
    assert response.status_code == 200
    assert response.json()["entries"] == []


async def test_get_returns_markdown(authed_client, journal_dir):
    post = await authed_client.post(
        "/api/journal", json={"content": "hello", "date": "2026-06-24"}
    )
    entry_id = post.json()["id"]
    response = await authed_client.get(f"/api/journal/{entry_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == entry_id
    assert body["date"] == "2026-06-24"
    assert "hello" in body["content"]


async def test_get_unknown_id_returns_404(authed_client, journal_dir):
    response = await authed_client.get("/api/journal/2099-01-01_120000")
    assert response.status_code == 404


async def test_get_invalid_id_returns_404(authed_client, journal_dir):
    response = await authed_client.get("/api/journal/not-a-date")
    assert response.status_code == 404


async def test_legacy_day_file_is_listed_and_readable(authed_client, journal_dir):
    """A bare YYYY-MM-DD.md file from the old model stays accessible."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    (journal_dir / "2026-06-20.md").write_text(
        "# Journal 2026-06-20\n\nlegacy note\n", encoding="utf-8"
    )
    listed = await authed_client.get("/api/journal")
    entry = next(e for e in listed.json()["entries"] if e["id"] == "2026-06-20")
    assert entry["date"] == "2026-06-20"
    got = await authed_client.get("/api/journal/2026-06-20")
    assert got.status_code == 200
    assert "legacy note" in got.json()["content"]


async def test_append_nonexistent_calendar_date_rejected(authed_client, journal_dir):
    """A well-formed but impossible date (2026-99-99) is rejected."""
    response = await authed_client.post(
        "/api/journal", json={"content": "x", "date": "2026-99-99"}
    )
    assert response.status_code == 400


async def test_soft_delete_moves_to_trash_and_excludes_from_list(authed_client, journal_dir):
    post = await authed_client.post(
        "/api/journal", json={"content": "to delete", "date": "2026-06-24"}
    )
    entry_id = post.json()["id"]

    resp = await authed_client.delete(f"/api/journal/{entry_id}")
    assert resp.status_code == 204
    # File moved under deleted/, gone from the active dir.
    assert not (journal_dir / f"{entry_id}.md").exists()
    assert (journal_dir / "deleted" / f"{entry_id}.md").exists()
    # No longer listed.
    listed = await authed_client.get("/api/journal")
    assert all(e["id"] != entry_id for e in listed.json()["entries"])


async def test_soft_delete_unknown_returns_404(authed_client, journal_dir):
    resp = await authed_client.delete("/api/journal/2099-01-01_120000")
    assert resp.status_code == 404


async def test_restore_returns_entry_to_active_list(authed_client, journal_dir):
    post = await authed_client.post(
        "/api/journal", json={"content": "restore me", "date": "2026-06-24"}
    )
    entry_id = post.json()["id"]
    await authed_client.delete(f"/api/journal/{entry_id}")

    resp = await authed_client.post(f"/api/journal/{entry_id}/restore")
    assert resp.status_code == 204
    assert (journal_dir / f"{entry_id}.md").exists()
    listed = await authed_client.get("/api/journal")
    assert any(e["id"] == entry_id for e in listed.json()["entries"])


async def test_restore_unknown_returns_404(authed_client, journal_dir):
    resp = await authed_client.post("/api/journal/2099-01-01_120000/restore")
    assert resp.status_code == 404


async def test_get_trashed_entry_returns_content(authed_client, journal_dir):
    post = await authed_client.post(
        "/api/journal", json={"content": "preview me", "date": "2026-06-24"}
    )
    entry_id = post.json()["id"]
    await authed_client.delete(f"/api/journal/{entry_id}")

    resp = await authed_client.get(f"/api/journal/trash/{entry_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == entry_id
    assert "preview me" in body["content"]


async def test_get_trashed_unknown_returns_404(authed_client, journal_dir):
    resp = await authed_client.get("/api/journal/trash/2099-01-01_120000")
    assert resp.status_code == 404


async def test_get_trashed_active_entry_returns_404(authed_client, journal_dir):
    # An entry that is still active (not trashed) must not be readable via the
    # trash preview endpoint.
    post = await authed_client.post(
        "/api/journal", json={"content": "still active", "date": "2026-06-24"}
    )
    entry_id = post.json()["id"]
    resp = await authed_client.get(f"/api/journal/trash/{entry_id}")
    assert resp.status_code == 404


async def test_purge_permanently_deletes_from_trash(authed_client, journal_dir):
    post = await authed_client.post(
        "/api/journal", json={"content": "purge me", "date": "2026-06-24"}
    )
    entry_id = post.json()["id"]
    await authed_client.delete(f"/api/journal/{entry_id}")

    resp = await authed_client.delete(f"/api/journal/{entry_id}?purge=true")
    assert resp.status_code == 204
    assert not (journal_dir / "deleted" / f"{entry_id}.md").exists()


async def test_delete_requires_auth(async_client, journal_dir):
    resp = await async_client.delete("/api/journal/2026-06-24_120000")
    assert resp.status_code == 401


async def test_purge_param_requires_literal_true(authed_client, journal_dir):
    """A non-'true' purge value soft-deletes (no accidental permanent delete)."""
    post = await authed_client.post(
        "/api/journal", json={"content": "keep recoverable", "date": "2026-06-24"}
    )
    entry_id = post.json()["id"]

    resp = await authed_client.delete(f"/api/journal/{entry_id}?purge=1")
    assert resp.status_code == 204
    # Soft-deleted, not purged: still recoverable in trash.
    assert (journal_dir / "deleted" / f"{entry_id}.md").exists()


async def test_trash_lists_soft_deleted_entries(authed_client, journal_dir):
    post = await authed_client.post(
        "/api/journal", json={"content": "trash me", "date": "2026-06-24"}
    )
    entry_id = post.json()["id"]
    await authed_client.delete(f"/api/journal/{entry_id}")

    resp = await authed_client.get("/api/journal/trash")
    assert resp.status_code == 200
    trashed = resp.json()["entries"]
    assert any(e["id"] == entry_id for e in trashed)
    row = next(e for e in trashed if e["id"] == entry_id)
    assert row["date"] == "2026-06-24"
    assert row["size"] > 0
    # Active list does not include the trashed entry.
    active = await authed_client.get("/api/journal")
    assert all(e["id"] != entry_id for e in active.json()["entries"])


async def test_trash_empty_when_nothing_deleted(authed_client, journal_dir):
    resp = await authed_client.get("/api/journal/trash")
    assert resp.status_code == 200
    assert resp.json()["entries"] == []


async def test_trash_requires_auth(async_client, journal_dir):
    resp = await async_client.get("/api/journal/trash")
    assert resp.status_code == 401


class TestNotionSync:
    """Notion sync is triggered when configured, and never breaks the API (best-effort)."""

    def _creds(self, database_id):
        return ("key", database_id)

    async def test_no_database_id_skips_sync(self, authed_client, journal_dir):
        with patch("web.routers.journal.config.get_journal_notion_credentials", return_value=("", "")), \
             patch("web.routers.journal.journal_sync.sync_new_entry") as mock_sync:
            response = await authed_client.post(
                "/api/journal", json={"content": "hi", "date": "2026-07-03"}
            )
        assert response.status_code == 200
        mock_sync.assert_not_called()

    async def test_new_entry_triggers_sync(self, authed_client, journal_dir):
        with patch(
            "web.routers.journal.config.get_journal_notion_credentials",
            return_value=self._creds("db-id"),
        ), patch("web.routers.journal.journal_sync.sync_new_entry") as mock_sync:
            response = await authed_client.post(
                "/api/journal", json={"content": "hi", "date": "2026-07-03"}
            )
        assert response.status_code == 200
        entry_id = response.json()["id"]
        mock_sync.assert_called_once_with(entry_id, "hi", "key", "db-id")

    async def test_sync_failure_does_not_break_create(self, authed_client, journal_dir):
        with patch(
            "web.routers.journal.config.get_journal_notion_credentials",
            return_value=self._creds("db-id"),
        ), patch(
            "web.routers.journal.journal_sync.sync_new_entry", side_effect=Exception("boom")
        ):
            response = await authed_client.post(
                "/api/journal", json={"content": "hi", "date": "2026-07-03"}
            )
        assert response.status_code == 200
        assert (journal_dir / f"{response.json()['id']}.md").exists()

    async def test_append_triggers_sync(self, authed_client, journal_dir):
        post = await authed_client.post(
            "/api/journal", json={"content": "hi", "date": "2026-07-03"}
        )
        entry_id = post.json()["id"]
        with patch(
            "web.routers.journal.config.get_journal_notion_credentials",
            return_value=self._creds("db-id"),
        ), patch("web.routers.journal.journal_sync.sync_append") as mock_sync:
            response = await authed_client.patch(
                f"/api/journal/{entry_id}", json={"content": "more"}
            )
        assert response.status_code == 204
        mock_sync.assert_called_once_with(entry_id, "more", "key", "db-id")

    async def test_append_sync_failure_does_not_break_patch(self, authed_client, journal_dir):
        post = await authed_client.post(
            "/api/journal", json={"content": "hi", "date": "2026-07-03"}
        )
        entry_id = post.json()["id"]
        with patch(
            "web.routers.journal.config.get_journal_notion_credentials",
            return_value=self._creds("db-id"),
        ), patch(
            "web.routers.journal.journal_sync.sync_append", side_effect=Exception("boom")
        ):
            response = await authed_client.patch(
                f"/api/journal/{entry_id}", json={"content": "more"}
            )
        assert response.status_code == 204

    async def test_list_exposes_notion_url_once_synced(self, authed_client, journal_dir):
        """The UI needs a link to the synced Notion page so users don't reach for
        the unrelated /notion-import skill (which targets the Briefing DB)."""
        from src import journal_store

        post = await authed_client.post(
            "/api/journal", json={"content": "hi", "date": "2026-07-03"}
        )
        entry_id = post.json()["id"]
        journal_store.save_notion_meta(entry_id, "page-1", "https://notion.so/page-1")

        response = await authed_client.get("/api/journal")
        entry = next(e for e in response.json()["entries"] if e["id"] == entry_id)
        assert entry["notion_url"] == "https://notion.so/page-1"

    async def test_list_notion_url_empty_when_not_synced(self, authed_client, journal_dir):
        post = await authed_client.post(
            "/api/journal", json={"content": "hi", "date": "2026-07-03"}
        )
        entry_id = post.json()["id"]

        response = await authed_client.get("/api/journal")
        entry = next(e for e in response.json()["entries"] if e["id"] == entry_id)
        assert entry["notion_url"] == ""
