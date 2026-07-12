// Maps a file name's extension to a representative accent color, echoing each
// language/tool's common brand color (e.g. Python blue, JSON yellow). Applied
// to the otherwise-monochrome file icon so file kinds are scannable at a
// glance, similar to VSCode's file icon theme.

const EXTENSION_COLORS: Record<string, string> = {
  py: "#3776AB",
  js: "#F7DF1E",
  jsx: "#61DAFB",
  ts: "#3178C6",
  tsx: "#3178C6",
  json: "#F7DF1E",
  md: "#42A5F5",
  markdown: "#42A5F5",
  html: "#E34C26",
  css: "#2965F1",
  scss: "#CC6699",
  yml: "#CB171E",
  yaml: "#CB171E",
  toml: "#9C4221",
  sh: "#4EAA25",
  bash: "#4EAA25",
  rs: "#DEA584",
  go: "#00ADD8",
  java: "#EA2D2E",
  rb: "#CC342D",
  php: "#777BB4",
  sql: "#4479A1",
  svg: "#FFB13B",
  png: "#A78BFA",
  jpg: "#A78BFA",
  jpeg: "#A78BFA",
  gif: "#A78BFA",
  pdf: "#EC4C47",
  txt: "#9CA3AF",
  env: "#ECD53F",
  lock: "#9CA3AF",
}

const DEFAULT_COLOR = "currentColor"

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".")
  return dot === -1 ? "" : name.slice(dot + 1).toLowerCase()
}

/** Returns a CSS color for the file's extension, or `currentColor` when unmapped. */
export function colorForFile(name: string): string {
  return EXTENSION_COLORS[extensionOf(name)] ?? DEFAULT_COLOR
}
