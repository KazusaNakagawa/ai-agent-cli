"""XSS 脆弱性インテリジェンスレポートを生成し Discord/Notion に配信するエントリーポイント。"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.xss_handler import lambda_handler

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XSS Intel agent")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate credentials and config without running the pipeline",
    )
    args = parser.parse_args()
    lambda_handler(dry_run=args.dry_run)
