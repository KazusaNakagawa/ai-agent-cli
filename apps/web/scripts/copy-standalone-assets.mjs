// Copy the assets `next build` leaves out of .next/standalone so the
// standalone server can serve them. Next.js documents this as a manual step.
import { cpSync, existsSync } from "node:fs"
import { join } from "node:path"
import { fileURLToPath } from "node:url"

const root = fileURLToPath(new URL("..", import.meta.url))
const standalone = join(root, ".next", "standalone")

if (!existsSync(join(standalone, "server.js"))) {
  console.error("copy-standalone-assets: .next/standalone/server.js not found — run `next build` first")
  process.exit(1)
}

cpSync(join(root, ".next", "static"), join(standalone, ".next", "static"), { recursive: true })
if (existsSync(join(root, "public"))) {
  cpSync(join(root, "public"), join(standalone, "public"), { recursive: true })
}
console.log("copy-standalone-assets: done")
