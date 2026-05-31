import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  turbopack: {
    // Anchor workspace root to this frontend directory so Turbopack
    // doesn't get confused by the parent package-lock.json files.
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
