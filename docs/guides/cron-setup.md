# Scheduled Execution — cron + pmset Setup

This is an **alternative** scheduling setup. The **currently active** approach is manual `./bin/run.sh` — see [launchd-setup.md](launchd-setup.md#manual-execution-active). launchd is documented there for always-awake / AC setups; use **at most one** scheduler (cron, launchd, or manual). `bin/run.sh` (root-level wrapper) sources `.env` and delegates to `apps/python/bin/run.sh`, so API credentials are available in non-interactive shells.

> **Only use cron if the Mac stays awake at the scheduled time.** cron skips a job entirely when the machine is asleep and never retries it. Measured on this machine: with the lid closed on battery, the `pmset repeat` wake at 04:55 produced only a ~20-second DarkWake before returning to sleep, so the 05:00 job never fired — for days, silently, with no log file created at all. launchd retries on wake but can burn tokens in short DarkWake windows ([#443](https://github.com/KazusaNakagawa/ai-agent-cli/issues/443)); manual execution avoids both failure modes on a laptop.

**Schedule behaviour:**

| Day | What runs |
|---|---|
| Mon – Sun | `python -m src.handler` (daily market briefing) |
| Fri | `python -m src.handler` → `python -m src.weekly_handler` (daily + weekly recap) |

## 1. crontab entry

```bash
crontab -e
```

```cron
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
0 5 * * * cd /Users/YOUR_USERNAME/work/ai-agent && ./bin/run.sh >> /Users/YOUR_USERNAME/work/ai-agent/log/cron-run.log 2>&1
```

| Part | Why |
|---|---|
| `PATH=...` line | cron's default PATH lacks `/opt/homebrew/bin`, where the `claude` CLI lives |
| `cd <repo>` | `bin/run.sh` resolves paths from its own location, but `cd` keeps relative output paths predictable |
| `>> log/cron-run.log 2>&1` | cron mails output by default; redirect it to a file instead. `log/` is gitignored |

Create the log directory once:

```bash
mkdir -p ~/work/ai-agent/log
```

## 2. Wake the Mac before the run (`pmset`)

cron does **not** fire while the Mac is asleep — a missed 05:00 slot is simply skipped, not deferred. Schedule a wake 5 minutes earlier so the network and disk are ready:

```bash
sudo pmset repeat wakeorpoweron MTWRFSU 04:55:00
```

| Token | Meaning |
|---|---|
| `wakeorpoweron` | Wake from sleep, or power on if the Mac was shut down |
| `MTWRFSU` | Every day (M=Mon, T=Tue, W=Wed, R=Thu, F=Fri, S=Sat, U=Sun) |

Verify:

```bash
pmset -g sched     # expect: "wake at 4:55AM every day"
```

> **`pmset repeat` holds only one repeating schedule.** Setting a new one replaces the previous entry — there is no way to keep two repeating wake times. Cancel with `sudo pmset repeat cancel`.

> **`pmset repeat` is not sufficient on a lid-closed laptop.** The wake it schedules is a DarkWake that lasts only as long as the pending maintenance work — around 20 seconds in practice — so the machine is asleep again well before a job scheduled 5 minutes later. Verify with `pmset -g log | grep -E "Wake|Sleep"` around the scheduled time: a `DarkWake` immediately followed by `Entering Sleep state` means cron will not fire. Keeping the Mac awake requires the lid open on AC power (`pmset -g custom` shows `sleep 0` on AC); closing the lid sleeps the machine regardless of power source.

Note that `apps/python/bin/run.sh` re-execs itself under `caffeinate -ims`, which prevents sleep *during* the run. It cannot wake a Mac that is already asleep when cron fires — that is what `pmset` covers.

## 3. Verify

```bash
crontab -l                              # confirm the entry is installed
tail -f ~/work/ai-agent/log/cron-run.log  # watch the next run
```

To test the command without waiting for 05:00, run the same line by hand:

```bash
cd ~/work/ai-agent && ./bin/run.sh
```

## Requirements

| Item | Why |
|---|---|
| Full Disk Access for `/usr/sbin/cron` | macOS TCC blocks cron jobs from reading `~/Documents`, `~/.claude/`, etc. Grant via System Settings → Privacy & Security → Full Disk Access → `+` → ⌘⇧G → `/usr/sbin/cron` |
| `.env` at project root | Root `bin/run.sh` sources it for API tokens |
| `~/.claude/` accessible | Claude Code CLI reads its OAuth token from here |
| `log/` directory exists | Redirect target for cron stdout/stderr |
| `/opt/homebrew/bin` in PATH | Required for the `claude` CLI installed via Homebrew |

If credentials are missing at runtime, the agent logs a WARNING per missing credential and writes output to `apps/python/output/briefing/briefing_YYYY-MM-DD.md` instead of sending to Discord/Notion.
