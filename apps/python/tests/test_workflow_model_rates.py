"""Tests for the ``model-rates`` workflow (#475).

The workflow is the daily gate in ``bin/run.sh``: an unpriced model must fail
the run, while rate drift only warns so a mid-flight price change does not
break the morning job.
"""
import json
import shutil
from pathlib import Path

import pytest

from src import claude_rates, rate_check
from src.workflow import registry
from src.workflow.definitions.model_rates import UnpricedModelError
from src.workflow.runner import run_workflow

COST_STATES = Path(__file__).resolve().parents[3] / "scripts" / "tests" / "fixtures" / "cost_state.jsonl"


def _usage_line(model: str) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": "2026-10-09T03:00:00.000Z",
            "message": {"id": f"id-{model}", "model": model, "usage": {"input_tokens": 1}},
        }
    )


@pytest.fixture
def transcripts(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    (root / "p").mkdir(parents=True)
    shutil.copy(COST_STATES, root / "p" / "costs.jsonl")
    monkeypatch.setattr(rate_check, "DEFAULT_TRANSCRIPTS", root)
    return root


# --- success ---


def test_model_rates_workflow_is_registered():
    assert registry.get("model-rates").title


def test_passes_when_every_model_is_priced(transcripts):
    record = run_workflow(registry.get("model-rates"))
    assert record.status == "done"
    assert record.results["check"]["drift"] == 0
    assert record.results["check"]["reconciled"] > 0


# --- failure ---


def test_fails_the_run_on_an_unpriced_model(transcripts):
    (transcripts / "p" / "new.jsonl").write_text(_usage_line("claude-future-9") + "\n")
    with pytest.raises(UnpricedModelError, match="claude-future-9"):
        run_workflow(registry.get("model-rates"))


def test_only_warns_on_drift(transcripts, monkeypatch, caplog):
    rates = dict(claude_rates.RATES)
    inp, out, cw5m, cw1h, _ = rates["claude-opus-5"]
    rates["claude-opus-5"] = (inp, out, cw5m, cw1h, 5.0)  # cache read 10x too high
    monkeypatch.setattr(claude_rates, "_cached_rates", rates)

    record = run_workflow(registry.get("model-rates"))

    assert record.status == "done"
    assert record.results["check"]["drift"] == 1
    assert "model rate drift — claude-opus-5" in caplog.text


# --- boundary ---


def test_an_empty_transcript_root_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(rate_check, "DEFAULT_TRANSCRIPTS", tmp_path / "missing")
    record = run_workflow(registry.get("model-rates"))
    assert record.results["check"] == {"reconciled": 0, "drift": 0}


def test_rate_table_ships_under_src():
    # The npm build copies src/ wholesale but only *.example from config/, so
    # a table under config/ would be missing from the published package.
    assert claude_rates.RATES_PATH.parent.name == "src"
    assert claude_rates.RATES_PATH.is_file()
