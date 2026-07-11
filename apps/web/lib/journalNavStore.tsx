"use client"
import { usePathname } from "next/navigation"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
  type ReactNode,
} from "react"

import { useJournalChatJobState } from "@/lib/journalChatJobStore"
import { useJournalChatState } from "@/lib/journalChatStore"

/**
 * Shared Journal navigation state, lifted out of JournalScreen so the entry
 * list (rendered in the global Sidebar rail) and the entry body (rendered in
 * the main content area) can live in separate parts of the tree while sharing
 * one selection. Provider is nested inside the journal chat providers so it
 * can drive their reset/entry-binding when the selection changes.
 */

export type JournalEntry = {
  id: string
  date: string
  size: number
  item: string
  notion_url: string
}

export type JournalNavContextValue = {
  entries: JournalEntry[]
  sortedEntries: JournalEntry[]
  entriesError: string | null
  trash: JournalEntry[]
  showTrash: boolean
  selected: string | null
  composing: boolean
  trashPreview: string | null
  content: string
  trashContent: string
  panelOpen: boolean
  selectedMeta: JournalEntry | undefined
  trashMeta: JournalEntry | undefined
  /** Bumped on every entry switch/compose/trash toggle; read by the body's
   *  brainstorm pending-turn logic to know when its view is still current. */
  viewEpoch: MutableRefObject<number>
  loadDates: () => Promise<JournalEntry[] | undefined>
  loadEntry: (entryId: string) => Promise<void>
  loadTrashEntry: (entryId: string) => Promise<void>
  loadTrash: () => Promise<void>
  deleteEntry: (entryId: string) => Promise<void>
  restoreEntry: (entryId: string) => Promise<void>
  purgeEntry: (entryId: string) => Promise<void>
  toggleTrash: () => void
  startCompose: () => void
  closePanel: () => void
}

const JournalNavContext = createContext<JournalNavContextValue | null>(null)

