"""GET / PUT /api/state — ``~/.ai-agent/state.json`` の読み書き。

``auth_mode`` 専用の ``/api/auth/mode`` と違い、こちらは state.json 全体を返す
/ 部分更新できる汎用エンドポイント。オンボーディングウィザードが
``onboarded: true`` を立てるために使う。

部分更新ポリシー: 渡されたフィールドだけを read-modify-write で書き戻す。
``version`` は read-only (バージョン番号は state schema が変わったときだけ
バックエンド側で bump する)。
"""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src import state as state_mod
from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


class StateResponse(BaseModel):
    onboarded: bool
    auth_mode: Literal["cli", "api"]
    migrated_from_env: bool
    version: int


class StatePatchBody(BaseModel):
    """全フィールド optional。指定されたものだけを書き戻す。

    ``version`` は受け付けない (クライアントが書き換える理由がない)。"""

    onboarded: bool | None = None
    auth_mode: Literal["cli", "api"] | None = None
    migrated_from_env: bool | None = None


def _to_response(s: state_mod.State) -> StateResponse:
    return StateResponse(
        onboarded=s.onboarded,
        auth_mode=s.auth_mode,
        migrated_from_env=s.migrated_from_env,
        version=s.version,
    )


@router.get("/state", response_model=StateResponse)
def get_state() -> StateResponse:
    return _to_response(state_mod.read_state())


@router.put("/state", response_model=StateResponse)
def put_state(body: StatePatchBody) -> StateResponse:
    current = state_mod.read_state()
    if body.onboarded is not None:
        current.onboarded = body.onboarded
    if body.auth_mode is not None:
        current.auth_mode = body.auth_mode
    if body.migrated_from_env is not None:
        current.migrated_from_env = body.migrated_from_env
    state_mod.write_state(current)
    return _to_response(current)
