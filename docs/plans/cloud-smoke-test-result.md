# Cloud Mode Smoke Test Result

Facts collected on the machine that executed `docs/plans/cloud-smoke-test.md`.
The git values were captured before the working tree was moved onto this
branch, so they describe the agent worktree the run started in.

| Command | Output |
| --- | --- |
| `uname -a` | `Darwin nakagawakazusanoMacBook-Air.local 25.5.0 Darwin Kernel Version 25.5.0: Tue Jun  9 22:26:22 PDT 2026; root:xnu-12377.121.10~1/RELEASE_ARM64_T8132 arm64` |
| `hostname` | `nakagawakazusanoMacBook-Air.local` |
| `pwd` | `/Users/nakagawakazusa/work/ai-agent/.claude/worktrees/agent-a0da46f541e54b3d1` |
| `git rev-parse --abbrev-ref HEAD` | `worktree-agent-a0da46f541e54b3d1` |
| `git rev-parse --short HEAD` | `5928c0b` |
| `date -u` | `2026年 8月28日 金曜日 23時38分53秒 UTC` |

The host is Darwin (local Mac), not Linux, so this run executed locally rather
than in a cloud environment.
