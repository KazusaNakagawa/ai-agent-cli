import pytest

from src.local_llm import cli
from src.local_llm.clients import EmbedModelMismatch


@pytest.fixture(autouse=True)
def _isolate_local_llm_env(monkeypatch):
    """ambient な LOCAL_LLM_* env (運用者の .env 等) を消してデフォルト挙動を検証する。

    運用者が LOCAL_LLM_MODEL=gemma2:9b 等を設定していると --status の出力が変わり
    アサーションが env 依存で揺れる。CLI の既定値経路をテストするため隔離する。
    """
    for key in ("LOCAL_LLM_MODEL", "LOCAL_LLM_EMBED_MODEL", "LOCAL_LLM_NUM_CTX",
                "LOCAL_LLM_TEMPERATURE", "LOCAL_LLM_TOP_K"):
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


def _raise_mismatch(_cfg):
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
