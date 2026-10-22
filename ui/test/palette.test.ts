// @vitest-environment happy-dom

/**
 * The palette's tiles, each handing over the kind it places when pressed
 * (EDITOR.md#palette).
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-palette.js";

/** The palette's fourth group is the widgets, each tile handing over its kind
 *  as a symbol's does (EDITOR.md#palette). */
describe("the palette", () => {
  it("offers a text, a button and a toggle in a group of their own", async () => {
    const palette = document.createElement("tc-palette");
    document.body.append(palette);
    await palette.updateComplete;
    const groups = palette.renderRoot.querySelectorAll(".group");
    expect(groups).toHaveLength(4);
    const tiles = [...groups[3]!.querySelectorAll("button")];
    expect(tiles.map((tile) => tile.title)).toEqual(["Text", "Button", "Toggle"]);

    const taken: string[] = [];
    palette.addEventListener("take", (event) =>
      taken.push((event as CustomEvent<string>).detail),
    );
    tiles[2]!.dispatchEvent(new PointerEvent("pointerdown", { button: 0 }));
    expect(taken).toEqual(["toggle"]);
  });
});
