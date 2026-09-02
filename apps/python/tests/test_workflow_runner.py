"""Execution semantics of ``run_workflow``.

The runner owns ordering, skipping, failure policy and the run record. It owns
neither LLM invocation nor retries (``src.claude_runner``), nor any knowledge of
delivery targets (those live inside a Step).
"""
import pytest

from src.workflow.model import InputSpec, Step, Workflow
from src.workflow.runner import WorkflowInputError, run_workflow


def _recorder(calls, name, value=None):
    def _step(ctx):
        calls.append(name)
        return value

    return _step


def _boom(ctx):
    raise RuntimeError("step exploded")


# --- ordering and data flow -------------------------------------------------


def test_steps_run_in_declared_order():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(
            Step("first", _recorder(calls, "first")),
            Step("second", _recorder(calls, "second")),
            Step("third", _recorder(calls, "third")),
        ),
    )

    record = run_workflow(wf)

    assert calls == ["first", "second", "third"]
    assert [s.id for s in record.steps] == ["first", "second", "third"]
    assert record.status == "done"


def test_a_step_reads_an_earlier_step_result_by_id():
    def produce(ctx):
        return 41

    def consume(ctx):
        return ctx.results["produce"] + 1

    wf = Workflow(id="w", title="W", steps=(Step("produce", produce), Step("consume", consume)))

    record = run_workflow(wf)

    assert record.results["consume"] == 42


def test_a_step_reads_the_run_inputs():
    def echo(ctx):
        return ctx.inputs["summary"]

    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("echo", echo),),
        inputs=(InputSpec("summary", required=True),),
    )

    record = run_workflow(wf, {"summary": "lambda error"})

    assert record.results["echo"] == "lambda error"


def test_record_carries_run_identity_and_timing():
    wf = Workflow(id="w", title="W", steps=(Step("a", _recorder([], "a")),))

    record = run_workflow(wf)

    assert record.workflow_id == "w"
    assert record.run_id
    assert record.started_at and record.finished_at
    assert record.steps[0].duration_ms >= 0


# --- input validation -------------------------------------------------------


def test_missing_required_input_fails_before_the_first_step():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("a", _recorder(calls, "a")),),
        inputs=(InputSpec("summary", required=True),),
    )

    with pytest.raises(WorkflowInputError, match="summary"):
        run_workflow(wf, {})

    assert calls == []


def test_unknown_input_is_rejected():
    # Catches a typo at the CLI rather than letting the step see None.
    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("a", _recorder([], "a")),),
        inputs=(InputSpec("summary"),),
    )

    with pytest.raises(WorkflowInputError, match="sumary"):
        run_workflow(wf, {"sumary": "typo"})


def test_declared_default_is_applied_when_the_input_is_omitted():
    def echo(ctx):
        return ctx.inputs["depth"]

    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("echo", echo),),
        inputs=(InputSpec("depth", default=3),),
    )

    assert run_workflow(wf, {}).results["echo"] == 3


def test_an_optional_input_with_no_default_is_none():
    def echo(ctx):
        return ctx.inputs["note"]

    wf = Workflow(id="w", title="W", steps=(Step("echo", echo),), inputs=(InputSpec("note"),))

    assert run_workflow(wf, {}).results["echo"] is None


# --- guard ------------------------------------------------------------------


def test_guard_reason_skips_the_whole_run():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("a", _recorder(calls, "a")),),
        guard=lambda ctx: "already ran today",
    )

    record = run_workflow(wf)

    assert record.status == "skipped"
    assert record.skip_reason == "already ran today"
    assert calls == []


def test_guard_returning_none_lets_the_run_proceed():
    calls = []
    wf = Workflow(
        id="w", title="W", steps=(Step("a", _recorder(calls, "a")),), guard=lambda ctx: None
    )

    assert run_workflow(wf).status == "done"
    assert calls == ["a"]


def test_force_bypasses_the_guard():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("a", _recorder(calls, "a")),),
        guard=lambda ctx: "already ran today",
    )

    record = run_workflow(wf, force=True)

    assert record.status == "done"
    assert calls == ["a"]


# --- skip_if ----------------------------------------------------------------


def test_skip_if_skips_only_its_own_step():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(
            Step("a", _recorder(calls, "a")),
            Step("b", _recorder(calls, "b"), skip_if=lambda ctx: True),
            Step("c", _recorder(calls, "c")),
        ),
    )

    record = run_workflow(wf)

    assert calls == ["a", "c"]
    assert {s.id: s.status for s in record.steps} == {"a": "done", "b": "skipped", "c": "done"}
    assert record.status == "done"


def test_skip_if_can_read_an_earlier_result():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(
            Step("a", _recorder(calls, "a", value=False)),
            Step("b", _recorder(calls, "b"), skip_if=lambda ctx: not ctx.results["a"]),
        ),
    )

    record = run_workflow(wf)

    assert calls == ["a"]
    assert next(s for s in record.steps if s.id == "b").status == "skipped"
    assert "b" not in record.results


# --- failure policy ---------------------------------------------------------


def test_best_effort_failure_does_not_stop_the_run():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(
            Step("flaky", _boom, best_effort=True),
            Step("after", _recorder(calls, "after")),
        ),
    )

    record = run_workflow(wf)

    assert record.status == "done"
    assert calls == ["after"]
    failed = next(s for s in record.steps if s.id == "flaky")
    assert failed.status == "failed"
    assert "step exploded" in failed.error


def test_a_normal_step_failure_propagates_and_stops_the_run():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("boom", _boom), Step("after", _recorder(calls, "after"))),
    )

    with pytest.raises(RuntimeError, match="step exploded"):
        run_workflow(wf)

    assert calls == []


def test_a_failed_run_record_is_attached_to_the_raised_exception():
    # The record is the only trace of a failed run, so it must survive the
    # raise — #455 persists it from here.
    wf = Workflow(id="w", title="W", steps=(Step("boom", _boom),))

    with pytest.raises(RuntimeError) as exc_info:
        run_workflow(wf)

    record = exc_info.value.workflow_run_record
    assert record.status == "failed"
    assert record.steps[0].status == "failed"
    assert record.finished_at


# --- dry run ----------------------------------------------------------------


def test_dry_run_executes_only_dry_run_ok_steps():
    calls = []
    wf = Workflow(
        id="w",
        title="W",
        steps=(
            Step("preflight", _recorder(calls, "preflight"), dry_run_ok=True),
            Step("deliver", _recorder(calls, "deliver")),
        ),
    )

    record = run_workflow(wf, dry_run=True)

    assert calls == ["preflight"]
    assert record.status == "dry_run"
    assert {s.id: s.status for s in record.steps} == {"preflight": "done", "deliver": "skipped"}


def test_dry_run_still_validates_inputs():
    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("a", _recorder([], "a")),),
        inputs=(InputSpec("summary", required=True),),
    )

    with pytest.raises(WorkflowInputError):
        run_workflow(wf, {}, dry_run=True)
