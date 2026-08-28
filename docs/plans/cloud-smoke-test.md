# Cloud Mode Smoke Test

A throwaway plan used only to verify that `claude --cloud` can pick up a
committed plan file, run it in a cloud environment, and hand the result back.
It must not touch anything else in the repository.

## Task

1. Collect the following facts about the machine executing this plan:

   ```bash
   uname -a
   hostname
   pwd
   git rev-parse --abbrev-ref HEAD
   git rev-parse --short HEAD
   date -u
   ```

2. Write the results to `docs/plans/cloud-smoke-test-result.md` as a Markdown
   table with two columns, `Command` and `Output`. Add one sentence below the
   table stating whether the host is Linux (cloud) or Darwin (local Mac).

3. Commit the new file with the message
   `chore: record cloud mode smoke test result` and open a pull request
   against `dev` titled `chore: record cloud mode smoke test result`.

## Constraints

- Create and modify only `docs/plans/cloud-smoke-test-result.md`.
- Do not touch `apps/`, `bin/`, `scripts/`, or any other documentation.
- Do not install dependencies, run the test suite, or start any application.
- If a step fails, stop and report the failure instead of working around it.
