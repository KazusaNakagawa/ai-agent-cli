from pathlib import Path

PROMPTS_DIR = Path(__file__).parents[1] / "prompts"


def render(template_name: str, **kwargs: str) -> str:
    """prompts/{template_name}.md を読み込み、変数を埋め込んで返す"""
    path = PROMPTS_DIR / f"{template_name}.md"
    template = path.read_text(encoding="utf-8")
    return template.format(**kwargs)
