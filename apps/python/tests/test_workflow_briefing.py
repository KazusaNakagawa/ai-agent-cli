"""The briefing workflow definition.

Behavior of the pipeline itself is covered by ``test_handlers.py``, which was
deliberately left unmodified by the migration. What is asserted here is the
shape of the definition and the properties the migration is supposed to buy:
the workflow is discoverable, its steps are ordered so the local copy survives
a delivery outage, and discovery stays independent of the briefing's own config.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from src.workflow import registry
from src.workflow.definitions.briefing import BRIEFING

PROJECT_ROOT = Path(__file__).parents[1]


def test_briefing_is_discoverable_by_id():
    assert registry.get("briefing") is BRIEFING


def test_step_order_puts_the_local_copy_before_every_delivery():
    ids = [s.id for s in BRIEFING.steps]

    assert ids == [
        "preflight",
        "fx",
        "stocks",
        "generate",
        "chart",
        "persist",
        "index",
        "deliver_discord",
        "deliver_notion",
    ]
    assert ids.index("persist") < ids.index("deliver_discord")
    assert ids.index("persist") < ids.index("deliver_notion")


def test_chart_is_rendered_before_the_delivery_that_carries_it():
    ids = [s.id for s in BRIEFING.steps]
    # After generate so a chart failure cannot waste the paid LLM call, and
    # before the Discord delivery that attaches the PNG.
    assert ids.index("generate") < ids.index("chart") < ids.index("deliver_discord")


def test_chart_is_best_effort():
    # The briefing body must ship with or without its illustration.
    assert next(s for s in BRIEFING.steps if s.id == "chart").best_effort is True


def test_preflight_is_the_only_preamble_step():
    # It is the credential check, so it runs before the guard and is the one
    # step a dry run executes.
    assert [s.id for s in BRIEFING.steps if s.preamble] == ["preflight"]


def test_deliveries_are_not_best_effort():
    # Today a Discord or Notion failure propagates, and the migration must not
    # quietly turn those into warnings.
    for step_id in ("deliver_discord", "deliver_notion", "persist", "generate"):
        step = next(s for s in BRIEFING.steps if s.id == step_id)
        assert step.best_effort is False


def test_chart_is_not_gated_on_any_delivery():
    """The dated PNG is the chart's primary destination, so it renders whether
    or not a delivery target happens to be configured. Gating it on Discord
    skipped it entirely on a Notion-only setup."""
    assert next(s for s in BRIEFING.steps if s.id == "chart").skip_if is None


@pytest.mark.parametrize("step_id", ["index", "deliver_discord", "deliver_notion"])
def test_conditional_steps_declare_a_skip_predicate(step_id):
    assert next(s for s in BRIEFING.steps if s.id == step_id).skip_if is not None


def test_discovery_does_not_import_the_briefing_handler():
    """Discovery must not depend on one workflow's runtime configuration.

    ``src.handler`` imports ``src.config``, whose ``CONFIG`` is read eagerly on
    first attribute access — so importing it during discovery would make
    ``workflow list`` fail on a machine with no ``config/briefing.json``, and
    would do it again for every workflow added later.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys;"
            "from src.workflow import registry;"
            "found = registry.discover();"
            "assert 'briefing' in found, found;"
            "print('src.handler' in sys.modules)",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(PROJECT_ROOT)},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