export function JournalNavProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [entriesError, setEntriesError] = useState<string | null>(null)
  const [trash, setTrash] = useState<JournalEntry[]>([])
  const [showTrash, setShowTrash] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const [content, setContent] = useState("")
  const entryReqSeq = useRef(0)
  // Read-only preview of a trashed entry (so the user can inspect before
  // restoring or permanently deleting it).
  const [trashPreview, setTrashPreview] = useState<string | null>(null)
  const [trashContent, setTrashContent] = useState("")
  const trashReqSeq = useRef(0)

  const journalChat = useJournalChatState()
  const job = useJournalChatJobState()
  const pathname = usePathname()
  const onJournal = pathname === "/journal" || Boolean(pathname?.startsWith("/journal/"))

  // Bumped on every entry switch/compose/trash toggle so a pending job
  // started under a previous view doesn't reappear if the id-matching
  // heuristic in the body can't distinguish "same view" from "new view"
  // (e.g. two successive new-entry sessions both have targetEntryId=null).
  const viewEpoch = useRef(0)

  const loadDates = useCallback(async () => {
    try {
      setEntriesError(null)
      const res = await fetch("/api/journal", { cache: "no-store" })
      if (!res.ok) {
        setEntriesError(`Failed to load entries (HTTP ${res.status})`)
        return
      }
      const data = (await res.json()) as { entries: JournalEntry[] }
      setEntries(data.entries)
      return data.entries
    } catch (e) {
      setEntriesError(`Failed to load entries: ${String(e)}`)
    }
  }, [])

  const loadEntry = useCallback(
    async (entryId: string) => {
      const seq = ++entryReqSeq.current
      setSelected(entryId)
      setComposing(false)
      setShowTrash(false)
      setTrashPreview(null)
      viewEpoch.current += 1
      // Bind the brainstorm session to this entry so subsequent turns append here.
      journalChat.reset()
      journalChat.setEntryId(entryId)
      // Clear immediately so the previous entry's body can't render under the
      // new header while the fetch is in flight (or if it fails).
      setContent("")
      let res: Response
      try {
        res = await fetch(`/api/journal/${entryId}`, { cache: "no-store" })
      } catch {
        return
      }
      if (seq !== entryReqSeq.current) return
      if (!res.ok) return
      const data = (await res.json()) as { content: string }
      if (seq !== entryReqSeq.current) return
      setContent(data.content)
    },
    [journalChat],
  )

  const loadTrashEntry = useCallback(async (entryId: string) => {
    const seq = ++trashReqSeq.current
    setTrashPreview(entryId)
    setTrashContent("")
    let res: Response
    try {
      res = await fetch(`/api/journal/trash/${entryId}`, { cache: "no-store" })
    } catch {
      return
    }
    if (seq !== trashReqSeq.current) return
    if (!res.ok) return
    const data = (await res.json()) as { content: string }
    if (seq !== trashReqSeq.current) return
    setTrashContent(data.content)
  }, [])

  const loadTrash = useCallback(async () => {
    try {
      setEntriesError(null)
      const res = await fetch("/api/journal/trash", { cache: "no-store" })
      if (!res.ok) {
        setEntriesError(`Failed to load trash (HTTP ${res.status})`)
        return
      }
      const data = (await res.json()) as { entries: JournalEntry[] }
      setTrash(data.entries)
    } catch (e) {
      setEntriesError(`Failed to load trash: ${String(e)}`)
    }
  }, [])

  // Scoped to Journal routes — Provider is mounted globally in MainLayout so
  // the journal chat providers stay available across navigation, but the
  // network fetch itself should only fire while the user is actually on
  // Journal (avoids an unnecessary /api/journal call on every other route).
  useEffect(() => {
    if (!onJournal) return
    void loadDates()
  }, [loadDates, onJournal])

  // Auto-open the compose panel on mount if there is persisted chat state to show.
  // The stores hydrate from sessionStorage in their own effects, so this effect reads
  // their current values and opens the panel once they are populated (if not already open).
  useEffect(() => {
    const hasChatState = journalChat.turns.length > 0 || job.jobId !== null
    const panelClosed = selected === null && !composing && trashPreview === null
    if (hasChatState && panelClosed) {
      setComposing(true)
    }
  }, [journalChat.turns.length, job.jobId, selected, composing, trashPreview])

  const closePanel = useCallback(() => {
    setSelected(null)
    setComposing(false)
    setTrashPreview(null)
    journalChat.setEntryId(null)
  }, [journalChat])

  const startCompose = useCallback(() => {
    setSelected(null)
    setTrashPreview(null)
    setShowTrash(false)
    viewEpoch.current += 1
    journalChat.reset()
    setComposing(true)
  }, [journalChat])

  const deleteEntry = useCallback(
    async (entryId: string) => {
      try {
        const res = await fetch(`/api/journal/${entryId}`, { method: "DELETE" })
        if (!res.ok) {
          setEntriesError(`Delete failed (HTTP ${res.status})`)
          return
        }
        // Collapse the panel if the open entry was the one removed.
        setSelected((cur) => (cur === entryId ? null : cur))
        await loadDates()
      } catch (e) {
        setEntriesError(`Delete failed: ${String(e)}`)
      }
    },
    [loadDates],
  )

  const restoreEntry = useCallback(
    async (entryId: string) => {
      try {
        const res = await fetch(`/api/journal/${entryId}/restore`, { method: "POST" })
        if (!res.ok) {
          setEntriesError(`Restore failed (HTTP ${res.status})`)
          return
        }
        setTrashPreview((cur) => (cur === entryId ? null : cur))
        await Promise.all([loadDates(), loadTrash()])
      } catch (e) {
        setEntriesError(`Restore failed: ${String(e)}`)
      }
    },
    [loadDates, loadTrash],
  )

  const purgeEntry = useCallback(
    async (entryId: string) => {
      try {
        const res = await fetch(`/api/journal/${entryId}?purge=true`, { method: "DELETE" })
        if (!res.ok) {
          setEntriesError(`Permanent delete failed (HTTP ${res.status})`)
          return
        }
        setTrashPreview((cur) => (cur === entryId ? null : cur))
        await loadTrash()
      } catch (e) {
        setEntriesError(`Permanent delete failed: ${String(e)}`)
      }
    },
    [loadTrash],
  )

  // Toggle the trash view, loading its contents when opening. Side effects stay
  // out of the state updater: compute `next`, set it, then conditionally load.
  const toggleTrash = useCallback(() => {
    const next = !showTrash
    setShowTrash(next)
    // Switching views closes any open panel/preview so the two modes don't mix.
    setSelected(null)
    setComposing(false)
    setTrashPreview(null)
    viewEpoch.current += 1
    journalChat.reset()
    if (next) void loadTrash()
  }, [showTrash, loadTrash, journalChat])

  const sortedEntries = useMemo(
    () => [...entries].sort((a, b) => b.id.localeCompare(a.id)),
    [entries],
  )
  const selectedMeta = sortedEntries.find((e) => e.id === selected)
  const trashMeta = trash.find((e) => e.id === trashPreview)
  const panelOpen = selected !== null || composing || trashPreview !== null

  const value = useMemo<JournalNavContextValue>(
    () => ({
      entries,
      sortedEntries,
      entriesError,
      trash,
      showTrash,
      selected,
      composing,
      trashPreview,
      content,
      trashContent,
      panelOpen,
      selectedMeta,
      trashMeta,
      viewEpoch,
      loadDates,
      loadEntry,
      loadTrashEntry,
      loadTrash,
      deleteEntry,
      restoreEntry,
      purgeEntry,
      toggleTrash,
      startCompose,
      closePanel,
    }),
    [
      entries,
      sortedEntries,
      entriesError,
      trash,
      showTrash,
      selected,
      composing,
      trashPreview,
      content,
      trashContent,
      panelOpen,
      selectedMeta,
      trashMeta,
      loadDates,
      loadEntry,
      loadTrashEntry,
      loadTrash,
      deleteEntry,
      restoreEntry,
      purgeEntry,
      toggleTrash,
      startCompose,
      closePanel,
    ],
  )

  return <JournalNavContext.Provider value={value}>{children}</JournalNavContext.Provider>
}

export function useJournalNav(): JournalNavContextValue {
  const ctx = useContext(JournalNavContext)
  if (!ctx) {
    throw new Error("useJournalNav must be used inside <JournalNavProvider>")
  }
  return ctx
}
