import assert from "node:assert/strict"
import { homedir } from "node:os"
import { join, resolve } from "node:path"
import { test } from "node:test"

import { isLoopbackHost, parseCliArgs, UsageError } from "../lib/args.mjs"

test("defaults", () => {
  const opts = parseCliArgs([], {})
  assert.equal(opts.port, 3000)
  assert.equal(opts.apiPort, 8000)
  assert.equal(opts.host, "127.0.0.1")
  assert.equal(opts.browser, true)
  assert.equal(opts.home, join(homedir(), ".brief-lens"))
  assert.equal(opts.help, false)
  assert.equal(opts.version, false)
})

test("flags override defaults", () => {
  const opts = parseCliArgs(
    ["--port", "3100", "--api-port=8100", "--no-browser", "--home", "/tmp/bl"],
    {},
  )
  assert.equal(opts.port, 3100)
  assert.equal(opts.apiPort, 8100)
  assert.equal(opts.browser, false)
  assert.equal(opts.home, "/tmp/bl")
})

test("BRIEF_LENS_HOME is used when --home is absent", () => {
  assert.equal(parseCliArgs([], { BRIEF_LENS_HOME: "/data/bl" }).home, "/data/bl")
})

test("--home wins over BRIEF_LENS_HOME", () => {
  assert.equal(parseCliArgs(["--home", "/a"], { BRIEF_LENS_HOME: "/b" }).home, "/a")
})

test("--home expands ~ and resolves relative paths", () => {
  assert.equal(parseCliArgs(["--home", "~/x"], {}).home, join(homedir(), "x"))
  assert.equal(parseCliArgs(["--home", "rel"], {}).home, resolve("rel"))
})

test("CI disables the browser", () => {
  assert.equal(parseCliArgs([], { CI: "true" }).browser, false)
})

test("--help / -h and --version / -v", () => {
  assert.equal(parseCliArgs(["-h"], {}).help, true)
  assert.equal(parseCliArgs(["--help"], {}).help, true)
  assert.equal(parseCliArgs(["-v"], {}).version, true)
  assert.equal(parseCliArgs(["--version"], {}).version, true)
})

for (const bad of ["0", "65536", "abc", "80.5", ""]) {
  test(`rejects port ${JSON.stringify(bad)}`, () => {
    assert.throws(() => parseCliArgs(["--port", bad], {}), UsageError)
  })
}

test("accepts boundary ports 1 and 65535", () => {
  assert.equal(parseCliArgs(["--port", "1"], {}).port, 1)
  assert.equal(parseCliArgs(["--api-port", "65535"], {}).apiPort, 65535)
})

test("rejects identical web and API ports", () => {
  assert.throws(() => parseCliArgs(["--port", "8000"], {}), /must differ/)
})

test("rejects unknown flags and positional args", () => {
  assert.throws(() => parseCliArgs(["--nope"], {}), UsageError)
  assert.throws(() => parseCliArgs(["serve"], {}), UsageError)
})

test("--host overrides BRIEF_LENS_HOST, which overrides the loopback default", () => {
  assert.equal(parseCliArgs([], { BRIEF_LENS_HOST: "0.0.0.0" }).host, "0.0.0.0")
  assert.equal(parseCliArgs(["--host", "::1"], { BRIEF_LENS_HOST: "0.0.0.0" }).host, "::1")
  assert.equal(parseCliArgs([], { BRIEF_LENS_HOST: "  " }).host, "127.0.0.1")
})

for (const bad of ["", "   ", "0.0.0.0 extra"]) {
  test(`rejects host ${JSON.stringify(bad)}`, () => {
    assert.throws(() => parseCliArgs(["--host", bad], {}), UsageError)
  })
}

test("--host accepts a bracketed IPv6 literal and uses the bare address", () => {
  assert.equal(parseCliArgs(["--host", "[::1]"], {}).host, "::1")
  assert.equal(parseCliArgs(["--host", " LocalHost "], {}).host, "localhost")
})

test("isLoopbackHost separates local-only from reachable addresses", () => {
  const loopback = [
    "127.0.0.1", "127.1.2.3", "localhost", "LOCALHOST", "::1", "[::1]",
    "0:0:0:0:0:0:0:1", "0000:0000:0000:0000:0000:0000:0000:0001",
    "::ffff:127.0.0.1", "::ffff:7f00:1", "[::ffff:127.0.0.1]",
  ]
  for (const h of loopback) assert.equal(isLoopbackHost(h), true, h)
  const reachable = [
    "0.0.0.0", "::", "192.168.1.5", "10.0.0.1", "example.com",
    // Names and malformed literals that merely start like loopback.
    "127.evil.example", "127.0.0.1.evil.example", "127.0.0", "127.0.0.256", "localhost.evil.example",
    "::ffff:192.168.1.5", "::2", "fe80::1",
  ]
  for (const h of reachable) assert.equal(isLoopbackHost(h), false, h)
})
