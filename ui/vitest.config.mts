import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // Native since Vite 7; the vite-tsconfig-paths plugin the Next docs still name is redundant.
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
  },
});
