from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parents[2] / "prompts"


def render(template_name: str, **kwargs: str) -> str:
    """prompts/{template_name}.md を読み込み、$name プレースホルダを埋め込んで返す。

    string.Template を使うことで、もし将来 ``render(user_input, ...)`` のように
    テンプレート側に外部入力が渡る経路が生まれても、``{0.__class__.__init__.__globals__}``
    のような attribute walk は構文として成立せず、Python レベルの情報漏洩を機構的に遮断する。
    """
    path = PROMPTS_DIR / f"{template_name}.md"
    template = Template(path.read_text(encoding="utf-8"))
    return template.substitute(**kwargs)
