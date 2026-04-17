"""マーケットブリーフィングを生成し Discord/Notion に配信するエントリーポイント。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.handler import lambda_handler

if __name__ == "__main__":
    lambda_handler()
