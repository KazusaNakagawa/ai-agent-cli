"""The daily model-rate check, declared as a workflow (#475).

Runs last in the ``daily`` workflow so a model missing from ``src/model_rates.json``
fails the next morning's run instead of reporting $0 in the Monitor tab for
weeks. Drift between the table and Claude Code's own cost records only warns:
it can be a mid-flight price change that needs a human to read the pricing
doc, not a broken run. ``python -m src.rate_check`` treats both as failures.

``src.rate_check`` is imported at call time, like the other definitions bind
their handlers, so registry discovery stays cheap and tests can point the
module's ``DEFAULT_TRANSCRIPTS`` at a fixture tree.
"""
from typing import Any

from src.workflow.model import Step, StepContext, Workflow


class UnpricedModelError(RuntimeError):
    """A model in the transcripts has no entry in the rate table."""


def check_rates(ctx: StepContext) -> dict[str, Any]:
    from src import claude_rates, rate_check

    if not rate_check.DEFAULT_TRANSCRIPTS.is_dir():
        # Not a failure (a fresh machine has nothing to check), but a wrong
        # root would otherwise pass silently every morning.
        ctx.logger.warning(
            "no transcripts found at %s — model rates not checked", rate_check.DEFAULT_TRANSCRIPTS
        )
    unpriced, drift, reconciled = rate_check.check(
        rate_check.DEFAULT_TRANSCRIPTS,
        claude_rates.RATES,
        claude_rates.load_tiered(claude_rates.RATES_PATH),
    )
    for line in drift:
        ctx.logger.warning("model rate drift — %s", line)
    if unpriced:
        # Only looked up on failure, so a passing morning never touches the
        # network. The lookup is advisory and cannot raise. Logged one line per
        # entry so the exception (and the run record's error) stays one line.
        for line in rate_check.suggest_from_upstream(unpriced):
            ctx.logger.warning("suggested model_rates.json entry — %s", line)
        raise UnpricedModelError(
            f"no rate in {claude_rates.RATES_PATH.name} for: {', '.join(unpriced)} "
            "— add the published rates (suggested entries logged above), "
            "then re-run scripts/check_model_rates.py"
        )
    return {"reconciled": reconciled, "drift": len(drift)}


MODEL_RATES = Workflow(
    id="model-rates",
    title="Model rate table check",
    steps=(Step("check", check_rates),),
)
