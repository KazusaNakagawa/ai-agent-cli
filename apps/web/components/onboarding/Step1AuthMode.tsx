"use client"
import { useState } from "react"

import { AuthMode, WizardData } from "./Wizard"
import { WizardShell } from "./wizard-shell"

type Props = {
  data: WizardData
  setData: (updater: (prev: WizardData) => WizardData) => void
  onNext: () => void
  step: 1 | 2 | 3 | 4
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
    hint: "Pay-per-use via ANTHROPIC_API_KEY. Set the key in Step 3.",
  },
]

export function Step1AuthMode({ data, setData, onNext, step }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch("/api/auth/mode", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ auth_mode: data.authMode }),
      })
      if (!res.ok) {
        setError(`Failed to set auth mode (HTTP ${res.status})`)
        return
      }
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error")
    } finally {
      setBusy(false)
    }
  }

  return (
    <WizardShell
      step={step}
      title="Choose how to call Claude"
      description="You can switch later from the sidebar."
      busy={busy}
      error={error}
      primaryLabel="Next"
      onPrimary={submit}
    >
      <fieldset className="space-y-3">
        <legend className="sr-only">Authentication mode</legend>
        {OPTIONS.map((opt) => (
          <label
            key={opt.value}
            className="flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-accent"
          >
            <input
              type="radio"
              name="auth-mode"
              value={opt.value}
              checked={data.authMode === opt.value}
              onChange={() =>
                setData((prev) => ({ ...prev, authMode: opt.value }))
              }
              className="mt-1"
            />
            <span className="flex flex-col">
              <span className="font-medium">{opt.label}</span>
              <span className="text-xs text-muted-foreground">{opt.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {data.authMode === "cli" && (
        <p className="text-xs text-muted-foreground">
          Run <code className="font-mono">claude login</code> in a terminal
          first if you have not authenticated yet.
        </p>
      )}
    </WizardShell>
  )
}
