"""Tests for the single data-home resolver (#485)."""
import importlib
import sys
from pathlib import Path

import pytest

from src import paths

APP_ROOT = Path(paths.__file__).resolve().parents[1]


# --- resolve_data_home ---


def test_data_home_defaults_to_the_in_repo_app_root():
    assert paths.resolve_data_home({}) == APP_ROOT


def test_data_home_follows_brief_lens_home(tmp_path):
    assert paths.resolve_data_home({"BRIEF_LENS_HOME": str(tmp_path)}) == tmp_path


def test_data_home_expands_user(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.resolve_data_home({"BRIEF_LENS_HOME": "~/.brief-lens"}) == tmp_path / ".brief-lens"


def test_data_home_makes_relative_paths_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert paths.resolve_data_home({"BRIEF_LENS_HOME": "data"}) == tmp_path / "data"


@pytest.mark.parametrize("value", ["", "   "])
def test_data_home_treats_blank_as_unset(value):
    assert paths.resolve_data_home({"BRIEF_LENS_HOME": value}) == APP_ROOT


# --- resolve_state_dir ---


def test_state_dir_defaults_to_dot_ai_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.resolve_state_dir({}) == tmp_path / ".ai-agent"


def test_state_dir_shares_brief_lens_home(tmp_path):
    assert paths.resolve_state_dir({"BRIEF_LENS_HOME": str(tmp_path)}) == tmp_path


# --- module constants ---


def test_module_constants_hang_off_the_env_home(monkeypatch, tmp_path):
    monkeypatch.setenv("BRIEF_LENS_HOME", str(tmp_path))
    try:
        reloaded = importlib.reload(paths)
        assert reloaded.CONFIG_DIR == tmp_path / "config"
        assert reloaded.OUTPUT_DIR == tmp_path / "output"
        assert reloaded.LOG_DIR == tmp_path / "log"
        assert reloaded.INPUT_DIR == tmp_path / "input"
        assert reloaded.TOKEN_FILE == tmp_path / "session-token"
    finally:
        monkeypatch.delenv("BRIEF_LENS_HOME")
        importlib.reload(paths)


def test_read_only_assets_stay_in_the_source_tree(monkeypatch, tmp_path):
    monkeypatch.setenv("BRIEF_LENS_HOME", str(tmp_path))
    try:
        reloaded = importlib.reload(paths)
        assert reloaded.PROMPTS_DIR == APP_ROOT / "prompts"
    finally:
        monkeypatch.delenv("BRIEF_LENS_HOME")
        importlib.reload(paths)


def test_consumers_resolve_through_paths():
    from src import constants, journal_store, logger, usage_logger
    from web import auth
    from web.routers import briefing, export

    assert constants.OUTPUT_DIR == paths.OUTPUT_DIR
    assert journal_store.JOURNAL_DIR == paths.OUTPUT_DIR / "journal"
    assert usage_logger.USAGE_DIR == paths.LOG_DIR / "usage"
    assert auth.TOKEN_FILE == paths.TOKEN_FILE
    assert briefing.BRIEFING_DIR == paths.OUTPUT_DIR / "briefing"
    assert export.INPUT_DIR == paths.INPUT_DIR
    assert logger is not None


def test_holdings_example_points_at_the_shipped_template(monkeypatch, tmp_path):
    # Load a throwaway copy under another name: reloading the real module
    # would swap its exception classes out from under other tests.
    import importlib.util

    from src.portfolio_snapshot import models

    monkeypatch.setenv("BRIEF_LENS_HOME", str(tmp_path))
    try:
        importlib.reload(paths)
        spec = importlib.util.spec_from_file_location("_holdings_probe", models.__file__)
        probe = importlib.util.module_from_spec(spec)
        # dataclasses look their module up in sys.modules while being defined.
        monkeypatch.setitem(sys.modules, spec.name, probe)
        spec.loader.exec_module(probe)
        assert probe.HOLDINGS_PATH == tmp_path / "config" / "holdings.json"
        assert probe.EXAMPLE_PATH == APP_ROOT / "config" / "holdings.json.example"
        assert probe.EXAMPLE_PATH.is_file()
    finally:
        monkeypatch.delenv("BRIEF_LENS_HOME")
        importlib.reload(paths)


# --- dotenv_files ---


def test_dotenv_files_use_the_repo_env_in_the_clone_layout(monkeypatch):
    from src import config

    monkeypatch.setattr(paths, "DATA_HOME", paths.APP_ROOT)
    assert config.dotenv_files() == [APP_ROOT.parent / ".env"]


def test_dotenv_files_use_only_the_data_home_env_when_relocated(monkeypatch, tmp_path):
    """A stray repo .env must not shadow the data-home one (load_dotenv never
    overrides a variable that is already set)."""
    from src import config

    monkeypatch.setattr(paths, "DATA_HOME", tmp_path)
    assert config.dotenv_files() == [tmp_path / ".env"]
