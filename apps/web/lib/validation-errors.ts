// FastAPI returns Pydantic v2 validation errors as:
//   { "detail": [ { "type": "...", "loc": ["body", "portfolio", "tickers", 0], "msg": "...", ... }, ... ] }
// This module turns that shape into a lookup table keyed by "/"-joined path,
// so form components can do `errors.get("portfolio/tickers")` for inline messages.

export type ValidationError = {
  type: string
  loc: (string | number)[]
  msg: string
}

export type ValidationErrorMap = Map<string, string>

export function buildErrorMap(detail: unknown): ValidationErrorMap {
  const out: ValidationErrorMap = new Map()
  if (!Array.isArray(detail)) return out
  for (const item of detail) {
    if (!item || typeof item !== "object") continue
    const { loc, msg } = item as Partial<ValidationError>
    if (!Array.isArray(loc) || typeof msg !== "string") continue
    // Drop the leading "body" segment FastAPI prepends; keep the rest as a path key.
    const path = loc[0] === "body" ? loc.slice(1) : loc
    if (path.length === 0) continue
    out.set(path.map(String).join("/"), msg)
  }
  return out
}

// Parses a FastAPI 422 response body. Returns an empty map on anything unexpected
// so callers can fall back to a generic banner without crashing.
export async function parseValidationErrors(
  res: Response,
): Promise<ValidationErrorMap> {
  try {
    const body = (await res.json()) as { detail?: unknown }
    return buildErrorMap(body.detail)
  } catch {
    return new Map()
  }
}
