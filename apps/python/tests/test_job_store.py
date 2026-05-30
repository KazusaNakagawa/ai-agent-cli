"""Tests for src/job_store.py — in-memory briefing run job store."""
import uuid

import pytest

from src import job_store


@pytest.fixture(autouse=True)
def reset_store():
    job_store._reset_for_tests()
    yield


def test_create_job_returns_pending_with_uuid():
    job = job_store.create_job()
    assert job.status == "pending"
    assert job.dry_run is False
    uuid.UUID(job.job_id)  # raises if not a valid UUID


def test_create_job_with_dry_run_flag():
    job = job_store.create_job(dry_run=True)
    assert job.dry_run is True


def test_create_job_returns_unique_ids():
    j1 = job_store.create_job()
    j2 = job_store.create_job()
    assert j1.job_id != j2.job_id


def test_get_returns_none_for_unknown():
    assert job_store.get_job("does-not-exist") is None


def test_get_returns_created_job():
    j = job_store.create_job()
    same = job_store.get_job(j.job_id)
    assert same is j


def test_mark_running_sets_status_and_started_at():
    j = job_store.create_job()
    job_store.mark_running(j.job_id)
    refreshed = job_store.get_job(j.job_id)
    assert refreshed.status == "running"
    assert refreshed.started_at is not None


def test_mark_done_sets_finished_at():
    j = job_store.create_job()
    job_store.mark_running(j.job_id)
    job_store.mark_done(j.job_id)
    refreshed = job_store.get_job(j.job_id)
    assert refreshed.status == "done"
    assert refreshed.finished_at is not None


def test_mark_failed_sets_error_and_finished_at():
    j = job_store.create_job()
    job_store.mark_failed(j.job_id, "boom")
    refreshed = job_store.get_job(j.job_id)
    assert refreshed.status == "failed"
    assert refreshed.error == "boom"
    assert refreshed.finished_at is not None


def test_state_transitions_for_unknown_job_return_none():
    assert job_store.mark_running("nope") is None
    assert job_store.mark_done("nope") is None
    assert job_store.mark_failed("nope", "x") is None


def test_to_dict_serializes_all_fields():
    j = job_store.create_job(dry_run=True)
    job_store.mark_failed(j.job_id, "err")
    d = job_store.get_job(j.job_id).to_dict()
    assert set(d.keys()) == {
        "job_id",
        "status",
        "dry_run",
        "started_at",
        "finished_at",
        "error",
    }
