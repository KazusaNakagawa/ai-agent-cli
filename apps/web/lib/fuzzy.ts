// A small VSCode-Quick-Open-style fuzzy matcher: query characters must appear
// in order (case-insensitive) inside the target string. Score rewards
// contiguous runs and matches right after a path separator or at the start,
// so "wscn" ranks "components/workspace/FileTree.tsx" above an unrelated
// file that merely contains those letters scattered far apart.

/** Returns a match score, or null when the query isn't a subsequence of target. */
export function matchScore(query: string, target: string): number | null {
  if (query.length === 0) return 0
  const q = query.toLowerCase()
  const t = target.toLowerCase()
  let qi = 0
  let score = 0
  let prevMatched = false
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      score += prevMatched ? 3 : 1
      if (ti === 0 || t[ti - 1] === "/") score += 2
      prevMatched = true
      qi++
    } else {
      prevMatched = false
    }
  }
  return qi === q.length ? score : null
}

/** Fuzzy-filter and rank `items` by `query`, highest score first. */
export function fuzzySearch<T>(
  items: T[],
  query: string,
  getText: (item: T) => string,
  limit = 20,
): T[] {
  if (query.trim() === "") return items.slice(0, limit)
  const scored: { item: T; score: number }[] = []
  for (const item of items) {
    const score = matchScore(query, getText(item))
    if (score !== null) scored.push({ item, score })
  }
  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, limit).map((m) => m.item)
}
