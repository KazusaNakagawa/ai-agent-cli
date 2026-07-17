import pytest

from src.local_llm import cli
from src.local_llm.clients import EmbedModelMismatch


@pytest.fixture(autouse=True)
def _isolate_local_llm_env(monkeypatch):
    """ambient な LOCAL_LLM_* env (運用者の .env 等) を消してデフォルト挙動を検証する。

    運用者が LOCAL_LLM_MODEL=gemma2:9b 等を設定していると --status の出力が変わり
    アサーションが env 依存で揺れる。CLI の既定値経路をテストするため隔離する。
    """
    for key in ("LOCAL_LLM_MODEL", "LOCAL_LLM_SYNTHESIS_MODEL", "LOCAL_LLM_EMBED_MODEL",
                "LOCAL_LLM_NUM_CTX", "LOCAL_LLM_TEMPERATURE", "LOCAL_LLM_TOP_K"):
        monkeypatch.delenv(key, raising=False)


def test_cli_status_prints_summary(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))

    class FakeColl:
        def count(self):
            return 42

    monkeypatch.setattr(cli, "make_chroma_collection", lambda cfg: FakeColl())

    rc = cli.main(["--status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "42" in out
    assert "qwen2.5:14b" in out
    assert "bge-m3" in out


def test_cli_sources_prints_top_k(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))

    from src.local_llm.retriever import RetrievedChunk

    class FakeRetriever:
        def __init__(self, *a, **kw): pass
        def retrieve(self, question, top_k=None):
            return [
                RetrievedChunk(source_path="a.py", start_line=1, end_line=10, text="", distance=0.1),
                RetrievedChunk(source_path="b.md", start_line=4, end_line=8, text="", distance=0.5),
            ]

    monkeypatch.setattr(cli, "Retriever", FakeRetriever)
    monkeypatch.setattr(cli, "make_chroma_collection", lambda cfg: object())
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)

    rc = cli.main(["--sources", "認証はどう動く？", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "a.py:1-10" in out
    assert "b.md:4-8" in out


def test_cli_requires_one_action(tmp_path):
    with pytest.raises(SystemExit):
        cli.main([])


def _raise_mismatch(_cfg, **_kw):
    raise EmbedModelMismatch(
        "embed_model='nomic-embed-text' vs 'bge-m3'. Rebuild with: "
        "bin/local_llm.sh --index --reset"
    )


def test_cli_status_exits_on_embed_model_mismatch(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(cli, "make_chroma_collection", _raise_mismatch)

    rc = cli.main(["--status", "--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "--index --reset" in captured.err
    assert "nomic-embed-text" in captured.err
    assert "bge-m3" in captured.err


def test_cli_sources_exits_on_embed_model_mismatch(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "make_chroma_collection", _raise_mismatch)

    rc = cli.main(["--sources", "test", "--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "--index --reset" in captured.err
    assert "nomic-embed-text" in captured.err
    assert "bge-m3" in captured.err


def test_cli_index_exits_on_embed_model_mismatch(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "make_chroma_collection", _raise_mismatch)

    rc = cli.main(["--index", "--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "--index --reset" in captured.err
    assert "nomic-embed-text" in captured.err
    assert "bge-m3" in captured.err


def test_cli_index_briefings_exits_on_embed_model_mismatch(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "make_chroma_collection", _raise_mismatch)

    rc = cli.main(["--index-briefings", "--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "--index --reset" in captured.err
    assert "nomic-embed-text" in captured.err
    assert "bge-m3" in captured.err


def test_cli_index_briefings_runs_and_prints_stats(monkeypatch, tmp_path, capsys):
    from src.local_llm.indexer import IndexStats

    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "make_chroma_collection", lambda cfg, collection_name=None: object())

    class FakeIndexer:
        def __init__(self, cfg, *, collection, ollama_client):
            self.cfg = cfg

        def run(self):
            return IndexStats(files=3, chunks=9, added=9, updated=0, deleted=0)

    monkeypatch.setattr(cli, "Indexer", FakeIndexer)

    rc = cli.main(["--index-briefings", "--root", str(tmp_path)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "3 files" in out
    assert "9 chunks" in out


def test_cli_index_briefings_targets_briefing_output_dir_not_repo_root(monkeypatch, tmp_path, capsys):
    """The indexed repo_root must be the briefing output dir, not --root,
    so `--index-briefings` never re-scans the source tree (#395)."""
    from src.constants import BRIEFING_OUTPUT_DIR
    from src.local_llm.indexer import IndexStats

    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "make_chroma_collection", lambda cfg, collection_name=None: object())

    seen_roots = []

    class FakeIndexer:
        def __init__(self, cfg, *, collection, ollama_client):
            seen_roots.append(cfg.repo_root)

        def run(self):
            return IndexStats()

    monkeypatch.setattr(cli, "Indexer", FakeIndexer)

    cli.main(["--index-briefings", "--root", str(tmp_path)])

    assert seen_roots == [BRIEFING_OUTPUT_DIR]


def test_cli_index_briefings_reset_deletes_only_briefing_collection(monkeypatch, tmp_path, capsys):
    from src.local_llm.indexer import IndexStats

    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "make_chroma_collection", lambda cfg, collection_name=None: object())
    monkeypatch.setattr(cli, "Indexer", lambda cfg, **kw: type("_", (), {"run": lambda self: IndexStats()})())
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    deleted = []
    monkeypatch.setattr(cli, "delete_collection", lambda cfg, name: deleted.append(name))

    from src.local_llm.config import BRIEFING_COLLECTION_NAME

    rc = cli.main(["--index-briefings", "--reset", "--root", str(tmp_path)])

    assert rc == 0
    assert deleted == [BRIEFING_COLLECTION_NAME]


def test_cli_ask_exits_on_embed_model_mismatch(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LOCAL_LLM_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(cli, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(cli, "ensure_models_available", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "make_chroma_collection", _raise_mismatch)

    rc = cli.main(["--ask", "test", "--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "--index --reset" in captured.err
    assert "nomic-embed-text" in captured.err
    assert "bge-m3" in captured.err


def test_cli_notion_without_briefing_errors(tmp_path, capsys):
    # --notion is meaningless without --briefing; argparse should reject it
    # rather than silently ignore.
    with pytest.raises(SystemExit):
        cli.main(["--status", "--notion", "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert "--notion requires --briefing" in err


def _stub_briefing_pipeline(monkeypatch, cli_mod, tmp_path, gen_calls, ensured):
    """Patch out the heavy --briefing collaborators, recording the model used per
    section generation so the dual-model routing (#171) can be asserted."""
    import types

    monkeypatch.setenv("BRAVE_API_KEY", "test-key")

    monkeypatch.setattr(cli_mod, "make_ollama_client", lambda cfg: object())
    monkeypatch.setattr(
        cli_mod,
        "ensure_models_available",
        lambda client, model, embed_model=None: ensured.append(model),
    )

    briefing_cfg = types.SimpleNamespace(
        portfolio=types.SimpleNamespace(tickers=["AAA"]),
        notion_api_key=None,
        notion_database_id=None,
    )
    monkeypatch.setattr(cli_mod, "load_briefing_config", lambda: briefing_cfg)
    monkeypatch.setattr(cli_mod, "fetch_stock_move_map", lambda tickers: {})
    monkeypatch.setattr(cli_mod, "BraveSearchClient", lambda key: object())
    monkeypatch.setattr(cli_mod, "prefetch_briefing_context", lambda *a, **k: object())
    monkeypatch.setattr(cli_mod, "enrich_with_article_text", lambda ctx: ctx)
    monkeypatch.setattr(cli_mod, "count_article_fetches", lambda ctx: (0, 0))
    monkeypatch.setattr(cli_mod, "load_local_briefing_system_prompt", lambda: "sys")
    for name in (
        "build_section_topnews_prompt",
        "build_section_sector_prompt",
        "build_section_geo_events_prompt",
        "build_section_insight_prompt",
    ):
        monkeypatch.setattr(cli_mod, name, lambda *a, **k: "prompt")
    monkeypatch.setattr(cli_mod, "generate_portfolio_table", lambda *a, **k: "PORT")
    monkeypatch.setattr(cli_mod, "ensure_geo_topics_covered", lambda body, ctx: body)
    monkeypatch.setattr(cli_mod, "collect_references", lambda ctx, prior: "REF")
    monkeypatch.setattr(cli_mod, "render_prefetch_debug_block", lambda ctx: "DBG")
    monkeypatch.setattr(cli_mod, "summarize_prefetch_hits", lambda ctx: "SUM")
    monkeypatch.setattr(
        cli_mod,
        "validate_urls",
        lambda body, ctx: types.SimpleNamespace(
            body=body, fabricated=0, total=0, verified=0
        ),
    )
    monkeypatch.setattr(cli_mod, "compose_briefing_md", lambda *a, **k: "MD")
    monkeypatch.setattr(cli_mod, "BRIEFING_OUTPUT_DIR", tmp_path / "out")

    def _fake_generate(prompt, *, ollama_client, model, system_prompt, options):
        gen_calls.append(model)
        return "section"

    monkeypatch.setattr(cli_mod, "generate_local_briefing", _fake_generate)


def test_briefing_routes_only_insight_to_synthesis_model(monkeypatch, tmp_path):
    # Extraction/summary stages use the main model; only the final synthesis
    # (insight) stage routes to the separate reasoning model (#171).
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:14b")
    monkeypatch.setenv("LOCAL_LLM_SYNTHESIS_MODEL", "qwen2.5:32b")

    gen_calls: list[str] = []
    ensured: list[str] = []
    _stub_briefing_pipeline(monkeypatch, cli, tmp_path, gen_calls, ensured)

    rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    # top / sector / geo / insight — only the last (insight) uses the synthesis model.
    assert gen_calls == [
        "qwen2.5:14b",
        "qwen2.5:14b",
        "qwen2.5:14b",
        "qwen2.5:32b",
    ]
    # Both models are verified as pulled before generation.
    assert "qwen2.5:14b" in ensured
    assert "qwen2.5:32b" in ensured


def test_briefing_synthesis_model_defaults_to_main_model(monkeypatch, tmp_path):
    # With no separate synthesis model configured, every stage uses the main
    # model and the extra availability check is skipped.
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:14b")

    gen_calls: list[str] = []
    ensured: list[str] = []
    _stub_briefing_pipeline(monkeypatch, cli, tmp_path, gen_calls, ensured)

    rc = cli.main(["--briefing", "--root", str(tmp_path)])

    assert rc == 0
    assert gen_calls == ["qwen2.5:14b"] * 4
    assert ensured == ["qwen2.5:14b"]
