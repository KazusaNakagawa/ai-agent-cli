"""Ollama / Chroma クライアントのファクトリと起動時チェック。"""

from __future__ import annotations

from .config import COLLECTION_NAME, LocalLLMConfig


class OllamaUnavailable(RuntimeError):
    pass


def ensure_models_available(client, model: str, embed_model: str | None) -> None:
    """Verify the generation model (and optionally an embed model) is pulled.

    `embed_model=None` is for the --briefing path which only generates and
    does not touch the embed model; otherwise users without nomic-embed-text
    pulled would be blocked from briefing for no reason (#145).
    """
    try:
        info = client.list()
    except Exception as e:
        raise OllamaUnavailable(
            "Cannot reach Ollama. Run 'ollama serve' to start it. "
            f"(underlying error: {e})"
        ) from e

    # Support both dict-style (test stubs) and the ollama lib's Pydantic
    # ListResponse, whose entries expose `.model` (not `.name`).
    models = info["models"] if isinstance(info, dict) else info.models
    available: set[str] = set()
    for m in models:
        if isinstance(m, dict):
            name = m.get("name") or m.get("model")
        else:
            name = getattr(m, "model", None) or getattr(m, "name", None)
        if name:
            available.add(name)

    def _present(name: str) -> bool:
        if name in available:
            return True
        # Ollama tags untagged pulls as ":latest"; accept the implicit tag.
        if ":" not in name and f"{name}:latest" in available:
            return True
        return False

    required = [model] + ([embed_model] if embed_model is not None else [])
    missing = [m for m in required if not _present(m)]
    if missing:
        cmds = "\n  ".join(f"ollama pull {m}" for m in missing)
        raise OllamaUnavailable(
            f"Required models not pulled: {', '.join(missing)}.\n  {cmds}"
        )


def make_ollama_client(cfg: LocalLLMConfig):
    import ollama
    return ollama.Client(host=cfg.ollama_host)


def make_chroma_collection(cfg: LocalLLMConfig):
    import chromadb
    cfg.chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(cfg.chroma_path))
    return client.get_or_create_collection(COLLECTION_NAME)
