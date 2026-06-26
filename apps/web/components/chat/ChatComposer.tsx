"use client"
import { useState, useRef, type KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ImageAttachArea } from "@/components/ui/ImageAttachArea"
import { useImageDrop } from "@/lib/hooks/useImageDrop"
import type { ImageAttachment } from "@/lib/types/image"

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
}: Props) {
  const composingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [attachedImage, setAttachedImage] = useState<ImageAttachment | null>(null)
  const { isDragging } = useImageDrop(textareaRef, setAttachedImage)

  function handleSend() {
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
            onChange={(e) => setInput(e.target.value)}
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
            className={`flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm${isDragging ? " ring-2 ring-primary" : ""}`}
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
        <ImageAttachArea
          attachedImage={attachedImage}
          onAttach={setAttachedImage}
          onRemove={() => setAttachedImage(null)}
          disabled={busy}
          isDragging={isDragging}
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
