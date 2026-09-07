import { css } from "lit";

import { dismiss, menuBox, menuRow, menuRowChosen } from "./shared.styles.js";

/** The right-click menu (tc-menu). */
export const menuStyles = css`
  ${dismiss}

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
    /* The key that does the same thing, set apart from the words rather than
       competing with them. Here and not in shared.styles.ts: with the menu
       bar gone this is the only menu with keys in it, and nothing lives in
       that module that fewer than two sheets wear (#132, ADR-0064). */
    color: var(--hint);
    font: inherit;
  }

  ${menuRowChosen}

  /* Offered and not choosable: greyed says *this does not apply just now*,
     where leaving the item out says nothing at all. */
  button:disabled {
    color: var(--hint);
    cursor: default;
  }
`;
