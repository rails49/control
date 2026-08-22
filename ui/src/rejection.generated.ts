// Generated from src/tc49/lib/rejection.py. Run `tc49 generate` to update.
//
// Why the dispatcher rejected a request. The names alone: what each one
// tells a reader is the panel's wording, and no part of the schema.

/** A rejection reason, as `tc49/dispatch/request_rejected` carries it. A
 *  wording table keyed by this is total, so a reason minted in Python and
 *  left unworded here is a compile error rather than a raw token on screen. */
export type Reason =
  | "malformed"
  | "unknown_train"
  | "unknown_block"
  | "no_origin"
  | "wrong_origin"
  | "no_fit"
  | "no_entry"
  | "unreachable";
