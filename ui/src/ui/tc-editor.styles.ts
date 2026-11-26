import { css } from "lit";

import { LIMITS } from "../model/divider.js";

/** The palette's column, with the netlist shut or open. */
const palette = css`clamp(${LIMITS.palette.least}px, var(--palette-size, var(--pane)), 100% - ${LIMITS.palette.leaves}px)`;

/** The editing view (`tc-editor`): the panes it lays out inside the app's work
 *  row.
 *
 * The palette and the drawing by default. The netlist is a
 * debugging view opened from `View ▸ Netlist` (ADR-0024), and while it is shut
 * the view renders no `tc-netlist` at all — so its column is not
 * declared either, and the canvas has the width rather than a 22rem gap. The
 * app reflects `netlist` onto this host, which is what a stylesheet can
 * read.
 *
 * The palette, the drawing and the netlist are panels on the paper colour,
 * and the view's background is the gap colour (`--gap`), which shows through
 * the dividers between them
 * ([#1401](https://github.com/rails49/control/issues/1401)).
 *
 * Each divider is a gap, `look-gap` (rails49/look#62), clear at rest. The one
 * right of the palette sets the palette's width. The view hands it over as
 * `--palette-size`, and until a person has dragged the divider the width is
 * the shell's `--pane` (#169). The one left of the netlist sets the
 * netlist's width. The view hands it over as `--netlist-size`, and until a
 * person has dragged the divider the width is 22rem. Each size is held to the
 * limits a drag is held to (`model/divider.ts`) when the window changes
 * size. */
export const editorStyles = css`
  :host {
    display: grid;
    grid-template-columns: ${palette} auto 1fr;
    /* The panels' row is the view's height. The menu and the dialogs are in
       rows after it, which are empty. */
    grid-template-rows: 1fr;
    grid-template-areas: "palette palette-divider canvas";
    background: var(--gap);
  }

  :host([netlist]) {
    grid-template-columns:
      ${palette} auto 1fr auto
      clamp(${LIMITS.netlist.least}px, var(--netlist-size, 22rem), 100% - ${LIMITS.netlist.leaves}px);
    grid-template-areas: "palette palette-divider canvas netlist-divider side";
  }

  tc-palette {
    grid-area: palette;
    overflow-y: auto;
    background: var(--paper);
  }

  /* The two look-gaps, by class: only where each sits is set here, and look
     draws the rest. */
  .palette {
    grid-area: palette-divider;
  }

  .netlist {
    grid-area: netlist-divider;
  }

  /* Track power freezes the drawing (ADR-0071), and the palette
     is the one part of this view that would otherwise look as pressable as
     ever: the rail greys its own buttons and the canvas's gestures are the
     machine's to refuse. Greyed and unpressable, not taken away — a frozen
     drawing is read-only, and the tiles say what the editor is for. */
  :host([frozen]) tc-palette {
    opacity: 0.4;
    pointer-events: none;
  }

  tc-canvas {
    grid-area: canvas;
    min-width: 0;
    background: var(--paper);
  }

  tc-netlist {
    grid-area: side;
    overflow-y: auto;
    padding: 0.6rem;
    background: var(--paper);
  }

  .hint {
    color: var(--hint);
  }
`;
