"""Tests for /api/run and /api/run/{job_id}."""
import uuid

import pytest

from src import job_store


@pytest.fixture(autouse=True)
def reset_store():
    job_store._reset_for_tests()
    yield


@pytest.fixture(autouse=True)
def mock_handler(monkeypatch):
    """No-op handler so tests don't actually generate briefings.

    Individual tests that need a different mock (e.g. raising) re-monkeypatch
    after this autouse fixture has run."""
    monkeypatch.setattr("src.handler.lambda_handler", lambda **kwargs: None)


async def test_post_run_returns_202_with_job_id(authed_client):
    response = await authed_client.post("/api/run")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    uuid.UUID(body["job_id"])


async def test_post_run_dry_run_query_param_persists(authed_client):
    response = await authed_client.post("/api/run?dry_run=true")
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    saved = job_store.get_job(job_id)
    assert saved.dry_run is True


async def test_post_run_default_dry_run_is_false(authed_client):
    response = await authed_client.post("/api/run")
    job_id = response.json()["job_id"]
    saved = job_store.get_job(job_id)
    assert saved.dry_run is False


async def test_post_run_invokes_handler_with_dry_run_flag(authed_client, monkeypatch):
    calls = []

    def fake_handler(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("src.handler.lambda_handler", fake_handler)

    await authed_client.post("/api/run?dry_run=true")
    assert calls == [{"dry_run": True}]


async def test_post_run_success_marks_status_done(authed_client):
    response = await authed_client.post("/api/run")
    job_id = response.json()["job_id"]
    saved = job_store.get_job(job_id)
    assert saved.status == "done"
    assert saved.started_at is not None
    assert saved.finished_at is not None


async def test_post_run_failure_marks_status_failed(authed_client, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("src.handler.lambda_handler", boom)

    response = await authed_client.post("/api/run")
    job_id = response.json()["job_id"]

    saved = job_store.get_job(job_id)
    assert saved.status == "failed"
    assert saved.error == "kaboom"
    assert saved.finished_at is not None


async def test_get_run_returns_404_for_unknown(authed_client):
    response = await authed_client.get("/api/run/does-not-exist")
    assert response.status_code == 404


async def test_get_run_returns_status_and_fields(authed_client):
    post_resp = await authed_client.post("/api/run")
    job_id = post_resp.json()["job_id"]

    get_resp = await authed_client.get(f"/api/run/{job_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["job_id"] == job_id
    assert body["status"] == "done"
    assert body["started_at"] is not None
    assert body["finished_at"] is not None
    assert body["dry_run"] is False
    assert body["error"] is None


async def test_get_run_exposes_error_on_failure(authed_client, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("Discord credentials missing")

    monkeypatch.setattr("src.handler.lambda_handler", boom)

    post_resp = await authed_client.post("/api/run")
    job_id = post_resp.json()["job_id"]

    get_resp = await authed_client.get(f"/api/run/{job_id}")
    body = get_resp.json()
    assert body["status"] == "failed"
    assert body["error"] == "Discord credentials missing"


async def test_post_run_requires_bearer(async_client):
    response = await async_client.post("/api/run")
    assert response.status_code == 401


async def test_get_run_requires_bearer(async_client):
    response = await async_client.get("/api/run/some-id")
    assert response.status_code == 401
