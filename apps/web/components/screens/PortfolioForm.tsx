"use client"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { ChipInput } from "@/components/ChipInput"
import { SaveStatus, SaveStatusValue } from "@/components/SaveStatus"
import { BriefingConfig } from "@/lib/config-types"
import {
  ValidationErrorMap,
  parseValidationErrors,
} from "@/lib/validation-errors"

type Props = { initial: BriefingConfig }

const upper = (s: string) => s.toUpperCase()

export function PortfolioForm({ initial }: Props) {
  const router = useRouter()
  const [tickers, setTickers] = useState<string[]>(initial.portfolio.tickers)
  const [themes, setThemes] = useState<string[]>(initial.portfolio.themes)
  const [status, setStatus] = useState<SaveStatusValue>("idle")
  const [errors, setErrors] = useState<ValidationErrorMap>(new Map())
  const [genericError, setGenericError] = useState<string | null>(null)

  const tickersError = errors.get("portfolio/tickers")
  const themesError = errors.get("portfolio/themes")

  const save = async () => {
    setStatus("saving")
    setErrors(new Map())
    setGenericError(null)
    const payload: BriefingConfig = {
      ...initial,
      portfolio: { tickers, themes },
    }
    const res = await fetch("/api/config", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    })
    if (res.ok) {
      setStatus("saved")
      router.refresh()
      return
    }
    if (res.status === 422) {
      setErrors(await parseValidationErrors(res))
    } else {
      setGenericError(`PUT /api/config failed (HTTP ${res.status})`)
    }
    setStatus("error")
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <label className="text-sm font-medium" htmlFor="tickers">
          Tickers
        </label>
        <ChipInput
          values={tickers}
          onChange={setTickers}
          placeholder="PLTR, NVDA, GOOGL"
          ariaLabel="Tickers"
          normalise={upper}
          testid="tickers-chips"
        />
        {tickersError && (
          <p className="text-xs text-destructive" data-testid="tickers-error">
            {tickersError}
          </p>
        )}
      </div>
      <div className="space-y-1">
        <label className="text-sm font-medium" htmlFor="themes">
          Themes
        </label>
        <ChipInput
          values={themes}
          onChange={setThemes}
          placeholder="AI規制, 半導体, 関税"
          ariaLabel="Themes"
          testid="themes-chips"
        />
        {themesError && (
          <p className="text-xs text-destructive" data-testid="themes-error">
            {themesError}
          </p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <Button onClick={() => void save()} disabled={status === "saving"}>
          Save
        </Button>
        <SaveStatus status={status} />
      </div>
      {genericError && (
        <p className="text-sm text-destructive" data-testid="generic-error">
          {genericError}
        </p>
      )}
    </div>
  )
}
