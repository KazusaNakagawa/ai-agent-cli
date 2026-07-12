"use client"

import { useCallback, useEffect, useState } from "react"

import { MarkdownView } from "@/components/ui/MarkdownView"
import { readFileHandle, writeFileHandle } from "@/lib/fsAccess"
import { useWorkspaceState } from "@/lib/workspaceStore"

type Mode = "edit" | "preview"

function isMarkdown(path: string): boolean {
  return /\.(md|markdown)$/i.test(path)
}

export function WorkspaceScreen() {
  const { selected } = useWorkspaceState()
  const [content, setContent] = useState<string>("")
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>("edit")

  // Load the selected file's content whenever the sidebar selection changes.
  useEffect(() => {
    if (selected === null) return
    let cancelled = false
    setStatus(null)
    setLoading(true)
    setMode(isMarkdown(selected.path) ? "preview" : "edit")
    readFileHandle(selected.handle)
      .then((text) => {
        if (!cancelled) setContent(text)
      })
      .catch((e) => {
        if (!cancelled) {
          setStatus(e instanceof Error ? e.message : "failed to load")
          setContent("")
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selected])

  const save = useCallback(async () => {
    if (selected === null) return
    setSaving(true)
    setStatus(null)
    try {
      await writeFileHandle(selected.handle, content)
      setStatus("Saved")
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "failed to save")
    } finally {
      setSaving(false)
    }
  }, [selected, content])

  const path = selected?.path ?? null

  return (
    <div className="flex h-[calc(100vh-12rem)]">
      {/* Editor + preview. The file tree lives in the global sidebar rail. */}
      <section className="flex min-w-0 flex-1 flex-col rounded border">
        <header className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
          <span className="truncate text-sm font-medium" data-testid="workspace-active-file">
            {path ?? "No file selected"}
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
                disabled={path === null}
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => setMode("preview")}
                className={`px-2 py-1 ${mode === "preview" ? "bg-accent font-medium" : ""}`}
                data-testid="workspace-mode-preview"
                disabled={path === null}
              >
                Preview
              </button>
            </div>
            <button
              type="button"
              onClick={save}
              disabled={path === null || saving}
              className="rounded bg-primary px-2 py-1 text-xs text-primary-foreground disabled:opacity-50"
              data-testid="workspace-save"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-auto p-3">
          {path === null ? (
            <p className="text-sm text-muted-foreground">
              Open a folder and select a file from the sidebar to edit or preview.
            </p>
          ) : loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : mode === "preview" && isMarkdown(path) ? (
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
