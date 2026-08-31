# A signal is what the dispatcher tells the driver

**Qualified by
[ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md).**
While the run is `held` every signalled end shows `stop`, whatever the locks
say. The reading below is unchanged and gated: an aspect answers "may the
train in this block leave via this end", and while held the answer is no.

**Amended for
[#235](https://github.com/rails49/control/issues/235):** the middle aspect was
`approach` when this was written and is now `caution`. The text below has been
rewritten to the new name; nothing about the reading changed.

The dispatcher's authority reaches the driver as a **signal aspect**, and the
driver's whole job is to turn that aspect into a speed. It decides nothing
about where the train goes: the turnouts are already thrown when the aspect
clears, so a train follows the rails it is given and the only open question is
how fast.

Three aspects, read off how far ahead the dispatcher has locked:

| Locked ahead | Aspect | Meaning to the driver |
| --- | --- | --- |
| nothing | `stop` | stand |
| one block | `caution` | proceed, prepared to stop at the next signal |
| two or more | `clear` | full speed |

**The three against the Swiss system**: `stop` = Halt, `caution` = Fb 2,
`clear` = Freie Fahrt (Fb 1)
([reference](https://gleis3a.de/threads/signalsystemschweiz)). `clear` already
is Freie Fahrt in signalling English and says line speed rather than mere
permission. `approach` was the odd one out: in signalling English it means
"prepared to stop at the next signal", a braking instruction, while Fb 2 names
a speed. `caution` says the same braking instruction in ordinary words. Whether
the middle aspect stays a braking instruction or becomes a speed is the open
speed-signalling subject in [GOALS.md](../GOALS.md#driving).

**Three is exactly sufficient, not a compromise.** A fourth aspect would need a
fourth speed regime to name, and there is none: full speed is full speed, so
locking a third block ahead says nothing a signal could show
([ADR-0026](0026-two-blocks-ahead-is-full-speed.md)). Signals are red unless a
block has been reserved, which falls out rather than being a rule — an aspect
is a function of locks held, and a block nobody has locked toward shows `stop`.

## The aspect rides on the grant

`move_granted` already carries `(train, transit, into)` and is already the
dispatcher's statement of authority. It gains the aspect, and
`SYSTEM.md`'s line about a grant being "the driver's green signal" stops being
a metaphor.

The tempting alternative was a topic addressed to the train, with
`move_granted` left as the lock ledger. It was rejected because it buys
nothing: a third encoding of one authority, and `move_granted` would be left
with no consumer outside metrics.

What is *not* optional is that the dispatcher addresses the driver at all. A
driver cannot work out which signal it faces on its own, because **sensors are
anonymous** — the layout interface never asserts train identity, and the
dispatcher recovers it from its own lock table
([SYSTEM.md](../SYSTEM.md#layout-interface)). A driver deriving its own
position would rebuild that lock table, and any divergence is a train obeying
the wrong signal. A human driver has no such trouble, which is why the goal
statement reads naturally and the bus contract does not.

Signals also have three audiences that are not the automated driver — a
signal head on the layout, the panel, and a person driving by eye — so the
aspects are published a second time, as one last-value state topic carrying
the aspect of every signalled block end. One topic rather than one per end:
leaf names must be globally unique for the trace, and a late subscriber wants
the whole picture on connect rather than a first change. Same writer, same
truth, projected for its two audiences.

## The driver says how fast, the layout interface says how

`move` gains a speed: *take this train into that block at this speed*. The
throttle-up, watch-the-detector, stop loop stays private to the layout
interface, where the locomotive's braking curve, the decoder's speed steps and
the detector's position already live and where they differ between a simulator
and a physical railroad.

That keeps the driver a pure function of the aspect it is handed —
stateless, layout-blind and hardware-blind — which is the footprint
[SYSTEM.md](../SYSTEM.md#driver) already claims for it and the reason a human
driver drops in behind the same boundary.
