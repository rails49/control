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

  /* The name field while it holds a name the drawing will not take. Red is
     what stops the edit landing, the same weight the canvas marks a fault
     that stops derivation in (ADR-0024). */
  sl-input.refused {
    --sl-input-border-color: var(--wrong);
    --sl-input-help-text-color: var(--wrong);
  }

  .hint {
    margin: 0 0 0.5rem;
    color: var(--hint);
  }
`;
