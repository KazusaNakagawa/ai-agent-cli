import assert from "node:assert/strict"
import { test } from "node:test"

import { displayHost, probeHost, urlHost } from "../lib/host.mjs"
import { isPortFree } from "../lib/serve.mjs"

test("probeHost maps wildcard binds to a loopback address and leaves others alone", () => {
  assert.equal(probeHost("0.0.0.0"), "127.0.0.1")
  assert.equal(probeHost("::"), "::1")
  assert.equal(probeHost("127.0.0.1"), "127.0.0.1")
  assert.equal(probeHost("::1"), "::1")
  assert.equal(probeHost("[::1]"), "::1")
  assert.equal(probeHost("192.168.1.5"), "192.168.1.5")
})

test("urlHost brackets IPv6 literals only", () => {
  assert.equal(urlHost("::1"), "[::1]")
  assert.equal(urlHost("[::1]"), "[::1]")
  assert.equal(urlHost("127.0.0.1"), "127.0.0.1")
  assert.equal(urlHost("example.com"), "example.com")
})

test("probe URLs for every accepted --host spelling are valid", () => {
  for (const host of ["127.0.0.1", "0.0.0.0", "::", "::1", "[::1]", "localhost", "192.168.1.5"]) {
    const url = new URL(`http://${urlHost(probeHost(host))}:3000/`)
    assert.equal(url.port, "3000", host)
  }
})

test("displayHost shows localhost for loopback IPv4 and wildcard binds, the address otherwise", () => {
  for (const h of ["127.0.0.1", "127.5.5.5", "0.0.0.0", "::", "localhost"]) assert.equal(displayHost(h), "localhost", h)
  assert.equal(displayHost("::1"), "[::1]")
  assert.equal(displayHost("192.168.1.5"), "192.168.1.5")
})

test("isPortFree checks the host it is given", async () => {
  const { createServer } = await import("node:net")
  const srv = createServer()
  await new Promise((resolve) => srv.listen(0, "127.0.0.1", resolve))
  const { port } = srv.address()
  try {
    assert.equal(await isPortFree(port, "127.0.0.1"), false)
    assert.equal(await isPortFree(port), false) // default host is loopback
  } finally {
    await new Promise((resolve) => srv.close(resolve))
  }
  assert.equal(await isPortFree(port, "127.0.0.1"), true)
})
