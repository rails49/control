# Transit conflicts are declared by inversion

A connection lists which pairs of its transits are `concurrent`; every pair not
listed conflicts. The natural-reading alternative — list the pairs that
*conflict* — was rejected on the direction of its failure mode.

Layouts are hand-authored by someone drawing a railroad, so a forgotten line is
the expected error, not the exceptional one. Under inversion a forgotten line
means two transits that could have run together are serialised: the layout
costs throughput and stays safe. Under the direct form a forgotten line means
two conflicting transits are believed compatible, and the dispatcher grants
both — a collision the safety check cannot catch, because conflicts are
enforced as instantaneous admissibility at the grant rather than by `safe()`
(see [SAFETY.md](../dispatcher/SAFETY.md)).

It also matches the shape of real track. Ladders and plain turnouts are fully
exclusive and now declare nothing; only genuine crossings say anything at all.
The Gotthard encoding declared no `concurrent` pairs whatsoever
([layouts/gotthard.drawing.yaml](../../layouts/gotthard.drawing.yaml)), which was
certainly too strict for a station that size — and is exactly the kind of thing
that should cost measured throughput until the real turnout geometry is
entered, rather than being assumed permissive. It did cost it, and #46 recovered
it: drawing Airolo and Claro west composed 37 pairs and cut the
`gotthard/saturation` makespan. Claro east, still undrawn, is still exclusive.
