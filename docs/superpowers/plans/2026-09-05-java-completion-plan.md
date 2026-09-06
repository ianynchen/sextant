# Java completion plan — everything outstanding, ordered

**Written 2026-09-05 at the user's request: "give me your recommended approach
with everything that needs to be done for Java included … don't want to miss
any of them out."**

This is an inventory plus an order, not a spec. Every line is sourced — from
the 2O plan, the sweep triage, the round-1 review, or a measurement taken
today against `spring-petclinic` and `macrozheng/mall`. Nothing here is
recalled.

Sizes are relative (S/M/L), not estimates. Where an item is a prerequisite for
another, it says so.

---

## The complete inventory

### A. Phase 2O — six tasks never started

| task | what | size |
|---|---|---|
| 8 | The two non-wire families | M |
| 9 | Spring Integration — the channel join, on measured evidence | M |
| 10 | The `@HttpExchange` direction flip | M |
| 11 | The loud-failure pin | S |
| 12 | The documentation sweep | M |
| 13 | Wire the consumers 9.15/9.16 unblocked — **three** consumers (`media_values`, `all_strings`, and `channel_of`, corrected in `e29b7ec`) | M |

Ledger: Tasks 1-7 and 7b complete. 2O is otherwise untouched since 7b's fix round.

### B. 2O residuals — deliberately left open, each with a COVERAGE row

| item | why it is open | closes by |
|---|---|---|
| Controller stereotype inherited from a `@Controller` superclass/interface | `isHandler` says yes (measured); whether component scan admits the subclass is not measured. Half a rule is §8.1 rule 4 | probe rank 1 |
| Spring Cloud Stream's `@Bean` conjunct | registration is unmeasured | probe rank 3 |
| `@ServerEndpoint` with no `@OnMessage` | a real served endpoint deriving nothing | probe rank 4 |
| Spring RSocket published as `websocket` | `@MessageMapping` is also RSocket's routing annotation and an RSocket controller IS a `@Controller`; behaviour unverified | probe |
| `A-M14` — Spring Data CRUD exclusion by **name** where the framework compares a signature | needs typed CRUD signatures per store plus `getMostSpecificMethod`'s type-variable resolution; the facts support neither | fact-stream change |
| `RouterFunctions$Builder` (7 verbs x 4 overloads) and the Kotlin `router` DSL (7 x 5) | undeclared, unmentioned in docs/catalogs/probes | catalog + measurement |
| Apache CXF (`A-Mi7`) | unmeasured | probe |

### C. Class A Minors — 23 open

Mostly stale prose, several of them ours from this week. Full list and evidence
in `docs/principles-sweep-2026-09-05.md`. **Fold into 2O Task 12's
documentation sweep** rather than running as a separate pass — they are the
same kind of work.

### D. Class B — 34 rows, documents describing an unbuilt system

Measured, not estimated: 6 base tables exist where D01 documents twelve plus
`edges`, `dispatch`, `trace_summary`, `findings` and a full-text index; D01 §5's
ten named queries appear nowhere in `src/`; 4 of M00's 25 CLI verbs exist; 8 of
D00's 15 fact kinds have a producer; the overlay tier is absent.

Per GUIDELINES §2 this is debt to be **addressed**, not dropped — retire-and-mark
is the expected outcome for most, taken deliberately and recorded.

Three of its rows are operational and already reclassified into Class A:
`ARCHITECTURE.md:341`'s redaction claim, the two documented config files that
abort every command, and `.sextantignore` loading at the module root.

### E. The per-catalog pass — 52 catalogs

Measurement and near-miss coverage merged into one pass per catalog, ruled
2026-09-05: **31 catalogs unmeasured, 33 with no declining test**, and both
questions need the same jar open. This is where B's residual probes run.

### F. Structural work found 2026-09-05 — prerequisites

