# What the backward value walk costs, measured before anything consumes it

Measurement date: 2026-09-23. Sextant snapshot: branch `spec/value-resolution`, head
`f27e1a3f`. Harness: [`scripts/measure_value_walk.py`](../../scripts/measure_value_walk.py).

**This is spec [§3a](../superpowers/specs/2026-09-22-value-resolution-design.md)'s gate.**
The approved ruling is *no cap in v1*, and that ruling is only safe if the measurement
happens before anything consumes the walk — otherwise "measure first" becomes "find out in
production". `resolve/values.py` therefore ships unwired (`fan_out` and `depth` are absent
from the reason vocabulary by ruling, not by oversight), and this document is what §3a step
3 rules on.

**Status: the numbers are in; the cap decision is the user's.** §3a makes it a ruling point
and nothing here implements one. §5 states what the data supports and why.

---

## 1. How the measurement was made

### 1.1 The corpora

Twenty-seven: every fixture that compiles, every example, and `mall-admin` — the largest
corpus available, 48 MB of facts across 648 documents, and the one §3a names. A corpus with
a full scan on disk (`.sextant/facts`, which includes the dependency jars the scan read) is
loaded from it; the rest are scanned from `target/classes` by the harness. Each corpus gets
a **fresh** workspace, loaded and then run through the two passes `value_edges` is
normalised out of (`record_return_flows`, `record_call_edges`) — nothing else in the
pipeline, because the edge query reads `call_sites`, `return_flows` and `call_edges` and the
walk reads `method_returns` beside them.

### 1.2 The positions — measured against real sites, never synthesised rows

`resolve_site` uses the row it is handed only to **name** the site; it resolves the
**projected** row for that `(caller, ordinal)` pair, so a synthesised row would be replaced
by the workspace's own and the measurement would be of something else. Every position here
is read out of `effective_call_sites` — the rows the engines see — through
`ValueIndex.sites`. Nothing is invented.

Two surfaces are measured, and the difference between them is the finding:

- **The asked surface** — every position a shipped catalog actually asks about. A catalog
  names one in three grammars, all three read: a `methods`/`entries`/`vocabulary` row
  carrying `arg` or a `<name>_arg` integer beside a method name; a `fluent` root/step/
  terminal carrying `captures: {name: argN}`; a `call_wrappers`/`record_wrappers` entry
  carrying a `<name>_ctor_arg` against a wrapper `type` (a position on that type's
  constructor, so the method is `<init>`; `payload_ctor_arg: last` is a rule rather than an
  index and is resolved per site). A row is matched to real sites on the keys the engines
  match on: owner where declared, method name, and the JVM `descriptor` or the `arity` where
  the row declares either.
- **The ceiling** — every argument **and the receiver** of every call site in every corpus,
  whether a catalog asks about it or not. Not what §3a asks for, and measured beside it
  rather than instead of it: a cap sized on today's asked surface alone would be
  re-litigated by the first catalog that asks somewhere new, and a ruling wants to know
  whether the corpus *holds* a pathological shape at all or merely fails to ask about one.

**Where a catalog row declares no owner the match is by method name alone**, which is wider
than the engine's own — `fluent`'s owner-free steps are really scoped to a chain the engine
has already rooted, and `ktor-routing`'s `request_reads` reach their receiver through a
`via` call. That is 22 of the 764 rows the shipped catalogs carry, and the names are common
ones (`get`, `url`, `method`, `uri`, `post`, `put`, `body`). It inflates the asked surface —
`ktor-routing`, `okhttp` and `jdk-httpclient` account for 508 of the 1,141 catalog-to-position
matches (over 898 distinct positions), most of them sites those catalogs would never really
claim. **The widening is deliberate and it is
the safe direction:** this measurement sizes a ceiling, so over-counting the asks can only
make the answer more conservative.

### 1.3 What is recorded

Per position, from the walk's own return value — a tuple of `(path, answer)` pairs:

| figure | what it is |
|---|---|
| **path count** | how many coherent paths reached the position |
| **hop depth** | crossings on the longest of those paths |
| **answer count** | **distinct** answers, which is not the path count: two callers passing the same literal are two paths and one answer |
| **positions visited** | every `(position, path)` the walk computed on the way — the work a cap would bound |
| **wall time** | `perf_counter` around the one call |

Per **site**, additionally, `resolve_site` itself is timed and its `Binding` count recorded.
§3b's "potentially unbounded and multiplicative" is about the **combination** step, and a
per-position measurement alone would miss it.

