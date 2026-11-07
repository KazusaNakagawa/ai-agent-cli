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

test("an onboarded user can re-run the setup wizard and back out (#543)", async ({ page }) => {
  // Seed the state this test needs instead of relying on the test above.
  const config = {
    portfolio: { tickers: ["MSFT", "GOOGL"], themes: ["AI"] },
    watch_sectors: [{ sector: "Cloud", tickers: ["MSFT"], notes: "kept" }],
    geopolitical: { conflicts: [] },
    watch_events: [],
  }
  expect((await page.request.put("/api/state", { data: { onboarded: true } })).ok()).toBe(true)
  expect((await page.request.put("/api/config", { data: config })).ok()).toBe(true)

  await page.goto("/portfolio")
  await page.getByTestId("config-toggle").click()
  await page.getByTestId("settings-nav-setup").click()
  await page.getByTestId("rerun-setup").click()

  // The wizard opens prefilled from the current settings.
  await expect(page).toHaveURL(/\/\?rerun=1$/)
  await expect(page.getByText("Choose how to call Claude")).toBeVisible()
  await page.getByRole("button", { name: "Next" }).click()
  await expect(page.getByTestId("tickers-input")).toHaveValue("MSFT, GOOGL")
  await page.getByTestId("tickers-input").fill("PLTR")
  await page.getByRole("button", { name: "Next" }).click()
  await expect(page.getByText("Notifications and credentials")).toBeVisible()

  // Cancel puts the saved config back and returns to the app. The onboarded
  // flag was never cleared, so nothing else is affected.
  await page.getByTestId("wizard-cancel-rerun").click()
  await expect(page).toHaveURL(/\/portfolio$/)
  await expect(page.getByTestId("nav-portfolio")).toBeVisible()
  // GET fills in schema defaults for fields the seed omitted.
  expect(await (await page.request.get("/api/config")).json()).toMatchObject(config)
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

test("chat: the log follows a streaming reply and pauses when scrolled up (#560)", async ({
  page,
}) => {
  // route.fulfill delivers a body in one piece, so the chat backend is faked
  // inside the page: each token is pushed from the test, making "the reply
  // grew" an explicit step rather than a timing race.
  await page.addInitScript(() => {
    const realFetch = window.fetch
    const encoder = new TextEncoder()
    const json = { "content-type": "application/json" }
    const w = window as unknown as Record<string, unknown>
    let controller: ReadableStreamDefaultController<Uint8Array>
    let jobs = 0
    window.fetch = async (input, init) => {
      const url = input instanceof Request ? input.url : String(input)
      if (url.endsWith("/api/chat") && init?.method === "POST") {
        jobs++
        return new Response(
          JSON.stringify({ job_id: `e2e-follow-${jobs}`, status: "pending" }),
          { status: 202, headers: json },
        )
      }
      if (/\/api\/chat\/e2e-follow-\d+\/stream$/.test(url)) {
        const body = new ReadableStream<Uint8Array>({
          start(c) {
            controller = c
            w.__streams = ((w.__streams as number) ?? 0) + 1
          },
        })
        return new Response(body, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        })
      }
      return realFetch(input, init)
    }
    w.__push = (text: string) =>
      controller.enqueue(encoder.encode(`data: ${text}\n\n`))
    w.__end = () => controller.close()
  })

  const log = page.getByTestId("chat-log")
  const scrollTop = () => log.evaluate((el) => el.scrollTop)
  const distance = () =>
    log.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight)
  const push = (text: string) =>
    page.evaluate((t) => {
      ;(window as unknown as { __push: (s: string) => void }).__push(t)
    }, text)
  const end = () =>
    page.evaluate(() => {
      ;(window as unknown as { __end: () => void }).__end()
    })
  const streamOpened = (count: number) =>
    expect
      .poll(() =>
        page.evaluate(
          () => (window as unknown as { __streams?: number }).__streams,
        ),
      )
      .toBe(count)
  const filler = (marker: string) => `${marker} ${"長い応答のテキストです。".repeat(300)}`

  await page.goto("/chat")
  await page.getByTestId("chat-input").fill("first question")
  await page.getByTestId("send-button").click()
  await streamOpened(1)

  // Following: every token leaves the log at its end.
  await push(filler("TOKEN-A"))
  await expect(log).toContainText("TOKEN-A")
  await push(filler("TOKEN-B"))
  await expect(log).toContainText("TOKEN-B")
  expect(await log.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
  await expect.poll(distance).toBeLessThanOrEqual(40)

  // Paused: a real wheel gesture holds the position against further tokens,
  // and the commit at the end of the stream does not disturb it.
  await log.hover()
  await page.mouse.wheel(0, -400)
  await expect.poll(distance).toBeGreaterThan(40)
  const held = await scrollTop()
  await push(filler("TOKEN-C"))
  await expect(log).toContainText("TOKEN-C")
  expect(await scrollTop()).toBe(held)
  await end()
  await expect(page.getByTestId("send-button")).toBeVisible()
  expect(await scrollTop()).toBe(held)

  // A new question resumes following from wherever the reader was.
  await page.getByTestId("chat-input").fill("second question")
  await page.getByTestId("send-button").click()
  await streamOpened(2)
  await push(filler("TOKEN-D"))
  await expect(log).toContainText("TOKEN-D")
  await expect.poll(distance).toBeLessThanOrEqual(40)
  await end()
  await expect(page.getByTestId("send-button")).toBeVisible()

  // A restored history opens at its end.
  await page.reload()
  await expect(log).toContainText("TOKEN-D")
  await expect.poll(distance).toBeLessThanOrEqual(40)
})

test("chat: real clipboard pastes add images and send them all (#559)", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  // Only the chat call is mocked: the paste and the upload route are real.
  let capturedBody: Record<string, unknown> | null = null
  await context.route("**/api/chat", async (route) => {
    if (route.request().method() !== "POST") {
      return route.fallback()
    }
    capturedBody = route.request().postDataJSON()
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "e2e-paste", status: "pending" }),
    })
  })
  await context.route("**/api/chat/e2e-paste/stream", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: "data: saw the image\n\n",
    })
  })

  const writeClipboard = (withText: boolean, color: string) =>
    page.evaluate(async ([text, fill]) => {
      const canvas = document.createElement("canvas")
      canvas.width = canvas.height = 8
      const ctx = canvas.getContext("2d")!
      ctx.fillStyle = fill
      ctx.fillRect(0, 0, 8, 8)
      const png = await new Promise<Blob>((resolve) =>
        canvas.toBlob((b) => resolve(b!), "image/png"),
      )
      const items: Record<string, Blob> = { "image/png": png }
      if (text) items["text/plain"] = new Blob([text], { type: "text/plain" })
      await navigator.clipboard.write([new ClipboardItem(items)])
    }, [withText ? "pasted caption" : "", color] as const)

  const input = page.getByTestId("chat-input")
  const previews = page.getByRole("img", { name: "Attached image" })
  try {
    await page.goto("/chat")

    // Plain text attaches nothing.
    await page.evaluate(() => navigator.clipboard.writeText("plain words"))
    await input.focus()
    await page.keyboard.press("ControlOrMeta+V")
    await expect(input).toHaveValue("plain words")
    await expect(previews).toHaveCount(0)

    // Image and text together: the text lands and the image attaches.
    await input.fill("")
    await writeClipboard(true, "red")
    await input.focus()
    await page.keyboard.press("ControlOrMeta+V")
    await expect(previews).toHaveCount(1)
    await expect(input).toHaveValue("pasted caption")

    // A second paste adds to the first instead of replacing it.
    await writeClipboard(false, "blue")
    await input.focus()
    await page.keyboard.press("ControlOrMeta+V")
    await expect(previews).toHaveCount(2)
    for (const img of await previews.all()) {
      await expect
        .poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth))
        .toBeGreaterThan(0)
    }

    await page.getByTestId("send-button").click()
    await expect(page.getByTestId("chat-msg-assistant")).toContainText("saw the image")
    expect(capturedBody).toMatchObject({ question: "pasted caption" })
    const paths = (capturedBody as unknown as { image_paths: string[] }).image_paths
    expect(paths).toHaveLength(2)
    expect(new Set(paths).size).toBe(2)
    for (const path of paths) expect(path).toMatch(/\.png$/)
    await expect(previews).toHaveCount(0)
  } finally {
    await context.unrouteAll({ behavior: "ignoreErrors" })
  }
})
