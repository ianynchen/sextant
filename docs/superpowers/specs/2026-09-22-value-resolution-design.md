# Value resolution: one backward walk, instead of one hop per catalog

**Status:** design. Brainstormed and approved section by section, 2026-09-22, after the Group D
branch (PR #36) closed and its post-merge audit found the cause behind six of its own recorded
boundaries. **Rewritten after an adversarial self-review** whose two Major findings the user ruled
on (§0c). Not yet planned.

**What it closes:** the Vert.x 5 builder tail and Quartz's two-chain join.

> **This list was longer, and four of its claims are WITHDRAWN — measured at Task 13,
> 2026-10-17, after Tasks 1-10 shipped.** It read: *"`OI-124` (a Temporal module that
> registers its workers in code derives nothing), `OI-126` (a consumer handed across
> methods), `OI-110` (a container built two beans away) … and — with the fifth edge —
> `akka-pekko-actors`, which COVERAGE tiers **C, possibly permanent** for exactly this
> reason."* All four are still open, each for a reason this design does not address:
>
> * **`OI-124`** needs one engine to attach a value read at a CALL SITE to a row another
>   engine derived from a DECLARATION. That entry said *"No such cross-engine attachment
>   exists"* before this spec was written, and this spec does not build one.
> * **`OI-126`** loses a chain's ROOT, not a value. A backward value walk cannot supply a
>   root; `engines/fluent.py` still keys every chain on one method body.
> * **`OI-110`** fails on a bean-graph hop, not a value edge: a `@Bean` method's parameter
>   is bound reflectively by the container, so there is no call site and no
>   `bound_to_parameter` edge to cross. Measured — the queue literal one bean away answers
>   `would_resolve` while the parameter that needs it answers `external`.
> * **`akka-pekko-actors`** is falsified by probe row 7 — see §4, corrected in place.
>
> The three OI entries carry the measurement. Recorded here rather than silently shortened,
> because this line is the one a reader checks the work against.

**What it is not:** a new subsystem. Five of the six edges it walks are already emitted as facts,
and one of them, `return_flows`, is already computed into a table that **no engine reads**.

**Standing requirements.** **No false positives** (user rule): every ambiguity is an `unresolved`
answer with a stated reason, never a guess. The resolve layer names no framework and no language.
**This design must hold when a second language backend and a tenth framework arrive** — §5 is where
that is enforced rather than hoped for.

---

## 0. The measurement this rests on

Run on the repository as it stood at `50d3f6e`. Every number is a count, not an estimate.

| finding | count |
|---|---|
| modules that follow a `source` id ("this value came from that call") | **6**, in 20 places |
| modules that state **"one hop"** as an explicit cap | **7**, in 18 places |
| `return_flows` rows on `mall-admin` — built, populated, read by no engine | **552 call sites / 566 returns** |
| multi-hop follows in the whole resolve layer | **1** — `fluent`'s chain walk, and it runs *forward* from a declared root to a declared terminal |
| per-catalog hop declarations | **19**, across 19 catalogs (`channel_via` ×13, `url_via` ×2, `record_wrappers` ×3, `call_wrappers` ×1) — 79 declaration sites |

*The hop-declaration row read **"16, across 14 catalogs (`channel_via` ×13, `url_via` ×2,
`call_wrappers` ×1)"** until 2026-09-23. **The enumeration omitted `record_wrappers`**, which is
`{type, <name>_ctor_arg}` — the same shape as `call_wrappers` — and which three catalogs declare
(`kafka-clients`, `spring-kafka-replying`, `spring-kafka-template`), each a byte-identical entry for
`ProducerRecord`'s constructor. The row is corrected above rather than silently renumbered: the count
was not a measurement that moved, it was an enumeration that was short by a key. The "14 catalogs"
half was wrong on its own terms too — no catalog declares two of these keys, so 16 pairs could only
ever have been 16 catalogs. Re-derived at this section's own snapshot `50d3f6e` by a walk of all 101
shipped catalogs for the four keys, which reproduces every other figure in the row. **The
undercount was already contradicted inside this document**: §3c's migration table gives `single_call`
**13 catalogs**, and that 13 only reaches 13 because it counts the three that declare
`record_wrappers`. Ruled 2026-09-23 (Task 6): `record_wrappers` is hoisted with the other three, and
Task 10 deletes and refuses four keys, not three.*

