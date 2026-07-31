import { ChatSplitView } from "@/components/screens/ChatSplitView"

export default function ChatPage() {
  // `h-full` resolves against the layout's scroll container, which already has a
  // definite height — that is what lets each pane own its own scrollbar.
  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <header>
        <h2 className="text-xl font-semibold">Q&amp;A Chat</h2>
        <p className="text-sm text-muted-foreground">
          Ask questions about today&apos;s briefing while reading it side by side.
          Streams Claude&apos;s answer live; supports Japanese voice input on
          Chrome / Edge.
        </p>
      </header>
      <div className="min-h-0 flex-1">
        <ChatSplitView />
      </div>
    </div>
  )
}
