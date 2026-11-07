"use client"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"

import { Button } from "@/components/ui/button"
import { LoadingDots } from "@/components/ui/loading-dots"
import type { ChatMessage } from "@/lib/chatStore"
import { useFollowTail } from "@/lib/hooks/useFollowTail"
import type { NotionSaveState } from "@/lib/hooks/useNotionSave"
import { cn } from "@/lib/utils"

type Props = {
  messages: ChatMessage[]
  busy: boolean
  retrying: boolean
  notionReady: boolean
  notionState: Record<number, NotionSaveState>
  onNotionSave: (idx: number) => void
  /**
   * Fill the host's height with the log scrolling inside it, instead of
   * capping the log's height. Used by the split view, where the surrounding
   * pane already has a definite height and the composer must stay pinned
   * below the scrolling log.
   */
  fill?: boolean
  /** Fill the composer with a suggestion (empty-state chips). */
  onSuggest?: (text: string) => void
}

const SUGGESTIONS = [
  "半導体セクターの新着リスクは？",
  "今日のブリーフィングを3行で要約して",
  "先週の見立てで外したテーマは？",
]

export function ChatMessageList({
  messages,
  busy,
  retrying,
  notionReady,
  notionState,
  onNotionSave,
  fill = false,
  onSuggest,
}: Props) {
  const { ref, onScroll } = useFollowTail(messages)
  return (
    <div
      ref={ref}
      onScroll={onScroll}
      className={cn(
        "scrollbar-slim overflow-y-auto",
        fill ? "min-h-0 flex-1" : "max-h-[70vh]",
      )}
      data-testid="chat-log"
    >
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-1 py-2">
        {messages.length === 0 ? (
          <div className="flex flex-col items-start gap-4 py-6">
            <p className="text-sm text-muted-foreground">
              Ask anything about today&apos;s briefing.
            </p>
            {onSuggest && (
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => onSuggest(s)}
                    className="rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          messages.map((m, i) =>
            m.role === "user" ? (
              <div
                key={i}
                className="max-w-[80%] self-end whitespace-pre-wrap rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-sm leading-relaxed"
                data-testid="chat-msg-user"
              >
                {m.content}
              </div>
            ) : (
              <div key={i} data-testid="chat-msg-assistant">
                {m.content ? (
                  <div className="prose prose-sm max-w-none leading-7 dark:prose-invert">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeSanitize]}
                    >
                      {m.content}
                    </ReactMarkdown>
                  </div>
                ) : busy && i === messages.length - 1 && !m.cancelled ? (
                  <LoadingDots label="調査中" data-testid="chat-thinking" />
                ) : null}
                {m.error && (
                  <p
                    className="mt-2 text-xs text-destructive"
                    data-testid="chat-error"
                  >
                    {m.error}
                  </p>
                )}
                {m.cancelled && (
                  <p
                    className="mt-2 text-xs text-muted-foreground"
                    data-testid="chat-cancelled"
                  >
                    Cancelled
                  </p>
                )}
                {m.content && !m.error && !m.cancelled && (
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
            ),
          )
        )}
        {retrying && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="chat-retrying"
          >
            Session expired upstream, retrying…
          </p>
        )}
      </div>
    </div>
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
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
      <Button
        type="button"
        variant="ghost"
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
