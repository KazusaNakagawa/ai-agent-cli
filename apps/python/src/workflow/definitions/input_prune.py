"""Delete raw inputs once processed: imported statements, unreferenced uploads (#605).

A thin wrapper over ``src.input_retention.prune`` so the daily run can call it.
Paths are read at call time, not import time, so tests (and a relocated
install) see the directories in effect when the step runs.
"""
from datetime import datetime

from src.workflow.model import Step, StepContext, Workflow


def prune(ctx: StepContext) -> list[str]:
    from src import input_retention, paths
    from src.constants import INPUT_RETENTION_DAYS
    from src.money.importer import import_log_path
    from src.money.models import STORE_PATH

    result = input_retention.prune(
        input_dir=paths.INPUT_DIR,
        output_dir=paths.OUTPUT_DIR,
        import_log=import_log_path(STORE_PATH),
        now=datetime.now(),
        retention_days=INPUT_RETENTION_DAYS,
        dry_run=False,
    )
    ctx.logger.info("input prune: %d file(s) deleted", len(result.deleted))
    return [str(p) for p in result.deleted]


INPUT_PRUNE = Workflow(
    id="input-prune",
    title="Delete imported statements and unreferenced uploads after the retention window",
    steps=(Step("prune", prune),),
)
