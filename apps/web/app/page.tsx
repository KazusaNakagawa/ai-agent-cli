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

export default async function Home() {
  const onboarded = await isOnboarded()
  if (onboarded) {
    redirect("/portfolio")
  }
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Wizard />
    </main>
  )
}
