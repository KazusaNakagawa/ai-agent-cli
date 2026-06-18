"""週次ブリーフィングサマリーを生成する。

このステップは「既に生成済みのブリーフィング群を決定的に要約する」低推論タスクで、
WebSearch も強い推論も要らない。コスト削減のため Claude API ではなくローカルの
Ollama スタック (src/local_llm/) で実行する (#193)。地政学・ポートフォリオ分析など
推論が重いステップは引き続き Claude API 経路 (generator/briefing.py) のまま。
"""
from datetime import date, timedelta

from src.generator.prompt import render
from src.local_llm.briefing.generate import generate_local_briefing
from src.local_llm.clients import make_ollama_client
from src.local_llm.config import load_config as load_local_config
from src.logger import get_logger
from src.prompt_safety import wrap_untrusted

logger = get_logger(__name__)


def _format_briefings(pages: list[dict]) -> str:
    """ページリストを要約プロンプト用テキストにまとめる。

    Each page body is wrapped in an untrusted-context block because the
    page text is prior LLM output that may itself have ingested
    attacker-controlled news content (indirect prompt injection).
    """
    return "\n\n---\n\n".join(
        f"### {p['date']} — {p['title']}\n\n"
        f"{wrap_untrusted(p['text'], label='previous_briefing')}"
        for p in pages
    )


def week_label() -> str:
    """今週の範囲ラベルを返す（例: 2026-04-19〜2026-04-25）。"""
    today = date.today()
    start = today - timedelta(days=6)
    return f"{start.strftime('%Y-%m-%d')}〜{today.strftime('%Y-%m-%d')}"


def generate_weekly_summary(pages: list[dict], *, ollama_client=None, cfg=None) -> str:
    """過去7日分のページリストから週次サマリーを生成して返す。

    ローカル Ollama スタックで生成する。``cfg`` / ``ollama_client`` は注入可能で、
    省略時は env ベースの ``load_local_config()`` と実 Ollama クライアントを使う
    （テストはここを差し替えてライブ呼び出しなしで検証できる）。
    """
    if not pages:
        raise ValueError("週次サマリー生成に必要なページが見つかりませんでした")

    # 明示的な None 判定: falsy だが有効な cfg/client（テスト用スタブ等）を
    # 取りこぼさないため、`or` ではなく省略時のみフォールバックする。
    if cfg is None:
        cfg = load_local_config()
    client = ollama_client if ollama_client is not None else make_ollama_client(cfg)

    prompt = render("weekly_summary", briefings=_format_briefings(pages), week_label=week_label())

    logger.info("週次サマリー生成中 (ローカル Ollama=%s, 対象ページ数=%d)...", cfg.model, len(pages))
    return generate_local_briefing(
        prompt,
        ollama_client=client,
        model=cfg.model,
        options={"num_ctx": cfg.num_ctx, "temperature": cfg.temperature},
    )
