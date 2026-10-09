// Assemble dist/ for the published package (runs as `prepack`):
//   dist/python  — backend sources, prompts, config templates, requirements lock
//   dist/web     — Next.js standalone server with its static assets
// then refuse to continue if anything personal or secret slipped in.
//
//   node scripts/build.mjs               # full build
//   node scripts/build.mjs --skip-web-build   # reuse apps/web/.next-pack
import { spawnSync } from "node:child_process"
import { cpSync, existsSync, readdirSync, rmSync, statSync } from "node:fs"
import { basename, join, relative, sep } from "node:path"
import { fileURLToPath } from "node:url"

import { findForbidden, findMissing } from "./verify-dist.mjs"

const pkgRoot = fileURLToPath(new URL("..", import.meta.url))
const repoRoot = join(pkgRoot, "..", "..")
const pythonSrc = join(repoRoot, "apps", "python")
const webSrc = join(repoRoot, "apps", "web")
const dist = join(pkgRoot, "dist")
// Separate from .next so a running `next dev` keeps its build directory.
const WEB_DIST_DIR = ".next-pack"

const skipPythonJunk = (src) => !["__pycache__", ".DS_Store"].includes(basename(src)) && !src.endsWith(".pyc")

function step(msg) {
  console.log(`build: ${msg}`)
}

function copyPython() {
  const out = join(dist, "python")
  for (const dir of ["src", "web", "prompts"]) {
    cpSync(join(pythonSrc, dir), join(out, dir), { recursive: true, filter: skipPythonJunk })
  }
  cpSync(join(pythonSrc, "requirements.txt"), join(out, "requirements.txt"))
  // The archive endpoint shells out to this script; the other bin/ scripts are
  // clone-only launchers.
  cpSync(join(pythonSrc, "bin", "archive.sh"), join(out, "bin", "archive.sh"))
  for (const name of readdirSync(join(pythonSrc, "config"))) {
    if (name.endsWith(".example")) cpSync(join(pythonSrc, "config", name), join(out, "config", name))
  }
}

function buildWeb(skip) {
  if (!skip) {
    const res = spawnSync("npm", ["run", "build"], {
      cwd: webSrc,
      stdio: "inherit",
      env: { ...process.env, NEXT_DIST_DIR: WEB_DIST_DIR, NEXT_TELEMETRY_DISABLED: "1" },
    })
    if (res.status !== 0) throw new Error("apps/web build failed")
  }
  const standalone = join(webSrc, WEB_DIST_DIR, "standalone")
  if (!existsSync(join(standalone, "server.js"))) {
    throw new Error(`${standalone}/server.js not found — run without --skip-web-build`)
  }
  // Standalone node_modules may contain symlinks; the tarball needs real files.
  cpSync(standalone, join(dist, "web"), { recursive: true, dereference: true })
}

function listFiles(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...listFiles(p))
    else out.push(relative(pkgRoot, p).split(sep).join("/"))
  }
  return out
}

function main() {
  const skipWeb = process.argv.includes("--skip-web-build")
  rmSync(dist, { recursive: true, force: true })
  step("copying Python backend")
  copyPython()
  step(skipWeb ? "reusing existing web build" : "building web (Next.js standalone)")
  buildWeb(skipWeb)
  cpSync(join(repoRoot, "LICENSE"), join(pkgRoot, "LICENSE"))

  const files = listFiles(dist)
  const forbidden = findForbidden(files)
  const missing = findMissing(files)
  if (forbidden.length || missing.length) {
    rmSync(dist, { recursive: true, force: true })
    if (forbidden.length) console.error(`build: refusing to package:\n  ${forbidden.join("\n  ")}`)
    if (missing.length) console.error(`build: missing required files:\n  ${missing.join("\n  ")}`)
    process.exit(1)
  }
  step(`dist ready (${files.length} files)`)
}

main()
