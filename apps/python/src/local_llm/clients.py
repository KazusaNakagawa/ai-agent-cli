"""Ollama / Chroma クライアントのファクトリと起動時チェック。"""

from __future__ import annotations

from .config import COLLECTION_NAME, LocalLLMConfig


class OllamaUnavailable(RuntimeError):
    pass


class EmbedModelMismatch(RuntimeError):
    """Existing Chroma collection was built with a different embed model.

    Raised by ``make_chroma_collection`` when the current `cfg.embed_model`
    does not match the embed model recorded in the persisted collection's
    metadata. Different embed models produce vectors of different
    dimensions (e.g. bge-m3=1024 vs nomic-embed-text=768), and mixing them
    in one collection raises a dim-mismatch error on the first upsert; we
    detect it up-front and tell the operator to ``--reset``.
    """


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


_LEGACY_EMBED_MODEL = "nomic-embed-text"


def make_chroma_collection(cfg: LocalLLMConfig):
    import chromadb
    cfg.chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(cfg.chroma_path))
    coll = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"embed_model": cfg.embed_model},
    )
    # Pre-#135 collections have no embed_model tag; they were built with the
    # previous default (nomic-embed-text). Fall back to that so the mismatch
    # check still catches a silent dimension change.
    prev_model = (coll.metadata or {}).get("embed_model") or _LEGACY_EMBED_MODEL
    if prev_model != cfg.embed_model:
        raise EmbedModelMismatch(
            f"Existing Chroma collection at {cfg.chroma_path} was built with "
            f"embed_model={prev_model!r}, but current config requests "
            f"{cfg.embed_model!r}. Embedding dimensions differ. Rebuild with:\n"
            f"  bin/local_llm.sh --index --reset"
        )
    return coll
