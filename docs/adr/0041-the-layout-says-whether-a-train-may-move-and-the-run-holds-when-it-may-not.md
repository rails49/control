# The layout says whether a train may move, and the run holds when it may not

Track power has a topic of its own, `tc49/layout/state/power`, retained and
written by the layout interface — one writing role, like every other topic
([ADR-0035](0035-a-topic-has-one-writing-role.md)). Three values: `on`,
`stopped` and `off`. The dispatcher reads it, and anything but `on` holds the
run ([ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).

**Amended for
[#242](https://github.com/rails49/control/issues/242):** a field whose values
are a closed set is an **enum**; this ADR calls it a *word*, the term
`CONTEXT.md` used until #242. Nothing below has been rewritten, so read *word*
as *enum* throughout.

Before this, track power was invisible to the software, and that was not
neutral. Cut power one boundary after a grant and the train stops between
blocks. No sensor fires, so the outstanding move never clears and the block
and the transit stay locked; that train is never granted anything again, and
every train waiting on those resources waits with it. Meanwhile the dispatcher
goes on granting to *other* trains, the driver goes on publishing `move` at
dead rails, and `state/aspects` goes on showing `clear` over track with no
volts in it — the lie ADR-0037 refuses to tell for a held run, arriving by
another route. Restarting the process was the only cure, and a power cut that
never took the apps down never reached it.

## The layout reports power; it does not yet take a command

A command station has both controls, and they are different things. **Power
off** removes the track supply: nothing moves, and the accessory decoders lose
it too, so no point position can be trusted afterwards. **Emergency stop**
broadcasts stop to every locomotive with the track still live: the locos
stand, points hold their positions and decoders keep their state.

Both are events the hardware raises, and both are observations before they are
anything else. The layout interface is *commands in, observations out*
([SYSTEM.md](../SYSTEM.md#layout-interface)), and its outbound vocabulary is
what hardware can implement — a booster's output state is about as
implementable as an observation gets.

The command half stays parked. Today the operator's ON is a physical action,
there is no booster interface to write against, and an emergency stop worth
the name is a hardwired contact rather than a message. What changes here is
that the app can be *told*, which is all the dispatcher needs to stop lying.

It is stated from the binding's constructor, always, so a joining client is
served the word rather than left to read one out of an absence
([ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md)).

## One topic, one axis

The question is "may a train move", and the values name why not.

Two topics would make every consumer combine them and decide what
powered-off-and-emergency-stopped means. One state topic has one writing role
and one retained value a joining client is served — the same argument ADR-0037
makes for `run` carrying a word rather than a boolean.

`stopped` and `off` **differ for the operator, not for the dispatcher**, which
branches only on "not `on`". They are kept apart because the person recovering
takes a different action for each — clear the emergency stop, or switch the
supply back on — and because the panel has to say which. The value is
`stopped` and not `stop` so that it does not collide with the aspect of that
name, which is a different thing on a different topic.

## Power leaving `on` holds the run; power returning does not release it

Holding is the whole of what the dispatcher does with the word, and it takes
the path a person's HOLD takes: nothing more is committed, and every signalled
end shows `stop`.

Returning to `on` changes nothing. That is @iot49's bar — an explicit GO
before anything moves — and it is the same guarantee the hardware gives at
power-up by coming back idle, held now in the app for a cut that did not take
the process down.

**GO is refused while power is not `on`.** Releasing into dead rails would
choose routes, grant moves, publish `move`, and strand the next train exactly
as the cut stranded the first. The dispatcher drops such a `run_wanted` in
silence and to the trace, as it drops every gesture it cannot act on
([ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)),
and the panel greys the button. A **hold** is honoured whatever the power is
doing: it asks for less, and there is no state of the rails in which a person
may not ask for it.

## The dispatcher hears the whole layout role

Its filter widens from `tc49/layout/+` to `tc49/layout/#`. `+` matches one
level and would never see a topic under `layout/state/`, so this is required
rather than cosmetic, and it is still one prefix filter naming one role
(SYSTEM.md, rule 3).

## Consequences

**The simulator publishes `on` and never changes it.** Simulated track is
always live; a power cut is a physical act, and simulating one would be the
field or the branch that stays out of every app
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)). What
exercises the dispatcher's side of it is the topic, published by a test. A
live session gains the button when the command half lands.

A **cold session gains a line at boundary 0** and the pinned benchmark trace
regenerates with it.

**A stranded train is drawn correctly and cannot yet be resolved.** The
crossing mark is written at the grant and dropped on arrival, so a train
caught mid-transit is already in `crossing` and the panel draws it on the
connection. What it cannot do is get out: a placement is refused for a train
with a request in flight, and nothing cancels a request. This decision makes
that edge reachable in an ordinary session rather than only after a restore.
Named rather than solved.

*Solved since, under
[ADR-0049](0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md):* a
placement cancels the request in flight and releases what it held, so the
stranded train is placed where the person can see it is. Nothing else in this
decision changes.

**A stranded train's points may have moved under it.** After an `off` the
accessory decoders lost their supply too, so no point position can be trusted;
what the dispatcher last commanded is not what the steel is doing. Every grant
re-aligns, so the picture self-heals for any train that moves again, and the
train standing on a turnout that lost its supply is a physical hazard the
software does not model.

**Recovery is still recovery.** A cut that also takes the apps down is the
case ADR-0032 and the restored-session hold answer, and nothing here changes
it. This is the other half: the apps stayed up, and the word is how they find
out.
