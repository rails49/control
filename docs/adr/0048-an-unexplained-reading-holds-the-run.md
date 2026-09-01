# An unexplained reading holds the run

Resolves the question [SYSTEM.md](../SYSTEM.md)'s layout-interface footprint
left open and [#260](https://github.com/rails49/control/issues/260) closes:
what a **running** dispatcher does with a detector reading that no granted
move accounts for.

**It holds the run**, by the path track power already takes, and the block or
the train the reading contradicts is named on `tc49/dispatch/state/disputed`
for a person to walk. Nothing is guessed, nothing is placed, and nothing
raises.

## What an unexplained reading is

The layout interface reports `block_occupied` and `block_vacated`
anonymously — a block detector cannot name a train
([DISPATCH.md](../dispatcher/DISPATCH.md), *sensors are anonymous*) — and the
dispatcher recovers the identity from its own lock table: the block's holder,
and the move that holder has outstanding. Some readings that table does not
explain:

- a hand puts a locomotive on a detected block, which is how stock joins an
  evening and how every session starts
  ([ADR-0039](0039-a-train-may-be-off-the-layout.md));
- a train is pushed, or rolls, while the supply is off;
- a coupling breaks and a cut of cars stands in a block nothing granted;
- a detector asserts on its own — dirt, a wiping wheel, a damp rail.

They differ for the person recovering and not for the dispatcher, exactly as
`stopped` and `off` do
([ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
All of them say one thing: the lock table has stopped being a description of
the steel.

## It may not raise

Milestone 1 raised on one while running, and said so openly rather than
pretending the case did not exist. It cannot stand. The bus does not
authenticate a publisher, so a consumer validates every payload it reads and
**never raises on one** (SYSTEM.md, rule 4;
[ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).
The exception was not thrown by the read — the frame is well formed, and
`{"block": "up_w"}` is exactly what the contract asks for — but it comes out
of the same handler and takes the app down from the bus just as certainly. On
a layout that detects occupancy the thing that throws it is a hand.

## It may not be dropped either

The other cheap answer is to ignore the reading. The dispatcher's safety
argument runs over its own picture: `safe()` asks whether the lock table plus
one more grant can still be drained
([SAFETY.md](../dispatcher/SAFETY.md)), and a block that reads occupied with
nothing claiming it is a block the check believes is free. Granting it to
another train is a collision the dispatcher would call safe. Ignoring the
reading is choosing the picture over the railroad, and
[ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md) ranks
them the other way round.

Nor can the dispatcher place the stray itself. Occupancy is anonymous, so it
has no train to place and nothing to place it from — the same reason the
dispute check resolves nothing
([#153](https://github.com/rails49/control/issues/153)).

## The hold, and the person

Whatever says trains may not move holds the run (ADR-0041). This is the layout
saying the dispatcher no longer knows where they are, which is the same
sentence one layer up. Every consequence is already defined:

- nothing new commits — no route chosen, no move granted, no lock taken
  ([ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md));
- every signalled end shows `stop`, rather than standing `clear` over a
  railroad whose state the dispatcher cannot account for;
- an outstanding move still runs to its sensors: a brake, not an emergency
  stop, and nothing on the bus retracts a `move` already sent;
- the **dispute check** turns on, and it is this comparison exactly — a block
  reading occupied with nothing claiming it, a train whose block reads clear —
  so the reading that held the run is what the panel points a person at (#153);
- the person walks the railroad, ends each entry with a `placement_wanted`,
  and presses GO. A block reading clear again releases nothing, just as power
  returning releases nothing: the bar is an explicit GO by somebody who has
  looked.

Nothing new on the bus: no topic, no field, no state. The hold is the run's
own mechanism, and an unexplained reading is one more reason to reach for it.

While the run is already **held** nothing changes at all. The reading was the
dispute check's business before this decision and still is, and holding a held
run is a no-op.

## What it costs

One false detector reading stops the railroad until somebody presses GO. That
is the fail-safe direction, and the other one grants moves over track the
dispatcher cannot account for. A batch run that produced an unexplained
reading now ends early and quiet where it used to end in a traceback: the
trace carries the reading, `state/run` going `held` behind it, and the
disputed set naming the block, which reads better than a stack.

## What it rules on

- **Closes** the open question in SYSTEM.md's layout-interface footprint. The
  assumption that every sensor event explains a granted move is no longer
  assumed: it is checked, and the run holds where it fails.
- **ADR-0041 stands**, with a second thing that holds the run beside track
  power. Power says a train may not move; an unexplained reading says the
  dispatcher does not know where the trains are.
- **ADR-0034 stands as written**, and this is the last place in the dispatcher
  where an event off the bus could raise.
- **ADR-0030 stands.** The milestone-1 simulator publishes sensors only for
  the moves it executes, so nothing behind the interface changes; this rule is
  written for the layout that detects occupancy, which is the binding that
  decides.
- **#153 stands** and gains its second moment: the dispute check was built for
  the held run a session comes up in, and now also names what held a running
  one.
