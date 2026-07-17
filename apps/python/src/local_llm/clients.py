"""Factories for the Ollama / Chroma clients and startup checks."""

from __future__ import annotations

from .config import BRIEFING_COLLECTION_NAME, COLLECTION_NAME, LocalLLMConfig

# Maps a collection name to the CLI flag that rebuilds *just* that collection.
# The two collections share cfg.chroma_path but reset independently (#395),
# so the mismatch error below must not always point at `--index --reset`.
_RESET_FLAG_BY_COLLECTION = {
    COLLECTION_NAME: "--index --reset",
    BRIEFING_COLLECTION_NAME: "--index-briefings --reset",
}


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


# Frozen historical value: the embed model that pre-#135 collections were
# built with (when collections carried no embed_model metadata). Do NOT
# update this when DEFAULT_EMBED_MODEL changes — it must remain the model
# that legacy on-disk indexes actually used, or the mismatch check below
# will silently miss a dimension change.
_LEGACY_EMBED_MODEL = "nomic-embed-text"


def make_chroma_collection(cfg: LocalLLMConfig, collection_name: str = COLLECTION_NAME):
    """Get or create a Chroma collection at ``cfg.chroma_path``.

    ``collection_name`` defaults to the repo-code collection; pass a
    different name (e.g. the briefings collection, #395) to keep separate
    indexes side by side in the same persistent store. The embed-model
    mismatch check below applies per collection.
    """
    import chromadb
    cfg.chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(cfg.chroma_path))
    coll = client.get_or_create_collection(
        collection_name,
        metadata={"embed_model": cfg.embed_model},
    )
    # Pre-#135 collections have no embed_model tag; they were built with the
    # previous default (nomic-embed-text). Fall back to that so the mismatch
    # check still catches a silent dimension change.
    prev_model = (coll.metadata or {}).get("embed_model") or _LEGACY_EMBED_MODEL
    if prev_model != cfg.embed_model:
        reset_flag = _RESET_FLAG_BY_COLLECTION.get(collection_name, "--index --reset")
        raise EmbedModelMismatch(
            f"Existing Chroma collection at {cfg.chroma_path} was built with "
            f"embed_model={prev_model!r}, but current config requests "
            f"{cfg.embed_model!r}. Embedding dimensions differ. Rebuild with:\n"
            f"  bin/local_llm.sh {reset_flag}"
        )
    return coll


def delete_collection(cfg: LocalLLMConfig, collection_name: str) -> None:
    """Delete one named collection, leaving ``cfg.chroma_path`` and any other
    collection stored alongside it untouched. Used by ``--index-briefings
    --reset`` (#395) — narrower than wiping the whole persistent store, which
    would also destroy the unrelated repo-code index sharing the same path.
    """
    import chromadb
    if not cfg.chroma_path.exists():
        return
    client = chromadb.PersistentClient(path=str(cfg.chroma_path))
    try:
        client.delete_collection(collection_name)
    except chromadb.errors.NotFoundError:
        pass
