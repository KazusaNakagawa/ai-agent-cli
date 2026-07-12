// Client-side file access via the File System Access API (Chromium). The user
// picks a local directory with a native dialog; we read/write through the
// returned handles — no server round-trip and no path configuration.

export type DirChild = {
  name: string
  kind: "file" | "directory"
  handle: FileSystemHandle
}

// Directories to skip when walking the tree for the file finder's index and
// for "expand all" — dependency/build/VCS noise that's rarely what someone
// is fuzzy-searching for, and that would otherwise make either operation
// scan tens of thousands of entries.
export const SKIP_DIR_NAMES = new Set([
  "node_modules",
  ".git",
  ".next",
  "dist",
  "build",
  "__pycache__",
  ".venv",
  "venv",
  ".cache",
  "coverage",
  ".turbo",
  ".pytest_cache",
])

export function isFileSystemAccessSupported(): boolean {
  return typeof window !== "undefined" && typeof window.showDirectoryPicker === "function"
}

/** Open the native folder picker and return the chosen directory handle. */
export async function pickDirectory(): Promise<FileSystemDirectoryHandle> {
  if (!isFileSystemAccessSupported()) {
    throw new Error("This browser does not support the File System Access API")
  }
  return window.showDirectoryPicker!({ mode: "readwrite" })
}

/** Order directory children: directories first, then case-insensitive by name. */
export function sortChildren(children: DirChild[]): DirChild[] {
  return [...children].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "directory" ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

/** List the immediate children of a directory handle, sorted. */
export async function listChildren(
  dir: FileSystemDirectoryHandle,
): Promise<DirChild[]> {
  const out: DirChild[] = []
  for await (const handle of dir.values()) {
    out.push({ name: handle.name, kind: handle.kind, handle })
  }
  return sortChildren(out)
}

export type IndexedFile = {
  path: string
  handle: FileSystemFileHandle
}

/**
 * Recursively walk a directory and return a flat list of every file, for the
 * fuzzy file finder. Skips SKIP_DIR_NAMES and stops after `maxFiles` so a
 * huge tree can't hang the UI.
 */
export async function buildFileIndex(
  root: FileSystemDirectoryHandle,
  maxFiles = 5000,
): Promise<IndexedFile[]> {
  const out: IndexedFile[] = []

  async function walk(dir: FileSystemDirectoryHandle, prefix: string): Promise<void> {
    for await (const handle of dir.values()) {
      if (out.length >= maxFiles) return
      const path = prefix ? `${prefix}/${handle.name}` : handle.name
      if (handle.kind === "directory") {
        if (SKIP_DIR_NAMES.has(handle.name)) continue
        await walk(handle as FileSystemDirectoryHandle, path)
      } else {
        out.push({ path, handle: handle as FileSystemFileHandle })
      }
    }
  }

  await walk(root, "")
  return out
}

/**
 * Resolve a markdown link's href against the path of the file it appears in,
 * for Workspace in-app navigation (see MarkdownView's `onLinkClick`). Returns
 * null for anything that isn't a same-workspace relative file link — absolute
 * URLs, other schemes (mailto:, etc.), and in-page-only anchors — so callers
 * fall back to normal browser link behavior for those.
 */
export function resolveWorkspaceLink(
  href: string,
  currentPath: string,
): string | null {
  if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return null
  if (href.startsWith("//")) return null
  if (href.startsWith("#")) return null
  // A leading "/" means site-root, not workspace-relative — treat it like
  // any other non-relative URL rather than silently rooting it under the
  // current directory.
  if (href.startsWith("/")) return null

  const [pathPart] = href.split("#")
  if (pathPart === "") return null

  const currentDir = currentPath.includes("/")
    ? currentPath.slice(0, currentPath.lastIndexOf("/"))
    : ""
  const segments = currentDir === "" ? [] : currentDir.split("/")

  for (const part of pathPart.split("/")) {
    if (part === "" || part === ".") continue
    if (part === "..") {
      segments.pop()
      continue
    }
    segments.push(part)
  }

  return segments.join("/")
}

export async function readFileHandle(
  handle: FileSystemFileHandle,
): Promise<string> {
  const file = await handle.getFile()
  return file.text()
}

/** Read a file as an object URL for `<img>` display. Caller must revoke it
 *  (via `URL.revokeObjectURL`) once no longer displayed, to avoid leaking. */
export async function readFileHandleAsObjectURL(
  handle: FileSystemFileHandle,
): Promise<string> {
  const file = await handle.getFile()
  return URL.createObjectURL(file)
}

export async function writeFileHandle(
  handle: FileSystemFileHandle,
  content: string,
): Promise<void> {
  const writable = await handle.createWritable()
  await writable.write(content)
  await writable.close()
}

/**
 * Ensure we hold read/write permission on a handle, prompting the user if the
 * permission was only persisted (e.g. restored from IndexedDB after reload).
 * Returns true when permission is granted.
 */
export async function ensureReadWrite(
  handle: FileSystemHandle,
): Promise<boolean> {
  const opts: FileSystemPermissionDescriptor = { mode: "readwrite" }
  if ((await handle.queryPermission?.(opts)) === "granted") return true
  return (await handle.requestPermission?.(opts)) === "granted"
}

// --- Persistence -----------------------------------------------------------
// Directory handles are structured-cloneable, so we stash the last-opened root
// in IndexedDB to restore it after a reload (re-prompting for permission).

const DB_NAME = "workspace"
const STORE = "handles"
const ROOT_KEY = "rootHandle"

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function withStore<T>(
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE, mode)
        const req = fn(tx.objectStore(STORE))
        req.onsuccess = () => resolve(req.result)
        req.onerror = () => reject(req.error)
      }),
  )
}

export async function saveRootHandle(
  handle: FileSystemDirectoryHandle,
): Promise<void> {
  await withStore("readwrite", (s) => s.put(handle, ROOT_KEY))
}

export async function loadRootHandle(): Promise<FileSystemDirectoryHandle | null> {
  try {
    const handle = await withStore<FileSystemDirectoryHandle | undefined>(
      "readonly",
      (s) => s.get(ROOT_KEY),
    )
    return handle ?? null
  } catch {
    return null
  }
}
