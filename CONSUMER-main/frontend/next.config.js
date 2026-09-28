const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: path.resolve(__dirname, ".."),
  // Standalone output produces a minimal, self-contained server bundle --
  // needed for a lean production Docker image; has no effect on `next dev`.
  output: "standalone",
  // Only relevant for the single-container deployment (Dockerfile.single at
  // the repo root), where the frontend is built with
  // NEXT_PUBLIC_API_BASE_URL=/api/v1 (a relative path, so the browser calls
  // the same origin the page was served from) and the backend runs
  // internally on INTERNAL_API_PORT. This proxies those same-origin calls
  // to the internal FastAPI process. In every other setup (local dev, the
  // split frontend/backend Docker Compose services) NEXT_PUBLIC_API_BASE_URL
  // is a full cross-origin URL, so requests never hit this rewrite at all --
  // safe to leave in unconditionally.
  async rewrites() {
    const port = process.env.INTERNAL_API_PORT || "8000";
    return [
      { source: "/api/v1/:path*", destination: `http://127.0.0.1:${port}/api/v1/:path*` },
      // getSystemHealth() in api-client.ts strips /api/v1 off the base URL
      // and calls /health directly (matching the backend's real route,
      // which isn't under the /api/v1 prefix) -- needed its own rule, the
      // /api/v1/* one above doesn't cover it.
      { source: "/health", destination: `http://127.0.0.1:${port}/health` },
      { source: "/health/live", destination: `http://127.0.0.1:${port}/health/live` },
    ];
  },
};

module.exports = nextConfig;
