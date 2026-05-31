import { RunForm } from "@/components/screens/RunForm"

export default function RunPage() {
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Run</h2>
        <p className="text-sm text-muted-foreground">
          Trigger the briefing pipeline immediately and watch it finish.
        </p>
      </header>
      <RunForm />
    </div>
  )
}
