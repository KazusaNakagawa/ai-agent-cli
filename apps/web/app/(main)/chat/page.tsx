import { ChatForm } from "@/components/screens/ChatForm"

export default function ChatPage() {
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Q&amp;A Chat</h2>
        <p className="text-sm text-muted-foreground">
          Ask questions about today&apos;s briefing. Streams Claude&apos;s answer
          live; supports Japanese voice input on Chrome / Edge.
        </p>
      </header>
      <ChatForm />
    </div>
  )
}