The walk's memo is per resolve and shared across one site's slots, so the harness builds one
`_Walk` per site and times each slot inside it — the production lifetime, not a friendlier
one. The subclass that counts computed positions lives in the harness; **nothing in `src/`
was changed for this measurement**, and the §3a grep
(`grep -rn "resolve_site\|resolve.values import" src/sextant/ | grep -v "resolve/values.py"`)
is still empty.

---

## 2. Answer 1 — how many positions shipped catalogs actually ask about

**898, across all twenty-seven corpora.** The ceiling on the same corpora is **98,454**. The
asked surface is **0.9%** of it.

§3b's guard shape holds, and harder than it did on `orders-quarkus`:

| corpus | call sites | value edges | positions asked | sites touched | asked / call sites |
|---|---|---|---|---|---|
| `mall-admin` | 25,057 | 59,254 | **78** | 52 | 0.3% |
| `mall-mbg` | 21,775 | 54,157 | **0** | 0 | 0% |
| `spring-petclinic-rest` | 3,037 | 4,032 | 71 | 44 | 2.3% |
| `mall-portal` | 2,200 | 2,434 | 77 | 41 | 3.5% |
| `orders-service` | 1,818 | 2,090 | 671 | 207 | 37% |
| `jhipster-sample-app` | 1,710 | 2,058 | 376 | 39 | 22% |
| `orders-ktor` | 471 | 584 | 137 | 49 | 29% |
| `grpc-probe` / `orders-quarkus` / `orders-spring7` / `orders-soap-final` / `orders-soap-client` | 391 / 13 / 13 / 6 / 0 | 539 / 7 / 5 / 0 / 0 | **0** each | 0 | 0% |

Six of the twenty-seven corpora ask about **nothing at all**, `mall-mbg` — 21,775 call
sites of MyBatis-generated model code — among them. The biggest corpus in the estate asks
about 78 positions. The fixtures ask proportionally far more because they exist to exercise
catalogs; the real applications do not.

Which catalogs ask (a position asked by two catalogs counts once for each):

| engine style | asked positions matched | catalogs that name a position |
|---|---|---|
| `combinator` | 452 | 5 of 5 |
| `fluent` | 428 | 12 of 12 |
| `single_call` | 234 | 30 of 30 |
| `supertype_dispatch` | 18 | 2 of 2 |
| `interface_implementation` | 9 | 1 of 1 |

Fifty of the 101 shipped catalogs name a call-site position at all; 47 of those matched
something somewhere in the corpora. The other 51 — `annotation_driven` and its relatives —
ask about annotation attributes, which this walk does not serve.

---

## 3. What the walk costs — distribution, maximum and tail

**No mean appears below.** A mean hides the pathological module, which is the only thing
this measurement is for.

### 3.1 The asked surface: 898 positions, 668 sites

| figure | p50 | p90 | p99 | max |
|---|---|---|---|---|
| paths per position | 1 | 1 | 2 | **3** |
| hop depth | 0 | 0 | 1 | **3** |
| distinct answers | 1 | 1 | 2 | 3 |
| positions visited | 0 | 1 | 4 | **11** |
| seconds per position | 0.9 µs | 3.0 µs | 15 µs | **29 µs** |

`resolve_site` over the same sites: **max 6 bindings**, worst site **38 µs**.
**Total walk time for every position every shipped catalog asks about, across all
twenty-seven corpora: 1.5 ms.** Total `resolve_site` time: 3.9 ms.

Path-count distribution: 885 positions have one path, 6 have two, 7 have three. Depth: 822
at 0, 72 at 1, 3 at 2, 1 at 3.

The worst asked positions by name:

| corpus | position | catalog | paths | depth | visits |
|---|---|---|---|---|---|
| `orders-ktor` / `-classlambdas` | `KtorRoutesKt#mount`@5 slots 0/1/2 | `ktor-routing` | 3 | 2 | 11 |
| `spring-petclinic-rest` | `ValidationMessageDto#putAdditionalProperty`@1 slot 0 | `okhttp` (name-only match) | 3 | 1 | 4 |
| `orders-gateway` | `GatewayRoutes#lambda$routes$1`@2 slot 0 | `spring-cloud-gateway` | 2 | 1 | 0 |
| `orders-service` | `StompBrokerConfig#registerStompEndpoints`@1 slot 0 | `spring-stomp-endpoint` | 2 | 1 | 0 |

The worst thing a shipped catalog asks about anywhere is a three-path, depth-2 Ktor route
mount. There is no tail.

### 3.2 The ceiling: 98,454 positions, 50,112 sites

