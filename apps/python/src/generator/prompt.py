from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parents[2] / "prompts"


def render(template_name: str, **kwargs: str) -> str:
    """Load prompts/{template_name}.md, fill in $name placeholders, and return it.

    Using string.Template means that even if a future path passes external input
    into the template (e.g. ``render(user_input, ...)``), an attribute walk like
    ``{0.__class__.__init__.__globals__}`` is not valid syntax, structurally
    blocking Python-level information leakage.
    """
    path = PROMPTS_DIR / f"{template_name}.md"
    template = Template(path.read_text(encoding="utf-8"))
    return template.substitute(**kwargs)
