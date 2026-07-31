"""macOS power-state inspection.

Exists because a launchd job that fires while the Mac is in DarkWake gets ~45
seconds of runtime before macOS goes back to sleep, severing the claude CLI's
HTTPS connection mid-response. Measured 2026-07-31: the 05:00 briefing woke at
05:06:54, slept at 05:07:39, and the sector sweep died with "Connection closed
mid-response" after three sleep cycles. ``caffeinate -s`` does not help — it is
only honoured on AC power, and the machine was on battery.
"""

import re
import subprocess

from src.logger import get_logger

logger = get_logger(__name__)

# Matches the event-type column of `pmset -g log`, e.g.
#   2026-07-31 06:01:25 +0900 Wake      \tWake from Deep Idle [CDNVA] : ...
# Only these three types describe the sleep/wake state; every other row
# (Assertions, Wake Requests, Kernel Client Acks) is noise for this purpose.
_POWER_EVENT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4} (DarkWake|Wake|Sleep)\s"
)

_PMSET_TIMEOUT = 30


def _pmset_log() -> str:
    """Return the raw `pmset -g log` output."""
    return subprocess.run(
        ["pmset", "-g", "log"],
        capture_output=True, text=True, check=True, timeout=_PMSET_TIMEOUT,
    ).stdout


def is_system_awake() -> bool:
    """True when the Mac is fully awake rather than in DarkWake or asleep.

    A full wake (lid opened, user present) keeps the machine up for as long as
    the work takes; a DarkWake does not. Anything unexpected — pmset missing,
    output unparseable, no power event in the log — fails open and reports
    awake, so a recovery run is never blocked by this guard alone.
    """
    try:
        log = _pmset_log()
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("pmset unavailable (%s) — assuming the system is awake", exc)
        return True

    last_event = None
    for line in log.splitlines():
        match = _POWER_EVENT_RE.match(line)
        if match:
            last_event = match.group(1)

    if last_event is None:
        logger.warning("no sleep/wake event found in pmset log — assuming the system is awake")
        return True

    logger.debug("last power event: %s", last_event)
    return last_event == "Wake"