*§7's **"fourteen"** was corrected to **nineteen** one round later. The first round left it alone,
reading it as the tasks 7 and 8 migration surface (1 + 13), which §3c's table does make
self-consistent. That reading lost, and the reason is worth keeping: §7's own sentences scope the
figure to the WHOLE work — "this work's entire purpose is to convert misses into answers … across
fourteen shipped catalogs", and §7a's "review fourteen catalogs' worth of new claims" — and the whole
work migrates all three engines, which is 1 + 13 + `fluent`'s 5. A figure that silently excludes
`fluent` is not what those sentences say, whatever arithmetic reproduces it.
`resolve/shadow.py`'s copy of the sentence is corrected with them.*

**The conclusion those numbers force:** there is no operation in this codebase that answers *what is
this value?* There is only *follow exactly one hop, in the direction a catalog named.*

### 0a. What that cost, historically

Every framework that put a value one hop further away than a catalog could reach was answered with a
**new catalog word**, not a new hop: `channel_via`, then `url_via`, then `type_carriers`, then
`call_wrappers`, then `getters`, then `indexed`, then `compose`. Group D nearly added two more —
`contract` and `argument_chain` — and both were cut in review, which is the only reason the count is
seven and not nine.

Each was a correct local decision. Together they are the disease: distance is described per catalog,
so it is re-described every time, and capped every time.

### 0b. A correction this design is built on, made three times before it stuck

**`channel_via` is not pure distance, and two earlier drafts claimed it was.**

```yaml
channel_arg: 0
channel_via: { owner: jakarta.jms.Session, method: createQueue, arg: 0 }
```

for `session.createProducer(session.createQueue("raw-audit"))`. A backward walk from argument 0
reaches the `createQueue` call and is then **stuck**: the value is a `Queue` object, and nothing in
the facts says what string identifies a `Queue`. Only framework knowledge does.

So `channel_via` welds two statements together — *"it is over there"* (distance; the walk replaces
this) and *"and argument 0 of that call identifies it"* (**meaning; DR-6 says this stays catalog
data**).

The general lesson, recorded because it was learned expensively: measuring a key's **syntax** — that
it is repeated across catalogs — does not establish its **semantics**. The check that catches it is
reading what the key's `arg` is *for*, and it costs a minute.

### 0c. What the adversarial review changed

