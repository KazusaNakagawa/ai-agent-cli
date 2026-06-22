import { redirect } from "next/navigation"

import { apiFetch } from "@/lib/api"
import { Sidebar } from "@/components/Sidebar"
import { ChatJobStateProvider } from "@/lib/chatJobStore"
import { ChatStateProvider } from "@/lib/chatStore"
import { JobStateProvider } from "@/lib/jobStore"

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

export default async function MainLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Guard: kick anyone not onboarded back to / for the wizard.
  if (!(await isOnboarded())) redirect("/")
  return (
    <JobStateProvider>
      <ChatStateProvider>
        <ChatJobStateProvider>
          <div className="flex h-dvh overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto p-8">{children}</main>
          </div>
        </ChatJobStateProvider>
      </ChatStateProvider>
    </JobStateProvider>
  )
}
