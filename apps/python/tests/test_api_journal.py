"""Tests for /api/journal — per-entry Markdown journal (#271, #295).

Contract:
- ``POST /api/journal`` creates a new entry file; returns {id, date}.
- ``GET /api/journal`` returns newest-first list of {id, date, size}.
- ``GET /api/journal/{entry_id}`` returns {id, date, content} (raw markdown).
- Unknown / invalid id returns 404.
- Auth is required (Bearer) on all endpoints.
- Legacy day-based files (YYYY-MM-DD.md) remain listable and readable.
"""
import pytest

from src import journal_store


@pytest.fixture
def journal_dir(tmp_path, monkeypatch):
    """Point the journal store at a tmp dir."""
    d = tmp_path / "journal"
    monkeypatch.setattr(journal_store, "JOURNAL_DIR", d)
    return d


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
