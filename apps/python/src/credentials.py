"""OS Keychain wrapper + .env fallback.

Stores credentials in the OS keychain via `python-keyring`. On read, falls back
to the same-named environment variable when the keychain has no value or cannot
be read. The fallback is logged per key (never the value), reported by
``credential_sources()``, and refused when ``STRICT_ENV`` is set.
Writes always go to the keychain (.env is immutable).

Names outside the allowed set (`ALLOWED_KEYS`) raise ``ValueError``. This guards
both the ``/api/credentials`` input sanitization and against operational
mistakes that would store unknown keys.
"""
import logging
import os
from typing import Any, Literal

import keyring

from src import paths

# Keychain service names. A relocated install (``BRIEF_LENS_HOME``, i.e. npx)
# keeps its own items: macOS ties each item's ACL to the python binary that
# created it, so reading the clone's items from the npx venv would prompt for
# the login password once per item, on every request.
SERVICE = "ai-agent"
RELOCATED_SERVICE = "brief-lens"
ALLOWED_KEYS: tuple[str, ...] = (
    "DISCORD_TOKEN",
    "CHANNEL_ID",
    "NOTION_API_KEY",
    "NOTION_DATABASE_ID",
    "NOTION_DATABASE_ID_JOURNAL",
    "ANTHROPIC_API_KEY",
)

_backend: Any = keyring

# Opt-in: when truthy, a value that would come from the environment (e.g. a
# plaintext .env) raises instead. Tests and CI leave it unset.
STRICT_ENV = "BRIEF_LENS_STRICT_CREDENTIALS"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

Source = Literal["keychain", "env"] | None

logger = logging.getLogger(__name__)
# Keys whose environment fallback was already logged in this process.
_fallback_logged: set[str] = set()


class CredentialSourceError(RuntimeError):
    """Strict mode refused a credential that is not readable from the keychain."""


def _ensure_allowed(name: str) -> None:
    if name not in ALLOWED_KEYS:
        raise ValueError(f"Unknown credential key: {name}")


def service_name() -> str:
    """Keychain service for this install (see ``SERVICE`` / ``RELOCATED_SERVICE``)."""
    return RELOCATED_SERVICE if paths.DATA_HOME != paths.APP_ROOT else SERVICE


def strict_mode() -> bool:
    """True when ``STRICT_ENV`` forbids reading credentials from the environment."""
    return os.environ.get(STRICT_ENV, "").strip().lower() in _TRUTHY


def _resolve(name: str) -> tuple[str | None, Source, bool]:
    """Return ``(value, source, keychain_failed)`` without enforcing strict mode."""
    keychain_failed = False
    try:
        value = _backend.get_password(service_name(), name)
    except keyring.errors.KeyringError:
        # No backend, or a locked / denied Keychain (e.g. a cancelled macOS prompt).
        value = None
        keychain_failed = True
    if value:
        return value, "keychain", keychain_failed
    env_value = os.environ.get(name) or None
    if env_value:
        return env_value, "env", keychain_failed
    return None, None, keychain_failed


def get_credential(name: str) -> str | None:
    """Read ``name`` from the keychain, falling back to the environment.

    The fallback logs the key name once per process (never the value). In
    strict mode it raises ``CredentialSourceError`` instead, as does a keychain
    that cannot be read; a key set nowhere still returns ``None`` so optional
    credentials keep working.
    """
    _ensure_allowed(name)
    value, source, keychain_failed = _resolve(name)
    if source == "keychain":
        return value
    if strict_mode():
        if keychain_failed:
            raise CredentialSourceError(
                f"{name}: the OS keychain could not be read and {STRICT_ENV} "
                "forbids the environment fallback. Unlock the keychain and retry."
            )
        if source == "env":
            raise CredentialSourceError(
                f"{name} is not in the OS keychain and {STRICT_ENV} forbids reading it "
                "from the environment. Store it in the keychain (Settings → Credentials) "
                "and remove it from .env."
            )
    if source == "env" and name not in _fallback_logged:
        _fallback_logged.add(name)
        # The rule fires on the word "credential" in the message; the value is
        # never passed (pinned by test_env_fallback_logs_key_and_source_but_not_value).
        logger.warning(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure -- logs the key name only
            "credential %s read from the environment, not the OS keychain; "
            "store it in the keychain and remove it from .env",
            name,
        )
    return value


def set_credential(name: str, value: str) -> None:
    _ensure_allowed(name)
    _backend.set_password(service_name(), name, value)


def has_keychain_entry(name: str) -> bool:
    """True when the keychain holds ``name``; raises ``KeyringError`` if unreadable."""
    _ensure_allowed(name)
    return _backend.get_password(service_name(), name) is not None


def delete_credential(name: str) -> None:
    _ensure_allowed(name)
    _backend.delete_password(service_name(), name)


def credential_sources() -> dict[str, Source]:
    """Where each allow-listed key currently resolves from: keychain, env, or unset."""
    return {name: _resolve(name)[1] for name in ALLOWED_KEYS}


def list_credentials() -> dict[str, bool]:
    # Resolve without strict enforcement: listing must not raise, and the
    # sources endpoint is what tells the user a value comes from the environment.
    return {name: source is not None for name, source in credential_sources().items()}
