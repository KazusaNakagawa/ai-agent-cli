export async function fetchCredentials(): Promise<Record<string, boolean>> {
  const res = await fetch("/api/credentials")
  if (!res.ok) throw new Error(`GET /api/credentials HTTP ${res.status}`)
  return (await res.json()) as Record<string, boolean>
}

export type CredentialSource = "keychain" | "env" | null

// Where each key resolves from. "env" means a plaintext .env (or the shell)
// is supplying it because the keychain has no entry.
export async function fetchCredentialSources(): Promise<Record<string, CredentialSource>> {
  const res = await fetch("/api/credentials/sources", { cache: "no-store" })
  if (!res.ok) throw new Error(`GET /api/credentials/sources HTTP ${res.status}`)
  return (await res.json()) as Record<string, CredentialSource>
}

// The backend explains a failed write in `detail` (e.g. no keychain backend).
export async function credentialError(res: Response, action: string): Promise<string> {
  const body = (await res.json().catch(() => null)) as { detail?: unknown } | null
  const fallback = `${action} failed (HTTP ${res.status})`
  return typeof body?.detail === "string" ? `${fallback}: ${body.detail}` : fallback
}
