import { execSync } from "node:child_process"
import { mkdirSync, rmSync, writeFileSync } from "node:fs"

import { defineConfig, devices } from "@playwright/test"

import { PATHS } from "./e2e/paths"

// Per-run isolation strategy: FastAPI stores state.json + session-token under
// `Path.home() / ".ai-agent"`, so launching it with HOME pointed at a
// throwaway tmp dir keeps `~/.ai-agent` untouched. `BRIEFING_CONFIG_PATH`
// does the same for briefing.json.
//
// The seed (wipe tmp HOME + generate matching tokens for FastAPI and the
// Next.js proxy) lives HERE rather than in `globalSetup` for two reasons:
//   1. Playwright launches `webServer` BEFORE running `globalSetup`. If we
//      seeded in globalSetup, FastAPI would boot first, read whatever stale
//      token a previous run left on disk, and cache it — every later
//      request that uses the freshly-seeded token would then 401.
//   2. Playwright re-imports this config in every worker, which would
//      otherwise re-run the seed mid-test and trigger the same race. The
//      `TEST_WORKER_INDEX` env var is set only inside workers, so we use it
//      to skip the seed there.
if (!process.env.TEST_WORKER_INDEX) {
  rmSync(PATHS.TMP_HOME, { recursive: true, force: true })
  mkdirSync(PATHS.TMP_AGENT_DIR, { recursive: true })
  const token = execSync(
    "node -e \"process.stdout.write(require('crypto').randomBytes(32).toString('base64url'))\"",
  )
    .toString()
    .trim()
  writeFileSync(PATHS.TMP_TOKEN_FILE, token, { mode: 0o600 })
  writeFileSync(PATHS.NEXT_TOKEN_FILE, token, { mode: 0o600 })
}

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts$/,
  outputDir: "./e2e/test-results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: ".venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000",
      cwd: PATHS.PYTHON_DIR,
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        HOME: PATHS.TMP_HOME,
        BRIEFING_CONFIG_PATH: PATHS.TMP_CONFIG_FILE,
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      command: "npm run dev",
      cwd: PATHS.WEB_DIR,
      url: "http://127.0.0.1:3000",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        AI_AGENT_TOKEN_PATH: PATHS.NEXT_TOKEN_FILE,
        API_BASE: "http://127.0.0.1:8000",
      },
    },
  ],
})
