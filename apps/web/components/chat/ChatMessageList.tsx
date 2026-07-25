"use client"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { LoadingDots } from "@/components/ui/loading-dots"
import type { ChatMessage } from "@/lib/chatStore"
import type { NotionSaveState } from "@/lib/hooks/useNotionSave"
import { cn } from "@/lib/utils"

type Props = {
  messages: ChatMessage[]
  busy: boolean
  retrying: boolean
  notionReady: boolean
  notionState: Record<number, NotionSaveState>
  onNotionSave: (idx: number) => void
}

export function ChatMessageList({
  messages,
  busy,
  retrying,
  notionReady,
  notionState,
  onNotionSave,
}: Props) {
  return (
    <Card>
      <CardContent
        className="max-h-[60vh] space-y-3 overflow-y-auto pt-6"
        data-testid="chat-log"
      >
        {messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Ask anything about today&apos;s briefing — e.g.
            {" "}&ldquo;半導体セクターの新着リスクは？&rdquo;
          </p>
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "rounded-md border p-3 text-sm",
                m.role === "user"
                  ? "border-primary/30 bg-primary/5"
                  : "border-muted bg-muted/30",
              )}
              data-testid={`chat-msg-${m.role}`}
            >
              <p className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">
                {m.role}
              </p>
              {m.role === "assistant" ? (
                m.content ? (
                  <div className="prose prose-sm max-w-none dark:prose-invert">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeSanitize]}
                    >
                      {m.content}
                    </ReactMarkdown>
                  </div>
                ) : busy && i === messages.length - 1 && !m.cancelled ? (
                  <LoadingDots label="調査中" data-testid="chat-thinking" />
                ) : null
              ) : (
                <p className="whitespace-pre-wrap">{m.content}</p>
              )}
              {m.error && (
                <p
                  className="mt-2 text-xs text-destructive"
                  data-testid="chat-error"
                >
                  {m.error}
                </p>
              )}
              {m.role === "assistant" && m.cancelled && (
                <p
                  className="mt-2 text-xs text-muted-foreground"
                  data-testid="chat-cancelled"
                >
                  Cancelled
                </p>
              )}
              {m.role === "assistant" &&
                m.content &&
                !m.error &&
                !m.cancelled && (
                  <NotionSaveRow
                    state={notionState[i]}
                    // Disable while this assistant message is still streaming
                    // (last message + busy) so the user can't persist a
                    // partial answer.
                    enabled={
                      notionReady && !(busy && i === messages.length - 1)
                    }
                    onSave={() => onNotionSave(i)}
                  />
                )}
            </div>
          ))
        )}
        {retrying && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="chat-retrying"
          >
            Session expired upstream, retrying…
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function NotionSaveRow({
  state,
  enabled,
  onSave,
}: {
  state: NotionSaveState | undefined
  enabled: boolean
  onSave: () => void
}) {
  const status: NotionSaveState["status"] = state?.status ?? "idle"
  const disabled = !enabled || status === "saving" || status === "saved"
  const title = enabled
    ? undefined
    : "Notion 認証情報が未設定です（Credentials タブで設定してください）"
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onSave}
        disabled={disabled}
        title={title}
        data-testid="notion-save-button"
      >
        {status === "saving"
          ? "追記中…"
          : status === "saved"
          ? "✓ Notion に追記済"
          : status === "error"
          ? "追記を再試行"
          : "Notion ブリーフィングに追記"}
      </Button>
      {status === "saved" && state?.url && (
        <a
          href={state.url}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline"
          data-testid="notion-save-link"
        >
          ページを開く
        </a>
      )}
      {status === "saved" && state?.localSaved && (
        <span className="text-muted-foreground" data-testid="local-save-note">
          ローカル md にも追記済
        </span>
      )}
      {status === "saved" && state?.localSaved === false && (
        <span className="text-destructive" data-testid="local-save-error">
          ローカル md への追記に失敗: {state.localError ?? "unknown error"}
        </span>
      )}
      {status === "error" && state?.error && (
        <span className="text-destructive" data-testid="notion-save-error">
          {state.error}
        </span>
      )}
    </div>
  )
}
