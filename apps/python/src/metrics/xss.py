"""Extract metrics for Notion number properties from the XSS report text."""
import re


def extract_xss_metrics(text: str) -> dict:
    """Return counts by severity (High/Medium/Low) in Notion extra_properties form.

    Only counts the structured ``深刻度: <level>`` lines from the prompt output,
    preventing miscounts from generic words like "high"/"low" in prose.

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
