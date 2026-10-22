/**
 * What more than one component wears: the palette and the symbol rules.
 *
 * What a menu is made of — its box, its rows, the overlay a press outside
 * lands on, and the row under the pointer — was here while the band's railroad
 * picker wore it beside the right-click menu (`tc-menu`). The picker went with
 * #733, and those rules moved into `tc-menu.styles.ts`.
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
 * comment below says which kind it is.
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

  /* Named buffer and not stop: stop is an aspect a signal shows (GLOSSARY.md),
     and a class of that name here would be inherited by the lamps of every
     signal at stop, which sit inside a group carrying the aspect's name. */
  .buffer,
  .portal-mouth,
  .tick {
    fill: none;
    stroke: var(--track);
    stroke-linecap: butt;
  }

  /* The A marking a block's A side, in the track's colour and smaller than the
     label, so it does not read as part of the name. */
  .end-a {
    font-family: system-ui, sans-serif;
    fill: var(--track);
    text-anchor: middle;
    dominant-baseline: middle;
    pointer-events: none;
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
