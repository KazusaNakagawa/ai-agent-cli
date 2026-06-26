# Image Vision Feature Design

**Issue:** #311
**Date:** 2026-06-26
**Replaces:** 2026-06-26-image-insert-design.md (#308, closed)

## Goal

Allow users to attach images to QA chat and Journal Brainstorm prompts. The image is stored locally and sent to Claude as a base64 vision content block via `claude -p -` stdin, so Claude can actually see and discuss the image. A shared "+" button and drag-and-drop interface handles upload in both text areas.

## Problem with #308 design

`![image](url)` was inserted as Markdown text. Claude received only the URL string and could not fetch or read it.

## Approach: `claude -p -` stdin JSON (cli mode)

Base64-encode the image locally and pipe a multimodal JSON message to `claude`'s stdin. This uses the existing OAuth session — no API key required. The backend Popen call already supports stdin; only the message format changes when an image is attached.

## Architecture

```
[+ button / drag-and-drop]
        ↓ File
[ImageInsertButton / useImageDrop]
        ↓ POST multipart/form-data
[POST /api/images/upload]  →  saves to apps/python/input/images/YYYY-MM-DD/<uuid>.<ext>
        ↓ returns { url, path }
[Frontend stores path; shows thumbnail preview]
        ↓ on Send: { question, image_path? }
[POST /api/chat  OR  POST /api/journal/chat]
        ↓ Python backend
    image_path present → run_claude_with_image(prompt, image_path)
                           → base64 encode → JSON message → stdin → claude -p -
    image_path absent  → existing run_claude(prompt) unchanged
        ↓ SSE stream back to browser
[Claude responds with image-aware answer]
```

## File Map

| Action | Path | Change |
|---|---|---|
| Modify | `apps/web/app/api/images/upload/route.ts` | Also return `path` (absolute local path) alongside `url` |
| Modify | `apps/web/lib/imageUpload.ts` | Return `{ url, path }` instead of Markdown snippet |
| Modify | `apps/web/components/ui/ImageInsertButton.tsx` | Store `{ url, path }`; show thumbnail; expose via `onAttach` callback instead of `onInsert` |
| Modify | `apps/web/lib/hooks/useImageDrop.ts` | Fix D&D bug: add `dragenter` + `stopPropagation`; call `onAttach` instead of `onInsert` |
| Modify | `apps/web/components/chat/ChatComposer.tsx` | Hold `attachedImage: { url, path } \| null`; include `image_path` in POST body; show thumbnail + remove button |
| Modify | `apps/web/components/screens/JournalScreen.tsx` | Same pattern for both "Record today" and Brainstorm textareas |
| Modify | `apps/python/src/claude_runner.py` | Add `run_claude_with_image(prompt, image_path, label, ...)` |
| Modify | `apps/python/web/routers/chat.py` | Add `image_path: str \| None = None` to `ChatBody` and `JournalChatBody`; route to vision variant when present |
| Keep | `apps/web/app/api/images/upload/route.ts` (base) | Upload + save logic unchanged |
| Keep | `apps/web/app/api/images/[...path]/route.ts` | Serve route unchanged (used for thumbnail preview) |

## API Changes

### `POST /api/images/upload` response

```ts
// Before
{ url: string }

// After
{ url: string; path: string }
// url  = "/api/images/YYYY-MM-DD/<uuid>.<ext>"  (for <img src>)
// path = "/abs/path/to/apps/python/input/images/YYYY-MM-DD/<uuid>.<ext>"
```

### `POST /api/chat` body

```ts
// Before
{ date: string; question: string }

// After
{ date: string; question: string; image_path?: string }
```

### `POST /api/journal/chat` body

```ts
// Before
{ question: string; days?: number }

// After
{ question: string; days?: number; image_path?: string }
```

## Component Interfaces

### `ImageInsertButton`

```ts
type Props = {
  onAttach: (image: { url: string; path: string }) => void
  disabled?: boolean
}
```

No longer calls `onInsert` with a Markdown snippet. Calls `onAttach` with the upload result.

### `useImageDrop`

```ts
function useImageDrop(
  ref: RefObject<HTMLTextAreaElement>,
  onAttach: (image: { url: string; path: string }) => void
): { isDragging: boolean }
```

#### D&D bug fix (browser opens image in new tab)

Add `dragenter` and use `stopPropagation()` on all three handlers:

```ts
el.addEventListener("dragenter", (e) => { e.preventDefault(); e.stopPropagation() })
el.addEventListener("dragover",  (e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true) })
el.addEventListener("drop",      async (e) => { e.preventDefault(); e.stopPropagation(); ... })
el.addEventListener("dragleave", () => setIsDragging(false))
```

### `ChatComposer` / `JournalScreen` compose area

State added:
```ts
const [attachedImage, setAttachedImage] = useState<{ url: string; path: string } | null>(null)
```

UI added below textarea:
- When `attachedImage` is set: show `<img src={attachedImage.url}>` thumbnail + ✕ remove button
- `ImageInsertButton` with `onAttach={setAttachedImage}`
- On send: include `image_path: attachedImage?.path` in POST body; clear `attachedImage` after send

## Python: `run_claude_with_image`

```python
def run_claude_with_image(
    prompt: str,
    image_path: str,
    label: str,
    timeout: int = 300,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
) -> str:
    """Invoke claude CLI with a vision content block via stdin.

    Builds a multimodal message (image + text) as JSON and pipes it to
    `claude -p -`, which reads the prompt from stdin when `-` is passed.
    Works with cli (OAuth) auth — no API key required.
    """
    img_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode()
    ext = Path(image_path).suffix.lstrip(".").lower()
    media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                  "png": "image/png", "gif": "image/gif",
                  "webp": "image/webp"}.get(ext, "image/png")

    message = json.dumps({
        "role": "user",
        "content": [
            {"type": "image", "source": {
                "type": "base64", "media_type": media_type, "data": b64,
            }},
            {"type": "text", "text": prompt},
        ],
    })

    env = build_env(auth_mode=state_mod.read_state().auth_mode)
    model = get_model()
    cmd = [claude_path, "-p", "-", "--output-format", "json", "--model", model]

    result = subprocess.run(
        cmd,
        input=message,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return _parse_and_log_usage(result.stdout, label)
```

For the **streaming** case (chat jobs), the Popen call is modified similarly:
- `stdin=subprocess.PIPE`
- After `Popen(...)`, write `message.encode()` to `proc.stdin` and close it

## Security

- `image_path` from the frontend is validated server-side: must resolve inside `apps/python/input/images/` (same traversal guard as the serve route)
- Max size 5 MB enforced at upload time (unchanged)
- Allowed extensions: jpg, jpeg, png, gif, webp (unchanged)

## Error Handling

| Scenario | Behavior |
|---|---|
| `image_path` outside storage root | 400 — "Invalid image path" |
| Image file not found at path | 400 — "Image file not found" |
| Claude vision call fails | SSE error event (same as existing chat error path) |
| No image attached | Falls through to existing `run_claude()` — no change |

## Out of Scope

- Generic file attachment (#309)
- Image resizing / optimization
- Paste-from-clipboard image insertion
- Multiple images per message
- api mode vision (SDK-based) — add if user switches to api mode
