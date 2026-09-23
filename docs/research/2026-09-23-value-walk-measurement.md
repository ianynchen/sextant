# What the backward value walk costs, measured before anything consumes it

Measurement date: 2026-09-23. Sextant snapshot: branch `spec/value-resolution`, **the ask
reader as of `ad210319`** — the commit that widened it to `parse_calls`, and **the last one
that changed what the harness produces**. Commits after it are documentation only and leave
`asks_of` AST-identical, so they reproduce the same numbers; several of them have corrected
figures in this document, which is a different thing.
Harness: [`scripts/measure_value_walk.py`](../../scripts/measure_value_walk.py).

*The line above read `02b2fe03` until 2026-09-23 and was wrong in a way that made §7's
closing sentence false: `src/sextant/application/resolve/shadow.py` does not exist at that
commit, the reader there does not open `parse_calls`, and running §7's own command on it
yields 948 / 1,209 / 686 rather than the 989 / 1,250 / 726 reported below. A provenance line
a reader cannot check out is worse than none.*

**This was spec [§3a](../superpowers/specs/2026-09-22-value-resolution-design.md)'s gate.**
The approved ruling was *no cap in v1*, and that ruling was only safe if the measurement
happened before anything consumed the walk — otherwise "measure first" becomes "find out in
production". `resolve/values.py` shipped unwired **at the snapshot above**, and this document
is what §3a step 3 ruled on.

*Task 7 wired the first engine to it (2026-09-23) and gave the walk §2's identity table to
resolve through — a hop this harness's own figures were measured without, since it passes no
identities. **Measured rather than assumed, on the same 27 corpora**: over the whole asked
surface the identity arm adds **19 visits (413 → 432, +4.6%)** and leaves the maximum depth
at **3**. It pushes no path step — an identity hop resolves another slot of the SAME site —
so neither the path count nor the depth this ruling was made on can move, and the cost it
adds is bounded by the number of identified producers a corpus actually calls. The §6.1
condition below (re-run this harness before capability 9.19) is what keeps that a measurement
rather than a standing claim.*

*What it moves, on the same surface, is **16 of 1,026 answers**, at 16 of §2's **989** asked
positions: **13 conversions**, a miss becoming an answer, and **3 corrections**, where a
value built by an identified initialiser answered with the symbol of the type it was built
from and now answers with the value. The count of RESOLVED answers therefore rises by 13 and
not by 16 (552 → 565) — a correction was already a resolved answer, and a wrong one.*

*Round 1 of the Task 7 report gave the denominator as 1,053 and it does not reproduce. It
counted `(position, path)` keys off `resolve_site`, which COMBINES a site's slots — a
two-slot site with two paths each yields up to four bindings — where 552 and every other
figure in this document count `_Walk.at(site, slot)`, one per slot. Re-derived on that
basis: **989 positions, 1,026 answers (474 unresolved + 552 resolved), 16 moved**, which
agrees with §2's position count and with this document's own 552.*

> ## RULING (2026-09-23): **no cap.**
>
> `fan_out` and `depth` do **not** join §1d's reason vocabulary. Two conditions are attached
> to the ruling and are stated in full in §6:
>
> 1. **This harness is re-run before capability 9.19 (`written_by`) ships** — not after.
> 2. **Tasks 5–10 thread the `ValueIndex` rather than rebuilding it per call, and report
>    `visits` rather than wall time.**

---

## 1. How the measurement was made

### 1.1 The corpora — and what was not measured

Twenty-seven: every fixture that compiles, every example, and `mall-admin` — the largest
corpus available, 48 MB of facts across 648 documents, and the one §3a names. A corpus with
a full scan on disk (`.sextant/facts`, which includes the dependency jars the scan read) is
loaded from it; the rest are scanned from `target/classes` by the harness. Each corpus gets
a **fresh** workspace, loaded and then run through the two passes `value_edges` is
normalised out of (`record_return_flows`, `record_call_edges`) — nothing else in the
pipeline, because the edge query reads `call_sites`, `return_flows` and `call_edges` and the
walk reads `method_returns` beside them.

**"Twenty-seven" is a property of this working tree, not of the repository**, and the
harness now says so on every run. A module with neither built classes nor a scan is not
measured; today that is four — `gradle-orders`, `orders-reactor`,
`spring-petclinic-microservices`, `mall-search` — and the harness prints them as
`NOT MEASURED` so a later run's corpus count cannot be compared against this one's without
noticing. Priming them is `python tests/fixture_build.py` plus an analysis run over
`examples/`.

### 1.2 The positions — measured against real sites, never synthesised rows

`resolve_site` uses the row it is handed only to **name** the site; it resolves the
**projected** row for that `(caller, ordinal)` pair, so a synthesised row would be replaced
by the workspace's own and the measurement would be of something else. Every position here
is read out of `effective_call_sites` — the rows the engines see — through
`ValueIndex.sites`. Nothing is invented.

Two surfaces are measured, and the difference between them is the finding:

- **The asked surface** — every position a shipped catalog actually asks about.
- **The ceiling** — every argument **and the receiver** of every call site in every corpus,
  whether a catalog asks about it or not. Not what §3a asks for, and measured beside it
  rather than instead of it: a cap sized on today's asked surface alone would be
  re-litigated by the first catalog that asks somewhere new, and a ruling wants to know
  whether the corpus *holds* a pathological shape at all or merely fails to ask about one.

### 1.3 How an "ask" is found — six shapes in two blocks, audited, not derived

The shipped catalogs spell a position in **six** shapes, in **two** catalog blocks. **They
were found by auditing all 101 files, not derived from a grammar, and that is the standing
caveat on every count below:** a catalog that invents a seventh spelling is missed until the
audit is redone. This is not hypothetical — the first version of this harness had three of
the six and under-counted the asked surface by 20 positions.

The table below has **seven rows for six shapes**: its last row is shape one again, spelled
in `parse_calls` rather than in `matches`. A second BLOCK is not a seventh shape, and the
distinction is the one the amendment below turns on: what was missed for three rounds was a
block, not a spelling.

