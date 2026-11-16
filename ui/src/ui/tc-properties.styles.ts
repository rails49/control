import { css } from "lit";

/** The properties dialog (`tc-properties`). */
export const propertiesStyles = css`
  sl-input,
  sl-select {
    display: block;
    margin-bottom: 0.7rem;
  }

  h3 {
    margin: 1rem 0 0.4rem;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
  }

  /* A text widget's Default: the buttons that put its codes in, and its
     preview, bold and coloured as on a run (#1280) in HTML's own terms —
     the run view's rules set SVG fill. */
  .codes {
    display: flex;
    gap: 0.4rem;
    margin: -0.3rem 0 0.7rem;
  }

  .preview {
    margin: 0 0 0.7rem;
  }

  .preview .bold {
    font-weight: 700;
  }

  .preview .red {
    color: var(--red);
  }

  .preview .amber {
    color: var(--amber);
  }

  .preview .green {
    color: var(--green);
  }

  .hint {
    margin: 0 0 0.5rem;
    color: var(--hint);
  }
`;
