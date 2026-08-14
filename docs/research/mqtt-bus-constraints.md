# MQTT Compatibility Constraints for the Bus Abstraction

Resolves [#14](https://github.com/iot49/tc49/issues/14), part of the
[System organization map](https://github.com/iot49/tc49/issues/13). Answers:
what may the milestone-1 in-process bus promise **without promising more than
MQTT can later deliver**? Everything below is sourced from the OASIS MQTT 5.0
specification [1] (3.1.1 [2] where it differs), and Eclipse Mosquitto's
first-party configuration docs [3] for broker-default behavior. Normative
statement IDs like `[MQTT-4.6.0-5]` are the spec's own.

## 1. Message ordering: what MQTT guarantees, and what it does not

**Guaranteed — per-topic FIFO from a single publisher, per QoS level.** The
spec defines an *Ordered Topic* as one "where the Client can be certain that
the Application Messages in that Topic from the same Client and at the same
QoS are received in the order they were published" (§4.6). A server MUST
"send PUBLISH packets to consumers (for the same Topic and QoS) in the order
that they were received from any given Client" `[MQTT-4.6.0-5]`, and MUST by
default treat every topic as an Ordered Topic for non-shared subscriptions
`[MQTT-4.6.0-6]` (3.1.1 says the same: `[MQTT-4.6.0-5]`/`[MQTT-4.6.0-6]` in
[2] §4.6). Note the qualifiers — the guarantee is scoped to *one topic*, *one
publishing client*, *one QoS level*, on non-shared subscriptions.

**Not guaranteed:**

- **Cross-topic ordering.** The ordering rule is stated per topic; nothing in
  §4.6 relates messages on different topics, even from the same publisher.
- **Cross-publisher ordering.** "From any given Client" — two publishers on
  the same topic have no defined interleaving.
- **Global ordering.** No total order exists across the system; each
  subscriber is delivered to independently (§4.3: "each Client is treated
  independently").
- **Order across QoS levels.** The Ordered Topic definition is "at the same
  QoS"; a QoS 0 and a QoS 1 message on the same topic may be reordered.
- **Order under re-delivery.** Even on an Ordered Topic at QoS 1, a
  reconnect can interleave duplicates with successors: the spec's own
  example (§4.6, non-normative) is publish `1,2,3,4`, receive
  `1,2,3,2,3,4`. Strict no-regression ordering additionally requires an
  in-flight window of 1 (Receive Maximum 1, §4.6/§4.9) — receive
  `1,2,3,3,4` but never `1,2,3,2,3,4`. Mosquitto's default
  `max_inflight_messages` is **20**; its docs state "If set to 1, this will
  guarantee in-order delivery of messages" [3].
- **Order on shared subscriptions.** §4.10.1: "when using Shared
  Subscriptions ... the order of message delivery is not guaranteed between
  multiple Clients."

## 2. QoS levels

Delivery is point-to-point per hop (publisher→broker, broker→each
subscriber); the outbound QoS to a subscriber can differ from the inbound QoS
(§4.3), and is capped by the QoS the subscriber requested (`[MQTT-3.3.4-2]`).

- **QoS 0 — at most once** (§4.3.1). No ack, no retry; "the message arrives
  at the receiver either once or not at all."
- **QoS 1 — at least once** (§4.3.2). PUBLISH/PUBACK; unacknowledged
  messages are re-sent with DUP=1, so **duplicates are normal**, and a
  receiver MUST treat a repeated Packet Identifier after PUBACK as a *new*
  application message `[MQTT-4.3.2-5]`. The DUP flag is per-hop and cannot
  be used for de-duplication: "The receiver of an MQTT Control Packet that
  contains the DUP flag set to 1 cannot assume that it has seen an earlier
  copy of this packet" (§3.3.1.1, non-normative), and a repetition can even
  arrive with DUP=0 under a fresh Packet Identifier.
- **QoS 2 — exactly once** (§4.3.3). Four-packet handshake
  (PUBLISH/PUBREC/PUBREL/PUBCOMP) with "increased overhead"; exactly-once
  holds per hop between client and broker, not end-to-end across a
  publisher–broker–subscriber chain with sessions expiring.

Practical stance: design consumers to be **idempotent** and assume QoS 1
semantics; QoS 2's cost buys per-hop de-duplication the application can get
more cheaply from idempotency.

## 3. Retained messages

- Publishing with RETAIN=1 makes the broker "replace any existing retained
  message for this topic and store the Application Message ... so that it can
  be delivered to future subscribers" `[MQTT-3.3.1-5]`. One retained message
  per topic — it is *last known state*, not history.
- A retained publish with a **zero-byte payload deletes** the retained
  message `[MQTT-3.3.1-6]`, `[MQTT-3.3.1-7]`.
- New non-shared subscribers receive the matching retained messages at
  subscribe time (Retain Handling option 0, the default: `[MQTT-3.3.1-9]`;
  options 1/2 suppress re-delivery or delivery entirely,
  `[MQTT-3.3.1-10]`/`[MQTT-3.3.1-11]`).
- Retained messages are **not session state**: "they are not deleted as a
  result of a Session ending" (§4.1) — they outlive the publisher.
- Spec's own use-case (§3.3.1.3, non-normative): "useful where publishers
  send state messages on an irregular basis. A new non-shared subscriber
  will receive the most recent state."
- Pitfalls: a **QoS 0 retained message MAY be discarded by the server at any
  time** (§3.3.1.3); a subscriber cannot distinguish a fresh retained value
  from a stale one left by a dead publisher (pair state topics with
  liveness, e.g. a Will Message, §3.1.2.5); Retain Handling knobs are MQTT
  5-only; forwarded live messages have RETAIN=0 unless Retain As Published
  is set (`[MQTT-3.3.1-12]`), so "retained" is not visible as a flag on live
  traffic by default.

**Bus-abstraction consequence:** "late subscriber sees last value per state
topic" is a *safe* thing to model (it maps to retained messages), but only as
last-value-per-topic — never "late subscriber sees missed events."

## 4. Topic naming and wildcards

- Topics are `/`-separated levels (§4.7.1.1); names and filters are **case
  sensitive**, may contain spaces, and leading/trailing `/` creates distinct
  topics (§4.7.3). Adjacent separators create zero-length levels.
- `+` matches exactly one level and must occupy a whole level
  `[MQTT-4.7.1-2]`; `#` matches the parent and any number of child levels
  and must be last in the filter `[MQTT-4.7.1-1]`. Wildcards are legal only
  in subscription filters, never in publish topic names `[MQTT-4.7.0-1]`.
- Topics starting with `$` are excluded from `#`/`+`-leading filters
  `[MQTT-4.7.2-1]` and are reserved for server purposes (`$SYS/...`);
  applications must not claim them (§4.7.2). `$share/{ShareName}/{filter}`
  is the shared-subscription syntax (§4.8.2).
- Design consequence: pick the level hierarchy so consumers can select with
  one `+`/`#` filter (e.g. `tc49/<component>/<entity>/<event>`); note that a
  message matching **overlapping filters** of one client MAY be delivered
  once *or* once per matching subscription (§3.3.4) — another reason
  consumers must tolerate duplicates.

## 5. Request/response over pub/sub

- **MQTT 5** provides first-class plumbing (§4.10): the requester publishes
  with a **Response Topic** property (§3.3.2.3.5) and optional **Correlation
  Data** (§3.3.2.3.6); the responder publishes its reply to that topic,
  copying the correlation data. The broker forwards both properties but
  "treats the Request Message and the Response Message like any other
  Application Message" (§4.10.1).
- Even in MQTT 5 this is **asynchronous and unreliable by construction**:
  "There could be multiple Responders subscribed to this Topic Name or there
  could be none," and "If there are no subscribers to the Response Topic when
  the Response Message is sent, the Response Message will not be delivered"
  (§4.10.1). The requester must subscribe to the response topic *before*
  publishing the request, and timeouts are the application's problem.
- **MQTT 3.1.1 has neither property**: request/response costs a hand-rolled
  convention — reply-topic and correlation id embedded in the payload or
  topic name — with the same races and no interop standard.

**Bus-abstraction consequence:** the bus contract must not offer a blocking
`request()` returning a value. If a query pattern is needed, model it as two
correlated events with an explicit timeout, or keep queries off the bus
entirely (the asset store's CRUD contract is separate for exactly this
reason).

## 6. Session state and the late joiner

- Session state (§4.1) holds subscriptions plus unacknowledged/pending
  **QoS 1 and QoS 2** messages; queueing QoS 0 for a disconnected session is
  merely OPTIONAL (§4.1) — Mosquitto's `queue_qos0_messages` defaults to
  false [3].
- **Clean Start = 1** discards any existing session (§3.1.2.4); Session
  Expiry Interval 0 (the default) ends the session when
  the connection closes; 0xFFFFFFFF means never (§3.1.2.11.2). The spec's
  equivalences: Clean Start 1 + expiry 0 ≡ 3.1.1 CleanSession 1; Clean
  Start 0 + no expiry ≡ CleanSession 0 (§3.1.2.11.2, non-normative).
- A **first-time or clean-start subscriber sees nothing from the past**
  except retained messages: "It will not receive Application Messages
  published before it connected and has to subscribe afresh"
  (§3.1.2.11.2, non-normative). Message queueing exists only for a
  *persistent session that already held a matching subscription* when the
  messages were published.
- Broker storage is finite: session state "can be discarded as a result of
  an administrator action" (§4.1.1); Mosquitto silently drops queued
  messages beyond `max_queued_messages` (default **1000**) [3].

**Bus-abstraction consequence:** subscription order matters. A component
that subscribes after another component publishes has missed the event, and
no replay exists. The in-process bus must not let milestone-1 code depend on
"subscribe whenever, see everything" — wire subscriptions before the first
publish, and carry state in retained-style last-value topics.

## 7. Pitfalls of swapping an in-process synchronous bus for a broker

1. **Publish is not delivery.** In-process, `publish()` can run every
   handler before returning. In MQTT, PUBACK only "transfers ownership" to
   the broker — "The receiver does not need to complete delivery of the
   Application Message before sending the PUBACK" (§4.3.2, note 1). There
   is **no delivery-completion signal** at any QoS; a publisher never learns
   that (or when, or by whom) a message was consumed.
2. **No same-tick causality.** In-process, a handler's own publishes can be
   processed before the outer publish "returns" (or at least
   deterministically ordered). Over a broker, a component that reacts to
   event A by publishing B gives no cross-topic guarantee about how others
   observe A vs B (§4.6 is per-topic only).
3. **Subscriber startup races.** See §6 — events published before a
   subscription exist nowhere. Deterministic in-process startup hides this
   race; MQTT exposes it.
4. **Back-pressure and overflow.** MQTT flow control (Receive Maximum,
   §4.9) throttles QoS>0 in-flight windows per connection, but a slow or
   disconnected persistent subscriber accumulates a broker-side queue that
   is dropped past a limit (Mosquitto: 1000, silent) [3]. QoS 0 to a slow
   client can be dropped with no trace at all (§4.3.1 "best efforts").
   The in-process bus has infinite, invisible "bandwidth"; the broker does
   not.
5. **Duplicates are normal.** QoS 1 re-delivery (§4.3.2), overlapping
   subscriptions (§3.3.4) — consumers must be idempotent.
6. **Payload is opaque bytes.** "The content and format of the data is
   application specific" (§3.3.3). Typed JSON is *our convention*, enforced
   by nothing; MQTT 5's Payload Format Indicator (§3.3.2.3.2) and Content
   Type (§3.3.2.3.9) are optional pass-through metadata, absent in 3.1.1.
   Schema/validity checking stays in the bus abstraction, not the transport.
7. **The broker is a process.** Connection loss, keep-alive timeouts
   (§3.1.2.10), server-initiated disconnects and redirection (§4.11) all
   become failure modes the in-process bus never had. Will Messages
   (§3.1.2.5) exist precisely because peers vanish silently.

## 8. What the in-process abstraction may safely promise

The intersection — everything below survives the MQTT swap unweakened:

- **Per-topic FIFO from a single publisher.** Events published by one
  component on one topic are observed by each subscriber in publish order
  (maps to Ordered Topics, `[MQTT-4.6.0-5]`/`-6`, with single-publisher
  topics and, later, in-flight window 1 for strictness).
- **Fan-out: every subscriber gets every matching event** (non-shared
  subscription semantics, §4.8.1) — but each independently, with no
  ordering relation between subscribers.
- **At-least-once mindset: consumers are idempotent.** The abstraction may
  deliver an event more than once; handlers must tolerate it (QoS 1
  semantics, §4.3.2, §3.3.4).
- **Last-value state topics.** A late subscriber to a *state* topic
  receives the most recent value (retained messages, `[MQTT-3.3.1-5]`,
  `[MQTT-3.3.1-9]`), including deletion by empty payload. Nothing more.
- **Topic grammar is MQTT's**: `/`-separated levels, `+`/`#` filters on
  subscribe only, no `$`-prefixed application topics, no wildcards in
  publish (§4.7).

And what it must **refuse** to promise, even though the in-process
implementation could trivially deliver it:

- **No synchronous request/reply** — no `publish()` that returns a value or
  blocks until handled. Query patterns are correlated event pairs with
  timeouts (§4.10) or live outside the bus (asset CRUD contract).
- **No delivery confirmation** — `publish()` completes when the bus accepts
  the event, promising nothing about consumption (§4.3.2 note 1).
- **No global or cross-topic ordering** — code must not depend on the
  relative order of events on different topics or from different
  publishers, even when the in-process scheduler happens to provide it
  (§4.6 scope).
- **No replay for late subscribers** — an event published before a
  subscription existed is gone (§3.1.2.11.2); only last-value state topics
  bridge the gap.
- **No unbounded queues** — a contract-level note that slow consumers may
  lose events keeps milestone-1 code honest about the broker future [3].

The deterministic, synchronous milestone-1 implementation is then a *legal
scheduler* of these weak semantics (one that happens to be replay-exact for
tests), rather than a stronger contract the MQTT transport would later break.

## References

[1] OASIS Standard, *MQTT Version 5.0*, 7 March 2019.
    <https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html>
    (§ numbers and `[MQTT-x.y.z-n]` normative IDs cited inline.)

[2] OASIS Standard, *MQTT Version 3.1.1*, 29 October 2014.
    <https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html>

[3] Eclipse Mosquitto, *mosquitto.conf(5)* manual:
    `max_inflight_messages` (default 20; "If set to 1, this will guarantee
    in-order delivery of messages"), `max_queued_messages` (default 1000;
    beyond it "messages will be silently dropped"), `queue_qos0_messages`
    (default false). <https://mosquitto.org/man/mosquitto-conf-5.html>
