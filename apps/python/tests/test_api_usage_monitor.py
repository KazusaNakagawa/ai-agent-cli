"""Tests for GET /api/usage/monitor — all-traffic transcript aggregation.

Contract (#364):
- Returns project/date/model breakdowns (tokens + API-equivalent cost).
- Each ``by_date`` entry carries per-model splits for stacked charts.
- ``since`` / ``until`` (YYYY-MM-DD) filter; malformed values return 422.
- Unpriced models are listed explicitly, not silently costed at $0.
- Auth is required (Bearer), same as other protected routers.
"""
import json

import pytest

from src import usage_monitor


def _line(mid, model="claude-sonnet-5", inp=100, out=10, ts="2026-07-10T03:00:00.000Z"):
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": ts,
            "message": {
                "id": mid,
                "model": model,
                "usage": {"input_tokens": inp, "output_tokens": out},
            },
        }
    )


@pytest.fixture
def transcripts_root(tmp_path, monkeypatch):
    """Point the monitor at a tmp transcript tree with two projects."""
    root = tmp_path / "projects"
    proj_a = root / "proj-a"
    proj_a.mkdir(parents=True)
    (proj_a / "s1.jsonl").write_text(
        "\n".join(
            [
                _line("a1", model="claude-sonnet-5", inp=100, out=10),
                _line("a2", model="claude-haiku-4-5", inp=200, out=20),
                _line("a3", model="claude-future-9", inp=50, out=5, ts="2026-07-11T03:00:00.000Z"),
            ]
        )
        + "\n"
    )
    proj_b = root / "proj-b"
    proj_b.mkdir(parents=True)
    (proj_b / "s2.jsonl").write_text(_line("b1", inp=30, out=3) + "\n")
    monkeypatch.setattr(usage_monitor, "DEFAULT_ROOT", root)
    return root


# --- success ---


@pytest.mark.anyio
async def test_monitor_returns_breakdowns(authed_client, transcripts_root):
    resp = await authed_client.get("/api/usage/monitor")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_tokens"] == 110 + 220 + 55 + 33
    assert {p["key"] for p in data["by_project"]} == {"proj-a", "proj-b"}
    assert {m["key"] for m in data["by_model"]} == {
        "claude-sonnet-5",
        "claude-haiku-4-5",
        "claude-future-9",
    }
    assert data["unpriced_models"] == ["claude-future-9"]

    # by_date is chronological and carries per-model splits
    dates = [d["date"] for d in data["by_date"]]
    assert dates == sorted(dates)
    day1 = next(d for d in data["by_date"] if d["date"] == "2026-07-10")
    models = {m["key"]: m["tokens"] for m in day1["models"]}
    assert models["claude-sonnet-5"] == 110 + 33
    assert models["claude-haiku-4-5"] == 220


@pytest.mark.anyio
async def test_monitor_date_filter(authed_client, transcripts_root):
    resp = await authed_client.get(
        "/api/usage/monitor", params={"since": "2026-07-11", "until": "2026-07-11"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tokens"] == 55
    assert [d["date"] for d in data["by_date"]] == ["2026-07-11"]


# --- failure ---


@pytest.mark.anyio
async def test_monitor_rejects_malformed_date(authed_client, transcripts_root):
    resp = await authed_client.get("/api/usage/monitor", params={"since": "2026/07/11"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_monitor_requires_auth(async_client, transcripts_root):
    resp = await async_client.get("/api/usage/monitor")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_monitor_caches_repeated_requests(authed_client, transcripts_root, monkeypatch):
    from web.routers import usage as usage_router

    calls = {"n": 0}
    real_aggregate = usage_monitor.aggregate

    def counting_aggregate(*args, **kwargs):
        calls["n"] += 1
        return real_aggregate(*args, **kwargs)

    monkeypatch.setattr(usage_router.usage_monitor, "aggregate", counting_aggregate)

    first = await authed_client.get("/api/usage/monitor")
    second = await authed_client.get("/api/usage/monitor")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert calls["n"] == 1  # second request served from the TTL cache

    # A different query is a different cache key and triggers a fresh scan.
    await authed_client.get("/api/usage/monitor", params={"since": "2026-07-11"})
    assert calls["n"] == 2


# --- boundary ---


@pytest.mark.anyio
async def test_monitor_missing_root_returns_zeros(authed_client, tmp_path, monkeypatch):
    monkeypatch.setattr(usage_monitor, "DEFAULT_ROOT", tmp_path / "nope")
    resp = await authed_client.get("/api/usage/monitor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tokens"] == 0
    assert data["by_project"] == []
    assert data["by_date"] == []
