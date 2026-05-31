"use client"
import { useState } from "react"

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

export function Wizard() {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1)
  const [data, setData] = useState<WizardData>(INITIAL)

  const goNext = () => setStep((s) => (s === 4 ? s : ((s + 1) as 1 | 2 | 3 | 4)))
  const goBack = () => setStep((s) => (s === 1 ? s : ((s - 1) as 1 | 2 | 3 | 4)))

  const props = { data, setData, onNext: goNext, onBack: goBack, step }

  return (
    <div className="w-full max-w-xl" data-testid="wizard">
      {step === 1 && <Step1AuthMode {...props} />}
      {step === 2 && <Step2Portfolio {...props} />}
      {step === 3 && <Step3Notifications {...props} />}
      {step === 4 && <Step4TestRun {...props} />}
    </div>
  )
}
