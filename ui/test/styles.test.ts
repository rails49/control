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
 *
 * The palette is the other thing a rule reads from outside itself, and a mark
 * saying the wrong thing about a drawing is as silent a fault as a sheet
 * painted in the browser's defaults, so which weight each fault is marked in
 * is checked here too.
 */

import { describe, expect, it } from "vitest";

import { COLOURS } from "../src/render/units.js";
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
import { headerStyles } from "../src/ui/tc-header.styles.js";
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

/**
 * The two weights a fault is marked in (#92).
 *
 * Red is what stops derivation; the quieter mark is what derives but is
 * unfinished (ADR-0024). Both are palette entries, so a rule asks for the
 * weight it means rather than for a colour that happens to match, and the
 * canvas keeps discriminating when the next unfinished thing — a turnout
 * without an address — takes the same mark.
 */
describe("the two weights a fault is marked in", () => {
  /** The block of a rule, by its selector, out of a sheet's text. */
  function rule(sheet: string, selector: string): string {
    const escaped = selector.replace(/[.]/g, "\\.");
    const found = sheet.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
    expect(found, `no rule for ${selector}`).not.toBeNull();
    return found![1]!;
  }

  it("are two colours, not one used twice", () => {
    expect(COLOURS["--unfinished"]).toBeDefined();
    expect(COLOURS["--unfinished"]).not.toBe(COLOURS["--wrong"]);
  });

  it("marks a square two symbols cover in the quieter one", () => {
    expect(rule(canvasStyles.cssText, ".stacked")).toContain(
      "var(--unfinished)",
    );
  });

  it("marks a symbol with no address in the quieter one as well", () => {
    // The second thing that derives and is unfinished, and so the same
    // weight rather than a third (#96).
    expect(rule(canvasStyles.cssText, ".unaddressed")).toContain(
      "var(--unfinished)",
    );
  });

  it("leaves a pin short of a wire and a lone portal label red", () => {
    expect(rule(canvasStyles.cssText, ".pin.red")).toContain("var(--wrong)");
    expect(rule(canvasStyles.cssText, ".unpaired")).toContain("var(--wrong)");
  });

  /** A way is lit in one colour when a transit is chosen and in another when
   *  derivation refused over it, and the second is a refusal (#93). Every
   *  stroke a way lights has to change, or a red run reads as a chosen one
   *  wherever it crosses a frog. */
  it("lights the way a refusal is about red, leg by leg", () => {
    for (const stroke of [".track.lit", ".tick.lit", ".bend.lit"]) {
      expect(
        rule(canvasStyles.cssText, `.symbol.offending ${stroke}`),
      ).toContain("var(--wrong)");
    }
  });

  /** The band's indicator is the coarse counterpart to the canvas's marks and
   *  shows only for what stopped derivation, so it wears that weight (#91). An
   *  overlap and a missing address leave it clean, and nothing there should
   *  ever read in the quiet one. */
  it("marks the band in the weight that stops derivation", () => {
    const mark = rule(headerStyles.cssText, ".refused");
    expect(mark).toContain("var(--wrong)");
    expect(mark).not.toContain("var(--unfinished)");
  });

  /** The ghost draws the same mark on the squares a drop cannot have, and that
   *  drop places nothing at all: a refusal, so it stays red. */
  it("leaves the squares a blocked drop wants red", () => {
    expect(rule(canvasStyles.cssText, ".ghost.blocked .stacked")).toContain(
      "var(--wrong)",
    );
  });
});
