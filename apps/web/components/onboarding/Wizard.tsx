"use client"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { BriefingConfig } from "@/lib/config-types"
import { Step1AuthMode } from "./Step1AuthMode"
import { Step2Portfolio } from "./Step2Portfolio"
import { Step3Notifications } from "./Step3Notifications"
import { Step4TestRun } from "./Step4TestRun"

export type AuthMode = "cli" | "api"

export type WizardData = {
  authMode: AuthMode
  tickers: string[]
  themes: string[]
}

const INITIAL: WizardData = {
  authMode: "cli",
  tickers: [],
  themes: [],
}

type Step = 1 | 2 | 3 | 4

type Props = {
  // Re-run from Config → Setup. The onboarded flag is never cleared: "/"
  // renders the wizard because of ?rerun=1, so leaving at any point is plain
  // navigation. The wizard starts from the current settings, keeps the parts
  // of briefing.json it does not edit, and Cancel restores what it saved.
  rerun?: boolean
}

type Original = { authMode: AuthMode; config: BriefingConfig | null }

const putJson = (url: string, body: unknown) =>
  fetch(url, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })

async function loadOriginal(): Promise<Original> {
  const [modeRes, configRes] = await Promise.all([fetch("/api/auth/mode"), fetch("/api/config")])
  if (!modeRes.ok) throw new Error(`GET /api/auth/mode failed (HTTP ${modeRes.status})`)
  // Only a missing file means "start fresh". Any other failure must stop the
  // wizard: Step 2 replaces the whole file, so guessing would wipe it.
  if (!configRes.ok && configRes.status !== 404) {
    throw new Error(`GET /api/config failed (HTTP ${configRes.status})`)
  }
  const mode = (await modeRes.json()) as { auth_mode: AuthMode }
  const config = configRes.ok ? ((await configRes.json()) as BriefingConfig) : null
  return { authMode: mode.auth_mode, config }
}

export function Wizard({ rerun = false }: Props) {
  const [step, setStep] = useState<Step>(1)
  // Furthest step reached: Step 1 saved the auth mode once we got to 2, and
  // Step 2 saved the config once we got to 3.
  const [reached, setReached] = useState<Step>(1)
  const [data, setData] = useState<WizardData>(INITIAL)
  const [original, setOriginal] = useState<Original | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)

  useEffect(() => {
    if (!rerun) return
    let active = true
    loadOriginal().then(
      (o) => {
        if (!active) return
        setOriginal(o)
        setData({
          authMode: o.authMode,
          tickers: o.config?.portfolio.tickers ?? [],
          themes: o.config?.portfolio.themes ?? [],
        })
      },
      (e: unknown) => {
        if (active) setLoadError(e instanceof Error ? e.message : "Network error")
      },
    )
    return () => {
      active = false
    }
  }, [rerun])

  const cancelRerun = async () => {
    setCancelling(true)
    setCancelError(null)
    try {
      if (original && reached >= 2) {
        const res = await putJson("/api/auth/mode", { auth_mode: original.authMode })
        if (!res.ok) throw new Error(`Restoring auth mode failed (HTTP ${res.status})`)
      }
      // A config created from scratch (no file before) has no API to delete
      // it, so it stays; there was nothing to lose.
      if (original?.config && reached >= 3) {
        const res = await putJson("/api/config", original.config)
        if (!res.ok) throw new Error(`Restoring config failed (HTTP ${res.status})`)
      }
      window.location.assign("/portfolio")
    } catch (e) {
      setCancelError(e instanceof Error ? e.message : "Network error")
      setCancelling(false)
    }
  }

  const goNext = () => {
    const next = (step === 4 ? step : step + 1) as Step
    setStep(next)
    setReached((r) => (next > r ? next : r))
  }
  const goBack = () => setStep((s) => (s === 1 ? s : ((s - 1) as Step)))

  const props = { data, setData, onNext: goNext, onBack: goBack, step }
  const loading = rerun && !original && !loadError

  return (
    <div className="w-full max-w-xl space-y-2" data-testid="wizard">
      {rerun && (
        <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span>Re-running setup. Cancel restores the auth mode and portfolio saved before.</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void cancelRerun()}
            disabled={cancelling}
            data-testid="wizard-cancel-rerun"
          >
            Cancel
          </Button>
        </div>
      )}
      {cancelError && (
        <p role="alert" className="text-sm text-destructive" data-testid="wizard-cancel-error">
          {cancelError}
        </p>
      )}
      {loadError ? (
        <p role="alert" className="text-sm text-destructive" data-testid="wizard-load-error">
          Could not load the current settings: {loadError}
        </p>
      ) : loading ? (
        <p className="text-sm text-muted-foreground">Loading current settings…</p>
      ) : (
        <>
          {step === 1 && <Step1AuthMode {...props} />}
          {step === 2 && <Step2Portfolio {...props} existing={original?.config ?? null} />}
          {step === 3 && <Step3Notifications {...props} />}
          {step === 4 && <Step4TestRun {...props} />}
        </>
      )}
    </div>
  )
}
