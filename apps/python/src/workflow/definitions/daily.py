"""The daily run, declared as a workflow that composes the other two.

``bin/run.sh`` used to be this composition: it ran the briefing and then the
weekly recap, under ``set -e`` so a failed briefing stopped the recap. Once
both pipelines became workflows (#461, #463) the script was the last place that
sequence was written down, and the only thing still invoking ``src.handler``
directly. Declaring the sequence here retires the script and puts the
composition in the same layer as everything else it composes (#472).

The children are looked up by id at call time rather than imported, for the
same reason the other definitions bind their handlers late: discovery must not
pull ``src.config`` in through a chain of imports, and a test can stub the
registry without reaching into this module.
"""
from typing import Any, Callable

from src.workflow.model import Step, StepContext, Workflow


def _preflight(ctx: StepContext) -> None:
    """Validate the credentials of both children.

    Declared ``preamble``, which is true of it: both handlers' preflights only
    log warnings for unset credentials. It earns its place by making
    ``workflow run daily --dry-run`` mean something — a dry run skips the two
    child steps, so without this the command would validate nothing at all.
    """
    from src import handler, weekly_handler

    handler.step_preflight(ctx)
    weekly_handler.step_preflight(ctx)


def _child(workflow_id: str) -> Callable[[StepContext], Any]:
    """Run another registered workflow as a step of this one."""

    def _run(ctx: StepContext) -> Any:
        from src.workflow.registry import get
        from src.workflow.runner import run_workflow

        # force propagates; each child keeps its own guard, so the briefing's
        # "already generated today" and the recap's Friday rule still decide
        # whether there is work to do.
        return run_workflow(get(workflow_id), force=ctx.force)

    _run.__name__ = workflow_id
    return _run


DAILY = Workflow(
    id="daily",
    title="Daily briefing, then the weekly recap on its day",
    steps=(
        Step("preflight", _preflight, preamble=True),
        # Not ``best_effort``: bin/run.sh ran under ``set -e``, so a failed
        # briefing meant the recap never started. Keeping that means a morning
        # that produced nothing to recap does not go on to recap it.
        Step("briefing", _child("briefing")),
        Step("weekly", _child("weekly")),
    ),
)
