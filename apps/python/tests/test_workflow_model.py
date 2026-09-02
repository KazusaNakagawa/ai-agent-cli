"""Structural invariants of the workflow data model.

These are enforced at construction time rather than by the runner: a malformed
definition should fail when its module is imported by the registry, not on the
morning its workflow first runs.
"""
import pytest

from src.workflow.model import InputSpec, Step, Workflow


def _noop(ctx):
    return None


def test_workflow_accepts_a_single_step():
    wf = Workflow(id="w", title="W", steps=(Step("only", _noop),))

    assert [s.id for s in wf.steps] == ["only"]


def test_workflow_accepts_declared_inputs():
    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("only", _noop),),
        inputs=(InputSpec("summary", required=True, help="what happened"),),
    )

    assert wf.inputs[0].id == "summary"


def test_workflow_rejects_duplicate_step_ids():
    with pytest.raises(ValueError, match="duplicate step id"):
        Workflow(id="w", title="W", steps=(Step("a", _noop), Step("a", _noop)))


def test_workflow_accepts_preamble_steps_declared_first():
    wf = Workflow(
        id="w",
        title="W",
        steps=(Step("check", _noop, preamble=True), Step("work", _noop)),
    )

    assert [s.id for s in wf.steps] == ["check", "work"]


def test_workflow_rejects_a_preamble_step_declared_after_a_normal_step():
    # Preamble steps run before the guard, so a late declaration would put the
    # declared order and the executed order out of step.
    with pytest.raises(ValueError, match="preamble step"):
        Workflow(
            id="w",
            title="W",
            steps=(Step("work", _noop), Step("check", _noop, preamble=True)),
        )


def test_workflow_rejects_no_steps():
    with pytest.raises(ValueError, match="at least one step"):
        Workflow(id="w", title="W", steps=())


@pytest.mark.parametrize("bad_id", ["", "   "])
def test_workflow_rejects_blank_id(bad_id):
    with pytest.raises(ValueError, match="workflow id"):
        Workflow(id=bad_id, title="W", steps=(Step("a", _noop),))


@pytest.mark.parametrize("bad_id", ["", "   "])
def test_step_rejects_blank_id(bad_id):
    with pytest.raises(ValueError, match="step id"):
        Step(bad_id, _noop)


@pytest.mark.parametrize("bad_id", ["", "   "])
def test_input_spec_rejects_blank_id(bad_id):
    with pytest.raises(ValueError, match="input id"):
        InputSpec(bad_id)


def test_input_spec_rejects_required_with_default():
    # A default would silently satisfy the requirement, so "required" would
    # never be able to fail — the two flags cannot both be meaningful.
    with pytest.raises(ValueError, match="required"):
        InputSpec("summary", required=True, default="x")


def test_input_spec_allows_required_without_default():
    spec = InputSpec("summary", required=True)

    assert spec.default is None
