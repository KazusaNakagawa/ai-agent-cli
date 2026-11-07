export const putJson = (url: string, body: unknown) =>
  fetch(url, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })

/** Creates briefing.json from the template if it is missing; never overwrites. */
export async function seedDefaults(): Promise<void> {
  const res = await fetch("/api/config/seed", { method: "POST" })
  if (!res.ok) throw new Error(`POST /api/config/seed failed (HTTP ${res.status})`)
}

/**
 * Persists onboarded=true and loads "/", whose Server Component then picks
 * the landing page (also from a re-run, whose URL carries ?rerun=1).
 */
export async function markOnboarded(): Promise<void> {
  const res = await putJson("/api/state", { onboarded: true })
  if (!res.ok) throw new Error(`PUT /api/state failed (HTTP ${res.status})`)
  window.location.assign("/")
}
