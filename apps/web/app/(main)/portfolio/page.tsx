import { apiFetch } from "@/lib/api"
import { BriefingConfig } from "@/lib/config-types"
import { PortfolioForm } from "@/components/screens/PortfolioForm"

async function loadConfig(): Promise<BriefingConfig | null> {
  const res = await apiFetch("/api/config")
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`GET /api/config returned HTTP ${res.status}`)
  return (await res.json()) as BriefingConfig
}

export const dynamic = "force-dynamic"

export default async function PortfolioPage() {
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
        <h2 className="text-xl font-semibold">Portfolio</h2>
        <p className="text-sm text-muted-foreground">
          Edit the tickers you want briefed and the themes Claude should anchor on.
        </p>
      </header>
      <PortfolioForm initial={config} />
    </div>
  )
}
