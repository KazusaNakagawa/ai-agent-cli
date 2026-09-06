import os

import pytest

from src.money import store
from src.money.models import MoneyError, Transaction
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


class TestLoad:
    # The ledger is a text file precisely so it can be repaired by hand, so a
    # hand-edit that breaks it has to come back as a readable error naming the
    # line — the CLI only turns MoneyError into an exit, anything else is a
    # traceback.
    def test_a_broken_line_names_the_file_and_the_line(self, store_path):
        store.save(store_path, [_tx("a"), _tx("b")])
        lines = store_path.read_text(encoding="utf-8").splitlines()
        lines[1] = lines[1][:-3]
        store_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with pytest.raises(MoneyError, match="line 2: is not valid JSON"):
            store.load(store_path)

    def test_a_line_that_is_not_an_object_is_refused(self, store_path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("[1, 2]\n", encoding="utf-8")

        with pytest.raises(MoneyError, match="expected a transaction object"):
            store.load(store_path)

    def test_a_line_missing_required_fields_is_refused(self, store_path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text('{"id": "a"}\n', encoding="utf-8")

        with pytest.raises(MoneyError, match="is not a transaction"):
            store.load(store_path)
