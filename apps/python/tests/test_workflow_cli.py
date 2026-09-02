"""``python -m src.workflow`` — the single entry point for every workflow.

One CLI for all workflows is what keeps ``bin/`` from growing another script
each time a business process is added, so the surface is tested here directly.
"""
import pytest

from src.workflow import cli, registry
from src.workflow.model import InputSpec, Step, Workflow


@pytest.fixture
def registered(monkeypatch):
    """Replace registry discovery with an explicit set of workflows."""

    def _install(*workflows):
        found = {wf.id: wf for wf in workflows}
        monkeypatch.setattr(registry, "discover", lambda package=None: found)
        return found

    return _install


def _echo_workflow(calls):
    return Workflow(
        id="demo",
        title="Demo workflow",
        steps=(
            Step("preflight", lambda ctx: calls.append("preflight"), preamble=True),
            Step("work", lambda ctx: calls.append("work")),
        ),
    )


# --- list -------------------------------------------------------------------


def test_list_prints_every_registered_workflow(registered, capsys):
    registered(_echo_workflow([]), Workflow(id="other", title="Other", steps=(Step("a", lambda ctx: None),)))

    assert cli.main(["list"]) == 0

    out = capsys.readouterr().out
    assert "demo" in out and "Demo workflow" in out
    assert "other" in out


def test_list_names_declared_inputs(registered, capsys):
    registered(
        Workflow(
            id="incident",
            title="Incident",
            steps=(Step("a", lambda ctx: None),),
            inputs=(InputSpec("summary", required=True, help="what happened"),),
        )
    )

    cli.main(["list"])

    assert "--summary" in capsys.readouterr().out


def test_list_with_no_workflows_says_so(registered, capsys):
    registered()

    assert cli.main(["list"]) == 0
    assert "no workflows" in capsys.readouterr().out.lower()


# --- run --------------------------------------------------------------------


def test_run_executes_the_named_workflow(registered):
    calls = []
    registered(_echo_workflow(calls))

    assert cli.main(["run", "demo"]) == 0
    assert calls == ["preflight", "work"]


def test_run_dry_run_executes_only_preamble_steps(registered):
    calls = []
    registered(_echo_workflow(calls))

    assert cli.main(["run", "demo", "--dry-run"]) == 0
    assert calls == ["preflight"]


def test_run_force_bypasses_the_guard(registered):
    calls = []
    guarded = Workflow(
        id="guarded",
        title="Guarded",
        steps=(Step("a", lambda ctx: calls.append("a")),),
        guard=lambda ctx: "already ran today",
    )
    registered(guarded)

    assert cli.main(["run", "guarded"]) == 0
    assert calls == []

    assert cli.main(["run", "guarded", "--force"]) == 0
    assert calls == ["a"]


def test_run_passes_a_declared_input_through(registered, capsys):
    seen = {}
    registered(
        Workflow(
            id="incident",
            title="Incident",
            steps=(Step("a", lambda ctx: seen.update(ctx.inputs)),),
            inputs=(InputSpec("summary", required=True),),
        )
    )

    assert cli.main(["run", "incident", "--summary", "lambda error"]) == 0
    assert seen == {"summary": "lambda error"}


def test_run_reports_a_missing_required_input(registered, capsys):
    registered(
        Workflow(
            id="incident",
            title="Incident",
            steps=(Step("a", lambda ctx: None),),
            inputs=(InputSpec("summary", required=True),),
        )
    )

    assert cli.main(["run", "incident"]) == 1
    assert "summary" in capsys.readouterr().err


def test_run_rejects_an_undeclared_option(registered):
    registered(_echo_workflow([]))

    with pytest.raises(SystemExit):
        cli.main(["run", "demo", "--bogus", "x"])


def test_run_reports_an_unknown_workflow(registered, capsys):
    registered(_echo_workflow([]))

    assert cli.main(["run", "nope"]) == 1
    err = capsys.readouterr().err
    assert "nope" in err
    assert "demo" in err  # tells the user what is available


def test_run_reports_a_skipped_run_without_failing(registered, capsys):
    registered(
        Workflow(
            id="guarded",
            title="Guarded",
            steps=(Step("a", lambda ctx: None),),
            guard=lambda ctx: "already ran today",
        )
    )

    assert cli.main(["run", "guarded"]) == 0
    assert "already ran today" in capsys.readouterr().out


def test_run_returns_nonzero_when_a_step_fails(registered, capsys):
    def _boom(ctx):
        raise RuntimeError("step exploded")

    registered(Workflow(id="broken", title="Broken", steps=(Step("a", _boom),)))

    assert cli.main(["run", "broken"]) == 1
    assert "step exploded" in capsys.readouterr().err
