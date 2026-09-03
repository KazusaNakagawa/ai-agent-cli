"""The single executor for every workflow.

``run_workflow`` owns step ordering, skipping, failure policy and the run
record. It deliberately owns nothing else: LLM invocation and its retries stay
in ``src.claude_runner``, and knowledge of any delivery target stays inside the
step that delivers.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from src.logger import get_logger
from src.workflow.model import RunRecord, Step, StepContext, StepRecord, Workflow

logger = get_logger(__name__)


class WorkflowInputError(ValueError):
    """Raised when supplied inputs do not match a workflow's ``InputSpec``s."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    """Readable-but-unique id: sorts chronologically, safe as a filename (#455)."""
    return f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def resolve_inputs(wf: Workflow, supplied: dict[str, Any] | None) -> dict[str, Any]:
    """Validate ``supplied`` against the workflow's declared inputs.

    Unknown keys are an error rather than being ignored: a mistyped option at
    the CLI would otherwise reach the step as a missing value, and the step
    would fail somewhere much further from the cause.
    """
    supplied = dict(supplied or {})
    declared = {spec.id: spec for spec in wf.inputs}

    unknown = sorted(set(supplied) - set(declared))
    if unknown:
        known = ", ".join(sorted(declared)) or "none"
        raise WorkflowInputError(
            f"workflow {wf.id!r}: unknown input(s) {', '.join(unknown)} (declared: {known})"
        )

    resolved: dict[str, Any] = {}
    missing = []
    for spec in wf.inputs:
        if spec.id in supplied:
            resolved[spec.id] = supplied[spec.id]
        elif spec.required:
            missing.append(spec.id)
        else:
            resolved[spec.id] = spec.default
    if missing:
        raise WorkflowInputError(
            f"workflow {wf.id!r}: missing required input(s) {', '.join(missing)}"
        )
    return resolved


def _run_steps(
    steps: tuple[Step, ...],
    ctx: StepContext,
    record: RunRecord,
    *,
    workflow_id: str,
    skip_all: bool = False,
) -> None:
    """Execute ``steps`` in order, recording each outcome onto ``record``.

    ``skip_all`` records every step as skipped without running it — how a dry
    run disposes of the steps that are not part of the preamble.
    """
    for step in steps:
        if skip_all:
            record.steps.append(StepRecord(step.id, "skipped", skip_reason="dry run"))
            continue
        if step.skip_if is not None and step.skip_if(ctx):
            record.steps.append(StepRecord(step.id, "skipped", skip_reason="skip_if"))
            logger.debug("step skipped: %s.%s (skip_if)", workflow_id, step.id)
            continue

        started = time.monotonic()
        try:
            result = step.run(ctx)
        except Exception as exc:  # noqa: BLE001 — policy decision, re-raised below
            elapsed = int((time.monotonic() - started) * 1000)
            record.steps.append(StepRecord(step.id, "failed", elapsed, error=str(exc)))
            if step.best_effort:
                logger.warning(
                    "step failed (best effort, continuing): %s.%s: %s", workflow_id, step.id, exc
                )
                continue
            record.status = "failed"
            record.finished_at = _now_iso()
            logger.error("workflow failed: %s at step %s", workflow_id, step.id)
            exc.workflow_run_record = record
            raise

        elapsed = int((time.monotonic() - started) * 1000)
        record.results[step.id] = result
        record.steps.append(StepRecord(step.id, "done", elapsed))
        logger.debug("step done: %s.%s (%dms)", workflow_id, step.id, elapsed)


def run_workflow(
    wf: Workflow,
    inputs: dict[str, Any] | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> RunRecord:
    """Execute a workflow and return its record.

    Execution order is: every ``preamble`` step, then ``wf.guard``, then the
    rest. Preamble steps are side-effect-free, so running them ahead of the
    guard means a run that turns out to have nothing to do still validates its
    configuration.

    ``force`` bypasses ``wf.guard``. ``dry_run`` runs the preamble and skips
    every other step, so credentials and config can be validated without
    delivering anything; it bypasses the guard for the same reason ``force``
    does — there is no real work for the guard to protect.

    A step that raises and is not ``best_effort`` propagates its original
    exception — callers such as ``src.handler`` depend on the exception type
    and message surviving. The run record is attached to that exception as
    ``workflow_run_record`` so the failed run still leaves a trace.
    """
    resolved = resolve_inputs(wf, inputs)

    record = RunRecord(
        run_id=_new_run_id(),
        workflow_id=wf.id,
        status="done",
        started_at=_now_iso(),
        inputs=resolved,
    )
    ctx = StepContext(
        run_id=record.run_id,
        workflow_id=wf.id,
        inputs=resolved,
        results=record.results,
        logger=logger,
    )

    logger.info("workflow start: %s (run_id=%s, dry_run=%s)", wf.id, record.run_id, dry_run)

    preamble = tuple(step for step in wf.steps if step.preamble)
    main = tuple(step for step in wf.steps if not step.preamble)

    _run_steps(preamble, ctx, record, workflow_id=wf.id)

    # A dry run does no real work, so the guard — which exists to stop real
    # work from being repeated — has nothing to protect against. Consulting it
    # would make `--dry-run` answer "skipped" on any day the workflow already
    # ran, which is not what someone validating their config is asking.
    if wf.guard is not None and not force and not dry_run:
        reason = wf.guard(ctx)
        if reason:
            record.status = "skipped"
            record.skip_reason = reason
            record.finished_at = _now_iso()
            logger.info("workflow skipped: %s — %s", wf.id, reason)
            return record

    _run_steps(main, ctx, record, workflow_id=wf.id, skip_all=dry_run)

    record.status = "dry_run" if dry_run else "done"
    record.finished_at = _now_iso()
    logger.info("workflow %s: %s (run_id=%s)", record.status, wf.id, record.run_id)
    return record
