/**
 * The work pane has no tooltip (EDITOR.md, #1305). A `title` attribute and an
 * SVG `<title>` show under a resting mouse pointer and nowhere else, so a
 * tablet cannot read them: what a component has to say is drawn on the screen.
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
