/** Markdown labels marking who wrote each part of a saved Q&A block. */
export const USER_LABEL = "**You:**"
export const AI_LABEL = "**AI:**"

// Backslash-escaped forms render identically in Markdown but are not matched
// as turn boundaries, so a body line that is just a label survives a round trip.
const ESCAPES: [label: string, escaped: string][] = [USER_LABEL, AI_LABEL].map((label) => [
  label,
  label.replaceAll("*", "\\*"),
])

function escapeLabels(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      const hit = ESCAPES.find(([label]) => line.trim() === label)
      return hit ? line.replace(hit[0], hit[1]) : line
    })
    .join("\n")
}

function unescapeLabels(lines: string[]): string {
  return lines
    .map((line) => {
      const hit = ESCAPES.find(([, escaped]) => line.trim() === escaped)
      return hit ? line.replace(hit[1], hit[0]) : line
    })
    .join("\n")
}

/**
 * Format one brainstorm turn as role-labelled Markdown for journal storage.
 *
 * Saved entries are plain Markdown files (also synced to Notion), so without
 * labels a question and its answer read as one undifferentiated block. The
 * labels keep the transcript readable anywhere the raw Markdown is viewed.
 */
export function formatQaBlock(question: string, answer: string): string {
  return `${USER_LABEL}\n\n${escapeLabels(question)}\n\n${AI_LABEL}\n\n${escapeLabels(answer)}`
}

export interface QaTurn {
  question: string
  answer: string
}

/**
 * Split a saved entry back into turns so it can render as chat bubbles.
 *
 * `preamble` is whatever precedes the first `**You:**` line (e.g. the
 * `## HH:MM:SS` heading). Returns null when the entry has no role labels
 * (legacy free-form entries), so the caller can fall back to plain Markdown.
 */
export function parseQaTranscript(
  md: string,
): { preamble: string; turns: QaTurn[] } | null {
  const lines = md.split("\n")
  const userIdx = lines.flatMap((l, i) => (l.trim() === USER_LABEL ? [i] : []))
  if (userIdx.length === 0) return null

  const preamble = lines.slice(0, userIdx[0]).join("\n").trim()
  const turns = userIdx.map((start, n) => {
    const end = n + 1 < userIdx.length ? userIdx[n + 1] : lines.length
    const block = lines.slice(start + 1, end)
    const aiAt = block.findIndex((l) => l.trim() === AI_LABEL)
    const question = unescapeLabels(aiAt === -1 ? block : block.slice(0, aiAt))
    const answer = aiAt === -1 ? "" : unescapeLabels(block.slice(aiAt + 1))
    // Turns appended to an entry are separated by a `---` rule; drop it so it
    // doesn't render inside the answer bubble.
    return { question: question.trim(), answer: answer.trim().replace(/\n*-{3,}$/, "").trim() }
  })
  return { preamble, turns }
}
