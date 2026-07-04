"use client"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"

type Props = { initial: Record<string, boolean> }

type Field = { name: string; label: string; secret: boolean }

// Mirrors apps/python/src/credentials.ALLOWED_KEYS so the UI lists exactly
// what the backend will accept.
const FIELDS: Field[] = [
  { name: "DISCORD_TOKEN", label: "Discord bot token", secret: true },
  { name: "CHANNEL_ID", label: "Discord channel id", secret: false },
  { name: "NOTION_API_KEY", label: "Notion integration key", secret: true },
  { name: "NOTION_DATABASE_ID", label: "Notion database id", secret: false },
  { name: "NOTION_DATABASE_ID_JOURNAL", label: "Notion journal database id", secret: false },
  { name: "ANTHROPIC_API_KEY", label: "Anthropic API key", secret: true },
]

export function CredentialsForm({ initial }: Props) {
  const router = useRouter()
  const [status, setStatus] = useState<Record<string, boolean>>(initial)
  const [editing, setEditing] = useState<Field | null>(null)
  const [draft, setDraft] = useState("")
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const openEdit = (f: Field) => {
    setEditing(f)
    setDraft("")
    setError(null)
  }
  const closeEdit = () => {
    setEditing(null)
    setDraft("")
  }

  const save = async () => {
    if (!editing) return
    const value = draft.trim()
    if (value === "") {
      setError("Value is required")
      return
    }
    setBusy(editing.name)
    setError(null)
    const res = await fetch(
      `/api/credentials/${encodeURIComponent(editing.name)}`,
      {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ value }),
      },
    )
    setBusy(null)
    if (!res.ok) {
      setError(`PUT failed (HTTP ${res.status})`)
      return
    }
    setStatus((prev) => ({ ...prev, [editing.name]: true }))
    closeEdit()
    router.refresh()
  }

  const remove = async (name: string) => {
    setBusy(name)
    setError(null)
    const res = await fetch(`/api/credentials/${encodeURIComponent(name)}`, {
      method: "DELETE",
    })
    setBusy(null)
    if (!res.ok) {
      setError(`DELETE failed (HTTP ${res.status})`)
      return
    }
    setStatus((prev) => ({ ...prev, [name]: false }))
    router.refresh()
  }

  return (
    <div className="space-y-3">
      {FIELDS.map((f) => {
        const set = Boolean(status[f.name])
        return (
          <Card key={f.name}>
            <CardContent className="flex items-center justify-between gap-4 pt-6">
              <div className="space-y-1">
                <p className="font-medium">{f.label}</p>
                <p className="text-xs font-mono text-muted-foreground">
                  {f.name}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Badge
                  variant={set ? "default" : "secondary"}
                  data-testid={`status-${f.name}`}
                >
                  {set ? "Set" : "Not set"}
                </Badge>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openEdit(f)}
                  disabled={busy === f.name}
                  data-testid={`update-${f.name}`}
                >
                  {set ? "Update" : "Set"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void remove(f.name)}
                  disabled={!set || busy === f.name}
                  data-testid={`delete-${f.name}`}
                >
                  Delete
                </Button>
              </div>
            </CardContent>
          </Card>
        )
      })}

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) closeEdit()
        }}
      >
        <DialogContent>
          {editing && (
            <>
              <DialogHeader>
                <DialogTitle>
                  {status[editing.name] ? "Update" : "Set"} {editing.label}
                </DialogTitle>
                <DialogDescription>
                  Stored in the OS keychain under
                  <code className="ml-1 font-mono">{editing.name}</code>.
                </DialogDescription>
              </DialogHeader>
              <Input
                autoFocus
                type={editing.secret ? "password" : "text"}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={
                  editing.secret ? "••••••••••" : "Paste the value"
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    void save()
                  }
                }}
                data-testid="credential-draft"
              />
              {error && (
                <p
                  className="text-sm text-destructive"
                  data-testid="credential-error"
                >
                  {error}
                </p>
              )}
              <DialogFooter>
                <Button variant="ghost" onClick={closeEdit}>
                  Cancel
                </Button>
                <Button
                  onClick={() => void save()}
                  disabled={busy === editing.name}
                  data-testid="credential-save"
                >
                  Save
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {error && !editing && (
        <p className="text-sm text-destructive" data-testid="generic-error">
          {error}
        </p>
      )}
    </div>
  )
}
