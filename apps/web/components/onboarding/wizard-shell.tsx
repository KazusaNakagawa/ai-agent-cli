"use client"
import { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export type ShellProps = {
  step: 1 | 2 | 3 | 4
  title: string
  description?: string
  error?: string | null
  busy?: boolean
  primaryLabel: string
  onPrimary: () => void | Promise<void>
  primaryDisabled?: boolean
  onBack?: () => void
  children: ReactNode
}

export function WizardShell({
  step,
  title,
  description,
  error,
  busy,
  primaryLabel,
  onPrimary,
  primaryDisabled,
  onBack,
  children,
}: ShellProps) {
  return (
    <Card>
      <CardHeader>
        <p className="text-xs text-muted-foreground">Step {step} / 4</p>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
      <CardFooter className="flex flex-col items-stretch gap-2">
        {error && (
          <p
            role="alert"
            className="text-sm text-destructive"
            data-testid="wizard-error"
          >
            {error}
          </p>
        )}
        <div className="flex justify-between gap-2">
          <Button
            variant="ghost"
            onClick={onBack}
            disabled={!onBack || busy}
            data-testid="wizard-back"
          >
            Back
          </Button>
          <Button
            onClick={() => void onPrimary()}
            disabled={busy || primaryDisabled}
            data-testid="wizard-primary"
          >
            {busy ? "..." : primaryLabel}
          </Button>
        </div>
      </CardFooter>
    </Card>
  )
}
