// Guards for what the published tarball may and must contain. Paths are
// package-relative with forward slashes (the shape `npm pack --json` reports).

// Personal data and secrets must never ship. Config templates (*.example) are
// fine; real configs, runtime output and tokens are not.
const FORBIDDEN = [
  /^dist\/python\/config\/(?!.*\.example$)[^/]+$/,
  /^dist\/python\/(output|input|log)\//,
  /(^|\/)__pycache__\//,
  /(^|\/)\.token$/,
  /(^|\/)\.env(\.[^/]*)?$/,
  /(^|\/)session-token$/,
]

// Without these the launcher cannot boot from the bundle layout.
const REQUIRED = [
  "dist/python/web/app.py",
  "dist/python/requirements.txt",
  "dist/python/config/briefing.json.example",
  "dist/web/server.js",
]

export function findForbidden(files) {
  return files.filter((f) => FORBIDDEN.some((re) => re.test(f)))
}

export function findMissing(files) {
  const present = new Set(files)
  return REQUIRED.filter((f) => !present.has(f))
}
