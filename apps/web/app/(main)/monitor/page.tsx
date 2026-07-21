export const dynamic = "force-dynamic"

import { MonitorDashboard } from "@/components/screens/MonitorDashboard"

export default function MonitorPage() {
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Monitor</h2>
        <p className="text-sm text-muted-foreground">
          Token usage across all Claude Code transcripts, broken down by day,
          model, and project. Separate from Settings &gt; Usage, which covers
          app-run costs only.
        </p>
      </header>
      <MonitorDashboard />
    </div>
  )
}
