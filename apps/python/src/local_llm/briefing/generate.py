"""Single-shot Ollama generation. Tool calling is retired (context is already injected by pre-fetch)."""

from __future__ import annotations

from typing import Any, Protocol

from src.logger import get_logger

logger = get_logger(__name__)


class _OllamaChatLike(Protocol):
    def chat(
        self, *, model: str, messages: list[dict], options: dict | None = None
    ) -> Any: ...


def _msg_field(msg: Any, key: str, default: Any = None) -> Any:
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


# For text with Japanese mixed in, 1 token ≈ 2-3 chars. Divide conservatively by 2
# to over-estimate, accepting false warnings over missed ones (#150).
_CHARS_PER_TOKEN_ESTIMATE = 2


def generate_local_briefing(
    prompt: str,
    *,
    ollama_client: _OllamaChatLike,
    model: str,
    system_prompt: str | None = None,
    options: dict | None = None,
) -> str:
    """Single-turn chat(). Tool calling is retired (context is already injected by pre-fetch).

    If `system_prompt` is given, a role=system message is stacked first. The
    qwen2.5 family follows system instructions strongly, so constraints like "write
    using only the given search results" go here.

    `options` are Ollama generation options (num_ctx / temperature, etc.). When
    unspecified, Ollama's default num_ctx (4096) silently truncates the tail of the
    prompt, so the production path (cli) always passes the cfg-derived value (#150).
    """
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    total_chars = sum(len(m["content"]) for m in messages)
    est_tokens = total_chars // _CHARS_PER_TOKEN_ESTIMATE
    num_ctx = (options or {}).get("num_ctx")
    if num_ctx and est_tokens > num_ctx:
        logger.warning(
            "[briefing] prompt est. %d tokens (%d chars) exceeds num_ctx=%d — "
            "the tail may be truncated",
            est_tokens,
            total_chars,
            num_ctx,
        )
    else:
        logger.info(
            "[briefing] prompt est. %d tokens (%d chars) / num_ctx=%s",
            est_tokens,
            total_chars,
            num_ctx if num_ctx else "(Ollama default)",
        )

    logger.info("[briefing] ollama.chat — single-shot generation (no tools)")
    resp = ollama_client.chat(model=model, messages=messages, options=options)
    msg = _msg_field(resp, "message")
    if msg is None:
        msg = resp
    content = _msg_field(msg, "content", "") or ""
    logger.info("[briefing] generation done (%d chars)", len(content))

    if content:
        print(content, flush=True)
    return content
