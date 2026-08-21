import { css } from "lit";

import {
  dismiss,
  menuBox,
  menuRow,
  menuRowChosen,
  menuShortcut,
} from "./shared.styles.js";

/** The right-click menu (`tc-menu`). */
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
    ${menuShortcut}
  }

  ${menuRowChosen}

  /* Offered and not choosable: greyed says *this does not apply just now*,
     where leaving the item out says nothing at all. */
  button:disabled {
    color: var(--hint);
    cursor: default;
  }
`;
