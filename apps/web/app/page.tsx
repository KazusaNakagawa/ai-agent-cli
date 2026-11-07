import { redirect } from "next/navigation"

import { apiFetch } from "@/lib/api"
import { Wizard } from "@/components/onboarding/Wizard"

async function isOnboarded(): Promise<boolean> {
  try {
    const res = await apiFetch("/api/state")
    if (!res.ok) return false
    const data = (await res.json()) as { onboarded?: boolean }
    return Boolean(data.onboarded)
  } catch {
    return false
  }
}

export const dynamic = "force-dynamic"

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ rerun?: string }>
}) {
  const { rerun: rerunParam } = await searchParams
  const onboarded = await isOnboarded()
  // ?rerun=1 (Config → Setup) opens the wizard for an onboarded user without
  // clearing the flag. Before onboarding it means nothing: show a first run.
  const rerun = onboarded && rerunParam === "1"
  if (onboarded && !rerun) {
    redirect("/portfolio")
  }
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Wizard rerun={rerun} />
    </main>
  )
}
