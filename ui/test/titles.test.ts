/**
 * The work pane has no tooltip (EDITOR.md, #1305): no component under
 * `src/ui/` sets a `title` attribute or draws an SVG `<title>`.
 */

import { readFileSync, readdirSync } from "node:fs";

import { describe, expect, it } from "vitest";

const COMPONENTS = new URL("../src/ui/", import.meta.url);

describe("the components", () => {
  it("set no title attribute and draw no SVG title", () => {
    const found = readdirSync(COMPONENTS).flatMap((file) =>
      readFileSync(new URL(file, COMPONENTS), "utf8")
        .split("\n")
        .flatMap((line, at) =>
          /\btitle=|<title\b/.test(line) ? [`${file}:${at + 1}`] : [],
        ),
    );
    expect(found).toEqual([]);
  });
});
