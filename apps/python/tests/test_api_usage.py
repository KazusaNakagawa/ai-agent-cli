"""Tests for /api/usage — list available dates + per-day JSONL records.

Contract (#225):
- ``GET /api/usage/dates`` returns ``{"dates": [...]}`` (newest first).
- ``GET /api/usage?date=YYYYMMDD`` returns ``{"date", "records": [...]}``.
- Unknown / malformed date returns 404.
- Auth is required (Bearer), same as other protected routers.
"""
import json

import pytest

from web.routers import usage as usage_router


@pytest.fixture
def usage_dir(tmp_path, monkeypatch):
    """Point the usage router at a tmp log dir with two sample days."""
    d = tmp_path / "usage"
    d.mkdir()
    day1 = d / "20260619-usage.jsonl"
    day1.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-19T05:05:17",
                "label": "メイン分析",
                "input_tokens": 787,
                "output_tokens": 4546,
                "cache_read_tokens": 95729,
                "cache_creation_tokens": 23308,
                "cost_usd": 0.468,
                "duration_ms": 113321,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    day2 = d / "20260620-usage.jsonl"
    day2.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-20T05:06:30",
                "label": "セクタースイープ",
                "input_tokens": 3445,
                "output_tokens": 6061,
                "cache_read_tokens": 165437,
                "cache_creation_tokens": 33895,
                "cost_usd": 0.827,
                "duration_ms": 186627,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(usage_router, "USAGE_DIR", d)
    return d


async def test_dates_requires_auth(async_client, usage_dir):
    response = await async_client.get("/api/usage/dates")
    assert response.status_code == 401


async def test_list_dates_newest_first(authed_client, usage_dir):
    response = await authed_client.get("/api/usage/dates")
    assert response.status_code == 200
    assert response.json()["dates"] == ["20260620", "20260619"]


async def test_get_records_for_date(authed_client, usage_dir):
    response = await authed_client.get("/api/usage?date=20260620")
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "20260620"
    assert len(body["records"]) == 1
    assert body["records"][0]["label"] == "セクタースイープ"
    assert body["records"][0]["cost_usd"] == 0.827


async def test_summary_requires_auth(async_client, usage_dir):
    response = await async_client.get("/api/usage/summary")
    assert response.status_code == 401


async def test_summary_aggregates_per_day_oldest_first(authed_client, usage_dir):
    response = await authed_client.get("/api/usage/summary")
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert [s["date"] for s in summary] == ["2026-06-19", "2026-06-20"]
    day = summary[1]
    assert day["calls"] == 1
    assert day["output_tokens"] == 6061
    assert day["cost_usd"] == 0.827


async def test_unknown_date_returns_404(authed_client, usage_dir):
    response = await authed_client.get("/api/usage?date=20990101")
    assert response.status_code == 404


async def test_malformed_date_returns_404(authed_client, usage_dir):
    response = await authed_client.get("/api/usage?date=not-a-date")
    assert response.status_code == 404


async def test_path_traversal_date_returns_404(authed_client, usage_dir):
    # ``..`` / パス区切りを含む date はファイルに触れず 404 になること。
    response = await authed_client.get("/api/usage?date=../../tmp/20260620")
    assert response.status_code == 404
