# Transit conflicts are declared by inversion

*(Amended for #161: the drawing cited below is now
[bench/layouts/gotthard-v0.drawing.yaml](../../bench/layouts/gotthard-v0.drawing.yaml).
The railroad on the bench splits Claro track 3 and separates the west throat,
so `gotthard` derives 15 blocks and 33 concurrent pairs where this page counts
14 and 37. The inversion argument does not depend on either count, and the
measurements were taken on the frozen file. Nothing here is re-measured.)*

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
([bench/layouts/gotthard-v0.drawing.yaml](../../bench/layouts/gotthard-v0.drawing.yaml)), which was
certainly too strict for a station that size — and is exactly the kind of thing
that should cost measured throughput until the real turnout geometry is
entered, rather than being assumed permissive. It did cost it, and #46 recovered
it: drawing Airolo and Claro west composed 37 pairs and cut the
`gotthard/saturation` makespan. Drawing Claro east (#58) then found it was two
throats rather than one, so its five transits stopped conflicting across the
two lines without a pair being declared anywhere.
