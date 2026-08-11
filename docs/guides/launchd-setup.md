# Scheduled Execution — macOS launchd Setup

macOS uses **launchd** instead of cron. `bin/run.sh` (root-level wrapper) sources `.env` and delegates to `apps/python/bin/run.sh`, so API credentials are available in non-interactive shells.

> **Current setup (2026-08-12): manual execution.** The maintainer's machine no longer loads the daily briefing or recovery launchd jobs. Run `./bin/run.sh` by hand once the Mac is open and fully awake. launchd remains documented below for AC-powered / always-awake setups only. cron + `pmset` is the other alternative — [cron-setup.md](cron-setup.md). Use at most one scheduler; running both would trigger the briefing twice.

## Manual execution (active)

Run from the repo root after opening the lid and confirming the Mac is awake (not DarkWake):

```bash
cd /path/to/ai-agent
./bin/run.sh
```

If today's sector sweep failed partway through, re-run only that half:

```bash
./bin/recover.sh
```

**Why not launchd on a lid-closed laptop?** On 2026-08-12 a missed 05:00 job started in DarkWake, transient retries burned the Anthropic session limit for >$2, and no briefing MD was produced ([#443](https://github.com/KazusaNakagawa/ai-agent-cli/issues/443)). `caffeinate` does not keep battery-powered DarkWake alive long enough for the claude CLI calls to finish.

### Unload launchd (already done on maintainer machine)

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.kazusa.ai-agent-briefing.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ai-agent.recovery.plist
launchctl list | grep ai-agent   # should print nothing
```

Plist files under `~/Library/LaunchAgents/` are left in place so they can be re-registered later; only the loaded jobs are removed.

---

## Optional: launchd scheduling

The sections below describe how to **re-enable** automatic daily runs. Only do this when the Mac is reliably awake at 05:00 (lid open on AC, or a always-on host).

**Why launchd rather than cron:** `man launchd.plist` states it plainly — *"Unlike cron which skips job invocations when the computer is asleep, launchd will start the job the next time the computer wakes up."* On a lid-closed, battery-powered Mac a scheduled `pmset` wake only produces a ~20-second DarkWake, so a 05:00 cron job never fires and is never retried. launchd runs the missed invocation at the next wake instead — which is exactly what caused the 2026-08-12 token burn when the wake was a short DarkWake.

**Schedule behaviour:**

| Day | What runs |
|---|---|
| Mon – Sun | `python -m src.handler` (daily market briefing) |
| Fri | `python -m src.handler` → `python -m src.weekly_handler` (daily + weekly recap) |

## DarkWake severs the sector sweep — the recovery job

On a lid-closed, battery-powered Mac the 05:00 job fires **inside a DarkWake**, which lasts about 45 seconds before macOS goes back to sleep. The claude CLI's HTTPS connection dies with `API Error: Connection closed mid-response`, and because the sector sweep is the long half of the pipeline (~20 web searches) it is the half that reliably loses the race.

Measured on 2026-07-31 (`pmset -g log`):

| Time | Event |
|---|---|
| 05:06:54 | DarkWake, `Using BATT` — launchd starts the briefing |
| 05:07:39 | `Entering Sleep state due to 'Maintenance Sleep'` — 903 s asleep |
| 05:22:42 / 05:38:31 | Two more DarkWake → sleep cycles |
| 05:54:19 | Sector sweep fails; wall clock 47 min against only 3 min of actual API time |

`caffeinate -ims` in `apps/python/bin/run.sh` does **not** prevent this: `man caffeinate` restricts `-s` to AC power, and the machine was on battery. Retrying in-process does not help either — the retry lands in the same sleep window.

The fix is a second launchd job that redoes **only** the sector sweep once the Mac is genuinely awake:

```bash
cp launchd/com.ai-agent.recovery.plist ~/Library/LaunchAgents/   # edit paths first
plutil -lint ~/Library/LaunchAgents/com.ai-agent.recovery.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ai-agent.recovery.plist
```

It is scheduled once a day at 08:00 and is a no-op unless today's `briefing_YYYY-MM-DD.md` carries the sector-failure notice — measured at 1.2 s with no claude call on a day the briefing succeeded. Before spending anything it calls `src.power.is_system_awake()`, which reads the last `Sleep` / `Wake` / `DarkWake` event from `pmset -g log` and defers when the machine is not fully awake. A single slot suffices because launchd runs a missed one as soon as the Mac wakes, so in practice it fires right when the lid opens. On success it splices the sweep into today's MD and appends it to the same Notion page — the main analysis is never re-run, so a recovery costs roughly half a full re-briefing.

Run it by hand any time with `bin/recover.sh`.

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

    <!-- Every day 05:00 (no Weekday key = all days) -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>5</integer>
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
  docs/guides/launchd-setup.md | grep -A 40 '<?xml' | head -40 > "$PLIST"
```

> Alternatively, copy the XML block above, replace `YOUR_USERNAME` and `/path/to/ai-agent` manually, and save to `$PLIST`.

## 3. Register and verify

```bash
# Validate, then register (`launchctl load` is deprecated)
plutil -lint "$PLIST"
launchctl bootstrap gui/$(id -u) "$PLIST"

# Confirm registered (shows "-  0  <LABEL>")
launchctl list | grep "$(whoami)"

# Confirm the schedule launchd actually holds
launchctl print "gui/$(id -u)/$LABEL" | grep -A 4 descriptor

# Test trigger immediately
launchctl start "$LABEL"

# Watch logs
tail -f "$PROJECT/apps/python/log/launchd.stderr.log"
```

## 4. Unregister (switch back to manual)

```bash
launchctl bootout gui/$(id -u) "$PLIST"
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ai-agent.recovery.plist
launchctl list | grep ai-agent   # should print nothing
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
