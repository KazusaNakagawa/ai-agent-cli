# Local LLM (experimental)

Optional fully-local RAG over this repository, powered by Ollama + Chroma. The existing Claude Code / briefing / XSS agents are unaffected.

## Prerequisites

```bash
brew install ollama       # or follow https://ollama.com
ollama serve &
ollama pull qwen2.5:14b   # for --briefing: reliable tool calling (~8.5GB RAM with Q4)
ollama pull qwen2.5:7b    # for --ask / --index: smaller, fits the RAG path
ollama pull bge-m3        # embedding model: stronger JP + code retrieval

# optional alternatives
ollama pull qwen2.5-coder:14b  # code-heavy --ask queries
ollama pull qwen2.5:32b        # deepest explanations / final synthesis (~20GB RAM)
```

Requires `BRAVE_API_KEY` in `.env` for `--briefing` (Free-plan key at <https://api-dashboard.search.brave.com/>).

## Usage

```bash
bin/local_llm.sh --index                       # index ~/work/ai-agent-cli into Chroma
bin/local_llm.sh --status                      # show indexed chunk count & models
bin/local_llm.sh --ask "認証はどう動く？"
bin/local_llm.sh --sources "認証はどう動く？"  # retrieval-only debug
bin/local_llm.sh --index --reset               # rebuild from scratch
bin/local_llm.sh --briefing                    # generate daily briefing locally
bin/local_llm.sh --briefing --notion           # ...and post to Notion
bin/local_llm.sh --index-briefings              # index output/briefing/*.md for cross-date chat RAG (#395)
bin/local_llm.sh --index-briefings --reset      # rebuild only the briefings collection
```

Chroma data is stored in `apps/python/.chroma_db/` (gitignored). `--index-briefings` writes to a separate collection (`ai_agent_briefings`) from `--index`'s repo-code collection (`ai_agent_repo`), so they don't mix and `--reset` on one never touches the other. The daily batch (`src.handler`) runs this indexing automatically after saving each day's briefing; failures (e.g. Ollama not running) are logged and don't block briefing delivery.

## Model options

Swap the generation model via `LOCAL_LLM_MODEL` (env) or `--model` (CLI flag).

| Model | Approx. RAM (Q4) | Best for |
|---|---|---|
| `qwen2.5:7b` | ~5 GB | `--ask` / `--index` — fastest |
| `qwen2.5-coder:14b` | ~9 GB | Code-heavy `--ask` queries |
| `qwen2.5:14b` (default) | ~8.5 GB | `--briefing` — balanced |
| `qwen2.5:32b` | ~20 GB | Deepest explanations / final synthesis |

```bash
LOCAL_LLM_MODEL=qwen2.5:32b bin/local_llm.sh --ask "..."
bin/local_llm.sh --briefing --model qwen2.5:7b
```

## Dual-model briefing (reasoning final stage)

The final synthesis stage (自分への示唆) can run on a stronger model while the cheaper main model handles extraction/summary stages.

```bash
LOCAL_LLM_MODEL=qwen2.5:14b \
LOCAL_LLM_SYNTHESIS_MODEL=qwen2.5:32b \
  bin/local_llm.sh --briefing
```

When `LOCAL_LLM_SYNTHESIS_MODEL` is unset, both stages use `LOCAL_LLM_MODEL`.

## Environment overrides

`LOCAL_LLM_MODEL`, `LOCAL_LLM_SYNTHESIS_MODEL`, `LOCAL_LLM_EMBED_MODEL`, `LOCAL_LLM_TOP_K`, `LOCAL_LLM_CHROMA_PATH`, `OLLAMA_HOST`

> **Switching embed models requires a rebuild.** `bge-m3` (1024 dim) and the legacy `nomic-embed-text` (768 dim) produce incompatible vectors. If you change `LOCAL_LLM_EMBED_MODEL`, rebuild with `bin/local_llm.sh --index --reset`.
