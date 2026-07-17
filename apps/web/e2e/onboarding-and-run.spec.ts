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

test("chat: Cancel mid-stream terminates the job and restores the question (Issue #99)", async ({
  page,
  context,
}) => {
  // Mock the job POST, hold the stream open until the user cancels,
  // and capture the DELETE so we can assert the backend cancel call
  // actually fires. The stream route is scoped to this job id, so any
  // DELETE that lands here is by definition for "e2e-cancel".
  let deleteHits = 0
  await context.route("**/api/chat", async (route) => {
    if (route.request().method() !== "POST") {
      return route.fallback()
    }
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "e2e-cancel", status: "pending" }),
    })
  })
  await context.route("**/api/chat/e2e-cancel/stream", async () => {
    // Hold the stream open without ever sending a body. The watch loop
    // sits at status="running" (busy=true → Cancel button visible),
    // and the user click below aborts the fetch via the store's
    // AbortController. The unroute in the finally block below releases
    // the handler before the context tears down so the pending promise
    // can't leak into a later test.
    // (Sending a one-shot body via route.fulfill would close the
    // response, which flips status to "done" before cancel can fire.)
    await new Promise<void>(() => {})
  })
  await context.route("**/api/chat/e2e-cancel", async (route) => {
    if (route.request().method() !== "DELETE") {
      return route.fallback()
    }
    deleteHits++
    await route.fulfill({ status: 204, body: "" })
  })

  try {
    await page.goto("/chat")
    await page.getByTestId("chat-input").fill("draft to cancel")
    await page.getByTestId("send-button").click()

    // The Cancel button replaces Send once the POST returns 202 and the
    // store flips into "running". The assistant bubble is mounted (the
    // bouncing-dots indicator renders while busy) but content stays
    // empty because the stream never emits.
    await expect(page.getByTestId("cancel-button")).toBeVisible()
    await expect(page.getByTestId("chat-msg-user")).toContainText(
      "draft to cancel",
    )

    await page.getByTestId("cancel-button").click()

    // Cancel turn is committed with the partial answer + Cancelled marker,
    // textarea is repopulated for re-edit, Send is back.
    await expect(page.getByTestId("chat-cancelled")).toBeVisible()
    await expect(page.getByTestId("chat-input")).toHaveValue("draft to cancel")
    await expect(page.getByTestId("send-button")).toBeVisible()
    await expect(page.getByTestId("chat-error")).toHaveCount(0)
    expect(deleteHits).toBe(1)
  } finally {
    await context.unrouteAll({ behavior: "ignoreErrors" })
  }
})

test("chat: the cross-date history toggle sends search_history:true (#395)", async ({
  page,
  context,
}) => {
  // Mock the chat backend so this doesn't need a real Ollama/chromadb index —
  // only the request the toggle produces is under test here.
  let capturedBody: Record<string, unknown> | null = null
  await context.route("**/api/chat", async (route) => {
    if (route.request().method() !== "POST") {
      return route.fallback()
    }
    capturedBody = route.request().postDataJSON()
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "e2e-history", status: "pending" }),
    })
  })
  await context.route("**/api/chat/e2e-history/stream", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: "data: from history search\n\n",
    })
  })

  try {
    await page.goto("/chat")
    await expect(page.getByTestId("search-history-toggle")).not.toBeChecked()

    await page.getByTestId("search-history-toggle").check()
    await page.getByTestId("chat-input").fill("NVDA について過去は？")
    await page.getByTestId("send-button").click()

    await expect(page.getByTestId("chat-msg-assistant")).toContainText(
      "from history search",
    )
    expect(capturedBody).toMatchObject({ search_history: true })
  } finally {
    await context.unrouteAll({ behavior: "ignoreErrors" })
  }
})
