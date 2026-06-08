"""Ollama / Chroma クライアントのファクトリと起動時チェック。"""

from __future__ import annotations

from .config import COLLECTION_NAME, LocalLLMConfig


class OllamaUnavailable(RuntimeError):
    pass


def ensure_models_available(client, model: str, embed_model: str) -> None:
    try:
        info = client.list()
    except Exception as e:
        raise OllamaUnavailable(
            "Cannot reach Ollama. Run 'ollama serve' to start it. "
            f"(underlying error: {e})"
        ) from e

    available = {m["name"] for m in info.get("models", [])}
    missing = [m for m in (model, embed_model) if m not in available]
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
