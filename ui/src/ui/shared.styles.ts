/**
 * What more than one component wears: the palette, the symbol rules, and what
 * a menu is made of — its box, its rows, the key set beside a
 * label, the overlay a press outside lands on, and the row under the pointer.
 *
 * The page is not here. There is one page, and `tc-app.styles.ts` is it
 * (ADR-0038).
 *
 * Nothing lives here that fewer than two component stylesheets wear. Without
 * that limit *what more than one component wears* admits every duplication
 * ever written, and this module grows back into the thousand-line `styles.ts`
 * it came out of by another road; `test/styles.test.ts` asserts it of every
 * export.
 *
 * The exports come in two kinds, and the module is sectioned by them because
 * their types cannot tell them apart. A **declaration body** is interpolated
 * inside a selector the caller writes; a **whole rule set** brings its own
 * selectors and is interpolated at the top level of a sheet. A body put where
 * a rule set was meant nests silently and paints nothing at all, so each doc
 * comment below says which kind it is. `menuRow` and `menuRowChosen` are the
 * pair to watch: one prefix, opposite calling conventions.
 *
 * The styles are kept out of the components so that what a component has is
 * behaviour; each component's own rules sit in a module beside it, and read
 * from here what it shares with another.
 *
 * Every dimension and every colour comes from `render/units.ts`: the colours
 * are declared here as the custom properties the rules read, and the widths
 * are interpolated straight in, so a stroke is W wide because W says so and
 * not because two files agree.
 */

import { css, unsafeCSS } from "lit";

import {
  BLOCK,
  COLOURS,
  HAIRLINE,
  SLIP,
  TERMINAL,
  W,
} from "../render/units.js";

// --- Declaration bodies ---------------------------------------------------
// Interpolated inside a selector the caller writes: `:host { ${palette} }`.

/** Declaration body. The palette, as the custom properties every rule
 *  reads. */
export const palette = unsafeCSS(
  Object.entries(COLOURS)
    .map(([name, value]) => `${name}: ${value};`)
    .join("\n    "),
);

/**
 * Declaration body. The box a menu drops into, shared by the right-click menu
 * and the bar's, so that the editor's two menu systems read as one. Position
 * is the caller's: one is pinned to the pointer and the other hangs off its
 * title. Named for the menu it belongs to, `tc-panel` being another thing
 * entirely.
 */
export const menuBox = css`
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  min-width: 12rem;
  border: 1px solid var(--rule);
  border-radius: 5px;
  background: var(--paper);
  box-shadow: 0 6px 18px rgb(0 0 0 / 0.14);
  font: 13px/1.4 system-ui, sans-serif;
`;

/** Declaration body. One row of a menu: a label that takes the width, and
 *  whatever sits either side of it. */
export const menuRow = css`
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
  padding: 0.3rem 0.5rem;
  border: none;
  border-radius: 3px;
  background: none;
  color: var(--ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
`;

/** Declaration body. The key that does the same thing, set apart from the
 *  words rather than competing with them. */
export const menuShortcut = css`
  color: var(--hint);
  font: inherit;
`;

// --- Whole rule sets ------------------------------------------------------
// Interpolated at the top level of a sheet, selectors and all: `${symbols}`.

/**
 * Whole rule sets. The symbols themselves, drawn the same on the canvas and
 * on a palette tile: both are the symbol's own coordinates, one grid square to
 * one user unit, so one set of rules serves both and a tile shows what will be
 * placed. Track is solid and round-capped, never patterned — wires run at any
 * angle, and a pattern's spacing would vary with direction.
 */
export const symbols = css`
  .track {
    fill: none;
    stroke: var(--track);
    stroke-width: ${W};
    stroke-linecap: round;
  }

  /* White in edit mode; run mode recolours it by occupancy through the same
     class, in the canvas's own sheet. */
  .block-body {
    fill: var(--body);
    stroke: var(--track);
    stroke-width: ${BLOCK.body.border};
  }

  /* A stroke ending inside another shape is cut square, so that a round cap
     cannot bulge past a buffer bar. */
  .track.cut {
    stroke-linecap: butt;
  }

  .plaque {
    fill: var(--track);
  }

  /* Every lamp is drawn, and edit mode shows every one lit. Run mode dims the
     lamps the aspect does not light; a lamp is named for its colour, an
     aspect being a set of lamps rather than one. */
  .lamp.green {
    fill: var(--green);
  }

  .lamp.red {
    fill: var(--red);
  }

  .lamp.amber {
    fill: var(--amber);
  }

  /* Named buffer and not stop: stop is an aspect a signal shows (CONTEXT.md),
     and a class of that name here would be inherited by the lamps of every
     signal at stop, which sit inside a group carrying the aspect's name. */
  .buffer,
  .mark,
  .portal-mouth,
  .tick {
    fill: none;
    stroke: var(--track);
    stroke-linecap: butt;
  }

  /* The plus marking a block's A side, at the weight of the rectangle it sits
     on the corner of. */
  .mark {
    stroke-width: ${BLOCK.body.border};
  }

  .buffer {
    stroke-width: ${TERMINAL.bar.w};
  }

  .portal-mouth {
    stroke: var(--hint);
    stroke-width: ${HAIRLINE};
  }

  .tick {
    stroke-width: ${SLIP.weight};
  }
`;


/**
 * Whole rule set. The overlay a menu drops over the page: a press anywhere
 * outside the menu lands here and dismisses it, and nothing under it is
 * clicked by the same press. Worn by both menu systems, which is why it has
 * to be one block — the two z-indices have to agree with each other and with
 * everything the bar lifts above it.
 */
export const dismiss = css`
  .dismiss {
    position: fixed;
    inset: 0;
    z-index: 10;
  }
`;

/**
 * Whole rule sets. The row under the pointer, in both menu systems: the one
 * item a press would choose, painted in the chosen colour so that a menu says
 * what it is about to do.
 *
 * The selector is `li` deep because the bar's rows are, and both menus wrap
 * every button in one; at (0,2,2) it still beats the `menuRow` the row wears
 * underneath, which the two callers write at (0,0,1) and (0,0,2). A disabled
 * row is left out — an item that does not apply is not about to be chosen.
 */
export const menuRowChosen = css`
  li button:hover:not(:disabled) {
    background: var(--chosen);
    color: #fff;
  }

  /* Whatever sits beside the label goes with it: the key set, and the .more
     glyph, which is the bar's own — tc-menu renders no such element and that
     half of the selector matches nothing there. */
  li button:hover:not(:disabled) kbd,
  li button:hover:not(:disabled) .more {
    color: inherit;
    opacity: 0.75;
  }
`;
