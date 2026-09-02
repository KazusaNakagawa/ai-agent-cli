"""Keeps ``python -m src.workflow`` working, matching src.money / src.portfolio_snapshot."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
