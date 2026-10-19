import path from "node:path";
import type { NextConfig } from "next";

const repository = path.join(import.meta.dirname, "..", "..");

const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  devIndicators: false,
  images: { unoptimized: true },
  transpilePackages: ["@relay/ui"],
  turbopack: { root: repository },
  outputFileTracingRoot: repository,
};

export default config;
