import assert from "node:assert/strict"
import { test } from "node:test"

import { findForbidden, findMissing } from "../scripts/verify-dist.mjs"

const REQUIRED = [
  "dist/python/web/app.py",
  "dist/python/requirements.txt",
  "dist/python/config/briefing.json.example",
  "dist/web/server.js",
]

test("a clean file list has nothing forbidden or missing", () => {
  const files = [...REQUIRED, "dist/python/src/paths.py", "dist/web/node_modules/next/package.json"]
  assert.deepEqual(findForbidden(files), [])
  assert.deepEqual(findMissing(files), [])
})

for (const leaked of [
  "dist/python/config/briefing.json",
  "dist/python/config/holdings.json",
  "dist/python/config/self_agent_profile.md",
  "dist/python/output/briefing/briefing_2026-09-22.md",
  "dist/python/input/images/a.png",
  "dist/python/log/20260922-app.log",
  "dist/python/src/__pycache__/paths.cpython-312.pyc",
  "dist/web/.token",
  "dist/web/.env",
  "dist/web/.env.local",
  "dist/python/.env",
  "dist/session-token",
]) {
  test(`flags ${leaked}`, () => {
    assert.deepEqual(findForbidden([...REQUIRED, leaked]), [leaked])
  })
}

test("config templates and third-party config files are allowed", () => {
  const files = [
    "dist/python/config/holdings.json.example",
    "dist/python/config/self_agent_profile.md.example",
    "dist/web/node_modules/some-lib/config/defaults.json",
  ]
  assert.deepEqual(findForbidden(files), [])
})

test("reports each missing required file", () => {
  assert.deepEqual(findMissing(["dist/web/server.js"]), [
    "dist/python/web/app.py",
    "dist/python/requirements.txt",
    "dist/python/config/briefing.json.example",
  ])
})

test("an empty list misses everything", () => {
  assert.deepEqual(findMissing([]), REQUIRED)
})
