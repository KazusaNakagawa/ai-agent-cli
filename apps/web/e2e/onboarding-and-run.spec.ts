import { expect, test } from "@playwright/test"

// The two tests below share backend state (onboarded=true is persisted into
// state.json by test 1, used by test 2). Run serially so the order is fixed
// and one test's failure aborts the rest instead of cascading.
test.describe.configure({ mode: "serial" })

test("first-time user can complete onboarding and reach the sidebar", async ({ page }) => {
  await page.goto("/")

  // Step 1 — Auth mode. "cli" is preselected; just advance.
  await expect(page.getByText("Choose how to call Claude")).toBeVisible()
  await page.getByRole("button", { name: "Next" }).click()

  // Step 2 — Portfolio. Tickers field is the only required input.
  await expect(page.getByText("Portfolio basics")).toBeVisible()
  await page.getByTestId("tickers-input").fill("PLTR, NVDA")
  await page.getByRole("button", { name: "Next" }).click()

  // Step 3 — Notifications. All blank so the wizard sends zero PUT
  // /api/credentials/* writes (the form filters empty values), keeping the
  // real Keychain untouched.
  await expect(page.getByText("Notifications and credentials")).toBeVisible()
  await page.getByRole("button", { name: "Next" }).click()

  // Step 4 — Dry-run pipeline check. Backend returns 202 immediately, then
  // job_store flips the status to "done" once lambda_handler(dry_run=True)
  // returns — typically sub-second.
  await expect(page.getByText("Verify the pipeline")).toBeVisible()
  await page.getByRole("button", { name: "Run test" }).click()
  await expect(page.getByTestId("job-status")).toHaveText("done", { timeout: 30_000 })

  // Finish triggers PUT /api/state {onboarded: true} then window.location.reload.
  // After reload, the Server Component sees onboarded=true and redirects "/"
  // to "/portfolio", which mounts the sidebar.
  await page.getByRole("button", { name: "Finish" }).click()
  await expect(page.getByTestId("nav-portfolio")).toBeVisible({ timeout: 15_000 })
})

test("chat: an in-flight job survives a page reload via sessionStorage resume (Issue #125)", async ({
  page,
  context,
}) => {
  // Route the chat backend at the browser→Next-proxy boundary so we don't
  // need a real briefing file or claude CLI. The first GET against the
  // stream hangs until reload aborts it; the second (post-reload) replay
  // delivers the full answer — modelling what the FastAPI tail loop does.
  let streamHits = 0
  await context.route("**/api/chat", async (route) => {
    if (route.request().method() !== "POST") {
      return route.fallback()
    }
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "e2e-resume", status: "pending" }),
    })
  })
  await context.route("**/api/chat/e2e-resume/stream", async (route) => {
    streamHits++
    if (streamHits === 1) {
      // Hold the response open. Reload aborts the request, so we don't
      // need to resolve this promise — Playwright reaps the route on
      // page navigation.
      await new Promise<void>(() => {})
      return
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: "data: Resumed answer.\n\n",
    })
  })

  // Test 1 above already ran the onboarding wizard, so MainLayout's
  // server-side onboarded check passes and the /chat route renders.
  await page.goto("/chat")
  await page.getByTestId("chat-input").fill("what's new?")
  await page.getByTestId("send-button").click()

  // The running snapshot must be in sessionStorage before reload —
  // that's what carries the jobId across the page lifecycle.
  await page.waitForFunction(
    () => {
      const raw = window.sessionStorage.getItem("ai-agent:chat-job:v1")
      if (!raw) return false
      const parsed = JSON.parse(raw) as { jobId?: string; status?: string }
      return parsed.jobId === "e2e-resume" && parsed.status === "running"
    },
    { timeout: 5_000 },
  )

  await page.reload()

  // After remount, the hydrated jobId triggers a fresh GET against the
  // stream and the replay fills in the assistant message. The user's
  // original question rehydrates from the persisted snapshot.
  await expect(page.getByTestId("chat-msg-user")).toContainText(
    "what's new?",
  )
  await expect(page.getByTestId("chat-msg-assistant")).toContainText(
    "Resumed answer.",
  )
  expect(streamHits).toBeGreaterThanOrEqual(2)
})
