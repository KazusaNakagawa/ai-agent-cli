import json
import os
import shutil
import subprocess
import time

from src import config as config_mod
from src import credentials as cred_mod
from src import state as state_mod
from src.constants import (
    DEFAULT_MODEL,
    RETRY_BACKOFF_FACTOR,
    RETRY_BASE_DELAY,
    RETRY_MAX_ATTEMPTS,
)
from src.logger import get_logger
from src.transient_errors import is_transient
from src.usage_logger import log_usage

logger = get_logger(__name__)


def _parse_and_log_usage(stdout: str, label: str) -> str:
    """``--output-format json`` の stdout を解析し使用量を記録、テキスト結果を返す。

    JSON でない / ``result`` フィールドが無い場合は警告を出して raw stdout を
    そのまま返す（使用量ログはスキップ）— 使用量計測のために本処理を壊さない。
    """
    try:
        parsed = json.loads(stdout)
        result_text = parsed["result"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning(
            "claude CLI 出力を JSON として解析できませんでした、使用量ログをスキップ [%s]", label,
        )
        return stdout.strip()

    usage = parsed.get("usage")
    if isinstance(usage, dict):
        log_usage(
            label=label,
            usage=usage,
            cost_usd=parsed.get("total_cost_usd"),
            duration_ms=parsed.get("duration_ms"),
        )
    else:
        # usage を出さない呼び出しは正常運用でもありうるため debug に留める（ノイズ回避）
        logger.debug("claude CLI 出力に usage が無いため使用量ログをスキップ [%s]", label)

    return result_text.strip() if isinstance(result_text, str) else str(result_text)


def _config_model() -> str | None:
    """briefing.json の ``model`` フィールドを返す。読めなければ None。

    briefing.json が無い / 壊れている場合でもモデル解決を止めないため、
    例外は握りつぶして None を返す（呼び出し側で DEFAULT_MODEL にフォールバック）。
    """
    try:
        model = config_mod.CONFIG.model
    except FileNotFoundError:
        # briefing.json 未作成（例: web 起動直後）は想定内なので静かに無視。
        return None
    except Exception:  # noqa: BLE001 — 予期しない config エラーでもモデル解決は止めない
        logger.warning("config からのモデル取得に失敗、DEFAULT_MODEL を使用", exc_info=True)
        return None
    return model.strip() if model and model.strip() else None


def get_model() -> str:
    """claude CLI に渡すモデル ID を解決する。

    優先順位: ``CLAUDE_MODEL`` env > briefing.json の ``model`` > ``DEFAULT_MODEL``。
    env はアドホックな上書き用に最優先のまま。
    """
    env_model = os.environ.get("CLAUDE_MODEL", "").strip()
    if env_model:
        return env_model
    return _config_model() or DEFAULT_MODEL


def _backoff_delay(attempt: int) -> float:
    """attempt 番目 (1-indexed) のリトライ前に待機する秒数を返す。"""
    return RETRY_BASE_DELAY * (RETRY_BACKOFF_FACTOR ** (attempt - 1))


def build_env(auth_mode: str) -> dict[str, str]:
    """auth_mode に応じてサブプロセスに渡す env を作る。

    - ``cli``: ``ANTHROPIC_API_KEY`` を削除して Claude Code CLI の OAuth を使わせる。
    - ``api``: Keychain (なければ .env 経由の os.environ) から
      ``ANTHROPIC_API_KEY`` を取り出して env に注入する。Keychain にも env にも
      無ければキーは未設定のまま — 呼び出し側で claude CLI が認証エラーになる。

    Public API — also imported by ``web.routers.chat``. (The earlier underscore
    prefix was a stale "internal" signal that didn't reflect actual usage.)
    """
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    if auth_mode == "api":
        key = cred_mod.get_credential("ANTHROPIC_API_KEY")
        if key:
            env["ANTHROPIC_API_KEY"] = key
    return env


def run_claude(
    prompt: str,
    label: str,
    timeout: int = 300,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
) -> str:
    """claude CLI を subprocess で呼び出し、結果を返す。

    ANTHROPIC_API_KEY を子プロセスに渡さないことで、
    WebSearch がサブスクリプション認証(OAuth)を使うようにする。

    Anthropic API の 5xx 系エラー (例: 529 Overloaded) は指数バックオフで
    最大 ``max_attempts`` 回までリトライする。
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts は 1 以上である必要があります (got {max_attempts})")

    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("claude CLI が見つかりません。PATH を確認してください。")

    env = build_env(auth_mode=state_mod.read_state().auth_mode)
    model = get_model()
    cmd = [
        claude_path, "-p", prompt,
        "--output-format", "json",
        "--allowedTools", "WebSearch",
        "--model", model,
    ]

    last_returncode = 0
    last_detail = ""
    for attempt in range(1, max_attempts + 1):
        logger.info(
            "claude CLI 呼び出し開始: %s (timeout=%ds, attempt=%d/%d)",
            label, timeout, attempt, max_attempts,
        )
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            logger.error("claude CLI タイムアウト: %s (%ds)", label, timeout)
            raise RuntimeError(f"claude CLI がタイムアウトしました ({label})") from exc

        if result.returncode == 0:
            logger.info("claude CLI 完了: %s (%d文字)", label, len(result.stdout))
            return _parse_and_log_usage(result.stdout, label)

        logger.error(
            "claude CLI エラー [%s] rc=%d attempt=%d/%d\nstdout=%s\nstderr=%s",
            label, result.returncode, attempt, max_attempts, result.stdout, result.stderr,
        )
        last_returncode = result.returncode
        last_detail = (result.stderr or result.stdout or "").strip()

        if is_transient(result.stdout, result.stderr) and attempt < max_attempts:
            delay = _backoff_delay(attempt)
            logger.warning(
                "一時的なエラーを検出、%.1fs 後にリトライします [%s] (attempt %d/%d)",
                delay, label, attempt, max_attempts,
            )
            time.sleep(delay)
            continue
        break

    if len(last_detail) > 2000:
        last_detail = last_detail[:2000] + "…(truncated)"
    raise RuntimeError(f"claude CLI エラー [{label}] rc={last_returncode}: {last_detail}")
