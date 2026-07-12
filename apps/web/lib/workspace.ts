import { promises as fs } from "node:fs"
import { isAbsolute, join, normalize, relative, resolve, sep } from "node:path"

// Root of the browsable workspace. Overridable via WORKSPACE_ROOT; defaults to
// the repo's `docs/` directory (real markdown content for the trial). All file
// access is confined to this root — see `resolveWithinRoot`.
export function workspaceRoot(): string {
  const configured = process.env.WORKSPACE_ROOT
  if (configured) return resolve(configured)
  // cwd is apps/web when Next.js runs; the repo root is two levels up.
  return resolve(process.cwd(), "..", "..", "docs")
}

export type TreeEntry = {
  name: string
  path: string // POSIX-style path relative to the workspace root
  type: "dir" | "file"
}

/**
 * Resolve a caller-supplied relative path against the workspace root, rejecting
 * any path that would escape the root (`..`, absolute paths, symlink-style
 * traversal). Returns the absolute on-disk path.
 * @throws Error when the path escapes the root.
 */
export function resolveWithinRoot(root: string, relPath: string): string {
  if (isAbsolute(relPath)) {
    throw new Error("absolute paths are not allowed")
  }
  const normalizedRoot = resolve(root)
  const target = resolve(normalizedRoot, normalize(relPath))
  const rel = relative(normalizedRoot, target)
  if (rel === "" ) return target // the root itself
  if (rel.startsWith("..") || rel.split(sep)[0] === "..") {
    throw new Error("path escapes the workspace root")
  }
  return target
}

function toPosix(relPath: string): string {
  return relPath.split(sep).join("/")
}

/** List the immediate children of a directory (relative to the root). */
export async function listDir(root: string, relDir = ""): Promise<TreeEntry[]> {
  const abs = resolveWithinRoot(root, relDir)
  const dirents = await fs.readdir(abs, { withFileTypes: true })
  const entries: TreeEntry[] = dirents
    .filter((d) => d.isDirectory() || d.isFile())
    .map((d) => ({
      name: d.name,
      path: toPosix(join(relDir, d.name)),
      type: d.isDirectory() ? ("dir" as const) : ("file" as const),
    }))
  // Directories first, then alphabetical by name.
  entries.sort((a, b) => {
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1
    return a.name.localeCompare(b.name)
  })
  return entries
}

/** Read a UTF-8 text file relative to the root. */
export async function readFile(root: string, relPath: string): Promise<string> {
  const abs = resolveWithinRoot(root, relPath)
  return fs.readFile(abs, "utf8")
}

/** Write a UTF-8 text file relative to the root, creating parent dirs. */
export async function writeFile(
  root: string,
  relPath: string,
  content: string,
): Promise<void> {
  const abs = resolveWithinRoot(root, relPath)
  await fs.mkdir(join(abs, ".."), { recursive: true })
  await fs.writeFile(abs, content, "utf8")
}
