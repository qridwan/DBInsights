import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The runtime collector is a workspace package shipped as TypeScript source.
  transpilePackages: ["@dbinsight/collector"],
};

export default nextConfig;
