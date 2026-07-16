# Scheduled Execution — macOS launchd Setup

macOS uses **launchd** instead of cron. `bin/run.sh` (root-level wrapper) sources `.env` and delegates to `apps/python/bin/run.sh`, so API credentials are available in non-interactive shells.

**Schedule behaviour:**

| Day | What runs |
|---|---|
| Mon – Sun | `python -m src.handler` (daily market briefing) |
| Fri | `python -m src.handler` → `python -m src.weekly_handler` (daily + weekly recap) |

## 0. Define variables

Run these in your shell before following any step below:

```bash
PROJECT="/path/to/ai-agent"          # absolute path to this repo
LABEL="com.$(whoami).ai-agent-briefing"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
```

> Replace `/path/to/ai-agent` with the actual absolute path (e.g. `/Users/$(whoami)/work/ai-agent`).

## 1. Validate credentials first (dry-run)

```bash
cd "$PROJECT"
source .env
(cd apps/python && .venv/bin/python -m src.handler --dry-run)
```

No WARNING lines → credentials are set correctly.

## 2. Create the plist

Save the following to `$PLIST`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.YOUR_USERNAME.ai-agent-briefing</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/path/to/ai-agent/bin/run.sh</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/YOUR_USERNAME</string>
    </dict>

    <!-- Every day 07:00 (no Weekday key = all days) -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>7</integer>
        <key>Minute</key><integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/path/to/ai-agent/apps/python/log/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/ai-agent/apps/python/log/launchd.stderr.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

Or generate it in one shot using the variables from Step 0:

```bash
sed \
  -e "s|YOUR_USERNAME|$(whoami)|g" \
  -e "s|/path/to/ai-agent|$PROJECT|g" \
  docs/launchd-setup.md | grep -A 40 '<?xml' | head -40 > "$PLIST"
```

> Alternatively, copy the XML block above, replace `YOUR_USERNAME` and `/path/to/ai-agent` manually, and save to `$PLIST`.

## 3. Register and verify

```bash
# Register
launchctl load "$PLIST"

# Confirm registered (shows "-  0  <LABEL>")
launchctl list | grep "$(whoami)"

# Test trigger immediately
launchctl start "$LABEL"

# Watch logs
tail -f "$PROJECT/apps/python/log/launchd.stderr.log"
```

## 4. Unregister (if needed)

```bash
launchctl unload "$PLIST"
```

## Requirements

| Item | Why |
|---|---|
| `.env` at project root | Root `bin/run.sh` sources it for API tokens |
| `~/.claude/` accessible | Claude Code CLI reads its OAuth token from here |
| `apps/python/log/` directory exists | Output target for launchd stdout/stderr |
| `/opt/homebrew/bin` in PATH | Required for `claude` CLI installed via Homebrew |

```bash
mkdir -p "$PROJECT/apps/python/log"
```

If credentials are missing at runtime, the agent logs a WARNING per missing credential and writes output to `apps/python/output/briefing/briefing_YYYY-MM-DD.md` instead of sending to Discord/Notion.
