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
 *
 * The shared module's limit is checked here as well, and in the other
 * direction: nothing lives in it that fewer than two component stylesheets
 * wear (#132). That one is mechanical, over every export the module has, so
 * that a block added there for a single component fails rather than passing
 * unnoticed until the module has grown back into the file it came out of.
 */

import type { CSSResult } from "lit";
import { describe, expect, it } from "vitest";

import { COLOURS } from "../src/render/units.js";
import * as shared from "../src/ui/shared.styles.js";
import {
  dismiss,
  menuBox,
  menuRow,
  menuRowChosen,
  menuShortcut,
  palette,
  symbols,
} from "../src/ui/shared.styles.js";
import { appStyles } from "../src/ui/tc-app.styles.js";
import { canvasStyles, exportStyles } from "../src/ui/tc-canvas.styles.js";
import { editorStyles } from "../src/ui/tc-editor.styles.js";
import { headerStyles } from "../src/ui/tc-header.styles.js";
import { menuStyles } from "../src/ui/tc-menu.styles.js";
import { menubarStyles } from "../src/ui/tc-menubar.styles.js";
import { paletteStyles } from "../src/ui/tc-palette.styles.js";
import { panelStyles } from "../src/ui/tc-panel.styles.js";
import { rosterStyles } from "../src/ui/tc-roster.styles.js";

/**
 * The component stylesheets, hand-listed: the imports above, named, so that a
 * sheet is counted as a wearer only once someone has said it is one.
 */
const sheets: Record<string, CSSResult> = {
  appStyles,
  canvasStyles,
  editorStyles,
  exportStyles,
  headerStyles,
  menuStyles,
  menubarStyles,
  paletteStyles,
  panelStyles,
  rosterStyles,
};

/**
 * The limit, executable (#132): a block only one component wears is that
 * component's own and does not belong in the shared module. Mechanical and
 * over every export, because the point is to catch the block nobody thought
 * to write an assertion for.
 */
describe("everything the shared module holds", () => {
  it.each(Object.entries(shared))(
    "%s is worn by at least two component stylesheets",
    (name, block) => {
      const wearers = Object.entries(sheets)
        .filter(([, sheet]) => sheet.cssText.includes(block.cssText))
        .map(([sheet]) => sheet);
      expect(
        wearers.length,
        `${name} is worn by ${wearers.join(", ") || "nothing"}`,
      ).toBeGreaterThanOrEqual(2);
    },
  );
});

describe("the palette", () => {
  /** The app's host, from which every component in the page inherits it.
   *  There is one page and one host to declare it on (ADR-0038), so the
   *  views do not declare it and must not: a second declaration is a second
   *  place for a colour to be changed in. */
  it("is declared on the one page every view is laid out in", () => {
    expect(appStyles.cssText).toContain(palette.cssText);
    expect(editorStyles.cssText).not.toContain(palette.cssText);
    expect(panelStyles.cssText).not.toContain(palette.cssText);
  });

  /** An exported file has no host above the svg to inherit from (#86). */
  it("is written onto the svg an export carries", () => {
    expect(exportStyles.cssText).toContain(palette.cssText);
  });
});

/**
 * The shell has one left-pane slot and each view fills it: the palette in
 * edit, the roster in run (#169). One width, declared where the page is, or
 * the two panes drift apart across a toggle and the slot stops being one.
 */
describe("the left-pane slot", () => {
  it("is declared on the page and read by both views", () => {
    expect(appStyles.cssText).toContain("--pane:");
    for (const sheet of [editorStyles, panelStyles]) {
      expect(sheet.cssText).toContain("var(--pane)");
      expect(sheet.cssText).not.toContain("--pane:");
    }
  });
});

describe("the drawing's own rules", () => {
  it("are worn by everything that draws a symbol", () => {
    expect(paletteStyles.cssText).toContain(symbols.cssText);
    expect(canvasStyles.cssText).toContain(symbols.cssText);
  });

  /** There is one surface that paints a whole drawing (#168), so the wires and
   *  the lit way are its own rules rather than something shared. The run view
   *  is that surface in run mode and declares none of it; the tiles show one
   *  symbol each and have no wire or lit way on them. */
  it("keep the wires and the lit way on the one surface that paints them", () => {
    for (const selector of [".wire", ".symbol .track.lit", ".wire.lit"]) {
      expect(canvasStyles.cssText).toContain(selector);
      expect(panelStyles.cssText).not.toContain(selector);
      expect(paletteStyles.cssText).not.toContain(selector);
    }
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

  /** The overlay a press outside lands on and the row under the pointer, both
   *  whole rule sets. Which two sheets wear them is the claim: the mechanical
   *  test above counts wearers and would take any two, and a menu is only one
   *  thing if these are the two. */
  it("dismisses and paints the chosen row the same way in both", () => {
    for (const part of [dismiss, menuRowChosen]) {
      expect(menuStyles.cssText).toContain(part.cssText);
      expect(menubarStyles.cssText).toContain(part.cssText);
    }
  });
});

/**
 * The two colours a committed route wears on the panel (#143).
 *
 * Green where the dispatcher holds the lock and the train may move, cyan
 * where the route is chosen and the claim has not been made yet. Both are
 * palette entries, so the owner moves either in one place, and every rule
 * that paints part of a route asks for the entry rather than for a hex that
 * happens to match — a stroke left behind is a route that reads as two.
 */
describe("the two colours a route's state is read in", () => {
  /** The canvas's rules without the palette an export carries, so that the
   *  entries' own declarations are not mistaken for a rule hardcoding one. */
  const panel = canvasStyles.cssText.replace(palette.cssText, "");

  it("are two named entries, and neither is the signal lamp's green", () => {
    expect(COLOURS["--locked"]).toBeDefined();
    expect(COLOURS["--planned"]).toBeDefined();
    expect(COLOURS["--locked"]).not.toBe(COLOURS["--green"]);
    expect(COLOURS["--planned"]).not.toBe(COLOURS["--chosen"]);
  });

  it("are never written as a hex in a rule", () => {
    for (const entry of ["--locked", "--planned"] as const) {
      expect(panel).not.toContain(COLOURS[entry]!);
    }
  });

  it("paint the block body, the track, the tick, the bend and the wire", () => {
    for (const state of ["locked", "planned"]) {
      for (const selector of [
        `.symbol.${state} .block-body`,
        `.symbol.${state} .track.lit`,
        `.symbol.${state} .tick.lit`,
        `.symbol.${state} .bend.lit`,
        `.wire.lit.${state}`,
      ]) {
        expect(panel, `no rule for ${selector}`).toContain(selector);
      }
      expect(panel).toContain(`var(--${state})`);
    }
  });

  /** One value moves a colour and its wash together, so the two cannot end up
   *  disagreeing about which state a block is in. */
  it("derive a block's pale fill from its own stroke", () => {
    for (const state of ["locked", "planned"]) {
      const body = panel.slice(panel.indexOf(`.symbol.${state} .block-body`));
      const fill = body.slice(body.indexOf("fill:"), body.indexOf(";"));
      expect(fill).toContain("color-mix");
      expect(fill).toContain(`var(--${state})`);
    }
  });

  /** The channel that is not hue, which is what survives red-green colour
   *  deficiency: whether the train may move here. Track and wires stay solid,
   *  a dash's spacing varying with a wire's angle. */
  it("dash a committed block body and leave a locked one solid", () => {
    const locked = panel.slice(panel.indexOf(".symbol.locked .block-body"));
    expect(locked.slice(0, locked.indexOf("}"))).not.toContain("dasharray");
    const planned = panel.slice(panel.indexOf(".symbol.planned .block-body"));
    expect(planned.slice(0, planned.indexOf("}"))).toContain("dasharray");
    const wire = panel.slice(panel.indexOf(".wire.lit.locked"));
    expect(wire.slice(0, wire.indexOf("}"))).not.toContain("dasharray");
  });

  /** Edit mode is not in this: only a run gets two colours, and a way chosen
   *  in the netlist pane keeps the one it has. The two modes' rules are
   *  declared apart, and an exported file is of the edit mode's sheet, so what
   *  a run paints is the one place to look for it. */
  it("leave the editor's chosen way and refused way as they were", () => {
    expect(exportStyles.cssText).not.toContain("var(--locked)");
    expect(exportStyles.cssText).not.toContain("var(--planned)");
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

  /** And the wires between those legs (#142). A wire sits outside every
   *  symbol's group, so it wears the mark itself and would have been the one
   *  stroke of a red run left in the chosen colour. */
  it("lights the wires of a refused way red as well", () => {
    expect(rule(canvasStyles.cssText, ".wire.lit.offending")).toContain(
      "var(--wrong)",
    );
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

/**
 * What one mode's rules must not reach (#168).
 *
 * The two modes share a stylesheet now, and nearly every rule in the run's
 * half hangs off a class only a run emits — a block is `occupied`, a route is
 * `locked`, a name is `dim` — so it cannot match anything the editor draws.
 * The signal is the exception: both modes draw one, lamps and all, so a rule
 * that dims them has to say whose it is or the editor's signals go dark.
 */
describe("a signal's lamps", () => {
  it("are dimmed only on a run, the editor showing every one lit", () => {
    const rules = [
      ...canvasStyles.cssText
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .matchAll(/([^{}]*)\{([^{}]*)\}/g),
    ].filter(
      ([, selector, declared]) =>
        selector!.includes(".lamp") && declared!.includes("opacity"),
    );
    expect(rules.length).toBeGreaterThan(0);
    for (const [, selector] of rules) {
      expect(selector, `${selector!.trim()} reaches both modes`).toContain(
        '[mode="run"]',
      );
    }
  });
});

/**
 * What the detectors dispute (#153). A block wearing the mark is one a person
 * is being sent to, so the two ways it can go wrong silently are worth
 * pinning: the mark written in a hex nobody can move from the palette, and
 * the mark declared where a block's own state outranks it.
 */
describe("the mark on a disputed block", () => {
  const panel = canvasStyles.cssText.replace(palette.cssText, "");

  it("is the amber entry rather than a hex", () => {
    const body = panel.slice(panel.indexOf(".symbol.disputed .block-body"));
    expect(body.slice(0, body.indexOf("}"))).toContain("var(--amber)");
    expect(panel).not.toContain(COLOURS["--amber"]!);
  });

  it("is declared after the states it rides over", () => {
    // Equal specificity, so source order is the whole of what decides it: a
    // disputed block is nearly always an occupied or a free one as well, and
    // a rule moved above these would take the mark off the blocks that carry
    // it most.
    const disputed = panel.indexOf(".symbol.disputed .block-body");
    for (const state of ["occupied", "locked", "planned"]) {
      expect(disputed).toBeGreaterThan(
        panel.indexOf(`.symbol.${state} .block-body`),
      );
    }
  });
});
