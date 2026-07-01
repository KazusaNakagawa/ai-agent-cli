"""Generate a weekly self-reflection report and profile diff via the claude CLI."""
from __future__ import annotations

import json
import logging

from src.claude_runner import run_claude

logger = logging.getLogger(__name__)

TIMEOUT = 300
REPORT_MARKER = "## WEEKLY_REPORT"
DIFF_MARKER = "## PROFILE_DIFF"


def _build_prompt(new_entries: list[dict], existing_profile: str | None) -> str:
    entries_json = json.dumps(new_entries, ensure_ascii=False, indent=2)
    profile_section = existing_profile or "(no existing profile yet)"
    return (
        "You are analyzing a personal judgment-log (rejections/corrections/notes) "
        "to surface thinking patterns and underlying motivations for a "
        "self-reflection agent.\n\n"
        f"New log entries this week:\n{entries_json}\n\n"
        f"Existing persona profile:\n{profile_section}\n\n"
        "Do not force conclusions from thin evidence -- it is fine to say there "
        "is no notable pattern this week.\n\n"
        "Output exactly two sections, in this order, with no other text:\n"
        f"{REPORT_MARKER}\n<this week's observations, in Japanese>\n\n"
        f"{DIFF_MARKER}\n<proposed durable additions/updates to the profile, in "
        "Japanese; leave empty if nothing durable this week>\n"
    )


def parse_response(raw: str) -> tuple[str, str]:
    """Split a raw model response into (weekly_report, profile_diff).

    Raises ValueError if either section marker is missing, so the caller can
    retry with the parse error fed back into the prompt.
    """
    if REPORT_MARKER not in raw or DIFF_MARKER not in raw:
        raise ValueError("response missing required section markers")
    report_part, _, diff_part = raw.partition(DIFF_MARKER)
    report = report_part.split(REPORT_MARKER, 1)[1].strip()
    diff = diff_part.strip()
    return report, diff


def generate_self_profile_update(
    new_entries: list[dict],
    existing_profile: str | None = None,
    max_retries: int = 2,
) -> tuple[str, str] | None:
    """Return (weekly_report, profile_diff), or None when there are no new entries.

    Skipping empty weeks avoids generating a hollow "nothing happened" report
    every time the judgment log hasn't grown.
    """
    if not new_entries:
        return None

    prompt = _build_prompt(new_entries, existing_profile)
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        raw = run_claude(prompt, "self-agent profile update", timeout=TIMEOUT)
        try:
            return parse_response(raw)
        except ValueError as exc:
            last_error = exc
            logger.warning(
                "self-profile attempt %d/%d failed: %s", attempt, max_retries, exc
            )
            prompt = (
                _build_prompt(new_entries, existing_profile)
                + f"\n\nYour previous output was invalid: {exc}\n"
                "Return the two sections exactly as specified."
            )
            continue

    raise ValueError(
        f"failed to parse self-profile response after {max_retries} attempts: {last_error}"
    )
