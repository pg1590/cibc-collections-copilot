import type { NextConfig } from "next";

// The FastAPI backend serves the contract under /api on 127.0.0.1:8000.
// Override with BACKEND_URL if the backend runs elsewhere locally.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
