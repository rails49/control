import { css, unsafeCSS } from "lit";

import { RAIL_BUTTON_PX, RAIL_TURNS_PX } from "../render/units.js";

/**
 * The rail down the left (tc-rail): the views, then the current view's
 * commands, then any press of its own (ADR-0064).
 *
 * A dark green column carrying runs of buttons on a lighter green, taken from
 * the occupancy UI so that two apps a person moves between within one session
 * look like one system. The group is what says which commands belong together
 * once their labels are gone, which is why there are two greens and not one.
 *
 * The button is `RAIL_BUTTON_PX`, which the look rules bind across the
 * project's UIs (`ui/look/tokens.css`, ADR-0003), and the column's width is
 * that plus the padding either side of it. This app would have picked smaller
 * — the rail is driven with a mouse in every view but the throttle — and the
 * size is not its to pick.
 *
 * **What that costs is height**, and the answer is a scroll. The editor's rail
 * is fifteen buttons — four views, then eleven verbs — which at this size is
 * about 710px of column and taller than the work in a laptop window. So the
 * spacing is as tight as the buttons will sit, and what is left over scrolls.
 * The views are pinned while it does: a person scrolled to the bottom of the
 * verbs can still leave the view, which is the one press that must not be the
 * one scrolled away. Folding the groups was the alternative and costs two
 * presses for every command to save a scroll on a short window.
 *
 * Scrolling is not what `RAIL_TURNS_PX` answers. That height is a window too
 * short for a column at all — a phone held sideways — and there the rail lies
 * down along the top of the work instead.
 */
export const railStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: center;
    /* No padding above the first group and none below the last: the column is
       long enough already, and a pinned group has to sit flush against the top
       of the scroll or the buttons under it show in the gap. */
    padding: 0 4px;
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
    gap: 2px;
    align-items: center;
    width: 100%;
    padding: 2px 0;
    border-radius: 6px;
    background: var(--rail-group);
  }

  /* The views, pinned to the top of the scroll. The way to another view is
     always the same press whatever the column has been scrolled to, and the
     group's own ground is opaque, so the verbs pass under it rather than
     through it. */
  .group.views {
    position: sticky;
    top: 0;
    z-index: 1;
  }

  button {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: ${RAIL_BUTTON_PX}px;
    height: ${RAIL_BUTTON_PX}px;
    border: none;
    border-radius: 5px;
    background: none;
    color: inherit;
    cursor: pointer;
  }

  /* The glyphs are drawn at 16 units square (ui/icons.ts) and the rail wants
     them bigger than the band does, so the size is the button's rather than
     the drawing's: a fraction of it, so the two cannot come apart. */
  button svg {
    width: ${0.6 * RAIL_BUTTON_PX}px;
    height: ${0.6 * RAIL_BUTTON_PX}px;
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
      padding: 4px 6px;
      overflow: auto hidden;
    }

    .group {
      flex-direction: row;
      width: auto;
      padding: 0 2px;
    }

    /* Nothing is pinned in the strip: it scrolls sideways, and a group stuck
       to the top of a row it is already at the top of would only cover the
       group beside it. */
    .group.views {
      position: static;
    }

    button.run {
      width: auto;
      padding: 0.3rem 0.6rem;
    }
  }
`;
