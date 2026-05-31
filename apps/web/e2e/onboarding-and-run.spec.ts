import { expect, test } from "@playwright/test"

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
