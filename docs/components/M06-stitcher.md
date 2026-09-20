# M06 — Stitcher

## Purpose

Match endpoints across participants.

This is where the system graph either earns trust or invents architecture, so its default is
to refuse rather than guess.

## Interface

```
Stitcher
  stitch(participants, claims) -> SystemGraph
```

**Where the code lives.** The stitcher is `application/stitch` — matching is core
computation, not an adapter. It reaches bundles only through the `Workspace` port's
federated views; any SQL lives in `storage/duckdb` as implementation of
[D01](D01-graph-schema.md).

## Inputs

The `ParticipantSet` from [M05](M05-sync.md), and each bundle's endpoints, shapes,
deployment facts and aliases. Claims from [M01](M01-overlay.md).

**No code, no repositories, no builds.** Everything needed already travelled in bundles.

## Output

`links`, `participants` and `findings` in [D01](D01-graph-schema.md); `proposals.yml`; and
open questions.

## Behaviour

### The filter chain

Each outbound endpoint runs through four steps. Survivors at the end decide the tier.

```
0. environment   select each participant's resolved values for THE system's environment
1. protocol      http | soap | grpc | kafka | jms | sqs | pubsub
2. wire identity path template │ topic name │ fully-qualified service and method
3. structure     directional payload compatibility
4. count         the number of survivors decides the resolution
```

**Step 0 exists because endpoints carry expressions, not values.** A listener's wire
identity is `${orders.topic}`; what it names lives in `resolved_config`, per environment.
`system.yml` declares exactly one environment, and every comparison in steps 1–3 uses the
values resolved **for that environment**.

**Matching never compares expression text.** Two services can use the same key name for
different topics, and different key names for the same topic. The rule is always
*expression → this environment's value → compare values*. An identity that is unresolved
for this environment is an unmatched link with its own reason — `unresolved_for_env` — which
tells the reader the profile is incomplete, not that the dependency is absent.

### Step 2 differs sharply by protocol

Three of the four protocols have a hard key. Only plain HTTP without deployment artifacts is
genuinely ambiguous.

| Protocol | Key | Strength |
|---|---|---|
| gRPC | Fully-qualified service and method | **Strongest.** Both sides derive from one schema, and the field numbers must agree or the wire breaks. |
| SOAP | Namespace and operation | Strong — **when the contract was read.** Since Phase 2I it usually is: a `.wsdl`/`.xsd` in the repository derives the operation's QName, and an annotation-derived row carries the identical string. A module whose contract is served only from a runtime URL, and a `@SoapAction` row (a different identity axis), still fall back to step 3. |
| Message | Topic name | Strong, once configuration resolved it |
| HTTP with a declared client | The service-discovery name the client states | Strong |
| HTTP with deployment artifacts | Configuration value, to Service name, to the module that owns it | Strong |
| HTTP, path only | The path template | **Weak on its own** |

Path templates match by shape, not by string: `/v1/orders/42` matches `/v1/orders/{id}`.
Where a concrete address matches several templates, **all are reported in specificity
order**. Predicting which one a framework would choose at runtime means writing a second
copy of somebody else's routing table, and it will eventually disagree with the real one.

### Step 3 — directional structural compatibility

Two tests pointing in opposite directions:

```
REQUEST    the client must contain every field the server REQUIRES
           client shape  ⊇  server's required fields

RESPONSE   the server must contain every field the client DECLARES
           client shape  ⊆  server's response
```

A client sending extra fields is fine. A client ignoring extra fields is fine. A client
missing a required field means these are not the same endpoint.

**The REQUEST test reads `endpoint_metadata` beside the payload shape** (spec 2026-09-19
§5e; [D01](D01-graph-schema.md) §3). An inbound row's entries with `requirement: required`
— a header, query parameter or cookie the server's framework rejects a request without —
are part of what the server REQUIRES: a client row whose own metadata carries no entry of
that kind and name fails the test the way a missing required body field does. Entries
marked `optional` or `absent`, and entries whose `requirement` is NULL (a bare read in the
handler, stating nothing), do not affect matching. The rows exist today, written by the
resolver; this paragraph is what the stitcher does with them when it is built.

**Comparison is on wire identity, never on type names.** `OrderCreationCommand` and
`CreateOrderRequest` may be the same contract; a rewritten schema with matching field
numbers still matches.

Where a format publishes compatibility rules, those rules are applied rather than
reimplemented.

The client shape compared against the response is the shape **as declared**, not the fields
the client actually reads. That is cheaper, and it catches a real defect: a declared field
the server never returns is a field that is always null.

### Step 4 — the tier falls out of uniqueness

| Survivors | `resolution` | `evidence` |
|---|---|---|
| A shared contract, or a resolved deployment chain | `resolved` | `declared` |
| Exactly one | `resolved` | `name_match` |
| Several | `narrowed`, all listed | `name_match` |
| None | `unresolved`, with a reason | — |
| Asserted by a person | `resolved` | `human` |

**No threshold is needed, and that is deliberate.** Structural matching discriminates well
on rich shapes and badly on thin ones — an endpoint taking `{id}` and returning `{status}`
is compatible with many others. But that case does not need a special rule: it produces
several survivors, which is already `narrowed` with every candidate listed. Uniqueness
across the system does the work, and there is no parameter to tune.

### Ambiguity goes to a person, cheaply

A `narrowed` link is recorded with all its candidates **and** written to `proposals.yml` in
exactly the shape a curation takes ([D03](D03-overlay-schema.md)). Accepting one means
deleting the wrong lines and moving the file.

If that loop is not this cheap, nobody uses it, and the strictness everywhere else becomes a
permanent hole.

### Curation wins, and disagreement is still recorded

A person may assert a link whose payloads are structurally incompatible. The link is
created at rank 90 **and** an open question is written. Both readings are interesting: a
gateway may be transforming payloads, which the architecture should say; or the curation
names the wrong endpoint.

### Two findings that are not errors

**An outbound endpoint matching nothing** is either a service outside the system, a
participant nobody added, or a dependency nobody documented.

**An inbound endpoint nobody calls** is either dead, or called from outside.

Both are output. Neither stops the run. But an unmatched call into a participant
[M05](M05-sync.md) marked **absent** is attributed to the gap, not reported as an
architectural finding.

### External participants

A call whose target resolves to a declared external host produces a link to that
participant. Without this, every third-party call reads as an unmatched outbound endpoint
and the real dependencies are lost in the noise.

## What it must not do

- **No reading code or repositories.**
- **No heuristic linking above `name_match`.** A wrong link invents an architectural
  dependency, which is fabrication rather than imprecision — and an agent will then reason
  from it.
- **No silent choice among candidates.** Several survivors is `narrowed`, never a pick.
- **No runtime prediction.** Report the candidates a router could match; do not simulate the
  router.
- **No writing to `system.yml` or `curations.yml`.** Proposals go to their own file.

## Honesty obligations

- Unmatched outbound and uncalled inbound endpoints, separately.
- Unmatched calls attributed to an absent participant, kept apart from real findings.
- Every `narrowed` link with all candidates and the evidence that produced them.
- Every open question from a curation that contradicted the structure.
- Where SOAP matching fell back to structure because no contract was read.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether a chain through a gateway that rewrites paths can be matched, or is always curated | [D03](D03-overlay-schema.md) |
| Whether message links distinguish a consumer group from a topic subscription | Message topology fidelity |
| Whether a link may be asserted against an endpoint no bundle declares | [D03](D03-overlay-schema.md), M05 |
| How shapes are compared when the two sides use different serialisation formats | Step 3 |
