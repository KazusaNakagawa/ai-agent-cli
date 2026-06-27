// A generic (non-image) file attachment. `name` is the original filename used
// to render the inserted Markdown link `[name](url)`.
export type FileAttachment = { url: string; path: string; name: string }
