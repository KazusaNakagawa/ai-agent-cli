"""The daily model-rate check, declared as a workflow (#475).

Runs last in ``bin/run.sh`` so a model missing from ``src/model_rates.json``
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

    unpriced, drift, reconciled = rate_check.check(
        rate_check.DEFAULT_TRANSCRIPTS, claude_rates.RATES
    )
    for line in drift:
        ctx.logger.warning("model rate drift — %s", line)
    if unpriced:
        raise UnpricedModelError(
            f"no rate in {claude_rates.RATES_PATH.name} for: {', '.join(unpriced)} "
            "— add the published rates, then re-run scripts/check_model_rates.py"
        )
    return {"reconciled": reconciled, "drift": len(drift)}


MODEL_RATES = Workflow(
    id="model-rates",
    title="Model rate table check",
    steps=(Step("check", check_rates),),
)
