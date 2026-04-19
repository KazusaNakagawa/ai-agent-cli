"""ブリーフィングテキストから Notion 数値プロパティ用のメトリクスを抽出する。"""
import re


def extract_briefing_metrics(text: str, tickers: list[str]) -> dict:
    """文字数・言及銘柄数を Notion extra_properties 形式で返す。

    ティッカーは ASCII 英数字・アンダースコアの lookaround で照合する。
    \b では日本語助詞に直接隣接するケース（例: "PLTRは上昇"）を検出できないため、
    (?<![A-Za-z0-9_])TICKER(?![A-Za-z0-9_]) を使用する。

    Returns:
        {"CharCount": {"number": N}, "TickerCount": {"number": M}}
    """
    char_count = len(text)
    ticker_count = sum(
        1 for t in tickers
        if re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])",
            text,
            re.IGNORECASE,
        )
    )
    return {
        "CharCount": {"number": char_count},
        "TickerCount": {"number": ticker_count},
    }
