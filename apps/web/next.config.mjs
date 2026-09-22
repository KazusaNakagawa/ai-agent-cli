/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server (.next/standalone/server.js) so the npx
  // launcher can run the UI without `next dev` or a repo checkout.
  output: "standalone",
  // The package build sets NEXT_DIST_DIR so it never clobbers the .next/ a
  // running `next dev` is using.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  experimental: {
    // File tracing copies files the server reads at runtime into standalone.
    // The dev-only bearer token mirror (and any .env) must never ride along
    // into a published build.
    outputFileTracingExcludes: {
      "*": ["./.token", "./.env*"],
    },
  },
}

export default nextConfig
