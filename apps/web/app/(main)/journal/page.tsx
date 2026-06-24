export const dynamic = "force-dynamic"

import { JournalScreen } from "@/components/screens/JournalScreen"

export default function JournalPage() {
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Journal</h2>
        <p className="text-sm text-muted-foreground">
          Jot down what happened today and your thoughts. Entries accumulate
          per day, and you can brainstorm over them with Claude.
        </p>
      </header>
      <JournalScreen />
    </div>
  )
}
