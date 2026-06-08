from pathlib import Path

from src.local_llm.config import load_config
from src.local_llm.indexer import Chunk, chunk_file, iter_source_files


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_iter_source_files_filters_excluded_and_extensions(tmp_path):
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    _write(tmp_path / "README.md", "# hi\n")
    _write(tmp_path / "node_modules" / "skip.js", "nope\n")
    _write(tmp_path / "image.png", "binary")
    big = tmp_path / "big.py"
    big.write_text("x\n" * 300_000)  # > 500KB

    cfg = load_config(repo_root=tmp_path)
    found = sorted(p.relative_to(tmp_path).as_posix() for p in iter_source_files(cfg))

    assert found == ["README.md", "src/a.py"]


def test_chunk_file_splits_with_overlap(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("\n".join(f"line{i}" for i in range(150)) + "\n")

    cfg = load_config(repo_root=tmp_path)
    chunks = chunk_file(f, cfg)

    assert all(isinstance(c, Chunk) for c in chunks)
    # 60 lines / 10 overlap → starts at 1, 51, 101, ...
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 60
    assert chunks[1].start_line == 51
    assert chunks[1].end_line == 110
    assert chunks[-1].end_line >= 150
    assert chunks[0].source_path == "x.py"
    assert "line0" in chunks[0].text


def test_chunk_file_short_file_one_chunk(tmp_path):
    f = tmp_path / "short.py"
    f.write_text("a\nb\nc\n")
    cfg = load_config(repo_root=tmp_path)
    chunks = chunk_file(f, cfg)
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3


def test_chunk_file_chunk_id_changes_with_content(tmp_path):
    f = tmp_path / "c.py"
    f.write_text("hello\n")
    cfg = load_config(repo_root=tmp_path)
    id1 = chunk_file(f, cfg)[0].chunk_id

    f.write_text("hello world\n")
    id2 = chunk_file(f, cfg)[0].chunk_id

    assert id1 != id2
