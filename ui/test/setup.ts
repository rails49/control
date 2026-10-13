// The suites draw no Bootstrap glyphs, so Shoelace fetches nothing: its icon
// requests would otherwise reach the store `support/shell.ts` puts behind
// `fetch`.
import { registerIconLibrary } from "@shoelace-style/shoelace/dist/utilities/icon-library.js";

registerIconLibrary("default", { resolver: () => "" });
