# Quick start with npx

Run the Web UI without cloning the repository:

```bash
npx brief-lens
```

The first run sets up a data home and the Python backend, then starts the API and
the Web UI and opens your browser. Later runs start in a few seconds.

> **Release status:** `brief-lens` is published from `v*` tags (see [Releasing](#releasing)).
> Until the first release is on npm, try a local build as described in
> [Trying an unreleased build](#trying-an-unreleased-build).

## Prerequisites

| Requirement | Why | Install |
|---|---|---|
| Node.js 18+ | runs the launcher and the Web UI | [nodejs.org](https://nodejs.org/) |
| [uv](https://docs.astral.sh/uv/) | creates the Python environment for the backend | `curl -LsSf https://astral.sh/uv/install.sh \| sh` or `brew install uv` |
| Claude Code CLI, logged in | every agent call goes through it | `npm install -g @anthropic-ai/claude-code`, then run `claude` once |
| A paid Claude plan (Pro/Max) | the CLI's OAuth session is what the app uses; the free plan cannot run it | — |
| macOS or Linux | the launcher and backend scripts assume a POSIX environment | — |

If anything is missing, the launcher lists each gap with its install command and exits
with status 1 before touching your disk.

## First run

```bash
npx brief-lens
```

What happens, in order:

1. **Pre-flight** — checks Node.js, `uv` and `claude`.
2. **Data home** — creates `~/.brief-lens/`, copies `config/briefing.json` from the shipped
   template, and generates a session token (mode 0600).
3. **Python environment** — `uv venv` + `uv pip sync` into `~/.brief-lens/runtime/venv`.
   This is the slow step (a few minutes on a cold uv cache). It is skipped on later runs
   unless a new version ships a changed `requirements.txt`.
4. **Servers** — starts the API on `127.0.0.1:8000` and the Web UI on `localhost:3000`,
   waits until both answer, then opens the browser.

The Web UI opens on the onboarding wizard. Press **Ctrl-C** in the terminal to stop both
servers.

## Options

```
--port <n>       Web UI port (default: 3000)
--api-port <n>   API port (default: 8000)
--home <dir>     Data home (default: $BRIEF_LENS_HOME or ~/.brief-lens)
--no-browser     Do not open the browser (also skipped when $CI is set)
-v, --version    Print the version and exit
-h, --help       Show this help and exit
```

Both servers listen on localhost only; they are not reachable from your LAN.

## Data home

Everything the app writes lives under one directory (default `~/.brief-lens/`, override
with `--home` or `BRIEF_LENS_HOME`):

```
~/.brief-lens/
  config/briefing.json   # your portfolio, watch sectors, geopolitical risks
  output/                # generated briefings, journal, exports
  input/                 # images and attachments uploaded in chat
  log/                   # app and usage logs
  runtime/venv/          # Python environment (safe to delete; rebuilt on next run)
  session-token          # bearer token shared by the API and the Web UI
  .env                   # optional: credentials fallback (see below)
```

Edit `config/briefing.json` directly or from the **Config** screen. The schema is described
in [configuration.md](configuration.md).

### Credentials

Discord and Notion credentials are stored in the OS keychain from the Web UI's settings.
An npx install uses its own keychain service, **`brief-lens`**, separate from a repository
checkout's `ai-agent` service — so a new install never triggers macOS password prompts for
items created by another install, and the two never share secrets. As a fallback, values
in `~/.brief-lens/.env` (same variable names as [`.env.example`](../../.env.example)) are
read when the keychain has no entry.

## Running next to a repository checkout

The npx install and a clone (`bin/serve.sh`) are fully separate: different data, different
keychain service. They do default to the same ports, so pick others for one of them:

```bash
npx brief-lens --port 3100 --api-port 8100
```

## Upgrade and uninstall

```bash
npx brief-lens@latest          # run the newest release (Python deps re-sync only if they changed)

rm -rf ~/.brief-lens           # remove all data, the venv and the token
# remove keychain items, one per credential you saved, e.g.:
security delete-generic-password -s brief-lens -a NOTION_API_KEY
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `missing prerequisites` and exit 1 | Install what it lists, then run again. |
| `port 8000 is already in use` | Another server (often a clone's `bin/serve.sh`) holds the port — use `--api-port` / `--port`. |
| `... session-token is a symlink` | The launcher refuses to write through a symlink. Remove it and run again. |
| First run seems stuck after "Installing Python dependencies" | uv is downloading packages; a cold cache can take several minutes. |
| Ctrl-C during the first install | Safe — the install is retried on the next run. |

## Limitations

- **Scheduled runs** (launchd/cron morning briefings, sleep recovery) are clone-only for now;
  see [launchd-setup.md](launchd-setup.md).
- **Save to Notion from chat** runs your user-level `/notion-import` Claude Code skill; without
  it installed, the local markdown copy is still saved.
- Windows is not supported.

## Trying an unreleased build

Build the tarball from a checkout and point npx at it. Use `--package=`: passing a tarball
path as the command makes npx try to execute the file.

```bash
cd apps/web && npm ci && cd ../..
cd packages/brief-lens && npm pack --pack-destination /tmp
npx --package=/tmp/brief-lens-0.1.0.tgz brief-lens
```

`npm pack` runs `scripts/build.mjs`, which builds the Web UI into `apps/web/.next-pack` (a
running `next dev` is unaffected) and refuses to package real configs, runtime output,
tokens or `.env` files.

## Releasing

Maintainers only. One-time setup in the GitHub repository settings:

1. **Environments → New environment** `npm-publish`, with yourself as a required reviewer.
2. Add an `NPM_TOKEN` secret (an npm automation token) to that environment.

Then bump `packages/brief-lens/package.json` `version`, merge to `main`, and push a matching
tag:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

The `publish` workflow checks that the tag matches the package version, runs the launcher
tests, waits for approval, and runs `npm publish --provenance`.