| figure | p50 | p90 | p99 | p99.9 | max |
|---|---|---|---|---|---|
| paths per position | 1 | 1 | 24 | 124 | **388** |
| hop depth | 0 | 1 | 2 | 4 | **8** |
| distinct answers | 1 | 1 | 5 | 78 | 386 |
| positions visited | 1 | 3 | 49 | 355 | **1,559** |
| seconds per position | 1.3 µs | — | 70 µs | 417 µs | **2.3 ms** |

`resolve_site` over every site: **max 388 bindings** (p99: 24), worst site **60 ms**.
**Total walk time for every position in every corpus: 0.44 s.** Total `resolve_site` time:
**1.04 s.** Two runs agree to within 1.5% on both totals and to the row on every maximum.

Depth is genuinely shallow: 75,721 positions at 0, 20,708 at 1, 1,302 at 2, 618 at 3, 61 at
4, 35 at 5, 7 at 6, 1 at 7, **1 at 8**.

The single pathological shape in the estate, named:

| corpus | position | paths | depth | answers | visits | seconds |
|---|---|---|---|---|---|---|
| `mall-admin` | `OmsOrderExample$Criterion#<init>`@0 slot 1 | **388** | 5 | 1 | **1,559** | 2.0 ms |
| `mall-admin` | `OmsOrderExample$GeneratedCriteria#addCriterion`@3 slot 1 | 388 | 4 | 1 | 1,557 | 1.9 ms |
| `mall-mbg` | `OmsOrderExample$Criterion#<init>`@0 slot 1 | 386 | 3 | 1 | 1,547 | 2.3 ms |
| `mall-admin` | `PmsProductExample$Criterion#<init>`@0 slot 1 | 337 | 5 | 3 | 1,367 | 1.8 ms |
| `mall-admin` | `UmsAdminExample$Criterion#<init>`@0 slot 1 | 98 | **8** | 1 | 401 | 0.4 ms |

It is one shape repeated per generated table: MyBatis Generator's `…Example$Criteria`
builder, whose `addCriterion(String condition, Object value, String property)` is called
from a few hundred sibling methods in the same class, each passing its own literal. Every
one of those callers is a real calling context, so 388 paths is the correct answer and not
an explosion — **and it collapses to ONE distinct answer** at slot 1, because the slot the
walk was asked about is the same in all of them. The worst site of the estate,
`OmsOrderExample$Criterion#<init>`@0 with three slots, resolves in 60 ms.

Wall time at this scale is dominated by measurement noise — one position with 128 paths and
515 visits recorded 32 ms in one run and 1 ms in another, on the same input. **`visits` is
the deterministic work figure and it is the one to rule on**; the two runs' `visits` maxima
are identical.

### 3.3 The multiplicative risk did not materialise

§3b's stated danger is the **combination**: two slots with independent fan-out would
multiply. Across all 50,112 sites, `resolve_site`'s binding count exceeds the largest
single-slot path count at only **48 sites**, and the largest multiple anywhere is **3×**
(`jhipster-sample-app`'s `ExceptionTranslator#buildCause`@2: 15 bindings over a 5-path
slot). At the 388-path shape the bindings count is also 388 — the coherence rule holds it
linear, because the slots there cross out of the same method through the same call and M-1's
rule makes that one choice rather than a product.

No site anywhere returned **zero** bindings, so the coherence rule is not silently deleting
answers on real code either.

---

## 4. Answer 2 — which `unresolved` reasons fire on real code

**On the asked surface (898 positions, 419 unresolved answers):**

| reason | count | never fires? |
|---|---|---|
| `external` | 197 | |
| `not_readable` | 190 | |
| `no_writer` | 13 | |
| `escapes` | 12 | |
| `non_enumerable` | 7 | |
| **`cycle`** | **0** | **never, on anything a shipped catalog asks about** |

Answer kinds on the asked surface: `literal` 478, `unresolved` 419, `expression` 21,
**`absent` 0**.

**On the ceiling (98,454 positions):**

| reason | count |
|---|---|
| `external` | 76,773 |
| `not_readable` | 6,979 |
| `escapes` | 4,380 |
| `no_writer` | 3,321 |
| `non_enumerable` | 62 |
| `cycle` | **7** |

Answer kinds: `unresolved` 91,522, `literal` 83,304, `absent` 915, `expression` 528.

**So no reason is dead vocabulary** — all six are produced by real code, and so is `absent`.
Two of them are only reachable outside what catalogs ask about today, and the report has to
say which is which:

