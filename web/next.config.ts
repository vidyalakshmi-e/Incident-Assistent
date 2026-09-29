import type { NextConfig } from "next";

// The UI talks to the FastAPI backend through a same-origin proxy (/api/* -> API_URL/*), so the
// browser never needs CORS or to know where the API lives.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
  devIndicators: { position: "bottom-right" },
  experimental: {
    // LLM-mode synthesis can take 10-20 s on a local model; the default proxy timeout is shorter.
    proxyTimeout: 180_000,
  },
};

export default nextConfig;
