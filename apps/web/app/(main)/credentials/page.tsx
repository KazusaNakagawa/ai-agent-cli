import { apiFetch } from "@/lib/api"
import { CredentialsForm } from "@/components/screens/CredentialsForm"

async function loadStatus(): Promise<Record<string, boolean>> {
  const res = await apiFetch("/api/credentials")
  if (!res.ok) {
    throw new Error(`GET /api/credentials returned HTTP ${res.status}`)
  }
  return (await res.json()) as Record<string, boolean>
}

export const dynamic = "force-dynamic"

export default async function CredentialsPage() {
  const status = await loadStatus()
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Credentials</h2>
        <p className="text-sm text-muted-foreground">
          Stored in the OS keychain. Existing values are never shown — only
          whether each key is set.
        </p>
      </header>
      <CredentialsForm initial={status} />
    </div>
  )
}
