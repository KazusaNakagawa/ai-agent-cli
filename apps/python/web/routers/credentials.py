"""GET / PUT / DELETE /api/credentials — Keychain CRUD。

GET は ``{name: bool}`` の形式で各 allow-listed キーの「設定済みか」を返す。
値そのものは返さない（漏洩防止と、UI 側で fingerprint だけ表示するため）。
PUT/DELETE は 204。allow-list 外のキーは 400。すべて Bearer 必須。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src import credentials as cred_mod
from web.auth import require_bearer

router = APIRouter()


class CredentialBody(BaseModel):
    value: str


@router.get("/credentials", dependencies=[Depends(require_bearer)])
def list_credentials() -> dict[str, bool]:
    return cred_mod.list_credentials()


@router.put(
    "/credentials/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bearer)],
)
def put_credential(name: str, body: CredentialBody) -> None:
    try:
        cred_mod.set_credential(name, body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete(
    "/credentials/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bearer)],
)
def delete_credential(name: str) -> None:
    try:
        cred_mod.delete_credential(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
