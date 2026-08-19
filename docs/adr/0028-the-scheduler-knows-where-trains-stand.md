# The scheduler knows where trains stand

The scheduler reads the layout from the store and tracks where each train is
by subscribing to `tc49/dispatch/#`. It stops being layout-blind.

It has to, to do the job [GOALS.md](../GOALS.md) gives it: deciding which train
departs from where, to where, and when, with requests arriving continually. A
generator that knows none of that cannot pick a train that is idle or a
destination that is reachable, so most of what it invents comes back
`wrong_origin` and a train parked in a yard is never chosen because nothing
steers toward what is possible.

The knowledge is cheap. `move_granted` already carries `(train, into)`, the
scenario seeds initial placement, and `request_completed` says when a train is
idle again — so position falls out of events the scheduler can already see.

## Knowing is not judging

**The dispatcher remains the single feasibility authority.** The scheduler
knows enough to propose sensibly; it checks nothing. Fit, entry, reachability
and departure-end consistency are settled at admission as before, and a
proposal the scheduler thought reasonable is still answered `request_rejected`
([ADR-0021](0021-a-bad-request-is-answered-not-raised.md)). Those are different
things, and only the second was ever the reason the scheduler was kept thin.

What is given up is the "layout-blind and tick-only" footprint, which bought a
scheduler with no reason to drift from the dispatcher. The mitigation is that
the scheduler's picture is advisory: nothing is unsafe if it is stale, because
nothing acts on it except the choice of what to ask for.

## One writer, three sources

A timetable released at its due times, a generator inventing traffic, and a
person clicking on the panel are three sources inside one scheduler, not three
publishers. [ADR-0016](0016-the-panel-is-a-scheduler.md) already settled that
and named this case: "the panel-scheduler can preload a scenario and also take
clicks, giving timetable-plus-ad-hoc while still being one writer". A generator
joins them on the same terms, which keeps the single-writer rule and one
deterministic minter of request ids.

Generating scenario files offline instead was rejected: it keeps replay free
but the arrivals are then neither continual nor able to respond to how the run
is actually going.
