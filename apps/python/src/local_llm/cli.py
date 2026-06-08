"""local_llm CLI エントリ。"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .clients import (
    OllamaUnavailable,
    ensure_models_available,
    make_chroma_collection,
    make_ollama_client,
)
from .config import load_config
from .indexer import Indexer
from .retriever import Retriever


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m local_llm")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--index", action="store_true", help="リポジトリを index")
    group.add_argument("--ask", metavar="QUESTION", help="質問に回答（生成あり）")
    group.add_argument("--sources", metavar="QUESTION", help="top-k のファイル位置だけ表示")
    group.add_argument("--status", action="store_true", help="現在の index 統計を表示")
    p.add_argument("--root", type=Path, default=None, help="リポジトリルート override")
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--model", default=None, help="生成モデル override")
    p.add_argument("--reset", action="store_true", help="--index 時に .chroma_db を消して全件再構築")
    return p


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
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
    return 2


def _cmd_status(cfg) -> int:
    coll = make_chroma_collection(cfg)
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
    except OllamaUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    coll = make_chroma_collection(cfg)
    import time
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
    except OllamaUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    coll = make_chroma_collection(cfg)
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
    except OllamaUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    coll = make_chroma_collection(cfg)
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
