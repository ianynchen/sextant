# Performance improvements

**These are not gaps.** A gap is something Sextant does not derive; every item here derives
the same output slower than it should. The order of work is the user's (2026-09-12): **fill
gaps first, then performance.** Nothing in this file is picked up while
[`java-kotlin-delivery-list.md`](java-kotlin-delivery-list.md) has an open blocker that a spec
or a plan can close, and nothing here is graded Critical or Major — it carries a measured
number instead.

Each item has: the measurement (machine, corpus, command), the cause as profiled, the shape
of the fix, and what would falsify the cause. A number written here without a run behind it
is a defect in this document.

---

## P-1 — a reactor module analyses in 111s; alone, in 8s

**Status: shipped in two steps, 2026-09-12 — `mall-admin` 111s → 8.7s, `orders-service` 7.0s → 2.5s.**

| step | change | `mall-admin` (+3 siblings) | `orders-service` |
|---|---|---|---|
| before | — | 108.6s (shapes 39.8s, endpoints 44.1s) | 7.0s |
| **P-1a** `83f5867` | the nine fact VIEWS (JSON re-extracted on every query) are materialized once per `load_facts` into `fact_*` tables the views point at; 0.4s to build; no index moved any query, none kept | **55.6s** (shapes 5.4s, endpoints 27.8s) | **4.6s** |
| **P-1b** `556d666` | the 33 fact-only named queries are read once per loaded fact set (cache keyed on name+params, cleared by `load_facts`; rows shared and read-only — the port says so); `method_declarations`/`call_sites` JSON parsed once; and a derivation's list parameter binds as ONE JSON value — DuckDB's client had tried `import pandas` for every value, 459,034 times in one derivation, 8.9s | **8.7s** | **2.5s** |

Local full suite: 4:10 → **1:58**. Output identical on both corpora: every workspace table
diffed row for row before and after each step. The retry route for a JSON bind that DuckDB's
cast refuses is counted (`_per_value_retries`) and asserted empty by the pipeline test.

**What remains, measured after P-1b** (`mall-admin` 8.7s): `derive_endpoints` 6.6s — of which
the `endpoints` statement is 1.6s (28 executions, ~55ms each) and Python folds the rest
(`single_call.run` 2.1s, `declared_parameters_of` 1.1s, `inherited_rows` 1.1s, `_origin_tiers`
0.9s); `derive_endpoint_shapes` 1.3s; scan 1.1s; `interpret schemas` 0.7s. See P-4, and A
below for the Python folds.

*The original analysis, kept for the record:*

**The rule the fix follows** (user, 2026-09-12). Every derivation has two sides. The **root
side** is what it derives *for* — this module's own classes, their annotations, their call
sites. The **lookup side** is what it may consult — anything scanned, a sibling's supertype,
an interface this module implements, a method it calls. Filter the root side to
`origin_tier = 'module_output'` at the **first read, in SQL**; leave the lookup side open.
Siblings are scanned in full (F4 §5.2 — this module declares them as dependencies, and a
type they declare has to be resolvable), but scanning them is not the same as deriving *for*
them. Filtering early on the roots and joining outward on demand is what DuckDB is for.

**Why the previous attempt failed.** "Lever 2" put the predicate on the lookup side — on the
document that *declares an annotation* — and dropped a route this module serves whose
annotation lives on a sibling's interface (`OrderController implements OrderApi`, `OrderApi`
in the api module). The root is the implementor; the interface is a lookup. A root filter
keeps it; an annotation-document filter loses it. It also saved nothing, because the SQL it
narrowed is 2.8s of the pass.

**Where the time is** (profiled 2026-09-12, replay over the loaded workspace, 31.7s):

| what | seconds | calls | rows read |
|---|---|---|---|
| `derive_endpoints.sql` (the `endpoints` derivation, every annotation-driven catalog) | 2.8s | 29 | — |
| `method_declarations` query | 6.0s | 59 | 1,301,481 |
| `call_sites` query | 4.7s | 38 | 952,166 |
| all 353 named queries together | 21.0s | | |
| `json.loads` over the rows those queries return | 7.7s | 2,647,512 | |

The 72 catalog engines cost 0.5–1.1s each with the same shape in every one: a Python
pre-pass pulls a whole fact table out of DuckDB (`method_declarations`, 22,059 rows, 59
times; `call_sites`, 25,000 rows, 38 times), parses every row's JSON, and filters in Python.

**The fix, in two parts, same principle twice:**

