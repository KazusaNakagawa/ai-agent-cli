export const dynamic = "force-dynamic"

import { BriefingDashboard } from "@/components/screens/BriefingDashboard"

export default function BriefingPage() {
  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <h1 className="text-lg font-semibold">Briefing</h1>
      <div className="min-h-0 flex-1 overflow-hidden">
        <BriefingDashboard />
      </div>
    </div>
  )
}
