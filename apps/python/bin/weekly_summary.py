"""週次ブリーフィング振り返りを生成し Notion に投稿するエントリーポイント。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.weekly_handler import weekly_handler

if __name__ == "__main__":
    weekly_handler()