1. Every engine's read carries the root predicate in SQL — `WHERE origin_tier =
   'module_output'` on the root side of the join, never on the lookup side.
2. Each fact table is read **once per resolve**, not once per catalog — a read shared across
   the engines, or the JSON parsed once at load.

**Falsified by** a profile on another corpus putting the cost somewhere else, or a root
filter that changes any endpoint row (the five tests that failed under lever 2 are the
alarm: `test_module_edge.py::test_an_exchange_interface_a_SIBLING_declares_still_serves_this_modules_route`
and the four `stubCharge` tests in `test_vertical_slice.py`).

**How to measure.** `pipeline._timed` logs one INFO line per resolve pass
(`logging.basicConfig(level=logging.INFO)` before `api.analyze`), pinned by
`tests/application/test_pipeline.py::test_every_resolve_pass_logs_its_seconds_at_info`.
Corpus: `examples/mall/mall-admin` with its three siblings (648 documents) against alone
(161). Apple M4, 24 GB, Python 3.14.7, DuckDB 1.5.5.

### History — what was tried, in order (moved here from `open-issues.md` `OI-68`)

*The title said "and most of it is avoidable" until W56 measured it. The cost is real and has
GROWN; the two mechanisms this entry blamed are not it.*

**Found by** the W24 review, and confirmed on the pinned corpus.

`mall-admin` analyses in **67s** with its three sibling dependencies scanned, against
roughly 6s without them: 648 documents instead of 161. The review's own breakdown of the
resolve half put `derive_endpoints` at 18.4s, `derive_endpoint_shapes` at 18.3s and
`record_call_edges` at 14.6s.

**Two of those three legitimately need the siblings.** Shape expansion is the whole point
of crossing the module edge, and `call_edges`/`type_hierarchy` resolve against types
declared next door. `derive_endpoints` does not: `drop_borrowed_endpoints.sql` deletes
every row a dependency's document mints, so that work is done and then thrown away.

**Consequence today:** slower analysis, not wrong output.

**Measured per phase, same fact tree with and without the sibling subtree:**

| phase | module only | with siblings | what the extra time buys |
|---|---|---|---|
| `derive_endpoints` | 2.1s | **15.2s** | **nothing** — 160 endpoints either way |
| `record_call_edges` | 1.6s | **16.7s** | 2,608 → 24,591 edges, none of them traced |
| `record_return_flows` | 0.3s | **5.8s** | 566 → 9,951 flows, same |
| `derive_endpoint_shapes` | — | ~16.5s | the point of the item: `CommonResult<T>` gains fields |

So roughly **33 of the ~61 seconds of derivation buys nothing**, and an earlier note here
described it as "work the guardrail then discards", which is wrong and worth correcting:
the guardrail discards NOTHING on this corpus, because the three sibling dependencies
declare no controllers. The cost is `derive_endpoints` SEARCHING 487 documents for
endpoints that are not there, and `call_edges`/`return_flows` building the dependencies'
own call graphs — 22,000 edges from callers nothing will ever trace.

**Closes by** honouring F4 §5.2's own wording. It says read a sibling module's **types**;
the implementation scans a sibling module ENTIRELY. What resolution needs from a sibling
is signatures, fields and hierarchy — `BaseEntity#getId` must exist — not its call sites
or its method annotations. Two levers, in order of value:

1. **A types-only scan for a dependency root.** The extractor already walks each class
   deciding what to emit; skipping call sites and method-level annotations for such a
   root would cut the fact volume (79,315 facts against 6,388) and therefore every pass
   downstream at once, rather than one pass at a time.
2. **Filter derivation roots to the module's own documents** at each row-minting pass,
   which makes `drop_borrowed_endpoints.sql` a belt-and-braces check rather than the
   mechanism, and removes `derive_endpoints`'s 13s outright.

**Falsified by** measuring that a sibling's call edges are reached by a real trace — if a
trace crosses into a dependency's body, its call graph is not waste and lever 1 would cost
recall.

---

## W56 ran this, and refuted both levers. The item stays OPEN.

**Lever 1 is falsified by the condition written directly above.** Traces cross into sibling
bodies constantly: **2,105 of `mall-admin`'s 3,892 reachability rows are sibling symbols**,
every one of them non-terminal — bodies that were read — at depths 1 through 8. So "none of
them traced" and "22,000 edges from callers nothing will ever trace" are both false, and the
call-graph work is buying recall.

