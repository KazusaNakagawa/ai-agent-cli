"""Guards the supported Python range against drift.

The range is declared once in `apps/python/pyproject.toml` and has to stay in
lockstep with three other places: the CI matrix that proves it, and the two
READMEs plus the testing guide that advertise it. Before #445 the README claimed
3.11+ while CI only ever ran 3.13, so the claim was untested prose. These tests
make that combination fail loudly instead.
"""

import re
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "apps" / "python" / "pyproject.toml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"
READMES = (REPO_ROOT / "README.md", REPO_ROOT / "README.ja.md")
TESTING_GUIDE = REPO_ROOT / "docs" / "guides" / "testing.md"


def declared_range() -> tuple[tuple[int, int], tuple[int, int]]:
    """Returns the inclusive lower and exclusive upper bound of requires-python."""
    metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    requires = metadata["project"]["requires-python"]
    lower = re.search(r">=\s*(\d+)\.(\d+)", requires)
    upper = re.search(r"<\s*(\d+)\.(\d+)", requires)
    assert lower is not None, f"requires-python has no lower bound: {requires}"
    assert upper is not None, f"requires-python has no upper bound: {requires}"
    return (
        (int(lower.group(1)), int(lower.group(2))),
        (int(upper.group(1)), int(upper.group(2))),
    )


def supported_versions() -> list[str]:
    """Every minor version the declared range covers, oldest first."""
    (major, low), (upper_major, high) = declared_range()
    assert major == upper_major, "range spanning major versions is not supported"
    return [f"{major}.{minor}" for minor in range(low, high)]


def matrix_versions() -> list[str]:
    """The python-version matrix the pytest workflow actually runs."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    matrices = [
        job["strategy"]["matrix"]["python-version"]
        for job in jobs.values()
        if "strategy" in job and "python-version" in job.get("strategy", {}).get("matrix", {})
    ]
    assert len(matrices) == 1, f"expected exactly one python-version matrix, found {len(matrices)}"
    return [str(version) for version in matrices[0]]


class TestDeclaredMetadata:
    def test_requires_python_is_declared_in_committed_metadata(self):
        """Success: the range lives in pyproject.toml, not only in prose."""
        assert PYPROJECT.is_file()
        metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        assert metadata["project"]["requires-python"].strip() != ""

    def test_the_running_interpreter_is_inside_the_declared_range(self):
        """Boundary: whichever leg of the matrix runs this, it must be supported."""
        assert f"{sys.version_info.major}.{sys.version_info.minor}" in supported_versions()


class TestCiMatrix:
    def test_matrix_covers_every_declared_version(self):
        """Success: nothing is declared that CI does not exercise."""
        assert matrix_versions() == supported_versions()

    def test_matrix_runs_no_version_outside_the_declared_range(self):
        """Failure: a version added to CI alone must not slip through."""
        assert set(matrix_versions()) <= set(supported_versions())


class TestDocumentation:
    @pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
    def test_readme_names_only_versions_ci_runs(self, readme: Path):
        """Failure: a stale `3.x` left in the docs fails the build."""
        mentioned = set(re.findall(r"3\.\d+", readme.read_text(encoding="utf-8")))
        unsupported = mentioned - set(supported_versions())
        assert unsupported == set(), f"{readme.name} names untested versions: {sorted(unsupported)}"

    @pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
    def test_readme_states_both_ends_of_the_range(self, readme: Path):
        """Boundary: the advertised range must reach the lowest and highest leg."""
        text = readme.read_text(encoding="utf-8")
        versions = supported_versions()
        for edge in (versions[0], versions[-1]):
            assert edge in text, f"{readme.name} does not mention {edge}"

    def test_testing_guide_documents_the_supported_range(self):
        """Success: the guide states the range and how the matrix runs it."""
        text = TESTING_GUIDE.read_text(encoding="utf-8")
        versions = supported_versions()
        for edge in (versions[0], versions[-1]):
            assert edge in text, f"testing.md does not mention {edge}"
