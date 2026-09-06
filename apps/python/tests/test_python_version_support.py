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

# The job whose matrix defines the supported range. Scoped by name so an
# unrelated job growing its own matrix later cannot be mistaken for this one.
MATRIX_JOB = "pytest"

# Only versions introduced by the word "Python" count, optionally as a range
# ("Python 3.11–3.13", "Python 3.11〜3.13"). A bare `3.x` elsewhere in the docs
# — a dependency version, an example — is none of this test's business.
PYTHON_VERSION_IN_PROSE = re.compile(r"Python\s+3\.\d+(?:\s*[–—〜~-]\s*3\.\d+)?")


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
    """The python-version matrix the `pytest` job actually runs."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert MATRIX_JOB in jobs, f"{WORKFLOW.name} has no `{MATRIX_JOB}` job"
    matrix = jobs[MATRIX_JOB]["strategy"]["matrix"]["python-version"]
    return [str(version) for version in matrix]


def documented_versions(text: str) -> set[str]:
    """Every Python version the prose names, ranges included."""
    return {
        version
        for phrase in PYTHON_VERSION_IN_PROSE.findall(text)
        for version in re.findall(r"3\.\d+", phrase)
    }


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
        mentioned = documented_versions(readme.read_text(encoding="utf-8"))
        assert mentioned != set(), f"{readme.name} states no Python version at all"
        unsupported = mentioned - set(supported_versions())
        assert unsupported == set(), f"{readme.name} names untested versions: {sorted(unsupported)}"

    @pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
    def test_readme_states_both_ends_of_the_range(self, readme: Path):
        """Boundary: the advertised range must reach the lowest and highest leg."""
        mentioned = documented_versions(readme.read_text(encoding="utf-8"))
        versions = supported_versions()
        for edge in (versions[0], versions[-1]):
            assert edge in mentioned, f"{readme.name} does not mention Python {edge}"

    def test_testing_guide_documents_the_supported_range(self):
        """Success: the guide states the range and how the matrix runs it."""
        text = TESTING_GUIDE.read_text(encoding="utf-8")
        versions = supported_versions()
        for edge in (versions[0], versions[-1]):
            assert edge in text, f"testing.md does not mention {edge}"
