import { NextResponse } from "next/server"

// The UI is a local-only tool. Binding to loopback is not enough on its own:
// a hostile web page can still reach it through DNS rebinding (Host is the
// attacker's domain) or a cross-site request (Origin is a foreign site).
const LOOPBACK_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]"])

function hostnameOf(hostHeader: string): string {
  // IPv6 literals look like "[::1]:3000"; everything else is "name[:port]".
  if (hostHeader.startsWith("[")) {
    const end = hostHeader.indexOf("]")
    return end === -1 ? hostHeader : hostHeader.slice(0, end + 1)
  }
  return hostHeader.split(":")[0]
}

function forbidden(reason: string): NextResponse {
  return NextResponse.json({ error: reason }, { status: 403 })
}

/**
 * Returns a 403 response when the request does not come from the local UI,
 * or null when it may proceed. Call it first in every API route handler.
 */
export function rejectForeignRequest(req: Request): NextResponse | null {
  const host = req.headers.get("host")
  if (!host || !LOOPBACK_HOSTNAMES.has(hostnameOf(host.toLowerCase()))) {
    return forbidden("Forbidden host")
  }

  // Browsers attach Origin to cross-site and non-GET requests. When present
  // it must match the Host the request was addressed to.
  const origin = req.headers.get("origin")
  if (origin !== null) {
    let originHost: string
    try {
      originHost = new URL(origin).host
    } catch {
      return forbidden("Forbidden origin")
    }
    if (originHost.toLowerCase() !== host.toLowerCase()) {
      return forbidden("Forbidden origin")
    }
  }
  return null
}
