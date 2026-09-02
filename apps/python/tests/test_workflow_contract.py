"""Contract every registered workflow must satisfy.

Parametrized over the live registry, so the checked surface grows on its own as
workflows are added — conformance never depends on a reviewer remembering the
rules. Construction-time invariants (unique step ids, blank ids, required vs
default) live in ``test_workflow_model.py``; what remains here is what can only
be checked once a workflow is registered: id uniqueness across the registry and
whether the declared callables can actually be invoked by the runner.
"""
import inspect

import pytest

from src.workflow import registry
from src.workflow.model import InputSpec, Step, Workflow

_REGISTERED = sorted(registry.discover().items())
_IDS = [wid for wid, _ in _REGISTERED]
_WORKFLOWS = [wf for _, wf in _REGISTERED]


def callable_takes_one_context(fn) -> bool:
    """True when ``fn`` can be called with a single ``StepContext`` argument."""
    try:
        inspect.signature(fn).bind(object())
    except TypeError:
        return False
    return True


def check_workflow_contract(wf: Workflow) -> None:
    """Raise ``AssertionError`` describing the first contract breach found."""
    for step in wf.steps:
        assert callable_takes_one_context(step.run), (
            f"{wf.id}.{step.id}: run must accept a single StepContext"
        )
        if step.skip_if is not None:
            assert callable_takes_one_context(step.skip_if), (
                f"{wf.id}.{step.id}: skip_if must accept a single StepContext"
            )
    if wf.guard is not None:
        assert callable_takes_one_context(wf.guard), (
            f"{wf.id}: guard must accept a single StepContext"
        )
    input_ids = [spec.id for spec in wf.inputs]
    assert len(input_ids) == len(set(input_ids)), f"{wf.id}: duplicate input id"


@pytest.mark.parametrize("wf", _WORKFLOWS, ids=_IDS)
def test_registered_workflow_satisfies_the_contract(wf):
    check_workflow_contract(wf)


def test_registered_workflow_ids_are_unique():
    assert len(_IDS) == len(set(_IDS))


# --- the checker itself -----------------------------------------------------


def test_contract_checker_accepts_a_well_formed_workflow():
    check_workflow_contract(
        Workflow(
            id="ok",
            title="OK",
            steps=(Step("a", lambda ctx: None, skip_if=lambda ctx: False),),
            inputs=(InputSpec("note"),),
            guard=lambda ctx: None,
        )
    )


def test_contract_checker_rejects_a_step_that_takes_no_context():
    wf = Workflow(id="bad", title="Bad", steps=(Step("a", lambda: None),))

    with pytest.raises(AssertionError, match="single StepContext"):
        check_workflow_contract(wf)


def test_contract_checker_rejects_a_guard_that_takes_no_context():
    wf = Workflow(id="bad", title="Bad", steps=(Step("a", lambda ctx: None),), guard=lambda: None)

    with pytest.raises(AssertionError, match="guard"):
        check_workflow_contract(wf)


def test_contract_checker_rejects_duplicate_input_ids():
    wf = Workflow(
        id="bad",
        title="Bad",
        steps=(Step("a", lambda ctx: None),),
        inputs=(InputSpec("note"), InputSpec("note")),
    )

    with pytest.raises(AssertionError, match="duplicate input id"):
        check_workflow_contract(wf)
