"use client"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { BriefingConfig } from "@/lib/config-types"
import { Step1AuthMode } from "./Step1AuthMode"
import { Step2Portfolio } from "./Step2Portfolio"
import { Step3Notifications } from "./Step3Notifications"
import { markOnboarded, putJson, seedDefaults } from "./onboardingApi"
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
  const [confirmSkip, setConfirmSkip] = useState(false)
  const [skipping, setSkipping] = useState(false)
  const [skipError, setSkipError] = useState<string | null>(null)
  // A step is saving (or running the Step 4 test). Skipping then would race
  // that request, so "Skip setup" waits.
  const [stepBusy, setStepBusy] = useState(false)

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

  // First run only: creates briefing.json from the template if nothing has
  // yet (a source checkout has none; npx already seeded one), marks
  // onboarding done, and runs no test. What earlier steps saved stays.
  const skipSetup = async () => {
    setSkipping(true)
    setSkipError(null)
    try {
      await seedDefaults()
      await markOnboarded()
    } catch (e) {
      setSkipError(e instanceof Error ? e.message : "Network error")
      setSkipping(false)
    }
  }

  const goNext = () => {
    const next = (step === 4 ? step : step + 1) as Step
    setStep(next)
    setReached((r) => (next > r ? next : r))
  }
  const goBack = () => setStep((s) => (s === 1 ? s : ((s - 1) as Step)))

  const props = { data, setData, onNext: goNext, onBack: goBack, step, onBusyChange: setStepBusy }
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
      {!rerun && !confirmSkip && (
        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirmSkip(true)}
            disabled={stepBusy}
            data-testid="wizard-skip"
          >
            Skip setup
          </Button>
        </div>
      )}
      {!rerun && confirmSkip && (
        <div
          className="space-y-2 rounded-md border p-3 text-sm"
          data-testid="wizard-skip-note"
        >
          <p>
            {reached >= 2
              ? "Skip the remaining steps? What you already saved stays, and anything not set up yet starts from the default settings."
              : "Skip setup and start with the default settings?"}{" "}
            You can change them later in Config → Setup, or run this wizard again from there.
          </p>
          {skipError && (
            <p role="alert" className="text-destructive" data-testid="wizard-skip-error">
              {skipError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setConfirmSkip(false)
                setSkipError(null)
              }}
              disabled={skipping}
              data-testid="wizard-skip-dismiss"
            >
              Continue setup
            </Button>
            <Button
              size="sm"
              onClick={() => void skipSetup()}
              disabled={skipping}
              data-testid="wizard-skip-confirm"
            >
              {skipping ? "..." : "Skip setup"}
            </Button>
          </div>
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
        // Hidden, not unmounted, while the skip is confirmed: the step can't
        // be submitted underneath it, and "Continue setup" brings back what
        // was typed.
        <div hidden={confirmSkip}>
          {step === 1 && <Step1AuthMode {...props} />}
          {step === 2 && <Step2Portfolio {...props} existing={original?.config ?? null} />}
          {step === 3 && <Step3Notifications {...props} />}
          {step === 4 && <Step4TestRun {...props} />}
        </div>
      )}
    </div>
  )
}
