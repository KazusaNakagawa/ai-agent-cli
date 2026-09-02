"""Command-line entry point shared by every workflow.

One entry point is what stops ``bin/`` gaining another script per business
process. A workflow's own options are built from its ``InputSpec``s once the
workflow is known, so this module never learns any workflow's details — and
``run <id> --help`` can still show them.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Sequence

from src.workflow import registry
from src.workflow.model import Workflow
from src.workflow.runner import WorkflowInputError, run_workflow


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workflow",
        description="Run a declared workflow. With no arguments, lists what is available.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List registered workflows")

    # Declared so `workflow --help` lists it, but never routed through: `run`
    # is dispatched in main() before argparse, because which options are valid
    # depends on the workflow and this parser cannot know them yet.
    sub.add_parser("run", help="Run one workflow: workflow run <workflow_id> [options]")
    return parser


def _run_usage() -> None:
    print("usage: workflow run <workflow_id> [options]")
    print()
    print("Options go after the workflow id — which options exist depends on the")
    print("workflow. See them with: workflow run <workflow_id> --help")
    print()
    _cmd_list(hint=False)


def _workflow_parser(wf: Workflow) -> argparse.ArgumentParser:
    """Build the option parser for one workflow: runner switches + declared inputs."""
    parser = argparse.ArgumentParser(
        prog=f"workflow run {wf.id}",
        description=wf.title,
    )
    parser.add_argument("--force", action="store_true", help="Ignore the workflow's skip guard")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run only the side-effect-free preamble steps; deliver nothing",
    )
    for spec in wf.inputs:
        # Required-ness and defaults are deliberately not declared here: the
        # runner's resolve_inputs owns both, so the CLI and a future web form
        # report the same thing for the same workflow.
        suffix = " (required)" if spec.required else ""
        parser.add_argument(f"--{spec.id}", dest=spec.id, help=(spec.help or "") + suffix or None)
    return parser


def _available() -> str:
    return ", ".join(sorted(registry.discover())) or "none"


def _cmd_list(*, hint: bool = True) -> int:
    """Print the registered workflows.

    The header names the first column ``WORKFLOW_ID`` on purpose: without it
    the column reads as a display name, and nothing connects it to the
    ``<workflow_id>`` the usage strings ask for.
    """
    found = registry.discover()
    if not found:
        print("no workflows registered")
        print(f"add one as a module under {registry.DEFINITIONS_PACKAGE.replace('.', '/')}/")
        return 0

    print(f"{'WORKFLOW_ID':<20} TITLE")
    for workflow_id in sorted(found):
        wf = found[workflow_id]
        options = " ".join(f"--{spec.id}" for spec in wf.inputs)
        print(f"{workflow_id:<20} {wf.title}" + (f"  [{options}]" if options else ""))
    if hint:
        # A real id, not "<workflow_id>": with the placeholder, the nearest
        # thing on screen that looks like a value is the TITLE column header.
        print(f"\nrun one with: workflow run {sorted(found)[0]}")
    return 0


def _cmd_run(workflow_id: str | None, options: Sequence[str]) -> int:
    if workflow_id is None:
        print("workflow run needs a workflow id", file=sys.stderr)
        print(f"available: {_available()}", file=sys.stderr)
        return 1

    if workflow_id.startswith("-"):
        print(
            f"options go after the workflow id: workflow run <workflow_id> {workflow_id} ...",
            file=sys.stderr,
        )
        print(f"available: {_available()}", file=sys.stderr)
        return 1

    try:
        wf = registry.get(workflow_id)
    except KeyError as exc:
        print(str(exc).strip("\"'"), file=sys.stderr)
        return 1

    opts = vars(_workflow_parser(wf).parse_args(list(options)))
    force = opts.pop("force")
    dry_run = opts.pop("dry_run")
    inputs = {key: value for key, value in opts.items() if value is not None}

    try:
        record = run_workflow(wf, inputs, force=force, dry_run=dry_run)
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
    argv = list(sys.argv[1:] if argv is None else argv)
    # Bare `workflow` answers the question someone running it is actually
    # asking — what can I run? — instead of an argparse usage error.
    if not argv:
        return _cmd_list()

    if argv[0] == "run":
        rest = argv[1:]
        if rest and rest[0] in ("-h", "--help"):
            _run_usage()
            return 0
        return _cmd_run(rest[0] if rest else None, rest[1:])

    _build_parser().parse_args(argv)  # only `list` reaches here; else it exits
    return _cmd_list()


if __name__ == "__main__":
    raise SystemExit(main())
