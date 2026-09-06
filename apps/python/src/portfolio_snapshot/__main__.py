"""Keeps ``python -m src.portfolio_snapshot`` working after the package split."""
from .cli import main

if __name__ == "__main__":
    main()
