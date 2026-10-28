"""The daily composite workflow.

``daily`` is the one command the scheduled job runs. It exists to preserve what
``bin/run.sh`` did — the briefing, the weekly recap on its own day, then the
model-rate check — now that all three are workflows in their own right. These tests pin the composition
itself, not the children: the children are stubbed so a failure here always
means the composite is wrong.
"""
import types
from unittest.mock import patch

import pytest

from src.workflow import registry
from src.workflow.model import Step, Workflow
from src.workflow.runner import run_workflow


@pytest.fixture
def calls():
    return []


def _child(workflow_id: str, calls: list, *, guarded: bool = False, fail: bool = False):
    """A stand-in for one of the real child workflows.

    ``guarded`` gives it a guard that always skips, which is how the tests
    observe whether ``force`` reached the child: only a forced run gets past it.
    """

    def _step(ctx):
        if fail:
            raise RuntimeError(f"{workflow_id} blew up")
        calls.append(workflow_id)
        return f"{workflow_id} ran"

    return Workflow(
        id=workflow_id,
        title=workflow_id,
        steps=(Step("work", _step),),
        guard=(lambda ctx: "guarded") if guarded else None,
    )


def _stub_registry(children: dict[str, Workflow]):
    """Patch registry lookups so ``daily`` resolves to the stub children."""
    return patch.object(registry, "get", lambda workflow_id, **kw: children[workflow_id])


def _children(calls: list, **overrides: Workflow) -> dict[str, Workflow]:
    """One stub per child of ``daily``; ``overrides`` replaces individual ones."""
    children = {wid: _child(wid, calls) for wid in ("briefing", "weekly", "model-rates")}
    children.update({wid.replace("_", "-"): wf for wid, wf in overrides.items()})
    return children


def _daily():
    from src.workflow.definitions.daily import DAILY

    return DAILY


def test_runs_the_briefing_the_weekly_recap_then_the_model_rate_check(calls):
    """Success: all three children run, in the order bin/run.sh ran them."""
    with _stub_registry(_children(calls)):
        record = run_workflow(_daily())

    assert calls == ["briefing", "weekly", "model-rates"]
    assert record.status == "done"
    assert [s.id for s in record.steps if s.status == "done"] == [
        "preflight", "briefing", "weekly", "model-rates",
    ]


def test_a_failed_briefing_stops_the_weekly_recap(calls):
    """Failure: bin/run.sh ran under `set -e`, so a failed briefing meant the
    recap never started. The composite must not quietly become more permissive."""
    children = _children(calls, briefing=_child("briefing", calls, fail=True))

    with _stub_registry(children), pytest.raises(RuntimeError, match="briefing blew up") as exc:
        run_workflow(_daily())

    assert calls == []
    # The runner attaches the record to the exception, so the failed run still
    # says how far it got: neither the recap nor the rate check may appear.
    record = exc.value.workflow_run_record
    assert [s.id for s in record.steps] == ["preflight", "briefing"]
    assert record.steps[-1].status == "failed"


def test_a_failed_recap_stops_the_model_rate_check(calls):
    """Failure: the same `set -e` held between the recap and the rate check.
    A morning that already failed is already in front of the operator, and the
    rate check only reads transcripts, so it loses nothing by waiting a day."""
    children = _children(calls, weekly=_child("weekly", calls, fail=True))

    with _stub_registry(children), pytest.raises(RuntimeError, match="weekly blew up") as exc:
        run_workflow(_daily())

    assert calls == ["briefing"]
    assert [s.id for s in exc.value.workflow_run_record.steps] == [
        "preflight", "briefing", "weekly",
    ]


def test_a_failed_model_rate_check_fails_the_run_after_the_deliveries(calls):
    """Failure: the rate check runs last so its failure cannot hold back the
    briefing or the recap, yet it must still fail the run — that is how an
    unpriced model gets noticed the next morning."""
    children = _children(calls, model_rates=_child("model-rates", calls, fail=True))

    with _stub_registry(children), pytest.raises(RuntimeError, match="model-rates blew up") as exc:
        run_workflow(_daily())

    assert calls == ["briefing", "weekly"]
    record = exc.value.workflow_run_record
    assert record.status == "failed"
    assert record.steps[-1].id == "model-rates"


def test_force_reaches_the_children(calls):
    """Success: --force on the composite must bypass each child's own guard.

    Without propagation the switch would look accepted at the CLI and do
    nothing, which is worse than rejecting it.
    """
    children = _children(
        calls,
        briefing=_child("briefing", calls, guarded=True),
        weekly=_child("weekly", calls, guarded=True),
    )

    with _stub_registry(children):
        run_workflow(_daily(), force=True)

    assert calls == ["briefing", "weekly", "model-rates"]


def test_without_force_each_child_still_consults_its_own_guard(calls):
    """Boundary: the composite declares no guard of its own — idempotency stays
    with the child that owns it, so a guarded child skips on an ordinary run."""
    children = _children(
        calls,
        briefing=_child("briefing", calls, guarded=True),
        weekly=_child("weekly", calls, guarded=True),
    )

    with _stub_registry(children):
        record = run_workflow(_daily())

    assert calls == ["model-rates"]
    assert record.status == "done"
    assert record.results["briefing"].status == "skipped"
    assert record.results["weekly"].status == "skipped"


def test_a_dry_run_validates_config_without_running_any_child(calls):
    """Boundary: --dry-run must still be worth typing. The preamble runs, so
    credentials are checked, and no child is started."""
    children = _children(calls)
    preflights = []

    with _stub_registry(children), \
         patch("src.handler.step_preflight", lambda ctx: preflights.append("briefing")), \
         patch("src.weekly_handler.step_preflight", lambda ctx: preflights.append("weekly")):
        record = run_workflow(_daily(), dry_run=True)

    assert calls == []
    assert preflights == ["briefing", "weekly"]
    assert record.status == "dry_run"


def test_the_preflight_checks_both_children_credentials():
    """Success: the composite's preamble covers both children, because a dry run
    of `daily` is the only place either one is validated."""
    preflights = []

    with patch("src.handler.step_preflight", lambda ctx: preflights.append("briefing")), \
         patch("src.weekly_handler.step_preflight", lambda ctx: preflights.append("weekly")):
        from src.workflow.definitions.daily import _preflight

        _preflight(types.SimpleNamespace())

    assert preflights == ["briefing", "weekly"]


def test_daily_is_discoverable_by_the_registry():
    """Success: registration is the act of adding the module — nothing else."""
    found = registry.discover()

    assert "daily" in found
    assert found["daily"].id == "daily"


def test_daily_resolves_from_an_unambiguous_prefix():
    """Boundary: 'd' names only this workflow, so the CLI shorthand must reach it."""
    assert registry.resolve("d").id == "daily"
