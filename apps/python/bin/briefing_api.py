"""Claude API briefing cost-verification spike entrypoint (#204)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.generator.briefing_api import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
