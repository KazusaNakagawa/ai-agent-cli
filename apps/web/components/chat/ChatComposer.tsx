"use client"
import { useEffect, useState, useRef, type KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import { insertAtCursor } from "@/lib/insertAtCursor"
import type { ImageAttachment } from "@/lib/types/image"

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
  onSend: (imagePath?: string) => void
  onCancel: () => void
  onHistoryKeyDown?: (e: KeyboardEvent<HTMLTextAreaElement>) => void
  searchHistory: boolean
  onToggleSearchHistory: (value: boolean) => void
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
  searchHistory,
  onToggleSearchHistory,
}: Props) {
  const composingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [attachedImage, setAttachedImage] = useState<ImageAttachment | null>(null)
  const { isDragging } = useImageDrop(textareaRef, setAttachedImage)

  // Covers height updates from sources other than direct typing (history
  // recall via Up/Down, mic dictation, drag-and-drop file insert), which set
  // `input` without going through the textarea's own onChange.
  useEffect(() => {
    if (textareaRef.current) resizeTextarea(textareaRef.current)
  }, [input])

  function handleSend() {
    // Guard the keyboard path: ChatForm.send no-ops on empty input, so without
    // this the Enter key would clear the attachment without ever sending it.
    if (input.trim().length === 0) return
    const path = attachedImage?.path
    setAttachedImage(null)
    onSend(path)
  }

  return (
    <Card>
      <CardContent className="space-y-2 pt-6">
        <div className="flex items-end gap-2">
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
            placeholder="Ask about today's briefing…"
            rows={2}
            className={`flex-1 resize-none overflow-hidden rounded-md border bg-background px-3 py-2 text-sm${isDragging ? " ring-2 ring-primary" : ""}`}
            data-testid="chat-input"
          />
          {supportsMic && (
            <Button
              type="button"
              variant={listening ? "destructive" : "outline"}
              onClick={() => onToggleMic(input)}
              data-testid="mic-button"
              aria-label={listening ? "音声入力停止" : "音声入力開始"}
              aria-pressed={listening}
              title={listening ? "音声入力停止" : "音声入力開始 (ja-JP)"}
            >
              {listening ? "🛑" : "🎤"}
            </Button>
          )}
          {busy ? (
            <Button
              type="button"
              variant="destructive"
              onClick={onCancel}
              data-testid="cancel-button"
              title="送信中の応答を中止 (Esc)"
            >
              Cancel
            </Button>
          ) : (
            <Button
              onClick={handleSend}
              disabled={input.trim().length === 0}
              data-testid="send-button"
            >
              Send
            </Button>
          )}
        </div>
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
        <ImageAttachArea
          attachedImage={attachedImage}
          onAttach={setAttachedImage}
          onRemove={() => setAttachedImage(null)}
          disabled={busy}
          isDragging={isDragging}
          onInsertFile={(markdown) =>
            setInput(insertAtCursor(textareaRef.current, input, markdown))
          }
        />
        {!supportsMic && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="mic-unsupported"
          >
            Voice input is unavailable in this browser (Chrome / Edge supported).
          </p>
        )}
      </CardContent>
    </Card>
  )
}
