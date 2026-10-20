import { css } from "lit";

/**
 * The station clock (`tc-clock`): a white face, black bars and hands, and a
 * red second hand, in whatever theme the page is in — it is a picture of a
 * clock on a platform, which is those colours by day and by night, and so the
 * one sheet here that names colours rather than asking the palette
 * (ui/THROTTLE.md).
 */
export const clockStyles = css`
  :host {
    display: inline-block;
    width: 4.5rem;
    height: 4.5rem;
  }

  svg {
    display: block;
    width: 100%;
    height: 100%;
  }

  .face {
    fill: #fff;
    stroke: #000;
    stroke-width: 1.5;
  }

  .marker {
    stroke: #000;
    stroke-width: 4;
  }

  .hour,
  .minute {
    stroke: #000;
    stroke-linecap: butt;
  }

  .hour {
    stroke-width: 7;
  }

  .minute {
    stroke-width: 5;
  }

  .second {
    stroke: #d40000;
    stroke-width: 1.5;
  }
`;
