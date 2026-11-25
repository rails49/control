import { css, unsafeCSS } from "lit";

import { DARK } from "../render/units.js";
import { palette } from "./shared.styles.js";

/** Declaration body. What the palette's entries become on a dark page, built
 *  the way `palette` is built from the light ones (render/units.ts). */
const afterDark = unsafeCSS(
  Object.entries(DARK)
    .map(([name, value]) => `${name}: ${value};`)
    .join("\n      "),
);

/**
 * The app (tc-app): the page every view is laid out on.
 *
 * The band, the rail and the frame around the work are `@rails49/look`'s, and
 * this sheet styles none of them. The palette of custom properties is declared
 * here, a page being the host every component inherits it from (#86).
 *
 * The editor and the run view fill the work with a left pane and a surface,
 * and the shell is where that pane's width is declared: the editor's palette
 * has it, and the run view's pane has it until a person drags its divider
 * ([#169](https://github.com/rails49/control/issues/169),
 * [#1344](https://github.com/rails49/control/issues/1344)).
 *
 * Every view sits in the work, over the others, and the ones that are not
 * current are hidden rather than taken away. Taking it away would close the
 * live session on every toggle, which is the wrong price for looking at the
 * netlist; and visibility leaves the hidden view its real width and height,
 * so a canvas fitted while it is hidden fits to the shape it will be seen at.
 */
export const appStyles = css`
  :host {
    ${palette}

    /* The left pane's width: the palette in edit, and the roster in run until
       its divider is dragged. */
    --pane: 12rem;

    display: block;
    background: var(--paper);
    color: var(--ink);
    font: 13px/1.4 system-ui, sans-serif;
  }

  /* The same palette on a dark page, and the operating system decides
     (look#12). Only the work follows it; the chrome is look's and keeps one
     value in both.

     It is on the same host the palette is, which is the page every view
     inherits from, and it is written here rather than in shared.styles.ts
     because one component wears it and nothing lives there that fewer than two
     do (#132). */
  @media (prefers-color-scheme: dark) {
    :host {
      ${afterDark}
    }
  }

  tc-editor,
  tc-panel,
  tc-stock,
  tc-throttle {
    position: absolute;
    inset: 0;
    overflow: hidden;
  }

  /* Not the HTML hidden attribute: its display:none would take the view's
     width and height away with it, and the shape is the half worth keeping. */
  .off {
    visibility: hidden;
  }
`;
