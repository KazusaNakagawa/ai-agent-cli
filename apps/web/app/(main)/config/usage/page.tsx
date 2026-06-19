export const dynamic = "force-dynamic"

export default function UsagePage() {
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Usage</h2>
        <p className="text-sm text-muted-foreground">
          Token usage and cost per Claude run, charted from the daily JSONL logs.
        </p>
      </header>
      <div
        data-testid="usage-dashboard-placeholder"
        className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground"
      >
        Usage dashboard coming soon.
      </div>
    </div>
  )
}
