# Journal Chat State Persistence Across Navigation — Design

Issue: #350

## Problem

`JournalScreen`'s brainstorm chat (pending "Thinking…" request and turn
history) lives in component-local `useState`. Navigating to another page
unmounts `JournalScreen`, losing the in-flight request and the visible
conversation. Returning to Journal shows an empty panel even though the
backend chat job may have completed (or is still running) in the meantime.

## Goal

Keep the Journal chat's turn history and in-flight job alive across page
navigation, by lifting them out of `JournalScreen` into providers mounted at
the `(main)` layout level — mirroring the existing split used for the main
Q&A chat (`chatStore.tsx` + `chatJobStore.tsx` + `createJobStoreProvider`).

## Architecture

### `apps/web/lib/journalChatStore.tsx` (new)

Holds **committed** turns (`{ question: string; answer: string }[]`) plus the
`entryId` the current brainstorm session is bound to. Persisted to
`sessionStorage` (FIFO-capped), mirroring `chatStore.tsx`'s message list.

```ts
type JournalChatStateContextValue = {
  turns: Turn[]
  entryId: string | null
  addTurn: (turn: Turn) => void
  setEntryId: (id: string | null) => void
  reset: () => void
}
```

`reset()` clears turns + entryId — called when the user starts composing a
new entry, opens a different entry, or toggles trash (same trigger points
`JournalScreen` already resets `turns` at today).

### `apps/web/lib/journalChatJobStore.tsx` (new)

A `createJobStoreProvider` instance tracking the **in-flight** brainstorm
job:

```ts
type JournalChatJobState = {
  jobId: string | null
  status: "idle" | "pending" | "running" | "done" | "failed"
  question: string
  targetEntryId: string | null  // snapshot of entryId at job start
  imagePath: string | null
  assistantContent: string       // not persisted, rebuilt from stream replay
  error: string | null
  saved: boolean                 // completion has been committed+saved
}
```

- `start({question, imagePath, targetEntryId})`: `POST /api/journal/chat`,
  same shape as `chatJobStore.start` (handle non-2xx, missing `job_id`).
- `watch(jobId, ctx)`: `GET /api/chat/{jobId}/stream`, accumulate
  `assistantContent` via `readSseEvents` (reuse `lib/sse.ts`). No
  `stale_session` handling — the journal chat backend route
  (`POST /journal/chat` in `chat.py`) does not use the retry-on-stale-session
  mechanism the main chat does.
- `isPersistable`: `jobId` present && (`in-flight` || `!saved`) — so a job
  that finished while no one was watching still survives until the
  completion effect (below) processes it.

### `apps/web/components/journal/JournalChatBridge.tsx` (new)

A small, always-mounted component (rendered once inside both providers in
`(main)/layout.tsx`) that owns the completion side effect:

```ts
useEffect(() => {
  if (job.status !== "done" || job.saved) return
  void (async () => {
    const qaBlock = formatQaBlock(job.question, job.assistantContent)
    const saveRes = job.targetEntryId
      ? await fetch(`/api/journal/${job.targetEntryId}`, { method: "PATCH", ... })
      : await fetch("/api/journal", { method: "POST", ... })
    if (!saveRes.ok) {
      job.setError(`Auto-save failed (HTTP ${saveRes.status})`)
      return
    }
    if (!job.targetEntryId) {
      const saved = await saveRes.json()
      journalChat.setEntryId(saved.id)
    }
    journalChat.addTurn({ question: job.question, answer: job.assistantContent })
    job.reset()
  })()
}, [job.status, job.saved])
```

Because this bridge is mounted at layout level (like `ChatJobStateProvider`
already is), the save happens as soon as the stream completes — the user
does not need to be on the Journal page for the exchange to be persisted
server-side.

Renders `null` — no UI.

## Data Flow

1. `JournalScreen.brainstorm()` calls `journalChatJobStore.startJob({
   question, image_path: brainstormImage?.path, targetEntryId:
   journalChatStore.entryId })` instead of managing its own fetch/turns.
2. Rendered transcript = `[...journalChatStore.turns, ...(job.jobId ? [{
   question: job.question, answer: job.assistantContent }] : [])]`.
3. Navigating away leaves the layout-level providers + `JournalChatBridge`
   running; the SSE stream keeps draining and, on completion, the bridge
   saves + commits the turn regardless of which page is active.
4. Returning to Journal re-renders `JournalScreen` from the (unchanged)
   store state — no re-fetch needed, no duplicate turns (turns are only
   appended once, by the bridge, guarded by `saved`).
5. Cancel ("Stop" button / Esc): `DELETE /api/chat/{jobId}` then
   `journalChatJobStore.reset()`. `createJobStoreProvider`'s watch effect
   aborts its internal `AbortController` automatically when `jobId` changes
   (existing factory behavior) — no separate `AbortController` needed in the
   Journal code.
6. Entry-switch/new-entry/trash-toggle in `JournalScreen` call
   `journalChatStore.reset()` (turns) but do NOT touch an in-flight job —
   matches current behavior where switching entries mid-brainstorm doesn't
   cancel it (existing `targetEntryId` snapshot semantics preserved via
   `job.targetEntryId`, now a stored field instead of a `useRef`).

## Error Handling

- `status === "failed"`: `job.error` surfaces as `chatError` in
  `JournalScreen`. Not committed to `journalChatStore`. User can retype and
  resend; the failed job is cleared (`reset()`) when a new one starts.
- Auto-save failure (bridge's PATCH/POST fails): `job.error` set (via a
  `setError`-style helper on the job store), `saved` stays `false` so the
  transcript still shows the "Thinking…" turn (now showing an error) instead
  of silently vanishing. No automatic retry.

## Testing

- Unit test `journalChatJobStore` start/watch/reconnect (mirror
  `tests/chat-job-store.test.tsx`).
- Extend `tests/journal-cancel.test.tsx` (or a new
  `journal-chat-persist.test.tsx`): start a brainstorm, unmount
  `JournalScreen`, resolve the stream, remount, assert the completed turn is
  visible and no duplicate turn exists.
- Verify cancel still works end-to-end (DELETE fired, job reset, question
  restored for re-edit).

## Out of Scope

- Persisting/restoring which entry was `selected`/`composing` across
  navigation (confirmed with user: only chat state, not entry-list
  selection, needs to survive).
- Multiple concurrent Journal brainstorm sessions (single global job store,
  same constraint as the existing main chat).
