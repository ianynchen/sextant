# D03 — Overlay files

Statements about the graph that did not come from reading code. Written by people, by the
overlay skill, and by [M06](M06-stitcher.md). Read by [M01](M01-overlay.md).

Four kinds. Two are written by a person and outrank code; two are written by a model and
outrank nothing.

---

## 1. The rule every overlay obeys

> **An overlay may name only symbols, endpoints, shapes and modules that already exist in
> the graph.**

[M01](M01-overlay.md) checks this before any overlay is used, and rejects the file
otherwise. This is not a lint. It is what makes invention structurally impossible rather
than detected afterwards — an unvalidated model stage will eventually report boundaries
that exist in no code, and only a check that runs by construction cannot be forgotten.

---

## 2. Common envelope

Every overlay file carries:

| Field | Meaning |
|---|---|
| `kind` | `curation`, `components`, `view`, `proposals` |
| `schema` | Versioned, e.g. `sextant.overlay.curation.v1` |
| `scope` | The module or system it applies to |
| `source` | `human`, or `llm:<model>` |
| `generated_from` | The graph stamp it was produced against — absent for hand-written files |

Human-written files use `.yml`. Machine-written files that a person is expected to edit —
`proposals.yml` — are also `.yml`. Nothing here is JSON, because everything here is edited
by hand at some point.

---

## 3. `curation` — written by a person, rank 90

The highest-trust source in the model. A curated statement is presented to every consumer
as **`resolution: resolved`, `evidence: human`**.

```yaml
kind: curation
schema: sextant.overlay.curation.v1
scope: system/order-platform

links:
  assert:
    - from: { service: orders,  endpoint: "POST /v1/orders" }
      to:   { service: billing, endpoint: "POST /v1/charge" }
      note: "goes through the gateway, which rewrites the path"
  delete:
    - from: { service: orders,  endpoint: "GET /health" }
      to:   { service: billing, endpoint: "GET /health" }

aliases:
  - service: orders
    add: [orders-svc, ORDERS-SERVICE]

classification:
  - module: ":tools:codegen"
    kind: library
```

Four capabilities: assert a link, delete a wrong one, add aliases, and override a module
classification the evidence left undetermined.

**Curations reference endpoints by wire contract** — service name plus method and path
template, topic, or remote method — which is exactly what endpoint identity is minted from
([D01](D01-graph-schema.md)). So a curation survives any refactor that leaves the wire
unchanged, and breaks only when the endpoint it described genuinely stopped existing —
which is then a *correct* validation failure, not an orphaning.

**A curation that disagrees with the graph still wins — and the disagreement is recorded.**
If a person asserts a link whose payloads are structurally incompatible, the link is
created at rank 90 *and* an `open_question` is written. Both explanations are interesting:
there may be a gateway transforming payloads, which the architecture should say; or the
curation names the wrong endpoint. Silently accepting it would hide a typo forever.

---

## 4. `proposals` — written by Sextant, read by a person

Machine-written in **exactly the shape a curation takes**, so accepting one is deleting the
wrong lines and moving the file. If that loop is not this cheap, nobody uses it and the
strictness elsewhere becomes a permanent hole.

```yaml
kind: proposals
schema: sextant.overlay.proposals.v1
scope: system/order-platform

links:
  assert:
    - from: { service: orders, endpoint: "POST /v1/orders" }
      to:   { service: billing, endpoint: "POST /v1/charge" }
      # ---- evidence, stripped when accepted ----
      evidence: name_match
      why: "path template matches; request shape satisfies 6 required fields"
      competing:
        - { service: legacy-billing, endpoint: "POST /v1/charge" }
```

Everything under `evidence`, `why` and `competing` is commentary. Accepting a proposal
means moving the entry; the commentary may be left in place and is ignored.

Two things go here: **ambiguous links**, where several inbound endpoints survived matching;
and **discovered aliases** that were inferred by similarity rather than declared by a
module's own artifacts.

---

## 5. `components` — written by the skill, rank 10

Names and purposes for groupings that the code does not express structurally.

```yaml
kind: components
schema: sextant.overlay.components.v1
scope: module/:services:orders
source: llm:claude-opus-5
generated_from: sha256:a3f9…

components:
  - id: cmp_7c1a4f
    name: Order Intake
    purpose: >
      Accepts orders from the storefront, validates them against the
      catalogue, and writes them to the order store.
    members:
      - "sextant-jvm maven com.acme/orders 2.1.0 com/acme/OrderController#"
      - "sextant-jvm maven com.acme/orders 2.1.0 com/acme/OrderService#"
    content_hash: sha256:9b2e…
    membership_changes:
      - { symbol: "…/OrderValidator#", action: added, why: "…" }
```

**`id` is derived from the sorted member list, never assigned in sequence.** Otherwise a
re-run renumbers every component and every document churns. `content_hash` covers the
members and their graph slice, so prose is regenerated only when what it describes has
changed.

Membership may be adjusted away from what clustering proposed, but **every change is listed
with a reason**. Silent moves are rejected.

---

## 6. `view` — written by the skill, rank 10

Presentation instructions for one trace. **The skill never draws a diagram; it says what to
show.** The renderer draws from real graph rows, so a diagram cannot contain a call that
does not exist.

```yaml
kind: view
schema: sextant.overlay.view.v1
scope: module/:services:orders
trace: ep_3f8b

hide:     ["…/OrderMapper#toDto()."]
collapse: [{ symbols: ["…/OrderRepository#save().", "…/AuditLog#write()."], as: "persist order" }]
promote:  ["…/PricingService#price()."]
note:     [{ at: "…/OrderValidator#check().", text: "rejects on stale catalogue" }]

dispatch:
  - call_site: cs_91b4
    groups:
      - { candidates: ["…/ExpressShipper#ship().",  "…/PriorityShipper#ship()."], label: "expedited" }
      - { candidates: ["…/StandardShipper#ship()."], label: "standard" }
    primary: "…/StandardShipper#ship()."
    condition_note: "chosen by order.channel"
```

Three validation rules beyond the general one:

- **A terminal of kind `unresolved` or `cycle` may never be hidden.** Those are the places a
  person must look, and no overlay can suppress them.
- **Every candidate at a grouped call site appears in exactly one group**, or the rendered
  diagram states how many were not shown.
- **`primary` is a presentation choice.** It never changes a fact's `resolution`.

---

## 7. Where overlay files live

| File | Location | In git |
|---|---|---|
| `curations.yml` | Module root, or beside `system.yml` | **Yes** — it is an input |
| `proposals.yml` | The workspace | No — regenerated each run |
| `components`, `view` | Beside `curations.yml` | **Yes**, deliberately |

Component and view files are the one exception to *outputs do not go in git*. They cost
money to regenerate, come back differently worded each time, and a person may correct them
by hand. That behaviour is closer to source than to build output — which is exactly why the
identifier and hashing rules in section 5 are compulsory rather than advisable.

---

## 8. Open decisions

| Decision | Blocks |
|---|---|
| Whether a curation may assert an endpoint that no code declares, for a service Sextant cannot analyse | M06, and how external participants are modelled |
| Whether `view` can apply to a class diagram as well as a trace | M07 |
| How a curation survives a symbol being renamed | The curation lifecycle |
