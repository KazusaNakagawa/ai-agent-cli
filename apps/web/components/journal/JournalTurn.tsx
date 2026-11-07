"use client"
import { LoadingDots } from "@/components/ui/loading-dots"
import { MarkdownView } from "@/components/ui/MarkdownView"

/**
 * One Q&A turn in the chat's conversation grammar: the question as a muted
 * bubble on the right, the answer as plain Markdown with no frame. `answer`
 * null shows the thinking indicator; an empty string omits the answer (a
 * saved question that never got one).
 */
export function JournalTurn({ question, answer }: { question: string; answer: string | null }) {
  return (
    <div className="flex flex-col gap-4">
      <div
        className="max-w-[80%] self-end rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-sm leading-relaxed"
        data-testid="journal-turn-question"
      >
        <MarkdownView content={question} breaks />
      </div>
      {answer === null ? (
        <LoadingDots label="Thinking…" data-testid="journal-chat-thinking" />
      ) : (
        answer && (
          <div className="leading-7" data-testid="journal-turn-answer">
            <MarkdownView content={answer} />
          </div>
        )
      )}
    </div>
  )
}
