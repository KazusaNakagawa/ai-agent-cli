"""Journal API — create and read per-entry Markdown notes (#271, #295).

- ``POST /api/journal`` creates a new entry file (for today, or ``date``).
- ``GET /api/journal`` lists available entries, newest first.
- ``GET /api/journal/{entry_id}`` returns the raw Markdown for an entry.

Notes are stored under ``output/journal/`` (gitignored), one file per entry.
"""
from pathlib import Path

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException

from src import journal_store
from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


class JournalEntry(BaseModel):
    id: str  # entry id (file stem), e.g. 2026-06-24_153045
    date: str  # YYYY-MM-DD
    size: int  # bytes
    item: str  # short label ≤20 chars, empty for legacy entries


class JournalListResponse(BaseModel):
    entries: list[JournalEntry]


class JournalEntryResponse(BaseModel):
    id: str
    date: str
    content: str


class AppendEntryRequest(BaseModel):
    content: str = Field(min_length=1)
    date: str | None = None  # defaults to today when omitted
    item: str | None = None  # optional short label (≤20 chars)


class PatchEntryRequest(BaseModel):
    content: str = Field(min_length=1)


class AppendEntryResponse(BaseModel):
    id: str
    date: str


def _to_entries(files: list[tuple[str, Path]]) -> list[JournalEntry]:
    return [
        JournalEntry(
            id=entry_id,
            date=journal_store.date_of(entry_id),
            size=path.stat().st_size,
            item=journal_store.get_item(entry_id),
        )
        for entry_id, path in files
    ]


@router.get("/journal", response_model=JournalListResponse)
def list_journal() -> JournalListResponse:
    """Return available journal entries, newest first."""
    return JournalListResponse(entries=_to_entries(journal_store.list_files()))


@router.get("/journal/trash", response_model=JournalListResponse)
def list_trash() -> JournalListResponse:
    """Return soft-deleted journal entries, newest first."""
    files = journal_store.list_trashed()
    entries = [
        JournalEntry(
            id=entry_id,
            date=journal_store.date_of(entry_id),
            size=path.stat().st_size,
            item=journal_store.get_trashed_item(entry_id),
        )
        for entry_id, path in files
    ]
    return JournalListResponse(entries=entries)


@router.post("/journal", response_model=AppendEntryResponse)
def append_journal(req: AppendEntryRequest) -> AppendEntryResponse:
    """Create a new journal entry file and return its id."""
    try:
        entry_id = journal_store.append_entry(req.content, req.date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.item:
        try:
            journal_store.save_item(entry_id, req.item)
        except Exception:
            pass  # item label is best-effort; entry is already committed
    return AppendEntryResponse(id=entry_id, date=journal_store.date_of(entry_id))


@router.patch("/journal/{entry_id}", status_code=204)
def patch_journal(entry_id: str, req: PatchEntryRequest) -> None:
    """Append additional content to an existing journal entry.

    Used when a brainstorm session continues: subsequent turns are appended to
    the same file rather than creating a new one.
    """
    ok = journal_store.append_to_entry(entry_id, req.content)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Journal not found: {entry_id}")


@router.get("/journal/{entry_id}", response_model=JournalEntryResponse)
def get_journal(entry_id: str) -> JournalEntryResponse:
    """Return the Markdown body for an entry. Unknown/invalid id returns 404."""
    content = journal_store.read_entry(entry_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Journal not found: {entry_id}")
    return JournalEntryResponse(
        id=entry_id, date=journal_store.date_of(entry_id), content=content
    )


@router.delete("/journal/{entry_id}", status_code=204)
def delete_journal(entry_id: str, purge: str | None = None) -> None:
    """Soft-delete an entry (move to trash), or permanently delete it.

    Only a literal ``?purge=true`` performs a permanent delete; any other value
    (``?purge=1``, ``?purge=yes``, ``?purge=false``, or omission) soft-deletes.
    The strict match guards against accidental permanent deletes from FastAPI's
    lenient bool coercion.
    """
    should_purge = purge == "true"
    ok = journal_store.purge(entry_id) if should_purge else journal_store.soft_delete(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Journal not found: {entry_id}")


@router.post("/journal/{entry_id}/restore", status_code=204)
def restore_journal(entry_id: str) -> None:
    """Restore a soft-deleted entry back into the active list."""
    if not journal_store.restore(entry_id):
        raise HTTPException(status_code=404, detail=f"Trashed journal not found: {entry_id}")
