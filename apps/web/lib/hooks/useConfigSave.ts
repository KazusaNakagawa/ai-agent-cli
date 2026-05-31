"use client"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { SaveStatusValue } from "@/components/SaveStatus"
import { BriefingConfig } from "@/lib/config-types"
import {
  ValidationErrorMap,
  parseValidationErrors,
} from "@/lib/validation-errors"

export type UseConfigSave = {
  status: SaveStatusValue
  errors: ValidationErrorMap
  genericError: string | null
  save: (payload: BriefingConfig) => Promise<void>
}

export function useConfigSave(): UseConfigSave {
  const router = useRouter()
  const [status, setStatus] = useState<SaveStatusValue>("idle")
  const [errors, setErrors] = useState<ValidationErrorMap>(new Map())
  const [genericError, setGenericError] = useState<string | null>(null)

  const save = async (payload: BriefingConfig) => {
    setStatus("saving")
    setErrors(new Map())
    setGenericError(null)
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

  return { status, errors, genericError, save }
}
