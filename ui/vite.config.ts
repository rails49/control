import { defineConfig } from "vitest/config";

// The store's HTTP face runs separately (`uv run tc49 serve`), so the dev
// server proxies to it and the editor talks to its own origin.
export default defineConfig({
  server: {
    proxy: {
      "/drawings": "http://127.0.0.1:8765",
      "/review": "http://127.0.0.1:8765",
    },
  },
  test: {
    include: ["test/**/*.test.ts"],
  },
});
