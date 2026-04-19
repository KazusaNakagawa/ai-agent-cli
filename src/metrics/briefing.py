"""ブリーフィングテキストから Notion 数値プロパティ用のメトリクスを抽出する。"""
import re


def extract_briefing_metrics(text: str, tickers: list[str]) -> dict:
    """文字数・言及銘柄数を Notion extra_properties 形式で返す。

    ティッカーは単語境界（\b）で照合し、部分文字列の誤カウントを防ぐ。

    Returns:
        {"CharCount": {"number": N}, "TickerCount": {"number": M}}
    """
    char_count = len(text)
    ticker_count = sum(
        1 for t in tickers if re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE)
    )
    return {
        "CharCount": {"number": char_count},
        "TickerCount": {"number": ticker_count},
    }
