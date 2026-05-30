"""Bearer トークン生成と検証 dependency。"""
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, status

TOKEN_FILE = Path.home() / ".ai-agent" / "session-token"
_token_cache: str | None = None


def _ensure_token() -> str:
    """起動時に呼ばれ、なければ生成・書込してキャッシュする。"""
    global _token_cache
    if _token_cache is not None:
        return _token_cache
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        _token_cache = TOKEN_FILE.read_text().strip()
    else:
        _token_cache = secrets.token_urlsafe(32)
        TOKEN_FILE.write_text(_token_cache)
        TOKEN_FILE.chmod(0o600)
    return _token_cache


def require_bearer(authorization: str = Header(default="")) -> None:
    expected = _ensure_token()
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )
    token = authorization[len("Bearer "):].strip()
    if not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer token",
        )
