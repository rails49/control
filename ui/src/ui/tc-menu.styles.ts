import { css } from "lit";

import { menuBox, menuRow, menuShortcut } from "./shared.styles.js";

/** The right-click menu (`tc-menu`). */
export const menuStyles = css`
  .sheet {
    position: fixed;
    inset: 0;
    z-index: 10;
  }

  menu {
    position: fixed;
    z-index: 11;
    ${menuBox}
  }

  button {
    ${menuRow}
  }

  button span {
    flex: 1;
  }

  kbd {
    ${menuShortcut}
  }

  button:hover {
    background: var(--chosen);
    color: #fff;
  }

  button:hover kbd {
    color: inherit;
    opacity: 0.75;
  }
`;
