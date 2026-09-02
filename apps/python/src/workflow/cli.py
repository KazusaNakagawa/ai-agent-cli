"""Command-line entry point shared by every workflow.

One entry point is what stops ``bin/`` gaining another script per business
process. Workflow-specific options are built at parse time from the selected
workflow's ``InputSpec``s, so this module never learns any workflow's details.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Sequence

from src.workflow import registry
from src.workflow.model import Workflow
from src.workflow.runner import WorkflowInputError, run_workflow


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflow", description="Run a declared workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List registered workflows")

    run = sub.add_parser("run", help="Run one workflow")
    run.add_argument("workflow_id", help="Workflow id (see `list`)")
    run.add_argument("--force", action="store_true", help="Ignore the workflow's skip guard")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Run only the steps marked safe for a dry run; deliver nothing",
    )
    return parser


def _parse_workflow_inputs(wf: Workflow, argv: Sequence[str]) -> dict[str, Any]:
    """Parse the leftover argv against the workflow's declared inputs.

    Undeclared options exit here rather than being ignored — silently dropping
    a mistyped option is how a run ends up doing the wrong thing quietly.
    """
    parser = argparse.ArgumentParser(prog=f"workflow run {wf.id}", add_help=False)
    for spec in wf.inputs:
        parser.add_argument(f"--{spec.id}", dest=spec.id, help=spec.help or None)
    parsed = vars(parser.parse_args(list(argv)))
    return {key: value for key, value in parsed.items() if value is not None}


def _cmd_list() -> int:
    found = registry.discover()
    if not found:
        print("no workflows registered")
        return 0
    for workflow_id in sorted(found):
        wf = found[workflow_id]
        options = " ".join(f"--{spec.id}" for spec in wf.inputs)
        print(f"{workflow_id:<20} {wf.title}" + (f"  [{options}]" if options else ""))
    return 0


def _cmd_run(args: argparse.Namespace, extra: Sequence[str]) -> int:
    try:
        wf = registry.get(args.workflow_id)
    except KeyError as exc:
        print(str(exc).strip("\"'"), file=sys.stderr)
        return 1

    inputs = _parse_workflow_inputs(wf, extra)

    try:
        record = run_workflow(wf, inputs, force=args.force, dry_run=args.dry_run)
    except WorkflowInputError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI boundary: report, don't traceback
        print(f"workflow {wf.id} failed: {exc}", file=sys.stderr)
        return 1

    if record.status == "skipped":
        print(f"{wf.id}: skipped — {record.skip_reason}")
    else:
        print(f"{wf.id}: {record.status} (run_id={record.run_id})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args, extra = _build_parser().parse_known_args(argv)
    if args.command == "list":
        return _cmd_list()
    return _cmd_run(args, extra)


if __name__ == "__main__":
    raise SystemExit(main())
