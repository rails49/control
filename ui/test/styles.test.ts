/**
 * What the split stylesheets share (#104).
 *
 * Each component's rules sit in a module beside it, so what more than one of
 * them wears is now an import rather than a line further down the same file.
 * An import that goes missing costs no type error and no test: the palette
 * simply stops resolving and the pane paints in the browser's defaults. So
 * each sheet is checked to carry the shared block it reads, against the block
 * itself rather than a copy of a rule out of it.
 */

import { describe, expect, it } from "vitest";

import { menuBox, palette, symbols, way } from "../src/ui/shared.styles.js";
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

describe("the box a menu drops into", () => {
  it("is the same for the right-click menu and the bar's", () => {
    expect(menuStyles.cssText).toContain(menuBox.cssText);
    expect(menubarStyles.cssText).toContain(menuBox.cssText);
  });
});
