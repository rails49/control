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

import { readdirSync, readFileSync } from "node:fs";

import type { CSSResult } from "lit";
import { describe, expect, it } from "vitest";

import {
  COLOURS,
  DARK,
  RAIL_BUTTON_PX,
  RAIL_TURNS_PX,
} from "../src/render/units.js";
import * as shared from "../src/ui/shared.styles.js";
import {
  dismiss,
  menuBox,
  menuRow,
  menuRowChosen,
  palette,
  symbols,
} from "../src/ui/shared.styles.js";
import { appStyles } from "../src/ui/tc-app.styles.js";
import { canvasStyles, exportStyles } from "../src/ui/tc-canvas.styles.js";
import { editorStyles } from "../src/ui/tc-editor.styles.js";
import { headerStyles } from "../src/ui/tc-header.styles.js";
import { menuStyles } from "../src/ui/tc-menu.styles.js";
import { paletteStyles } from "../src/ui/tc-palette.styles.js";
import { panelStyles } from "../src/ui/tc-panel.styles.js";
import { railStyles } from "../src/ui/tc-rail.styles.js";
import { rosterStyles } from "../src/ui/tc-roster.styles.js";
import { throttleStyles } from "../src/ui/tc-throttle.styles.js";

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
  paletteStyles,
  panelStyles,
  railStyles,
  rosterStyles,
  throttleStyles,
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
    expect(throttleStyles.cssText).not.toContain(palette.cssText);
  });

  /** An exported file has no host above the svg to inherit from (#86). */
  it("is written onto the svg an export carries", () => {
    expect(exportStyles.cssText).toContain(palette.cssText);
  });
});

/**
 * The shell has one left-pane slot and each view fills it: the palette in
 * edit, the roster in run, the trains to drive in the throttle (#169, #291).
 * One width, declared where the page is, or the panes drift apart across a
 * switch and the slot stops being one.
 */
