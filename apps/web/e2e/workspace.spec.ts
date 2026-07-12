import { expect, test } from "@playwright/test"

// The Workspace file browser: browse the sidebar tree, open a markdown file,
// edit it, save, reload, and confirm the change persisted to disk. Uses the
// isolated WORKSPACE_ROOT (e2e/.tmp-workspace) seeded in playwright.config.ts.

test.beforeEach(async ({ page }) => {
  // Pass the (main) layout onboarding guard without running the full wizard.
  const res = await page.request.put("/api/state", {
    data: { onboarded: true },
  })
  expect(res.ok()).toBeTruthy()
})

test("open, edit, save and persist a workspace file", async ({ page }) => {
  await page.goto("/workspace")

  await expect(page.getByRole("heading", { name: "Workspace" })).toBeVisible()

  // Select the seeded markdown file from the sidebar tree.
  await page.getByTestId("tree-file-readme.md").click()
  await expect(page.getByTestId("workspace-active-file")).toHaveText("readme.md")

  // Markdown opens in preview mode by default.
  await expect(page.getByTestId("markdown-view")).toContainText("Hello Workspace")

  // Switch to edit, change the content, and save.
  await page.getByTestId("workspace-mode-edit").click()
  const editor = page.getByTestId("workspace-editor")
  await editor.fill("# Hello Workspace\n\nEdited by e2e.\n")
  await page.getByTestId("workspace-save").click()
  await expect(page.getByTestId("workspace-status")).toHaveText("Saved")

  // Reload, reopen, and confirm the edit persisted.
  await page.reload()
  await page.getByTestId("tree-file-readme.md").click()
  await page.getByTestId("workspace-mode-edit").click()
  await expect(page.getByTestId("workspace-editor")).toHaveValue(/Edited by e2e\./)
})

test("the file API rejects paths outside the workspace root", async ({ page }) => {
  const res = await page.request.get("/api/workspace/file?path=../secret.md")
  expect(res.status()).toBe(400)
})
