"use client"
import { useEffect, useState } from "react"

import { AuthModeForm } from "@/components/screens/AuthModeForm"
import { fetchCredentials } from "@/lib/credentials"

type Initial = { authMode: "cli" | "api"; anthropicKeySet: boolean }

export function AuthPanel() {
  const [initial, setInitial] = useState<Initial | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetch("/api/auth/mode"), fetchCredentials()])
      .then(async ([modeRes, creds]) => {
        if (!modeRes.ok) throw new Error(`GET /api/auth/mode HTTP ${modeRes.status}`)
        const mode = (await modeRes.json()) as { auth_mode: "cli" | "api" }
        setInitial({
          authMode: mode.auth_mode,
          anthropicKeySet: Boolean(creds.ANTHROPIC_API_KEY),
        })
      })
      .catch(() => setError("Failed to load auth settings."))
  }, [])

  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (!initial) return <p className="text-sm text-muted-foreground">Loading…</p>
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
