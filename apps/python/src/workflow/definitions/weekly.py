"""The weekly briefing recap, declared as a workflow.

The step implementations live in ``src.weekly_handler`` alongside the config,
fetchers and notifiers they use, and are bound by name at call time for the
same two reasons as the briefing definition: discovery must not import
``src.config`` (whose ``CONFIG`` is read eagerly on first attribute access), and
late binding keeps ``patch("src.weekly_handler.send_to_notion")`` and friends
effective, so the migration is verified by the original weekly-handler tests.

The Friday rule that used to live in ``bin/run.sh`` is the workflow's guard, so
``workflow run weekly`` can be invoked any day and only acts on the recap day.
"""
from typing import Any, Callable

from src.workflow.model import Step, StepContext, Workflow


def _handler(name: str) -> Callable[[StepContext], Any]:
    """Bind ``src.weekly_handler.<name>`` at call time."""

    def _run(ctx: StepContext) -> Any:
        from src import weekly_handler

        return getattr(weekly_handler, name)(ctx)

    _run.__name__ = name
    return _run


WEEKLY = Workflow(
    id="weekly",
    title="Weekly briefing recap",
    steps=(
        Step("preflight", _handler("step_preflight"), preamble=True),
        Step("fetch", _handler("step_fetch")),
        Step("summarize", _handler("step_summarize"), skip_if=_handler("skip_without_pages")),
        # Ordered before the delivery: the local copy is what the Briefing
        # viewer reads, and it must survive a Notion outage.
        Step("persist", _handler("step_persist"), skip_if=_handler("skip_without_pages")),
        Step(
            "deliver_notion",
            _handler("step_deliver_notion"),
            skip_if=_handler("skip_without_pages"),
        ),
        # Not ``best_effort``: the step absorbs its own failure so the warning
        # can name Notion comment ingestion (see ``step_ingest_comments``).
        Step("ingest_comments", _handler("step_ingest_comments"), skip_if=_handler("skip_ingest")),
    ),
    guard=_handler("weekly_guard"),
)
