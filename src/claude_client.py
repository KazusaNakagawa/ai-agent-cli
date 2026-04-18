"""Anthropic Python SDK を使った Claude 呼び出しユーティリティ。

claude CLI の代わりに直接 API を呼ぶことで、launchd などの
非インタラクティブ環境でも確実に動作する。
"""
import os
import time
import anthropic
from src.logger import get_logger

logger = get_logger(__name__)

_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_WAIT = 60  # seconds
_MAX_TOKENS = 8192
_WEB_SEARCH_TOOL: anthropic.types.ToolParam = {
    "type": "web_search_20250305",  # type: ignore[typeddict-item]
    "name": "web_search",
}


def run_with_web_search(prompt: str, label: str, timeout: int = 300) -> str:
    """WebSearch を使って claude に問い合わせ、テキストを返す。

    Args:
        prompt: ユーザープロンプト
        label: ログ用のラベル
        timeout: タイムアウト秒数

    Returns:
        claude の応答テキスト

    Raises:
        RuntimeError: API エラーまたはクレデンシャル不足
    """
    logger.info("Anthropic API 呼び出し開始: %s (model=%s)", label, _MODEL)

    client = anthropic.Anthropic(timeout=float(timeout))
    messages: list[anthropic.types.MessageParam] = [
        {"role": "user", "content": prompt}
    ]
    result_texts: list[str] = []

    while True:
        response = None
        for attempt in range(1, _RATE_LIMIT_RETRIES + 1):
            try:
                response = client.beta.messages.create(
                    model=_MODEL,
                    max_tokens=_MAX_TOKENS,
                    tools=[_WEB_SEARCH_TOOL],  # type: ignore[list-item]
                    messages=messages,
                    betas=["web-search-2025-03-05"],
                )
                break
            except anthropic.RateLimitError as e:
                if attempt == _RATE_LIMIT_RETRIES:
                    raise RuntimeError(f"Anthropic レート制限（{_RATE_LIMIT_RETRIES}回リトライ後）: {e}") from e
                logger.warning("レート制限に当たりました。%d秒後にリトライ (%d/%d)", _RATE_LIMIT_WAIT, attempt, _RATE_LIMIT_RETRIES)
                time.sleep(_RATE_LIMIT_WAIT)
            except anthropic.AuthenticationError as e:
                raise RuntimeError(f"Anthropic 認証エラー: {e}") from e
            except anthropic.APIError as e:
                raise RuntimeError(f"Anthropic API エラー [{label}]: {e}") from e
        assert response is not None

        for block in response.content:
            if hasattr(block, "text"):
                result_texts.append(block.text)

        if response.stop_reason == "end_turn":
            break

        # web_search が呼ばれた場合はサーバー側で処理済みなので結果を空で返す
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            break

        messages.append({"role": "assistant", "content": response.content})  # type: ignore[arg-type]
        messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tu.id, "content": ""}
                for tu in tool_uses
            ],
        })

    text = "\n".join(result_texts).strip()
    logger.info("Anthropic API 完了: %s (%d文字)", label, len(text))
    return text
