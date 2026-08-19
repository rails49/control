/**
 * What the split stylesheets share (#104).
 *
 * Each component's rules sit in a module beside it, so what more than one of
 * them wears is now an import rather than a line further down the same file.
 * Half of that the compiler already holds: an interpolation whose import went
 * missing does not resolve, and an import nothing interpolates is unused, so
 * either edit on its own is a type error.
 *
 * What compiles is a sheet that lost both — the block and the import for it —
 * which is what tidying a stylesheet does, and what a sheet written fresh for
 * a new component does by omission. Nothing fails then until a browser paints
 * the pane in its own defaults. So each sheet is checked to carry the shared
 * blocks it reads, against the blocks themselves rather than a copy of a rule
 * out of one.
 */

import { describe, expect, it } from "vitest";

import {
  menuBox,
  menuRow,
  menuShortcut,
  palette,
  symbols,
  way,
} from "../src/ui/shared.styles.js";
import { canvasStyles, exportStyles } from "../src/ui/tc-canvas.styles.js";
import { appStyles } from "../src/ui/tc-editor.styles.js";
import { menuStyles } from "../src/ui/tc-menu.styles.js";
import { menubarStyles } from "../src/ui/tc-menubar.styles.js";
import { paletteStyles } from "../src/ui/tc-palette.styles.js";
import { panelStyles } from "../src/ui/tc-panel.styles.js";

describe("the palette", () => {
  /** The two pages' hosts, from which every component inherits it. */
  it("is declared by the editor's shell and by the panel", () => {
    expect(appStyles.cssText).toContain(palette.cssText);
    expect(panelStyles.cssText).toContain(palette.cssText);
  });

  /** An exported file has no host above the svg to inherit from (#86). */
  it("is written onto the svg an export carries", () => {
    expect(exportStyles.cssText).toContain(palette.cssText);
  });
});

describe("the drawing's own rules", () => {
  it("are worn by everything that draws a symbol", () => {
    expect(paletteStyles.cssText).toContain(symbols.cssText);
    expect(canvasStyles.cssText).toContain(symbols.cssText);
    expect(panelStyles.cssText).toContain(symbols.cssText);
  });

  /** The tiles show one symbol each and have no wire or lit way on them. */
  it("carry the way on the two surfaces that paint a whole drawing", () => {
    expect(canvasStyles.cssText).toContain(way.cssText);
    expect(panelStyles.cssText).toContain(way.cssText);
    expect(paletteStyles.cssText).not.toContain(way.cssText);
  });
});

describe("what a menu is made of", () => {
  /** The box, a row of it, and the key set beside a label: all three, or the
   *  editor's two menu systems stop reading as one. */
  it("is the same for the right-click menu and the bar's", () => {
    for (const part of [menuBox, menuRow, menuShortcut]) {
      expect(menuStyles.cssText).toContain(part.cssText);
      expect(menubarStyles.cssText).toContain(part.cssText);
    }
  });
});
