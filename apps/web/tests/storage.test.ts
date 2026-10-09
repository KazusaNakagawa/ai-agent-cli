import path from "path"
import { describe, expect, it } from "vitest"

import { inputRoot } from "@/lib/storage"

describe("inputRoot", () => {
  it("defaults to apps/python/input relative to the apps/web cwd", () => {
    expect(inputRoot({}, "/repo/apps/web")).toBe("/repo/apps/python/input")
  })

  it("prefers AI_AGENT_INPUT_DIR so the standalone server is cwd-independent", () => {
    expect(
      inputRoot({ AI_AGENT_INPUT_DIR: "/home/u/.brief-lens/input" }, "/pkg/web/.next/standalone"),
    ).toBe("/home/u/.brief-lens/input")
  })

  it("resolves a relative AI_AGENT_INPUT_DIR against the cwd", () => {
    expect(inputRoot({ AI_AGENT_INPUT_DIR: "data/input" }, "/srv")).toBe(path.resolve("/srv", "data/input"))
  })

  it.each(["", "   "])("treats a blank AI_AGENT_INPUT_DIR (%j) as unset", (value) => {
    expect(inputRoot({ AI_AGENT_INPUT_DIR: value }, "/repo/apps/web")).toBe("/repo/apps/python/input")
  })
})
