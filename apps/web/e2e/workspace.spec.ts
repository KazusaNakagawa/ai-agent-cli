import { expect, test } from "@playwright/test"

// The File System Access API's folder picker is a native OS dialog Playwright
// cannot drive. We stub `window.showDirectoryPicker` with an in-memory fake
// directory tree before each test, so the app's tree/search/edit logic runs
// against something that behaves like a real handle (values(), getFile(),
// createWritable(), queryPermission/requestPermission) without a real dialog.
const FAKE_TREE = {
  name: "demo-repo",
  files: { "readme.md": "# Demo\n\nHello.\n" },
  dirs: [
    {
      name: "src",
      files: { "app.py": "def handler():\n    return 1\n" },
      dirs: [],
    },
  ],
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript((tree) => {
    class FakeFileHandle {
      kind = "file" as const
      name: string
      private content: string
      constructor(name: string, content: string) {
        this.name = name
        this.content = content
      }
      async getFile() {
        return new File([this.content], this.name)
      }
      async createWritable() {
        return {
          write: async (data: string) => {
            this.content = data
          },
          close: async () => {},
        }
      }
      async queryPermission() {
        return "granted"
      }
      async requestPermission() {
        return "granted"
      }
    }

    class FakeDirHandle {
      kind = "directory" as const
      name: string
      private children: (FakeFileHandle | FakeDirHandle)[]
      constructor(name: string, children: (FakeFileHandle | FakeDirHandle)[]) {
        this.name = name
        this.children = children
      }
      async *values() {
        for (const c of this.children) yield c
      }
      async queryPermission() {
        return "granted"
      }
      async requestPermission() {
        return "granted"
      }
    }

    type TreeNode = {
      name: string
      files?: Record<string, string>
      dirs?: TreeNode[]
    }

    function buildDir(node: TreeNode): FakeDirHandle {
      const children: (FakeFileHandle | FakeDirHandle)[] = []
      for (const [name, content] of Object.entries(node.files ?? {})) {
        children.push(new FakeFileHandle(name, content))
      }
      for (const dir of node.dirs ?? []) {
        children.push(buildDir(dir))
      }
      return new FakeDirHandle(node.name, children)
    }

    const root = buildDir(tree as TreeNode)
    // @ts-expect-error -- test-only stub; real signature returns a live handle
    window.showDirectoryPicker = async () => root
  }, FAKE_TREE)

  const res = await page.request.put("/api/state", { data: { onboarded: true } })
  expect(res.ok()).toBeTruthy()
})

test("open a folder, expand/collapse all, fuzzy search, edit and save", async ({
  page,
}) => {
  await page.goto("/workspace")

  await page.getByTestId("workspace-open-folder").click()

  await expect(page.getByTestId("tree-dir-src")).toBeVisible()
  await expect(page.getByTestId("tree-file-readme.md")).toBeVisible()
  await expect(page.getByTestId("tree-file-src/app.py")).toBeHidden()

  // Expand all cascades into the nested "src" directory.
  await page.getByTestId("workspace-expand-all").click()
  await expect(page.getByTestId("tree-file-src/app.py")).toBeVisible()

  // Collapse all folds it back up.
  await page.getByTestId("workspace-collapse-all").click()
  await expect(page.getByTestId("tree-file-src/app.py")).toBeHidden()

  // Fuzzy search finds and opens the nested file without manual tree expansion.
  await page.getByTestId("workspace-search-input").fill("app")
  await page.getByTestId("workspace-search-result-src/app.py").click()
  await expect(page.getByTestId("workspace-active-file")).toHaveText("src/app.py")

  // Code preview renders the file's syntax-highlighted content by default.
  await expect(page.getByTestId("code-view")).toContainText("def handler")

  // Edit + save writes back through the fake handle.
  await page.getByTestId("workspace-mode-edit").click()
  await page.getByTestId("workspace-editor").fill("def handler():\n    return 2\n")
  await page.getByTestId("workspace-save").click()
  await expect(page.getByTestId("workspace-status")).toHaveText("Saved")
})

test("markdown opens in preview mode with rendered content", async ({ page }) => {
  await page.goto("/workspace")
  await page.getByTestId("workspace-open-folder").click()

  await page.getByTestId("tree-file-readme.md").click()
  await expect(page.getByTestId("workspace-active-file")).toHaveText("readme.md")
  await expect(page.getByTestId("markdown-view")).toContainText("Demo")
})
