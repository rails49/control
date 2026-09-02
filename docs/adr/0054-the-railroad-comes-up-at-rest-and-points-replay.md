# The railroad comes up at rest, and points replay

Resolves [#333](https://github.com/rails49/control/issues/333).
[ADR-0051](0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)
rules that the railroad comes up dark: `layout` starts having written
`wanted/track: off`, and a person turns it on. That covers the supply and not
the throttles, and with a durable bus the throttles are where the hazard went.

## The failure

`wanted/traction/<addr>` is a retained state topic, so a session run with
`--state` keeps it in the durable file. Nothing zeroed it. `DccEx.shutdown()`
sends its zeros to the **station** and publishes nothing, so the row still
said `{"speed": 0.5}` when the process ended; the next session's `DccEx`
subscribed to `wanted/#`, was handed the row on subscription, and sent it at
the first connect. The power-on that followed sent no zeros of its own —
`_act_track` guards those behind a latch that is false on a fresh object with
a fresh link — so the station had a speed for that locomotive and the rails
went live over it.

On real steel the locomotive rolls the instant the operator presses power-on.
No grant, no `move`, the run still **held**, and nothing on the bus that says
why. Held-by-default, which is the whole safety mechanism, never enters the
path: the row was written by the *previous* session's dispatcher, and
admission has nothing left to refuse.

`--state` with `--station` is allowed on purpose — it is the one combination
hardware improves, because the trains really are still standing where the last
session left them — so refusing the combination is not the answer.

## `layout` opens by wanting zero on every retained traction row

Beside the `wanted/track: off` it already writes, and for the same reason.
`layout` is the one writer of every desired row (SYSTEM.md, rule 1), so this
is its ruling to make and no other app's to undo, and the file the bus keeps
then records a railroad at rest rather than one holding a speed nobody asked
for.

The two alternatives were both narrower.

**A translator standing down** — `shutdown()` publishing its zeros on the bus
as well as sending them to the station — is the smallest change and holds only
where a process exits cleanly. A session killed at the wall leaves the row
exactly as it is today, which is the case that matters: an evening's running
ended by pulling the plug is the ordinary way a layout goes to bed.

**A fresh link arming the latch**, so the first power-on sends the zeros
whatever the bus holds, was argued for on the ground that it also catches a
station somebody left powered from outside this system. It does not: the zeros
go to `self._commanded`, which a translator fills from the desired rows it has
been handed, so a fresh object with no rows sends no zeros. It covers nothing
the ruling above does not, and it leaves the lie standing on the bus for
everything else to read.

Where the resting state of a restarted railroad is written is the whole
question, and the answer is: on the topic, by the app that owns it, at the
moment that app comes up.

## Points replay, and the asymmetry is not an oversight

`wanted/point/<addr>` is retained the same way and is **left alone**.

Traction has a resting value and a point has none. Zero is a real speed
meaning stopped, so "come up at rest" is a sentence that can be said about a
locomotive; there is no neutral position to write into a point row, and the
choice is between replaying the last session's belief and throwing every point
on the layout at startup. Throwing them all is worse — it is motion nobody
asked for on a railroad whose blades may have been moved by hand — and the
retained value is at least what the last session commanded.

So the route picture comes back and a turnout may be somewhere a person did
not leave it. That is startling rather than dangerous: the rails are dark
until somebody presses ON, and ADR-0051 already makes a person the backstop
for what the layout looks like when they do.

## Consequences

A restart no longer preserves a speed, and nothing wanted it to. The dispatcher
comes up held and re-issues what it grants, and a person's throttle is a hand
on a lever that a restart is not (the same argument `state/mode` already makes
by coming up empty).

`DccEx.shutdown()` is unchanged. Its zeros are about the **station's** memory —
a slot left holding a speed is a train that rolls when somebody powers the
rails from a throttle this system never sees — which is a different fact in a
different place from the desired row, and both are wanted.

A hand-edited state file with a speed in it is now zeroed on the way in rather
than obeyed. That is the intent: the file is a record of a railroad, and a
railroad at rest is what a session may safely assume it is coming back to.
