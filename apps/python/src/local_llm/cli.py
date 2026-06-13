"""local_llm CLI エントリ。"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path

from src.config import load_config as load_briefing_config
from src.constants import BRIEFING_OUTPUT_DIR
from src.fetcher.stocks import fetch_stock_move_map
from src.logger import get_logger
from src.notifier.notion import send_to_notion

logger = get_logger(__name__)

from .articles import count_article_fetches, enrich_with_article_text
from .briefing import (
    build_section_geo_events_prompt,
    build_section_insight_prompt,
    build_section_sector_prompt,
    build_section_topnews_prompt,
    collect_references,
    compose_briefing_md,
    ensure_geo_topics_covered,
    generate_local_briefing,
    has_simplified_chinese_text,
    load_local_briefing_system_prompt,
    prefetch_briefing_context,
    render_prefetch_debug_block,
    summarize_prefetch_hits,
    validate_urls,
)
from .portfolio import generate_portfolio_table
from .clients import (
    EmbedModelMismatch,
    OllamaUnavailable,
    ensure_models_available,
    make_chroma_collection,
    make_ollama_client,
)
from .config import load_config
from .indexer import Indexer
from .retriever import Retriever
from .search import BraveSearchClient


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m local_llm")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--index", action="store_true", help="リポジトリを index")
    group.add_argument("--ask", metavar="QUESTION", help="質問に回答（生成あり）")
    group.add_argument("--sources", metavar="QUESTION", help="top-k のファイル位置だけ表示")
    group.add_argument("--status", action="store_true", help="現在の index 統計を表示")
    group.add_argument("--briefing", action="store_true", help="ローカル LLM で日次ブリーフィングを生成")
    p.add_argument("--root", type=Path, default=None, help="リポジトリルート override")
    p.add_argument("--notion", action="store_true", help="--briefing 時に Notion へも投稿する")
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--model", default=None, help="生成モデル override")
    p.add_argument("--reset", action="store_true", help="--index 時に .chroma_db を消して全件再構築")
    return p


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.notion and not args.briefing:
        parser.error("--notion requires --briefing")
    cfg = load_config(repo_root=args.root)
    if args.model:
        cfg = cfg.__class__(**{**cfg.__dict__, "model": args.model})
    if args.top_k is not None:
        cfg = cfg.__class__(**{**cfg.__dict__, "top_k": args.top_k})

    if args.status:
        return _cmd_status(cfg)
    if args.index:
        return _cmd_index(cfg, reset=args.reset)
    if args.sources is not None:
        return _cmd_sources(cfg, args.sources)
    if args.ask is not None:
        return _cmd_ask(cfg, args.ask)
    if args.briefing:
        return _cmd_briefing(cfg, post_to_notion=args.notion)
    return 2


def _cmd_status(cfg) -> int:
    try:
        coll = make_chroma_collection(cfg)
    except EmbedModelMismatch as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    count = coll.count() if hasattr(coll, "count") else 0
    print(f"chroma_path : {cfg.chroma_path}")
    print(f"model       : {cfg.model}")
    print(f"embed_model : {cfg.embed_model}")
    print(f"top_k       : {cfg.top_k}")
    print(f"indexed     : {count} chunks")
    return 0


def _cmd_index(cfg, *, reset: bool) -> int:
    if reset and cfg.chroma_path.exists():
        ans = input(f"Delete {cfg.chroma_path}? [y/N]: ").strip().lower()
        if ans != "y":
            print("aborted")
            return 1
        shutil.rmtree(cfg.chroma_path)

    try:
        olm = make_ollama_client(cfg)
        ensure_models_available(olm, cfg.model, cfg.embed_model)
        coll = make_chroma_collection(cfg)
    except (OllamaUnavailable, EmbedModelMismatch) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    t0 = time.time()
    stats = Indexer(cfg, collection=coll, ollama_client=olm).run()
    dt = time.time() - t0
    print(
        f"indexed {stats.files} files, {stats.chunks} chunks "
        f"(added {stats.added}, updated {stats.updated}, deleted {stats.deleted}) "
        f"in {dt:.1f}s"
    )
    return 0


def _cmd_sources(cfg, question: str) -> int:
    try:
        olm = make_ollama_client(cfg)
        ensure_models_available(olm, cfg.model, cfg.embed_model)
        coll = make_chroma_collection(cfg)
    except (OllamaUnavailable, EmbedModelMismatch) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    chunks = Retriever(cfg, collection=coll, ollama_client=olm).retrieve(question)
    if not chunks:
        print("該当する文脈が見つかりませんでした")
        return 0
    print(f"{'distance':>10}  source")
    for c in chunks:
        print(f"{c.distance:>10.4f}  {c.source_path}:{c.start_line}-{c.end_line}")
    return 0


def _cmd_ask(cfg, question: str) -> int:
    try:
        olm = make_ollama_client(cfg)
        ensure_models_available(olm, cfg.model, cfg.embed_model)
        coll = make_chroma_collection(cfg)
    except (OllamaUnavailable, EmbedModelMismatch) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    retr = Retriever(cfg, collection=coll, ollama_client=olm)
    chunks = retr.retrieve(question)
    if not chunks:
        print("該当する文脈が見つかりませんでした")
        return 0

    for tok in retr.generate(question, chunks):
        print(tok, end="", flush=True)
    print()

    seen = []
    for c in chunks:
        key = f"{c.source_path}:{c.start_line}-{c.end_line}"
        if key not in seen:
            seen.append(key)
    print("\nSources:")
    for s in seen:
        print(f"  - {s}")
    return 0


def _cmd_briefing(cfg, *, post_to_notion: bool) -> int:
    logger.info("=== ローカル LLM ブリーフィング開始 (model=%s) ===", cfg.model)

    brave_api_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not brave_api_key:
        logger.error(
            "BRAVE_API_KEY が未設定です — `.env` に BRAVE_API_KEY=... を追加してください "
            "(https://api-dashboard.search.brave.com/ で Free プラン取得)"
        )
        return 1

    try:
        logger.info("Ollama 接続確認中...")
        olm = make_ollama_client(cfg)
        # briefing は generation のみ。embed_model 未 pull で弾かれないよう None で渡す。
        ensure_models_available(olm, cfg.model, embed_model=None)
    except OllamaUnavailable as e:
        logger.error("Ollama に接続できません: %s", e)
        return 1

    logger.info("briefing.json 読み込み中...")
    briefing_cfg = load_briefing_config()

    logger.info(
        "株価取得中 (tickers=%s)...", ", ".join(briefing_cfg.portfolio.tickers)
    )
    moves = fetch_stock_move_map(briefing_cfg.portfolio.tickers)

    today = date.today().isoformat()  # YYYY-MM-DD — ファイル名・プロンプト両方で共用
    search_client = BraveSearchClient(brave_api_key)

    logger.info(
        "Brave Search pre-fetch 開始 — 銘柄 %d 件 + マクロ + 地政学",
        len(briefing_cfg.portfolio.tickers),
    )
    ctx = prefetch_briefing_context(
        briefing_cfg, search_client=search_client, today=today
    )
    logger.info("Brave Search pre-fetch 完了 — 上位ヒットの記事本文を取得")

    # スニペットだけではモデルが具体的事実を書けないため、上位ヒットの本文を
    # 抽出してプロンプトに注入する (#151)。失敗分はスニペットにフォールバック。
    ctx = enrich_with_article_text(ctx)
    attempted, fetched = count_article_fetches(ctx)
    article_summary = f"{fetched}/{attempted} 件取得 (上位ヒットのみ・失敗はスニペットで代替)"
    logger.info("記事本文取得完了 — プロンプトに注入")

    system_prompt = load_local_briefing_system_prompt()

    # 5 段階のセクション分割生成 (トップニュース / セクター / 地政学 / 保有銘柄
    # テーブル / 示唆)。1 回 chat() で全セクション書かせると attention が散って
    # 保有銘柄テーブルで URL 捏造が頻発したため (#後続)、各段で渡す web_context を
    # そのセクションに必要な分だけに絞る。
    # Ollama 既定 num_ctx (4096) はセクションプロンプトでも溢れ得るため明示 (#150)。
    gen_options = {"num_ctx": cfg.num_ctx, "temperature": cfg.temperature}

    def _gen(label: str, prompt: str) -> str:
        logger.info("[section] %s 生成開始", label)
        for attempt in range(2):
            out = generate_local_briefing(
                prompt,
                ollama_client=olm,
                model=cfg.model,
                system_prompt=system_prompt,
                options=gen_options,
            )
            if not has_simplified_chinese_text(out):
                break
            if attempt == 0:
                logger.warning("[section] %s に中国語を検出 — 再生成します", label)
        logger.info("[section] %s 生成完了 (%d 文字)", label, len(out))
        return out

    body_top = _gen(
        "トップニュース",
        build_section_topnews_prompt(briefing_cfg, ctx=ctx, today=today),
    )
    # 世界 → セクター → 銘柄 のナラティブ中間層。トップニュース本文から波及
    # セクターを抽出し保有銘柄へ接続する (#162)。
    body_sector = _gen(
        "セクター影響",
        build_section_sector_prompt(briefing_cfg, prior_text=body_top, today=today),
    )
    # 保有銘柄テーブルは銘柄ごとの構造化出力 (#152)。モデルは {topic, source_index}
    # の JSON しか書かず、URL・値動き・テーブル組成は Python 側で行う。
    logger.info("[section] 保有銘柄テーブル 構造化生成開始")
    body_port = generate_portfolio_table(
        briefing_cfg.portfolio.tickers,
        ctx=ctx,
        moves=moves,
        ollama_client=olm,
        model=cfg.model,
        options=gen_options,
        today=today,
    )
    logger.info("[section] 保有銘柄テーブル 生成完了 (%d 文字)", len(body_port))
    body_geo = _gen(
        "地政学+イベント",
        build_section_geo_events_prompt(briefing_cfg, ctx=ctx, today=today),
    )
    # モデルが投資影響あるトピック (中東=原油 等) を黙って省略しても、設定済み
    # トピックの見出しと出典を Python 側で必ず残す安全網 (#175)。
    body_geo = ensure_geo_topics_covered(body_geo, ctx)
    # 世界(トップニュース) → セクター → 地政学 → 銘柄(テーブル) の順に積んで
    # 示唆段へ渡す (#162)。
    prior_text = "\n\n".join([body_top, body_sector, body_geo, body_port]).strip()
    body_insight = _gen(
        "自分への示唆",
        build_section_insight_prompt(
            briefing_cfg, prior_text=prior_text, today=today
        ),
    )

    references_md = collect_references(ctx, prior_text)
    debug_block = render_prefetch_debug_block(ctx)
    # 出力順: 世界(トップニュース) → セクター → 地政学 → 銘柄(テーブル) → 示唆 (#162)
    body = "\n\n".join(
        [
            body_top,
            body_sector,
            body_geo,
            body_port,
            body_insight,
            references_md,
            debug_block,
        ]
    )

    validation = validate_urls(body, ctx)
    if validation.fabricated > 0:
        logger.warning(
            "[briefing] URL 捏造検出: %d/%d 件を <URL未検証> に置換しました",
            validation.fabricated,
            validation.total,
        )
    else:
        logger.info(
            "[briefing] URL 検証 OK: %d/%d 件が pre-fetch 由来",
            validation.verified,
            validation.total,
        )

    md = compose_briefing_md(
        validation.body,
        model=cfg.model,
        generated_at=datetime.now(),
        url_validation=validation,
        prefetch_summary=summarize_prefetch_hits(ctx),
        article_summary=article_summary,
    )

    BRIEFING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRIEFING_OUTPUT_DIR / f"local_{today}.md"
    out_path.write_text(md, encoding="utf-8")
    logger.info("ブリーフィング保存完了: %s", out_path)

    if post_to_notion:
        if not (briefing_cfg.notion_api_key and briefing_cfg.notion_database_id):
            logger.error(
                "--notion 指定だが NOTION_API_KEY / NOTION_DATABASE_ID が未設定"
            )
            return 1
        logger.info("Notion へ投稿中...")
        url = send_to_notion(
            md,
            briefing_cfg.notion_api_key,
            briefing_cfg.notion_database_id,
            title=f"ローカルブリーフィング — {today}",  # today は YYYY-MM-DD
            tags=["agent", "local"],
        )
        if url:
            logger.info("Notion 投稿完了: %s", url)
        else:
            logger.error("Notion 投稿に失敗しました")

    logger.info("=== ローカル LLM ブリーフィング終了 ===")
    return 0
