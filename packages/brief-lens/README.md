# brief-lens

A personal market-intelligence briefing agent with a local Web UI. It ties
geopolitical events, stock moves and sector themes to *your* portfolio, using
the Claude Code CLI for every model call.

```bash
npx brief-lens
```

The first run creates `~/.brief-lens/`, installs the Python backend with `uv`,
then starts the API and Web UI and opens your browser.

## Requirements

- Node.js 18+
- [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://docs.claude.com/en/docs/claude-code) CLI, logged in, on a paid Claude plan (Pro/Max)
- macOS or Linux

## Options

```
--port <n>       Web UI port (default: 3000)
--api-port <n>   API port (default: 8000)
--home <dir>     Data home (default: $BRIEF_LENS_HOME or ~/.brief-lens)
--no-browser     Do not open the browser
-v, --version    Print the version
-h, --help       Show help
```

Source, full docs and issues: https://github.com/KazusaNakagawa/ai-agent-cli
