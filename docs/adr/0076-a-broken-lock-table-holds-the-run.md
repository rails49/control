# A broken lock table holds the run

Resolves the question [#761](https://github.com/rails49/control/issues/761)
raised: what the dispatcher does when its own lock table stops agreeing with
itself.

The dispatcher keeps four maps on `State`: `locks`, `block_of`, `crossing` and
`residue`. Together they say where every train is and what it holds. They are
written at 26 places, and nothing checks that they agree. Three paths the
physical railroad can produce leave a placed train without the lock on the
block it stands in: a stuck detector with GO pressed over the dispute, a train
routed back through its own residue, and a vacate that arrives before the
occupy behind it. Two of them end in a `KeyError` that stops the dispatcher.

[ADR-0048](0048-an-unexplained-reading-holds-the-run.md) settled the same
question for a reading the table cannot explain. This is the table itself.

## Decision

1. **The dispatcher checks the lock table's rules after every event it handles
   and before every grant pass, on the live layout.** The rules are conditions
   on the four maps at one moment, such as "a placed train holds the lock on its
   block". #761 lists them. The check costs about 3 µs against about 65 µs per
   event.
2. **A rule that was not broken at the last check and is broken now holds the
   run**, by the path ADR-0048 takes, and the rule is written to stderr. Nothing
   new goes on the bus.
3. **GO is honoured.** A rule still broken from the last check does not hold
   again, so a person can go on. A rule that clears and breaks later holds
   again.
4. **It does not raise.** ADR-0048's reason stands: an exception out of a
   handler takes the app off the bus.

## Consequences

- A broken table grants nothing until a person has looked and pressed GO.
- A check that is wrong costs one hold and one GO, not a stopped railroad.
- The causes of the three paths are a separate issue. The check makes them
  visible; it does not fix them.

## Considered

- **Raise.** The process exits and the container restarts held, losing the
  queue and every residue. A rule broken at startup restarts it in a loop.
  [ADR-0074](0074-a-person-commands-track-power-and-it-is-cut-when-layout-goes-silent.md)
  decision 8: no power cut covers a dispatcher that stops while `layout` runs.
- **Hold and refuse GO until every rule holds.** The residue path has no
  gesture that repairs it, so the railroad stays held until the container
  restarts, which a person on an iPad cannot do.
- **Check in tests only.** The simulator produces none of the three paths, so
  the check would never fire on them.
