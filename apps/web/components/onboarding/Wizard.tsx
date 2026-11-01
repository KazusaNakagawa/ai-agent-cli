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

type Props = {
  // Re-run from Config → Setup: start from the current settings, keep the
  // parts of briefing.json the wizard does not edit, and allow backing out.
  rerun?: boolean
}

export function Wizard({ rerun = false }: Props) {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1)
  const [data, setData] = useState<WizardData>(INITIAL)
  const [existing, setExisting] = useState<BriefingConfig | null>(null)
  const [loading, setLoading] = useState(rerun)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)

  useEffect(() => {
    if (!rerun) return
    let active = true
    const loadMode = fetch("/api/auth/mode")
      .then(async (res) => (res.ok ? ((await res.json()) as { auth_mode: AuthMode }).auth_mode : null))
      .catch(() => null)
    const loadConfig = fetch("/api/config")
      .then(async (res) => (res.ok ? ((await res.json()) as BriefingConfig) : null))
      .catch(() => null)
    // A failed read just leaves the first-run defaults in place.
    void Promise.all([loadMode, loadConfig]).then(([mode, config]) => {
      if (!active) return
      setExisting(config)
      setData((prev) => ({
        authMode: mode ?? prev.authMode,
        tickers: config?.portfolio.tickers ?? prev.tickers,
        themes: config?.portfolio.themes ?? prev.themes,
      }))
      setLoading(false)
    })
    return () => {
      active = false
    }
  }, [rerun])

  const cancelRerun = async () => {
    setCancelling(true)
    setCancelError(null)
    try {
      const res = await fetch("/api/state", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ onboarded: true }),
      })
      if (!res.ok) {
        setCancelError(`PUT /api/state failed (HTTP ${res.status})`)
        setCancelling(false)
        return
      }
      window.location.assign("/portfolio")
    } catch (e) {
      setCancelError(e instanceof Error ? e.message : "Network error")
      setCancelling(false)
    }
  }

  const goNext = () => setStep((s) => (s === 4 ? s : ((s + 1) as 1 | 2 | 3 | 4)))
  const goBack = () => setStep((s) => (s === 1 ? s : ((s - 1) as 1 | 2 | 3 | 4)))

  const props = { data, setData, onNext: goNext, onBack: goBack, step }

  return (
    <div className="w-full max-w-xl space-y-2" data-testid="wizard">
      {rerun && (
        <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span>Re-running setup. Your current settings are kept unless you change them.</span>
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
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading current settings…</p>
      ) : (
        <>
          {step === 1 && <Step1AuthMode {...props} />}
          {step === 2 && <Step2Portfolio {...props} existing={existing} />}
          {step === 3 && <Step3Notifications {...props} />}
          {step === 4 && <Step4TestRun {...props} />}
        </>
      )}
    </div>
  )
}
