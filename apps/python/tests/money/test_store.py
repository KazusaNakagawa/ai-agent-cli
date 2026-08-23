import os

import pytest

from src.money import store
from src.money.models import Transaction
from src.money.normalize import match_key, normalize_description


def _tx(tid, date="2026-01-05", account="mufg", amount=-1000, desc="X"):
    return Transaction(
        id=tid,
        date=date,
        account=account,
        amount=amount,
        desc_raw=desc,
        desc=normalize_description(desc),
        desc_key=match_key(desc),
    )


class TestSave:
    def test_round_trips_through_the_file(self, store_path):
        store.save(store_path, [_tx("a"), _tx("b")])
        assert [t.id for t in store.load(store_path)] == ["a", "b"]

    def test_leaves_no_temporary_file_behind(self, store_path):
        store.save(store_path, [_tx("a")])
        assert [p.name for p in store_path.parent.iterdir()] == [store_path.name]

    def test_a_failed_write_keeps_the_previous_ledger(self, store_path, monkeypatch):
        # This file is the only copy of the data. Writing over it in place
        # would leave it truncated when the process dies mid-write, so the
        # replacement has to be all-or-nothing.
        store.save(store_path, [_tx("a"), _tx("b")])
        before = store_path.read_text(encoding="utf-8")

        def explode(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", explode)
        with pytest.raises(OSError):
            store.save(store_path, [_tx("c")])

        assert store_path.read_text(encoding="utf-8") == before
        assert [t.id for t in store.load(store_path)] == ["a", "b"]
        assert [p.name for p in store_path.parent.iterdir()] == [store_path.name]
