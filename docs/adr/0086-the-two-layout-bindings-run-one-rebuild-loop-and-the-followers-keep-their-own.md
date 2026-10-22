# The two layout bindings run one rebuild loop and the followers keep their own

Part of [#912](https://github.com/rails49/control/issues/912). Narrows
[#491](https://github.com/rails49/control/issues/491).

`layout` and `simulator` are the two layout bindings. Each one's `serve`
does the same steps in the same order:

1. Read the railroad the store records, or stand where it has none.
2. Follow `tc49/layout/railroad_wanted` before building.
3. Record the railroad and build on it.
4. Run until another railroad is named.
5. On a drawing that is not a valid drawing, name the railroad with
   `built: false` and keep running.
6. Under the same name, keep the trains whose blocks remain (ADR-0071).
7. Clear the rows it owns.

What differs is what each reads, how each builds, its inner loop, and the
rows it owns. Since ADR-0070 both answer the pick under the same rule.

From 2026-09-22 to 2026-10-21, seven commits made the same behavioural
change to both bodies (#564, #727, #730, #731, #742, #883, #889). The
simulator's paths for a railroad named and not built had no test.

#491 refused a runner shared by every app. Among the four apps it compared,
four things differ: where `follow` sits relative to the build, the
retained-row wait, the inner loop, and the teardown. That refusal stands for
the scheduler, the dispatcher and the driver.

## Decision

1. **`lib/loading.py` runs the rebuild loop for whichever layout binding is
   running**, from the store's record to clearing the owned rows.
2. **A layout binding hands the loop a `LayoutBinding`**. It says how to
   read a railroad, what to run on when the drawing is not valid, the
   `Layout` in what it read, how to build and run an app, and which rows it
   owns. Anything only one binding does, such as `layout`'s wait for the
   traction rows (#333), happens inside its own build.
3. **The followers keep their own `serve`.** A follower follows the row
   after it is built and waits for different retained rows.

## Consequences

- A change to how a layout binding answers a pick is made once and tested
  once, on the in-process bus.
- A step only one binding needs goes in that binding's build. A step both
  need goes in the loop.
- `layout/__main__.py` and `simulator/__main__.py` keep the broker wait,
  their constructor, their inner loop, `OWNED` and their log prefix.

## Considered

- **One runner for every app** (#491). The followers differ from the
  bindings on the four points above.
- **Share only the step after a railroad is named.** Both loops would still
  be written out twice.