| # | Finding | Ruling |
|---|---|---|
| M-1 | Resolving positions **independently** across a method boundary mints combinations no code path produces: a helper called as `register("orders", OrderImpl)` and `register("billing", BillingImpl)` yielded 2×2 = four rows, two of them fabricated at `resolved` | **The unit of resolution is the PATH, not the position.** The user's correction: *"it's not 2×2, it's 2 paths — record two paths, because that's the reality."* §1c rebuilt around it; incoherent combinations become structurally impossible rather than contractually forbidden |
| M-2 | §2 deleted the hop declarations of every catalog that carries one (19 across 19 — the corrected count under §0's table; "16 across 14" as this row originally read), putting all their output in a new walk's blast radius — where the existing declarations already contain exactly what the new model needs | **Hoist, then delete, then refuse.** The loader reads existing hop declarations as identity entries (no catalog edit forced, nothing breaks); the declarations are then deleted and the keys made invalid. Chosen on the "which design holds when the tenth framework arrives" test: leaving two ways to say one thing guarantees new catalogs copy the old one |
| I-3 | `return_flow.py` and `call_edges.py` read **raw** `call_sites`, bypassing the projection that re-targets `$default` bridges and class-compiled lambdas | §1a names the projection each edge is built over; `effective_call_sites` is the only one the walk rides |
| I-4 | `value_edges` was specified as a new materialised table, duplicating data three existing tables already hold | It is a **view** (§3b) |
| I-5 | `identified_by.owner` was required; `field` named an OO concept; the fifth edge was specified as "ASM work" | All three made language-neutral (§5) |

### 0d. What building the walk changed (Task 3, ruled 2026-09-23)

Three answers the vocabulary could not spell, each found by implementing §1b against the
fact grammar rather than by reading it again. Same voice, same table, because they are
corrections of the same kind — a shape the design named in prose and had no word for.

| # | Finding | Ruling |
|---|---|---|
| T-1 | §6's "a concatenation stays `unresolved`" read against §1b's `expression`, which exists for "a composed expression, carried verbatim". Discarding the template would also make the `produced_by` arm's fix pointless — it was re-pointed at `call_sites` precisely so a concat site is reachable | §6 refuses the **evaluation**, never the template. A concatenation is an `expression` carrying its template with the holes unfilled, and no hole is ever filled in. §6's bullet amended |
| T-2 | An explicit `null` and a **zero-length** varargs call had no answer: §1b admits a literal, an expression or a reason, so both came back as a miss — and D00 §5 says the opposite in as many words, that "the empty list is the fact ... 'called with no values' is a different statement from 'the array could not be read'" | `Answer.kind` gains **`absent`** — *the code states there is no value here*. A RESOLVED answer, distinguishable from both a literal and every reason. Calling a known-empty call ambiguous contradicted the facts it was read from |
| T-3 | A declaration reference (`OrderWorker.class`) IS the value and the answer must carry the symbol; carried as a `string` literal, a catalog reading a destination out of that slot publishes `com/acme/OrderWorker#` as an address — a wrong row at `resolved`, which is §7's whole risk | `literal_kind` gains **`symbol`**. The `kind` set is untouched: it is the literal vocabulary that grew, and a consumer wanting text still tests for `string` |

The fix round on the same task added three more. T-5 **reverses a ruling this document's own
Task 2 made** — that the edge query's raw slot numbering was a boundary for §3a to size. It
was not a boundary; it was a wrong answer, and those are fixed when they are identified.

| # | Finding | Ruling |
|---|---|---|
| T-4 | §1d defines `no_writer` as "a binding nothing in this module writes", which is not what it can mean while `written_by` has no producer — a reader would take today's answer for a property of the code | The row says both: what it will mean, and that today it means *no writer edge exists to follow*. The code says the same at the constant and at the function |
| T-5 | `bound_to_parameter` pairs a **projected callee** with a **raw slot index**. A walk reading raw `call_sites` was handed the bridge's leading receiver for the sibling's parameter 0 — a type symbol where a string belongs, IN RANGE, so nothing caught it — and answered a defaulted parameter with the value the bridge pushed | The walk reads `effective_call_sites`, which puts the callee and the argument list on one row: parameter *p* is slot *p*, and the edge's index only SELECTS which sites bind a parameter. Measured both ways on the canonical bridge shape. §3a sizes no boundary here because there is none left |
| T-6 | `escapes` did not survive a return crossing: a value mutated inside a callee before its `return` resolved to the pre-mutation literal — byte for byte the shape the rule exists for (`result.setFilename(x); return result;`), one method along | A return has no position in control flow to bound the window with (`method_returns.ordinal` numbers return instructions), so the CLASS is refused: any call on the value after its producer. **MEASURED across every fixture with compiled classes: 112 of 836 returned values carrying a source, 13.4%; 33 of 413 on `orders-service`.** A miss is the acceptable half of the trade; a stale value asserted at `resolved` is not |

---

## 1. Edges, paths, and what `unresolved` is allowed to mean

### 1a. The edges

Six kinds. Each names the fact behind it **and the projection it is built over** — I-3's finding is
that this was unstated and the existing tables disagree:

| kind | from | to | fact | projection |
|---|---|---|---|---|
| `produced_by` | (method, value id) | a call site in that method | `source` ✅ | `effective_call_sites` |
| `returned_by` | (method, value id) | a callee symbol; read its returns | `return_flows` ✅ *(unread)* | **must move to** `effective_call_sites` |
| `read_from_binding` | (method, value id) | a binding symbol | binding-kind arguments ✅ | `effective_call_sites` |
| `written_by` | a binding symbol | (method, value id) | `field_write` ✅ *(constructors only — §4 extends)* | extractor |
| `bound_to_parameter` | (method, value id) | (method, parameter index) | `call_edges` ✅ | **must move to** `effective_call_sites` |
| `names_declaration` | (method, value id) | a declaration symbol | type and binding references ✅ | `effective_call_sites` |

Five of six need no extractor work. Two existing tables must be re-pointed at the projection before
the walk can trust them — a fix they need on their own merits, since a Kotlin `$default` bridge is
already invisible to both.

### 1b. The primitive is a site, resolved per path

```
resolve_site(site) -> list[Binding]

Binding = { path, slots: {slot_index: Answer} }
```

One `Binding` per distinct **path** — the chain of calling contexts that reaches the enclosing
method. An engine reads whichever slots it cares about **out of each binding**; it never sees a loose
per-slot set, so it cannot combine across paths.

A `slot` is any position on the call: an argument index or the receiver. **One entry point, not two**
— a receiver is a slot like any other, and splitting them is how a third form gets added later.

An `Answer` is one of:

- **`literal(value, kind)`** — a string, number or boolean the code states. `kind` is carried because
  catalogs already read non-strings (`@ConsumeEvent(local = false)`), and a stringly answer would
  force every consumer to re-infer it. **`kind` also admits `symbol`** (T-3): a declaration reference
  is the value, and carrying its symbol as a `string` lets a destination-reading catalog publish
  `com/acme/OrderWorker#` as an address.
- **`expression(text)`** — a `${…}` or composed expression, carried **verbatim and never evaluated**
  (§8.2 keeps this repository out of guessing deployed values). A concatenation's template arrives
  this way, holes unfilled (T-1).
- **`absent`** — the code states there is no value: an explicit null, a zero-length varargs call
  (T-2). A resolved answer, and distinguishable from every reason, because "called with no values"
  is a different statement from "it could not be read" (D00 §5's own line).
- **`unresolved(reason)`**

### 1c. Paths, not positions — and what multiplicity means

**Approved ruling, as corrected by M-1.** The naive design resolves each position independently and
lets the consumer recombine. That fabricates:

```java
void register(String queue, Class<?> type) {
    factory.newWorker(queue).registerWorkflowImplementationTypes(type);
}
register("orders",  OrderWorkflowImpl.class);     // path A
register("billing", BillingWorkflowImpl.class);   // path B
```

Per-position: `queue ∈ {orders, billing}`, `type ∈ {OrderImpl, BillingImpl}` → four rows, two of
which **no code path can produce**, at `resolved`, indistinguishable from an observation.

Per-path: **two bindings, two rows.** The 2×2 was never reality; it was an artifact of recombination.

So multiplicity has exactly one rule, and it is about paths:

- **Several paths give several bindings** — several callers, several returns in a callee, several
  enumerable array elements. Each is real code, each becomes its own row. This is what
  `method_return` already does by keeping several returns as several facts on the stated ground that
  *"picking one would be a fact about code that may never run."*
- **A single path whose value cannot be enumerated gives one `unresolved`** — a loop, a branch-merged
  value, a partly-written array. That is D00's array rule generalised: every index a distinct written
  constant yields elements; built in a loop, populated on a branch, left partly unwritten, or handed
  to another method first yields `unresolved` with no element list at all.

**Memoisation is per (position, path), never per position.** Memoising per position is precisely what
discards the correlation and reintroduces M-1.

### 1d. The `unresolved` reasons

A closed set; each names a different thing a reader can act on:

| reason | means |
|---|---|
| `not_readable` | the producer is there; its value cannot be named (today's bare `unresolved`) |
| `non_enumerable` | a loop, a branch-merged value, a partly-written array |
| `escapes` | the value reached a method that might mutate it before use. **Across a callee's RETURN the whole tail counts** (T-6): a return has no position in control flow to bound the window with, so any call on the value after its producer refuses |
| `no_writer` | a binding nothing in this module writes — **today: no writer edge exists to follow at all** (T-4), because `written_by` waits on capability 9.19 (§4). It narrows to the left-hand meaning when that lands, and until then a reader must not take it as a property of the code |
| `external` | the producer is outside what was scanned — a dependency jar |
| `cycle` | the walk returned to a position it had already visited on this path |

`fan_out` and `depth` are **deliberately absent** — §3a decides whether they are ever needed.

Today every one collapses into one word, so COVERAGE can say only *"unresolved"* and a reader cannot
tell *"we cannot see the jar"* from *"the code branches"*. Six reasons make a miss diagnosable —
**but only if something records them**, which §3d requires.

### 1e. The line that does not move

**The walk answers what a value is. The catalog still says what it means.** `channel_arg: 0`
continues to say *this position carries the destination*; the walk simply stops needing `channel_via`
to add *and it is one hop that way*. DR-6 is untouched. `evidence` stays `compiler` at any depth —
a value five hops away was still read off the code, and depth is not a confidence signal.

---

## 2. What the hop keys become: hoist, delete, refuse

Hop declarations do not vanish. The identity half is framework knowledge (§0b), so it **relocates**
from once-per-consumer to once-per-producer, in a shared model beside the shipped `bean-models/` and
`step-models/`:

```yaml
# value-models/jms.yml
identified_by:
  - { owner: jakarta.jms.Session, method: createQueue, arg: 0 }
  - { owner: jakarta.jms.Session, method: createTopic, arg: 0 }
```

and a consuming catalog says only `channel_arg: 0`.

### 2a. Three steps, in this order

1. **Hoist.** The loader reads every existing `channel_via` / `url_via` / `call_wrappers` /
   `record_wrappers` entry as an `identified_by` entry. They are the same three fields saying the
   same thing; only the declaration site differs. **No catalog edit is forced and no behaviour
   changes.** *`record_wrappers` was missing from this list until 2026-09-23 — see the correction
   under §0's table. It is `{type, <name>_ctor_arg}`, exactly `call_wrappers`' shape, and its three
   shipped occurrences are byte-identical entries for one producer, which is the duplication
   "declared once per producer" exists to end. A wrapper entry hoists as the type's `<init>`, one
   entry per `<name>_ctor_arg` it declares — `record_wrappers` declares two, and they are two
   claims about two arguments of one constructor.*
2. **Delete.** Once the walk is proven on a catalog (§3c), its now-redundant hop declarations go.
3. **Refuse.** The loader rejects the removed keys — all four — outright, the way every closed
   vocabulary here is enforced.

**Step 3 is the one that makes the design hold.** A design that merely *recommends* the new way
decays: a new catalog author copies the nearest example, and the nearest example is whatever thirteen
other catalogs do. That is the exact mechanism that produced §0a's seven words — `bean_via` already
existed as a general-ish hop when `contract` and `argument_chain` were proposed. One way, enforced by
the loader, is the only version that survives the tenth framework.

### 2b. What each engine keeps

| engine | today | after |
|---|---|---|
| `single_call` | `channel_of`, then `linked_channels` if unresolved, capped at one hop | `resolve_site` |
| `interface_implementation` | its own copy of the same | `resolve_site` |
| `fluent` | chain walk **plus** `_address_read`, `_literal_of`, the bean-chain fold | chain walk **stays**; value reads inside it call `resolve_site` |
| `annotation_driven` | declaration-side; reads no call values | unchanged |

**`fluent` keeping its chain walk is the point.** The walk answers *what is this value*; the chain
walk answers *which calls form one boundary*. Different questions — and conflating them is what
produced `bean_via`.

---

## 3. Data flow, the measurement gate, and sequencing

### 3a. The measurement is a gate, not a report

**Approved ruling: no cap in v1.** This is the task that makes that safe, and **nothing consumes the
walk until it passes**:

1. Build the edge view and the walk. **No engine calls it.**
2. Measure on the largest corpus available (`mall-admin` — 48 MB of facts, 648 documents) plus every
   fixture: for every position a shipped catalog actually asks about — path count, hop depth, answer
   count, wall time. Report the **distribution, the maximum and the tail**, never the mean.
3. **Ruling point.** The data either says no cap is needed or names the cap and its reason. If it
   names one, `fan_out` and `depth` join §1d then and not before.
4. Only then does migration begin.

### 3b. Where it runs, and why nothing is materialised

`value_edges` is a **view**, not a table (I-4). Every edge but `written_by` is already held by
`call_sites`, `return_flows` or `call_edges`; a materialised copy would add a writer, a reset, schema
growth and a second version that can drift from the first. The view normalises three shapes into one
without storing anything.

The transitive walk runs **on demand**, memoised per (position, path) for one resolve. Under §1c and
§3a the closure is potentially unbounded and multiplicative, and materialising *that* is the one
thing that could make a resolve unusable. The edge view cannot explode — it is linear in the facts —
and the walk explores only what a catalog asks about. On `orders-quarkus`, eight catalogs declared
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
written **only** for positions a catalog asked about and failed to resolve — bounded by what catalogs
ask, not by the facts. COVERAGE's boundary statements are generated from it rather than hand-written,
and a catalog author debugging a NULL address can query *why*.

---

## 4. The sixth edge is a capability, not a backend's work

`written_by` beyond a constructor — a binding assigned anywhere but the initialiser — is the only
edge with no fact behind it. D00 states the current limit plainly: `field_write` is *"constructors
only, direct traces only"*, and setter injection is *"a named gap, not an omission."*

**It is specified as D00 capability 9.19, not as ASM work** (I-5). Any backend may or may not report
it; the walk degrades **visibly** where it is absent, the way `nested_annotation_args` makes a
scanner's limitation skip a catalog loudly instead of under-reporting silently. The JVM backend's
implementation is one consumer of that capability, with its own probe and fixture, and it **must land
and be measured before the edge it feeds is wired** — a wrong binding-write fact fabricates silently
everywhere, which is why it runs on its own track.

~~It is what closes `akka-pekko-actors`: a reference obtained in one method and used in another is
the shape, and COVERAGE's *"possibly permanent"* tier is a statement about this missing capability
rather than about actors.~~

**CORRECTED 2026-10-17, measured.** The first half is false. `ActorRef ref = system.actorOf(props,
"worker")` assigns a CALL'S RESULT, and `scripts/probes/cp33_binding_writes.md` row 7 measures what
javac emits for that shape: `aload_0; aload_1; iconst_0; invokeinterface; checkcast; putfield`. A
call sits between the receiver load and the `putfield`, so the `ALOAD 0; xLOAD k; PUTFIELD` triple
`field_write` matches never presents — for the same reason it does not present for
`@PostConstruct`'s `ldc`. A parameter-sourced capability 9.19 would read a setter-injected
`ActorRef` and would NOT read the factory form the framework's own documentation uses, so that
framework's tier does not move on this edge.

The second half stands and is now sharper: the *"possibly permanent"* tier is a statement about a
**value-sourced** binding write, which is a larger fact than `{field, from_parameter}` can carry and
a larger one than Task 11 was scoped to build. The capability itself is deferred — `OI-136`, 16 of
756 asked positions.

---

## 5. Holding for the next language, and the next framework

This section exists because the first draft failed both tests and the failures were cheap to fix
then and expensive later.

### 5a. Language neutrality

- **`identified_by.owner` is OPTIONAL.** Go's `nats.Connect(url)` and Python's `boto3.client("sqs")`
  are free functions. The fact grammar already admits them — `owner_of` documents that *"an ownerless
  symbol is an answer here, never an exception"* — so requiring `owner` would bake OO into a model
  the facts do not.
- **`binding`, never `field`.** A named mutable location is a field in one language, a module-level
  variable in another, a package var or a closure cell elsewhere. The edge kinds say `binding`.
- **The sixth edge is a capability** (§4), so a backend that cannot see binding writes says so rather
  than the design assuming every backend is ASM.
- **`arg` is positional**, and a backend whose language has keyword-only arguments normalises to
  positions in the facts. Stated, not solved — no such backend exists yet.
- **No construct in §1 names a language feature.** `produced_by`, `returned_by`, `read_from_binding`,
  `written_by`, `bound_to_parameter`, `names_declaration` are statements about values and callables,
  all six of which exist in every imperative language this project targets.

### 5b. Framework extension

A new framework needs **no new word**. It declares which slot carries its address (`channel_arg: 0`,
as today), and — only if its producer is novel — one `identified_by` entry with a probe row behind it.
Distance is never described again.

The enforcement is §2a step 3: the old keys are invalid, so the cheap wrong path is closed rather
than merely discouraged.

---

## 6. Scope boundaries

- **It does not decide what a value means.** `identified_by` is framework knowledge with a probe
  behind every entry.
- **It is not a points-to analysis.** No heap modelling, no collection contents, no dynamically
  indexed elements. It follows *declared* edges; everything else is `unresolved`.
- **It does not cross the module boundary.** A producer in an unscanned dependency is `external`.
- **It does not resolve configuration.** `${…}` is carried verbatim; `resolved_config` still owns
  substitution.
- **It does not change linking.** A resolved value is a value; whether two rows link stays the
  linking tier's business.
- **It does not touch `fluent`'s chain walk** (§2b).
- **No reflection, no dynamic proxies, no computed strings.** A concatenation is never
  **evaluated**; its template is carried verbatim as an `expression` with its holes unfilled, and no
  hole is ever filled in (amended by T-1, §0d — the original bullet read "a concatenation stays
  `unresolved`", which would have discarded the template the `produced_by` arm was fixed to reach).

---

## 7. The risk, and the mitigation that is part of the design

Everything this project does rests on *misses are acceptable, fabrications are not*. **This work's
entire purpose is to convert misses into answers** — so every conversion is a new assertion, made at
scale, across nineteen shipped catalogs.

That is inverted from every other change in this repository. Group D's risk was *"we might not derive
something."* This one's is *"we might now derive something wrong, in nineteen places, and the tests
will go green because the rows are new."*

§3c's diff catches **movement**. It does not catch **wrongness** — a wrong address looks exactly like
a right one in a diff.

### 7a. Shadow mode

The walk runs and writes what it *would* resolve into §3d's `value_resolutions` table **without
publishing it**. Every candidate conversion is reviewable as data, on the real corpus, before a single
row changes; then each migration flips one engine and its diff is already known.

It costs one flag, and it converts *"review nineteen catalogs' worth of new claims under time
pressure"* into *"read a table."* **This work should not proceed without it.**

### 7b. The second risk

`value-models/` becomes a dumping ground — entries accumulate because adding one is easy, and nobody
measures whether the framework really identifies that value that way. The mitigation is the rule this
codebase already enforces everywhere else: **every `identified_by` entry carries its probe row**,
checked by the architecture suite exactly as `measured:` blocks are.

---

## 8. Testing

- A fixture arm **per edge kind** and **per `unresolved` reason** — including the negative ones, which
  are the point: a loop-built array, a branch-merged value, a binding with no writer, a value from an
  unscanned jar, a cycle.
- **A fixture arm for M-1 specifically**: a helper called from two sites with different values, pinning
  **two** rows and not four. That case is why the primitive is a path, and nothing else in the suite
  would catch a regression to per-position resolution.
- **Mutation guards on the three rules that carry the design**: termination, enumerable-versus-
  ambiguous, and path-coherence. If any can be broken without a test failing, the no-false-positives
  guarantee is unpinned.
- The migration diffs of §3c are the test of correctness; the unit tests are the test of the walk.

---

## 9. Self-review

**Placeholders.** None. Every count in §0 is measured at `50d3f6e`; every edge in §1a names its fact
and its projection; the one edge without a fact is §4 and says so.

**Internal consistency.** §1c's path primitive forces §3b's memoisation key and §8's M-1 fixture —
checked in both directions. §1d's vocabulary is used by §3d and nothing else, which is why §3d exists.
§2a's three steps are what §5b's enforcement argument rests on. §1e's `evidence` rule answers a
question §3c would otherwise raise.

**Ambiguity.** Two terms could be read two ways and are defined against existing rules rather than
left to judgement: *enumerable* (against D00's array rule, §1c) and *path* (the chain of calling
contexts, §1b).

**Generic over specific.** The six edge kinds name no language feature and no framework; the one
framework-specific thing, `identified_by`, is data with a probe behind it. §5a lists what was
JVM-shaped in the first draft and is not now.

**Complements rather than breaks.** §2a's hoist means no catalog edit is forced and no behaviour
changes on day one; the walk can only add until a migration deliberately flips an engine. The one
place this design does break something is §2a step 3, and §5b is the argument for why that break is
necessary rather than convenient.

**What the review did not settle, and the plan must.** Whether `return_flows` and `call_edges` are
re-pointed at `effective_call_sites` as a prerequisite task of this work or as a separate fix first.
They need it on their own merits — a Kotlin `$default` bridge is invisible to both today — so doing it
first, measured alone, is probably right; but that is a sequencing decision, not a design one.
