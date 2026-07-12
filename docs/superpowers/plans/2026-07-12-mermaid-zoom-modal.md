# mermaid 図のモーダル拡大表示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `MermaidBlock` が描画する mermaid 図をクリックすると、GitHub 風のモーダルでズーム（+/-/リセットボタン）とドラッグパンによる拡大表示ができるようにする。

**Architecture:** 新規コンポーネント `MermaidModal` が `react-zoom-pan-pinch` の `TransformWrapper`/`TransformComponent` で SVG をラップし、全画面オーバーレイとして表示する。`MermaidBlock` は成功時の SVG 表示にクリックハンドラを追加し、`isModalOpen` state で `MermaidModal` の表示を切り替える。

**Tech Stack:** Next.js (apps/web), React, `react-zoom-pan-pinch`（新規追加）, Vitest + Testing Library。

## Global Constraints

- モーダル対象は `MermaidBlock` が描画する SVG のみ。通常の Markdown 画像は対象外。
- モーダルを開く手段は図の直接クリックのみ（拡大アイコン等は追加しない）。
- モーダルを閉じる手段は ✕ ボタン・ESC キー・オーバーレイ背景クリックの3つ。
- ズーム/パン操作はボタン（+/-/リセット）とドラッグパンのみ。マウスホイールズームは明示的に無効化する（`wheel={{ disabled: true }}`）。
- モーダル表示中は `document.body` のスクロールを止める。

---

### Task 1: `react-zoom-pan-pinch` 依存追加

**Files:**
- Modify: `apps/web/package.json`

**Interfaces:**
- Consumes: なし
- Produces: `react-zoom-pan-pinch` パッケージが `apps/web` の依存として import 可能になる。

- [ ] **Step 1: パッケージを追加する**

```bash
cd apps/web && npm install react-zoom-pan-pinch
```

- [ ] **Step 2: package.json に追加されたことを確認する**

Run: `grep -n '"react-zoom-pan-pinch"' apps/web/package.json`
Expected: `"react-zoom-pan-pinch": "^<version>",` の行が出力される

- [ ] **Step 3: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json
git commit -m "chore(web): add react-zoom-pan-pinch dependency"
```

---

### Task 2: `MermaidModal` コンポーネント作成（表示・閉じる動作）

**Files:**
- Create: `apps/web/components/ui/MermaidModal.tsx`
- Test: `apps/web/tests/mermaid-modal.test.tsx`

**Interfaces:**
- Consumes: `react-zoom-pan-pinch` の `TransformWrapper`, `TransformComponent`, `useControls`（`import { TransformWrapper, TransformComponent, useControls } from "react-zoom-pan-pinch"`）
- Produces: `MermaidModal` という named export のコンポーネント。Props: `{ svg: string; onClose: () => void }`。Task 4 で `MermaidBlock.tsx` から利用する。

- [ ] **Step 1: 失敗するテストを書く（表示・✕ボタン・ESC・背景クリックで閉じる）**

`apps/web/tests/mermaid-modal.test.tsx` を新規作成:

```tsx
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MermaidModal } from "@/components/ui/MermaidModal"

const SVG = '<svg data-testid="modal-svg"><rect /></svg>'

