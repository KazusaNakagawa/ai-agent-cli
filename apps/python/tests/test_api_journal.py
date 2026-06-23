"""Tests for /api/journal — daily Markdown journal append + read (#271).

Contract:
- ``POST /api/journal`` appends a timestamped note to the day's file,
  creating the file if absent; returns {date}.
- ``GET /api/journal`` returns newest-first list of {date, size}.
- ``GET /api/journal/{date}`` returns {date, content} (raw markdown).
- Unknown / invalid date returns 404.
- Auth is required (Bearer) on all endpoints.
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
    assert response.json()["date"] == "2026-06-24"
    path = journal_dir / "2026-06-24.md"
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert "# Journal 2026-06-24" in body
    assert "First thought" in body


async def test_append_twice_keeps_both(authed_client, journal_dir):
    await authed_client.post("/api/journal", json={"content": "one", "date": "2026-06-24"})
    await authed_client.post("/api/journal", json={"content": "two", "date": "2026-06-24"})
    body = (journal_dir / "2026-06-24.md").read_text(encoding="utf-8")
    assert "one" in body and "two" in body
    # only one top-level heading
    assert body.count("# Journal 2026-06-24") == 1


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
    dates = [d["date"] for d in response.json()["dates"]]
    assert dates == ["2026-06-24", "2026-06-23", "2026-06-22"]


async def test_list_includes_size(authed_client, journal_dir):
    await authed_client.post("/api/journal", json={"content": "x", "date": "2026-06-24"})
    response = await authed_client.get("/api/journal")
    assert response.json()["dates"][0]["size"] > 0


async def test_list_empty_when_dir_missing(authed_client, journal_dir):
    response = await authed_client.get("/api/journal")
    assert response.status_code == 200
    assert response.json()["dates"] == []


async def test_get_returns_markdown(authed_client, journal_dir):
    await authed_client.post("/api/journal", json={"content": "hello", "date": "2026-06-24"})
    response = await authed_client.get("/api/journal/2026-06-24")
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-06-24"
    assert "hello" in body["content"]


async def test_get_unknown_date_returns_404(authed_client, journal_dir):
    response = await authed_client.get("/api/journal/2099-01-01")
    assert response.status_code == 404


async def test_get_invalid_date_returns_404(authed_client, journal_dir):
    response = await authed_client.get("/api/journal/not-a-date")
    assert response.status_code == 404
