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
