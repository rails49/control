import { css } from "lit";

/**
 * Declaration body. The box a menu drops into, shared by the right-click menu
 * and the band's picker, so that the app's two menus read as one. Position is
 * the caller's: one is pinned to the pointer and the other hangs off the name
 * it lists alternatives to. Named for the menu it belongs to, `tc-panel` being
 * another thing entirely.
 */
const menuBox = css`
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
const menuRow = css`
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

/**
 * Whole rule set. The overlay a menu drops over the page: a press anywhere
 * outside the menu lands here and dismisses it, and nothing under it is
 * clicked by the same press. Worn by both menus, which is why it has to be one
 * block — the two z-indices have to agree with each other and with everything
 * `tc-app.styles.ts` lifts above it.
 *
 * What the overlay does with a press is `dismissal.ts`, which is the element
 * that wears this, for both components. A right-click is the one it hands on
 * rather than swallows (#180).
 */
const dismiss = css`
  .dismiss {
    position: fixed;
    inset: 0;
    z-index: 10;
  }
`;

/**
 * Whole rule sets. The row under the pointer, in both menus: the one item a
 * press would choose, painted in the chosen colour so that a menu says what it
 * is about to do.
 *
 * The selector is `li` deep because both menus wrap every button in one; at
 * (0,2,2) it still beats the `menuRow` the row wears underneath, which the two
 * callers write at (0,0,1) and (0,0,2). A disabled row is left out — an item
 * that does not apply is not about to be chosen.
 */
const menuRowChosen = css`
  li button:hover:not(:disabled) {
    background: var(--chosen);
    color: #fff;
  }

  /* Whatever sits beside the label goes with it: the key set, which is
     tc-menu's, and the .more glyph, which is the picker's — neither renders
     the other's element, so half of the selector matches nothing in each. */
  li button:hover:not(:disabled) kbd,
  li button:hover:not(:disabled) .more {
    color: inherit;
    opacity: 0.75;
  }
`;

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
