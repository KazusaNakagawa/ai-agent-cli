"""Data model for declarative workflows.

A workflow is a business process declared once as a ``Workflow`` instance in a
module under ``src/workflow/definitions/``. The runner (``src.workflow.runner``)
is the only thing that knows how to execute one, so adding a process means
adding a definition rather than another handler and shell script.

Structural invariants are enforced in ``__post_init__`` rather than by the
runner: a malformed definition then fails when the registry imports its module,
not on the morning that workflow first runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from logging import Logger
from typing import Any, Callable, Literal

StepStatus = Literal["done", "skipped", "failed"]
RunStatus = Literal["done", "skipped", "failed", "dry_run"]


@dataclass
class StepContext:
    """Everything a step is allowed to see.

    Steps communicate only through ``results`` keyed by the producing step's id.
    There is deliberately no shared mutable scratch space: a step that needs a
    value must name the step it came from, which keeps the dependency visible
    in the definition.
    """

    run_id: str
    workflow_id: str
    inputs: dict[str, Any]
    results: dict[str, Any]
    logger: Logger


@dataclass(frozen=True)
class Step:
    """One unit of work in a workflow.

    ``best_effort`` marks a step whose failure must not sink the run — the
    Chroma indexing in the briefing pipeline is the original example. Anything
    else that raises fails the run and propagates.

    ``dry_run_ok`` marks a step that is safe to execute during a dry run
    (credential preflight, validation). Every other step is skipped, so a dry
    run never delivers anything.

    There is intentionally no ``timeout`` field. Steps run in-process and a
    wall-clock limit could not actually interrupt arbitrary Python, so the field
    would look enforced without being enforced. LLM timeouts already belong to
    ``src.claude_runner.run_claude``.
    """

    id: str
    run: Callable[[StepContext], Any]
    best_effort: bool = False
    dry_run_ok: bool = False
    skip_if: Callable[[StepContext], bool] | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("step id must not be blank")


@dataclass(frozen=True)
class InputSpec:
    """A workflow-specific parameter.

    Runner-level switches (``force``, ``dry_run``) are not declared here — they
    apply to every workflow and are passed to ``run_workflow`` directly. What a
    workflow declares is only what is specific to it, which is what lets the CLI
    (and, later, a web form) collect inputs without knowing the workflow.
    """

    id: str
    required: bool = False
    default: Any = None
    help: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("input id must not be blank")
        if self.required and self.default is not None:
            raise ValueError(
                f"input {self.id!r}: required inputs must not carry a default — "
                "the default would satisfy the requirement and it could never fail"
            )


@dataclass(frozen=True)
class Workflow:
    """A named, ordered sequence of steps.

    ``guard`` returns a human-readable reason to skip the whole run, or ``None``
    to proceed. It is how idempotency lands in the model: the briefing's
    "already generated today" check is a guard, and ``force`` bypasses it.
    """

    id: str
    title: str
    steps: tuple[Step, ...]
    inputs: tuple[InputSpec, ...] = ()
    guard: Callable[[StepContext], str | None] | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("workflow id must not be blank")
        if not self.steps:
            raise ValueError(f"workflow {self.id!r} must declare at least one step")
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"workflow {self.id!r}: duplicate step id {step.id!r}")
            seen.add(step.id)


@dataclass
class StepRecord:
    """Outcome of one step within a run."""

    id: str
    status: StepStatus
    duration_ms: int = 0
    error: str | None = None
    skip_reason: str | None = None


@dataclass
class RunRecord:
    """Outcome of one workflow run.

    ``results`` is in-memory only — it can hold a whole briefing body, and the
    record is meant to stay small enough to keep forever. #455 persists every
    field except this one.
    """

    run_id: str
    workflow_id: str
    status: RunStatus
    started_at: str
    inputs: dict[str, Any] = field(default_factory=dict)
    steps: list[StepRecord] = field(default_factory=list)
    finished_at: str | None = None
    skip_reason: str | None = None
    results: dict[str, Any] = field(default_factory=dict)
