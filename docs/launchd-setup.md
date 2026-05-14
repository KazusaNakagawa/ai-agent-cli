# Scheduled Execution — macOS launchd Setup

macOS uses **launchd** instead of cron. `bin/run.sh` sources `.env` automatically so API credentials are available in non-interactive shells.

**Schedule behaviour:**

| Day | What runs |
|---|---|
| Mon – Sun | `briefing.py` (daily market briefing) |
| Fri | `briefing.py` → `weekly_summary.py` (daily + weekly recap) |

## 1. Validate credentials first (dry-run)

```bash
cd /path/to/ai-agent
source .env
.venv/bin/python bin/briefing.py --dry-run
```

No WARNING lines → credentials are set correctly.

## 2. Create the plist

Save the following to `~/Library/LaunchAgents/com.kazusa.ai-agent-briefing.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kazusa.ai-agent-briefing</string>

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
    <string>/path/to/ai-agent/log/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/ai-agent/log/launchd.stderr.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

Replace `/path/to/ai-agent` and `YOUR_USERNAME` with your actual values.

## 3. Register and verify

```bash
# Register
launchctl load ~/Library/LaunchAgents/com.kazusa.ai-agent-briefing.plist

# Confirm registered (shows "-  0  com.kazusa.ai-agent-briefing")
launchctl list | grep kazusa

# Test trigger immediately
launchctl start com.kazusa.ai-agent-briefing

# Watch logs
tail -f /path/to/ai-agent/log/launchd.stderr.log
```

## 4. Unregister (if needed)

```bash
launchctl unload ~/Library/LaunchAgents/com.kazusa.ai-agent-briefing.plist
```

## Requirements

| Item | Why |
|---|---|
| `.env` at project root | `bin/run.sh` sources it for API tokens |
| `~/.claude/` accessible | Claude Code CLI reads its OAuth token from here |
| `log/` directory exists | Output target for launchd stdout/stderr |
| `/opt/homebrew/bin` in PATH | Required for `claude` CLI installed via Homebrew |

```bash
mkdir -p /path/to/ai-agent/log
```

If credentials are missing at runtime, the agent logs a WARNING per missing credential and writes output to `output/briefing_YYYY-MM-DD.md` instead of sending to Discord/Notion.
