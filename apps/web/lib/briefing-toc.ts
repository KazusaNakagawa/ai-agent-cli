import type { Element, Nodes, Root } from "hast"
import { defaultSchema } from "rehype-sanitize"
import { visit } from "unist-util-visit"

export interface TocEntry {
  id: string
  text: string
  level: number
}

// Slug used for heading ids. It only needs to be identical between extractToc
// and the rehype plugin (CSS.escape handles any leftover characters at query
// time), so we avoid \p{…} unicode escapes for broad target compatibility.
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\s]+/g, "-")
    .replace(/["'`()[\]{}<>（）「」、。,.!?！？:：;；/\\|#*~]/g, "")
}

// Build a slug-id generator that disambiguates repeated headings with a counter,
// matching the behaviour shared by extractToc and rehypeHeadingIds.
function createSlugger() {
  const seen = new Map<string, number>()
  return (text: string): string => {
    const base = slugify(text)
    const count = seen.get(base) ?? 0
    seen.set(base, count + 1)
    return count === 0 ? base : `${base}-${count}`
  }
}

// Extract text from a hast node recursively.
function hastText(node: Nodes): string {
  if (node.type === "text") return node.value
  if ("children" in node) return node.children.map(hastText).join("")
  return ""
}

// rehype plugin: attach an id to h1/h2/h3 before sanitization so the TOC can
// scroll to them.
export function rehypeHeadingIds() {
  return (tree: Root) => {
    const slug = createSlugger()
    visit(tree, "element", (node: Element) => {
      if (!/^h[1-3]$/.test(node.tagName)) return
      node.properties = { ...node.properties, id: slug(hastText(node)) }
    })
  }
}

// Allow id on heading elements so TOC scroll targets survive sanitization.
// clobberPrefix is cleared so heading ids match the slugs computed in extractToc
// (default prefixes them with "user-content-", breaking querySelector lookups).
export const sanitizeSchema = {
  ...defaultSchema,
  clobberPrefix: "",
  attributes: {
    ...defaultSchema.attributes,
    h1: [...(defaultSchema.attributes?.h1 ?? []), "id"],
    h2: [...(defaultSchema.attributes?.h2 ?? []), "id"],
    h3: [...(defaultSchema.attributes?.h3 ?? []), "id"],
  },
}

// Parse markdown for h1-h3 headings, mirroring the ids assigned by
// rehypeHeadingIds so the rendered TOC entries resolve to real DOM nodes.
export function extractToc(markdown: string): TocEntry[] {
  const slug = createSlugger()
  const entries: TocEntry[] = []
  for (const line of markdown.split("\n")) {
    const m = line.match(/^(#{1,3})\s+(.+)/)
    if (!m) continue
    const text = m[2].trim()
    entries.push({ id: slug(text), text, level: m[1].length })
  }
  return entries
}
