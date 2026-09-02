"""Discovery of workflow definitions.

Registration is the act of putting a module under ``src/workflow/definitions/``
— there is no table to update alongside it. YAML definitions were rejected for
this project because they split one workflow across a declaration and its
implementation; a registration table would reintroduce exactly that split, so
the package contents are the registry.
"""
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from src.workflow.model import Workflow

DEFINITIONS_PACKAGE = "src.workflow.definitions"


def _definitions_package() -> ModuleType:
    return importlib.import_module(DEFINITIONS_PACKAGE)


def discover(package: ModuleType | None = None) -> dict[str, Workflow]:
    """Import every module in ``package`` and collect the workflows they define.

    A workflow re-exported by a second module (``from .alpha import ALPHA``) is
    the same object and is not a conflict; two *different* workflows claiming
    one id is, and fails loudly here rather than letting one shadow the other.
    """
    package = package or _definitions_package()
    found: dict[str, Workflow] = {}

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{module_name}")
        for value in vars(module).values():
            if not isinstance(value, Workflow):
                continue
            existing = found.get(value.id)
            if existing is not None and existing is not value:
                raise ValueError(
                    f"duplicate workflow id {value.id!r}: defined by two different workflows"
                )
            found[value.id] = value

    return found


def get(workflow_id: str, *, package: ModuleType | None = None) -> Workflow:
    """Return one registered workflow, or raise ``KeyError`` naming the alternatives."""
    found = discover(package)
    if workflow_id not in found:
        available = ", ".join(sorted(found)) or "none"
        raise KeyError(f"unknown workflow {workflow_id!r} (available: {available})")
    return found[workflow_id]
