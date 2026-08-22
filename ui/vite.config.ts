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
      "/rosters": "http://127.0.0.1:8765",
    },
  },
  test: {
    include: ["test/**/*.test.ts"],
    // Six times vitest's default, and for every suite rather than the three
    // that happened to lose a race (#157). A gate run once took 979s and the
    // suites that timed out were not special — the load was — so pinning a
    // number on those three leaves the next one exposed. A green run is
    // unaffected, the whole suite finishing in seconds, and the only cost is
    // a slower report on a genuine hang. What is bought is that an unattended
    // gate cannot go red for a reason indistinguishable from a regression.
    testTimeout: 30000,
  },
});
