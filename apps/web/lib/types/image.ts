export type ImageAttachment = { url: string; path: string }

// Images one chat message may carry. Mirrors MAX_IMAGES_PER_MESSAGE in
// apps/python/web/routers/chat.py, which rejects anything over it.
export const MAX_IMAGES_PER_MESSAGE = 5
