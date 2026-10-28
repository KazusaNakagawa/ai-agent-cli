"""The briefing's Marp slide deck step (#518)."""
from unittest.mock import MagicMock, patch

import pytest

from src.config import SlidesConfig
from tests.generator.test_briefscript_notion import _full_doc


def _run_step(tmp_path, slides: SlidesConfig):
    from src.handler import step_slides

    ctx = MagicMock()
    ctx.results = {"generate": _full_doc()}
    with (
        patch("src.handler.CONFIG") as cfg,
        patch("src.handler.SLIDES_OUTPUT_DIR", tmp_path / "slides"),
    ):
        cfg.slides = slides
        return step_slides(ctx)


def test_writes_the_dated_deck(tmp_path):
    path = _run_step(tmp_path, SlidesConfig())
    assert path == str(tmp_path / "slides" / "briefing_2026-10-25.slides.md")
    assert open(path, encoding="utf-8").read().startswith("---\nmarp: true\n")


def test_max_claims_comes_from_the_config(tmp_path):
    with patch("src.handler.render_document_slides", return_value="deck") as render:
        _run_step(tmp_path, SlidesConfig(max_claims=1))
    assert render.call_args.kwargs["max_claims"] == 1


def test_write_failure_is_swallowed(tmp_path, caplog):
    with patch("src.handler.save_slides", side_effect=OSError("disk full")):
        assert _run_step(tmp_path, SlidesConfig()) is None
    assert any("slide deck write failed" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("bad", [{"max_claims": 0}, {"max_claim": 3}])
def test_invalid_config_is_rejected(bad):
    with pytest.raises(ValueError):
        SlidesConfig(**bad)
