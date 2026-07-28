"""Tests for src.generator.prompt.render().

These tests anchor the Option 1 hardening for issue #101: replacing
str.format() with string.Template so that user / config values can never
reach a format-string position that supports attribute walks like
{0.__class__.__init__.__globals__}.
"""
import ast
from pathlib import Path

import pytest

from src.generator import prompt as prompt_mod
from src.generator.prompt import render


# ---------------------------------------------------------------------------
# Substitution mechanism — drives the str.format → string.Template switch.
# ---------------------------------------------------------------------------


class TestRenderDollarSyntax:
    def test_substitutes_dollar_name_placeholder(self, tmp_path, monkeypatch):
        (tmp_path / "tmpl.md").write_text("Hello $name", encoding="utf-8")
        monkeypatch.setattr(prompt_mod, "PROMPTS_DIR", tmp_path)
        assert render("tmpl", name="World") == "Hello World"

    def test_does_not_substitute_curly_brace_syntax(self, tmp_path, monkeypatch):
        """{name} must be inert — only $name is substituted under the new mechanism."""
        (tmp_path / "tmpl.md").write_text("Hello {name}", encoding="utf-8")
        monkeypatch.setattr(prompt_mod, "PROMPTS_DIR", tmp_path)
        assert render("tmpl", name="World") == "Hello {name}"


# ---------------------------------------------------------------------------
# Existing prompt templates must still render with their known kwargs.
# Acts as a snapshot guard against the {name} → $name migration.
# ---------------------------------------------------------------------------


class TestExistingTemplates:
    def test_briefing_renders_all_placeholders(self):
        out = render(
            "briefing",
            themes="THM",
            tickers="TKR",
            geopolitical="GEO",
            watch_events="EVT",
            stocks="STK",
            fx="FX",
            few_shot="FEWSHOT",
        )
        for marker in ("THM", "TKR", "GEO", "EVT", "STK", "FX", "FEWSHOT"):
            assert marker in out
        for placeholder in ("$themes", "$tickers", "$geopolitical", "$watch_events", "$stocks", "$fx", "$few_shot"):
            assert placeholder not in out

    def test_briefing_few_shot_value_dollar_is_not_reinterpreted(self):
        """few_shot 値内の $name は再置換されない（単一パス置換の回帰ガード）。

        load_briefing_few_shot() が値として渡すため、例の本文に $ が含まれても
        他のプレースホルダとして解釈されてはならない。
        """
        out = render(
            "briefing",
            themes="THM",
            tickers="TKR",
            geopolitical="GEO",
            watch_events="EVT",
            stocks="STK",
            fx="FX",
            few_shot="INSIDE $themes NOT REPLACED",
        )
        assert "INSIDE $themes NOT REPLACED" in out

    def test_briefing_sectors_renders_all_placeholders(self):
        out = render("briefing_sectors", watch_sectors="SECT", stocks="STK")
        assert "SECT" in out
        assert "STK" in out
        assert "$watch_sectors" not in out
        assert "$stocks" not in out

    def test_weekly_summary_renders_all_placeholders(self):
        out = render("weekly_summary", briefings="BRF", week_label="W22")
        assert "BRF" in out
        assert "W22" in out
        assert "$briefings" not in out
        assert "$week_label" not in out

    def test_xss_intel_renders_all_placeholders(self):
        out = render(
            "xss_intel",
            date="2026-06-01",
            frameworks="React",
            keywords="XSS",
            libraries="DOMPurify",
        )
        for marker in ("2026-06-01", "React", "XSS", "DOMPurify"):
            assert marker in out
        for placeholder in ("$date", "$frameworks", "$keywords", "$libraries"):
            assert placeholder not in out


# ---------------------------------------------------------------------------
# Value-side safety — kwarg values are inert text, never re-interpolated.
# ---------------------------------------------------------------------------


class TestRenderValueSafety:
    def test_value_with_format_string_attack_payload_is_literal(
        self, tmp_path, monkeypatch
    ):
        """A {0.__class__.__init__.__globals__}-style value must be emitted verbatim."""
        (tmp_path / "tmpl.md").write_text("X=$payload", encoding="utf-8")
        monkeypatch.setattr(prompt_mod, "PROMPTS_DIR", tmp_path)
        payload = "{0.__class__.__init__.__globals__}"
        out = render("tmpl", payload=payload)
        assert out == f"X={payload}"

    def test_value_with_dollar_syntax_is_not_re_substituted(self, tmp_path, monkeypatch):
        """A value containing '$other' must NOT be re-substituted from kwargs (single-pass)."""
        (tmp_path / "tmpl.md").write_text("A=$a B=$b", encoding="utf-8")
        monkeypatch.setattr(prompt_mod, "PROMPTS_DIR", tmp_path)
        out = render("tmpl", a="$b", b="SECRET")
        assert out == "A=$b B=SECRET"


# ---------------------------------------------------------------------------
# AST gate — every render() call in src/ must use a string-literal first arg.
# Prevents future render(user_input, ...) misuse from reaching the template
# position regardless of the underlying substitution mechanism.
# ---------------------------------------------------------------------------


class TestRenderCallSitesAreLiteral:
    def test_all_render_first_args_are_string_literals(self):
        src_dir = Path(__file__).resolve().parents[1] / "src"
        offenders: list[str] = []
        for path in src_dir.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                is_render_call = (
                    (isinstance(func, ast.Name) and func.id == "render")
                    or (isinstance(func, ast.Attribute) and func.attr == "render")
                )
                if not is_render_call or not node.args:
                    continue
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    offenders.append(f"{path.relative_to(src_dir.parent)}:{node.lineno}")
        assert not offenders, (
            "render() must be called with a string-literal template name; "
            f"non-literal first arg at: {offenders}"
        )
