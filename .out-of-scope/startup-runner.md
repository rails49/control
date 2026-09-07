# A shared startup runner in `lib`

`lib/startup.py` will keep stating the coming-up order in prose and will not
gain a function that runs it. The six `__main__` modules go on writing their
own `serve()` bodies.

## Why this is out of scope

The order `startup.py` states is three steps — the documents, the broker, the
rows this app already owns — and `lib` already holds every piece of it that is
genuinely shared: `connected()`, `retained()`, `command_line()`, and the four
timing constants. What is left in an app's `serve()` is the outer railroad
loop and an inner loop, about ten lines, and the apps disagree about them on
four axes:

- **Where the retained wait goes, and what it names.** `scheduler` and
  `dispatcher` name a row and come back the instant it lands. `layout` and
  `dccex` have nothing to name — their rows are keyed by address and no app
  holds a list of which addresses a railroad has — so each waits its window
  out whole, in a `_retained` of its own. `simulator` waits for nothing, having
  no previous process's rows to adopt. `driver` owns no row at all.
- **Where `follow` sits relative to the build.** The five apps that follow the
  retained state row subscribe *after* they are built, because a gesture
  published in the instant between an app's opening rows and its own handlers
  is lost. `layout` subscribes *first*, because what it watches is a gesture
  and an event is not retained, so a press landing before the subscription is
  simply gone. Both orderings are argued at length where they are, and they
  are opposites.
- **What the inner loop body is.** A drain and a sleep for `scheduler`,
  `dispatcher` and `driver`; a clock advance and a settle as well for
  `layout`; `simulator.run_live` for `simulator`, which cuts a turn short to
  the next scheduled event; an asyncio task beside the drain for `dccex`.
- **What the teardown is.** `dropped(bus, OWNED, …)` for four of them,
  `bus.forget()` for `driver`, which owns no retained row, and nothing for
  `dccex`, which is bound to no railroad.

A function taking four behavioural parameters to share ten lines is not a
reduction. Worse, each of those four axes is a decision that ADR-0030,
ADR-0050, ADR-0059 or ADR-0060 reached, stated today in the app the decision
is about. Folding them into `lib` turns each into a flag, and the argument for
the flag has to be written somewhere no app can hold it.

That is the failure mode #440's audit named when `lib/startup.py` acquired
three lines listing which app reads no documents: "a seventh place to keep in
sync — the exact failure mode the issue exists to remove." A runner would be
that at full size.

The repetition this leaves is genuinely small:

```python
# scheduler, dispatcher, driver — three lines each
while not stop.is_set() and not loaded.moved:
    bus.drain()
    stop.wait(period_s)
```

## What is not out of scope

Duplication in an app's `__main__` that carries no such decision. The four
copies of the `_loading` helper — identical apart from a type annotation that
is not even a difference — are ordinary repetition and belong in `lib`. That
is #502, and closing this concept does not close that one.

Nor is the prose. `startup.py` stating the order once, and each app stating
only its own difference, is #440 and it stands.

## Prior requests

- #491: "lib: startup states the coming-up order and no code runs it"
  (architecture review, 2026-09-07, severity 2 of 5)