**How much a types-only scan would cost, measured:** **48.2% — 1,874 of the 3,892 rows** (measured by deleting the sibling bodies' outgoing edges and re-running `record_reachability` itself, so the real walk answers rather than a replay of it). The composition is the sharper point: **856 of the 2,105 sibling rows SURVIVE**, because a sibling method called straight from a module body keeps its row, and **625 of the lost rows are not the dependency's own at all** — this module's symbols and its libraries', reachable only THROUGH a sibling body.

*W56 first published "54%", which was the 2,105 restated as a consequence rather than measured
as one. The measurement above deletes the sibling bodies' outgoing edges from a copy of the
workspace and re-runs `record_reachability`, so the walk that answers is the one that built the
table — no replay, which is what the first two attempts at this number got wrong.*

**Lever 2 was built, measured and reverted.** Filtering sibling annotations out of the
endpoint root is output-neutral on this corpus — every table identical — and saves no
measurable time: alternating runs put it within noise, in both directions. *That is itself
evidence this entry's attribution was wrong. If removing every sibling annotation from the
endpoint root changes nothing, the 13s charged to sibling roots in `derive_endpoints` is not
there.*

**And it loses a real route**, which is why it cannot simply be made cheaper and kept:
`drop_borrowed_endpoints.sql` keys on the row's HANDLER, a root filter keys on the
ANNOTATION's own document, and the two come apart wherever a catalog rebinds a handler to an
implementing type. `tests/application/test_module_edge.py::test_an_exchange_interface_a_SIBLING_declares_still_serves_this_modules_route`
is that case and fails with such a filter in. Deriving from every document and deleting what
the module does not own is load-bearing.

**Where the cost actually sits, profiled 2026-09-11** — every figure in the table above has
drifted, the two largest passes upward, and the whole analyze is now ~100s rather than 67s:

| pass | this entry recorded | measured today |
|---|---|---|
| `derive_endpoints` | 15.2s | **~25-36s** |
| `derive_endpoint_shapes` | ~16.5s | **~35-37s** |
| `record_call_edges` | 16.7s | **~14-19s** |
| `record_return_flows` | 5.8s | **~5-6s** |
| `record_reachability` | not in the table | **~1s** |

*Two independent profiles taken the same day differ by several seconds a pass, so these are
ranges rather than points — which is the honest shape for a wall-clock figure on one machine,
and is why a single-run comparison misled this wave once already.*

**Still closes by** attacking the two passes that actually dominate, which are shape
expansion and endpoint derivation — not by the two levers named above. **Falsified by** a
profile on another corpus putting the cost somewhere else entirely.

---

## Lever 2 was measured a second time on 2026-09-12, and the pass was profiled to the query. It is not the SQL.

The pipeline now has a standing per-pass timer (`pipeline._timed`, one INFO line per pass,
pinned by `tests/application/test_pipeline.py::test_every_resolve_pass_logs_its_seconds_
at_info`), so these tables come from the instrument rather than from a script. Apple M4,
24 GB, Python 3.14.7, DuckDB 1.5.5; `mall-admin`, 160 endpoints either way; two runs of
each, the second within 1s a pass of the first.

**Before anything was changed** — with its three siblings (648 documents) and alone (161):

| pass | alone | with siblings |
|---|---|---|
| `record_return_flows` | 0.3s | 4.3s |
| `record_call_edges` | 1.3s | 12.7s |
| `derive_endpoints` | 3.6s | **47.4s** |
| `derive_endpoint_shapes` | 1.5s | **39.7s** |
| `record_service_identity_gaps` | 0.1s | 1.6s |
| `record_routing_conflicts` | 0.1s | 1.4s |
| `record_reachability` | 0.4s | 1.3s |
| whole analyze | 8.0s | **111.9s** |

**Lever 2, applied and measured.** `annotations_effective` in `derive_endpoints.sql`
restricted to documents whose `origin_tier` is `module_output`, run over the same
with-siblings workspace: `derive_endpoints` 32.0s against 31.7s without it (a resolve
replayed over an already-loaded workspace runs the pass in ~32s; a fresh analyze runs it
in ~47s — both are recorded, neither is explained here), the `endpoints` statement 3.07s
against 2.82s, the 160 rows identical on this corpus. **And it drops two real routes on the
fixture:** the sibling-declared exchange interface's `/orders/list`
(`test_module_edge.py::test_an_exchange_interface_a_SIBLING_declares_still_serves_this_
modules_route`) and the opted-in library's `{http://billing.example.com/ws}stubCharge`
(four tests in `tests/e2e/test_vertical_slice.py`) — the second because `origin_tier` is
`dependency` for a consented library and a sibling alike, which is the distinction
`drop_borrowed_endpoints.sql` already explains it cannot read from the tier. The filter
was reverted; the SQL is byte-identical to before.

**After** (the same code plus the timer; the second full run):

| pass | alone | with siblings |
|---|---|---|
| `record_return_flows` | 0.3s | 4.4s |
| `record_call_edges` | 1.3s | 13.0s |
| `derive_endpoints` | 3.6s | **47.4s** |
| `derive_endpoint_shapes` | 1.6s | **38.7s** |
| whole analyze | 8.1s | **111.3s** |

**Where `derive_endpoints` actually spends its time**, replayed over the with-siblings
workspace with every named query and derivation timed (31.7s in the replay):

| what | seconds | calls | rows read |
|---|---|---|---|
| `derive_endpoints.sql` (the `endpoints` derivation, every annotation-driven catalog) | 2.8s | 29 | — |
| every other named derivation together | 0.2s | | |
| `method_declarations` query | 6.0s | 59 | 1,301,481 |
| `call_sites` query | 4.7s | 38 | 952,166 |
| `constructor_declarations` query | 1.6s | 36 | 29,448 |
| `interface_symbols` query | 1.5s | 30 | 4,020 |
| `annotations` query | 1.4s | 41 | 73,103 |
| `enum_types` query | 1.3s | 32 | 32 |
| `supertypes` query | 1.3s | 31 | 31 |
| `implementations` query | 1.2s | 28 | 3,360 |
| `superclasses` query | 1.0s | 24 | 2,184 |
| all named queries together | 21.0s | 353 | |
| `json.loads` over the rows those queries return (cProfile) | 7.7s | 2,647,512 | |

The SQL that lever 2 would have narrowed is 2.8s of the pass, so **no root filter in
`derive_endpoints.sql` can save more than that**, which is why W56 measured nothing and
this did too. The 72 catalogs cost 0.5–1.1s EACH and the cost is the same shape in every
one of them: each engine's Python pre-pass re-reads the whole `method_declarations`
(22,059 rows × 59 reads) or `call_sites` table (25,000 rows × 38 reads) and re-parses
every row's JSON, per catalog, when the table is the same table every time. A `supertypes`
query that returns one row costs 41ms because it scans the fact table to find it.

**What closes it, now that the number is measured:** the pass reads each fact table once
per resolve rather than once per catalog — a read shared across the engines, or the JSON
parsed once at load. That is a change to how engines read, not to any SQL, and it is not
a root filter. `derive_endpoint_shapes` (39s) was not profiled to the query here.
**`GAP-7` stays open**: 111s against the 10s the register calls acceptable.

---

## P-2 — the CI test job takes ~20 minutes

**Status:** open, tracked in Plane as [SEXTANT-185](https://app.plane.so/portolan/browse/SEXTANT-185/); the biggest single lever is P-1.

**Measured** (PR #20 run 34669970510, 2026-09-12, `--durations=20`): pytest 20:19 of a
23:10 job on a 4-vCPU `ubuntu-latest` runner, against 4:10 locally on a 10-core laptop. One
`module analyze` of `fixtures/orders-service` takes ~75s on the runner against ~15s locally,
and the slowest tests are the ones that must run their own analysis (two determinism tests
that analyse twice, the reactor test, the stale-render test) — 130–170s each on the runner.

**Cause.** Four workers each running a JVM extractor plus a DuckDB resolve on four vCPUs,
each DuckDB instance defaulting to every core it can see. The suite already shares one
analysis per session wherever a test only reads (`analyzed_orders_service`,
`full_run`, `rendered_fixture`) and dispatches the pipeline-running files first
(`tests/conftest.py`), which took the run from 38 minutes failing to 23 green; the remainder
is the analyses that cannot be shared, multiplied by P-1's per-analysis cost.

**The fix, in order of expected value:**

1. P-1 — every analysis in the suite pays the same 72-engine re-read. **Shipped**; local
   suite 4:10 → 1:58. CI figure: the next run of this branch.
2. ~~Cap DuckDB threads per worker~~ — **measured and refuted** (draft PR #22, run
   34705066921): pytest 23:25 against the 20:19 baseline with `SET threads = 1` per xdist
   worker. DuckDB's parallelism inside a pass is worth more than the oversubscription costs.
3. `scripts/check.sh` split into three workflow steps (`--lint` · `--extractor` · `--tests`)
   so a lint or type failure is visible in seconds and the pytest log streams on its own.
   **Shipped** with this ledger; the local gate is unchanged.
4. D — the suite's own overhead: Maven re-verifying compiled fixtures 25 times per run.
   **Shipped**; local suite 104s → 90s, CPU 513s → 398s, Maven runs 25 → 6. On the runner
   the priming step now writes the stamps, so the suite's compiles find nothing to do.

**Falsified by** a run where the per-analysis cost on the runner is not the dominant term
of the slowest tests.

---

## P-3 — export walks every fact payload for redaction, twice

**Status: shipped `c36b360` + `abb98fb`, 2026-09-12 — `mall-admin` export 3.3s → 1.2s.**

**Measured.** `DuckDbWorkspace._stage_fact_redactions` selected every non-`config_entry`
payload (75,296 on `mall-admin`), parsed and walked each in Python through
`Redactor.redact_json` (3.26M `_masked` calls, 1.49M regex passes), and ran twice per export —
4.0s of a 5.4s export under the profiler.

**Fix, the same rule twice.** Staged once per export (keyed on the redactor's rule-set hash,
cleared by `load_facts`). And filtered early: a DuckDB `regexp_matches` predicate that is a
measured SUPERSET of the three rules a payload can change under — URL userinfo, a value
pattern's literal prefix, a key pattern spelled as `normalize_key` run backwards — so only
payloads a rule can touch reach Python: 75,296 → 592 on `mall-admin`, 3,929 → 4 on
`orders-service`. The superset is pinned by running the old path against the new over the
fixture's whole fact set and an adversarial set that covers RE2-vs-Python case folds (the
review found the Kelvin-sign fold entry was an ASCII `K` — one byte, one under-masked payload;
fixed and pinned), HTML-safe JSON escapes, upper-case schemes, and matches that exist only
after the userinfo strip. Bundles byte-identical on both corpora.

## P-4 — the `endpoints` statement runs once per catalog

**Status: shipped 2026-09-12 as B, below.** The measurement that opened it, kept for the
record: `derive_endpoints.sql` (1,332 lines, ~50 `$params`) executes
once per annotation-driven catalog: 28–29 times, ~55ms each = 1.4s of `orders-service`'s 2.5s
analyze (the suite pays this ~25× per run, CI ~5× slower again) and 1.6s of `mall-admin`'s.
Benchmarked 2026-09-12: the cost is the statement's SIZE — 1,300 terms cost 26–33ms whether
they are `$` placeholders, literals, a one-row CTE or a temp table — so a prepared statement,
MATERIALIZED CTEs or comment stripping cannot move it (all measured). Only running it ONCE
per resolve, over a table of every catalog's parameters joined in, cuts it. That is a rewrite
of the largest SQL file, the design §8.7 would have asked for at the start; it is the biggest
single item left for the suite and CI.

## A — the engines' per-catalog folds over the fact tables

**Status: shipped 2026-09-12 — whole `api.analyze`, `mall-admin` (+3 siblings) 9.5s → 7.0s,
`orders-service` 2.6s → 2.5s** (Apple M4, three runs each, before and after every step; the
before is higher than the P-1 row's 8.7s because it is this session's machine, and every
number in the table below is from the same session).

**Measured.** After P-1b every fact query is read once, so what remained was each engine
folding the same cached rows into the same catalog-independent structure once per catalog:
`single_call` indexed the 24,815 `call_sites` rows by caller 25 times and tested every one of
them against its owners; `derive_shapes` built the symbol → origin-tier map 79 times;
`declared_parameters_of` folded 22,059 method rows 31 times; `annotation_driven` decoded every
annotation's `args` 30 times and rebuilt the type hierarchy the inheritance walk reads 19
times. ~4s of the 6.9s resolve on `mall-admin`, ~0.5s on `orders-service`.

**Fix — one rule, `Workspace.once(build)`.** A structure that depends on no catalog is built
once per load and handed back until the next `load_facts`, the lifetime the cached rows
already have; the memo lives on the workspace (cleared where `_fact_reads` is), keyed by the
builder function, and a builder that reads a derived table is refused at the read, so a value
cannot survive the derivation that changed it. Chosen over a per-resolve context threaded
through every engine's `run(workspace, catalog)` because it changes eight call sites and no
signature — the context would have touched thirteen engines, the shape pass and every test
that calls an engine directly. What is shared is read-only to its consumers, the same contract
the port states for query rows. Output identical: every workspace table (`ORDER BY ALL`, every
column as text) and `metadata.json` compare equal before and after each step on both corpora.

| step | structure, built once per load | `mall-admin` | `orders-service` |
|---|---|---|---|
| before | — | 9.5s | 2.6s |
| 1 | `CallSiteIndex` (`call_sites` by caller, by bare caller, positions by owner) — `single_call` reads the sites on its owners instead of testing every site (`run` own time 0.81s → 0.00s under cProfile) | **8.6s** | 2.6s |
| 2 | `annotations` rows with `args` decoded; `TypeHierarchy` for the inheritance walk (`_synthetic_annotations` 1.27s → 0.56s, `inherited_rows` 1.15s → 0.51s) | **8.3s** | 2.6s |
| 3 | `_origin_tiers` (0.96s over 79 calls → 0.03s, one call) | **7.7s** | 2.6s |
| 4 | `declared_parameters_of` (0.79s/31 → 0.01s/1) and `FieldDeclarations`, the four catalog-independent maps of `FieldFacts` (0.47s/31 → 0.02s) | **7.1s** | 2.5s |
| 5 | `fluent` reads the same `CallSiteIndex` (`run` 0.50s → 0.44s) | **7.0s** | 2.5s |

**Left, with the number.** `inherited_rows_over` still costs 0.51s over 19 catalogs on
`mall-admin`: what remains is the walk itself — which ancestor method carries one of THIS
catalog's mapping annotations — and the per-target annotation map it reads, both of which
take the catalog's fqns as input; the catalog-independent half is the hierarchy, and that is
step 2. `fluent.run`'s own 0.15s is its per-caller receiver index, 25k `setdefault`s per
catalog over six catalogs; below the threshold this round set. The `endpoints` statement
(P-4) was then the largest item inside `derive_endpoints` on both corpora — B, below.

## B — the `endpoints` statement runs once per resolve (P-4)

**Status: shipped 2026-09-12 — whole `api.analyze`, `orders-service` 2.4s → 1.3s,
`mall-admin` (+3 siblings) 6.9s → 6.0s** (Apple M4, three runs each; the `derive_endpoints`
pass 1.5s → 0.3s and 2.5s → 1.4s; the statement itself 1.4s over 29 executions → 0.11s over
ONE on `orders-service`, 1.4s over 28 → 0.12s over one on `mall-admin`).

**Measured before designing.** The order `derive_endpoints` runs catalogs in was logged on
both corpora rather than read off the code: 30 annotation-driven catalogs run on
`orders-service` (`spring-rsocket` skipped on its dependency gate), 29 on `mall-admin`
(`spring-stomp` too), and they are NOT contiguous — the sort is by filename within a
direction, so `jakarta-servlet`, `javalin`, `kafka-consumer`, `pekko-connectors-kafka`,
`spring-mvc-router`, `spring-stomp-endpoint`, `spring-websocket` and the outbound call-site
catalogs sit between them, 11 contiguous runs in all. That matters because the statement's
closing `NOT EXISTS (… FROM endpoints …)` is earlier-catalog-wins over the wire identity,
and `derive_call_endpoints.sql`'s guard is the same rule for the other engines: a topic a
`@KafkaListener` and a programmatic consumer both name belongs to whichever ran first. A
batch that merged across one of those boundaries would swap the winner; a batch per
contiguous run would have executed the statement 11 times.

**Fix — derive once, insert per turn.** `derive_endpoints.sql` takes every catalog at once
(`$catalogs`, one STRUCT per catalog, the P-1b binding shape) and writes every catalog's
candidate rows to the temp table `endpoint_candidates`, `catalog_id` carried through every
CTE so rows never mix; the earlier-catalog-wins guard moved, unchanged, into the 30-line
`insert_endpoints.sql`, which `derive_endpoints` runs at each catalog's own turn in the
unchanged order. So the guard is asked at exactly the moment it always was, against exactly
the table it always saw — the interleaving, the reply rows a catalog derives after its own
insert, and the content-negotiation pairs one catalog mints for one route (which the
brief's `row_number()` shape would have collapsed to one) all come out as before, by
construction rather than by proof. The engine is `params_for` (the 32 values, a pure
function of the catalog and the fact tables — `_direction_flip` reads facts only),
`stage(workspace, catalogs)` and `insert(workspace, catalog)`; `run` is a batch of one for
a caller with one catalog. The per-catalog statement costs ~1ms; the batch statement ~110ms
for 30 catalogs.

**Identity.** Every workspace table (`ORDER BY ALL`, every column as text) and
`metadata.json` equal before and after on both corpora; the `endpoints` rows dumped WITH
`catalog_id` equal line for line (a row minted by a different catalog would be a wrong
order even at the same wire identity); the full suite. The one difference the suite caught
and the corpora could not: a select-list alias (`direction`) read back inside the same
SELECT is shadowed once the joined catalog row has a column of that name — a flipped
`@HttpExchange` row landed its symbol on the wrong side, and neither corpus has a flipped
row. Pinned by `test_two_catalogs_in_one_batch_claiming_one_wire_identity_derive_the_
earlier_ones_rows` (both filename orders) and
`test_the_endpoints_statement_runs_once_per_resolve_and_every_catalog_takes_its_turn`.

## D — a compiled fixture is compiled again only when its inputs change

**Status: shipped 2026-09-12 — full suite 104.1s / 105.2s / 103.6s → 90.0s / 90.2s / 89.9s
(pytest's own figure; Apple M4, `-n 4 --dist loadfile`, three runs each), 513s → 398s user
CPU, Maven invocations 25 → 6 per run, Maven wall 50.7s → 7.0s.** No product code changed.

**Measured.** A `mvn` shim on `PATH` logged every Maven call the suite made: 25, 50.7s of
wall time between them, ~130s of the 510s CPU. `fixtures/orders-service` 4× (once per
xdist worker, 4.6s each under load); `orders-micronaut`, `orders-spring7`,
`orders-receivers` 2× each; the two module-scoped COPIES of `orders-service`
(`tests/api/test_facade.py::compiled_fixture`, `tests/cli/test_enrich_command.py::
compiled_fixture`) 5.5s each although `copytree` keeps `target/` and Maven finds nothing
to do; seven other fixture roots once each; six synthetic one-module reactors in
`tests/cli/test_app.py`, ~1.2s each, which write their own POM and must compile. One
`compile_fixture(orders-service)` on an up-to-date tree costs 3.4–3.6s wall and 10–11s
CPU — Maven's JVM plus its own incremental check — and 19 of the 25 verified a tree that
had not changed.

**Cause.** `tests/fixture_build.py::compile_fixture` memoised in a process-local set: per
worker under xdist, and nothing across sessions. `fixture_stub.py::is_current` already
solves the same problem for the stub jar with a currency check against its sources; the
fixtures had no equivalent.

**The fix.** After a compile, `target/sextant-fixture.stamp` records a sha256 over every
compile input: the relative path and bytes of every file under the root except `target/`,
`.sextant/`, `.sextant-enrichment.json`, `.tradewind/` and `.git/`; the parent directory's
`pom.xml` when the root's POM declares a `<parent>` (`billing-lib` reaches the reactor
parent by `<relativePath>`); and the stub jar's path, size and mtime (`orders-service`
compiles against it, and the session fixture rebuilds it first). `compile_fixture` runs
Maven only when `target/classes` is missing or the stamp differs from today's
fingerprint. Content rather than mtimes, so a `copytree` of a stamped root is stamped
too — that is what removes the two 5.5s copies — and a `touch` forces nothing. The
fingerprint of `orders-service` (112 files) costs 4ms; every other fixture under 1ms.
`python tests/fixture_build.py` compiles `PRIMED_FIXTURES` online and writes the stamps;
`.github/workflows/pr.yml`'s priming step runs it in place of ten `mvn` lines, so the
stamps exist before the suite starts — without them each worker would still compile every
root once. Pinned by `tests/scripts/test_fixture_build.py`: a stamped root does not
invoke Maven, a copy of one is current, one changed source byte re-invokes it and rewrites
the stamp, a missing `target/classes` re-invokes it with a matching stamp, and the parent
POM and stub jar are inputs.

**After.** The shim on a stamped tree: 6 invocations, 7.0s — the six synthetic reactors,
which have no stamp to find. The first run after the change, stamps absent: 17 (each root
once, the copies already finding the stamp the real root's compile wrote), 21.9s. With
`fixtures/orders-spring7/target` deleted: 7 invocations — that root compiled once, by the
first of the two files that need it, and was stamped for the second; every other root
untouched.

**Falsified by** a shim run on a stamped tree that names a fixture root.

## C — analyze reads the whole fact tree to find descriptors, and parses the catalogs in pure Python

**Status: shipped 2026-09-12 — whole `api._analyze`, `mall-admin` (+3 siblings) 5.6s → 3.8s,
`orders-service` 1.15s → 1.0s** (Apple M4, on top of A+B, three runs each, the per-phase
timer over `api._analyze`).

**Measured, before.** Two reads that do no work, on every analyze of every module:

| phase | `mall-admin` (+3 siblings) | `orders-service` |
|---|---|---|
| scan (4 JVM launches / 2) | 1.05s | 0.31s |
| interpret schemas | **0.71s** | 0.02s |
| resolve | 3.67s | 0.67s |
| of which `load_facts` | 0.45s | 0.03s |
| catalog load (`YamlCatalogSource.load`) | **0.19s** | **0.18s** |
| total | 5.6s | 1.15s |

1. **"interpret schemas" interprets nothing on `mall-admin`.** The corpus holds no
   `embedded_descriptor` fact at all (`orders-service` holds one in 11 of its 139 files), and
   `interpret_descriptors` runs in 0.000s under cProfile. The 0.71s is `read_fact_tree` in
   `stages/analyze.py`: every fact file — 648 files, 47MB, 124k lines — read, JSON-parsed and
   validated through pydantic, to find the descriptors; `load_facts` then reads the same tree
   again inside resolve. Only a document that DOES carry a descriptor is ever written back.
   And the cost did not end with the phase: the parsed facts stayed alive in the stage's
   locals through the whole resolve, and the collector walked them on every pass — dropping
   them before resolve, nothing else changed, took `mall-admin`'s resolve 3.50s → 2.52s. The
   interpret step is now a function of its own, so what it parses dies with it by
   construction: a module with hundreds of generated schema classes still retains hundreds
   of parsed files after the prefilter, and would have carried them through resolve.
2. **The catalogs are parsed with the pure-Python loader.** 79 catalogs and the shape model
   through `yaml.safe_load`: 0.18s on every analyze, whatever the module — 16% of an
   `orders-service` analyze, ~40 analyses per suite run — with libyaml installed beside it
   (`yaml.CSafeLoader`; PyYAML's published wheels bundle it — every 6.0.x manylinux and macOS
   wheel).

**Fix.** (1) `read_fact_tree` takes a `containing: bytes` token and parses only the files
whose bytes hold it — the P-3 pattern, an exact byte-level superset test before the parse. The
stage passes the descriptor kind's JSON spelling (`"embedded_descriptor"`, derived from the
model's own `kind` default, not a second literal), which is what both writers put on disk — the
quoted value rather than the `"kind":...` pair, because the pair's spelling depends on a
writer's separators and the value's does not. A skipped file is one no interpreter could have
produced a shape for (every interpreter stamps a shape with its descriptor's own document id),
so it is one the stage would not have rewritten. Sorted order kept; the stage still reads
through the domain function (`test_application_reads_no_files`). (2) `YamlCatalogSource`
loads through `yaml.CSafeLoader` where the interpreter has it. `.sextant.yml`
(`sextant_config.py`) is one small file per module, usually absent, and left alone; the
repository-config reader (`read/yaml_config.py`) uses its own loader subclass that keeps every
scalar's raw spelling and key order, and a C-backed subclass is a different loader with its
own construction path — out of this item's scope, and not on the per-catalog path.

**Proof of identity.** Every workspace table (`ORDER BY ALL`, every column as text) and
`metadata.json` compare equal before and after on both corpora; both fact trees compare equal
byte for byte after a run (`diff -r`), `orders-service`'s 11 descriptor files and the 7 that
carry interpreted shapes included. The two loaders: every shipped catalog and shape model is
read with both and the objects compared equal, scalar types included
(`tests/ingress/test_catalog_source.py`) — libyaml and the pure loader differ on a few YAML
1.1 corners, and that test is the whole claim that none of ours hits one. The token: pinned
against `write_fact_file`'s own output (`test_the_descriptor_token_is_what_the_writer_spells`).

**After** (three runs each; the resolve column is where the retained facts had been):

| phase | `mall-admin` (+3 siblings) | `orders-service` |
|---|---|---|
| scan | 1.04–1.20s | 0.29–0.33s |
| interpret schemas | **0.02–0.03s** | 0.01s |
| resolve | **2.53–2.55s** | **0.50s** |
| of which `load_facts` | 0.44–0.46s | 0.03s |
| catalog load | **0.02s** | **0.02s** |
| total | **3.73–3.80s** | **0.94–0.98s** |

The gate's pytest line after the change: 3233 passed in 65.3s, one run (D's three runs were
90.0–90.2s; the suite analyzes ~40 modules, each of which paid the catalog parse).

**Scan — measured, not started.** `mall-admin`'s scan is 4 JVM launches, 1.05s; the
`mall-mbg` sibling alone is 0.59s wall / 2.2s user standalone for 458 classes → 42MB of facts
(`Main.java:441` joins every line into one string and then writes the bytes); the JVM startup
floor is ~0.05s (`--capabilities`). Nothing cheap and exact here; it needs a profile inside
the extractor.

**Falsified by** a fact file that holds a descriptor whose bytes do not spell
`"embedded_descriptor"`, or a shipped catalog the two loaders read differently.

## The whole flow, after A, B and C (analyze → render → export, 2026-09-12)

Each corpus analyzed in place on a copy under `/tmp/perf/corpora/`, two runs, the analyze
row split by the per-phase timer. The previous table (after P-1 and P-3) read 2.7s / 10.4s.

| stage | `orders-service` | `mall-admin` (+3 siblings) |
|---|---|---|
| analyze — scan | 0.3s | 1.1s |
| analyze — interpret schemas | 0.0s | 0.0s |
| analyze — resolve | 0.5s | 2.6s |
| render | 0.1s | 0.3s |
| export | 0.2s | 1.3s |
| **total** | **1.3–1.4s** | **5.2–5.5s** |
