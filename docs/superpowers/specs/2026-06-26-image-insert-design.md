# Image Insert Feature Design

**Issue:** #308
**Date:** 2026-06-26

## Goal

Add a shared image-insert capability to all text-input areas in the web app (QA chat, Journal "Record today", Journal Brainstorm). Users can insert images via a "+" button (file picker) or drag-and-drop. Inserted images are stored locally and rendered inline in Markdown previews.

## Architecture

```
[textarea + ImageInsertButton / drag-and-drop]
        ↓ File (multipart/form-data)
[POST /api/images/upload  (Next.js Route Handler)]
        ↓ fs.writeFile
[apps/python/input/images/YYYY-MM-DD/<uuid>.<ext>]
        ↑ GET /api/images/YYYY-MM-DD/<filename>
[<img> rendered in Markdown preview]
```

## Shared Components & Hooks

### `components/ui/ImageInsertButton.tsx`

- Renders a `+` icon button below the textarea
- On click: opens OS file picker (accept `image/*`)
- On file selected: POST to `/api/images/upload`, then call `onInsert(markdownSnippet)`
- Props:
  ```ts
  type Props = {
    onInsert: (snippet: string) => void  // e.g. "![image](/api/images/2026-06-26/uuid.png)"
    disabled?: boolean
  }
  ```

### `hooks/useImageDrop.ts`

- Attaches `dragover` / `drop` event listeners to a given textarea ref
- On drop: same upload flow → call `onInsert(markdownSnippet)`
- Returns `{ isDragging }` for optional visual feedback (e.g. border highlight)
- Signature:
  ```ts
  function useImageDrop(
    ref: RefObject<HTMLTextAreaElement>,
    onInsert: (snippet: string) => void
  ): { isDragging: boolean }
  ```

Both components share a single `uploadImage(file: File): Promise<string>` utility in `lib/imageUpload.ts` that handles the fetch POST and returns the Markdown snippet.

## API Routes

### POST `/api/images/upload`

- Accepts `multipart/form-data` with a single `file` field
- Validates: extension in `[jpg, jpeg, png, gif, webp]`, size ≤ 5 MB
- Saves to `apps/python/input/images/YYYY-MM-DD/<uuid>.<ext>`
- Creates the date directory if it does not exist
- Returns `{ url: "/api/images/YYYY-MM-DD/<uuid>.<ext>" }` on success
- Returns `{ error: string }` with appropriate HTTP status on failure (400 for bad type/size, 500 for write error)

### GET `/api/images/[...path]`

- Maps `/api/images/<rest>` → `apps/python/input/images/<rest>`
- Streams the file with correct `Content-Type`
- Returns 404 if file does not exist
- Path traversal guard: resolved path must start with the `input/images/` absolute path

## Integration Points

| File | Change |
|---|---|
| `components/chat/ChatComposer.tsx` | Add `ImageInsertButton` below textarea; apply `useImageDrop` to textarea ref; insert snippet at cursor |
| `components/screens/JournalScreen.tsx` | Same for "Record today" textarea and Brainstorm textarea (two separate instances) |

### Cursor insertion helper

A small utility `insertAtCursor(ref, snippet)` moves the textarea value and selection point so the snippet lands at the caret:

```ts
function insertAtCursor(
  ref: RefObject<HTMLTextAreaElement>,
  setValue: (v: string) => void,
  snippet: string
): void
```

This is called by both `onInsert` handlers.

## Constraints

- Allowed types: `jpg`, `jpeg`, `png`, `gif`, `webp` (validated server-side by extension + MIME sniff)
- Max size: 5 MB (checked via `Content-Length` and stream byte count)
- Storage path: `apps/python/input/images/YYYY-MM-DD/<uuid>.<ext>` (gitignored)
- URL pattern: `/api/images/YYYY-MM-DD/<uuid>.<ext>`
- Markdown snippet: `![image](/api/images/YYYY-MM-DD/<uuid>.<ext>)`

## Error Handling

| Scenario | Behavior |
|---|---|
| Non-image file selected | Button: show inline error below button; drop: ignore silently or brief toast |
| File > 5 MB | Inline error "Image must be under 5 MB" |
| Upload fails (network / write) | Inline error "Upload failed, please try again" |
| File not found on GET | 404 response |
| Path traversal attempt | 400 response |

## Out of Scope

- Generic file attachment (tracked separately in #309)
- Cloud storage (local only for now; URL abstraction makes migration straightforward)
- Image resizing / optimization
- Paste-from-clipboard image insertion (potential follow-up)
