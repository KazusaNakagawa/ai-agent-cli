"""GET / PUT / DELETE /api/credentials — Keychain CRUD。

GET は ``{name: bool}`` の形式で各 allow-listed キーの「設定済みか」を返す。
値そのものは返さない（漏洩防止と、UI 側で fingerprint だけ表示するため）。
PUT/DELETE は 204。allow-list 外のキーは 400。すべて Bearer 必須。
"""
import keyring.errors
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src import credentials as cred_mod
from src import paths
from web.auth import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


class CredentialBody(BaseModel):
    value: str = Field(min_length=1)


def _keyring_unavailable(
    error: keyring.errors.KeyringError, env_edit: str
) -> HTTPException:
    """503 naming the cause and the .env route, which only applies after a restart."""
    if isinstance(error, keyring.errors.NoKeyringError):
        reason = "No OS keychain backend is available on this machine."
    else:
        reason = "The OS keychain could not complete the request. Unlock it and retry."
    return HTTPException(
        status_code=503,
        detail=f"{reason} Alternatively, {env_edit} {paths.dotenv_paths()[0]} and restart the app.",
    )


@router.get("/credentials")
def list_credentials() -> dict[str, bool]:
    return cred_mod.list_credentials()


@router.get("/credentials/sources")
def credential_sources() -> dict[str, str | None]:
    """Where each key resolves from ("keychain", "env" or null) — never the value."""
    return cred_mod.credential_sources()


@router.put("/credentials/{name}", status_code=status.HTTP_204_NO_CONTENT)
def put_credential(name: str, body: CredentialBody) -> None:
    try:
        cred_mod.set_credential(name, body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except keyring.errors.KeyringError as e:
        raise _keyring_unavailable(e, f"add a {name}=<value> line to") from e


@router.delete("/credentials/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(name: str) -> None:
    try:
        cred_mod.delete_credential(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except keyring.errors.KeyringError as e:
        raise _keyring_unavailable(e, f"remove the {name} line from") from e
