import { isIPv4, isIPv6 } from "node:net"

/** Strip surrounding brackets and case: "[::1]" -> "::1". */
export function normalizeHost(host) {
  return host.trim().toLowerCase().replace(/^\[(.*)\]$/, "$1")
}

/**
 * True only for addresses that this machine alone can reach.
 *
 * IP literals are parsed rather than pattern-matched on a prefix: a name such as
 * `127.evil.example` is not loopback, while the expanded (`0:0:0:0:0:0:0:1`) and
 * IPv4-mapped (`::ffff:127.0.0.1`) spellings of the loopback addresses are.
 */
export function isLoopbackHost(host) {
  const h = normalizeHost(host)
  if (h === "localhost") return true
  if (isIPv4(h)) return h.startsWith("127.")
  if (isIPv6(h)) {
    let canonical
    try {
      canonical = new URL(`http://[${h}]`).hostname.slice(1, -1)
    } catch {
      return false
    }
    // 127.x.y.z maps to ::ffff:7fxx:yyzz in URL's canonical form.
    return canonical === "::1" || /^::ffff:7f[0-9a-f]{2}:[0-9a-f]{1,4}$/.test(canonical)
  }
  return false
}

/** The address to connect to for a server bound to `host`: wildcards answer on loopback. */
export function probeHost(host) {
  const h = normalizeHost(host)
  if (h === "0.0.0.0") return "127.0.0.1"
  if (h === "::") return "::1"
  return h
}

/** Host part of a URL: IPv6 literals need brackets. */
export function urlHost(host) {
  const h = normalizeHost(host)
  return h.includes(":") ? `[${h}]` : h
}

/**
 * Address to show the user. Wildcard and IPv4 loopback binds are reached as
 * `localhost` (what the Web UI's host check expects); anything else is shown as bound.
 */
export function displayHost(host) {
  const h = normalizeHost(host)
  if (h === "0.0.0.0" || h === "::" || h === "localhost" || (isIPv4(h) && h.startsWith("127."))) return "localhost"
  return urlHost(h)
}
