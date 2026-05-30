"""Bearer トークン生成と検証 dependency。

``HTTPBearer`` security scheme を使うことで OpenAPI 仕様に認証要件が乗り、
Swagger UI (``/docs``) の右上に "Authorize" ボタンが出る。トークンを 1 回
ペーストすれば protected な全エンドポイントで自動付与される。
"""
import secrets
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TOKEN_FILE = Path.home() / ".ai-agent" / "session-token"
_token_cache: str | None = None

# ``auto_error=False`` so we return our own 401 message instead of FastAPI's
# generic 403 "Not authenticated" when the header is missing.
_bearer_scheme = HTTPBearer(auto_error=False)


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


def require_bearer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    expected = _ensure_token()
    if credentials is None or credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )
    if not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer token",
        )
