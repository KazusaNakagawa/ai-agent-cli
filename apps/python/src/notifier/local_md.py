import re
from datetime import date
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)

_BRIEFING_FILE_RE = re.compile(r"^briefing_(\d{4}-\d{2}-\d{2})\.md$")


def save_briefing_md(
    text: str,
    output_dir: Path,
    retention_days: int,
    today: date | None = None,
    *,
    rotation_enabled: bool = True,
) -> Path:
    """ブリーフィング本文を briefing_YYYY-MM-DD.md として書き込む。

    rotation_enabled=True のとき output_dir 内の同パターンファイルを
    新しい順に retention_days 件残して削除する。
    rotation_enabled=False のとき削除は行わず全ファイルを無制限に保持する。
    """
    if retention_days < 1:
        raise ValueError(
            f"retention_days は 1 以上である必要があります (got {retention_days})"
        )

    today = today or date.today()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"briefing_{today.strftime('%Y-%m-%d')}.md"
    path.write_text(text, encoding="utf-8")
    logger.info("ローカル MD 出力: %s (%d文字)", path, len(text))

    if rotation_enabled:
        _prune_old(output_dir, retention_days)
    else:
        logger.debug("ローテーション無効 — 古い MD は削除しません")
    return path


def write_md_file(output_dir: Path, filename: str, text: str) -> Path:
    """output_dir/filename にテキストを書き込む。ディレクトリがなければ作成する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(text, encoding="utf-8")
    logger.info("MD 出力: %s (%d文字)", path, len(text))
    return path


def _prune_old(output_dir: Path, retention_days: int) -> None:
    matched = [
        p for p in output_dir.iterdir()
        if p.is_file() and _BRIEFING_FILE_RE.match(p.name)
    ]
    matched.sort(key=lambda p: p.name, reverse=True)  # ISO date sorts lexicographically
    for stale in matched[retention_days:]:
        try:
            stale.unlink()
            logger.info("古い MD を削除: %s", stale.name)
        except FileNotFoundError:
            pass
