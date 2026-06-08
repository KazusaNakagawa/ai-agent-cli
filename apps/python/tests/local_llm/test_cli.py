import pytest

from src.local_llm import cli


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
    assert "qwen2.5:7b" in out
    assert "nomic-embed-text" in out


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
