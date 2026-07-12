# Workspace mermaid レンダリング対応 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Workspace（および Briefing/Journal/Chat が共用する `MarkdownView`）で ```mermaid コードフェンスを実際の図としてレンダリングできるようにする。

**Architecture:** `mermaid` パッケージをクライアントサイドで動的 import し、新規コンポーネント `MermaidBlock` が `mermaid.render()` を呼び出して SVG を描画する。`MarkdownView` の `code` コンポーネントをオーバーライドし、`className` が `language-mermaid` のときだけ `MermaidBlock` に処理を委譲する。それ以外の言語・インラインコードは既存のデフォルト表示を維持する。

**Tech Stack:** Next.js (apps/web), React, react-markdown v10, mermaid (新規追加), Vitest + Testing Library。

## Global Constraints

- 対応範囲は `MarkdownView.tsx` 共通コンポーネント全体（Workspace/Briefing/Journal/Chat すべて）。Workspace 限定の分岐は作らない。
- レンダリングはクライアントサイドの `mermaid.js` 動的レンダリングのみ。SSR/Puppeteer系のビルド時レンダリングは採用しない。
- mermaid 構文エラー時は、エラーメッセージを表示し、かつ元のコードを `<details>` で折りたたみ表示して確認可能にする（非表示にしない）。
- `rehypeSanitize`(`sanitizeSchema`, `apps/web/lib/briefing-toc.ts`) の `defaultSchema` は `code` 要素の `language-*` クラスを標準で許可しており、スキーマ変更は不要（変更しないこと）。
- ダークモードのmermaidテーマ切り替えやPlantUML等の他記法対応はスコープ外。

---

### Task 1: `mermaid` 依存追加

**Files:**
- Modify: `apps/web/package.json`

**Interfaces:**
- Consumes: なし
- Produces: `mermaid` パッケージが `apps/web` の依存として `import`/`require` 可能になる。

- [ ] **Step 1: パッケージを追加する**

```bash
cd apps/web && npm install mermaid
```

- [ ] **Step 2: package.json に `mermaid` が dependencies に追加されたことを確認する**

Run: `grep -n '"mermaid"' apps/web/package.json`
Expected: `"mermaid": "^<version>",` の行が出力される

- [ ] **Step 3: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json
git commit -m "chore(web): add mermaid dependency"
```

---

### Task 2: `MermaidBlock` コンポーネント作成（正常系）

**Files:**
- Create: `apps/web/components/ui/MermaidBlock.tsx`
- Test: `apps/web/tests/mermaid-block.test.tsx`

**Interfaces:**
- Consumes: `mermaid`（Task 1 で追加した npm パッケージ）の `mermaid.render(id: string, code: string): Promise<{ svg: string }>` API（デフォルトエクスポートの `mermaid` オブジェクトを動的 `import("mermaid")` で取得する）
- Produces: `MermaidBlock` という named export のコンポーネント。Props: `{ code: string }`。Task 3 で `MarkdownView.tsx` から利用する。

- [ ] **Step 1: 失敗するテストを書く（正常系: SVGが描画される）**

`apps/web/tests/mermaid-block.test.tsx` を新規作成:

```tsx
import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MermaidBlock } from "@/components/ui/MermaidBlock"

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (id: string) => ({
      svg: `<svg data-testid="mermaid-svg" id="${id}"></svg>`,
    })),
  },
}))

