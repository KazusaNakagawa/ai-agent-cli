import { join, resolve } from "node:path"

const WEB_DIR = resolve(__dirname, "..")
const PYTHON_DIR = resolve(WEB_DIR, "..", "python")
const TMP_HOME = join(WEB_DIR, "e2e", ".tmp-home")
const TMP_AGENT_DIR = join(TMP_HOME, ".ai-agent")
const TMP_TOKEN_FILE = join(TMP_AGENT_DIR, "session-token")
const TMP_CONFIG_FILE = join(TMP_AGENT_DIR, "briefing.json")
const NEXT_TOKEN_FILE = join(WEB_DIR, ".token")

export const PATHS = {
  WEB_DIR,
  PYTHON_DIR,
  TMP_HOME,
  TMP_AGENT_DIR,
  TMP_TOKEN_FILE,
  TMP_CONFIG_FILE,
  NEXT_TOKEN_FILE,
}
