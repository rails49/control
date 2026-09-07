import { css, unsafeCSS } from "lit";

import { RAIL_TURNS_PX } from "../render/units.js";

/**
 * The rail down the left (tc-rail): the views, then the current view's
 * commands, then any press of its own (ADR-0064).
 *
 * A dark green column carrying runs of buttons on a lighter green, taken from
 * the occupancy UI so that two apps a person moves between within one session
 * look like one system. The group is what says which commands belong together
 * once their labels are gone, which is why there are two greens and not one.
 *
 * The width and the button are sized against each other and against the
 * editor's fifteen buttons: four views, then eleven verbs. At the 44px an
 * occupancy button takes that column is 720px tall and does not fit a laptop,
 * so the button is 35px here. The device this app is driven from is a mouse
 * for everything on the rail — the throttle is the touch surface and it has no
 * commands at all — so the touch target the labelling app needs is not what
 * this one is sized to.
 */
export const railStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    align-items: center;
    padding: 0.35rem 0.25rem;
    width: var(--rail-width);
    box-sizing: border-box;
    background: var(--rail);
    color: #fff;
    user-select: none;
    overflow: hidden auto;
  }

  /* One run of buttons: the views at the top, then a group of the current
     view's commands. A group is the only thing that says which commands
     belong together, the labels having gone with the menus (ADR-0064). */
  .group {
    display: flex;
    flex: none;
    flex-direction: column;
    gap: 0.2rem;
    align-items: center;
    width: 100%;
    padding: 0.2rem 0;
    border-radius: 6px;
    background: var(--rail-group);
  }

  button {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 2.2rem;
    height: 2.2rem;
    border: none;
    border-radius: 5px;
    background: none;
    color: inherit;
    cursor: pointer;
  }

  /* The glyphs are drawn at 16 units square (ui/icons.ts) and the rail wants
     them bigger than the band does, so the size is the button's rather than
     the drawing's. */
  button svg {
    width: 1.35rem;
    height: 1.35rem;
  }

  button:hover:not(:disabled) {
    background: rgb(255 255 255 / 0.22);
  }

  /* A command that does not apply. Dead and not hidden, so the column does not
     move under the hand as a selection comes and goes. */
  button:disabled {
    opacity: 0.4;
    cursor: default;
  }

  /* Where you are. A mark and not a missing button: the list is what the views
     are, and the current one is one of them (ADR-0038). */
  button.current {
    background: rgb(255 255 255 / 0.28);
  }

  /* What a command has to say before anybody presses it, which is backup's
     alone (#321). It warns and never disables, so it rides on the button
     rather than changing it. */
  button {
    position: relative;
  }

  .mark {
    position: absolute;
    top: 0.1rem;
    right: 0.2rem;
    color: var(--amber);
    font-size: 0.7rem;
    font-weight: 700;
    line-height: 1;
  }

  /* HOLD and GO: the run view's own press, and the one thing on the rail that
     is not a command (ADR-0037). A word and not a glyph, because what it says
     is what the press will do and the two words are not the same picture. */
  button.run {
    width: 100%;
    height: auto;
    padding: 0.3rem 0;
    border: 1px solid rgb(255 255 255 / 0.5);
    font: inherit;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.06em;
  }

  button.run:disabled {
    border-color: rgb(255 255 255 / 0.25);
  }

  /* A window too short for the column — a phone held sideways, which is how
     the throttle is used. The rail lies down along the top of the work
     instead, and tc-app.styles.ts gives it the row to lie in; both have to
     turn together or the strip is drawn inside a column that is still there,
     which is why the height is RAIL_TURNS_PX in both (render/units.ts). */
  @media (max-height: ${unsafeCSS(RAIL_TURNS_PX)}px) {
    :host {
      flex-direction: row;
      width: auto;
      padding: 0.25rem 0.4rem;
      overflow: auto hidden;
    }

    .group {
      flex-direction: row;
      width: auto;
      padding: 0 0.2rem;
    }

    button.run {
      width: auto;
      padding: 0.3rem 0.6rem;
    }
  }
`;
