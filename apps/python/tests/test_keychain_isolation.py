import subprocess
import sys

import keyring
import pytest
from keyring.backends import fail

from src import credentials


def test_pytest_never_uses_the_real_keychain():
    # A real backend would pop a macOS Keychain dialog and block the run (#548).
    assert isinstance(keyring.get_keyring(), fail.Keyring)


def test_child_processes_never_use_the_real_keychain():
    # Covers code paths that initialize keyring outside this process's
    # set_keyring() call, e.g. subprocesses spawned by tests.
    out = subprocess.run(
        [sys.executable, "-c", "import keyring; print(type(keyring.get_keyring()).__module__)"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "keyring.backends.fail"


@pytest.mark.usefixtures("clear_credential_env")
def test_unisolated_lookup_reads_nothing_from_keychain():
    assert credentials.get_credential("NOTION_API_KEY") is None
