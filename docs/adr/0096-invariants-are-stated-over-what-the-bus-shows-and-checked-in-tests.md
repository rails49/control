# Invariants are stated over what the bus shows, and checked in tests

The rules about the railroad's state are prose in the ADRs, and the code
that keeps them is spread over the apps, each its own process (ADR-0059).
Of 58 such rules in ADR-0001 to ADR-0094, seven were checked after every
event, all through the dispatcher's `broken()`. Bugs that broke the others
(#791, #806, #811, #836, #1041) were found by reading the code.

## Decision

1. **An invariant reads only what the bus shows:** the retained values, and
   a record it keeps of the messages so far. It reads no app's internal
   state. It then describes the railroad rather than the code, it holds
   through a rewrite of an app, and any app or test can use it.
2. **`tc49/lib/invariants.py` holds them**, one function per ADR rule, named
   for the ADR. The module is the list of which ADRs state invariants. No ADR
   is marked, since an accepted ADR does not change (the organisation's
   ADR-0021). An issue that adds an ADR stating an invariant adds its
   function.
3. **When one is checked depends on whose topics it reads.**
   - One app's topics: after every message.
   - Several apps' topics, retained values only: once the bus has nothing
     left to deliver. Between messages such an invariant can be broken for a
     moment, for example power `off` before the dispatcher's `aspects`
     follow.
   - Several apps' topics, with a record of messages: on the in-process bus
     only, where every subscriber sees one order. Under reordered delivery an
     observer cannot tell what another app had heard when it acted.
4. **Invariants are checked in tests only**, by the property suite and the
   stateful tests, over the simulator assembly and over an assembly with
   `layout` in which the test publishes the device rows. A check on the
   running railroad waits until they have run in tests without false alarms.
5. **A rule that needs an app's internal state stays in that app's tests.**
   `broken()` and `safe()` are of this kind.

## Rejected

- **Invariants over retained values only.** It leaves 36 of the 58 rules in
  app tests; a block's occupancy, for one, is only ever an event.
- **Invariants over each app's internal state.** They would describe the
  code, break with every rewrite, and could not be read from `lib`.
- **A live check now.** It needs a rule for how long a breach of a
  cross-app invariant must last before it counts, and what follows it.
