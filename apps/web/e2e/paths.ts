import { join, resolve } from "node:path"

const WEB_DIR = resolve(__dirname, "..")
const PYTHON_DIR = resolve(WEB_DIR, "..", "python")
const TMP_HOME = join(WEB_DIR, "e2e", ".tmp-home")
const TMP_AGENT_DIR = join(TMP_HOME, ".ai-agent")
const TMP_TOKEN_FILE = join(TMP_AGENT_DIR, "session-token")
const TMP_CONFIG_FILE = join(TMP_AGENT_DIR, "briefing.json")
// Inside TMP_HOME (not apps/web/.token) so an E2E run never clobbers the
// real `.token` that bin/serve.sh writes for the developer's local Next.js
// session. The Next dev server reaches this path via AI_AGENT_TOKEN_PATH.
const NEXT_TOKEN_FILE = join(TMP_HOME, ".token")
// Isolated workspace root for the Workspace file-browser e2e, so the test can
// edit/save files without touching the repo's real `docs/`.
const TMP_WORKSPACE = join(WEB_DIR, "e2e", ".tmp-workspace")

export const PATHS = {
  WEB_DIR,
  PYTHON_DIR,
  TMP_HOME,
  TMP_AGENT_DIR,
  TMP_TOKEN_FILE,
  TMP_CONFIG_FILE,
  NEXT_TOKEN_FILE,
  TMP_WORKSPACE,
}
