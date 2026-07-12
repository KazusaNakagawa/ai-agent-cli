"use client"

import { useCallback, useState } from "react"

import { FileTree } from "@/components/workspace/FileTree"
import { MarkdownView } from "@/components/ui/MarkdownView"

type Mode = "edit" | "preview"

function isMarkdown(path: string): boolean {
  return /\.(md|markdown)$/i.test(path)
}

export function WorkspaceScreen() {
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [content, setContent] = useState<string>("")
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>("edit")

  const openFile = useCallback(async (path: string) => {
    setSelectedPath(path)
    setStatus(null)
    setLoading(true)
    setMode(isMarkdown(path) ? "preview" : "edit")
    try {
      const res = await fetch(`/api/workspace/file?path=${encodeURIComponent(path)}`)
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string }
        throw new Error(body.error ?? `HTTP ${res.status}`)
      }
      const data = (await res.json()) as { content: string }
      setContent(data.content)
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "failed to load")
      setContent("")
    } finally {
      setLoading(false)
    }
  }, [])

  const save = useCallback(async () => {
    if (selectedPath === null) return
    setSaving(true)
    setStatus(null)
    try {
      const res = await fetch(`/api/workspace/file?path=${encodeURIComponent(selectedPath)}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content }),
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string }
        throw new Error(body.error ?? `HTTP ${res.status}`)
      }
      setStatus("Saved")
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "failed to save")
    } finally {
      setSaving(false)
    }
  }, [selectedPath, content])

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-3">
      {/* Left sidebar: file tree */}
      <aside
        className="w-64 flex-shrink-0 overflow-y-auto rounded border bg-muted/30 p-1"
        data-testid="workspace-sidebar"
      >
        <FileTree selectedPath={selectedPath} onSelectFile={openFile} />
      </aside>

      {/* Editor + preview */}
      <section className="flex min-w-0 flex-1 flex-col rounded border">
        <header className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
          <span className="truncate text-sm font-medium" data-testid="workspace-active-file">
            {selectedPath ?? "No file selected"}
          </span>
          <div className="flex items-center gap-2">
            {status !== null ? (
              <span className="text-xs text-muted-foreground" data-testid="workspace-status">
                {status}
              </span>
            ) : null}
            <div className="flex overflow-hidden rounded border text-xs">
              <button
                type="button"
                onClick={() => setMode("edit")}
                className={`px-2 py-1 ${mode === "edit" ? "bg-accent font-medium" : ""}`}
                data-testid="workspace-mode-edit"
                disabled={selectedPath === null}
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => setMode("preview")}
                className={`px-2 py-1 ${mode === "preview" ? "bg-accent font-medium" : ""}`}
                data-testid="workspace-mode-preview"
                disabled={selectedPath === null}
              >
                Preview
              </button>
            </div>
            <button
              type="button"
              onClick={save}
              disabled={selectedPath === null || saving}
              className="rounded bg-primary px-2 py-1 text-xs text-primary-foreground disabled:opacity-50"
              data-testid="workspace-save"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-auto p-3">
          {selectedPath === null ? (
            <p className="text-sm text-muted-foreground">
              Select a file from the sidebar to edit or preview.
            </p>
          ) : loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : mode === "preview" && isMarkdown(selectedPath) ? (
            <MarkdownView content={content} />
          ) : (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="h-full w-full resize-none rounded border bg-background p-2 font-mono text-sm"
              spellCheck={false}
              data-testid="workspace-editor"
            />
          )}
        </div>
      </section>
    </div>
  )
}
