"""Tests for /api/briefing — file list + markdown content.

Contract (#239):
- ``GET /api/briefing`` returns newest-first list of {name, type, date, size}.
- ``GET /api/briefing/{name}`` returns {name, content} (raw markdown).
- Unknown / invalid / traversal name returns 404.
- Auth is required (Bearer) on both endpoints.
"""
import pytest

from web.routers import briefing as briefing_router


@pytest.fixture
def briefing_dir(tmp_path, monkeypatch):
    """Point the briefing router at a tmp dir with sample files."""
    d = tmp_path / "briefing"
    d.mkdir()
    (d / "briefing_2026-06-20.md").write_text("# Briefing 2026-06-20\nContent A.", encoding="utf-8")
    (d / "briefing_2026-06-19.md").write_text("# Briefing 2026-06-19\nContent B.", encoding="utf-8")
    (d / "local_2026-06-18.md").write_text("# Local 2026-06-18\nContent C.", encoding="utf-8")
    (d / "briefing_2026-06-16-001.md").write_text("Numbered.", encoding="utf-8")
    (d / "ignored.txt").write_text("not a briefing", encoding="utf-8")
    monkeypatch.setattr(briefing_router, "BRIEFING_DIR", d)
    return d


async def test_list_requires_auth(async_client, briefing_dir):
    response = await async_client.get("/api/briefing")
    assert response.status_code == 401


async def test_list_newest_first(authed_client, briefing_dir):
    response = await authed_client.get("/api/briefing")
    assert response.status_code == 200
    files = response.json()["files"]
    names = [f["name"] for f in files]
    # .txt is excluded; newest first by date DESC
    assert names == [
        "briefing_2026-06-20.md",
        "briefing_2026-06-19.md",
        "local_2026-06-18.md",
        "briefing_2026-06-16-001.md",
    ]


async def test_list_parses_type_and_date(authed_client, briefing_dir):
    response = await authed_client.get("/api/briefing")
    assert response.status_code == 200
    files = {f["name"]: f for f in response.json()["files"]}
    assert files["briefing_2026-06-20.md"]["type"] == "briefing"
    assert files["briefing_2026-06-20.md"]["date"] == "2026-06-20"
    assert files["local_2026-06-18.md"]["type"] == "local"
    assert files["local_2026-06-18.md"]["date"] == "2026-06-18"
    assert files["briefing_2026-06-16-001.md"]["date"] == "2026-06-16"


async def test_list_includes_size(authed_client, briefing_dir):
    response = await authed_client.get("/api/briefing")
    assert response.status_code == 200
    f = next(f for f in response.json()["files"] if f["name"] == "briefing_2026-06-20.md")
    assert f["size"] > 0


async def test_list_empty_when_dir_missing(authed_client, tmp_path, monkeypatch):
    monkeypatch.setattr(briefing_router, "BRIEFING_DIR", tmp_path / "nonexistent")
    response = await authed_client.get("/api/briefing")
    assert response.status_code == 200
    assert response.json()["files"] == []


async def test_get_requires_auth(async_client, briefing_dir):
    response = await async_client.get("/api/briefing/briefing_2026-06-20.md")
    assert response.status_code == 401


async def test_get_returns_markdown(authed_client, briefing_dir):
    response = await authed_client.get("/api/briefing/briefing_2026-06-20.md")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "briefing_2026-06-20.md"
    assert "Briefing 2026-06-20" in body["content"]


async def test_get_unknown_file_returns_404(authed_client, briefing_dir):
    response = await authed_client.get("/api/briefing/briefing_9999-01-01.md")
    assert response.status_code == 404


async def test_get_path_traversal_returns_404(authed_client, briefing_dir):
    response = await authed_client.get("/api/briefing/..%2Fapp.py")
    assert response.status_code == 404


async def test_get_invalid_extension_returns_404(authed_client, briefing_dir):
    response = await authed_client.get("/api/briefing/ignored.txt")
    assert response.status_code == 404


async def test_list_newest_first_sorted_correctly(authed_client, briefing_dir):
    """Ensure sort order: briefing_2026-06-20 > briefing_2026-06-19 > briefing_2026-06-16-001."""
    response = await authed_client.get("/api/briefing")
    names = [f["name"] for f in response.json()["files"]]
    briefing_names = [n for n in names if n.startswith("briefing_")]
    # briefing files sorted newest-first by date
    assert briefing_names == ["briefing_2026-06-20.md", "briefing_2026-06-19.md", "briefing_2026-06-16-001.md"]
