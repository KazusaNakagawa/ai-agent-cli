/** Markdown labels marking who wrote each part of a saved Q&A block. */
export const USER_LABEL = "**You:**"
export const AI_LABEL = "**AI:**"

/**
 * Format one brainstorm turn as role-labelled Markdown for journal storage.
 *
 * Saved entries are plain Markdown files (also synced to Notion), so without
 * labels a question and its answer read as one undifferentiated block. The
 * labels keep the transcript readable anywhere the raw Markdown is viewed.
 */
export function formatQaBlock(question: string, answer: string): string {
  return `${USER_LABEL}\n\n${question}\n\n${AI_LABEL}\n\n${answer}`
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
    const question = (aiAt === -1 ? block : block.slice(0, aiAt)).join("\n")
    const answer = aiAt === -1 ? "" : block.slice(aiAt + 1).join("\n")
    // Turns appended to an entry are separated by a `---` rule; drop it so it
    // doesn't render inside the answer bubble.
    return { question: question.trim(), answer: answer.trim().replace(/\n*-{3,}$/, "").trim() }
  })
  return { preamble, turns }
}
