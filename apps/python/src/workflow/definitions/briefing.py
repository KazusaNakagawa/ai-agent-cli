"""The daily market briefing, declared as a workflow.

The step implementations live in ``src.handler`` alongside the config,
fetchers and notifiers they use. They are bound by name at call time rather
than imported here, for two reasons:

* ``src.handler`` imports ``src.config``, whose ``CONFIG`` is read eagerly on
  first attribute access. Importing it at module scope would make
  ``workflow list`` fail on a machine with no ``config/briefing.json`` —
  discovery must never depend on one workflow's runtime configuration.
* Late binding keeps ``patch("src.handler.send_to_discord")`` and friends
  effective, so the migration is verified by the original handler tests
  rather than by tests rewritten to match the new structure.
"""
from typing import Any, Callable

from src.workflow.model import Step, StepContext, Workflow


def _handler(name: str) -> Callable[[StepContext], Any]:
    """Bind ``src.handler.<name>`` at call time."""

    def _run(ctx: StepContext) -> Any:
        from src import handler

        return getattr(handler, name)(ctx)

    _run.__name__ = name
    return _run


BRIEFING = Workflow(
    id="briefing",
    title="Daily market briefing",
    steps=(
        Step("preflight", _handler("step_preflight"), preamble=True),
        Step("fx", _handler("step_fx")),
        Step("stocks", _handler("step_stocks")),
        Step("generate", _handler("step_generate")),
        # After the paid generate step so a chart failure cannot waste it, and
        # before the deliveries that carry the PNG. best_effort: the briefing
        # body ships with or without its illustration.
        Step("chart", _handler("step_chart"), best_effort=True),
        # Ordered before every delivery: the local copy is the operator's
        # diagnostic fallback and must survive a Discord or Notion outage.
        Step("persist", _handler("step_persist")),
        # Not ``best_effort``: the step absorbs its own failure so the warning
        # can name chromadb rather than a step id (see ``step_index``).
        Step("index", _handler("step_index"), skip_if=_handler("skip_index")),
        Step("deliver_discord", _handler("step_deliver_discord"), skip_if=_handler("skip_discord")),
        Step("deliver_notion", _handler("step_deliver_notion"), skip_if=_handler("skip_notion")),
    ),
    guard=_handler("briefing_guard"),
)
