"use client"
import { useEffect, useState } from "react"

import { CredentialsForm } from "@/components/screens/CredentialsForm"
import { apiFetch } from "@/lib/api"

export function CredentialsPanel() {
  const [status, setStatus] = useState<Record<string, boolean> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch("/api/credentials")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<Record<string, boolean>>
      })
      .then(setStatus)
      .catch((e: unknown) => setError(String(e)))
  }, [])

  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (!status) return <p className="text-sm text-muted-foreground">Loading…</p>
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
