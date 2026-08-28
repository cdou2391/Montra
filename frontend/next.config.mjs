/** @type {import('next').NextConfig} */

// The client calls the API at a relative /api/v1, so it works on whatever
// origin it was loaded from. Behind the nginx proxy that path is routed for
// us; hitting the dev server directly on :3000 it is not, so the dev server
// forwards it itself. Without this, localhost:3000 would load but every API
// call would 404.
const apiOrigin = process.env.API_ORIGIN ?? "http://api:8000";

const nextConfig = {
  reactStrictMode: true,
  // Emits a self-contained server with only the modules the build actually
  // reached, so the production image needs no package manager.
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
};

export default nextConfig;
