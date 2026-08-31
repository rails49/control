# Two blocks ahead is full speed

**Corrected in part by
[ADR-0029](0029-a-lock-held-ahead-is-a-block-the-check-must-see.md).** The
conclusion below stands — target two blocks ahead, never a third — and 0029 is
where it is built. What does not stand is "The safety core does not change":
the check had to learn what a train holds ahead of where it stands, because
until then it could not see a lock it had not been told about. 0029 also
records what depth two costs, measured.

Incremental locking targets **two blocks ahead** and never asks for a third.
One block ahead is enough to move, at the reduced speed the `caution` aspect
commands ([ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md));
two is what buys full speed.

The reason is braking. A train cannot stop in the length of a signal, so a
driver told only that the next block is free must run slow enough to stop at
the far end of it. Given the block after that as well, it can run through the
first at speed and find out about the third on the way. This is why the
lookahead is a number at all rather than simply "the next resource".

## The safety core does not change

Locking the second block ahead is an **ordinary grant**, made earlier than the
train needs it. The route-aware banker's check of
[ADR-0003](0003-route-aware-bankers-safety-check.md) takes a state and answers
whether it is safe; it has no notion of depth, and a safe state reached by one
more granted lock is still safe. So depth is a property of the strategy asking,
not of the layer answering.

That puts it at the seam [ADR-0005](0005-seam-at-locking-strategy.md) already
drew: depth is a parameter of `Incremental`, and the `FullRoute` baseline is
the same idea at unbounded depth.

## Never deeper than two

Grabbing a third block when the check happens to pass was rejected. No aspect
distinguishes depth three from depth two, so it buys no speed; it costs a
safety check per extra grant; and it holds track speculatively that another
train may be waiting for. The claim that spare track can be taken "without
throughput penalty" is only true when nobody else wants it, which is exactly
what the dispatcher cannot cheaply know.

Depth varying per train — an express looking further than a shunting move —
was rejected for the same reason request priorities were: it adds request-level
policy to a benchmark that wants one variable, and the upgrade path stays open
through the same parameter.

## Braking distance is an open subject

Something has to make `caution` honest. The working answer is that the
caution speed is a per-locomotive calibration behind the layout interface,
where the braking curve already lives, together with a constraint on the
railroad rather than on the software: **a block is at least a braking distance
long at caution speed**. The driver is layout-blind and cannot know a block's
length; the dispatcher has the lengths but no locomotive, and giving it braking
models would make it a physics engine.

This is recorded as the working answer and not as a settled one. It is a large
subject with several known solutions — speed signalling that puts a limit in
the aspect among them — and which is implemented will be decided once there is
running experience to decide it with.
