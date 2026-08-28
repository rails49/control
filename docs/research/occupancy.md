# What the occupancy hardware publishes

Resolves [#197](https://github.com/rails49/control/issues/197). Reads
[rails49/occupancy](https://github.com/rails49/occupancy) — camera-based track
occupancy detection — for what it puts on the wire, so the layout interface of
[SYSTEM.md](../SYSTEM.md#layout-interface) can be bound to it. Source pinned at
`rails49/occupancy@58afe0d` (main, cloned 2026-08-28); every `path:line` below
is into that commit. Terminology of this repo follows [CONTEXT.md](../../CONTEXT.md);
the source repo's own words (L0, L1, sensor, archive) are kept where they
are quoted.

Each claim is tagged: **[fact]** is stated in or read off the source repo;
**[inference]** is this document's reading of it.

## The one finding

**It publishes nothing.** [fact] There is no MQTT client, broker address,
topic, or payload anywhere in the repository. The word `mqtt` occurs once, in
a list of intended uses — *"Real-time classification, e.g. on a mobile device,
uploading results via MQTT to a model railroad controller such as Rocrail"*
(`SPEC.md:435`) — and nowhere in code, lockfile, or any `package.json`. What
exists is a per-frame occupancy map computed inside a browser tab and drawn
over the camera image. Everything the ticket asks about the wire — topic
shape, payload, retention, an inquiry for current state — is therefore
**unanswered by the repo because it is undecided**, not because it is hidden.
The remaining questions (what a region is addressed by, startup, repeat and
latency behaviour) do have answers, from the in-browser contract that a
publisher would be wrapping. Those follow.

## What exists: the in-browser occupancy contract

### Two layers, and the second is the one a controller reads

[fact] The system reports "two layers and no more" (`SPEC.md:100-111`):

| | What it is | Source |
| --- | --- | --- |
| **L0** | every detected car: oriented box (centre, length, width, angle), class, confidence, exactly as the detector emitted it | the YOLO26n-OBB model |
| **L1** | per-sensor state: `occupied` / `clear` / `unknown` | pure geometry over L0 |

L1 is a pure function of L0 — `occupancy()` in
`lib/detector/src/occupancy.ts:42-98` — never a second model. A sensor is
`occupied` when a detection's oriented box strictly contains its point, after
the box's width is replaced by a DPT-derived constant (`occupancy.ts:76-94`,
`geometry.ts:154-164`, `SPEC.md:113-117`).

[fact] The L1 vocabulary (`SPEC.md:134-148`, `lib/detector/src/types.ts:54-69`):

- `occupied` — any detection above the confidence threshold covers the point,
  low-confidence ones included; carries the covering `Detection`.
- `clear` — no detection covers the point; carries **no** confidence, "absent,
  not `0.0` and not `1.0`", because nothing scored it (`SPEC.md:154`).
- `unknown` — the system *cannot look*: `no-model`, `no-calibration`,
  `outside-frame`, or `drift` (camera moved from the pose the sensors were
  authored in). "Never a confidence outcome" (`SPEC.md:142`).

[fact] Errors are biased toward `occupied` deliberately, and the spec accepts
the consequence in the controller's terms: "a permanently blocked block is
never entered and never cleared, so it can **deadlock a controller's
schedule**. Weighed against a collision and accepted" (`SPEC.md:144-148`).

### Everything above L1 is deliberately unspecified

[fact] "Everything above L1 — event and transition semantics (Rocrail's
enter/in sensors fire on *transitions*, not per-frame state) and block-span
occupancy — is deliberately unspecified" (`SPEC.md:111`). It is listed as
**in scope, still unresolved**: "L2: event and transition semantics ...
Converting one to the other needs debouncing and hysteresis, which is exactly
where a phantom becomes a spurious 'train entered block' a controller acts on.
Deferred until a real controller is in the loop" (`SPEC.md:620`). Block-span
occupancy is "retrofittable for free from L0, but a named interval on track
presupposes track" — and the `.r49` format stores no track geometry
(`SPEC.md:302-314`, `SPEC.md:621`).

## What a detected region is addressed by

[fact] A **sensor** is a single point, authored per layout (not per image),
in `camera.resolution` pixel coordinates, with an `id` and an optional `name`
(`lib/r49/src/manifest.schema.ts:264-272`, `:359-360`; `SPEC.md:296`,
`SPEC.md:300`). The schema:

```ts
const SensorSchema = z.object({
  id: z.string().min(1),
  x: z.number(),
  y: z.number(),
  /** Free text, not unique, and never auto-generated — absent when unset. */
  name: z.string().optional(),
}).strict();
```

[fact] The editor mints the id with `make_id(SENSOR_NODE_ID)`
(`ui/src/rr-editor-view.ts:2001`): a Snowflake-like 64-bit id encoded as
**exactly 11 Base62 characters** — 41 bits of milliseconds since 2024-01-01,
10 bits node, 12 bits sequence (`lib/uid/src/uid.ts:27-38`). The fixture
archive shows the shape: `{"id": "sensor-fixture-1", "x": 640, "y": 500,
"name": "siding 3"}` in a 1920×1080 frame
(`lib/r49/tests/fixtures/format-v4.r49`, `manifest.json`). Ids are unique
within an archive's sensor list (`manifest.schema.ts:317-329`); an archive
itself carries an optional `id` (`manifest.schema.ts:380-392`).

[fact] "**Sensor identity: consumers key on `id`;** `name` is optional
passthrough, absent when unset and never auto-generated. ids survive edits;
names are free text, are not unique, and a controller mapping keyed on one
breaks the moment someone renames it ... The optional `name` exists for
Rocrail and for humans who cannot remember hex strings" (`SPEC.md:173`;
same rule at `ui/src/rr-sensor-dialog.ts:19-30`). The L1 result is a
`ReadonlyMap<string, SensorState>` keyed by that id (`occupancy.ts:48-50`,
`:94`).

