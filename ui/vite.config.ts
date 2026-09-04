import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// The store's HTTP face runs separately (`uv run tc49 serve`), so the dev
// server proxies to it and the app talks to its own origin.
//
// One entry, `index.html`, and vite finds it without being told: the app is
// one page with a view in its hash (ADR-0038).
const STORE = "http://127.0.0.1:8765";

export default defineConfig({
  server: {
    // A second `pnpm dev` must fail rather than move to the next free port:
    // the tab already open on 5173 keeps fetching its own origin, and when the
    // first server goes away every call there dies as `Failed to fetch`.
    strictPort: true,
    // Every interface, not just loopback: the reverse proxy that serves
    // `dev.rails49.org` runs in a container and reaches the host by address
    // (docs/DEPLOY.md). Vite refuses a request whose `Host` header it has not
    // been told about, so the name is named.
    host: true,
    allowedHosts: ["dev.rails49.org"],
    // `changeOrigin: false` on every store route, which the string shorthand
    // does not give: vite turns `"/x": "http://…"` into `changeOrigin: true`
    // and rewrites `Host` to the target, so the store saw the page's origin
    // against its own address and refused every write (#351). The reverse
    // proxy in front of a layout server passes the host header through, so
    // this is what makes development behave the way deployment does.
    proxy: {
      "/backup": { target: STORE, changeOrigin: false },
      "/drawings": { target: STORE, changeOrigin: false },
      "/review": { target: STORE, changeOrigin: false },
      "/layouts": { target: STORE, changeOrigin: false },
      "/rosters": { target: STORE, changeOrigin: false },
      "/catalogue": { target: STORE, changeOrigin: false },
      // The broker's WebSocket listener under a path of the app's own origin,
      // which is what lets the panel build one URL whether TLS is terminated
      // in front of it or not. The proxy in front of a layout server strips
      // the same prefix (docs/DEPLOY.md).
      "/mqtt": {
        target: "ws://127.0.0.1:9001",
        ws: true,
        rewrite: (path) => path.replace(/^\/mqtt/, ""),
      },
    },
  },
  test: {
    include: ["test/**/*.test.ts"],
    // The broker stands where MQTT.js does. The run view is a client of a
    // broker (ADR-0059, decision 4), so what a DOM suite has to drive is the
    // broker's side — a connection that lands, retained rows answering a
    // subscription, and what the page published back — and that is
    // `test/support/broker.ts`. The library itself is not this repo's to
    // test, and the surface the view asks of it is five calls wide.
    alias: {
      mqtt: fileURLToPath(new URL("./test/support/broker.ts", import.meta.url)),
    },
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
