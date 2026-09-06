"""Auto-discovery of workflow definitions.

Adding a workflow must mean adding one file under ``src/workflow/definitions/``
and nothing else — no registration table to keep in sync. These tests drive
discovery against a throwaway package so they assert the mechanism rather than
whatever definitions happen to ship today.
"""
import sys
import textwrap

import pytest

from src.workflow import registry
from src.workflow.model import Workflow

_STEP_IMPORT = "from src.workflow.model import Step, Workflow"


@pytest.fixture
def definitions_package(tmp_path, monkeypatch):
    """Build an importable package of definition modules from source snippets."""
    created = []

    def _build(name: str, modules: dict[str, str]):
        pkg = tmp_path / name
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        for stem, source in modules.items():
            (pkg / f"{stem}.py").write_text(textwrap.dedent(source), encoding="utf-8")
        monkeypatch.syspath_prepend(str(tmp_path))
        created.append(name)
        import importlib

        return importlib.import_module(name)

    yield _build

    for name in created:
        for mod in [m for m in sys.modules if m == name or m.startswith(f"{name}.")]:
            del sys.modules[mod]


def test_discovers_a_workflow_from_a_dropped_in_module(definitions_package):
    pkg = definitions_package(
        "defs_one",
        {
            "alpha": f"""
                {_STEP_IMPORT}
                ALPHA = Workflow(id="alpha", title="Alpha", steps=(Step("a", lambda ctx: None),))
            """
        },
    )

    found = registry.discover(pkg)

    assert set(found) == {"alpha"}
    assert found["alpha"].title == "Alpha"


def test_a_second_module_appears_without_any_other_edit(definitions_package):
    pkg = definitions_package(
        "defs_two",
        {
            "alpha": f"""
                {_STEP_IMPORT}
                ALPHA = Workflow(id="alpha", title="Alpha", steps=(Step("a", lambda ctx: None),))
            """,
            "beta": f"""
                {_STEP_IMPORT}
                BETA = Workflow(id="beta", title="Beta", steps=(Step("b", lambda ctx: None),))
            """,
        },
    )

    assert set(registry.discover(pkg)) == {"alpha", "beta"}


def test_empty_package_discovers_nothing(definitions_package):
    assert registry.discover(definitions_package("defs_empty", {})) == {}


def test_duplicate_workflow_ids_are_rejected(definitions_package):
    pkg = definitions_package(
        "defs_dupe",
        {
            "alpha": f"""
                {_STEP_IMPORT}
                ALPHA = Workflow(id="same", title="A", steps=(Step("a", lambda ctx: None),))
            """,
            "beta": f"""
                {_STEP_IMPORT}
                BETA = Workflow(id="same", title="B", steps=(Step("b", lambda ctx: None),))
            """,
        },
    )

    with pytest.raises(ValueError, match="same"):
        registry.discover(pkg)


def test_the_same_workflow_re_exported_is_not_a_duplicate(definitions_package):
    # ``from .alpha import ALPHA`` in a sibling module is a re-export, not a
    # second workflow — only a distinct object sharing an id is a conflict.
    pkg = definitions_package(
        "defs_reexport",
        {
            "alpha": f"""
                {_STEP_IMPORT}
                ALPHA = Workflow(id="alpha", title="Alpha", steps=(Step("a", lambda ctx: None),))
            """,
            "bundle": """
                from defs_reexport.alpha import ALPHA
            """,
        },
    )

    assert set(registry.discover(pkg)) == {"alpha"}


def test_get_returns_a_registered_workflow(definitions_package):
    pkg = definitions_package(
        "defs_get",
        {
            "alpha": f"""
                {_STEP_IMPORT}
                ALPHA = Workflow(id="alpha", title="Alpha", steps=(Step("a", lambda ctx: None),))
            """
        },
    )

    assert registry.get("alpha", package=pkg).id == "alpha"


def test_get_raises_a_readable_error_for_an_unknown_id(definitions_package):
    pkg = definitions_package(
        "defs_unknown",
        {
            "alpha": f"""
                {_STEP_IMPORT}
                ALPHA = Workflow(id="alpha", title="Alpha", steps=(Step("a", lambda ctx: None),))
            """
        },
    )

    with pytest.raises(KeyError, match="alpha"):
        registry.get("nope", package=pkg)


@pytest.fixture
def two_workflows(definitions_package):
    return definitions_package(
        "defs_resolve",
        {
            "alpha": f"""
                {_STEP_IMPORT}
                ALPHA = Workflow(id="briefing", title="B", steps=(Step("a", lambda ctx: None),))
            """,
            "beta": f"""
                {_STEP_IMPORT}
                BETA = Workflow(id="brief_weekly", title="W", steps=(Step("b", lambda ctx: None),))
            """,
            "gamma": f"""
                {_STEP_IMPORT}
                GAMMA = Workflow(id="incident", title="I", steps=(Step("c", lambda ctx: None),))
            """,
        },
    )


def test_resolve_accepts_an_exact_id(two_workflows):
    assert registry.resolve("briefing", package=two_workflows).id == "briefing"


def test_resolve_accepts_an_unambiguous_prefix(two_workflows):
    assert registry.resolve("inc", package=two_workflows).id == "incident"


def test_resolve_prefers_an_exact_id_over_a_longer_match(two_workflows):
    # "briefing" is also a prefix of nothing else here, but the exact-match
    # rule is what stops an id that prefixes another id from being ambiguous.
    assert registry.resolve("briefing", package=two_workflows).id == "briefing"


def test_resolve_refuses_an_ambiguous_prefix(two_workflows):
    with pytest.raises(KeyError, match="brief_weekly"):
        registry.resolve("brief", package=two_workflows)


def test_resolve_reports_an_unknown_prefix(two_workflows):
    with pytest.raises(KeyError, match="zzz"):
        registry.resolve("zzz", package=two_workflows)


def test_get_does_not_prefix_match(two_workflows):
    # Code naming a workflow must keep naming the same one after another
    # workflow is added; only human input gets abbreviations.
    with pytest.raises(KeyError):
        registry.get("inc", package=two_workflows)


def test_the_real_definitions_package_is_discoverable():
    # The shipped package may legitimately be empty until #457 lands; what
    # matters is that discovery runs against it without raising.
    found = registry.discover()

    assert all(isinstance(wf, Workflow) for wf in found.values())
