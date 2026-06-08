"""ローカル LLM 用ブリーフィング生成。プロンプト組立・Ollama 呼び出し・MD 組成。"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Iterable, Protocol

from src.config import BriefingConfig
from src.generator.briefing import (
    build_geopolitical_context,
    build_watch_events_context,
    join_safe,
)
from src.generator.prompt import render


def build_local_briefing_prompt(cfg: BriefingConfig, stocks: str) -> str:
    """既存ヘルパを再利用して local_briefing.md テンプレートに入力を流し込む。

    Note: watch_sectors は意図的に渡していない。Claude 経路の並列セクタースイープに
    相当する出力をローカル版では行わない方針 (#142 spec の non-goal)。
    """
    tickers = join_safe(cfg.portfolio.tickers, sep=", ")
    themes = join_safe(cfg.portfolio.themes, sep=", ")
    return render(
        "local_briefing",
        tickers=tickers,
        themes=themes,
        geopolitical=build_geopolitical_context(cfg),
        watch_events=build_watch_events_context(cfg),
        stocks=stocks,
    )


class _OllamaLike(Protocol):
    def generate(self, model: str, prompt: str, stream: bool) -> Iterable[dict]: ...


def generate_local_briefing(
    prompt: str,
    *,
    ollama_client: _OllamaLike,
    model: str,
) -> str:
    """Ollama の stream を 1 本のテキストに集約しつつ stdout にもエコーする。"""
    pieces: list[str] = []
    for piece in ollama_client.generate(model=model, prompt=prompt, stream=True):
        tok = piece.get("response", "")
        if tok:
            pieces.append(tok)
            print(tok, end="", flush=True)
        if piece.get("done"):
            break
    print()  # final newline so the next CLI output starts fresh
    return "".join(pieces)


def compose_briefing_md(
    body: str,
    *,
    model: str,
    generated_at: datetime,
) -> str:
    """Caveat ヘッダと本文を `---` で連結する。"""
    head = (
        "> **※ ローカル LLM 生成（実験版）**\n"
        f"> - model: {model}\n"
        "> - WebSearch 未使用 — モデルの学習知識と入力データのみで生成\n"
        f"> - generated_at: {generated_at.isoformat(timespec='seconds')}\n"
    )
    return f"{head}\n---\n\n{body.rstrip()}\n"
