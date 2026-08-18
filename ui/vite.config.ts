import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// The store's HTTP face runs separately (`uv run tc49 serve`), so the dev
// server proxies to it and the editor talks to its own origin.
export default defineConfig({
  // Two pages, one stack: the editor at `/`, the panel at `/panel.html`.
  build: {
    rollupOptions: {
      input: {
        editor: fileURLToPath(new URL("index.html", import.meta.url)),
        panel: fileURLToPath(new URL("panel.html", import.meta.url)),
      },
    },
  },
  server: {
    // A second `pnpm dev` must fail rather than move to the next free port:
    // the tab already open on 5173 keeps fetching its own origin, and when the
    // first server goes away every call there dies as `Failed to fetch`.
    strictPort: true,
    proxy: {
      "/drawings": "http://127.0.0.1:8765",
      "/review": "http://127.0.0.1:8765",
      "/scenarios": "http://127.0.0.1:8765",
    },
  },
  test: {
    include: ["test/**/*.test.ts"],
  },
});
