import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // API URL is exposed as NEXT_PUBLIC_API_URL (replaces former VITE_API_URL).
  // The backend runs on localhost:8000 by default.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
