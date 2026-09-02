# The bench's fixtures

What the benchmark suite is run *on*: the drawn railroads and the stock they
own under `layouts/`, the models an installation knows under `catalogue/`, and
the placements and request lists under `scenarios/`. The asset store is rooted
here in a checkout, so the paths under this directory are the ones
[LAYOUT.md](../docs/store/LAYOUT.md) describes.

These are the harness's inputs and nobody's railroad. They sit under `bench/`
rather than beside `src/` for that reason: a `layouts/` at the top level reads
as the place an installation puts its own drawings, and the top level is the
system's rather than the harness's
([#319](https://github.com/rails49/control/issues/319)). Where an
installation's own documents live is
[#318](https://github.com/rails49/control/issues/318) and is not settled here.

A fixture is frozen once it is committed. Every number in
[BENCHMARKS.md](../docs/bench/BENCHMARKS.md) is a number over one of these
files, so a fixture that tracked a changing railroad would make a comparison
across six months measure the railroad rather than the dispatcher.