| shape | where | key occurrences |
|---|---|---|
| `arg` / `<name>_arg` integer beside a method name | `single_call`, `combinator`, `interface_implementation`, `supertype_dispatch`, `config_join` | most |
| `captures: {name: argN}` | `fluent` roots/steps/terminals | 139 |
| a **nested** capture, `captures: {channel_link: {bean_via: arg0}}` | `spring-integration-*` | 11 |
| a **sub-object** carrying slots while the method name stays on the parent — `ktor-routing`'s `request_requirement: {kind: header, name_arg: 1, value_arg: 2}`, `spring-kafka-message`'s `when: {arg: 0, equals: "kafka_topic"}` | `combinator`, `fluent`, `single_call` | 22 |
| `arg: all_strings` — **every** positional argument, a varargs array read as its elements (`shapes/arguments._all_string_channels`) | `kafka-consumer`, `kafka-streams`, `pekko-connectors-kafka` | 13 |
| `<name>_ctor_arg` against a wrapper `type` — a position on that type's **constructor**, so the method name is `<init>`; `payload_ctor_arg: last` is a rule resolved per site | `call_wrappers`, `record_wrappers` | 7 |
| `bytes_arg`/`class_arg` in the top-level **`parse_calls`** block — shape one, outside `matches` | `spring-web` | 8 |

> **Amended 2026-09-23, after Task 5. The reader was corrected twice and WIDENED once, and
> figures in this document moved.** It now lives in
> `src/sextant/application/resolve/shadow.py`; this harness imports it, because spec §3d's
> shadow table is written for exactly the positions measured here and two copies of "what
> does a catalog ask" would be two answers the day a catalog invents a spelling.
>
> * **Row six's count was wrong: 5, now 7.** Every row counts KEY OCCURRENCES that really
>   become an ask — 139 plain `captures`, 11 nested, 13 `all_strings`, all re-derived and
>   matching — and on that convention the four matching nodes (`kafka-clients`,
>   `spring-kafka-replying`, `spring-kafka-template`, `spring-resttemplate`, naming
>   `ProducerRecord` and `HttpEntity`) carry seven `_ctor_arg` keys between them.
> * **Row four's count was wrong too: 26, now 22** (derived 2026-09-23, the first time any
>   round checked it). It is **14 sub-object nodes carrying 22 arg-shaped keys** between
>   them, in `spring-cloud-gateway` (6 nodes / 12 keys), `ktor-routing` (4 / 6),
>   `spring-ws-template` (3 / 3) and `spring-kafka-message` (1 / 1). 26 reproduces under no
>   reading: nodes reaching the arm are 16, keys on them 24, slots they name 24, and the
>   emitting subsets are 14 and 22. The two excluded nodes are
>   `spring-cloud-stream.yml`'s `suffix[].payload_arg: 0`, which `shadow.py`'s own
>   *Which blocks are read, and which are refused* section accounts for — **not** the
>   short refusal list below, which names `wrappers`, `serialization`, `protocol_hint` and
>   `wrappers[].when` and has never named `suffix[]`. Counting them here would list one
>   occurrence as both a shape found and a key refused. Rows two, three and five are
>   unchanged by the same derivation — every one of their occurrences is on a node that
>   emits, and rows four and six are 22 keys on 14 nodes and 7 keys on 4 nodes, which is
>   what the KEY OCCURRENCES column heading means.
> * **Row six's match was narrowed** to require a `_ctor_arg` key: a `payload_arg` beside a
>   `type` is a generic type-argument index, not a call slot, so matching on the shape alone
>   would have been a wrong answer rather than slack. **No ask changed**, on any catalog.
> * **Row seven is new.** `parse_calls` is a top-level catalog block outside `matches`, and
>   its entries spell shape one exactly; `shapes/parse_binding.py` reads them as real
>   call-argument indices — `_argument_at(site, entry.bytes_arg)` at `:264`,
>   `_argument_at(site, entry.class_arg)` at `:329`, and `_argument_at` itself indexing
>   `site["arguments"]` at `:349`/`:352`. Eight positions this harness previously measured as
>   zero. **This is what moved the figures below**, and the moves are recorded where they
>   occur: the asked surface goes from 948 positions / 1,209 asks / 686 sites to
>   **989 / 1,250 / 726**, `orders-service` and `grpc-probe` are the two corpora affected,
>   and the maximum `visits` on the asked surface goes from 11 to **15**. The §5 ruling is
>   unchanged and the margins it rests on are unchanged. **What the widening added is very
>   largely SLACK rather than production reach** — the third over-match below measures how
>   much.
>
> `wrappers` (`payload_arg` x151 across 55 files), `serialization` (`arg` x70),
> `protocol_hint` and `wrappers[].when` (`annotation_arg` x2 and x1) are all read and
> REFUSED, each with the line of its consumer that settles it, in `shadow.py`'s own
> docstring. None is a call position.

**`all_strings` is the one spelling where a single catalog row asks about an unbounded
number of positions**, and it is the only bound-free thing in the ask grammar. It adds **20
positions across seven corpora**, and the two forms it meets show why the bound is absent:

- `jhipster-sample-app`'s `PublicUserResource#<clinit>`@0 calls `List.of` through its
  **seven-argument fixed-arity overload**, so one catalog row asks about seven positions at
  one site;
- `UserResource#<clinit>`@0 calls the **varargs** overload, so `all_strings` asks about the
  one array slot — and the WALK then answers **11 paths and 11 distinct answers** for it,
  because §1c's array rule enumerates eleven written constants. That is the asked surface's
  path-count and answer-count maximum, at a position that costs **zero** traversal.

It matches nothing in `mall-admin` or `mall-mbg`, and **that is luck rather than a bound**:
nothing there calls `List.of`, `Arrays.asList` or `Subscriptions.topics`.

### The three over-matches, and what they conceal

