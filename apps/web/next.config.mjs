/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server (.next/standalone/server.js) so the npx
  // launcher can run the UI without `next dev` or a repo checkout.
  output: "standalone",
}

export default nextConfig
