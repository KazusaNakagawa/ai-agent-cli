import { apiFetch } from "@/lib/api"
import { BriefingConfig } from "@/lib/config-types"
import { GeopoliticalForm } from "@/components/screens/GeopoliticalForm"

async function loadConfig(): Promise<BriefingConfig | null> {
  const res = await apiFetch("/api/config")
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`GET /api/config returned HTTP ${res.status}`)
  return (await res.json()) as BriefingConfig
}

export const dynamic = "force-dynamic"

export default async function GeopoliticalPage() {
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
        <h2 className="text-xl font-semibold">Geopolitical Risks</h2>
        <p className="text-sm text-muted-foreground">
          Conflicts or events Claude should weave into the briefing. Optional.
        </p>
      </header>
      <GeopoliticalForm initial={config} />
    </div>
  )
}
