"use client"
import { useRef } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

type Props = {
  input: string
  setInput: (value: string) => void
  busy: boolean
  supportsMic: boolean
  listening: boolean
  // Receives the textarea's current value at toggle-on time so the mic
  // hook can append transcripts to whatever the user already typed.
  onToggleMic: (prefix: string) => void
  onSend: () => void
  onCancel: () => void
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
}: Props) {
  // Tracks IME composition so Enter doesn't submit while picking kanji.
  const composingRef = useRef(false)

  return (
    <Card>
      <CardContent className="space-y-2 pt-6">
        <div className="flex items-end gap-2">
          <textarea
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
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !composingRef.current &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault()
                onSend()
              }
            }}
            placeholder="Ask about today's briefing…"
            rows={2}
            className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm"
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
              onClick={onSend}
              disabled={input.trim().length === 0}
              data-testid="send-button"
            >
              Send
            </Button>
          )}
        </div>
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
