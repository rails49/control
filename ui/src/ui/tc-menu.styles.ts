import { css } from "lit";

import { menuBox, menuRow, menuShortcut } from "./shared.styles.js";

/** The right-click menu (`tc-menu`). */
export const menuStyles = css`
  .dismiss {
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

  button:hover:not(:disabled) {
    background: var(--chosen);
    color: #fff;
  }

  button:hover:not(:disabled) kbd {
    color: inherit;
    opacity: 0.75;
  }

  /* Offered and not choosable: greyed says *this does not apply just now*,
     where leaving the item out says nothing at all. */
  button:disabled {
    color: var(--hint);
    cursor: default;
  }
`;
