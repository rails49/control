# The catalogue

The models an installation knows: what a product *is*, independent of any
railroad that owns one (CONTEXT.md, **Catalogue**). One file per model, named
for itself — the file's `model:` and its path must agree, because the name is
the key every car refers to it by.

## Length is over buffers

`length` is millimetres of actual model track, measured **over buffers** on
the item in front of you, not taken from the manufacturer's sheet.

Over buffers because that is what occupies the block. A body length is
shorter, and a clearance check made against it is optimistic in the one
direction that puts two trains in the same place. Measured because a sheet
states a design and a decoder-fitted item with a coupler on each end is what
actually runs.

Scale never enters the arithmetic: a length is millimetres of real track
whether the product is N or H0, and the block lengths it is checked against
are measured the same way.

## Naming a real product

`<manufacturer>-<product>`, e.g. `conrad-e10`. The prototype alone will not
do: several manufacturers make the same one, with different decoders and so
different function maps, and what a catalogue entry holds is a fact about the
item in the box. The article number is better than the prototype where it is
known; `manufacturer` is also its own field, and the name still carries it
because the name is the unique key and article numbers repeat across makers.

## The synthetic models

`bench-<length>` is a stand-in nobody owns, carrying a length and a kind and
no functions. They are the library railroads' stock, and their lengths are
pinned so no benchmark result moves
([#223](https://github.com/rails49/control/issues/223)).

The real entries beside them are on loan. An installation's own documents do
not belong in this repository and move out under
[#318](https://github.com/rails49/control/issues/318); this page and the
conventions on it stay.
