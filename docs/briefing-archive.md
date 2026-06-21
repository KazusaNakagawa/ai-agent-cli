# Briefing Archive — Monthly Zip to Google Drive

Archive accumulated briefing markdown files (`apps/python/output/briefing/*_YYYY-MM-*.md`)
into a monthly zip and upload it to Google Drive at zero cost via
[`rclone`](https://rclone.org/). Runnable manually (CLI), automatically
(launchd), or from the Web UI (the **Archive last month** button on the Briefing
screen, which calls `POST /api/archive`).

> `rclone` is a standalone CLI tool — **not** an MCP server and unrelated to
> Claude. The archive scripts shell out to it directly. If it is missing or
> unconfigured, archiving exits non-zero with a setup hint (this is expected
> until you complete the steps below).

## 1. Install rclone

```bash
brew install rclone
```

## 2. Configure a Google Drive remote

`rclone config` is interactive and opens a browser for Google OAuth:

```bash
rclone config
```

- `n` — New remote
- name — **`gdrive`** (the scripts' default; use another name only if you also set `RCLONE_REMOTE`, see below)
- Storage — `drive` (Google Drive)
- `client_id` / `client_secret` — leave blank (press Enter) for the defaults
- scope — `1` (full access) or `drive.file` is enough
- accept the remaining defaults, then complete the browser sign-in
- `y` to confirm, `q` to quit

Verify:

```bash
rclone listremotes      # should list: gdrive:
```

## 3. Run the archive

```bash
# Previous month (default), keep local md files
bin/archive.sh

# A specific month
bin/archive.sh --month 2026-05

# Delete local md after a successful upload
bin/archive.sh --month 2026-05 --prune
```

Result: `briefing_YYYY-MM.zip` is created under `apps/python/output/archive/` and
uploaded to `gdrive:ai-agent/briefing/`. With no matching files the script exits
zero and prints a skip message; local md files are **kept** unless `--prune` is given.

## Configuration

Override via environment variables (e.g. in `.env`, which the root wrappers and
`bin/serve.sh` source so the Web API picks them up too):

| Variable | Default | Purpose |
|---|---|---|
| `RCLONE_REMOTE` | `gdrive` | rclone remote name |
| `RCLONE_PATH` | `ai-agent/briefing` | Remote path under the remote |
| `ARCHIVE_BRIEFING_DIR` | `apps/python/output/briefing` | Source dir of md files |
| `ARCHIVE_OUTPUT_DIR` | `apps/python/output/archive` | Where the zip is written |

## Web UI

The **Archive last month** button on the Briefing screen issues
`POST /api/archive` (optional `?month=YYYY-MM&prune=true`). On success it shows
the script stdout; on failure it shows a `500` with a stderr excerpt — the same
rclone setup hint surfaces here.

## Scheduled execution (launchd)

A monthly job template lives at `launchd/com.ai-agent.archive.plist` (runs on the
1st of each month at 03:00, archiving the previous month).

```bash
# Edit the absolute paths inside the plist to match your checkout first, then:
cp launchd/com.ai-agent.archive.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ai-agent.archive.plist

# Unload
launchctl unload ~/Library/LaunchAgents/com.ai-agent.archive.plist
```

See [launchd-setup.md](launchd-setup.md) for general launchd notes (PATH/HOME
environment keys matter for non-interactive runs).
