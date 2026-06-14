"""Tests for src/chat_job_store.py — in-memory chat job store."""
import subprocess
import uuid
from unittest.mock import MagicMock

import pytest

from src import chat_job_store


@pytest.fixture(autouse=True)
def reset_store():
    chat_job_store._reset_for_tests()
    yield
    chat_job_store._reset_for_tests()


def test_create_job_assigns_uuid_and_pending_defaults():
    job = chat_job_store.create_job()
    uuid.UUID(job.job_id)  # raises if not a valid UUID
    assert job.status == "pending"
    assert job.started_at is None
    assert job.finished_at is None
    assert job.error is None
    assert len(job.events) == 0
    assert job.process is None


def test_create_job_returns_unique_ids():
    j1 = chat_job_store.create_job()
    j2 = chat_job_store.create_job()
    assert j1.job_id != j2.job_id


def test_get_job_returns_created_job():
    job = chat_job_store.create_job()
    assert chat_job_store.get_job(job.job_id) is job


def test_get_job_returns_none_for_unknown():
    assert chat_job_store.get_job("nope") is None


def test_mark_running_sets_status_and_started_at():
    job = chat_job_store.create_job()
    updated = chat_job_store.mark_running(job.job_id)
    assert updated is job
    assert job.status == "running"
    assert job.started_at is not None


def test_mark_done_sets_finished_at():
    job = chat_job_store.create_job()
    chat_job_store.mark_done(job.job_id)
    assert job.status == "done"
    assert job.finished_at is not None


def test_mark_failed_records_error_and_finished_at():
    job = chat_job_store.create_job()
    chat_job_store.mark_failed(job.job_id, "boom")
    assert job.status == "failed"
    assert job.error == "boom"
    assert job.finished_at is not None


def test_state_transitions_for_unknown_job_return_none():
    assert chat_job_store.mark_running("nope") is None
    assert chat_job_store.mark_done("nope") is None
    assert chat_job_store.mark_failed("nope", "x") is None


def test_append_event_assigns_monotonic_seq_ids():
    job = chat_job_store.create_job()
    assert chat_job_store.append_event(job.job_id, b"data: a\n\n") == 1
    assert chat_job_store.append_event(job.job_id, b"data: b\n\n") == 2
    assert list(job.events) == [(1, b"data: a\n\n"), (2, b"data: b\n\n")]


def test_append_event_returns_none_for_unknown_job():
    assert chat_job_store.append_event("nope", b"data: lost\n\n") is None


def test_event_buffer_trims_oldest_at_max_but_seq_keeps_climbing(monkeypatch):
    # The field default factory reads DEFAULT_EVENT_BUFFER_MAX at call time,
    # so monkeypatching before create_job() changes the maxlen of new deques.
    monkeypatch.setattr(chat_job_store, "DEFAULT_EVENT_BUFFER_MAX", 3)
    job = chat_job_store.create_job()
    for i in range(5):
        chat_job_store.append_event(job.job_id, f"data: {i}\n\n".encode())
    # Oldest two are dropped from the deque but the seq ids of the surviving
    # entries are stable, so a client with last_seen_seq=2 sees only 3,4,5.
    assert list(job.events) == [
        (3, b"data: 2\n\n"),
        (4, b"data: 3\n\n"),
        (5, b"data: 4\n\n"),
    ]


def test_snapshot_events_since_returns_new_events_with_status():
    job = chat_job_store.create_job()
    chat_job_store.append_event(job.job_id, b"a")
    chat_job_store.append_event(job.job_id, b"b")
    chat_job_store.append_event(job.job_id, b"c")

    events, status = chat_job_store.snapshot_events_since(job.job_id, last_seq=1)
    assert events == [(2, b"b"), (3, b"c")]
    assert status == "pending"

    # last_seq beyond the latest returns an empty list but still the live status.
    events, status = chat_job_store.snapshot_events_since(job.job_id, last_seq=99)
    assert events == []
    assert status == "pending"


def test_snapshot_events_since_returns_none_status_for_unknown_job():
    events, status = chat_job_store.snapshot_events_since("nope", last_seq=0)
    assert events == []
    assert status is None


def test_attach_process_records_handle():
    job = chat_job_store.create_job()
    fake_proc = MagicMock(spec=subprocess.Popen)
    chat_job_store.attach_process(job.job_id, fake_proc)
    assert job.process is fake_proc


def test_attach_process_silent_on_unknown_job():
    fake_proc = MagicMock(spec=subprocess.Popen)
    # Must not raise even though no job exists for this id.
    chat_job_store.attach_process("nope", fake_proc)


def test_detach_process_clears_handle_but_keeps_events():
    job = chat_job_store.create_job()
    chat_job_store.attach_process(job.job_id, MagicMock(spec=subprocess.Popen))
    chat_job_store.append_event(job.job_id, b"data: kept\n\n")
    chat_job_store.detach_process(job.job_id)
    assert job.process is None
    assert list(job.events) == [(1, b"data: kept\n\n")]


def test_detach_process_silent_on_unknown_job():
    # Must not raise.
    chat_job_store.detach_process("nope")


def test_remove_job_pops_and_returns_the_job():
    job = chat_job_store.create_job()
    removed = chat_job_store.remove_job(job.job_id)
    assert removed is job
    assert chat_job_store.get_job(job.job_id) is None


def test_remove_job_returns_none_for_unknown():
    assert chat_job_store.remove_job("nope") is None