describe("MermaidModal", () => {
  it("renders the given SVG (success)", () => {
    render(<MermaidModal svg={SVG} onClose={vi.fn()} />)
    expect(screen.getByTestId("modal-svg")).toBeInTheDocument()
  })

  it("calls onClose when the close button is clicked (success)", () => {
    const onClose = vi.fn()
    render(<MermaidModal svg={SVG} onClose={onClose} />)
    fireEvent.click(screen.getByRole("button", { name: /close/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("calls onClose when Escape is pressed (boundary)", () => {
    const onClose = vi.fn()
    render(<MermaidModal svg={SVG} onClose={onClose} />)
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("calls onClose when the overlay background is clicked, but not when the content is clicked (boundary)", () => {
    const onClose = vi.fn()
    render(<MermaidModal svg={SVG} onClose={onClose} />)

    fireEvent.click(screen.getByTestId("modal-svg"))
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId("mermaid-modal-overlay"))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `cd apps/web && npx vitest run tests/mermaid-modal.test.tsx`
Expected: FAIL（`MermaidModal` が存在しないためモジュール解決エラー）

- [ ] **Step 3: 最小実装を書く**

`apps/web/components/ui/MermaidModal.tsx` を新規作成:

```tsx
"use client"

import { useEffect } from "react"
import { TransformComponent, TransformWrapper, useControls } from "react-zoom-pan-pinch"

function ZoomControls() {
  const { zoomIn, zoomOut, resetTransform } = useControls()

  return (
    <div className="absolute bottom-4 right-4 flex flex-col gap-2">
      <button
        type="button"
        aria-label="Zoom in"
        className="rounded bg-gray-800 px-3 py-2 text-white"
        onClick={() => zoomIn()}
      >
        +
      </button>
      <button
        type="button"
        aria-label="Reset zoom"
        className="rounded bg-gray-800 px-3 py-2 text-white"
        onClick={() => resetTransform()}
      >
        ⟳
      </button>
      <button
        type="button"
        aria-label="Zoom out"
        className="rounded bg-gray-800 px-3 py-2 text-white"
        onClick={() => zoomOut()}
      >
        −
      </button>
    </div>
  )
}

export function MermaidModal({ svg, onClose }: { svg: string; onClose: () => void }) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handleKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [onClose])

  return (
    <div
      data-testid="mermaid-modal-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={onClose}
    >
      <button
        type="button"
        aria-label="Close"
        className="absolute right-4 top-4 text-2xl text-white"
        onClick={onClose}
      >
        ×
      </button>
      <div
        className="relative h-[80vh] w-[80vw] bg-gray-950"
        onClick={(e) => e.stopPropagation()}
      >
        <TransformWrapper wheel={{ disabled: true }}>
          <ZoomControls />
          <TransformComponent wrapperStyle={{ width: "100%", height: "100%" }}>
            {/* biome-ignore lint/security/noDangerouslySetInnerHtml: SVG string is generated locally by mermaid.render, not from untrusted user input rendered as HTML from the network. */}
            <div dangerouslySetInnerHTML={{ __html: svg }} />
          </TransformComponent>
        </TransformWrapper>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: テストを実行して成功を確認する**

Run: `cd apps/web && npx vitest run tests/mermaid-modal.test.tsx`
Expected: PASS（4件すべて成功）

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ui/MermaidModal.tsx apps/web/tests/mermaid-modal.test.tsx
git commit -m "feat(web): add MermaidModal with zoom/pan controls and close interactions"
```

---

### Task 3: `MermaidModal` のズームボタン動作テスト

**Files:**
- Modify: `apps/web/tests/mermaid-modal.test.tsx`

**Interfaces:**
- Consumes: Task 2 の `MermaidModal`
- Produces: なし（テストのみ追加）

- [ ] **Step 1: ズームボタンが存在し操作可能であることを確認するテストを追加する**

`apps/web/tests/mermaid-modal.test.tsx` の `describe` ブロック内に追加:

```tsx
  it("exposes zoom in, zoom out, and reset controls (success)", () => {
    render(<MermaidModal svg={SVG} onClose={vi.fn()} />)

    const zoomIn = screen.getByRole("button", { name: /zoom in/i })
    const zoomOut = screen.getByRole("button", { name: /zoom out/i })
    const reset = screen.getByRole("button", { name: /reset zoom/i })

    // Clicking should not throw and should not trigger onClose (verified
    // implicitly by the presence of the modal after interaction).
    fireEvent.click(zoomIn)
    fireEvent.click(zoomOut)
    fireEvent.click(reset)

    expect(screen.getByTestId("modal-svg")).toBeInTheDocument()
  })
```

- [ ] **Step 2: テストを実行して成功を確認する**

Run: `cd apps/web && npx vitest run tests/mermaid-modal.test.tsx`
Expected: PASS（5件すべて成功）

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/mermaid-modal.test.tsx
git commit -m "test(web): cover MermaidModal zoom control buttons"
```

---

### Task 4: `MermaidBlock` に SVG クリックでモーダルを開く動作を追加

**Files:**
- Modify: `apps/web/components/ui/MermaidBlock.tsx`
- Test: `apps/web/tests/mermaid-block.test.tsx`

**Interfaces:**
- Consumes: Task 2 の `MermaidModal`（`import { MermaidModal } from "@/components/ui/MermaidModal"`, Props: `{ svg: string; onClose: () => void }`）
- Produces: `MermaidBlock` が SVG クリックで `MermaidModal` を表示するようになる。

- [ ] **Step 1: 失敗するテストを書く**

`apps/web/tests/mermaid-block.test.tsx` の先頭 import 群の直後（`vi.mock("mermaid", ...)` の前後どちらでもよい）に以下を追加する:

```tsx
vi.mock("@/components/ui/MermaidModal", () => ({
  MermaidModal: ({ onClose }: { svg: string; onClose: () => void }) => (
    <div data-testid="mermaid-modal">
      <button type="button" onClick={onClose}>
        close
      </button>
    </div>
  ),
}))
```

続けて `describe("MermaidBlock", ...)` ブロック内に以下のテストケースを追加する（`fireEvent` を import に追加すること: `import { fireEvent, render, screen, waitFor } from "@testing-library/react"`）:

```tsx
  it("opens MermaidModal when the rendered SVG is clicked, and closes it via onClose (success)", async () => {
    renderMock.mockResolvedValueOnce({ svg: '<svg data-testid="mermaid-svg-click"></svg>' })
    render(<MermaidBlock code="flowchart TB\n  A --> B" />)

    const svgContainer = await screen.findByTestId("mermaid-svg-click")
    expect(screen.queryByTestId("mermaid-modal")).not.toBeInTheDocument()

    fireEvent.click(svgContainer)
    expect(screen.getByTestId("mermaid-modal")).toBeInTheDocument()

    fireEvent.click(screen.getByText("close"))
    expect(screen.queryByTestId("mermaid-modal")).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `cd apps/web && npx vitest run tests/mermaid-block.test.tsx`
Expected: FAIL（クリックしても `mermaid-modal` が表示されない）

- [ ] **Step 3: `MermaidBlock.tsx` を編集する**

`apps/web/components/ui/MermaidBlock.tsx` の内容を以下に置き換える:

```tsx
"use client"

import { useEffect, useId, useState } from "react"

import { MermaidModal } from "@/components/ui/MermaidModal"

type RenderState =
  | { status: "loading" }
  | { status: "success"; svg: string }
  | { status: "error"; message: string }

// mermaid.initialize() only needs to run once per page load, not per mount.
// `securityLevel: "strict"` disables raw HTML/script content in diagram
// labels so the SVG we pass to dangerouslySetInnerHTML below can't carry
// injected markup even though the diagram source ultimately comes from
// user-authored markdown.
let mermaidInitialized = false

export function MermaidBlock({ code }: { code: string }) {
  const rawId = useId()
  const elementId = `mermaid-${rawId.replace(/:/g, "")}`
  const [state, setState] = useState<RenderState>({ status: "loading" })
  const [isModalOpen, setIsModalOpen] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function run() {
      try {
        const { default: mermaid } = await import("mermaid")
        if (!mermaidInitialized) {
          mermaid.initialize({ startOnLoad: false, securityLevel: "strict" })
          mermaidInitialized = true
        }
        const { svg } = await mermaid.render(elementId, code)
        if (!cancelled) {
          setState({ status: "success", svg })
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err)
          setState({ status: "error", message })
        }
      }
    }

    void run()

    return () => {
      cancelled = true
    }
  }, [code, elementId])

  if (state.status === "loading") {
    return <div className="text-sm text-gray-500">Rendering mermaid diagram...</div>
  }

  if (state.status === "error") {
    return (
      <div className="my-2">
        <p className="text-sm text-red-600 dark:text-red-400">
          Mermaid render error: {state.message}
        </p>
        <details className="mt-1">
          <summary className="cursor-pointer text-sm text-gray-500">Show source</summary>
          <pre className="whitespace-pre-wrap text-xs">
            <code>{code}</code>
          </pre>
        </details>
      </div>
    )
  }

  return (
    <>
      {/* biome-ignore lint/security/noDangerouslySetInnerHtml: SVG string is generated locally by mermaid.render, not from untrusted user input rendered as HTML from the network. */}
      <div
        className="my-2 cursor-zoom-in"
        onClick={() => setIsModalOpen(true)}
        dangerouslySetInnerHTML={{ __html: state.svg }}
      />
      {isModalOpen && (
        <MermaidModal svg={state.svg} onClose={() => setIsModalOpen(false)} />
      )}
    </>
  )
}
```

- [ ] **Step 4: テストを実行して成功を確認する**

Run: `cd apps/web && npx vitest run tests/mermaid-block.test.tsx`
Expected: PASS（既存4件 + 新規1件すべて成功）

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ui/MermaidBlock.tsx apps/web/tests/mermaid-block.test.tsx
git commit -m "feat(web): open MermaidModal when a rendered mermaid diagram is clicked"
```

---

### Task 5: 全体テスト実行とブラウザでの手動確認

**Files:**
- なし（検証のみ）

**Interfaces:**
- Consumes: Task 1〜4 の全成果物
- Produces: なし

- [ ] **Step 1: apps/web のテストスイート全体を実行する**

Run: `cd apps/web && npm test`
Expected: 全テストが PASS

- [ ] **Step 2: `tsc --noEmit` で型エラーがないことを確認する**

Run: `cd apps/web && npx tsc --noEmit`
Expected: エラーなし

- [ ] **Step 3: 開発サーバーを起動し、Workspace 画面で mermaid 図を含む Markdown ファイルを開く**

Run: `cd apps/web && npm run dev`

期待結果: 図をクリックするとモーダルが全画面オーバーレイで開く。

- [ ] **Step 4: モーダルの各操作を確認する**

- +/-/リセットボタンで図が拡大・縮小・リセットされる
- 図をドラッグするとパン（移動）できる
- マウスホイールを回してもズームしない
- ✕ ボタンでモーダルが閉じる
- 再度開いた状態で ESC キーを押すと閉じる
- 再度開いた状態でオーバーレイの背景（図の外側）をクリックすると閉じる。図自体をクリックしても閉じない

- [ ] **Step 5: 開発サーバーを停止する**
