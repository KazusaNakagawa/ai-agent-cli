"use client"
import { useEffect, useRef, useState } from "react"

import { BriefingPanel } from "@/components/briefing/BriefingPanel"
import { ChatForm } from "@/components/screens/ChatForm"
import { ResizeHandle } from "@/components/ResizeHandle"
import { Button } from "@/components/ui/button"
import { useBriefingData } from "@/lib/hooks/useBriefingData"
import { useResizable } from "@/lib/hooks/useResizable"
import { cn } from "@/lib/utils"

const WIDTH_STORAGE_KEY = "ai-agent:chat-split-width:v1"
const DEFAULT_WIDTH = 480
const MIN_WIDTH = 320
const MAX_WIDTH = 880

/**
 * Two-pane Q&A screen: the conversation on the left, the generated briefing
 * document on the right, so follow-up questions can be asked while reading the
 * output.
 *
 * Both panes scroll independently and the container never scrolls — the host
 * must give this component a definite height. Below `lg` the panes collapse to
 * a single column and the header toggle picks which one is on screen.
 */
export function ChatSplitView() {
  const { files, selected, content, loadingContent, listError, contentError, fetchContent } =
    useBriefingData()
  const { width, startResize } = useResizable({
    storageKey: WIDTH_STORAGE_KEY,
    defaultWidth: DEFAULT_WIDTH,
    minWidth: MIN_WIDTH,
    maxWidth: MAX_WIDTH,
    edge: "left",
  })
  // Narrow-viewport only: which of the two panes is on screen. Q&A wins by
  // default so the screen still opens on its primary purpose.
  const [docOnTop, setDocOnTop] = useState(false)

  // Open the newest document once the list arrives. Guarded by a ref so a later
  // manual pick isn't clobbered when `files` identity changes.
  const autoOpened = useRef(false)
  useEffect(() => {
    if (autoOpened.current) return
    if (files === null || files.length === 0) return
    autoOpened.current = true
    fetchContent(files[0])
  }, [files, fetchContent])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex justify-end pb-2 lg:hidden">
        <Button
          type="button"
          variant="outline"
          size="sm"
          data-testid="chat-doc-toggle"
          onClick={() => setDocOnTop((v) => !v)}
        >
          {docOnTop ? "Back to Q&A" : "Show document"}
        </Button>
      </div>

      <div data-testid="chat-split-view" className="flex min-h-0 flex-1">
        {/* Q&A pane */}
        <div
          data-testid="chat-pane-qa"
          className={cn(
            "flex min-h-0 min-w-0 flex-1 flex-col pr-0 lg:pr-4",
            docOnTop && "hidden lg:flex",
          )}
        >
          <ChatForm fill />
        </div>

        {/* Document pane — fixed (resizable) width from `lg` up, full width below */}
        <div
          data-testid="chat-pane-doc"
          style={{ "--doc-width": `${width}px` } as React.CSSProperties}
          className={cn(
            "relative flex min-h-0 w-full min-w-0 flex-1 flex-col",
            "lg:w-[length:var(--doc-width)] lg:flex-none",
            !docOnTop && "hidden lg:flex",
          )}
        >
          <ResizeHandle
            onPointerDown={startResize}
            edge="left"
            ariaLabel="Resize document pane"
            data-testid="chat-split-resizer"
            className="hidden lg:block"
          />
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border">
            {files !== null && files.length > 0 && (
              <div className="flex items-center gap-2 border-b px-3 py-2">
                <label htmlFor="chat-doc-picker" className="text-xs text-muted-foreground">
                  Document
                </label>
                <select
                  id="chat-doc-picker"
                  data-testid="chat-doc-picker"
                  value={selected?.name ?? ""}
                  onChange={(e) => {
                    const file = files.find((f) => f.name === e.target.value)
                    if (file) fetchContent(file)
                  }}
                  className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-xs"
                >
                  {files.map((file) => (
                    <option key={file.name} value={file.name}>
                      {file.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="min-h-0 flex-1 overflow-hidden">
              <DocumentBody
                listError={listError}
                loadingList={files === null}
                selected={selected}
                content={content}
                loadingContent={loadingContent}
                contentError={contentError}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

type DocumentBodyProps = {
  listError: string | null
  loadingList: boolean
  selected: ReturnType<typeof useBriefingData>["selected"]
  content: string | null
  loadingContent: boolean
  contentError: string | null
}

function DocumentBody({
  listError,
  loadingList,
  selected,
  content,
  loadingContent,
  contentError,
}: DocumentBodyProps) {
  if (listError !== null) {
    return (
      <p data-testid="chat-doc-error" className="p-4 text-sm text-destructive">
        Failed to load documents: {listError}
      </p>
    )
  }
  if (loadingList) {
    return (
      <p data-testid="chat-doc-loading" className="p-4 text-sm text-muted-foreground">
        Loading documents…
      </p>
    )
  }
  if (selected === null) {
    return (
      <p data-testid="chat-doc-empty" className="p-4 text-sm text-muted-foreground">
        No briefing document to show yet. Run a briefing, then pick it here to read it
        alongside the conversation.
      </p>
    )
  }
  return (
    <BriefingPanel
      file={selected}
      content={content}
      loading={loadingContent}
      error={contentError}
    />
  )
}
