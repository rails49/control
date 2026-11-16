// @vitest-environment happy-dom

/**
 * The palette's tiles, each handing over the kind it places when pressed
 * (EDITOR.md#palette).
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-palette.js";

describe("the palette", () => {
  it("lays its tiles in five groups: block, points, crossings, ends, widgets", async () => {
    const palette = document.createElement("tc-palette");
    document.body.append(palette);
    await palette.updateComplete;
    const groups = [...palette.renderRoot.querySelectorAll(".group")];
    expect(
      groups.map((group) =>
        [...group.querySelectorAll("button")].map((tile) => tile.title),
      ),
    ).toEqual([
      ["Block"],
      ["Turnout", "Single slip", "Double slip"],
      ["90° crossing", "90° crossing, diagonal", "Crossing"],
      ["Terminal", "Portal"],
      ["Button", "Toggle", "Text"],
    ]);
  });

  it("starts the slips on a row of their own, below the turnout", async () => {
    const palette = document.createElement("tc-palette");
    document.body.append(palette);
    await palette.updateComplete;
    const points = palette.renderRoot.querySelectorAll(".group")[1]!;
    const first = [...points.querySelectorAll<HTMLButtonElement>("button.first")];
    expect(first.map((tile) => tile.title)).toEqual(["Turnout", "Single slip"]);
  });

  /** The widgets' tiles hand over their kind as a symbol's do. */
  it("hands over a widget's kind when its tile is pressed", async () => {
    const palette = document.createElement("tc-palette");
    document.body.append(palette);
    await palette.updateComplete;
    const tiles = [...palette.renderRoot.querySelectorAll(".group")[4]!.querySelectorAll("button")];

    const taken: string[] = [];
    palette.addEventListener("take", (event) =>
      taken.push((event as CustomEvent<string>).detail),
    );
    tiles[1]!.dispatchEvent(new PointerEvent("pointerdown", { button: 0 }));
    expect(taken).toEqual(["toggle"]);
  });

  /** The word `text` is drawn at the large size so it reads at the tile's
   *  size; a new text widget still starts at normal (#1279). */
  it("draws the text tile's word at the large size", async () => {
    const palette = document.createElement("tc-palette");
    document.body.append(palette);
    await palette.updateComplete;
    const tile = palette.renderRoot.querySelector('button[title="Text"]')!;
    expect(tile.querySelector("text")!.getAttribute("font-size")).toBe("0.55");
  });
});