- **`cycle` fires seven times in the whole estate**, all of them genuine recursion:
  `orders-service`'s `SoleRefiner#shorten`@0 and `TraceProbe#describe`@5; and
  `jhipster-sample-app`'s `ExceptionTranslator#buildCause`@2 slot 2, `#customizeProblem`@25
  slot 0 and @31 slot 1, and `#getPathValue`@1 slot 0. **The word is earned and the
  termination rule is exercised** — but nothing a shipped catalog asks about is recursive,
  so this is a gap in the *asked surface*, not in the corpus and not in the vocabulary.
- **`absent` never appears on the asked surface** (915 times on the ceiling). Explicit
  `null` and zero-length varargs happen constantly in application code and never in the
  positions a framework catalog reads a destination or a payload out of. Ruling T-2's answer
  kind is correct and, for now, only the ceiling produces it.
- `non_enumerable` is the rarest reason that fires either way (62 of 98,454). Task 3's
  report already records why: it is reachable **only** through the array rule, because a
  loop-built or branch-merged value arrives as an unread argument and no fact says it was a
  loop. That prediction is confirmed here by the count.
- `escapes` is 4.8% of unresolved answers on the ceiling and 2.9% on the asked surface,
  which is in line with the 13.4% the Task 3 fix round measured over the narrower
  return-crossing population.

---

## 5. What the data says about the cap

**This is §3a's ruling point and the ruling is the user's.** What the data supports:

**No cap is needed for v1.**

1. **The asked surface is not near any plausible cap, on any corpus.** Max 3 paths, max
   depth 3, max 11 positions visited, 29 µs worst. Every position every shipped catalog asks
   about, across twenty-seven corpora including the 48 MB one, resolves in **1.5 ms total**.
   A cap would never fire.
2. **The ceiling is not near one either, and it is the number that matters** because it is
   what the asked surface could grow into. Resolving **every argument and receiver of every
   call site in the estate** — 98,454 positions, 50,112 `resolve_site` calls — costs
   **0.44 s of walking and 1.04 s including combination**. That is a whole-estate figure
   against which the pipeline's own `call_edges_insert` pass spends 8.9 s on `mall-admin`
   alone.
3. **The worst shape in the estate is correct rather than pathological.** 388 paths at
   `OmsOrderExample$Criterion` are 388 real calling contexts, and the walk answers them in
   2 ms and collapses them to one distinct answer. A `fan_out` cap set anywhere below ~400
   would refuse a position the walk resolves correctly and cheaply, and would refuse it with
   a word that means "we gave up" — the precise failure §1d's six reasons exist to avoid.
4. **Depth is bounded by the code, not by luck.** 97.9% of positions are at depth 0 or 1;
   exactly one position in 98,454 reaches depth 8. Termination is already guaranteed by the
   path (`cycle`), and the measurement shows the path does not get long.
5. **The multiplicative risk §3b names is real but small**: at most 3× anywhere, and 1× at
   the fan-out extreme, because the coherence rule holds it.

**If a cap is ruled in anyway**, the data names where it would have to sit to cost nothing:
`fan_out` at **512 paths per position** and `depth` at **16 crossings**, both well above the
measured maxima of 388 and 8, which would make them a crash barrier rather than a policy.
Anything tighter starts refusing answers the walk gets right today. Note that `visits`
rather than wall time is the figure to bound if one is wanted — wall time at these
magnitudes is noise, and `visits` reproduced exactly across runs.

**What would change this answer**, stated so it can be re-checked rather than re-assumed:

- A corpus whose generated code is an order of magnitude larger than `mall-mbg`'s, **and** a
  catalog that asks about a position inside it. Today those two conditions never co-occur:
  the corpus with the fan-out asks about nothing, and the corpora that ask have no fan-out.
- `written_by` (capability 9.19) landing. Every binding read ends at `no_writer` today —
  3,321 of them on the ceiling — and each is a walk that stops immediately. When the edge
  exists, those become real traversals, and this measurement should be re-run before the
  capability ships rather than after.
- A catalog that asks about a **receiver**. The asked surface is arguments only; the ceiling
  includes receivers, so the headroom is already measured, but the mix would shift towards
  the `escapes` check.

---

## 6. Reproducing this

```bash
JAVA_HOME=… .venv/bin/python scripts/measure_value_walk.py            # the asked surface
JAVA_HOME=… .venv/bin/python scripts/measure_value_walk.py --all-slots # the ceiling
```

Both print the per-corpus tables, the worst positions by name and the reason distribution;
`--json OUT` writes every row. A run over all twenty-seven corpora takes about 8 s, almost
all of it loading facts.
