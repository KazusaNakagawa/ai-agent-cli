"""GET / PUT /api/auth/mode — CLI / API モード切替。

GET は現在のモードを返す。PUT は ``Literal["cli", "api"]`` でバリデートして
``~/.ai-agent/state.json`` に永続化する。他の state フィールド
(``onboarded`` / ``migrated_from_env``) は read-modify-write でそのまま温存。
"""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src import state as state_mod
from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


class AuthModeBody(BaseModel):
    auth_mode: Literal["cli", "api"]


@router.get("/auth/mode")
def get_auth_mode() -> dict[str, str]:
    return {"auth_mode": state_mod.read_state().auth_mode}


@router.put("/auth/mode")
def put_auth_mode(body: AuthModeBody) -> dict[str, str]:
    current = state_mod.read_state()
    current.auth_mode = body.auth_mode
    state_mod.write_state(current)
    return {"auth_mode": body.auth_mode}
