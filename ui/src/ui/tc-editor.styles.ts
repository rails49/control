import { css } from "lit";

/** The editing view (`tc-editor`): the panes it lays out inside the app's work
 *  row.
 *
 * Two columns by default, the palette and the drawing. The netlist is a
 * debugging view opened from `View ▸ Netlist` (ADR-0024), and while it is shut
 * the view renders no `tc-netlist` at all — so the third column is not
 * declared either, and the canvas has the width rather than a 22rem gap. The
 * app reflects `netlist` onto this host, which is what a stylesheet can
 * read. */
export const editorStyles = css`
  :host {
    display: grid;
    grid-template-columns: 12rem 1fr;
    grid-template-areas: "palette canvas";
  }

  :host([netlist]) {
    grid-template-columns: 12rem 1fr 22rem;
    grid-template-areas: "palette canvas side";
  }

  tc-palette {
    grid-area: palette;
    border-right: 1px solid var(--rule);
    overflow-y: auto;
  }

  tc-canvas {
    grid-area: canvas;
    min-width: 0;
  }

  tc-netlist {
    grid-area: side;
    border-left: 1px solid var(--rule);
    overflow-y: auto;
    padding: 0.6rem;
  }

  .hint {
    color: var(--hint);
  }
`;
