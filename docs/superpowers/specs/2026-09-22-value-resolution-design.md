# Value resolution: one backward walk, instead of one hop per catalog

**Status:** design. Brainstormed and approved section by section, 2026-09-22, after the Group D
branch (PR #36) closed and its post-merge audit found the cause behind six of its own recorded
boundaries. Not yet planned.

**What it closes:** `OI-124` (a Temporal module that registers its workers in code derives nothing),
`OI-126` (a consumer handed across methods), `OI-110` (a container built two beans away), the
Vert.x 5 builder tail, Quartz's two-chain join, and — with the fifth edge — `akka-pekko-actors`,
which COVERAGE tiers **C, possibly permanent** for exactly this reason.

**What it is not:** a new subsystem. Four of the five edges it walks are already emitted as facts,
and one of them, `return_flows`, is already computed into a table that **no engine reads**.

---

## 0. The measurement this rests on

Run on the repository as it stood at `50d3f6e`. Every number is a count, not an estimate.

| finding | count |
|---|---|
| modules that follow a `source` id (the "this value came from that call" fact) | **6**, in 20 places |
| modules that state **"one hop"** as an explicit cap | **7**, in 18 places |
| `return_flows` rows on `mall-admin` — built, populated, read by no engine | **552 call sites / 566 returns** |
| multi-hop follows in the whole resolve layer | **1** — `fluent`'s chain walk, and it runs *forward* from a declared root to a declared terminal |
| per-catalog hop declarations | **16**, across 14 catalogs (`channel_via` ×13, `url_via` ×2, `call_wrappers` ×1) |

**The conclusion those numbers force:** there is no operation in this codebase that answers *what is
this value?* There is only *follow exactly one hop, in the direction a catalog named.*

### 0a. What that cost, historically

Every framework that put a value one hop further away than a catalog could reach was answered with a
**new catalog word**, not a new hop: `channel_via`, then `url_via`, then `type_carriers`, then
`call_wrappers`, then `getters`, then `indexed`, then `compose`. Group D nearly added two more —
`contract` and `argument_chain` — and both were cut in review, which is the only reason the count
is seven and not nine.

Each of those was a correct local decision. Together they are the disease: distance is described
per catalog, so it is re-described every time, and capped every time.

### 0b. A correction this design is built on, made three times before it stuck

**`channel_via` is not pure distance, and two earlier drafts of this argument claimed it was.**

```yaml
channel_arg: 0
channel_via: { owner: jakarta.jms.Session, method: createQueue, arg: 0 }
```

for `session.createProducer(session.createQueue("raw-audit"))`. A backward walk from argument 0
reaches the `createQueue` call and is then **stuck**: the value is a `Queue` object, and nothing in
the facts says what string identifies a `Queue`. Only framework knowledge does.

So `channel_via` welds two statements together — *"it is over there"* (distance; the walk replaces
this) and *"and argument 0 of that call is what identifies it"* (**meaning; DR-6 says this stays
catalog data**).

The general lesson, recorded because it was learned expensively: measuring a key's **syntax** —
that it is repeated across catalogs — does not establish its **semantics**. The check that catches
it is reading what the key's `arg` is *for*, and it costs a minute.

---

## 1. Edges, answers, and what `unresolved` is allowed to mean

### 1a. The edge table

One pass builds `value_edges` once per resolve, linear in the facts. An edge says only *where a
value came from*:

| kind | from | to | fact behind it |
|---|---|---|---|
| `produced_by` | (method, value id) | a call site in that method | `source` — **exists** |
| `returned_by` | (method, value id) | a callee symbol; read its returns | `return_flows` — **exists, unread** |
| `read_from_field` | (method, value id) | a field symbol | field-kind arguments — **exists** |
| `written_by` | a field symbol | (method, value id) | `field_write` — **exists for constructors only; §4 extends it** |
| `bound_to_parameter` | (method, value id) | (method, parameter index) | `call_edges` — **exists** |
| `names_declaration` | (method, value id) | a declaration symbol | class literals, bean references — **exists** |

Six kinds. Five need no extractor work at all.

### 1b. The answer

```
resolve_argument(site, index) -> list[Answer]
resolve_receiver(site)        -> list[Answer]
```

An `Answer` is one of:

- **`literal(text)`** — a string the code states
- **`expression(text)`** — a `${…}` or composed expression, carried **verbatim and never evaluated**
  (§8.2 keeps this repository out of guessing deployed values)
- **`unresolved(reason)`**

### 1c. Multiplicity — one row per real answer

**Approved ruling.** A position with several *enumerable* answers returns several, and each becomes
its own row:

```java
String queue() {
    if (highPriority) return "orders-fast";
    return "orders";
}
factory.newWorker(queue());          // two answers, two rows
```

This follows the facts layer rather than departing from it: `method_return` already keeps several
returns as several facts, on the stated ground that *"picking one would be a fact about code that
may never run"*, and varargs already yield one row per element.

**The line it draws:** *enumerable multiplicity* yields several answers; *non-enumerable ambiguity*
yields one `unresolved`. That is D00's array rule generalised — an array whose every index is a
distinct written constant yields its elements; one built in a loop, populated on a branch, left
partly unwritten, or handed to another method first is `unresolved` with no element list at all.

### 1d. The `unresolved` reasons

A closed set. Each names a different thing a reader can act on:

| reason | means |
|---|---|
| `not_readable` | the producer is there; its value cannot be named (today's bare `unresolved`) |
| `non_enumerable` | a loop, a branch-merged value, a partly-written array |
| `escapes` | the value reached a method that might mutate it before use |
| `no_writer` | a field nothing in this module writes |
| `external` | the producer is outside what was scanned — a dependency jar |
| `cycle` | the walk returned to a position it had already visited |

`fan_out` and `depth` are **deliberately absent** — §3a decides whether they are ever needed.

Today every one of these collapses into one word, so COVERAGE can say only *"unresolved"* and a
reader cannot tell *"we cannot see the jar"* from *"the code branches"*. Six reasons make a miss
diagnosable, which is what turns a boundary into a work item — **but only if something records
them**, which §3d requires.

### 1e. The line that does not move

**The walk answers what a value is. The catalog still says what it means.** `channel_arg: 0`
continues to say *this position carries the destination*; the walk simply stops needing
`channel_via` to add *and it is one hop that way*. DR-6 is untouched.

---

## 2. What the hop keys become

Hop declarations do not vanish. They **deduplicate and relocate**, for §0b's reason: the identity
half is framework knowledge.

Today each consuming catalog re-declares how to identify a producer's value. Instead, one shared
model — `value-models/`, beside the shipped `bean-models/` and `step-models/` — declares it once per
producing method:

```yaml
# value-models/jms.yml
identified_by:
  - { owner: jakarta.jms.Session, method: createQueue, arg: 0 }
  - { owner: jakarta.jms.Session, method: createTopic, arg: 0 }
```

and every consuming catalog says only `channel_arg: 0`. The walk follows as many hops as it takes,
consulting the model whenever it lands on a produced value.

**The honest accounting:**

- **deleted** — 16 per-catalog hop declarations, the one-hop cap, the `*_via` shape validation in
  three engines; and `argument_chain`/`contract` are never written
- **relocated** — the identity statements, declared once each instead of once per consumer
- **gained** — unbounded hops, and a framework whose value hides N hops away needs **no new word**,
  only an `identified_by` entry if its producer is novel

### 2a. What each engine keeps

| engine | today | after |
|---|---|---|
| `single_call` | `channel_of`, then `linked_channels` if unresolved, capped at one hop | `resolve_argument` |
| `interface_implementation` | its own copy of the same | `resolve_argument` |
| `fluent` | chain walk **plus** `_address_read`, `_literal_of`, the bean-chain fold | chain walk **stays**; value reads inside it call `resolve_argument` |
| `annotation_driven` | declaration-side; reads no call values | unchanged |

**`fluent` keeping its chain walk is the point.** The walk answers *what is this value*; the chain
walk answers *which calls form one boundary*. Different questions — and conflating them is what
produced `bean_via`.

---

## 3. Data flow, the measurement gate, and sequencing

### 3a. The measurement is a gate, not a report

**Approved ruling: no cap in v1.** This is the task that makes that safe, and **nothing consumes the
walk until it passes**:

1. Build `value_edges` and the walk. **No engine calls it.**
2. Measure on the largest corpus available (`mall-admin` — 48 MB of facts, 648 documents) plus every
   fixture: for every position a shipped catalog actually asks about — hop count, answer count, wall
   time. Report the **distribution, the maximum and the tail**, never the mean.
3. **Ruling point.** The data either says no cap is needed or names the cap and its reason. If it
   names one, `fan_out` and `depth` join §1d then and not before.
4. Only then does migration begin.

### 3b. Where it runs

Beside the tier that already exists for derived edges, before `derive_endpoints`:

```
facts → call_edges, return_flows → value_edges → derive_endpoints (engines resolve) → …
```

Reset ahead of any writer, on the `endpoint_metadata_reset` discipline. The walk builds an index
over the table once per resolve and memoises answers per position (`Workspace.once`).

**Why the edges are materialised and the closure is not:** under §1c and §3a the closure is
potentially unbounded and multiplicative, and materialising it is the one thing that could make a
resolve unusable. The edge table cannot explode — it is linear in the facts — and the on-demand walk
explores only what a catalog asks about. On `orders-quarkus`, eight catalogs declared
`metadata_from` and **zero** annotation walks ran; the same guard shape applies here.

### 3c. Migration, one engine at a time, each measured alone

Per migration: run the analysis before and after and diff **every column** of `endpoints`,
`endpoint_metadata` and `shapes`.

- `unresolved` → resolved is the win, and **each one is read** — a newly resolved value is a new
  claim, and a wrong one is a fabrication.
- **Any other movement stops the migration** and is a finding.
- The e2e pins move in the same change, never a later one.

Order: smallest pinned surface first — `interface_implementation` (one catalog), then `single_call`'s
thirteen, then `fluent`'s. The first migration should be the cheapest place to discover the walk is
wrong.

### 3d. Where the `unresolved` reasons live

§1d's vocabulary is decoration unless something records it. A small `value_resolutions` table is
written **only** for positions a catalog asked about and failed to resolve — bounded by what
catalogs ask, not by the facts. COVERAGE's boundary statements are generated from it rather than
hand-written, and a catalog author debugging a NULL address can query *why*.

---

## 4. The fifth edge, which is extractor work

`written_by` beyond constructors — a field assigned anywhere but `<init>` — is the only edge with no
fact behind it. D00 states the current limit plainly: `field_write` is *"constructors only, direct
traces only"*, and setter injection is *"a named gap, not an omission"*.

It is ASM work in `extractor-jvm/`, with its own capability number, its own probe and its own
fixture, and it **must land and be measured before the edge it feeds is wired**. A wrong field-write
fact fabricates silently everywhere, which is why it runs on its own track rather than inside a
resolve-layer migration.

It is what closes `akka-pekko-actors`: an `ActorRef` obtained in one method and told in another is
the shape, and COVERAGE's *"possibly permanent"* tier is a statement about this missing fact rather
than about actors.

---

## 5. Scope boundaries

Stated so nothing is assumed:

- **It does not decide what a value means.** `identified_by` is framework knowledge with a probe
  behind every entry.
- **It is not a points-to analysis.** No heap modelling, no collection contents, no dynamically
  indexed array elements. It follows *declared* edges; everything else is `unresolved`.
- **It does not cross the module boundary.** A producer in an unscanned jar is `external`.
- **It does not resolve configuration.** `${…}` is carried verbatim; `resolved_config` still owns
  substitution.
- **It does not change linking.** A resolved value is a value; whether two rows link stays the
  linking tier's business.
- **It does not touch `fluent`'s chain walk** (§2a).
- **No reflection, no dynamic proxies, no computed strings.** A concatenation stays `unresolved`.

---

## 6. The risk, and the mitigation that is part of the design

Everything this project does rests on *misses are acceptable, fabrications are not*. **This work's
entire purpose is to convert misses into answers** — so every conversion is a new assertion, made at
scale, across fourteen shipped catalogs at once.

That is inverted from every other change in this repository. Group D's risk was *"we might not derive
something"*. This one's is *"we might now derive something wrong, in fourteen places, and the tests
will go green because the rows are new."*

§3c's diff catches **movement**. It does not catch **wrongness** — a wrong address looks exactly like
a right one in a diff.

### 6a. Shadow mode

The walk runs and writes what it *would* resolve into §3d's `value_resolutions` table **without
publishing it**. Every candidate conversion is reviewable as data, on the real corpus, before a
single row changes; then each migration flips one engine and its diff is already known.

It costs one flag, and it converts *"review fourteen catalogs' worth of new claims under time
pressure"* into *"read a table."* **This work should not proceed without it.**

### 6b. The second risk

`value-models/` becomes a dumping ground — entries accumulate because adding one is easy, and nobody
measures whether the framework really identifies that value that way. The mitigation is the rule
this codebase already enforces everywhere else: **every `identified_by` entry carries its probe
row**, checked by the architecture suite exactly as `measured:` blocks are.

---

## 7. Testing

- A fixture arm **per edge kind** and **per `unresolved` reason** — including the negative ones,
  which are the point: a loop-built array, a branch-merged value, a field with no writer, a value
  from an unscanned jar, a cycle.
- **Mutation guards on the two rules that carry the whole design**: termination, and
  enumerable-versus-ambiguous. If either can be broken without a test failing, the
  no-false-positives guarantee is unpinned.
- The migration diffs of §3c are the real test of correctness; the unit tests are the test of the
  walk.

---

## 8. Self-review

**Placeholder scan.** None. Every count in §0 is measured at `50d3f6e`; every edge in §1a names the
fact behind it; the one edge without a fact is §4 and says so.

**Internal consistency.** §1c's multiplicity ruling is what forces §3b's "materialise edges, not the
closure" and §3a's measurement gate — checked in both directions. §1d's reason vocabulary is used by
§3d and by nothing else, which is why §3d exists. §2's accounting matches §0's count of 16
declarations.

**Ambiguity.** The one term that could be read two ways is *enumerable*, so §1c defines it against
D00's array rule rather than leaving it to judgement.

**Scope.** This is one subsystem with one new fact. §4 is separable and explicitly on its own track;
if it slipped, §§1–3 still close five of the six boundaries.

**What the review did not settle, and the plan must.** The order in which `value-models/` entries are
written for the 14 migrating catalogs — whether each migration writes its own, or whether they are
extracted up front from the existing `channel_via` declarations. The second is mechanical and
probably right, but it is a plan decision, not a design one.
