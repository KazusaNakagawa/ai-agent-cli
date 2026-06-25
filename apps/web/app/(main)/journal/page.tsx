export const dynamic = "force-dynamic"

import { JournalScreen } from "@/components/screens/JournalScreen"

export default function JournalPage() {
  return (
    <div className="flex h-full flex-col gap-4">
      <header>
        <h2 className="text-xl font-semibold">Journal</h2>
        <p className="text-sm text-muted-foreground">
          Jot down what happened today and your thoughts. Entries accumulate
          per day, and you can brainstorm over them with Claude.
        </p>
      </header>
      <div className="min-h-0 flex-1 overflow-hidden">
        <JournalScreen />
      </div>
    </div>
  )
}
