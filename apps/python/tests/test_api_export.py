"""Tests for /api/export — zip download of the output/ tree.

Contract:
- ``GET /api/export`` returns a 200 application/zip attachment.
- The zip contains every file under output/ (paths kept relative to output/).
- ``.DS_Store`` files and ``.sessions`` dirs are excluded.
- Auth (Bearer) is required.
"""
import io
import zipfile

import pytest

from web.routers import export as export_router


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """Point the export router at a tmp output tree with sample files."""
    d = tmp_path / "output"
    (d / "briefing").mkdir(parents=True)
    (d / "briefing" / "briefing_2026-06-24.md").write_text("hi", encoding="utf-8")
    (d / "journal").mkdir()
    (d / "journal" / "2026-06-24.md").write_text("note", encoding="utf-8")
    (d / "briefing" / ".sessions").mkdir()
    (d / "briefing" / ".sessions" / "2026-06-24").write_text("uuid", encoding="utf-8")
    (d / ".DS_Store").write_text("junk", encoding="utf-8")
    monkeypatch.setattr(export_router, "OUTPUT_DIR", d)
    return d


async def test_requires_auth(async_client, output_dir):
    response = await async_client.get("/api/export")
    assert response.status_code == 401


async def test_returns_zip_attachment(authed_client, output_dir):
    response = await authed_client.get("/api/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert ".zip" in response.headers["content-disposition"]


async def test_zip_contains_output_files(authed_client, output_dir):
    response = await authed_client.get("/api/export")
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(zf.namelist())
    assert "output/briefing/briefing_2026-06-24.md" in names
    assert "output/journal/2026-06-24.md" in names


async def test_zip_excludes_noise(authed_client, output_dir):
    response = await authed_client.get("/api/export")
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(zf.namelist())
    assert not any(".DS_Store" in n for n in names)
    assert not any(".sessions" in n for n in names)


async def test_empty_output_returns_empty_zip(authed_client, tmp_path, monkeypatch):
    monkeypatch.setattr(export_router, "OUTPUT_DIR", tmp_path / "nonexistent")
    monkeypatch.setattr(export_router, "INPUT_DIR", tmp_path / "nonexistent_input")
    response = await authed_client.get("/api/export")
    assert response.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    assert zf.namelist() == []
