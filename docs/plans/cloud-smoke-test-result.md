# Cloud Mode Smoke Test Result

Facts collected on the machine that executed `docs/plans/cloud-smoke-test.md`.

| Command | Output |
| --- | --- |
| `uname -a` | `Linux vm 6.18.44-fc-v22 #1 SMP PREEMPT_DYNAMIC @0 x86_64 x86_64 x86_64 GNU/Linux` |
| `hostname` | `vm` |
| `pwd` | `/home/user/ai-agent-cli` |
| `git rev-parse --abbrev-ref HEAD` | `chore/cloud-smoke-test` |
| `git rev-parse --short HEAD` | `31d3b50` |
| `date -u` | `Sat Aug 29 00:23:27 UTC 2026` |

The host is Linux (cloud), so this run executed in a cloud environment rather
than on the local Mac.

## Previous run

An earlier execution of the same plan ran locally and recorded a Darwin
(`arm64`) host from a local agent worktree. This file now records the cloud
run, which is what the plan set out to verify.
