import { defineConfig } from "vitest/config";

// The store's HTTP face runs separately (`uv run tc49 serve`), so the dev
// server proxies to it and the app talks to its own origin.
//
// One entry, `index.html`, and vite finds it without being told: the app is
// one page with a view in its hash (ADR-0038).
export default defineConfig({
  server: {
    // A second `pnpm dev` must fail rather than move to the next free port:
    // the tab already open on 5173 keeps fetching its own origin, and when the
    // first server goes away every call there dies as `Failed to fetch`.
    strictPort: true,
    proxy: {
      "/drawings": "http://127.0.0.1:8765",
      "/review": "http://127.0.0.1:8765",
      "/scenarios": "http://127.0.0.1:8765",
      "/rosters": "http://127.0.0.1:8765",
    },
  },
  test: {
    include: ["test/**/*.test.ts"],
  },
});
