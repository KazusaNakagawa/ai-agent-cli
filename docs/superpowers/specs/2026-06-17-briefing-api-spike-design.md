# Claude API Briefing — Cost-Verification Spike

Date: 2026-06-17
Status: Design approved, pending implementation plan

## Goal

Verify whether running the daily briefing through the **raw Anthropic Messages
API** (Sonnet 4.6, no tools) costs materially less than the current `claude` CLI
path. The CLI injects a large agentic system prompt + tool definitions, which the
cost analysis (`docs/reports/cost-analysis/2026-06-17-usage-cost-analysis.md`) identified
as the dominant cache_creation cost. This spike runs in parallel with the
existing CLI briefing and is compared via the shared usage log.

This is a **spike**, not a production replacement. Scope is deliberately minimal.

## Non-goals (YAGNI)

- No change to the existing CLI briefing (`src/generator/briefing.py`, `bin/run.sh`).
- No Notion posting, no production cutover, no Haiku comparison, no retry/backoff
  hardening. These are deferred until the cost result justifies them.

## Isolation requirement

The spike MUST be a **separate command**, fully decoupled from the current run
path. It does not touch `bin/run.sh` or the existing briefing module.

- Entrypoint: `apps/python/bin/briefing_api.py`
- Thin wrapper: `bin/briefing_api.sh` (repo root), mirroring `bin/run.sh` style.
- Invocation: `bin/briefing_api.sh`

## Architecture

```
Brave pre-fetch (reuse local_llm) → format context block → Claude API (Sonnet 4.6, no tools)
   → save output .md → log usage with "(API)" labels + computed cost
```

### Components

1. **`src/generator/briefing_api.py`** (new) — the spike body.
   - Reuse `src.local_llm.briefing.prefetch_briefing_context` +
     `enrich_with_article_text` (+ `BraveSearchClient`) to fetch today's articles.
   - Format the fetched hits into a plain-text context block.
   - Build the prompt from the existing `prompts/briefing.md` /
     `prompts/briefing_sectors.md`, with the `WebSearchを使って今日の最新情報を調べ`
     instruction replaced by "use the following pre-fetched articles as your
     source" + the injected context block. The output format section is reused
     verbatim so the result is comparable to the CLI version.
   - Call the `anthropic` SDK `messages.create` with `model="claude-sonnet-4-6"`,
     no tools. Format/citation rules go in the `system` parameter.
   - Run メイン分析 and セクタースイープ (same two jobs as the CLI version).

2. **Cost + usage logging.**
   - Map `response.usage` → the existing `usage_logger.log_usage` record. The SDK
     usage fields (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
     `cache_read_input_tokens`) already match the logger's expected keys.
   - Compute `cost_usd` from Sonnet 4.6 pricing (input / output / cache-write /
     cache-read per-Mtok constants defined in the module).
   - Labels: `メイン分析(API)` and `セクタースイープ(API)` so both the CLI and API
     rows land in the same `log/usage/<date>-usage.jsonl` for direct A/B compare.

3. **Dependency.** Add `anthropic` to `requirements.in`, recompile to
   `requirements.txt`.

4. **Auth.** API key from `credentials.get_credential("ANTHROPIC_API_KEY")`
   (Keychain → `.env`). Independent of the CLI OAuth `auth_mode` toggle — the
   spike is a pure API call and always needs a key. Fail fast with a clear error
   if the key is missing.

### Output

Write the generated briefing to a file (e.g. `output/briefing_api_<date>.md`) for
side-by-side quality comparison with the CLI version. No Notion posting.

## Data flow

1. Load `briefing.json` (reuse `src.config.load_config`).
2. Fetch stock moves (reuse `fetch_stock_move_map`).
3. Brave pre-fetch + article enrichment (reuse local_llm).
4. Render context block + build the two API prompts.
5. Two `messages.create` calls (can be sequential for the spike — simplicity over
   the CLI's parallelism).
6. Assemble output, write .md, log usage per call.

## Error handling

- Missing `ANTHROPIC_API_KEY` → clear error, exit non-zero.
- Missing `BRAVE_API_KEY` → clear error (same as local_llm path).
- An API call failure is logged and surfaced; the spike may abort (no elaborate
  fallback — this is a spike).
- Usage logging failures are swallowed (existing `log_usage` behavior).

## Testing

- Unit test for the Sonnet cost computation (given a usage dict → expected USD).
- Unit test for prompt construction: the context block is injected and the
  `WebSearch` instruction is absent.
- The API call itself is mocked (no live API in tests); assert the SDK is called
  with the expected model and no tools, and that usage is logged with the
  `(API)` label.

## Verification (A/B)

Run `bin/briefing_api.sh` on the same day as the CLI briefing, then inspect
`log/usage/<date>-usage.jsonl`: `メイン分析` vs `メイン分析(API)` etc. Compare
cost_usd, token breakdown (expect cache_creation to drop sharply), and read both
output .md files for quality. Optionally extend `bin/usage_report.py` later to
group by label, but that is out of scope here.

## Open follow-ups (post-spike, not in this work)

- If cost + quality are acceptable: production cutover, Notion posting, parallel
  calls, model tuning.
