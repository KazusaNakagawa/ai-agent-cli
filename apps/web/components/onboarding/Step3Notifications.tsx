"use client"
import { useState } from "react"

import { Input } from "@/components/ui/input"
import { WizardData } from "./Wizard"
import { WizardShell } from "./wizard-shell"

type Props = {
  data: WizardData
  setData: (updater: (prev: WizardData) => WizardData) => void
  onNext: () => void
  onBack: () => void
  step: 1 | 2 | 3 | 4
}

type Field = {
  name: string
  label: string
  hint?: string
  secret?: boolean
}

const FIELDS: Field[] = [
  { name: "DISCORD_TOKEN", label: "Discord bot token", secret: true },
  { name: "CHANNEL_ID", label: "Discord channel id" },
  { name: "NOTION_API_KEY", label: "Notion integration API key", secret: true },
  { name: "NOTION_DATABASE_ID", label: "Notion database id" },
]

export function Step3Notifications({
  data,
  onNext,
  onBack,
  step,
}: Props) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(FIELDS.map((f) => [f.name, ""])),
  )
  // ANTHROPIC_API_KEY only shown when API auth mode is selected in Step 1.
  const showAnthropicKey = data.authMode === "api"
  const allFields: Field[] = showAnthropicKey
    ? [
        ...FIELDS,
        {
          name: "ANTHROPIC_API_KEY",
          label: "Anthropic API key",
          hint: "Required because you picked API mode in Step 1.",
          secret: true,
        },
      ]
    : FIELDS

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const writes = allFields
        .map((f) => [f.name, (values[f.name] ?? "").trim()] as const)
        .filter(([, v]) => v.length > 0)
      for (const [name, value] of writes) {
        const res = await fetch(
          `/api/credentials/${encodeURIComponent(name)}`,
          {
            method: "PUT",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ value }),
          },
        )
        if (!res.ok) {
          const text = await res.text()
          setError(`PUT /api/credentials/${name} failed (HTTP ${res.status}): ${text}`)
          return
        }
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
      title="Notifications and credentials"
      description="Leave any field blank to skip. You can add them later from the sidebar."
      busy={busy}
      error={error}
      primaryLabel="Next"
      onPrimary={submit}
      onBack={onBack}
    >
      {allFields.map((f) => (
        <label key={f.name} className="block space-y-1">
          <span className="text-sm font-medium">{f.label}</span>
          <Input
            type={f.secret ? "password" : "text"}
            value={values[f.name] ?? ""}
            onChange={(e) =>
              setValues((prev) => ({ ...prev, [f.name]: e.target.value }))
            }
            data-testid={`cred-${f.name}`}
          />
          {f.hint && (
            <span className="text-xs text-muted-foreground">{f.hint}</span>
          )}
        </label>
      ))}
    </WizardShell>
  )
}
