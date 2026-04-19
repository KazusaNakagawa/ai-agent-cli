"""XSS レポートテキストから Notion 数値プロパティ用のメトリクスを抽出する。"""
import re


def extract_xss_metrics(text: str) -> dict:
    """重要度別（High/Medium/Low）の件数を Notion extra_properties 形式で返す。

    レポート内の "High" / "Medium" / "Low" キーワード出現数をカウントする。

    Returns:
        {"HighCount": {"number": N}, "MediumCount": {"number": M}, "LowCount": {"number": L}}
    """
    def count(pattern: str) -> int:
        return len(re.findall(pattern, text, re.IGNORECASE))

    return {
        "HighCount": {"number": count(r"\bhigh\b")},
        "MediumCount": {"number": count(r"\bmedium\b")},
        "LowCount": {"number": count(r"\blow\b")},
    }