describe("MermaidBlock", () => {
  it("renders the SVG produced by mermaid.render (success)", async () => {
    render(<MermaidBlock code="flowchart TB\n  A --> B" />)

    await waitFor(() => {
      expect(screen.getByTestId("mermaid-svg")).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `cd apps/web && npx vitest run tests/mermaid-block.test.tsx`
Expected: FAIL（`MermaidBlock` が存在しないためモジュール解決エラー）

- [ ] **Step 3: 最小実装を書く**

`apps/web/components/ui/MermaidBlock.tsx` を新規作成:

```tsx
"use client"

import { useEffect, useId, useState } from "react"

type RenderState =
  | { status: "loading" }
  | { status: "success"; svg: string }
  | { status: "error"; message: string }

export function MermaidBlock({ code }: { code: string }) {
  const rawId = useId()
  const elementId = `mermaid-${rawId.replace(/:/g, "")}`
  const [state, setState] = useState<RenderState>({ status: "loading" })

  useEffect(() => {
    let cancelled = false

    async function run() {
      try {
        const { default: mermaid } = await import("mermaid")
        mermaid.initialize({ startOnLoad: false })
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

  // biome-ignore lint/security/noDangerouslySetInnerHtml: SVG string is generated locally by mermaid.render, not from untrusted user input rendered as HTML from the network.
  return <div className="my-2" dangerouslySetInnerHTML={{ __html: state.svg }} />
}
```

- [ ] **Step 4: テストを実行して成功を確認する**

Run: `cd apps/web && npx vitest run tests/mermaid-block.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ui/MermaidBlock.tsx apps/web/tests/mermaid-block.test.tsx
git commit -m "feat(web): add MermaidBlock component for client-side mermaid rendering"
```

---

### Task 3: `MermaidBlock` のエラー系テスト追加

**Files:**
- Modify: `apps/web/tests/mermaid-block.test.tsx`

**Interfaces:**
- Consumes: Task 2 の `MermaidBlock`（Props: `{ code: string }`）
- Produces: なし（テストのみ追加）

- [ ] **Step 1: 失敗するテストを追加する（異常系: 構文エラー時にメッセージと折りたたみコードが表示される）**

`apps/web/tests/mermaid-block.test.tsx` の `vi.mock("mermaid", ...)` を、テストごとに挙動を切り替えられるように書き換え、テストケースを追加する:

```tsx
import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MermaidBlock } from "@/components/ui/MermaidBlock"

const renderMock = vi.fn()

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: (...args: unknown[]) => renderMock(...args),
  },
}))

describe("MermaidBlock", () => {
  it("renders the SVG produced by mermaid.render (success)", async () => {
    renderMock.mockResolvedValueOnce({ svg: '<svg data-testid="mermaid-svg"></svg>' })
    render(<MermaidBlock code="flowchart TB\n  A --> B" />)

    await waitFor(() => {
      expect(screen.getByTestId("mermaid-svg")).toBeInTheDocument()
    })
  })

  it("shows an error message and a collapsible source block on invalid mermaid syntax (failure)", async () => {
    renderMock.mockRejectedValueOnce(new Error("Parse error on line 1"))
    render(<MermaidBlock code="not a valid diagram" />)

    await waitFor(() => {
      expect(screen.getByText(/Mermaid render error: Parse error on line 1/)).toBeInTheDocument()
    })
    expect(screen.getByText("Show source")).toBeInTheDocument()
    expect(screen.getByText("not a valid diagram")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: テストを実行して新規ケースが通ることを確認する**

Run: `cd apps/web && npx vitest run tests/mermaid-block.test.tsx`
Expected: PASS（2件とも成功。Step 1 の書き換えで既存の成功系テストも `renderMock` 経由になっている点に注意）

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/mermaid-block.test.tsx
git commit -m "test(web): cover MermaidBlock error path"
```

---

### Task 4: `MarkdownView` に mermaid 分岐を追加

**Files:**
- Modify: `apps/web/components/ui/MarkdownView.tsx`
- Modify: `apps/web/tests/markdown-view.test.tsx`

**Interfaces:**
- Consumes: Task 2 の `MermaidBlock`（`import { MermaidBlock } from "@/components/ui/MermaidBlock"`, Props: `{ code: string }`）
- Produces: `MarkdownView` が ```mermaid フェンスを `MermaidBlock` 経由でレンダリングするようになる。他画面（Workspace/Briefing/Journal/Chat）はコード変更不要でこの挙動を継承する。

- [ ] **Step 1: 失敗するテストを書く**

`apps/web/tests/markdown-view.test.tsx` の `describe("MarkdownView", ...)` ブロック内に以下を追加する（先頭の import に `vi` は既存で使用済み。`MermaidBlock` を mock する）:

```tsx
vi.mock("@/components/ui/MermaidBlock", () => ({
  MermaidBlock: ({ code }: { code: string }) => (
    <div data-testid="mermaid-block">{code}</div>
  ),
}))
```

を `describe` ブロックの外、既存の `import` の直後に追加し、続けて次のテストケースを `describe` ブロック内に追加する:

```tsx
  it("delegates ```mermaid fenced code blocks to MermaidBlock (boundary)", () => {
    render(<MarkdownView content={"```mermaid\nflowchart TB\n  A --> B\n```"} />)

    const block = screen.getByTestId("mermaid-block")
    expect(block).toHaveTextContent("flowchart TB")
    expect(block).toHaveTextContent("A --> B")
  })

  it("renders non-mermaid fenced code blocks as plain code, not MermaidBlock (boundary)", () => {
    render(<MarkdownView content={"```ts\nconst a = 1\n```"} />)

    expect(screen.queryByTestId("mermaid-block")).not.toBeInTheDocument()
    expect(screen.getByText("const a = 1")).toBeInTheDocument()
  })
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `cd apps/web && npx vitest run tests/markdown-view.test.tsx`
Expected: FAIL（1件目のテストで `mermaid-block` の testid が見つからない）

- [ ] **Step 3: `MarkdownView.tsx` に `code` コンポーネントのオーバーライドを実装する**

`apps/web/components/ui/MarkdownView.tsx` を編集する:

```tsx
import type React from "react"
import { useMemo } from "react"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"

import { sanitizeSchema } from "@/lib/briefing-toc"
import { MermaidBlock } from "@/components/ui/MermaidBlock"

// Shared markdown renderer. Same plugin stack (GFM + sanitize) and prose styling
// used by the Briefing panel, extracted so other screens (Workspace preview)
// render markdown identically.
const PROSE_CLASS =
  "prose prose-sm max-w-none dark:prose-invert " +
  "prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline dark:prose-a:text-blue-400"

// `onLinkClick` lets a caller (e.g. Workspace) intercept a link's href before
// the browser navigates it. Returning true means the caller handled it (e.g.
// switched to another open file) and default navigation is suppressed;
// returning false (or omitting the prop) keeps the normal target=_blank open.
type LinkHandler = (href: string) => boolean

function extractText(children: React.ReactNode): string {
  if (typeof children === "string") return children
  if (Array.isArray(children)) return children.map(extractText).join("")
  return ""
}

function makeMarkdownComponents(onLinkClick?: LinkHandler) {
  return {
    a: ({ children, href, ...props }: React.ComponentPropsWithoutRef<"a">) => (
      <a
        {...props}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => {
          // Let modified clicks (middle-click, cmd/ctrl/shift-click) through
          // untouched so users can still open the link in a new tab/window.
          if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
            return
          }
          if (href !== undefined && (onLinkClick?.(href) ?? false)) {
            e.preventDefault()
          }
        }}
      >
        {children}
      </a>
    ),
    code: ({ className, children, ...props }: React.ComponentPropsWithoutRef<"code">) => {
      if (className === "language-mermaid") {
        return <MermaidBlock code={extractText(children).replace(/\n$/, "")} />
      }
      return (
        <code className={className} {...props}>
          {children}
        </code>
      )
    },
  }
}

export function MarkdownView({
  content,
  onLinkClick,
}: {
  content: string
  onLinkClick?: LinkHandler
}) {
  const components = useMemo(
    () => makeMarkdownComponents(onLinkClick),
    [onLinkClick],
  )
  return (
    <div className={PROSE_CLASS} data-testid="markdown-view">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
```

- [ ] **Step 4: テストを実行して成功を確認する**

Run: `cd apps/web && npx vitest run tests/markdown-view.test.tsx`
Expected: PASS（既存4件 + 新規2件すべて成功）

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ui/MarkdownView.tsx apps/web/tests/markdown-view.test.tsx
git commit -m "feat(web): render mermaid fenced code blocks via MermaidBlock in MarkdownView"
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
Expected: 全テストが PASS（既存テストにリグレッションがないこと、Task 2〜4 の新規テストが含まれること）

- [ ] **Step 2: 開発サーバーを起動する**

Run: `cd apps/web && npm run dev`

- [ ] **Step 3: ブラウザで Workspace 画面を開き、`articles/article11_rag.md`（またはmermaidブロックを含む任意のMarkdownファイル）のプレビューを確認する**

期待結果: ```mermaid ブロックがコードテキストではなく実際のフローチャート図としてレンダリングされる。

- [ ] **Step 4: 意図的に不正な mermaid コードを含む一時的な Markdown ファイルをWorkspaceで作成し、エラー表示を確認する**

例: `flowchart TB\n  A --->> B` のような不正構文を含むファイルを開き、赤色のエラーメッセージと "Show source" の折りたたみが表示されることを確認する。確認後、このファイルは削除する。

- [ ] **Step 5: 開発サーバーを停止する**
