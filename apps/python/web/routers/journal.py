"""Journal API — accumulate and read daily Markdown notes (#271, Phase 1).

- ``POST /api/journal`` appends a timestamped note to today's file
  (or to ``date`` when provided).
- ``GET /api/journal`` lists available journal dates, newest first.
- ``GET /api/journal/{date}`` returns the raw Markdown for a date.

Notes are stored under ``output/journal/`` (gitignored). Phase 2 will feed
this content into the chat flow for brainstorming.
"""
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException

from src import journal_store
from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


class JournalDate(BaseModel):
    date: str  # YYYY-MM-DD
    size: int  # bytes


class JournalListResponse(BaseModel):
    dates: list[JournalDate]


class JournalEntryResponse(BaseModel):
    date: str
    content: str


class AppendEntryRequest(BaseModel):
    content: str = Field(min_length=1)
    date: str | None = None  # defaults to today when omitted


class AppendEntryResponse(BaseModel):
    date: str


@router.get("/journal", response_model=JournalListResponse)
def list_journal() -> JournalListResponse:
    """Return available journal dates, newest first."""
    dates = [
        JournalDate(date=date, size=path.stat().st_size)
        for date, path in journal_store.list_files()
    ]
    return JournalListResponse(dates=dates)


@router.post("/journal", response_model=AppendEntryResponse)
def append_journal(req: AppendEntryRequest) -> AppendEntryResponse:
    """Append a note to the day's journal file, creating it if absent."""
    try:
        date = journal_store.append_entry(req.content, req.date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AppendEntryResponse(date=date)


@router.get("/journal/{date}", response_model=JournalEntryResponse)
def get_journal(date: str) -> JournalEntryResponse:
    """Return the Markdown body for a date. Unknown/invalid date returns 404."""
    content = journal_store.read_entry(date)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Journal not found: {date}")
    return JournalEntryResponse(date=date, content=content)