[fact] Sensors are points, not spans, by decision: "a span would match a
prototype block more closely, but L0 carries full car pose so block semantics
stay derivable later, whereas authoring intervals is real UI for a consumer
not yet observable" (`SPEC.md:300`). Spans and track were ruled out of v4 in
occupancy issues [#7](https://github.com/rails49/occupancy/issues/7) and
[#13](https://github.com/rails49/occupancy/issues/13).

### How it maps onto a block end's `sensors`

[fact, this repo] The drawing gives a block "a signal and a sensor at each
end, always", neither placed nor optional, and records only "a sensor's
hardware id, which is a property of a sensor that already exists"
([DRAWING.md](../store/DRAWING.md#symbols), *A block carries...*). `sensors`
is a mapping from end (`A`, `B`) to id; the store checks the id with
`check_name` — a non-empty string containing neither `.` nor `/`
(`src/tc49/store/drawing.py:820-826`, `src/tc49/lib/layout.py:177-179`).
Derivation drops it; nothing on the bus sees it
([DRAWING.md](../store/DRAWING.md#hardware-ids)).

[inference] The two models fit each other directly: an occupancy **sensor**
*is* a point detector at one block end, and its `.r49` `id` *is* the hardware
id the drawing wants — `sensors: {A: 0Ab3xY9kLmN, B: 0Ab3xY9kLmP}`. An 11-char
Base62 id passes `check_name` as-is. The `name` field is the human label and
must not be used for the join, per the source repo's own rule.

[inference] Two things do not fit and would be the adapter's job:

1. **A point sees only its point.** A short train standing mid-block covers
   neither end sensor and reads as two `clear`s. The prototype's track circuit
   this drawing models ("a sensor at each end") is a span in reality; the
   camera gives a point. Whether the dispatcher's `block_occupied` needs the
   span (a standing train that never reached an end sensor — placement after a
   power cut, [#153](https://github.com/rails49/control/issues/153)) or only the
   edges (a train arriving trips the entry end) is a question for this repo,
   and it decides how much of L0 the adapter has to read. L0 carries every
   car's pose; the *drawing* carries track geometry the `.r49` refuses to
   store; nothing in either repo maps camera pixels onto drawing coordinates.
2. **The bus is keyed by block, the map by sensor.** `block_occupied` /
   `block_vacated` carry a block ([SYSTEM.md](../SYSTEM.md#event-inventory));
   the map carries two sensors per block. The fold (either end occupied →
   block occupied, and its inverse) is the adapter's, and so is what `unknown`
   at one end means for the block.

## Whether the current state of every sensor can be queried

[fact] Inside the browser, **yes, at every frame**: `occupancy()` is total —
"one entry per sensor, always" (`occupancy.ts:12`) — and the live view
replaces the whole map each frame (`ui/src/rr-live-view.ts:77-78`,
`:426-432`). There is no edge detection and no memory between frames; each
map is the complete current state.

[fact] Outside the browser, **no**: the map is a Lit `@state` field rendered
into the viewer as coloured diamonds and reduced to a count in the stats bar
(`rr-live-view.ts:437-444`, `ui/src/rr-stats-bar.ts:124-125`). No API, no
retained value, no export. Whether a published form would be retained or
answer an inquiry is not a question the repo has faced.

## Startup

[fact] Mounting the live view starts the camera, then detection
(`rr-live-view.ts:185-189`). `_startDetection` **awaits** the detector load
(`openDetector()`, `ui/src/detectorSession.ts:66-69`), then awaits the drift
check's preparation, then starts the frame loop (`rr-live-view.ts:217-236`).
Frames before the video has metadata are skipped, not reported
(`rr-live-view.ts:281-297`). Measured time to first result is **1.0–4.5 s**;
session creation alone ranged 32 ms to 3.6 s (`SPEC.md:452`).

[fact] The loop runs whether or not the model loaded; with no model every
sensor reads `unknown`/`no-model` rather than the last frame's answers being
left on screen (`rr-live-view.ts:52-56`, `occupancy.ts:67-70`). Until a
calibration resolves, every sensor is `unknown`/`no-calibration`
(`occupancy.ts:71-74`).

[fact] The first L1 map is a **full state**, not a diff: a car sitting on a
sensor when the view opens reads `occupied` on the first frame. Initial
occupancy is reported — as state, because there is nothing else.

[fact] The first drift sample is taken on the first ready frame and lands
asynchronously (`rr-live-view.ts:345-351`); until it lands `_drifted` is
`false`, so L1 is answered — "not evidence of drift" but not evidence against
it either (`rr-live-view.ts:314-323`). If the check cannot run at all, the
view says so and reports sensor states anyway (`rr-live-view.ts:460-466`).

## Repeat and latency behaviour

[fact] The loop is `requestAnimationFrame` → `await detect()` → compute L1 →
`requestAnimationFrame` again (`rr-live-view.ts:379-435`), so its cadence is
one inference. Median `session.run()` alone at 960×544: **120 ms** iPhone (4
threads), 191 ms iPhone (1 thread), **445 ms** iPad, 298 ms 2017 MacBook
(`SPEC.md:439-453`); the spec says to "plan against ~450 ms" and notes
threading needs cross-origin isolation that a CDN silently takes away
(`SPEC.md:451-453`). A drift sample (~0.27 s of arithmetic) is interleaved
every 3 s (`rr-live-view.ts:23-38`). So the map refreshes at roughly **2–8 Hz**
and every refresh is a complete level reading. [inference] A backgrounded
phone tab is throttled by the browser — the repo measured 0.53 s of work taking
6 s once nested timers were clamped (`ui/CLAUDE.md:530-534`) — so a phone
that is not kept in the foreground is not a sensor.

[fact] **There is no debounce, hysteresis, or transition event.** L1 is
"per-frame state" and L2 is deferred (`SPEC.md:111`, `:620`). The accuracy
contract (occupancy [#126](https://github.com/rails49/occupancy/issues/126))
binds on **static scenes only**: "Cars in motion — arrival latency, flicker
mid-traversal — are outside it and stay fog on the map (L1 hysteresis for
moving stock)". Its targets: false clear < 0.1 %, false occupied < 1 %, per
(sensor, static scene). Nothing measures them yet — "there is no held-out
protocol for either model" and the confidence threshold "is a placeholder"
(`SPEC.md:617`, `config.yaml:110-113`); the shipped detector's
`version.txt` says `unreleased` (root `CLAUDE.md:167`).

[fact] One repeat pattern is quantified: a long car on a tight curve bows off
the box's chord, so "a sensor near the car's midpoint falls outside the box.
The ends still register, so a long car crossing a sensor reads occupied →
clear → occupied" (`SPEC.md:119-132`; 85 ft cars fail below ~25″ radius in
HO). The suggested mitigation is inflating `layout.standard_width` in
`config.yaml`, not code.

[fact] Camera drift past a tolerance (a quarter track width,
`config.yaml:102`) makes **every** sensor `unknown`/`drift` while L0 boxes keep
being drawn; a human override on the view re-enables L1 and is not sticky
across a remount (`occupancy.ts:57-66`, `rr-live-view.ts:58-66`, `:118-126`).

## What it means for the contract

- **[fact] There is no adapter to write against; there is a publisher to
  design.** Both halves of the MQTT bridge are unbuilt, and the occupancy repo
  says in as many words that it is waiting for "a real controller in the
  loop" before deciding L2 (`SPEC.md:620`). This repo is that controller, so
  the topic shape and payload are ours to propose, and the occupancy repo's
  side is a ticket there, not a fact to discover here.

- **[inference] What it can honestly publish is per-sensor *state*, ~2–8 Hz,
  keyed by `.r49` sensor id, with `unknown` as a first-class value.** That is a
  state topic in SYSTEM.md's terms, not the `block_occupied` /
  `block_vacated` events. Turning level into edge — debounce, hysteresis, the
  two-ends-into-one-block fold, and what `unknown` means for a block — is
  exactly the deferred L2, and by [ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md)
  it belongs in the layout interface, behind the contract, not in the
  dispatcher and not in the camera.

- **[inference] Power-up and #153.** The first frame after model load
  (1–4.5 s) is a total map, so "the current state of every sensor" exists
  from the start without any inquiry. If the publisher writes it as a retained
  per-camera map, a late-joining layout interface reads it, and the dispute
  check gets its readings without the bus answering a query — which the bus
  refuses ([SYSTEM.md](../SYSTEM.md#the-bus)). `unknown` maps onto #153's
  "silence is not a clear reading": an `unknown` sensor must reach the
  dispatcher as *not reported*, never as clear. Reporting initial occupancy as
  **state** also keeps SYSTEM.md's "initial occupancy is never published"
  true of the *event* topics while still delivering it.

- **[inference] The contract's own choices are unaffected, and its assumptions
  are confirmed.** Anonymous occupancy is what the camera gives — L0 knows
  car class, never train identity, so "it never asserts train identity"
  ([SYSTEM.md](../SYSTEM.md#layout-interface)) holds. The layout interface
  picking its own cadence ([ADR-0009](../adr/0009-layout-interface-owns-time.md))
  is right: at 120–450 ms per frame with flicker unspecified, a boundary that
  is a few frames wide with a debounce inside it is the adapter's business.
  The fail-occupied bias and the accepted phantom deadlock are the
  wedged-block outcome [ADR-0040](../adr/0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md)
  already chooses; the recourse — hold and `placement_wanted` — is the same.

- **[inference] The drawing's `sensors` needs no change.** One `.r49` sensor
  id per block end, opaque, passes today's `check_name`. What the drawing
  cannot express and may need to is *which camera* — a layout under several
  phones is several archives, each with its own sensor list, and a topic will
  want the archive `id` (`manifest.schema.ts:392`) or a camera name in its
  path. A sensor id is globally unique enough (Snowflake) that the join works
  without it; the camera matters for `unknown`/`drift`, which is per camera.

## Left unanswered by the source repo

Stated so nobody guesses: topic grammar, payload encoding, QoS, retention,
what a camera calls itself, whether L0 boxes should go on the wire alongside
L1, any debounce or hysteresis constant, arrival latency for a moving train,
measured accuracy of any kind, and whether the app can run unattended (a
phone with a tab in the foreground is the only deployment that exists —
`README.md:13`). The span-versus-point question in
[How it maps](#how-it-maps-onto-a-block-ends-sensors) is this repo's to
answer first, because it decides whether the adapter reads L1 or L0.
