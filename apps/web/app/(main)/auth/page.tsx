import { apiFetch } from "@/lib/api"
import { AuthModeForm } from "@/components/screens/AuthModeForm"

type Initial = {
  authMode: "cli" | "api"
  anthropicKeySet: boolean
}

async function loadInitial(): Promise<Initial> {
  const [modeRes, credsRes] = await Promise.all([
    apiFetch("/api/auth/mode"),
    apiFetch("/api/credentials"),
  ])
  if (!modeRes.ok) {
    throw new Error(`GET /api/auth/mode returned HTTP ${modeRes.status}`)
  }
  if (!credsRes.ok) {
    throw new Error(`GET /api/credentials returned HTTP ${credsRes.status}`)
  }
  const mode = (await modeRes.json()) as { auth_mode: "cli" | "api" }
  const creds = (await credsRes.json()) as Record<string, boolean>
  return {
    authMode: mode.auth_mode,
    anthropicKeySet: Boolean(creds.ANTHROPIC_API_KEY),
  }
}

export const dynamic = "force-dynamic"

export default async function AuthPage() {
  const initial = await loadInitial()
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">Auth</h2>
        <p className="text-sm text-muted-foreground">
          How ai-agent talks to Claude. Switch any time.
        </p>
      </header>
      <AuthModeForm
        initialAuthMode={initial.authMode}
        anthropicKeySet={initial.anthropicKeySet}
      />
    </div>
  )
}
