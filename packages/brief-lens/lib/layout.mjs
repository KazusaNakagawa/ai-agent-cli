import { existsSync } from "node:fs"
import { join } from "node:path"

/**
 * Locate the Python backend and the Next.js standalone server.
 *
 * - bundle: a published package carries both under dist/ (assembled by the
 *   package build script).
 * - repo:   running from a checkout, packages/brief-lens sits next to apps/.
 */
export function resolveLayout(pkgRoot) {
  const bundle = {
    pythonDir: join(pkgRoot, "dist", "python"),
    webDir: join(pkgRoot, "dist", "web"),
    source: "bundle",
  }
  if (existsSync(join(bundle.pythonDir, "web", "app.py")) && existsSync(join(bundle.webDir, "server.js"))) {
    return bundle
  }

  const apps = join(pkgRoot, "..", "..", "apps")
  const repo = {
    pythonDir: join(apps, "python"),
    webDir: join(apps, "web", ".next", "standalone"),
    source: "repo",
  }
  if (existsSync(join(repo.pythonDir, "web", "app.py"))) {
    if (!existsSync(join(repo.webDir, "server.js"))) {
      throw new Error(
        `web build not found at ${repo.webDir}\n    Build it first: (cd ${join(apps, "web")} && npm run build)`,
      )
    }
    return repo
  }
  throw new Error(`cannot find the brief-lens app files under ${pkgRoot}`)
}