**F1. Capture RESOLVED dependencies, with versions. (S, prerequisite for F5, F7,
and version-awareness generally.)**
`ModuleFact.dependency_coordinates` is `groupId:artifactId` only, and Maven
records **direct declarations only** — `mall-admin` declares five coordinates and
none of them is Spring. `classpath` is empty for Maven. Consequences, all live:
- `DEPENDENCY_GATED` is `{derived_resource, config_join}`; a Spring Cloud Stream
  module inheriting its starter from a parent POM is **skipped today**. Widening
  the gate further makes this worse.
- No version means no `measured:` scope (F5), no Jackson 2/3 discrimination
  (F7), and no answer at all for a *broad* framework divergence.

**F2. Extract the JSON shape model into its own catalog. (M, prerequisite for
F7.)**
`@JsonProperty`, the wire-type table and the nullability rules are **duplicated
across 42 catalogs**. Sweep 2's `A-C2` is the consequence: the `Void` mapping
replicated in 28 with **9 missing the repairing entry**, so `ResponseEntity<Void>`
publishes a bogus object shape in nine frameworks. A Jackson 2/3 split on the
current shape would mean 84 copies.

**F3. The javax/jakarta gaps. (M, needs F4 for one of them.)**
Measured today. Spring's own annotations never moved, so MVC/WebFlux/Feign/
Kafka/Rabbit work across Boot 2.x, 3.x and 4.x. These do not:

| surface | Boot 2.x (`javax`) |
|---|---|
| JMS (`jakarta-jms.yml`) | **derives nothing** |
| SOAP outbound identity (`spring-ws-template.yml`, `jakarta.xml.bind`) | operation name lost |
| WebSocket (`jakarta-websocket.yml`) | detection-only — recognised, derives nothing |

Servlets and SOAP endpoints already ship both spellings.

