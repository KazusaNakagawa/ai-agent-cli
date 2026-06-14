"""XSS レポートテキストから Notion 数値プロパティ用のメトリクスを抽出する。"""
import re


def extract_xss_metrics(text: str) -> dict:
    """重要度別（High/Medium/Low）の件数を Notion extra_properties 形式で返す。

    プロンプト出力の構造化行 「深刻度: <level>」 のみをカウントし、
    散文中の high/low といった一般語による誤カウントを防ぐ。

    Returns:
        {"HighCount": {"number": N}, "MediumCount": {"number": M}, "LowCount": {"number": L}}
    """
    def count(level: str) -> int:
        return len(re.findall(rf"深刻度[:：]\s*{level}", text, re.IGNORECASE))

    return {
        "HighCount": {"number": count("High")},
        "MediumCount": {"number": count("Medium")},
        "LowCount": {"number": count("Low")},
    }
