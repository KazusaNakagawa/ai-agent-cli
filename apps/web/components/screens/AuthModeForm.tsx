"use client"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { SaveStatus, SaveStatusValue } from "@/components/SaveStatus"

type AuthMode = "cli" | "api"

type Props = {
  initialAuthMode: AuthMode
  anthropicKeySet: boolean
}

const OPTIONS: { value: AuthMode; label: string; hint: string }[] = [
  {
    value: "cli",
    label: "Claude Pro / Max subscription (CLI)",
    hint: "Uses the OAuth session from `claude login`. No API key billing.",
  },
  {
    value: "api",
    label: "Anthropic API key",
    hint: "Pay-per-use via ANTHROPIC_API_KEY (stored in the keychain).",
  },
]

export function AuthModeForm({ initialAuthMode, anthropicKeySet }: Props) {
  const router = useRouter()
  const [selected, setSelected] = useState<AuthMode>(initialAuthMode)
  const [status, setStatus] = useState<SaveStatusValue>("idle")
  const [error, setError] = useState<string | null>(null)

  // Guard: API mode requires ANTHROPIC_API_KEY in the keychain. We let the
  // user select the radio but prevent submission with an inline message,
  // so they can read the rationale + the link before committing.
  const apiBlocked = selected === "api" && !anthropicKeySet

  const save = async () => {
    if (apiBlocked) {
      setError(
        "Set ANTHROPIC_API_KEY in Credentials before switching to API mode.",
      )
      setStatus("error")
      return
    }
    setStatus("saving")
    setError(null)
    const res = await fetch("/api/auth/mode", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ auth_mode: selected }),
    })
    if (!res.ok) {
      setError(`PUT /api/auth/mode failed (HTTP ${res.status})`)
      setStatus("error")
      return
    }
    setStatus("saved")
    router.refresh()
  }

  return (
    <div className="space-y-4">
      <fieldset className="space-y-3" data-testid="auth-options">
        <legend className="sr-only">Authentication mode</legend>
        {OPTIONS.map((opt) => (
          <Card key={opt.value}>
            <CardContent className="pt-6">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="radio"
                  name="auth-mode"
                  value={opt.value}
                  checked={selected === opt.value}
                  onChange={() => setSelected(opt.value)}
                  className="mt-1"
                  data-testid={`auth-radio-${opt.value}`}
                />
                <span className="flex flex-col">
                  <span className="font-medium">{opt.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {opt.hint}
                  </span>
                </span>
              </label>
            </CardContent>
          </Card>
        ))}
      </fieldset>

      {apiBlocked && (
        <p
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          data-testid="api-blocked"
        >
          API mode requires <code className="font-mono">ANTHROPIC_API_KEY</code>
          {" "}in the keychain. Open{" "}
          <Link
            href="/credentials"
            className="underline underline-offset-2"
          >
            Credentials
          </Link>{" "}
          to set it, then come back.
        </p>
      )}

      <div className="flex items-center gap-3">
        <Button
          onClick={() => void save()}
          disabled={status === "saving" || selected === initialAuthMode}
          data-testid="auth-save"
        >
          Save
        </Button>
        <SaveStatus status={status} />
      </div>

      {error && (
        <p className="text-sm text-destructive" data-testid="generic-error">
          {error}
        </p>
      )}
    </div>
  )
}
