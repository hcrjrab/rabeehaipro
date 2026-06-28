import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /*
   * Dev-time proxy so the browser can call `/api/*` and reach the FastAPI
   * backend on :8000 without CORS friction. In production the Electron main
   * process (or the reverse proxy) routes the same prefix.
   */
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/:path*`,
      },
    ];
  },
};

export default nextConfig;
