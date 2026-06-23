"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"

const toastVariants = cva(
  "pointer-events-auto flex items-start gap-3 rounded-md border px-4 py-3 shadow-lg",
  {
    variants: {
      variant: {
        success: "border-green-700 bg-green-600 text-white",
        error: "border-red-700 bg-red-600 text-white",
      },
    },
    defaultVariants: {
      variant: "success",
    },
  }
)

export interface ToastProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof toastVariants> {
  onClose?: () => void
}

/** Dismissible popup notification. Success → green, error → red. */
function Toast({ className, variant, onClose, children, ...props }: ToastProps) {
  return (
    <div role="status" className={cn(toastVariants({ variant }), className)} {...props}>
      <div className="flex-1 break-words text-sm">{children}</div>
      {onClose && (
        <button
          type="button"
          aria-label="Close"
          data-testid="toast-close"
          onClick={onClose}
          className="rounded-sm opacity-80 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-white/60"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

/** Fixed bottom-right overlay container for toasts. */
function ToastViewport({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2",
        className
      )}
      {...props}
    />
  )
}

export { Toast, ToastViewport, toastVariants }
