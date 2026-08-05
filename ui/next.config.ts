import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The shipped product is one process and that process is Python, so it serves plain files.
  // `npm run build` stages them into src/standup/web — distDir cannot point outside the project.
  output: "export",
  devIndicators: false,
};

export default nextConfig;
