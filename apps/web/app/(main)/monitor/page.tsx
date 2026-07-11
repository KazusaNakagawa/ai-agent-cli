export const dynamic = "force-dynamic"

import { MonitorDashboard } from "@/components/screens/MonitorDashboard"

export default function MonitorPage() {
  return (
    <div className="flex h-full flex-col gap-4">
      <header>
        <h2 className="text-xl font-semibold">Monitor</h2>
        <p className="text-sm text-muted-foreground">
          Token usage across all Claude Code transcripts, broken down by day,
          model, and project. Separate from Settings &gt; Usage, which covers
          app-run costs only.
        </p>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <MonitorDashboard />
      </div>
    </div>
  )
}
