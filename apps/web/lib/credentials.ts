export async function fetchCredentials(): Promise<Record<string, boolean>> {
  const res = await fetch("/api/credentials")
  if (!res.ok) throw new Error(`GET /api/credentials HTTP ${res.status}`)
  return (await res.json()) as Record<string, boolean>
}
