# What a JMRI or Rocrail roster file holds

Resolves [#222](https://github.com/rails49/control/issues/222). Reads JMRI's
roster and Rocrail's plan file against the three-level stock model settled in
[#199](https://github.com/rails49/control/issues/199) — a **model** (what a
product is), a **car** (a model with fields overridden, plus its own bare DCC
address) and a **train** (an ordered list of cars, each recording which way
round it is coupled) — and against the fields that model needs: length, kind,
address, function meanings, train composition, orientation and priority
([CONTEXT.md](../../CONTEXT.md#stock),
[ADR-0045](../adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
The prior stands: **we define our own shape and import.** The point is two
worked examples, not a format to adopt.

This is about the **roster**, not the protocol. The JSON servlet's envelope,
session, subscription rules and throttle semantics are
[docs/research/jmri.md](https://github.com/rails49/control/blob/research/jmri/docs/research/jmri.md)
(#196); §5 below only says which roster *content* travels over it.

Sources are pinned:

- `JMRI/JMRI@23604e8` (master, 2026-08-26) — the same commit #196 was read at.
  Every `path` below is into that commit. `www.jmri.org` sits behind a bot
  challenge, so help pages were read from `help/en/...` in the repository,
  which is what the site serves.
- The Rocrail wiki, `wiki.rocrail.net`, read 2026-08-28. Its pages render
  Lorem ipsum without JavaScript, so each was fetched with `&do=export_xhtml`.
  The instance titles itself *"Innovative Model Railroad Control System
  (Backup)"* — it is the wiki the project links, on a backup host.
- `TomTheGeek/Rocrail@c7fd684` — `rocrail/public/wrapper.xml`, Rocrail's own
  declaration of every plan-file object, attribute, default and unit. **This
  is a mirror and it is stale (2014-12-07).** The upstream
  `github.com/rocrail/Rocrail` answers *"Git Repository is empty"*, and every
  GitHub copy found dates from 2014–2015. Attribute names taken from it are
  marked, and each is cross-checked against a current wiki page where one
  documents the same field; newer attributes will be missing from it.

Each claim is tagged: **[fact]** is stated in or read off a source;
**[inference]** is this document's reading of it.

## 1. Where JMRI's roster lives

[fact] Two levels of file, holding the same data twice. `Roster.java`'s own
javadoc: *"The roster is stored in a 'Roster Index', which can be read or
written. Each individual entry (once stored) contains a filename which can be
used to retrieve the locomotive information for that roster entry. Note that
the RosterEntry information is duplicated in both the Roster (stored in the
roster.xml file) and in the specific file for the entry."*

| | Where | Schema |
| --- | --- | --- |
| Roster index | `roster.xml` (`Roster.DEFAULT_ROSTER_INDEX`) in the Roster Files Location, which defaults to the profile's user-files path (`Roster.rosterLocation = FileUtil.getUserFilesPath()`) | `xml/schema/roster.xsd` |
| One file per entry | the `roster/` subdirectory of that location (`Roster.getRosterFilesLocation()` = roster location + `roster` + separator); the entry's `fileName` attribute names it | `xml/schema/locomotive-config.xsd` |
| Consists | `roster/consist/consist.xml` (`ConsistFile.getFileLocation()`, `defaultConsistFilename()`) | `xml/DTD/consist-roster-config.dtd` |

[fact] The help page's data table agrees: roster entry info lives in
*"Individual files in subdirectory 'roster' in Roster Files Location"* and
roster groups in *"roster.xml Roster Files Location"*
(`help/en/html/apps/DataManagement.shtml`).

[fact] `roster.xsd`: `<roster-config>` contains one or more `<roster>`, each
containing `<locomotive>` elements of type `LocomotiveType` — the same type the
per-entry file uses — plus optional `<rosterGroup><group>` elements. The
`<roster>` element takes an optional `filter` attribute, *"used by the
RosterServlet"*.

[inference] So an importer can read `roster.xml` alone, off disk, with no JMRI
process running, and get every entry. It is the per-entry files that carry
nothing extra of interest to us (§2 lists what they hold).

## 2. What a JMRI roster entry holds

[fact] `LocomotiveType` in `locomotive-config.xsd`, in full.

Attributes: `id` (**required**, the key), `fileName`, `dccAddress`
(*deprecated*), `roadName`, `roadNumber`, `mfg`, `model`, `owner`, `comment`,
`URL`, `groupName`, `imageFilePath`, `iconFilePath`, `IsShuntingOn`,
`maxSpeed` (*"maximum speed as a fraction from 0 to 1.0"*), `decoderModes`,
`manufacturerID`, `productID`, `developerID`, `locoDataEnabled`, and a physics
block — `physicsTractionType`, `physicsWeightKg`, `physicsPowerKw`,
`physicsTractiveEffortKn`, `physicsMaxSpeedKmh`,
`physicsMechanicalTransmission`.

Children, in order: `dateUpdated`; `decoder` (**required**, attributes
`family`, `model`, `decoderModes`, `comment`, `maxFnNum`, `programmingmode`);
`locoaddress` (`<dcclocoaddress number longaddress>` plus an optional
`<protocol>` from `dcc | dcc_long | dcc_short | selectrix | motorola | mfx |
m4`); `functionlabels`; `soundlabels`; `attributepairs`; `speedprofile`;
`values`.

[fact] `functionlabels` is a list of `<functionlabel num="…" lockable=""
visible="" functionImage="" functionImageSelected="">text</functionlabel>` —
the label is the element's text, keyed by function number, with `num` a
non-negative integer. `soundlabels` is the same shape without the icons.
`attributepairs` is an unbounded list of `<keyvaluepair><key/><value/></…>` —
free-form per-entry storage. `speedprofile` is forward/reverse over-run times
plus a `<speed step forward reverse>` table. `values` holds
`<decoderDef><varValue item value>` and `<CVvalue name value>` /
`<indexedCVvalue …>` — i.e. **the decoder's programmed values live in the
roster entry**, one entry per CV.

[fact] **What is not there.** The schema has no `length` of any kind
(`grep -ci length locomotive-config.xsd` → 0), no kind or category, no
priority, no train membership, and no orientation. `physicsWeightKg` and
`physicsMaxSpeedKmh` are prototype physics for simulation, not a scale
dimension.

[inference] The JMRI roster is a **decoder-programming record with a
locomotive's identity attached**, and the identity half is bibliographic —
road, number, manufacturer, owner, model, picture. Two of #199's seven fields
(address, function meanings) are first-class; the rest are absent. `roadName`
+ `roadNumber` + `mfg` + `model` are what a *model* would be named by, but
they are strings on each entry, deduplicated nowhere; two copies of the same
product are two unrelated entries. There is one place a length could be
smuggled — `attributepairs` — and it is a convention, not a field.

## 3. Decoder definition versus roster entry

[fact] A roster entry names its decoder by `<decoder family="…" model="…">`
and nothing more; the definition itself is one of the files under
`xml/decoders/`, to `xml/schema/decoder-4-15-2.xsd`. What the definition
contributes:

- **The CV variable model.** `<variables>` (required) defines every named
  variable, its CV, mask, type and default; the roster entry stores only
  values against those names (§2's `<values>`).
- **Default function labels.** `functionlabels` appears twice in the decoder
  schema — once on `FamilyType` and once on the `model` element — and is the
  same `functionlabelsType` (`num`, `visible`, `lockable`, internationalised
  `<text xml:lang>`).
- **How many functions exist.** The model's `maxFnNum`, default 28: *"This is
  the highest F key number that will appear in the Function Labels Pane and
  throttles… European standards now allow up to 68"*. `RosterEntry`'s javadoc
  says the same from the other side: *"The default value (28) can be
  overridden by a 'maxFnNum' attribute in the 'model' element of a decoder
  definition file."* Also `numFns`, `numOuts`, `show`, version-ID ranges, and
  a `suppressFunctionLabels` flag on the decoder element.

[fact] The merge rule is explicit in `RosterEntry.loadFunctions(Element, String
source)`, whose parameter is documented as *"'family' if source is the decoder
definition, or 'model' if source is the roster entry itself"*, and whose
javadoc says *"Does not change values that are already present!"*. The body
sets a label only `if ((this.getFunctionLabel(num) == null) ||
(source.equalsIgnoreCase("model")))`, and a `loadedOnce` guard exists *"so
that when the roster entry is edited only the first set of function labels are
displayed ie those saved in the roster file, rather than … being over-written
by the defaults linked to the decoder def"*.

[inference] This is exactly #199's override relation, one level down and for
one field: **the decoder definition is the shared product-level document, the
roster entry overrides it, and blank means inherit.** But its subject is the
*decoder*, not the *item*. It says what F4 does on this circuit board; it
cannot say how long the locomotive is or what kind it is, and two locomotives
with the same decoder share nothing else. JMRI has the mechanism #199 wants
and points it at a different noun.

## 4. Consists and trains — three answers, none of them a rake

**(a) `consist.xml` — a traction consist.** [fact]
`consist-roster-config.dtd`: `<consist-roster-config><roster><consist
id …><loco …/>+`. A `<consist>` carries `consistNumber`, `protocol`,
`longAddress`, `type` (`CSAC` command-station-assisted | `DAC`
decoder-assisted, default `DAC`), plus `roadName`, `roadNumber`, `model`,
`comment`. Each `<loco>` carries `dccLocoAddress` (**required**), `protocol`,
`longAddress`, `locoName` (`lead | rear | mid`, default `mid`),
`locoMidNumber`, `locoRosterId`, and **`locoDir` (`normal | reverse |
unknown`, default `normal`)**.

[fact] DecoderPro's help (`help/en/manual/DecoderPro/Main_ConsistControl.shtml`)
names the three kinds and their limits — a shared primary address; a CSAC
(Digitrax Universal, Lenz Double Header, NCE Old Style, EasyDCC Standard); and
a DAC using CV19, where *"If you add 128 to the consist address, the
locomotive will run backwards (relative to it's normal direction of travel) in
the consist"* and the consist address is limited to 1–127.

[inference] `locoDir` **is** per-member orientation, and `lead/mid/rear` +
`locoMidNumber` **is** an order — but the members are locomotives only, and
the file's purpose is to make several decoders answer one address. It is
#199's train shape applied to traction, and it stops at the tender.

**(b) OperationsPro — cars, engines, trains as a switching game.** [fact]
Three separate files, `OperationsCarRoster.xml`, `OperationsEngineRoster.xml`
and `OperationsTrainRoster.xml` (`CarManagerXml`, `EngineManagerXml`,
`TrainManagerXml`), to `operations-cars.dtd`, `operations-engines.dtd`,
`operations-trains.dtd`.

- `<car>` has `id`, `roadName`, `roadNumber`, `type`, `color`, **`length`**,
  `weight`, `weightTons`, `built`, `owner`, `load`, `kernel` + `leadKernel`,
  `blocking`, `rfid`, and the flags `passenger`, `caboose`, `fred`, `utility`,
  `hazardous`, `outOfService` — plus a large amount of live routing state
  (`location`, `destination`, `trainId`, `routeLocationId`, `rweDestId`, …).
- `<engine>` has the same spine plus `model`, `hp`, `consist`, `consistNum`,
  `leadConsist`, `bUnit`, **`length`** — and **no DCC address at all**.
- `<train>` is **not a list of cars.** It is a working: `route`/`routeId`,
  departure time, `numberEngines`, `engineModel`, `cabooseRoad`, `builtStart/
  EndYear`, and long allow/deny lists (`carTypes`, `carRoads`, `carLoads`,
  `carOwners`, leg-2/leg-3 helper options), plus build status. Membership runs
  the other way: the **car** carries `train`/`trainId`.

[fact] The two worlds are joined by guesswork. `Engine.getDccAddress()` is
documented as *"Get the DCC address for this engine from the JMRI roster. Does
4 attempts, 1st by road and number, 2nd by number, 3rd by dccAddress using the
engine's road number, 4th by id"*, and the code takes `list.get(0)` of each
`Roster.matchingList(...)` in turn.

[fact] The files do contain catalogue-shaped sections — `<types>`,
`<lengths>`, `<models>`, `<roads>`, `<owners>`, `<colors>`, `<kernels>` — but
each is a list of bare `name`/`value` strings, the pick-lists behind the
editor's combo boxes. They hold no per-product facts.

[inference] Operations has the **length** and the **kind** that the roster
lacks, and a car with an owner, but it is a paperwork simulation: no address,
no ordered rake, and a four-way string guess bridging to the roster. Taking
length and kind from here means importing a second, differently-keyed file and
inheriting that join.

**(c) Nothing else.** [inference] Between them, JMRI's three answers cover
*traction consist* (ordered, oriented, locomotives) and *switching-list train*
(unordered, un-oriented, cars) and never the thing #199 calls a train.

## 5. What of the roster reaches the wire

[fact] Two doors, both on the Web Server.

**The JSON protocol** (`java/src/jmri/server/json/roster/`) serves four types
— `roster` (a list of `rosterEntry` objects, optionally filtered to a group),
`rosterEntry`, `rosterGroup`, `rosterGroups` (`JsonRoster.java`). A
`rosterEntry` message (`rosterEntry-server.json`,
`JsonRosterHttpService.getRosterEntry`) is exactly:

`name` (the entry's `id`), `address`, `isLongAddress`, `road`, `number`,
`mfg`, `model`, `decoderModel`, `decoderFamily`, `maxSpeedPct`,
`shuntingFunction`, `owner`, `dateModified`, `comment`, `icon`, `image`,
`functionKeys[]`, `rosterGroups[]`, `attributes[]`.

`functionKeys` is emitted `for (int i = 0; i <= entry.getMaxFnNumAsInt(); i++)`
as `{name: "F<i>", label, lockable, icon, selectedIcon}` — so **the function
labels do travel**, up to the decoder definition's `maxFnNum`, though
`visible` does not. `attributes` is the `attributepairs` list.

[fact] What does not travel: the `<values>` CV block, the speed profile, the
sound labels, the physics attributes, and the address protocol. The servlet's
own source carries the TODO *"Include decoder defs and CVs in roster entry
response"* (`RosterServlet.java`).

[fact] `JsonRosterSocketService` registers listeners so roster and
roster-group changes are pushed to a connected socket afterwards, under the
subscription rules of #196.

**The Roster servlet** (`/roster`, `RosterServlet.java`,
`help/en/html/web/RosterServlet.shtml`) answers `/roster/`, `/roster/list`,
`/roster/list?filter=…`, `/roster/<ID>`, `/roster/entry/<ID>`,
`/roster/<ID>/image`, `/roster/<ID>/icon`, with `?format=xml` giving the
roster XML (and `/prefs/roster.xml` redirecting to it). It also accepts a POST
upload of a roster file.

[fact] Consists are reachable too, as type `consist`
(`consist-server.json`): `{address, isLongAddress, type (0 advanced, 1 command
station), id, sizeLimit, engines[{address, isLongAddress, forward,
position}]}`. That is the only place in the whole JSON protocol where a
per-member **orientation** (`forward`) and **order** (`position`) appear.
`JsonConsistHttpService` works against the live `ConsistManager` and calls
`new ConsistFile().writeFile(...)` on a change, so it is the running consist,
persisted.

[fact] Operations is reachable as types `car`, `engine`, `train`, `carType`,
`kernel`, `location`, `track`, `rollingStock`
(`java/src/jmri/server/json/operations/`). The JSON `train` carries
`length`, `weight`, `route`, and *"Sorted list of engines in train"* /
*"Sorted list of cars in train"* — an ordering the XML does not state, derived
at serve time; still no orientation.

[inference] For a seed, the JSON `rosterEntry` is enough for **address plus
function meanings plus identity**, over one HTTP GET of `/json/v5/roster`, and
reading `roster.xml` off disk gives the same thing without JMRI running.
Everything else #199 needs is in a different JMRI subsystem or nowhere.

## 6. Rocrail: one plan file holds the layout and the stock

[fact] Rocrail has no roster file. It has a **workspace** — a folder — and the
wiki is blunt about it: *"As a rule, there are no individual (plan) files in
Rocrail, but WORK AREAS (called workspace) to be opened (created and saved).
The main reason for this is that a Rocrail working environment not only
consists of the plan, but also the rocrail.ini with the essential definitions
for controllers, automatic operation, locomotive occupancy, etc."*
(`stepbystep-en`). The plan is `plan.xml`.

[fact, mirror] `wrapper.xml` declares `<plan>` as *"Root node of the
planfile"*, and `<lclist>`, `<carlist>`, `<operatorlist>` and `<waybilllist>`
are its children, siblings of the track, block, route and signal lists. **Stock
and layout are one document.**

### `<lc>` — a locomotive

[fact, mirror] `id` (required), `addr` *"Digital address. (0 == analog)"*,
`secaddr`, `iid` (interface id), `bus`, `prot` (`P` by server, `M` Märklin,
`N` DCC short, `L` DCC long, `A` analog, `C` car decoder, `S/X` Selectrix,
`F` MFX), `spcnt` speed steps; `len` — *"Total length of loc with wagons to
check with block length"* — and `nrcars`; the speed family `V_max`, `V_min`,
`V_mid`, `V_cru`, `V_mode` (`kmh` | `percent`) and reverse equivalents;
`dir` *"Direction; true is forwards"*; **`placing`** *"If loc is placed back to
front this should be set to false"*; **`priority`** *"train priority used for
multiplying the wait time if no destination is found"* (1–100, default 10);
`cargo` from `all, lightgoods, light, regional, person, goods, mixed, none,
ice, post, shunting, cleaning`; `class`; `commuter`; `engine` (`diesel |
electric | steam | automobile`); `era`; `roadname`, `number`, `desc`,
`catnr`, `value`; `dectype` *"Decoder type. (CV8)"*; `decfile` *"Decoder
definition file"* (default `nmra-rp922.xml`); `fncnt` and a list of
`<fundef>`.

[fact, wiki, `loc-gen-en`] The `len` rule is documented as a fork: *"If no
trains were assembled in Rocrail, then, the length of the entire train
(locomotive plus all cars) has to be entered. If trains were assembled, only
the length of the loco has to be specified here. The total length is then
automatically calculated when a train is assigned to the loco and results from
the length of the locomotive plus the sum of all car lengths."* The unit is
whatever the user chose, *"the same for all length definitions throughout
Rocrail"*.

[fact, wiki, `text-gen-en`, modified 3 months before reading] The current
documentation confirms the live fields: `%lcplacing%` — *"Loco placing:
'norm'/'swap'"*, `%lcdir%` — *"fwd"/"rev"*, `%lccargo%` — *"Loco or train
cargo(type)"*, `%lclen%` — *"Loco or train length"*, `%lcengine%`, `%lcclass%`.

### `<fundef>` — one function's meaning

[fact, mirror] `fn` (number), `text` *"function label"*, `timer`, `sound`
(file), `icon`, `on`, `onevent`/`onblockid` and `offevent`/`offblockid` from
`enter_block, exit_block, in_block, out_block`, `addr` *"Function decoder
address"*, `mappedfn` *"Mapped function number in case of other address then
main decoder"*. It hangs off both `<lc>` and `<car>`.

[fact, wiki, `loc-fun-en`, `car-fun-en`] F0–F32 per locomotive, each with a
Description (*"mandatory for saving a function definition; Without a
description all other settings are lost"*), a pushbutton/switch flag, a code
for icon selection, timer, events, sound, icon, address and `Fx` remap.

[inference] Rocrail's function meanings are **per owned item**, not per
product, and they are richer than a label: a function definition can fire
itself on a block event. Our model records the meaning only
([#199](https://github.com/rails49/control/issues/199): *"Functions are
recorded on the model and nothing commands one"*), which is the smaller half
of what Rocrail stores.

### `<car>` — a car, with its own decoder

[fact, mirror] `id` (required), `ident` (BiDi/RFID code), `number`,
`roadname`, `owner`, `color`, `era`, `image`, `remark`, `manuid`;
**`type`** (`freight | passenger`, default `freight`) and **`subtype`** from a
fixed list — `boxcar, gondola, flatcar, reefer, stockcar, tankcar, wellcar,
hopper, caboose, autorack, autocarrier, logdumpcar, coilcar` and `coach,
lounge, dome, express, dinner, sleeper, baggage, postoffice`; **`len`**
*"Car lenght"*, unit cm; `weight_empty` / `weight_loaded`; `V_max`;
`waybills`, `status` (`empty | loaded | maintenance`); `location` plus three
`prevlocation` slots; **`iid`, `bus`, `addr` *"Digital address"*, `prot`,
`protver`** with the decoder options `usedir`, `invdir`, `uselights`,
`f0vcmd`, `fnlights`; `decfile`; `<cvbyte>` values; **`placing`** (bool,
default true); `commuter`; and a list of `<fundef>`.

[fact, wiki, `car-int-en`] *"A car decoder can be controlled with function
actions. If the address > 0 the car will be also listed in the loco control
dialog."* The dialog's options are DirV (*"Send direction and velocity commands
from the operator/throttle to the function decoder"*), Invert (*"Invert the
direction before sending it"*), Logical Direction (*"Checked is default,
unchecked is swapped"*) and Lights.

[fact, wiki, `car-details-en`] Length is *"Scale length of the railroad car in
the same units as used for block and loco lengths"*, with a note that
standardised reference points (coupler centres) should be used *"to avoid the
addition of errors if many railroad cars are coupled"*. Also Radius (minimum
safe curve), wheel diameter, weight empty/loaded, Max. km/h (*"The lowest of
all train cars, greater then zero, will be used"*), Location (*"The block in
which the car actually resides"*, updated automatically by RFID/RailCom).

### `<operator>` — a train

[fact, mirror] The whole element: `id` (required), `lcid` (required — the
assigned locomotive), **`carids`** *"Comma separated car IDs"*, `cargo`,
`class`, `V_max`, `location`, and a `cmd` taking `addcar`, `removecar`,
`emptycar`, `loadcar`.

[fact, wiki, `operator-consist-en`] The Train tab's own words: the list *"contains
the train cars with the location of the train and if necessary with the
assigned freight bill and its destination"*; **Length** is *"Total accumulated
train length of all selected railroad cars. (Read only)"*, with a second field
for a train without cars; **Up/Down** *"Move a railroad car in the list up or
down"*; Add / Leave add and drop a car. Train type, class, roadname, home
location, max km/h, radius, max incline sit on the train, and *"no matter what
locomotive is assigned to a train — all train parameters will overrule the
corresponding locomotive parameters!"*

[fact, wiki, `operator-index-en`] Trains are created, copied, deleted,
imported and exported from the index; images render *"in the order of the car
list"*, with *"Swap train image"* and *"Swap loco image"* controlling which end
the locomotive is drawn at.

[inference] `<operator>` **is** #199's train: a durable, named, ordered list of
car ids with a locomotive attached, whose length is derived from its members
and whose type overrides the locomotive's. Two differences matter. Its order
is a comma-separated string inside one attribute, so it is a list of ids and
nothing per-member. And the locomotive is *not* in `carids` — it is `lcid`, a
different field of a different type — which is precisely the split #199
refused when it made a locomotive a car.

[inference, unverified] `car@placing` in the 2014 wrapper is the only candidate
for per-car orientation, and it is a bare boolean with no `remark`. The
locomotive's `placing` is documented in the current wiki (`%lcplacing%`,
`loc-gen-en`) and clearly means which way round the item stands; the car's is
not documented on any current car page I read (`car-gen-en`, `car-details-en`,
`car-int-en`, `car-fun-en` list no such field, and the Interface tab's
"Invert" / "Logical Direction" are decoder-command options, not a coupling
fact). **Treat per-car orientation in Rocrail as unconfirmed.**

### Rocrail has no product level

[fact] Nothing in `<plan>` is a product. The only shared, per-product document
is `decfile`, a decoder definition from `decspecs/` (`nmra-rp922.xml`,
`nmra-rp922-acc.xml`, and vendor folders for Digitrax, ESU, NCE, TCS, Zimo) —
the same noun JMRI's decoder definitions describe, and referenced by `<lc>`,
`<car>` and switches alike.

[fact] What stands in for one is copy-and-import. `car-en`: **Copy** — *"Use
the selected car entry as template for a new car"*; **Import** — *"Import cars
from another plan or CSV file"*, where *"The first row must contain the
attribute names"*. The car table exports to CSV in the same shape.

## 7. Which of #199's three levels each format has

| Level | JMRI DecoderPro roster | JMRI OperationsPro | Rocrail plan |
| --- | --- | --- | --- |
| **Model** (the product) | **absent.** The decoder *definition* is the only shared per-product file, and it describes the decoder | **absent.** `<types>`, `<lengths>`, `<models>` are pick-lists of bare strings | **absent.** `decfile` is a decoder definition; a "template" is a copied car |
| **Car** (the owned item) | **locomotives only** — `<locomotive>`, address on it | **both** — `<car>` and `<engine>`, **no address on either** | **both** — `<car>` and `<lc>`, address on both |
| **Train** (ordered list) | **no** — `consist.xml` is a traction consist of locomotives | **no** — `<train>` is a working with a route; membership is `trainId` on the car | **yes** — `<operator lcid carids>` |

[inference] **Neither product has #199's model level.** Both stop one short: a
per-decoder definition that a per-item entry overrides, with the item's own
physical facts written out longhand every time. That is the strongest single
result here — the catalogue is ours to invent, and the two mature formats are
evidence that skipping it is survivable, not that it is right. Rocrail
separates car from train the way #199 does and JMRI does not; JMRI separates
product from item at the decoder and Rocrail barely does.

## 8. Where each field #199 needs actually lives

| #199 field | JMRI roster | JMRI Operations | Rocrail |
| --- | --- | --- | --- |
| **length** | **nowhere** (no such attribute; only `attributepairs` by convention) | `car@length`, `engine@length`; unit is the Operations setting | `car@len` (per car, cm) and `lc@len` (loco alone, or loco+train if no train is assembled); train length is the derived sum |
| **kind** | **nowhere**; roster *groups* and `attributepairs` are the only handles | `car@type` + `passenger`/`caboose`/`fred` flags; `engine@type`, `@model` | `car@type` (`freight`/`passenger`) + `car@subtype` (21 values); `lc@engine`; train kind is `cargo`, **authored on the loco or the train**, not derived |
| **address** | `<locoaddress><dcclocoaddress number longaddress>` + `<protocol>`; the entry-level `dccAddress` is deprecated | **absent**; recovered from the roster by a four-way name guess | `lc@addr` and `car@addr`, each with `iid`, `bus`, `prot`, `protver` — a **system-qualified** address, not a bare one |
| **function meanings** | `<functionlabels><functionlabel num lockable visible>`; defaults inherited from the decoder definition, blank-means-inherit | — | `<fundef fn text icon sound timer addr mappedfn>` per car and per loco; label plus behaviour |
| **train composition** | `consist.xml`: ordered locomotives (`lead`/`mid`+`locoMidNumber`/`rear`) | membership on the car (`trainId`); order only implied by `blocking` and `kernel` | `operator@carids`, an ordered comma-separated string; the locomotive is `lcid`, outside the list |
| **orientation in train** | `consist.xml` `loco@locoDir` (`normal`/`reverse`); over JSON, `consist.engines[].forward` | — | `lc@placing` (documented); `car@placing` (present in the 2014 wrapper, **unconfirmed in current docs**) |
| **priority** | — | `carLoad@priority` (a load's priority, not a train's) | `lc@priority`, 1–100, but *"used for multiplying the wait time if no destination is found"* — a politeness weight, not our strict ordering |

[inference] Two mismatches are structural rather than missing-field. Rocrail's
address is **system-qualified** (`iid` picks the command station) — the exact
thing ADR-0045 refused for traction, and its stated reason (several command
stations at once) is real for Rocrail because Rocrail drives accessories and
traction from one table. And Rocrail's train kind is **authored** and
overriding, where ours is derived from the cars ignoring locomotives; an
importer must either drop `cargo` or treat it as a hint to check the
derivation against.

## 9. Is an import cheap, and what would it not carry

[inference] **Cheap for the half it covers, and the half is the expensive half
to type.**

**From JMRI.** One read of `roster.xml` off disk (no running JMRI), or one
GET of `/json/v5/roster` (§5), yields per locomotive: a stable `id`, the DCC
address with its long/short flag, the decoder family and model, road name and
number, manufacturer, owner, comment, an image, and every function label with
its lockable flag. That is #199's address and function meanings, complete,
plus everything needed to name a model. It is the whole reason the ticket was
opened — *every address is typed once instead of twice* — and it holds.

It would **not** carry: any length; any kind; any train, because JMRI has no
rake; any orientation, unless the owner happens to keep DCC consists, in which
case `consist.xml` gives locomotive order and `locoDir`; any priority. Nor
would it carry non-locomotive stock at all: the roster has one element type,
`<locomotive>`, so a rake of coaches is invisible to it. Taking length and kind
from OperationsPro instead means a second import, from three more files, joined
to the first by JMRI's own four-attempt string guess — which is a join we would
be inheriting, not making.

**From Rocrail.** One read of `plan.xml` yields cars *and* locomotives *and*
trains: id, address, length, type and subtype, function definitions, and
`carids` giving each train's ordered membership. Structurally that is five of
#199's seven fields in one file, and the CSV export of the car table is an even
cheaper path for the stock alone. The costs: stock is mixed into the same
document as the entire track plan, so the importer parses a layout file to find
it; the address is system-qualified and has to be reduced to a bare number; the
locomotive sits outside `carids` and has to be prepended as a car; `cargo` is an
authored train kind that our derivation would contradict; `priority` means
something else; and per-car orientation is unconfirmed, so orientation may have
to be asked for after import anyway.

[inference] **What neither carries, and what that says.** Both files mix
durable stock with live state — Rocrail's `location`, `V`, `dir`, `status`,
`prevlocation1..3`; Operations' `location`, `destination`, `trainId`,
`routeLocationId`, build status. Our roster is durable only (ADR-0039's
*known* is separate from *placed*), so an importer drops all of it, and the
drop is not lossy for us. Neither carries anything answering to a block's
**role**, our **facing**, or a derived train kind, because none of those is a
property of stock. And neither has a model: an import produces cars with every
field written out, and either we accept a flat roster on day one or the model
level is populated by hand afterwards — which is an argument for the model
being *optional to reference*, not for it being absent.

## Open points not settled by the sources

- **`car@placing` in current Rocrail.** Present in a 2014 mirror of the
  wrapper, absent from every current car wiki page read. Whether Rocrail
  records which way round a car is coupled is **unverified**; the locomotive's
  `placing` is verified.
- **The Rocrail wrapper's currency generally.** Every attribute above marked
  *[fact, mirror]* comes from 2014. Where a current wiki page names the same
  field it is cross-checked and cited; fields added since are invisible here,
  and no upstream Rocrail source repository was reachable to close the gap.
- **Whether `<operator carids>` order is the physical order.** The wiki's
  Up/Down and *"images … in the order of the car list"* say the list is
  ordered and the order is meaningful to the display; nothing read states that
  Rocrail uses it as the physical sequence for anything else.
- **Rocrail's client protocol (TCP 8051).** Whether the plan's stock can be
  read over it rather than off disk was not investigated; the disk read is
  sufficient for an import and the wiki documents the plan file, not the wire.
- **JMRI roster attribute conventions.** `attributepairs` is free-form and
  other JMRI tools write into it; which keys a real DecoderPro roster carries
  in practice was not measured, only the mechanism read.
- **Whether any owner's real roster is a useful seed.** Everything here is the
  format's capacity. What a particular DecoderPro roster actually has filled in
  — function labels especially, which are optional and tedious — is a question
  for the owner's file, not for the schema.
