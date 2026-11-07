"use client"
import { ArrowUp, Mic, Square } from "lucide-react"
import { useEffect, useRef, type KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"
import { useImageAttachments } from "@/lib/hooks/useImageAttachments"
import { insertAtCursor } from "@/lib/insertAtCursor"
import { cn } from "@/lib/utils"

const MIN_TEXTAREA_HEIGHT_PX = 40
const MAX_TEXTAREA_HEIGHT_PX = 200

function resizeTextarea(el: HTMLTextAreaElement) {
  el.style.height = "auto"
  const next = Math.min(
    Math.max(el.scrollHeight, MIN_TEXTAREA_HEIGHT_PX),
    MAX_TEXTAREA_HEIGHT_PX,
  )
  el.style.height = `${next}px`
  el.style.overflowY = el.scrollHeight > MAX_TEXTAREA_HEIGHT_PX ? "auto" : "hidden"
}

type Props = {
  input: string
  setInput: (value: string) => void
  busy: boolean
  supportsMic: boolean
  listening: boolean
  onToggleMic: (prefix: string) => void
  onSend: (imagePaths: string[]) => void
  onCancel: () => void
  onHistoryKeyDown?: (e: KeyboardEvent<HTMLTextAreaElement>) => void
  /** The cross-date history toggle renders only when its handler is given. */
  searchHistory?: boolean
  onToggleSearchHistory?: (value: boolean) => void
  placeholder?: string
  /** Accessible name of the round send button. */
  sendLabel?: string
  cancelLabel?: string
}

export function ChatComposer({
  input,
  setInput,
  busy,
  supportsMic,
  listening,
  onToggleMic,
  onSend,
  onCancel,
  onHistoryKeyDown,
  searchHistory = false,
  onToggleSearchHistory,
  placeholder = "Ask about today's briefing…",
  sendLabel = "Send",
  cancelLabel = "Cancel",
}: Props) {
  const composingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const {
    images: attachedImages,
    attach: attachImage,
    remove: removeImage,
    take: takeImages,
    error: attachError,
    isDragging,
    uploading,
    onPickerUploadingChange,
  } = useImageAttachments(textareaRef)

  // Covers height updates from sources other than direct typing (history
  // recall via Up/Down, mic dictation, drag-and-drop file insert), which set
  // `input` without going through the textarea's own onChange.
  useEffect(() => {
    if (textareaRef.current) resizeTextarea(textareaRef.current)
  }, [input])

  function handleSend() {
    // Guard the keyboard path: ChatForm.send no-ops on empty input, so without
    // this the Enter key would clear the attachment without ever sending it.
    // Sending mid-upload would lose the image from this message and leave it
    // attached to the next one.
    if (input.trim().length === 0 || uploading) return
    onSend(takeImages())
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-1">
      <div
        className={cn(
          "rounded-3xl border bg-card shadow-sm",
          isDragging && "ring-2 ring-primary",
        )}
      >
        <div className="px-3 pt-3">
          <textarea
            ref={textareaRef}
            aria-label="Chat message"
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              resizeTextarea(e.target)
            }}
            onCompositionStart={() => {
              composingRef.current = true
            }}
            onCompositionEnd={() => {
              composingRef.current = false
            }}
            onKeyDown={(e) => {
              if (composingRef.current || e.nativeEvent.isComposing) return
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSend()
                return
              }
              onHistoryKeyDown?.(e)
            }}
            placeholder={placeholder}
            rows={2}
            className="w-full resize-none overflow-hidden bg-transparent px-1 text-sm outline-none placeholder:text-muted-foreground"
            data-testid="chat-input"
          />
        </div>
        <div className="flex items-center gap-1 px-2 pb-2">
          <ImageAttachArea
            attachedImages={attachedImages}
            onAttach={attachImage}
            onRemove={removeImage}
            onUploadingChange={onPickerUploadingChange}
            disabled={busy}
            isDragging={isDragging}
            onInsertFile={(markdown) =>
              setInput(insertAtCursor(textareaRef.current, input, markdown))
            }
          />
          {supportsMic && (
            <Button
              type="button"
              variant={listening ? "destructive" : "ghost"}
              size="icon"
              className="rounded-full"
              onClick={() => onToggleMic(input)}
              data-testid="mic-button"
              aria-label={listening ? "音声入力停止" : "音声入力開始"}
              aria-pressed={listening}
              title={listening ? "音声入力停止" : "音声入力開始 (ja-JP)"}
            >
              {listening ? <Square aria-hidden className="h-4 w-4" /> : <Mic aria-hidden className="h-4 w-4" />}
            </Button>
          )}
          {onToggleSearchHistory && (
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={searchHistory}
                onChange={(e) => onToggleSearchHistory(e.target.checked)}
                disabled={busy}
                data-testid="search-history-toggle"
              />
              過去ブリーフィングを検索
            </label>
          )}
          <div className="flex-1" />
          {busy ? (
            <Button
              type="button"
              variant="destructive"
              className="rounded-full"
              onClick={onCancel}
              data-testid="cancel-button"
              title="送信中の応答を中止 (Esc)"
            >
              {cancelLabel}
            </Button>
          ) : (
            <Button
              onClick={handleSend}
              disabled={input.trim().length === 0 || uploading}
              data-testid="send-button"
              size="icon"
              className="shrink-0 rounded-full"
              aria-label={sendLabel}
            >
              <ArrowUp aria-hidden className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {attachError && (
        <p
          className="px-2 pt-2 text-xs text-destructive"
          role="alert"
          data-testid="attach-error"
        >
          {attachError}
        </p>
      )}
      {!supportsMic && (
        <p
          className="px-2 pt-2 text-xs text-muted-foreground"
          data-testid="mic-unsupported"
        >
          Voice input is unavailable in this browser (Chrome / Edge supported).
        </p>
      )}
    </div>
  )
}