describe("the left-pane slot", () => {
  it("is declared on the page and read by every view that fills it", () => {
    expect(appStyles.cssText).toContain("--pane:");
    for (const sheet of [editorStyles, panelStyles, throttleStyles]) {
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
  /** The box and a row of it: both, or the app's two menus stop reading as
   *  one. The key set beside a label is no longer among them — with the menu
   *  bar gone only `tc-menu` prints one (ADR-0064), so those rules are its
   *  own. */
  it("is the same for the right-click menu and the band's picker", () => {
    for (const part of [menuBox, menuRow]) {
      expect(menuStyles.cssText).toContain(part.cssText);
      expect(headerStyles.cssText).toContain(part.cssText);
    }
  });

  /** The overlay a press outside lands on and the row under the pointer, both
   *  whole rule sets. Which two sheets wear them is the claim: the mechanical
   *  test above counts wearers and would take any two, and a menu is only one
   *  thing if these are the two. */
  it("dismisses and paints the chosen row the same way in both", () => {
    for (const part of [dismiss, menuRowChosen]) {
      expect(menuStyles.cssText).toContain(part.cssText);
      expect(headerStyles.cssText).toContain(part.cssText);
    }
  });
});

/**
 * The rail turns into a strip along the top of the work below a short window
 * (ADR-0064), and two sheets have to turn with it: `tc-app` gives it the row
 * to lie in and `tc-rail` lies its own contents down. A media query cannot read
 * a custom property, so the height is interpolated into each from
 * `render/units.ts`; switching at different heights would draw the strip inside
 * a column that is still there.
 */
describe("the height the rail turns at", () => {
  it("is the one number in both sheets that turn", () => {
    const turn = `@media (max-height:${RAIL_TURNS_PX}px)`;
    for (const sheet of [appStyles, railStyles]) {
      expect(sheet.cssText.replace(/\s+/g, "")).toContain(
        turn.replace(/\s+/g, ""),
      );
    }
  });
});

/**
 * Both themes, with the operating system deciding (#547).
 *
 * LOOK.md binds three things here: both Shoelace themes are linked with no
 * toggle in the page, the chrome keeps one value in both, and the work pane
 * follows the theme. The first two are checked above and beside this; this is
 * the third, and it is the one a sheet breaks by accident — a ground written
 * as a hex is invisible in the light theme and unreadable in the dark one,
 * where the text over it has moved and the ground has not.
 */
describe("what a pane paints its ground with", () => {
  /** The sheets of the work, which is everything but the chrome. The band and
   *  the rail are the two that must not follow the theme, and they are left
   *  out by identity rather than by name: renaming a sheet would otherwise
   *  quietly change what this covers. */
  const chrome: CSSResult[] = [headerStyles, railStyles];
  const panes = Object.entries(sheets).filter(
    ([, sheet]) => !chrome.includes(sheet),
  );

  it.each(panes)("%s asks the palette rather than naming a colour", (_, sheet) => {
    const written = sheet.cssText
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(palette.cssText, "");
    const named = [
      ...written.matchAll(/(?:background|fill)\s*:[^;}]*#[0-9a-fA-F]{3,8}/g),
    ].map(([rule]) => rule.trim());
    expect(named).toEqual([]);
  });

  /** The dark half of the palette, on the one host the light half is declared
   *  on (ADR-0038). A view redeclaring it would be a second place for a colour
   *  to be changed in, and a view that only redeclared half of it would paint
   *  a dark pane inside a light page. */
  it("is redeclared for a dark page on the page itself", () => {
    expect(appStyles.cssText).toContain("prefers-color-scheme: dark");
    expect(appStyles.cssText).toContain(`--paper: ${DARK["--paper"]}`);
    for (const sheet of [editorStyles, panelStyles, throttleStyles]) {
      expect(sheet.cssText).not.toContain("prefers-color-scheme");
    }
  });

  /** An export is a file that leaves here: it carries the light palette
   *  whichever theme drew it, so what it looks like does not depend on the
   *  settings of the machine it was saved from (#86). */
  it("leaves an exported file in the light palette it was written in", () => {
    expect(exportStyles.cssText).not.toContain("prefers-color-scheme");
  });

  /** The page under the app, which is a plain stylesheet and cannot read the
   *  palette. It shows while the module loads and nowhere else, and the two
   *  values it names are the two the app would paint. */
  it("is the app's own paper on the page underneath it", () => {
    const page = readFileSync(
      new URL("../src/page.css", import.meta.url),
      "utf8",
    );
    const grounds = [...page.matchAll(/background:\s*([^;]+);/g)].map(
      ([, value]) => value!.trim(),
    );
    expect(grounds).toEqual([COLOURS["--paper"], DARK["--paper"]]);
  });

  /** Both themes linked, wherever one of them is. Shoelace's dark theme is a
   *  class rather than a query of its own, so linking it is half the job and
   *  `ui/theme.ts` is the other half; a module that linked one theme alone
   *  would leave that page in it whatever the system says. */
  it("links both Shoelace themes in every module that links one", () => {
    const dir = new URL("../src/ui/", import.meta.url);
    for (const file of readdirSync(dir).filter((it) => it.endsWith(".ts"))) {
      const source = readFileSync(new URL(file, dir), "utf8");
      expect(
        source.includes("themes/light.css"),
        `${file} links one theme and not the other`,
      ).toBe(source.includes("themes/dark.css"));
    }
  });
});

/**
 * The values the look rules bind, against the copy they came from (#548).
 *
 * Six colours and two sizes are one system across rails49's UIs
 * ([ADR-0003](https://github.com/rails49/.github/blob/main/docs/adr/0003-the-look-rules-bind-place-colour-and-small-screens-not-code.md)),
 * and this app keeps them in its own form: the colours in the table that holds
 * every other colour it draws with, the sizes beside them as numbers a media
 * query and a stylesheet can be interpolated from. `ui/look/tokens.css` is the
 * copy of what they are, verbatim and pinned to a commit (ADR-0005), and this
 * is the assertion that the two agree.
 *
 * It reads the copy and nothing else. A check that fetched the source would go
 * red on somebody else's commit, and under this repository's rule that `main`
 * moves only by a green required check with no bypass, that red-lights every
 * open pull request here until someone syncs.
 */
describe("the values the look rules bind", () => {
  /** The copy, as the tokens it declares. Comments out first: they carry a
   *  `--rail-button` or two in prose, and a regex reading declarations cannot
   *  tell those from the real ones. */
  const bound = Object.fromEntries(
    [
      ...readFileSync(new URL("../look/tokens.css", import.meta.url), "utf8")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .matchAll(/(--[a-z-]+)\s*:\s*([^;]+);/g),
    ].map(([, name, value]) => [name!, value!.trim()]),
  );

  /** The colours among them: the chrome's, which keep one value in both
   *  themes. */
  const chrome = Object.keys(bound).filter((name) => bound[name]!.startsWith("#"));

  /** Every token in the copy, so that one added over there fails here rather
   *  than passing unnoticed: a value this app has not followed yet is the
   *  whole point of keeping the copy. */
  it("are the eight the copy holds", () => {
    expect(Object.keys(bound).sort()).toEqual([
      "--band",
      "--band-ink",
      "--rail",
      "--rail-button",
      "--rail-group",
      "--rail-turns",
      "--stop",
      "--stop-ink",
    ]);
  });

  it("paint the band and the rail", () => {
    for (const token of chrome) {
      expect(COLOURS[token], token).toBe(bound[token]);
    }
  });

  /** STOP and every fault on the band are drawn with the copy's red and
   *  nothing else, so the band's red is the same one in both themes and in
   *  every app (#582). */
  it("are the only red the band draws with", () => {
    const flat = headerStyles.cssText.replace(/\s+/g, "");
    expect(flat).toContain("background:var(--stop)");
    expect(flat).toContain("color:var(--stop-ink)");
    expect(flat).not.toMatch(/var\(--wrong/);
  });

  it("turn the rail into a strip at the height the copy gives", () => {
    expect(`${RAIL_TURNS_PX}px`).toBe(bound["--rail-turns"]);
  });

  it("size every button on the rail", () => {
    expect(`${RAIL_BUTTON_PX}px`).toBe(bound["--rail-button"]);
  });

  /** And the number is what the sheet draws with, not a constant beside it: a
   *  button sized in `rem` next to a `RAIL_BUTTON_PX` nothing reads would pass
   *  the assertion above with the rule broken. */
  it("are what the rail's own sheet is written in", () => {
    const flat = railStyles.cssText.replace(/\s+/g, "");
    expect(flat).toContain(`width:${RAIL_BUTTON_PX}px`);
    expect(flat).toContain(`height:${RAIL_BUTTON_PX}px`);
  });

  /** The chrome keeps one value in both themes and the work pane follows the
   *  theme, which is the division LOOK.md draws and this is it in code: the
   *  six colours the copy binds have no dark value, and every other colour
   *  the app draws with has one. A colour added to the palette without one
   *  fails here rather than painting in its light value on a dark page. */
  it("are the colours that keep one value in both themes", () => {
    for (const name of Object.keys(COLOURS)) {
      expect(name in DARK, `${name} in the dark palette`).toBe(
        !chrome.includes(name),
      );
    }
    expect(Object.keys(DARK).every((name) => name in COLOURS)).toBe(true);
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
    expect(COLOURS["--committed"]).toBeDefined();
    expect(COLOURS["--locked"]).not.toBe(COLOURS["--green"]);
    expect(COLOURS["--committed"]).not.toBe(COLOURS["--chosen"]);
  });

  it("are never written as a hex in a rule", () => {
    for (const entry of ["--locked", "--committed"] as const) {
      expect(panel).not.toContain(COLOURS[entry]!);
    }
  });

  it("paint the block body, the track, the tick, the bend and the wire", () => {
    for (const state of ["locked", "committed"]) {
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
    for (const state of ["locked", "committed"]) {
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
    const committed = panel.slice(panel.indexOf(".symbol.committed .block-body"));
    expect(committed.slice(0, committed.indexOf("}"))).toContain("dasharray");
    const wire = panel.slice(panel.indexOf(".wire.lit.locked"));
    expect(wire.slice(0, wire.indexOf("}"))).not.toContain("dasharray");
  });

  /** Edit mode is not in this: only a run gets two colours, and a way chosen
   *  in the netlist pane keeps the one it has. The two modes' rules are
   *  declared apart, and an exported file is of the edit mode's sheet, so what
   *  a run paints is the one place to look for it. */
  it("leave the editor's chosen way and refused way as they were", () => {
    expect(exportStyles.cssText).not.toContain("var(--locked)");
    expect(exportStyles.cssText).not.toContain("var(--committed)");
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
   *  shows only for what stopped derivation, so it wears that weight (#91) —
   *  in the chrome's red, which is the light theme's and stays put on a dark
   *  page (#582). An overlap and a missing address leave it clean, and nothing
   *  there should ever read in the quiet one. */
  it("marks the band in the weight that stops derivation", () => {
    const mark = rule(headerStyles.cssText, ".refused");
    expect(mark).toContain("var(--stop-ink)");
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

  it("are lit by every aspect the dispatcher publishes", () => {
    // The aspect arrives as a class name, so a sheet that misses one leaves
    // those signals wrongly lit and nothing red: the classes are correct and
    // only the paint is wrong, which is what the rename of `approach` to
    // `caution` could have left behind (#235). Each lamp of each aspect, not
    // each aspect: a `caution` that lost its amber rule paints green alone,
    // which is `clear` — full speed where the dispatcher said be ready to
    // stop.
    for (const lit of [
      ".signal.stop .lamp.red",
      ".signal.caution .lamp.green",
      ".signal.caution .lamp.amber",
      ".signal.clear .lamp.green",
    ]) {
      expect(canvasStyles.cssText).toContain(lit);
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
    for (const state of ["occupied", "locked", "committed"]) {
      expect(disputed).toBeGreaterThan(
        panel.indexOf(`.symbol.${state} .block-body`),
      );
    }
  });
});