A row is matched to real call sites on the keys the engines match on: owner where declared
(converted through the catalogs' own `catalog_symbols`), method name, and the JVM
`descriptor` or the `arity` where the row declares either. **What this harness does not
model is the engines' *reachability*** — whether an engine would ever arrive at that row for
that site — and three classes of row are over-matched as a result.

**1. Rows declaring no owner are matched by method name alone.** `fluent`'s owner-free steps
are really scoped to a chain the engine has already rooted, and `ktor-routing`'s
`request_reads` reach their receiver through a `via` call. That is **24 of the 807 rows**,
and the names are common ones (`get`, `url`, `method`, `uri`, `post`, `put`, `body`):
`ktor-routing`, `okhttp` and `jdk-httpclient` alone account for 520 of the 1,250
catalog-to-position asks. **Of those 520, an owner-free row is the only thing that produced
258 — 49.6%** (`ktor-routing` 77 of 313, `okhttp` 136 of 136, `jdk-httpclient` 45 of 71);
the rest were also reached by a row that does declare its owner. Estate-wide the figure is
**402 of 1,250**. *(This sentence said "most of them" until 2026-09-23. The mechanism it is
attached to supports the measurement above and not that quantifier — under half, not most —
and how many of the 258 an engine would really refuse is a further question this harness
does not answer.)*

**2. Every `all_strings` row is a `channel_via`, which an engine reaches only by following a
`source` link back from a site it has already matched.** All thirteen of them
(`fluent.py`: *"`all_strings` is `channel_via`'s alone"*). This harness matches them by
owner plus method against every call site in the estate, so it asks about `List.of` and
`Arrays.asList` calls in modules that use no Kafka at all — and **this is the over-match that
produces the asked surface's path-count and answer-count maxima** (over-match 3 produces its
visit-count one; the depth maximum of 3 is reached by a genuine `ktor-routing` position as
well, so it is not an over-match's). Measured:

| corpus | positions `all_strings` adds | max paths / answers | would production ask? |
|---|---|---|---|
| `jhipster-sample-app` | **11** | **11 / 11** | **no** — the module contains no Kafka |
| `orders-pekko` | 2 | **2 / 2** | yes (`Subscriptions.topics`) |
| `orders-service` | 2 | 1 / 1 | yes |
| `orders-streams` | 2 | 1 / 1 | yes |
| `spring-integration-probe`, `mall-demo`, `mall-portal` | 1 each | 1 / 1 | no |

So §3.1's eleven-path maximum is attributed to `kafka-consumer` and `kafka-streams` at a
`jhipster-sample-app` site **those catalogs would never be asked about in production**.
**Restricted to the three corpora where a `channel_via` parent really matches —
`orders-service`, `orders-streams`, `orders-pekko` — these positions top out at 2 paths and
2 answers.**

**3. `spring-web`'s protobuf `parse_calls` row declares `owner_hierarchy` and not `owner`,
so this harness matches `parseFrom` by method name alone** — it is one of the 24 owner-free
rows of over-match 1, and it is the one the widening added. Production does not match that
way: `shapes/parse_binding.py`'s `_matches` (`:273`) falls through to `_reaches` (`:287`),
which walks the receiver type's *declared ancestry* for one of the four protobuf markers
(`MessageOrBuilder`, `GeneratedMessage`, `GeneratedMessageV3`, `GeneratedMessageLite`).
**Measured by running every site this harness matched through `_vocabulary` + `_matches` +
`_facts` themselves:**

| corpus | sites this harness asks about | production's matcher accepts | refuses |
|---|---|---|---|
| `orders-service` | 28 | **4** | 24 |
| `grpc-probe` | 12 | **0** | 12 |

Every refusal is the same one: the call's receiver is `com.google.protobuf.Parser`, a
library type with no ancestry fact in the module at all, so `_reaches` ends its walk
immediately. The four production really accepts are three `OrderProtos$OrderRequest#parseFrom`
receivers and one `JsonMapper#readValue` — **5 positions**, topping out at 3 paths, depth 2
and 9 visits. So the whole of `grpc-probe`'s new ask and 24 of `orders-service`'s 28 new
sites are slack, and **§3.1's fifteen-visit maximum is one of the refused ones**.

**All three over-matches are deliberate and all three are the safe direction:** this
measurement sizes a ceiling, so over-counting the asks can only make the answer more
conservative. But the second and third are worth saying out loud rather than leaving for a
reader to find, because of what they conceal: **the asked surface production will really
present is further from needing a cap than this document's own headline suggests.** Every
figure below is an upper bound on the asked surface, not an estimate of it — and no figure
below may be quoted as a *production* maximum without that discount applied.

### 1.4 Two bases, which are not interchangeable

| basis | asked surface | meaning |
|---|---|---|
| **catalog-to-position asks** | **1,250** | a distinct (catalog, position) pair. Two catalogs asking about one slot is two asks, and this is what the per-catalog and per-style tables add up to |
| **distinct positions** | **989** | a distinct `(site, slot)` — a walk that actually runs, whoever asked |

A **site** is a distinct `(caller, ordinal)` — one call, whatever slots are asked about on
it; the asked surface has **726**. Both rows above are defined in terms of it, and
`resolve_site` is called once per site (§1.5). It is deliberately not a basis for cost: a
maximum held at three sites may be held by any number of positions, so §3.1 and §5 each name
the unit they are counting in. Substituting the site count for the position count is an
error this document has made and corrected more than once.

Both bases are printed per corpus and in total. **Every cost figure in §3 is per distinct
position**; the asks number appears only where the question is "how much do catalogs ask",
never where the question is "how much does it cost".

(A third base exists and is deliberately not used: counting one catalog ROW per position
gives **2,038**, because a catalog often matches a site through more than one overload row.
The first draft of this document printed that number — 1,997, on the reader as it then was —
in a column headed "positions asked" beside a headline of distinct positions, which is the
mistake this section exists to prevent.)

### 1.5 What is recorded

Per position, from the walk's own return value — a tuple of `(path, answer)` pairs: **path
count**; **hop depth** (crossings on the longest path); **distinct answer count**, which is
not the path count — two callers passing the same literal are two paths and one answer;
**positions visited**, every `(position, path)` the walk computed, which is the work a cap
would bound; and wall time.

Per **site**: `resolve_site` itself is timed and its `Binding` count recorded, because
§3b's "potentially unbounded and multiplicative" is about the **combination** step.

**The index fold is timed beside both.** `value_index` folds five queries, and
`resolve_site` rebuilds it whenever a caller does not pass one — there is no cache anywhere,
and `Workspace.once` refuses this fold because two of the five are derived. It is reported
as a headline, not a footnote; §3.3 says why.

The walk's memo is per resolve and shared across one site's slots, so the harness builds one
`_Walk` per site and times each slot inside it — the production lifetime, not a friendlier
one. The subclass that counts computed positions lives in the harness; **nothing in `src/`
was changed for the measurement §3a gated** — that is a statement about `02b2fe03`, the tree
Task 4 measured, and not about the header's snapshot: `ad210319` is a `feat(resolve)` commit
that widened the reader and moved the figures here (§1.3). The §3a grep
(`grep -rn "resolve_site\|resolve.values import" src/sextant/ | grep -v "resolve/values.py"`)
was **empty at that tree**, which is what §3a ruled on.

**It is not empty at the header's snapshot, and that is Task 5 rather than a regression.**
At `ad210319` it returns five lines, all in
`src/sextant/application/resolve/shadow.py` and all five named: two docstring mentions
(`:146`, `:149`), the import of `resolve_site` and `value_index` (`:170`), a code comment
(`:481`) and **one call** (`:495`). Only the last executes anything. That is spec §3d's
shadow mode, which is the first consumer and is a RECORDER — it publishes nothing, and §3a's
gate was that the walk ship unwired *until this document existed*, not for ever. The reader
moved into the same file (§1.3's amendment), which is why the harness now imports from
`src/` too. **The gate is stated as of the tree it was a gate on**, because the header moved
and this sentence did not follow it.

**`scripts/` is not type-checked by `scripts/check.sh`** — the gate runs `mypy src`, and
`pyproject.toml` sets `files = ["src"]`. Ruff, by contrast, runs over the whole tree, so
this harness is lint-clean and format-clean but unverified by
mypy, and that is stated rather than fixed: bringing `scripts/` under the type gate is a
change to the gate, not to this task.

### 1.6 Wall time is not reproducible at these magnitudes; `visits` is

**Measured across six runs of the ceiling on identical input**: the maximum per-position
wall time was 2.1 ms, 2.1 ms, 2.3 ms, 2.3 ms, 32.4 ms and 32.7 ms — a **15× spread**, and
the 32 ms outlier was a 128-path position that other runs resolved in about 1 ms. The worst
*site* ranged 29–61 ms across the same runs. **In every one of those runs the maximum
`visits` was 1,559, the maximum path count 388 and the maximum depth 8, to the row.**

So: **no wall-time figure in this document is presented as a maximum.** Wall time appears
only as a total (where the noise averages out) or explicitly labelled noisy. `visits` is the
deterministic work figure, it is what the tail is ranked by, and it is what would be bounded
if anything ever were.

---

## 2. Answer 1 — how many positions shipped catalogs actually ask about

**989 distinct positions (1,250 catalog-to-position asks), across all twenty-seven
corpora.** The ceiling on the same corpora is **98,454**. The asked surface is **1.0%** of
it. *(948 / 1,209 / 0.96% before the reader was widened to `parse_calls` — see §1.3.)*

§3b's guard shape holds, and harder than it did on `orders-quarkus`:

| corpus | call sites | value edges | asks | **positions** | sites | positions / call sites |
|---|---|---|---|---|---|---|
| `mall-admin` | 25,057 | 59,254 | 56 | **56** | 52 | 0.2% |
| `mall-mbg` | 21,775 | 54,157 | 0 | **0** | 0 | 0% |
| `spring-petclinic-rest` | 3,037 | 4,032 | 48 | 44 | 44 | 1.4% |
| `mall-portal` | 2,200 | 2,434 | 43 | 42 | 42 | 1.9% |
| `orders-service` | 1,818 | 2,090 | 402 | 308 | 237 | 17% |
| `jhipster-sample-app` | 1,710 | 2,058 | 113 | 50 | 44 | 2.9% |
| `orders-ktor` / `-classlambdas` | 471 / 515 | 584 / 610 | 133 | 123 | 49 | 26% / 24% |
| `spring-integration-probe` | 198 | 183 | 90 | 52 | 52 | 26% |
| `grpc-probe` | 391 | 539 | 12 | 12 | 12 | 3.1% |
| `orders-quarkus`, `orders-spring7`, `orders-soap-final`, `orders-soap-client` | 13 / 13 / 6 / 0 | 7 / 5 / 0 / 0 | 0 | **0** each | 0 | 0% |

Four of the twenty-seven corpora ask about **nothing at all**, and `mall-mbg` — 21,775 call
sites of MyBatis-generated model code, which is exactly where the estate's worst shape lives
— is a **fifth**. It was five plus `mall-mbg` until `parse_calls` was read, and that move is
one the reader made and production did not: **`grpc-probe`'s twelve protobuf `parseFrom`
positions are asked about by this harness and by shadow mode, and refused by production's
own matcher — all twelve** (§1.3, over-match 3). On the engines' own terms `grpc-probe`
still asks about nothing. The biggest corpus in the estate asks about 56 positions. The
fixtures ask proportionally far more because they exist to exercise catalogs; the real
applications do not.

Which catalogs ask (asks, so one position once per catalog that asks about it; these sum
to the 1,250):

| engine style | asks matched | catalogs that name a position |
|---|---|---|
| `combinator` | 467 | 5 of 5 |
| `fluent` | 441 | 12 of 12 |
| `single_call` | 274 | 30 of 30 |
| `annotation_driven` | 41 | 1 of 38 |
| `supertype_dispatch` | 18 | 2 of 2 |
| `interface_implementation` | 9 | 1 of 1 |

Fifty-one of the 101 shipped catalogs name a call-site position at all; 48 of those matched
something somewhere. **The other 50 name no call-site position**, and 37 of them are
`annotation_driven` — they ask about annotation attributes alone, which this walk does not
serve. The remaining **13 are not**: `graphql-schema`, `grpc-java`, `grpc-net-devh`,
`grpc-schema`, `spring-advice`, `spring-cloud-gateway-properties`, `spring-cloud-stream`,
`spring-data-rest`, `spring-integration`, `spring-kafka-media`, `spring-scheduling`,
`spring-stomp-advice` and `wsdl-schema` — three `schema_operations`, four `config_join`, two
`error_advice`, and one each of `supertype_derived`, `injected_client`, `derived_resource`
and `scheduled_work`. What each of those reads instead is not measured here; what is
measured is that they are not annotation catalogs, so saying "the other 50 ask about
annotation attributes" was wrong in thirteen cases.
**The one `annotation_driven` catalog that does name a position is
`spring-web`**, and it is there only through `parse_calls` — its `matches` block names none.
That row was absent until the reader was widened (§1.3); before it, the line read
"Fifty ... 47 ... the other 51 — `annotation_driven` and its relatives".

---

## 3. What the walk costs — distribution, maximum and tail

**No mean appears below.** A mean hides the pathological module, which is the only thing
this measurement is for.

### 3.1 The asked surface: 989 positions, 726 sites

*(948 / 686 before the reader was widened to `parse_calls` — §1.3. Every figure in this
section was re-measured after the widening; the five cells that moved are marked.)*

**Percentiles are the harness's own** — `percentile()` is `ordered[round(f * (n - 1))]`, a
nearest-rank-on-the-interior rule, and this table reports the instrument rather than
restating it under a different convention. On 989 values p99.9 is therefore the second
largest, not the largest; a nearest-rank-**ceiling** reading would put the maximum in the
p99.9 column and did, in this table's previous revision.

| figure | p50 | p90 | p99 | p99.9 | **max** |
|---|---|---|---|---|---|
| paths per position | 1 | 1 | 2 | 5 *(was 3)* | **11** |
| hop depth | 0 | 0 | 1 | 3 *(was 2)* | **3** |
| distinct answers | 1 | 1 | 2 | 3 | **11** |
| positions visited | 0 | 1 | 5 *(was 4)* | 11 *(was 7)* | **15** *(was 11)* |

`resolve_site` over the same sites: **max 11 bindings** (p99: 3).
**Totals across all twenty-seven corpora: index fold 0.38 s, walking 1.7 ms,
`resolve_site` 4.3 ms.**

Path-count distribution: 972 positions have one path, 7 have two, 8 have three, one has
five, **one has eleven**. Depth: 906 at 0, 77 at 1, 4 at 2, 2 at 3.

**Both maxima are over-matches; rows three and four are the figures production can really
be handed.** The table names each row's status rather than leaving it to §1.3:

| what | position | paths | depth | answers | visits |
|---|---|---|---|---|---|
| most paths, most answers, most bindings — **over-matched (§1.3, no. 2)** | `jhipster-sample-app` `UserResource#<clinit>`@0 slot 0 (attributed to `kafka-consumer`, `kafka-streams` via `all_strings`; the module has no Kafka, so production never asks) | **11** | 1 | **11** | 0 |
| most work — **also over-matched (§1.3, no. 3)** | `orders-service` `OrderProtos$OrderRequest#parseFrom`@0 slot 0 (`spring-web`, through `parse_calls`). Its callee is `com.google.protobuf.Parser#parseFrom`, a library type with no ancestry fact, and production's `_matches` refuses it | 5 | **3** | 1 | **15** |
| **the most work at a position production really asks about** | `orders-ktor-classlambdas` `KtorRoutesKt#mount`@5 slot 0 (`ktor-routing`, on `RoutingBuilderKt.route` — owner declared, arity 3 matched, so no over-match applies) | 3 | 2 | 1 | 11 |
| deepest — and **production really asks about this one too**, so depth 3 is not an over-match's | `orders-ktor-classlambdas` `KtorRoutesKt#orders2`@2 slot 0 (`ktor-routing`, on `RoutingBuilderKt.get` — owner declared, arity 3 matched) | 1 | **3** | 1 | 7 |

The eleven-path case does **no traversal at all** — `visits` is 0, because it is one varargs
array argument holding eleven written constants and §1c's array rule enumerates them on the
spot. On the corpora where that catalog row is genuinely reachable the same shape gives
**2 paths**.

The fifteen-visit case is the one the `parse_calls` widening added, and §1.3's third
over-match is the reason it cannot be read as a production figure: at that site the callee
is `Parser`, not a generated message, so production's own matcher never arrives. **Where the
protobuf row really binds — the four accepted sites on `orders-service`, five positions —
the same shape tops out at 3 paths, depth 2 and 9 visits.**

**The maxima that survive all three discounts: 3 paths, depth 3, 3 answers, 11 visits.**
Measured by classifying all 989 positions by whether any **owner-declared,
non-`all_strings`** ask matches them — exactly the negation of over-matches 1, 2 and 3 —
which leaves **664 genuine positions**. No one position holds all four. The holders are
**seven positions** (§1.4's unit: a distinct `(site, slot)`) at **three sites**, and **no
fewer than three positions** carry all four maxima between them — `mount`@5 slot 1 for
answers, `mount`@5 slot 0 for paths and visits, `orders2`@2 slot 0 for depth. Position and
site are two counts here and are not interchangeable:

| maximum | value | held by |
|---|---|---|
| paths | 3 | `KtorRoutesKt#mount`@5 slots 0, 1 and 2, in **both** `orders-ktor` and `orders-ktor-classlambdas` — six positions |
| distinct answers | 3 | `KtorRoutesKt#mount`@5 **slot 1**, in both corpora — two positions |
| positions visited | 11 | `orders-ktor-classlambdas` `KtorRoutesKt#mount`@5 **slot 0** — one |
| hop depth | 3 | `orders-ktor-classlambdas` `KtorRoutesKt#orders2`@2 slot 0 — one; callee `RoutingBuilderKt.get`/3, against an ask declaring that owner and that arity |

Row 3 of the table above is the visits holder and carries **1** answer, not 3; the answers
maximum is its sibling slot. The shape the widened `parse_calls` row can really hand the
walk — `orders-service` `OrderIngest#process`@0 slot 0, 3 paths / depth 2 / 1 answer / 9
visits — is **no larger than any of the four, and equal to the first**. There is no tail on
any reading.

### 3.2 The ceiling: 98,454 positions, 50,112 sites

| figure | p50 | p90 | p99 | p99.9 | **max** |
|---|---|---|---|---|---|
| paths per position | 1 | 1 | 24 | 124 | **388** |
| hop depth | 0 | 1 | 2 | 4 | **8** |
| distinct answers | 1 | 1 | 5 | 78 | **386** |
| positions visited | 1 | 3 | 49 | 355 | **1,559** |

`resolve_site` over every site: **max 388 bindings** (p99: 24).
**Totals: index fold 0.40 s, walking 0.41–0.44 s, `resolve_site` 1.08–1.09 s** (two runs).

Depth is genuinely shallow: 75,721 positions at 0, 20,708 at 1, 1,302 at 2, 618 at 3, 61 at
4, 35 at 5, 7 at 6, 1 at 7, **1 at 8**.

**The single pathological shape in the estate, stated whole rather than by its kind half.**
It is `mall-admin`'s `com/macro/mall/model/OmsOrderExample$Criterion#<init>`@0 — MyBatis
Generator's `…Example$Criteria` builder, whose `addCriterion(String, Object, String)` is
called from a few hundred sibling methods in the same class, each passing its own literals.
One site, three slots:

| slot | paths | depth | **distinct answers** | visits |
|---|---|---|---|---|
| 0 (the condition) | 386 | 2 | **386** | 389 |
| 1 (the value) | 388 | 5 | 1 | **1,559** |
| 2 | 1 | 0 | 1 | 0 |

**`resolve_site` returns 388 bindings for that site**, in 29–61 ms depending on the run.
Slot 1 collapses 388 paths to one answer; **slot 0 does not — it yields 386 distinct
answers** — and the site's binding count is what an engine would actually receive. The
earlier draft of this document quoted slot 1 alone, which was the reassuring half; the
ruling in §5 is made over the whole site.

388 paths is the **correct** answer there: each is a real calling context, and the
per-caller correlation is exactly what §1c's per-path rule exists to keep. The shape repeats
once per generated table (`PmsProductExample` 337, `OmsOrderReturnApplyExample` 246,
`UmsAdminExample` 98 — which is also the one position in the estate at depth 8).

### 3.3 The index fold is comparable to the walk, and is nobody's yet

| | asked surface | ceiling |
|---|---|---|
| index fold, all corpora | **0.38 s** | 0.40 s |
| walking | 0.0017 s | 0.41–0.44 s |
| `resolve_site` incl. combination | 0.0043 s | 1.08–1.09 s |

On `mall-admin` alone the fold is **0.16 s** — more than every walk in that corpus put
together, by three orders of magnitude on the asked surface. It is **irrelevant to the cap**
and it is the largest cost this measurement found on the surface that will actually be used.

`resolve_site(workspace, site)` **rebuilds the whole fold** when no index is passed, and
nothing caches it: `Workspace.once` refuses it, because `value_edges` and `call_edges` are
derived and a derivation run after the fold would leave it stale. So an engine that calls
`resolve_site` per site without threading an index pays 0.16 s **per call** on `mall-admin`.
That is the shape §6's second condition exists to prevent.

### 3.4 The multiplicative risk did not materialise

§3b's stated danger is the **combination**: two slots with independent fan-out would
multiply. **The test is `bindings > max(paths) over that site's slots`** — stated here
rather than left implicit, because it is the one figure in this document that did not
reproduce when it was checked, and the next reader should not have to guess the reading.
Across all 50,112 sites of the ceiling run it is true at **11 sites**, and the largest
multiple anywhere is **3×** (`jhipster-sample-app`'s `ExceptionTranslator#buildCause`@2: 15
bindings over a 5-path slot; the next is 2×, at ten sites, nine of them a generated
`equals`). At the 388-path shape the binding count is also 388 — the coherence rule holds it
linear, because those slots cross out of the same method through the same call and M-1's
rule makes that one choice rather than a product.

*Corrected 2026-09-23: this sentence said **48 sites**, and 48 does not reproduce under that
reading or under any of `>=`, ratio > 1, multi-slot only, against max answers, against min or
sum or product of slot paths. The measured value is 11, and the conclusion is the one it
already drew, more strongly.*

No site anywhere returned **zero** bindings, so the coherence rule is not silently deleting
answers on real code either.

---

## 4. Answer 2 — which `unresolved` reasons fire on real code

**On the asked surface (989 positions, 474 unresolved answers):**

| reason | count | never fires? |
|---|---|---|
| `external` | 252 | |
| `not_readable` | 190 | |
| `no_writer` | 13 | |
| `escapes` | 12 | |
| `non_enumerable` | 7 | |
| **`cycle`** | **0** | **never, on anything a shipped catalog asks about** |

Answer kinds on the asked surface: `literal` 531, `unresolved` 474, `expression` 21,
**`absent` 0**.

*Before the reader was widened to `parse_calls` (§1.3): 948 positions, 428 unresolved,
`external` 206, `literal` 530. **The widening added 47 answers — 46 `external` and one
`literal`**, which is what this section's own 206 → 252 and 530 → 531 say. A `parseFrom` or
`readValue` argument mostly comes from outside what was scanned, which is the boundary
`external` exists to name. No reason changed rank and none became reachable or
unreachable.*

**On the ceiling (98,454 positions, 91,522 unresolved answers):**

| reason | count |
|---|---|
| `external` | 76,773 |
| `not_readable` | 6,979 |
| `escapes` | 4,380 |
| `no_writer` | 3,321 |
| `non_enumerable` | 62 |
| `cycle` | **7** |

Answer kinds: `unresolved` 91,522, `literal` 83,304, `absent` 915, `expression` 528.

*The `escapes` row reads **3,706** since Task 7 opened the mutation window at a value's
CONSTRUCTION rather than before it — the §6.3 bullet below has the measurement and the
reason. It is left at the snapshot's own figure here, because this table is what the walk
answered at `ad210319` and a table half re-measured is worse than one that is not.*
**This table counts ANSWERS; a position may hold several.** On a POSITION basis the same
`escapes` population is 4,338 → 3,664, which is the same movement of 674 counted twice.

**So no reason is dead vocabulary** — all six are produced by real code, and so is `absent`.
Two of them are only reachable outside what catalogs ask about today, and the report has to
say which is which:

- **`cycle` fires seven times in the whole estate, at six positions** — one position answers
  it twice, on two different paths, which is why the two counts differ. All six are genuine
  recursion:

  | corpus | position | cycle answers |
  |---|---|---|
  | `orders-service` | `SoleRefiner#shorten`@0 slot 0 | 1 |
  | `orders-service` | `TraceProbe#describe`@5 slot 0 | **2** |
  | `jhipster-sample-app` | `ExceptionTranslator#buildCause`@2 slot 2 | 1 |
  | `jhipster-sample-app` | `ExceptionTranslator#customizeProblem`@25 slot 0 | 1 |
  | `jhipster-sample-app` | `ExceptionTranslator#customizeProblem`@31 slot 1 | 1 |
  | `jhipster-sample-app` | `ExceptionTranslator#getPathValue`@1 slot 0 | 1 |

  **The word is earned and the termination rule is exercised** — but nothing a shipped
  catalog asks about is recursive, so this is a gap in the *asked surface*, not in the
  corpus and not in the vocabulary.
- **`absent` never appears on the asked surface** (915 times on the ceiling). Explicit
  `null` and zero-length varargs happen constantly in application code and never in the
  positions a framework catalog reads a destination or a payload out of. Ruling T-2's answer
  kind is correct and, for now, only the ceiling produces it.
- `non_enumerable` is the rarest reason that fires either way (62 of 98,454). Task 3's
  report already records why: it is reachable **only** through the array rule, because a
  loop-built or branch-merged value arrives as an unread argument and no fact says it was a
  loop. That prediction is confirmed here by the count.
- `escapes` is 4.8% of unresolved answers on the ceiling and 2.5% on the asked surface
  (12 of 474; it was 2.8% of the narrower 428 before the widening),
  which is in line with the 13.4% the Task 3 fix round measured over the narrower
  return-crossing population.

---

## 5. The ruling: no cap, and why the data carries it

**Ruled 2026-09-23. `fan_out` and `depth` do not join §1d.** What the data supports:

1. **The asked surface is not near any plausible cap, on any corpus.** Max 11 paths (one
   varargs array of eleven written constants, enumerated on the spot at zero traversal
   cost), max depth 3, max 15 positions visited, max 11 bindings. Every position every
   shipped catalog asks about, across twenty-seven corpora including the 48 MB one, walks
   in **1.7 ms total**. A cap would never fire — and the margin is **larger** than these
   figures say, because **both of those maxima are over-matches** (§1.3). The 11 paths is
   §1.3's `channel_via` artefact: where that row is genuinely reachable the same shape gives
   2 paths. The 15 visits is §1.3's third over-match: the `spring-web` protobuf row declares
   `owner_hierarchy`, this harness matches `parseFrom` by name alone, and production's own
   matcher refuses that site along with 23 others on `orders-service` and all 12 on
   `grpc-probe`; where the row really binds the same shape gives 3 paths and 9 visits.
   **Restricted to the 664 positions an owner-declared, non-`all_strings` ask matches — the
   negation of all three over-matches — the maxima are 3 paths, depth 3 and 11 visits**.
   Seven POSITIONS hold one or another of those three, at **three SITES** across the two
   Ktor corpora, and **two positions carry all three between them** — both in
   `orders-ktor-classlambdas`: `KtorRoutesKt#mount`@5 slot 0 (3 paths *and* 11 visits) and
   `KtorRoutesKt#orders2`@2 slot 0 (depth 3). §3.1 names every holder; §1.4 is why position
   and site are spelled apart here.
   Every one of those is further below the crash barrier this section's closing paragraph
   sizes at 512 paths and 16 crossings than the unrestricted figures are.

   *Max visits was 11 and the total 1.6 ms when this was ruled; both moved when the reader
   was widened to `parse_calls` (§1.3), which is a re-measure and not a re-ruling — the
   ruling is made over the CEILING as much as over this surface, and the ceiling did not
   move at all. 15 against a crash barrier the same paragraph sizes at 512 paths and 16
   crossings is the same answer it was.*
2. **The ceiling is not near one either, and it is the number that matters** because it is
   what the asked surface could grow into. Resolving **every argument and receiver of every
   call site in the estate** — 98,454 positions, 50,112 `resolve_site` calls — costs
   **0.41 s of walking and 1.08 s including combination**. Against that, the pipeline's own
   `call_edges_insert` pass spends 8.9 s on `mall-admin` alone.
3. **The worst shape in the estate is correct rather than pathological**, and it is correct
   at its hardest slot too: `OmsOrderExample$Criterion#<init>`@0 returns **388 bindings**,
   386 of them carrying **distinct** answers, from 388 real calling contexts. A `fan_out`
   cap set anywhere below ~400 would refuse a site the walk resolves correctly in tens of
   milliseconds, and would refuse it with a word meaning "we gave up" — the precise
   undiagnosable miss §1d's six reasons exist to abolish.
4. **Depth is bounded by the code, not by luck.** 97.9% of positions are at depth 0 or 1;
   exactly one position in 98,454 reaches depth 8. Termination is already guaranteed by the
   path (`cycle`, §4), and the measurement shows the path does not get long.
5. **The multiplicative risk §3b names is real but small**: at most 3× anywhere, and 1× at
   the fan-out extreme, because the coherence rule holds it.

**If a cap is ever ruled in**, the data names where it would have to sit to cost nothing:
`fan_out` at **512 paths per position** and `depth` at **16 crossings**, both well above the
measured maxima of 388 and 8, which would make them a crash barrier rather than a policy.
Anything tighter starts refusing answers the walk gets right today. And it would have to
bound **`visits`, not wall time** — §1.6 shows wall time varying 15× run to run on identical
input while `visits` reproduces to the row.

---

## 6. The two conditions attached to the ruling

**These are what makes "no cap" safe later, and they are conditions rather than notes.**

### 6.1 Re-run this harness before capability 9.19 (`written_by`) ships — not after

Every binding read ends at `no_writer` today: 3,321 of them on the ceiling, 13 on the asked
surface. **Each is a walk that stops immediately** because `value_edges` emits no
`written_by` row for anything to follow. When capability 9.19 lands and the sixth edge
exists, every one of those becomes a real traversal into whatever writes the binding, and
none of the numbers above constrains what that costs. A binding written from many places is
structurally the same fan-out as `addCriterion`'s 388 callers, and nothing here has measured
it because nothing here could.

So: **9.19's own gate includes re-running `scripts/measure_value_walk.py` and re-reading
§5.** This is not a suggestion to re-measure at some point; it is the condition under which
the no-cap ruling continues to hold.

### 6.2 Tasks 5–10 thread the index, and report `visits`

Both halves follow from §3.3 and §1.6.

- **Thread the `ValueIndex`.** `resolve_site(workspace, site)` with no index rebuilds the
  whole five-query fold, which costs 0.16 s on `mall-admin` — more than every walk in that
  corpus put together. There is no cache and there cannot be one in `Workspace.once`. An
  engine resolving `mall-admin`'s **52 asked SITES** without threading an index would pay
  about 8 s where the work itself is under a millisecond — SITES, because `resolve_site` is
  called once per site and the fold is what each call rebuilds. §1.4's two bases are asks and
  positions, and on this corpus both are **56**; neither is the number that multiplies here. Each migrated engine builds `value_index(workspace)` once per run and passes
  it to every `resolve_site` call.
- **Report `visits`, not wall time.** A migration that claims "the walk is fast here" from a
  wall-time reading is reading noise: §1.6 measured a 15× spread on identical input. Where
  §3c's per-engine diff wants a cost figure, it is the positions-visited count.

### 6.3 What else would reopen the ruling

- A corpus whose generated code is an order of magnitude larger than `mall-mbg`'s **and** a
  catalog that asks about a position inside it. Today those two conditions never co-occur:
  the corpus with the fan-out asks about nothing, and the corpora that ask have no fan-out.
- **A codebase whose Kafka topic list is long**, reached through a `channel_via` spelling
  `arg: all_strings`. It is the only ask in the grammar with no bound on how many positions
  one row claims. Nothing here measures that case: the corpora where such a row is genuinely
  reachable hold short lists (max 2), and the eleven-element list this harness found is in a
  module with no Kafka, so it is the over-match rather than the case (§1.3).
- A catalog that asks about a **receiver**. The asked surface is arguments only; the ceiling
  includes receivers, so the headroom is already measured, but the mix would shift towards
  the `escapes` check.
- A seventh ask spelling, which this harness would silently not see (§1.3).
- **A `value-models/` entry that identifies a producer this estate calls often, or a chain
  of them.** The identity arm (Task 7, the note under the ruling above) costs one `_resolve`
  per hop and pushes no path step, so it cannot move the path or depth figures — but the
  harness itself passes NO identities, so its `visits` column is the walk without them. The
  gap is +4.6% at 25 shipped entries and is re-derived by the §6.1 re-run rather than by
  this sentence.
- **A corpus that CONSTRUCTS the values its catalogs read**, rather than obtaining them from
  static factories. Reaching an initialiser also moved `escapes` to where it belongs: an
  initialiser produces no value of its own, so `produced_by` carries no edge for it and the
  mutation window used to open before the construction itself. MEASURED over the ceiling —
  §3.2's own **98,454 positions**, all 27 corpora — **707 positions move**: **674** where the
  window now opens at the construction and **33** where an identity entry reaches one.
  Counted a second way and independently, positions answering `escapes` fall **4,338 →
  3,664**: the same 674. (§5's reason table counts ANSWERS rather than positions, where the
  same population reads 4,380 → 3,706 — a note beside that row says so.) **None** of the 707
  is a position any catalog asks about, so no figure above moves and the reason vocabulary is
  more truthful than it was.

  *Round 1 of the Task 7 report gave "719 of 208,430", which contradicted §3.2 by 2.1× and
  does not reproduce. Same cause as the asked-surface denominator above: it counted
  `(position, path)` keys off `resolve_site` rather than positions. Re-derived on §3.2's own
  basis, twice and independently — by diffing per-position answers and by counting `escapes`
  answers before and after.*

---

## 7. Reproducing this

```bash
JAVA_HOME=… .venv/bin/python scripts/measure_value_walk.py            # the asked surface
JAVA_HOME=… .venv/bin/python scripts/measure_value_walk.py --all-slots # the ceiling
```

Both print which modules were **not** measured, the per-corpus tables on both bases, the
worst positions and worst sites by name, and the reason distribution; `--json OUT` writes
every row and `--corpus NAME` limits the run. Over all twenty-seven corpora the asked
surface takes **6.9 s** and the ceiling **9.0 s** (measured 2026-09-23), almost all of it
loading facts.

**Two figures here are not printed by either command**, so a reader reproducing them needs
the definition, and — since the two are not obtained the same way — the data source too:

* **§3.4's multiplicative count** is `bindings > max(paths)` over each site's own slots, and
  it **is** derivable from `--json` output: join `rows` to `site_rows` on
  `(caller, ordinal)`.
* **§3.1's and §5's restricted maxima**, over the 664 positions matched by at least one
  **owner-declared, non-`all_strings`** ask, are **not**. The JSON's per-position `catalogs`
  field carries catalog NAMES, and owner-declaredness is a property of the individual `Ask`,
  not of the catalog that holds it — `ktor-routing` has both kinds. Reproducing the 664
  means re-running `positions_asked`'s matching loop with each match's own `Ask` in hand and
  tagging the position from it; no function of the JSON separates them.

Every deterministic figure in this document reproduces exactly across runs, **at the
snapshot named in the header**; an older reader answers a different question, which is what
the corrected provenance line is for. Wall time does not reproduce, and is labelled wherever
it appears.
