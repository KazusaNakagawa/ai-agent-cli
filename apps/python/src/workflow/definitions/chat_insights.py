"""chat.sh conversation archive and usage analysis, declared as workflows.

``chat-archive`` is free and runs inside ``daily``: it has to run while Claude
Code still holds the transcripts, which it prunes after 30 days by default.
``chat-insights`` adds the paid analysis and is run by hand (or weekly).

``src.chat_insights`` is imported at call time, like the other definitions
bind their handlers, so registry discovery stays cheap and tests can point the
module's directories at a fixture tree.
"""
from datetime import date
from typing import Any

from src.workflow.model import Step, StepContext, Workflow

ANALYZE_TIMEOUT_SEC = 600


def archive(ctx: StepContext) -> dict[str, Any]:
    from src import chat_insights

    result = chat_insights.archive_sessions(
        chat_insights.SESSIONS_DIR, chat_insights.TRANSCRIPTS_DIR, chat_insights.ARCHIVE_DIR
    )
    ctx.logger.info(
        "chat archive: %d session(s) archived, %d already pruned by Claude Code",
        len(result.archived),
        len(result.missing),
    )
    return {"archived": result.archived, "missing": result.missing}


def collect(ctx: StepContext) -> dict[str, Any]:
    from src import chat_insights

    turns = chat_insights.load_archive(
        chat_insights.ARCHIVE_DIR, chat_insights.window_start(date.today())
    )
    return {"turns": turns, "stats": chat_insights.compute_stats(turns)}


def skip_without_turns(ctx: StepContext) -> bool:
    return not ctx.results["collect"]["stats"]["user_turns"]


def analyze(ctx: StepContext) -> str:
    from src import chat_insights
    from src.claude_runner import run_claude

    collected = ctx.results["collect"]
    prompt = chat_insights.build_prompt(
        collected["turns"], collected["stats"], ctx.results["archive"]["missing"]
    )
    return run_claude(prompt, label="チャット傾向分析", timeout=ANALYZE_TIMEOUT_SEC)


def persist(ctx: StepContext) -> str:
    from src import chat_insights

    today = date.today().isoformat()
    chat_insights.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = chat_insights.REPORT_DIR / f"chat-insights_{today}.md"
    out.write_text(f"# チャット傾向レポート ({today})\n\n{ctx.results['analyze']}\n", encoding="utf-8")
    ctx.logger.info("chat insights written: %s", out)
    return str(out)


CHAT_ARCHIVE = Workflow(
    id="chat-archive",
    title="Archive chat.sh conversations before Claude Code prunes them",
    steps=(Step("archive", archive),),
)

CHAT_INSIGHTS = Workflow(
    id="chat-insights",
    title="Analyze recent chat.sh usage into a trend report",
    steps=(
        Step("archive", archive),
        Step("collect", collect),
        Step("analyze", analyze, skip_if=skip_without_turns),
        Step("persist", persist, skip_if=skip_without_turns),
    ),
)
