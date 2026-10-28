"""Write the spoken briefing script and, optionally, its audio (#517).

The audio engine is macOS ``say``. It is an optional extra: a machine without
it, or a ``say`` run that fails, logs a warning and returns None — it never
fails the briefing, whose text deliveries have already gone out.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import date
from pathlib import Path

from src.constants import TIMEOUT_SPEECH_AUDIO
from src.logger import get_logger

logger = get_logger(__name__)

_ENGINE = "say"


def save_speech_script(text: str, output_dir: Path, day: date) -> Path:
    """Write the script as ``briefing_YYYY-MM-DD.txt`` and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"briefing_{day.strftime('%Y-%m-%d')}.txt"
    path.write_text(text, encoding="utf-8")
    logger.info("speech script written: %s (%d chars)", path, len(text))
    return path


def synthesize_audio(script: Path, voice: str | None = None) -> Path | None:
    """Read ``script`` aloud into an ``.m4a`` beside it, or None if that failed."""
    engine = shutil.which(_ENGINE)
    if engine is None:
        logger.warning("%r not found — skipping the briefing audio", _ENGINE)
        return None
    out = script.with_suffix(".m4a")
    # Without --data-format the .m4a holds raw PCM, about ten times the size.
    cmd = [engine, "-f", str(script), "-o", str(out), "--file-format=m4af", "--data-format=aac"]
    if voice:
        cmd += ["-v", voice]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=TIMEOUT_SPEECH_AUDIO)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("briefing audio failed: %s — skipping", exc)
        return None
    logger.info("briefing audio written: %s", out)
    return out
