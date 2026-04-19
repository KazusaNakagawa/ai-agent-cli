"""ブリーフィングテキストから Notion 数値プロパティ用のメトリクスを抽出する。"""


def extract_briefing_metrics(text: str, tickers: list[str]) -> dict:
    """文字数・言及銘柄数を Notion extra_properties 形式で返す。

    Returns:
        {"CharCount": {"number": N}, "TickerCount": {"number": M}}
    """
    char_count = len(text)
    ticker_count = sum(1 for t in tickers if t.upper() in text.upper())
    return {
        "CharCount": {"number": char_count},
        "TickerCount": {"number": ticker_count},
    }
