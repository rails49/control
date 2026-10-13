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

  .hint {
    margin: 0 0 0.5rem;
    color: var(--hint);
  }
`;