**F4. Multi-valued annotation vocabulary. (M, blocks F3's WebSocket half.)**
`mapping.prefix_annotation` is SINGLE-valued, so one catalog cannot name both
spellings. Engine work, neutral vocabulary. Same shape as the `matches.owner`
single-value limit the descriptor sweep hit.

**F5. A `measured:` block on the catalog schema. (S, needs F1.)**
There is no version field on `Catalog` and none in D02's grammar. 32 of 52
catalogs state no version; the 20 that do state it in comments nothing enforces.
A catalog silently claims a rule for every version on evidence from one — and
rules move (`isHandler` lost a disjunct; `WebClient.exchange` exists at 6.1.6 and
is **removed** at 7.0.2).

**F6. Boot 2.x and Boot 4.x acceptance projects. (M.)**
Boot 3.x is proven (mall). Nobody has run Sextant against a Boot 2.x or Boot 4.x
application. F3's table above is derived from catalog contents, not from a run.

**F7. Jackson 2 vs Jackson 3. (M, needs F1 and F2.)**
Measured today: `tools.jackson.core:jackson-databind` (3) vs
`com.fasterxml.jackson.core:jackson-databind` (2) — different groupId, so the
coordinate discriminates. But `@JsonProperty` **kept its exact FQN**, so the
javax/jakarta trick (sibling catalogs told apart by FQN) does not work. Where no
discriminator is available the honest answer is `narrowed` or an open question,
never a guess.

### G. 2Q — the full request-to-response trace

Scope and evidence in the roadmap (`6668ee0`). Five pieces:

| | what | size |
|---|---|---|
| G1 | Lambda bodies — record `bootstrapMethodArguments[1]` instead of the factory. **Proven recoverable** | S |
| G2 | Record the value id `ARETURN` pops. The value chain already exists — 993 of 1817 arguments carry a `source` | S |
| G3 | Cross-method return propagation — link a callee's return to the caller's `result` id | **L — the real work** |
| G4 | `call_edges` table plus bounded, cycle-refusing traversal | M |
| G5 | Interface dispatch: sole in-module implementer resolves, several list as a branch. **The branch rule has never run on real code** | M |

### I. Roots as first-class — ruled 2026-09-05, user

**The user's point, and it corrected my scoping.** A `@Scheduled` method contains
business logic, starts work, and deserves a trace and a sequence diagram exactly
as an HTTP endpoint does. I had scoped 2Q's traces from ENDPOINTS only — 159 of
160 — and that is wrong.

`CONTEXT.md` already settles the modelling, and it is why a `timer` protocol is
the wrong mechanism:

> **Root**: the kind of thing a trace starts from — an inbound endpoint, **a
> scheduled job**, or a program entry point.
> **Endpoint**: a place where something enters or leaves a process… **Protocol is
> a property of an endpoint.**

A scheduled job is a **Root but not an Endpoint**. Adding `timer` to the protocol
closed set would put a non-endpoint into the endpoint model: `endpoints`'
identity is `(protocol, direction, method, path)` and a cron job has no method
and no path; it is neither `inbound` nor `outbound`; and `Link` is defined as a
matched pair of one module's outbound endpoint and another's inbound — **a timer
can never link, so it would be a protocol that cannot do the one thing protocols
exist for.**

Four pieces, and only the first is paperwork today:

**I1. A `root_kind` producer. (M — promoted OUT of Class B.)**
D00 §4 documents `root_kind` with a `scheduled` member and **nothing produces
it** (sweep 3; `engines/scheduled_work.py:12-18` says so in its own docstring).
Building it is what makes a scheduled method a first-class root rather than a
table nobody traces from. Members: inbound endpoint, scheduled job, program
entry point.

**I2. Quartz. (M — new catalog, currently ZERO support.)**
`grep -rl quartz src/ docs/` returns nothing. Spring's `@Scheduled` is not the
only scheduler in real estates; Quartz `Job`/`JobDetail`/`Trigger` and
`@DisallowConcurrentExecution` are a separate surface with its own root shape.
Measured like any other catalog in the per-catalog pass — **`@Scheduled` support
without Quartz is a stated boundary until then, not silence.**

**I3. 2Q traces from every root kind, not just endpoints. (folds into G.)**
G4's traversal takes a root; today every root it has been given is an endpoint
handler. Scheduled jobs and entry points are roots by the same definition and
must produce the same traces and sequence diagrams. **This widens 2Q and was
missing from its scope.**

**I4. A root section the LLM can fill. (S, needs I1.)**
`domain/closed_sets.Anchor` is a **closed set of four** —
`after-component-overview`, `after-endpoint-table`, `beside-open-question`,
`end-of-document` — with nowhere to attach a claim about a root. Needs a fifth
member (NFR-5 amendment, versioned with its estate cost), the brief's
`_ANCHOR_LINES`, INSTRUCTIONS.md and the overlay validation.

**The hard line on I4, stated so it is not softened later:** the LLM describes
what a *derived* scheduled job does — an Overlay at `evidence: llm`, which
"never produces facts and never overrides evidence silently". It does **not**
fill an EMPTY section. If we found no scheduled work, `None found.` is the
content; asking a model to write something there is exactly how fabrication
enters.

### H. Quality and infrastructure debt

- **mall is scratch.** If it is the acceptance corpus it needs a committed
  clone-and-build script with a pinned commit, not committed source.
- **`mall-portal` never built** — the reactor stopped after `mall-admin`, so every
  number is from one module.
- **The negative-claim ratchet.** Sweep 2 inventoried 53 distinct negative claims
  in the tree; **3 cite evidence, 9 are false**. A comment asserting a boundary
  is a claim nothing checks.
- **The probe-symbol check.** A probe that names a framework predicate it never
  measured is an unanswered question in plain sight — `isCustomMethod` sat in
  CP-13's own table for a full round and cost a Critical. Greppable.
- **Cross-module linking (`Bundle`/`Link`).** 1,041 of `mall-admin`'s calls leave
  for sibling Maven modules. Harmless where a mapper is the terminal; a service
  delegating real logic to a sibling module stops early and we would not know.

---

## Recommended order

### Stage 1 — close 2O (A + C, and B's cheap half)

**Why first: GUIDELINES §2, which the user wrote today.** Six open tasks in a
phase is exactly "half-baked", and Task 12 is a documentation sweep that the 23
Class A Minors belong inside. Closing 2O also retires Task 13, which is the only
thing making capabilities 9.15/9.16 visible in output.

Deliverable: 2O complete, Minors closed, a phase that is done rather than parked.

### Stage 2 — the prerequisites (F1, F5, F2)

Small, and each fixes a live defect as well as unblocking later work:
- F1 stops the dependency gate skipping modules that inherit their starters.
- F5 makes a catalog say which version it was measured against — the condition
  under which every rule in the estate is true.
- F2 removes 42 duplications and makes `A-C2`'s nine-catalog defect structurally
  impossible.

**These are prerequisites for anything version-aware. Doing them after Boot 4
support would mean doing Boot 4 support twice.**

### Stage 3 — 2Q, the traces (G1-G5)

The thing this project has been asked for since day one, and the missing half of
what `CONTEXT.md` promises. Feasibility is proven on real code, not argued:
158 of 160 endpoints reach a real terminal, 98% of scanned-class calls resolve,
180 interface calls resolve to a sole implementer.

Order within the stage: G1 and G2 first (small, and G1 recovers business logic
that is invisible today), then G3, then G4/G5. **I1 and I3 land here too** —
a traversal that only accepts endpoint roots would have to be reopened, and
`root_kind` is what tells it what else to start from.

**Acceptance is `mall`, so output is judged against source rather than against a
report.** Requires H's clone-and-build script and `mall-portal` built.

### Stage 4 — the per-catalog pass (E, plus B's residual probes and F3/F4)

One pass per catalog: measure the framework rule at a pinned version, record it
in the `measured:` block F5 added, write the declining test, and run the residual
probes B lists. F3's javax gaps, F4's multi-valued vocabulary and **I2's Quartz catalog** land
here because they are the same reading.

**Sized as build work that produces defects, not as a review pass.** The Spring
Cloud Stream fabrication survived every review it had and died the moment
somebody asked what the catalog does when it should NOT match.

### Stage 5 — the documentation debt (D), and I4

**I4** (the root anchor and the enrichment prompt) lands here rather than in
Stage 3: it needs I1's roots to exist and it is a rendering/enrichment change,
which is what this stage already touches.

### Stage 5 continued — the documentation debt (D)

Built / designed / retired, for ~34 rows. Cheap, deliberate, recorded. It moves
after Stage 4 on the user's ruling of 2026-09-05: confidence in the output
matters more than honest documents about it.

### Stage 6 — multi-version support (F6, F7)

Boot 2.x and Boot 4.x acceptance projects, then the Jackson 2/3 shape catalogs
that F2 made a two-file change. Last because it is the only stage that needs all
of F1, F2 and F5 in place.

### Running alongside — H

The mall harness and `mall-portal` are needed by Stage 3 and should land with
it. The negative-claim ratchet and the probe-symbol check are cheap and belong
wherever there is slack; neither blocks anything.

---

## Explicitly NOT in scope

- **Tracing into MyBatis, Spring Data, or any third party.** The call is the
  terminal. We do not read MyBatis XML, so a terminal is
  `OmsOrderMapper#selectByExample`, never a table or a statement. **Ruled.**
- **Per-version catalog FILES.** A rule that is added or removed between versions
  needs no version constraint — code built against the other version cannot call
  it. Only a *semantic* change to the same declaration does, and that is rare
  enough to be a per-row constraint rather than a duplicated file.
- **Execution paths.** A trace is reachability. Two return statements yield a set
  of possible responses, not the one that runs.
- **AOP, interceptors and `@Transactional`** — applied to runtime proxies,
  absent from the call graph.
- **Second languages.** 2J (Micronaut, Quarkus, MicroProfile) is unaffected by
  this plan and unchanged in the roadmap.
