// Line-oriented highlighter for `.log` files. There's no standard Prism
// grammar for log output, so this applies a small set of regexes per line:
// a leading ISO-ish timestamp (dimmed) and a log-level keyword (colored by
// severity). Everything else renders in the default text color.

const LEVEL_COLORS: Record<string, string> = {
  ERROR: "#F87171",
  FATAL: "#F87171",
  CRIT: "#F87171",
  CRITICAL: "#F87171",
  WARN: "#FBBF24",
  WARNING: "#FBBF24",
  INFO: "#60A5FA",
  DEBUG: "#9CA3AF",
  TRACE: "#C084FC",
}

const LEVEL_PATTERN = new RegExp(`\\b(${Object.keys(LEVEL_COLORS).join("|")})\\b`)
const TIMESTAMP_PATTERN = /^(\S*\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\S*)/

function LogLine({ line }: { line: string }) {
  const tsMatch = line.match(TIMESTAMP_PATTERN)
  const rest = tsMatch ? line.slice(tsMatch[0].length) : line
  const levelMatch = rest.match(LEVEL_PATTERN)

  if (levelMatch === null) {
    return (
      <div>
        {tsMatch ? <span className="text-muted-foreground">{tsMatch[0]}</span> : null}
        {rest}
      </div>
    )
  }

  const before = rest.slice(0, levelMatch.index)
  const level = levelMatch[0]
  const after = rest.slice((levelMatch.index ?? 0) + level.length)

  return (
    <div>
      {tsMatch ? <span className="text-muted-foreground">{tsMatch[0]}</span> : null}
      {before}
      <span style={{ color: LEVEL_COLORS[level] }} className="font-semibold">
        {level}
      </span>
      {after}
    </div>
  )
}

export function LogView({ content }: { content: string }) {
  return (
    <pre
      className="whitespace-pre-wrap break-all font-mono text-xs leading-relaxed"
      data-testid="log-view"
    >
      {content.split("\n").map((line, i) => (
        // Log lines have no stable identity; index is fine for a static view.
        // eslint-disable-next-line react/no-array-index-key
        <LogLine key={i} line={line} />
      ))}
    </pre>
  )
}
