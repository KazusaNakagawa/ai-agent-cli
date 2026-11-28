# Running brief-lens in Docker

Run the Web UI in a container that uses the Claude login already set up on your
machine. No `ANTHROPIC_API_KEY` is involved: the container's `claude` CLI uses the same
OAuth login (paid Claude plan) as the one on the host.

> **Status:** written for [#622](https://github.com/KazusaNakagawa/ai-agent-cli/issues/622).
> The image has **not yet been built or run on a macOS host** (it has been built and booted in a Linux sandbox; see below) — see
> [Verification status](#verification-status) for what is still unproven.

## Quick start

Requires Docker (Docker Desktop on macOS) and a logged-in `claude` CLI on the host.

```bash
docker/sync-claude-auth.sh      # export the host's Claude login (once, and when it changes)
docker compose up --build
```

Run the script first. The credentials folder is mounted with `create_host_path: false`, so
if it does not exist yet `docker compose` stops with "bind source path does not exist"
instead of creating it as a root-owned directory the script could not then write to.

Then open <http://localhost:3000>. Stop with Ctrl-C, or `docker compose down`.
The first start installs the Python environment into the data volume and takes a few
minutes; later starts are quick.

Use another host port with `BRIEF_LENS_PORT=3100 docker compose up`.

## How Claude is reached

A macOS `claude` binary cannot run in a Linux container, and on macOS the login lives in
the Keychain, not in a file. So:

1. `docker/sync-claude-auth.sh` reads the login with `security find-generic-password -s
   "Claude Code-credentials"` (on Linux hosts it copies `~/.claude/.credentials.json`)
   and writes it to `~/.brief-lens-docker/claude-auth/.credentials.json` (directory
   0700, file 0600). The token is never printed.
2. `compose.yaml` mounts that directory **read-only** at `/run/claude-auth`.
3. The container entrypoint copies the file to `~/.claude/.credentials.json` for the
   Linux `claude` CLI (pinned in the `Dockerfile`) and starts brief-lens. That file lives
   in a persistent volume, and the CLI may refresh the tokens in it, so a restart does not
   blindly put the host export back: it replaces the installed login only when there is
   none, or when the export's access token expires later. Re-running the sync script after
   a host login change therefore takes effect on the next start.

The same idea is used by [MulmoClaude](https://github.com/receptron/mulmoclaude), which
exports the Keychain item at startup and mounts the result into its sandbox.
Alternatives considered: a host-side bridge that runs the host's `claude` (needs its own
authentication and a narrow command surface), and `claude setup-token` (a separate
long-lived token to manage). API-key mode stays a fallback only; compose never passes
`ANTHROPIC_API_KEY`, and `cli` auth mode strips it anyway.

## Security posture

- The Web UI is published as `127.0.0.1:3000` only, so it is reachable from the host's
  loopback but not from the LAN. The API is not published; inside the container it
  stays on `127.0.0.1` and the Web UI proxies to it.
- Inside the container the Web UI binds `0.0.0.0` (the launcher's `--host`), because a
  published port cannot reach a process bound to the container's loopback. That is only
  safe together with the loopback-only publish above — don't change the `ports` entry to
  `"3000:3000"`. A test (`packages/brief-lens/test/docker.test.mjs`) fails if it does.
- The Web UI's own request guard (`apps/web/lib/request-guard.ts`) is called from the API
  routes (`app/api/**`) and rejects a request whose `Host` is not `localhost`, `127.0.0.1`
  or `[::1]`. The HTML shell of a page is still served, but every data call behind it gets a
  403. Open `http://localhost:3000`; a LAN address or `host.docker.internal` does not work
  even if the port were published more widely.
- The entrypoint starts as root only to read the mounted login (its owner is the host
  user, which is not the image's `node` uid) and hand a copy to `node`; it then switches
  to `node` with `setpriv`, dropping every capability and setting no-new-privs, before
  anything else runs. The container itself keeps just `CHOWN`, `DAC_OVERRIDE`, `SETUID`
  and `SETGID` for that step, and `no-new-privileges` is set.
- No secret is baked into the image; `.dockerignore` keeps personal config, `.env`,
  `input/` and `output/` out of the build context.
- The exported login is a plaintext file on the host (mode 0600, like the CLI's own
  file on Linux). Delete it with `rm -r ~/.brief-lens-docker/claude-auth` when done.

## Data

| Volume | Mounted at | Holds |
|---|---|---|
| `brief-lens-data` | `/data` (`BRIEF_LENS_HOME`) | config, briefings, journal, uploads, venv, session token |
| `claude-state` | `/home/node/.claude` | the container's own Claude config and transcripts |

Back up or inspect the data with `docker run --rm -v brief-lens_brief-lens-data:/data
alpine ls /data`. `docker compose down -v` deletes both volumes.

### Discord / Notion credentials

There is no keyring in the container, so saving them from the Web UI is explained as
unavailable (#616). Use the `.env` route instead:

```bash
docker compose exec -T brief-lens sh -c 'umask 077; cat > /data/.env' < my.env
docker compose restart
```

`my.env` uses the variable names of [`.env.example`](../../.env.example).

## Parity with a macOS install

| Item | Expected in the container | Verified |
|---|---|---|
| Briefing run (incl. WebSearch) | works with the exported login | not yet |
| Q&A chat | works with the exported login | not yet |
| Chat attachments | stored under `/data/input` | not yet |
| Journal | stored under `/data/output` | not yet |
| Monitor | shows **only the container's own** usage: it reads `~/.claude/projects/` of the container, not the host's | limitation |
| Credentials without a keyring | `.env` route above | not yet |
| Save to Notion from chat | needs the user-level `/notion-import` skill in `~/.claude/skills/`, which the container does not have; copy it in with `docker compose cp ~/.claude/skills/notion-import brief-lens:/home/node/.claude/skills/` | not yet |
| Japanese text in charts | `fonts-noto-cjk` is installed | not yet |
| Scheduled runs | not supported: `power.py` and the `caffeinate` wrappers are macOS only, and the scheduling wrappers (`bin/*.sh`, launchd) are not in the image | limitation |

## Verification status

Checked in a Linux sandbox with a Docker daemon (image built from this `Dockerfile` with
three substitutions, listed below; run with the capability set from `compose.yaml`):

- The build stage (`npm ci` + `scripts/build.mjs`), the pinned `claude` CLI install, and the
  first-run Python environment (`uv` with `UV_PYTHON_PREFERENCE=only-system`) all work.
- The app comes up and the container reports `healthy`.
- The entrypoint reads credentials from a read-only mount owned by another uid, installs them
  for `node`, and then drops to `node`: the launcher, uvicorn and Next.js all run as uid 1000
  with an empty capability set. (A first version left the login unreadable and then in the
  wrong home directory; both were found this way and fixed.)
- The API listens on `127.0.0.1` only; the Web UI on `0.0.0.0` inside the container.
- The Web UI answers for `Host: localhost` and returns 403 for a LAN address and for
  `host.docker.internal`.
- The Linux `claude` treats a `.credentials.json` in the Keychain's JSON shape as an OAuth
  login and tries to use it. With a fake token it ends in "OAuth session expired and could
  not be refreshed", not "Not logged in". Whether a *real* login is accepted is not proven.

The `docker` workflow (`.github/workflows/docker.yml`) repeats the build and boot on every
relevant PR with the real `Dockerfile` and `compose.yaml` — including the `apt` and `uv`
layers — and checks the published port, that the runner's LAN address is refused, the host
guard, the privilege drop, the installed login, Python 3.11-3.13, the `claude` CLI and the CJK
fonts. It never calls Claude, so a real login is still the part only a macOS host can prove.

Not covered by the manual sandbox run, because of the sandbox: `apt-get` (the network policy blocked
`deb.debian.org`) was replaced by copying Python 3.11 and its libraries from the official
`python` image, so the `python3` / `fonts-noto-cjk` install line is untested; `uv` came from the
host instead of `ghcr.io/astral-sh/uv` (blocked), so that pull is untested; and the container
used host networking, so the `127.0.0.1:3000:3000` publish was not exercised. The launcher's
`--host` option, the compose guards and the shell scripts are also covered by unit tests and
by running them against a throwaway `HOME`.

Confirmed by the `docker` workflow on a Linux runner (first green run on PR #623): the image
builds as written (`apt` packages and the `uv` image pull included), the Web UI answers on the
published loopback port, and the runner's LAN address is refused.

Still to prove on a macOS host with Docker Desktop:

1. `docker compose up --build` and the Web UI opening from the host browser. Docker Desktop
   publishes ports through its own VM, so a quick look from another device on the LAN
   (`http://<host-ip>:3000` should be refused) is worth repeating there.
2. The Linux `claude` accepts the exported Keychain login (a similar attempt is reported
   not to work in [anthropics/claude-code#10039](https://github.com/anthropics/claude-code/issues/10039);
   MulmoClaude's approach suggests it does). One real briefing run and one Q&A chat.
3. **Token refresh.** The access token expires after several hours, and the CLI renews
   it with the refresh token. If the refresh token rotates, a refresh inside the
   container could leave the host's Keychain copy stale. Watch whether the host `claude`
   still works after the container has refreshed. If it does not, the fix is to keep
   refreshing on the host only and re-run the sync script.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `bind source path does not exist` from `docker compose` | The credentials folder is missing. Run `docker/sync-claude-auth.sh` first. |
| `sync-claude-auth: ... exists but you cannot write to it` | Compose created the folder as root on an earlier run. `sudo rm -r` it, then run the script before `docker compose`. |
| `no Claude credentials at /run/claude-auth/...` in the log | Run `docker/sync-claude-auth.sh`, then `docker compose restart`. |
| `keeping the container's login (the host export is not newer)` after a host re-login | The container holds a login that expires later than the export. To force the export: `docker compose exec -u node brief-lens rm /home/node/.claude/.credentials.json`, then `docker compose restart`. |
| Requests fail with an auth error after some hours | The exported token expired. Run `claude` on the host, re-run `docker/sync-claude-auth.sh`, restart the container. |
| `port is already allocated` | Another process uses 3000: `BRIEF_LENS_PORT=3100 docker compose up`. |
| Container stays "starting" for minutes on first run | The Python environment is being installed into `/data`; follow `docker compose logs -f`. |
