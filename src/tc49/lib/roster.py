"""The stock documents: the models a catalogue holds, and the cars and trains
a railroad owns.

A **model** is what a product is — a length, a **kind**, and what each DCC
function does on it — and it is a fact about the product rather than about any
railroad, so two railroads owning the same item read one entry (CONTEXT.md,
**Model**). A **car** is one item a railroad owns: that model with zero or
more fields overridden, plus its own address where it has a decoder. A
**train** is an ordered list of cars, each recording which way round it is
coupled, and its length and its kind are derived from them
([ADR-0045](../../../docs/adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).

A railroad's roster is the cars it owns, with the trains made up from them
alongside (CONTEXT.md, **Roster**). Being on it is what makes stock **known**,
which is separate from a train being **placed** — a railroad at rest says what
stock it has without saying where any of it stands
([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)).

The types live here beside :mod:`tc49.lib.scenario` for the same reason that
one does: they are the shared vocabulary every app reads, and the store owns
the binding and the validator that produce them.

Nothing here is live state and nothing commands a function: a model records
what a function *means*, and what puts one on the bus is the device
vocabulary's, if anything ever does (ADR-0045).
"""

from dataclasses import dataclass, field

LOCOMOTIVE = "locomotive"
KINDS = (LOCOMOTIVE, "passenger", "freight", "special")
"""What a model may be. A train's kind is derived and is not one of these
(CONTEXT.md, **Kind**): the two lists differ."""

MIXED = "mixed"
LIGHT_ENGINE = "light engine"

FORWARD = "forward"
REVERSE = "reverse"
ORIENTATIONS = (FORWARD, REVERSE)

OFF_ON = ("off", "on")
"""What a function is in where the model states no values: a plain switch,
off to begin with."""


@dataclass(frozen=True)
class Function:
    """What one DCC function number does on a product.

    `values` is what the function can be in, **first entry first**: that is
    the one it is in when nothing has been commanded, which is why the list
    is ordered rather than a set.
    """

    name: str
    values: tuple[str, ...] = OFF_ON


@dataclass(frozen=True)
class Model:
    """What a product is, independent of any railroad that owns one.

    Shared between railroads, which is why it is keyed by its own name and
    not by the railroad's (CONTEXT.md, **Catalogue**).
    """

    name: str
    kind: str
    length: int
    functions: dict[str, Function] = field(default_factory=dict[str, Function])


@dataclass(frozen=True)
class Car:
    """One item a railroad owns: its **model with fields overridden**.

    The merged result, so a car is complete however it was written and one
    rule reads it — the model's every field, with anything the car said
    instead. `model` is kept because it is what the car *is*, and a car
    always names one.

    `addr` is the number programmed into its decoder, **bare** — no system
    prefix, unlike a point's (ADR-0045) — and absent where the car has no
    decoder.
    """

    model: str
    kind: str
    length: int
    functions: dict[str, Function] = field(default_factory=dict[str, Function])
    addr: str | None = None


@dataclass(frozen=True)
class Coupled:
    """A car's place in a train: which car, and which way round it is coupled.

    `reverse` says the car's nose points toward the tail, which is what makes
    a top-and-tail set a reversed locomotive at the end (CONTEXT.md,
    **Orientation**).
    """

    car: Car
    orientation: str = FORWARD


@dataclass(frozen=True)
class Train:
    """A train the railroad has made up: an ordered list of cars, head first.

    Its length and its kind are **derived, never authored** — a length is one
    fact and the roster's whole job is that it stays one. `stated_length` is
    the one exception and it is the migration's: a roster written before
    [#223](https://github.com/rails49/control/issues/223) states a train's
    length and names no cars, and one still loads. No committed roster is
    written that way any more, #223 having rewritten the five into cars; the
    exception is what a person's own older file gets. A train may say one or
    the other and never both.
    """

    cars: tuple[Coupled, ...] = ()
    priority: int | None = None
    stated_length: int | None = None

    @property
    def length(self) -> int:
        """The sum of the train's cars, which is the whole of what the
        dispatcher's fit check reads a roster for."""
        if self.cars:
            return sum(coupled.car.length for coupled in self.cars)
        if self.stated_length is None:
            raise ValueError("train has neither cars nor a stated length")
        return self.stated_length

    @property
    def kind(self) -> str | None:
        """What the train is, from **the cars it hauls, ignoring
        locomotives**: every hauled train has one, so counting them would
        make every train *mixed* and the classification would say nothing.
        Exactly one sort hauled gives that sort, more than one gives `mixed`,
        and nothing but locomotives is a `light engine` (CONTEXT.md,
        **Kind**).

        A train that names no cars has no kind to derive, which is what a
        roster written the pre-#223 way says about every one of its trains.
        """
        if not self.cars:
            return None
        hauled = {
            coupled.car.kind for coupled in self.cars if coupled.car.kind != LOCOMOTIVE
        }
        if not hauled:
            return LIGHT_ENGINE
        return hauled.pop() if len(hauled) == 1 else MIXED

    @property
    def functions(self) -> tuple[Function, ...]:
        """What a person driving this train can switch: the functions its cars
        declare, **by name**, first car first and each name once.

        In the train's frame like everything else a throttle works in
        (CONTEXT.md, **Throttle**): a set with a locomotive at each end has one
        headlight to press, not two, and which car — which address, which
        orientation — a press reaches is `layout`'s, the same composition it
        does for a speed. So the name is the whole of the key, and the first
        car declaring one settles what its values are.

        No number: which DCC function a name sits on is what a model records
        for the translator to use, and it is a decoder detail no view shows
        (ADR-0045).
        """
        by_name: dict[str, Function] = {}
        for coupled in self.cars:
            for function in coupled.car.functions.values():
                by_name.setdefault(function.name, function)
        return tuple(by_name.values())

    @property
    def priority_key(self) -> tuple[int, int]:
        """Where the train sorts against another: lowest number highest, and
        **a train with no priority after every train that has one**
        (CONTEXT.md, **Priority**).

        Absent is not a number and is not written as one, so it cannot be
        confused with a number a document authored. Two trains at one
        priority compare equal and the caller's own order stands.
        """
        return (1, 0) if self.priority is None else (0, self.priority)


@dataclass(frozen=True)
class Roster:
    """A railroad's stock: the **cars** it owns, and the trains made up from
    them.

    Owned by the railroad rather than by a run, so one roster serves every
    scenario over that railroad — which is what makes a train's length one
    fact rather than one per scenario. A scenario says where a train starts;
    how long it is, is here.

    `trains` comes first because it is what milestone 1 reads and every
    caller already passes it positionally; the cars a train is made of are
    resolved at load, so a train answers for its own length without the
    roster in hand.
    """

    railroad: str
    trains: dict[str, Train]
    cars: dict[str, Car] = field(default_factory=dict[str, Car])

    def lengths(self) -> dict[str, int]:
        """Train to length, which is the whole of what the dispatcher's fit
        check and its `unknown_train` answer read a roster for."""
        return {name: train.length for name, train in self.trains.items()}
