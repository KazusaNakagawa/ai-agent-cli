"""Project-wide utility functions shared across modules."""


def is_configured(*values: str) -> bool:
    """Return True if all credential values are non-empty strings."""
    return all(values)
