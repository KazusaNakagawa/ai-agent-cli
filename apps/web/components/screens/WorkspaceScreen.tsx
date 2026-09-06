"use client"

import { useCallback, useEffect, useState } from "react"

import { CodeView } from "@/components/ui/CodeView"
import { LogView } from "@/components/ui/LogView"
import { MarkdownView } from "@/components/ui/MarkdownView"
import {
  isBinaryFile,
  isImageFile,
  isLogFile,
  isPdfFile,
  languageForFile,
} from "@/lib/fileColors"
import {
  readFileHandle,
  readFileHandleAsObjectURL,
  resolveWorkspaceLink,
  writeFileHandle,
} from "@/lib/fsAccess"
import { useWorkspaceState } from "@/lib/workspaceStore"

type Mode = "edit" | "preview"

function isMarkdown(path: string): boolean {
  return /\.(md|markdown)$/i.test(path)
}

function defaultModeFor(path: string): Mode {
  return isMarkdown(path) || isLogFile(path) || languageForFile(path) !== null
    ? "preview"
    : "edit"
}

export function WorkspaceScreen() {
  const { selected, fileIndex, selectFile } = useWorkspaceState()
  const [content, setContent] = useState<string>("")
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>("edit")

  const path = selected?.path ?? null
  const isImage = path !== null && isImageFile(path)
  const isPdf = path !== null && isPdfFile(path)
  // Any binary: images and PDFs have viewers, the rest have none. Decoding one
  // as text yields mojibake, and saving that back would overwrite the file with
  // it — so the whole edit/save affordance is withheld for all of them.
  const isBinary = path !== null && isBinaryFile(path)

  // Load the selected file whenever the sidebar selection changes. Images and
  // PDFs load as an object URL for <img>/<iframe>; other binaries are not read
  // at all; everything else loads as text.
  useEffect(() => {
    if (selected === null) return
    let cancelled = false
    let objectUrl: string | null = null
    setStatus(null)
    setLoading(true)
    setMode(defaultModeFor(selected.path))

    const viewableBinary =
      isImageFile(selected.path) || isPdfFile(selected.path)

    const load = viewableBinary
      ? readFileHandleAsObjectURL(selected.handle).then((url) => {
          if (cancelled) {
            URL.revokeObjectURL(url)
            return
          }
          objectUrl = url
          setBlobUrl(url)
        })
      : isBinaryFile(selected.path)
        ? Promise.resolve().then(() => {
            if (!cancelled) {
              setContent("")
              setBlobUrl(null)
            }
          })
        : readFileHandle(selected.handle).then((text) => {
            if (!cancelled) {
              setContent(text)
              setBlobUrl(null)
            }
          })

    load
      .catch((e) => {
        if (!cancelled) setStatus(e instanceof Error ? e.message : "failed to load")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      if (objectUrl !== null) URL.revokeObjectURL(objectUrl)
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

  const language = path !== null ? languageForFile(path) : null

  // Intercept relative markdown links (./other.md, ../dir/other.md) and switch
  // the Workspace selection to the matching indexed file instead of letting
  // the browser try to navigate a route that doesn't exist. Absolute URLs,
  // other schemes, and links to files outside the indexed set fall through to
  // MarkdownView's default target=_blank behavior.
  const handleLinkClick = useCallback(
    (href: string): boolean => {
      if (path === null) return false
      const resolved = resolveWorkspaceLink(href, path)
      if (resolved === null) return false
      const match = fileIndex.find((f) => f.path === resolved)
      if (match === undefined) return false
      selectFile({ handle: match.handle, path: match.path })
      return true
    },
    [path, fileIndex, selectFile],
  )

  return (
    <div className="flex h-[calc(100vh-12rem)]">
      {/* Editor + preview. The file tree lives in the global sidebar rail. */}
      <section className="flex min-w-0 flex-1 flex-col rounded border">
        <header className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
          <span className="truncate text-sm font-medium" data-testid="workspace-active-file">
            {path ?? "No file selected"}
          </span>
          {!isBinary && (
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
          )}
        </header>

        <div className="min-h-0 flex-1 overflow-auto p-3">
          {path === null ? (
            <p className="text-sm text-muted-foreground">
              Open a folder and select a file from the sidebar to edit or preview.
            </p>
          ) : loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : isImage ? (
            blobUrl !== null ? (
              // eslint-disable-next-line @next/next/no-img-element -- local blob: URL, not a Next-optimizable remote asset
              <img
                src={blobUrl}
                alt={path}
                className="max-h-full max-w-full object-contain"
                data-testid="workspace-image"
              />
            ) : null
          ) : isPdf ? (
            blobUrl !== null ? (
              <iframe
                src={blobUrl}
                title={path}
                className="h-full w-full border-0"
                data-testid="workspace-pdf"
              />
            ) : null
          ) : isBinary ? (
            <p className="text-sm text-muted-foreground" data-testid="workspace-binary-notice">
              Binary file — no preview available. Opening it as text would show
              mojibake, and saving that back would corrupt the file.
            </p>
          ) : mode === "preview" && isMarkdown(path) ? (
            <MarkdownView content={content} onLinkClick={handleLinkClick} />
          ) : mode === "preview" && isLogFile(path) ? (
            <LogView content={content} />
          ) : mode === "preview" && language !== null ? (
            <CodeView content={content} language={language} />
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
