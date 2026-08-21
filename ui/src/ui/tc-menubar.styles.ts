import { css } from "lit";

import {
  dismiss,
  menuBox,
  menuRow,
  menuRowChosen,
  menuShortcut,
} from "./shared.styles.js";

/**
 * The menu bar (`tc-menubar`): three titles at the left, the three commands
 * pressed constantly pinned at the right.
 */
export const menubarStyles = css`
  :host {
    display: flex;
    gap: 0.1rem;
    align-items: center;
    padding: 0.2rem 0.5rem;
    border-bottom: 1px solid var(--rule);
  }

  .spacer {
    flex: 1;
  }

  /* Everything on the bar sits above the overlay that dismisses a menu, so a
     click on the title that is down closes it instead of being swallowed. */
  .menu,
  .tool {
    position: relative;
    z-index: 12;
  }

  ${dismiss}

  .title {
    padding: 0.2rem 0.55rem;
    border: none;
    border-radius: 4px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .title:hover {
    background: #f0eeea;
  }

  .title.on {
    background: var(--chosen);
    color: #fff;
  }

  menu {
    position: absolute;
    top: calc(100% + 0.2rem);
    left: 0;
    z-index: 13;
    ${menuBox}
  }

  /* The drawings hang off the Open row rather than below it. */
  li.submenu {
    position: relative;
  }

  menu.drawings {
    top: -0.3rem;
    left: 100%;
    min-width: 9rem;
  }

  li button {
    ${menuRow}
  }

  /* A label never wraps: a drawing's name is one word however long it is, and
     wrapping is also what stops the submenu widening to fit one. */
  .label {
    flex: 1;
    white-space: nowrap;
  }

  /* The glyph column, one 16 unit square wide whatever the glyph, so every
     label in a menu starts at the same place. */
  .glyph {
    display: flex;
    width: 16px;
  }

  .tick {
    width: 16px;
  }

  .more {
    color: var(--hint);
  }

  kbd {
    ${menuShortcut}
  }

  ${menuRowChosen}

  /* A dead item still reads, so that what is missing to bring it back can be
     worked out from the word rather than from its absence. */
  li button:disabled {
    color: var(--hint);
    opacity: 0.6;
    cursor: default;
  }

  .divider {
    margin: 0.25rem 0.4rem;
    border-top: 1px solid var(--rule);
  }

  /* An icon button is square around its glyph. */
  .tool {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.9rem;
    height: 1.6rem;
    border: none;
    border-radius: 4px;
    background: none;
    color: inherit;
    cursor: pointer;
  }

  .tool:hover {
    background: #f0eeea;
  }
`;
