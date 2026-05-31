import { apiFetch } from "@/lib/api"
import { BriefingConfig } from "@/lib/config-types"
import { WatchSectorsForm } from "@/components/screens/WatchSectorsForm"

async function loadConfig(): Promise<BriefingConfig | null> {
  const res = await apiFetch("/api/config")
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`GET /api/config returned HTTP ${res.status}`)
  return (await res.json()) as BriefingConfig
}

export const dynamic = "force-dynamic"

export default async function WatchSectorsPage() {
  const config = await loadConfig()
  if (!config) {
    return (
      <div className="rounded-md border border-destructive/40 p-4 text-sm text-destructive">
        briefing.json is missing. Re-run onboarding from the home page.
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Watch Sectors</h2>
        <p className="text-sm text-muted-foreground">
          Groups of tickers Claude analyses together. At least one is required.
        </p>
      </header>
      <WatchSectorsForm initial={config} />
    </div>
  )
}
