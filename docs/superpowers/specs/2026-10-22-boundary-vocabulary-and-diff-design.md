# The boundary vocabulary, the derivation diff and the observability map — design

**Status: PROPOSED 2026-10-22; the user ruled 2026-10-22 to build the whole group ("don't shrink it. build it anyway") and is ruling §7's decisions one at a time — ALL RULED 2026-10-22 — the plan follows (`../plans/2026-10-22-boundary-vocabulary-and-diff.md`).** Group H of the register
(`docs/java-kotlin-delivery-list.md` §4): `FR-21` boundary vocabulary, `FR-22` derivation
diff, `FR-23` observability map, `FR-24` library embedding — *"asked for four times"*, written
into `REQUIREMENTS.md` on 2026-09-10 and built by nothing since. The consumer is Meridian
(`docs/meridian-integration.md`): a gate that compares what Sextant OBSERVED changed against
what a ticket SAID would change, and derives its "machine-verified" tags from what Sextant
could see.

**One thing this is not.** The agent query surface — M09 as a CLI and a coding-agent plugin,
`symbol find`/`callers`/`impact` — is gated on language coverage by the user's ruling of
2026-09-18 and stays gated. `FR-24` names a `query` operation; §5 says what happens to it.

---

## 1. Measured first: what a boundary-level diff actually says

Two analyses of one module, every derived table set-differenced on candidate identities.
Nothing about the diff was built for these numbers; they are DuckDB over the exported
Parquet, exactly the join NFR-3 promised.

### 1a. The fixture, before and after PR #61 (two conditional controllers added)

| table | before | after | by candidate identity |
|---|---|---|---|
| `endpoints` | 234 | 236 | **+2 −0** on (protocol, direction, method, path); the same +2 −0 with every attribute compared — not one of the 234 existing rows moved |
| `shapes`, `shape_fields` | 30 / 56 | 30 / 56 | +0 −0 |
| `resolved_config` | 26 | 28 | +2 −0 (`orders.legacy` in `default` and `prod`) |
| `roots` | 144 | 146 | +2 −0 |
| `scheduled_work`, `error_handlers`, `endpoint_metadata` | | | +0 −0 |
| `call_edges`, `symbols`, `type_hierarchy`, `raw_facts` | 1820 / 1237 / 407 / 4961 | 1822 / 1243 / 409 / 4984 | sub-boundary churn: correctly invisible to a boundary diff |

Identity held exactly. The one table the two bundles do NOT share is `endpoint_conditions`
(graph schema 2 → 3): a diff across that pair must refuse by name, which is §3c.

### 1b. Real history: `spring-petclinic-rest`, six months (`f957c77` 2026-03-05 → `4cd8e1b` 2026-09-01)

Upstream, in those six months: pagination added for owners and pets (two `v2` routes, two
page DTOs) and *"refactor(rest): organize controllers by version and split v2 APIs"* — every
controller moved from `rest/controller/` into `rest/controller/v1/` and renamed `…V1`.
41 files, 530 insertions.

| identity of an `endpoint` | the diff says |
|---|---|
| (protocol, direction, method, path) — the WIRE | **+2 −0**: `GET /petclinic/api/v2/owners`, `GET /petclinic/api/v2/pets` |
| the wire + the handler symbol | **+44 −42**: every route "removed" and "added" because its controller changed package and name |
| `data-contract` by shape symbol | +2 −0 (`OwnerPageDto`, `PetPageDto`); with `content_hash`: the same two — no existing contract changed |
| contract field by (shape, wire name) | +10 −0 |
| `boundary-property`, `error handler`, `schedule`, endpoint requirement | +0 −0 |

The first row is what happened to the architecture. The second row is what happened to the
code. `FR-22`'s own sentence — *"the diff answers 'did the architecture change', not 'did
the code change'"* — picks the first, and §2 makes the handler **evidence** rather than
identity or attribute. This measurement is why (decision 1, §7).

**Uniqueness, measured on the fixture's 236 rows:** the wire alone names 212 distinct
endpoints — `GET /**` is served by four handlers, `sqs orders-poll` has four consumers,
`POST /v1/orders` is called from three places. So an entry of kind `endpoint` is one WIRE
identity with a SET of grounding symbols, never one row per handler (§2).

### 1c. What the manifest already carries for FR-23

From the fixture's own `manifest.json`: `uncovered: []`; `skipped_catalogs` with the reason
each was skipped (`spring-rsocket` — no RSocket artifact in the resolved dependency set);
`coverage.partial_documents: 0`, `coverage.method_resolution` (`owner_not_scanned: 427`),
`coverage.reach` (`body_read: 535`, `boundary: 1287`); `gaps` — **a static list of 13 names
every manifest carries** (`egress/render/metadata.py::KNOWN_GAPS`), Sextant-wide stated
boundaries rather than per-analysis measurements; `environments`; `producer` with four
stamps. FR-23 is an assembly over these, as REQUIREMENTS says — but §4 is careful about
which of them is a measurement of THIS analysis and which is a statement about Sextant.

---

## 2. FR-21 — the vocabulary

A closed, versioned set of **kinds**, each naming the table it derives from, the columns
that IDENTIFY an entry, the columns that are its ATTRIBUTES (what `from`/`to` range over in a
`changed`), and the columns that are EVIDENCE (carried on every entry, compared by nothing).
`boundary_vocabulary_version = 1`, written beside the other three stamps in `metadata.json`
and the bundle manifest's `producer`.

| kind | derived from | identity | attributes (`changed`) | evidence |
|---|---|---|---|---|
| `module` | `metadata.json` `module` | module id | kind, languages, `dependency_source` | — |
| `endpoint` | `endpoints`, inbound | protocol, method, path (the exposed address, per protocol: topic for a broker, operation name for GraphQL, the operation's QName for SOAP) | request body and response body as field sets by wire name (each change labelled `compatible`/`breaking` by M06 step 3's test), consumes, produces, format, the requirement set (`endpoint_metadata`), the condition set (`endpoint_conditions`), resolution | handler symbols, documents |
| `dependency` | `endpoints`, outbound | protocol, method, path, peer | request body and response body as field sets by wire name (labelled as for `endpoint`), format, the header set (`endpoint_metadata`), resolution | caller symbols, documents |
| `data-contract` | `shapes` + `shape_fields` | shape symbol (`shape_id`) | `content_hash`; the field set as (wire name → wire type, format, required, nullable) so a `changed` names the field | the declaring document, `origin_tier` |
| `boundary-property` | `resolved_config` | key, environment | value (as the exit masks it), `unresolved_reason` | source file |
| `schedule` | `scheduled_work` | handler, trigger | expression, resolution | catalog |
| `error-handler` | `error_handlers` | handler, exception | advice, scope, status, response shape | catalog |

Rulings this table rests on, each measured in §1:

* **The wire is the identity; the symbol is evidence** (§1b). An endpoint that moved
  controller is the same endpoint; the entry's evidence shows the new symbols to anyone who
  looks, and the diff says nothing, because nothing on the wire changed.
* **One entry per wire identity, a SET of grounding symbols** (§1b uniqueness). Four
  handlers behind `GET /**` are one endpoint with four pieces of evidence.
* **A `dependency` keeps `peer`** in its identity because `POST /v1/orders` on `billing` and
  on `ledger` are two dependencies; a module-scope diff cannot resolve the peer to a
  participant and does not try. System-scope `dependency` over `links` is **not in this
  spec** (§6).
* **`data-contract` identity is the shape symbol**, never the content hash — the hash is
  what CHANGES when a field is added, which is the `changed` entry the drift scenario
  exists for. A bare-name shape (`AuditEntry`, a declared schema) is identified by that
  name, as `shapes` already does.
* **Meridian's five names are kept where they map** (`module`, `endpoint`, `dependency`,
  `data-contract`, `boundary-property`; `service` is `module` with `kind: service`); the two
  non-wire tables Sextant publishes and Meridian did not foresee (`schedule`,
  `error-handler`) are kinds too, because the vocabulary names what Sextant DERIVES, and
  leaving a published table out of it would make a change there invisible to the one
  consumer the vocabulary exists for. Decision 2, §7.
* **Enrichment never enters.** Components, prose, overlays: judgements, not facts
  (`meridian-integration.md` §0a).

The vocabulary is **data**: one registry (`application/boundary/vocabulary.py`) listing the
kinds with their column sets, read by the diff, the observability map and the exporter. Each
kind's rows come from ONE named query (`boundary_<kind>`) in `storage/duckdb/workspace.py`'s
registry, which already serves every other reader of the same tables (D01 §5's rule: shipped
as part of the schema, never written per consumer).

---

## 3. FR-22 — the diff

### 3a. Interface

```
sextant module diff <a> <b> [--out diff.json]
api.diff(a: Path, b: Path, *, allow_producer_change: bool = False) -> DiffResult
```

`a` and `b` are each a module **workspace** (`<module>/.sextant`) or a **bundle** directory
(`…/bundles/<id>@<commit>/`), any mix: both hold the same tables, one as DuckDB and one as
Parquet, and both are opened read-only. Two workspaces of the same module at two commits
are the ordinary case; a bundle shipped from CI against a local workspace is the drift
scenario.

### 3b. Output

Machine-readable first (FR-10's conventions), deterministic (NFR-1), one JSON document:

```json
{
  "boundary_vocabulary_version": 1,
  "a": {"module": "com.acme:orders-service", "commit": "630906a7", "producer": {…}},
  "b": {"module": "com.acme:orders-service", "commit": "778285e8", "producer": {…}},
  "producer_changed": false,
  "entries": [
    {"kind": "endpoint", "change": "added",
     "identity": {"protocol": "http", "method": "GET", "path": "/ops/status"},
     "to": {"request_shape": null, "response_shape": {…}, "format": null,
            "requirements": [], "conditions": [{"kind": "profile", "expression": {…}}]},
     "evidence": {"symbols": ["…OpsController#status(sig_0e30dfc9)."],
                  "documents": ["…/OpsController.class"]}},
    {"kind": "data-contract", "change": "changed",
     "identity": {"shape": "…/OwnerPageDto#"},
     "from": {"content_hash": "md5:…", "fields": {…}}, "to": {…},
     "evidence": {…}}
  ],
  "summary": {"endpoint": {"added": 2, "removed": 0, "changed": 0}, "data-contract": {…}, …}
}
```

* Entries sorted by (kind, change, identity); `summary` has one row per kind, every kind
  present even at zero, so an empty diff is `{"entries": [], "summary": {all zeros}}` and
  NEVER an absent file (NFR-7). Identical inputs produce exactly that.
* **`changed` is attribute-level**: `from`/`to` carry only the attributes that differ, each
  named, so a consumer reads "response shape changed" without diffing two blobs.
* **Attribution follows origin** (`meridian-integration.md` FR-22): an entry grounded only
  in `dependency`-origin documents is marked `origin: dependency`; a module is never
  reported as having changed a boundary its own build did not declare.
* **No prose about intent.** Sextant reports what changed, never why.
* A human rendering (`--format text`) prints the summary table and one line per entry; it
  is a view of the JSON, derived from it, never a second source.

### 3c. Refusals, never guesses

| condition | answer |
|---|---|
| `fact_schema_version`, `graph_schema_version` or `boundary_vocabulary_version` differ | **refuse**, naming the stamp and both values (§1a's own pair would) |
| the two analyses name different modules | **refuse**, naming both — FR-22 is "the same module" |
| `sextant_version`, `catalog_hash` or `redaction_set_hash` differ | **refuse by default**, naming them: a fixed dispatch bug or a new catalog changes rows with no code change, and a diff that mixed the two could not say which it was reporting. Under `allow_producer_change=True` (`--allow-producer-change`) the diff runs and the output carries `producer_changed: true` with both stamps — labelled, never silent (decision 3, §7) |
| a side is neither a workspace nor a bundle, or lacks a stamp | refuse — the `NotAnalyzedError` `render`/`export` already raise |

### 3d. Both sides are read through the same exit

Masking happens at exits (D04 §1): a bundle's `endpoints.path`/`peer` and `resolved_config.value`
are already masked; a workspace is verbatim. Diffed naively, every masked `dependency` peer
and every masked `boundary-property` value would read as a change — the CI-bundle-against-
local-workspace case, which is THE drift scenario. So the diff is itself an exit: each
side's address and value columns pass through the module's redactor before comparison (a
workspace side from its own `.sextant.yml`, exactly as `export` would have masked it; a
bundle side is already masked and passes through unchanged), and the diff's own output is
masked the same way. Two sides masked under different rule sets (`redaction_set_hash`)
refuse by default with the other producer stamps (§3c), because "the value changed" and "the
mask changed" cannot be told apart. *Ruled at the branch's final review (2026-10-22):* allowed,
both sides are masked by the UNION of the two rule sets, so nothing either side's rules hide
leaves in the clear (a bundle carries its rules' hash, not the rules, so its own additions
reach only its own side); a workspace outside its module's `.sextant` directory is refused by
name, since which `.sextant.yml` masks it is unknown.

**`analyze` starts writing `catalog_hash` into `metadata.json`.** Today only the exporter
computes it, from the catalogs installed at export time, so a workspace side would have no
hash of its own to compare — and hashing the catalogs installed NOW would describe the
diff's machine, not the analysis. The catalogs are loaded at `analyze`; the hash is written
then, beside the three stamps that already are (D01 §7's table gains the row).

### 3e. Cost (§8.7, decided here)

One named query per kind per side — 7 kinds × 2 sides = 14 reads, each over a table of at
most thousands of rows (the largest corpus, `ruoyi-vue-pro`, has 484 endpoints across 18
modules). The set difference is a dictionary join on identity in Python; no table is read
twice, nothing is re-derived. Measured in §1 at DuckDB speed over Parquet: well under a
second for both corpora.

---

## 4. FR-23 — the observability map

Per kind, `observable | partial | not-observable`, with the REASONS, written at `analyze`
into `metadata.json` (`observability`) and carried into the bundle manifest by the exporter
untouched (the never-re-derive rule every manifest field follows). Also answerable
in-process: `api.observability(path) -> ObservabilityMap`.

### 4a. The inputs, and what each is a measurement OF

| input | measures | reaches |
|---|---|---|
| `uncovered` (source files no class file accounts for) | this analysis | every kind whose evidence is code: `endpoint`, `dependency`, `data-contract`, `schedule`, `error-handler` → at best `partial`, naming the files |
| `coverage.partial_documents > 0` | this analysis | the same five kinds → `partial`, with the count |
| `skipped_catalogs` | this analysis | the kinds the skipped catalog FEEDS (§4b) → `partial`, naming the catalog and its reason; `not-observable` when EVERY catalog that could feed the kind on this module's languages was skipped |
| `dependency_source: declared` (Maven could not be asked) | this analysis | `dependency` and `data-contract` → `partial`: a type one hop out may be unread (OI-167's own boundary) |
| `KNOWN_GAPS` | **Sextant, not this analysis** | listed on the map under `stated_boundaries`, never folded into a verdict — a verdict about THIS module made from a sentence about the tool would be documentation masquerading as measurement, which `meridian-integration.md` FR-23 forbids in so many words |

Attribute-level verdicts (*"per attribute where they differ"*): only where a measured input
names one attribute — today `format` (the ladder's `unresolved` share is in `coverage`) and
`dependency`'s `peer` (`computed_base_addresses_not_traced` is static and so stays a stated
boundary). Everything else is per kind. Decision 4, §7.

### 4b. Which kinds a catalog feeds — recorded at `analyze`, no new catalog key

A catalog's `style`, `direction` and whether it declares a shape model already say what it writes:
`style: scheduled_work` → `schedule`; `style: error_advice` → `error-handler`; every other
style writes `endpoints` and feeds `endpoint` for `direction: inbound`, `dependency` for
`outbound`, both for `both`; a shape model declared (any of `serialization`, `nullability`, `known_types`) → `data-contract` too. The mapping is a
function over fields the catalogs carry today (D02), not a new declaration.

The catalogs are in hand at `analyze` and NOT in hand when a bundle's manifest is read
later, so the answer is recorded when it is known: each `skipped_catalogs` entry in
`metadata.json` gains `feeds: [kinds]`, and the metadata gains `catalogs_run: {kind: count}`
— how many catalogs that feed each kind actually ran on this module. The map is then a pure
function of the metadata (§4c holds). `not-observable` is `catalogs_run[kind] == 0` with at
least one skipped catalog feeding it; a kind nothing could ever feed on this module is
`observable` with an empty evidence set, which is the truth. A manifest written before this
spec carries neither field and gets `partial` for every code-grounded kind with the reason
*catalog kinds unrecorded: manifest predates boundary vocabulary 1* — a degraded answer
that says it is degraded, never a verdict from catalogs the machine happens to have today.

*The "unsupported language" input the proposal listed is dropped:* `analyze` refuses a
module whose language no scanner accepts (`NoAdapterError`), so no analysis with such a
module exists for the map to describe. An input that can never fire would be a false claim
on the map.

### 4c. Cost

Zero new reads: every input is already in hand when `metadata.json` is written. The map is
a pure function of the metadata dictionary, so a bundle produced before this spec can have
its map computed from its manifest alone.

---

## 5. FR-24 — library embedding

* **`diff` and `observability`** join `analyze`, `render`, `export`, `enrich`,
  `system_analyze` on `sextant.api`; the CLI verbs are thin wrappers, as every verb is.
* **`query` is built, minimal, in-process only — decision 5 ruled A on 2026-10-22,
  reopening the 2026-09-18 language gate for the function alone.** Six questions, each a
  named query over tables that exist (D01 §5's rule: shipped with the schema, never written
  per consumer):

  | question | answers from | returns |
  |---|---|---|
  | `source` | `symbols` + `documents` | the file and line range declaring a symbol |
  | `callers`, `callees` | `call_edges` | one hop, either direction, each with file and line |
  | `implementations` | `type_hierarchy` | the types implementing or extending a type |
  | `uses` | the type-reference edges | what references a TYPE (a payload class's real question) |
  | `impact` | the transitive closure of `callers` and `uses` | **three partitions, never one count** (D01 §5): `definite`, `possible` (through `narrowed` dispatch), `unknown_regions` (the `boundary` stops reached) |

  ```python
  api.query(path, "callers", symbol="…OrderService#place(sig_1a2b).")
  api.query(path, "impact", symbol="…Money#amount")   # {"definite": [...], "possible": [...], "unknown_regions": [...]}
  ```

  Module scope only. NOT built, named as waiting: `path` between two symbols, the endpoint
  family (`endpoint list`/`find`/`match`/`trace` — `match` and `trace` are system-scope
  questions over the federated views), the CLI `symbol`/`endpoint` nouns and the coding-agent
  plugin, which stay under the gate. `FR-24`'s clause table reads *four of the four*; `FR-10`'s
  state moves to *partial: six questions at module scope*.
* **A configuration object.** `AnalyzeOptions(allow_resolve: bool = False, shadow: bool =
  False, workspace_dir: Path | None = None)` — the three knobs the CLI already has, and no
  fourth invented here — accepted by `analyze(path, options=…)`; the flag form stays for
  compatibility. `DiffOptions(allow_producer_change)` likewise. No global state is added;
  the one environment read (the agent's API key) is the carve-out the requirement itself
  names.

---

## 6. What this does NOT do

* **No system-scope diff.** `links` and `participants` are two more kinds, and the drift
  scenario Meridian describes is per module (FR-22's own words). `system diff` stays on
  `PROJECT.md`'s deferred list.
* **No drift ENFORCEMENT** — no exit code policy, no CI gate. `PROJECT.md` defers that
  until false-positive rates are measured; §1b is the first such measurement (zero false
  positives on six months of one corpus), not the last.
* **No `query` beyond §5's six questions**, and no CLI noun or plugin for it.
* **No new facts, no new derived table, no catalog change.** The vocabulary reads what is
  derived; the map reads what is recorded.
* **No prose in the diff.** The architecture document is unchanged by this spec.

---

## 7. Decisions for the user

| # | decision | recommendation, and why |
|---|---|---|
| 1 | What identifies an `endpoint`: the wire alone, or the wire plus the handler | **RULED 2026-10-22: the exposed address.** *"Implementation should never matter. Only the exposed visible parts matter in identifying an endpoint"* — protocol, verb or operation where the protocol has one, path or topic or name; for every protocol, not HTTP alone. The request and response bodies are exposed ATTRIBUTES compared field by field by wire name (so a field added to a response reads `changed` with `from`/`to`, never gone-and-back), and each body change carries the stitcher's own directional test (M06 step 3) read forwards in time — `compatible` where the response gained or the request gained an optional field, `breaking` where the request gained a required field or the response lost one. The handler is evidence only. Measured: +2 −0 against +44 −42 on six months of petclinic-rest |
| 2 | Which kinds: Meridian's five, or every boundary table Sextant publishes | **RULED 2026-10-22: B** — the five plus `schedule` and `error-handler`; requirements and conditions stay attributes of their endpoint; open questions and roots are Sextant's working state and never enter. The one stated inconsistency: a schedule or error handler has no wire, so its handler symbol IS its identity and a renamed job reads removed-and-added |
| 3 | A diff whose two sides were produced by different Sextant versions, catalogs or redaction rules | **RULED 2026-10-22: C** — refuse by default naming the stamps; run and LABEL (`producer_changed: true`, both stamps) under `--allow-producer-change`. The user's observation recorded with it: the question exists only when one side is a STORED analysis (a CI bundle, a workspace left on disk); two sides analysed fresh by one build always agree, so C is the enforcement of "analyse both sides alike, or say that you did not". No `--analyze` convenience: the diff takes analyses, never builds |
| 4 | How far FR-23 goes below "per kind" | **RULED 2026-10-22: B** — per kind from measured inputs (uncovered files, partial documents, skipped catalogs via their recorded `feeds`, `dependency_source: declared`), per attribute only where a measurement names one (`endpoint.format` from the ladder's unresolved share, `dependency.peer` from per-row `resolution`); `KNOWN_GAPS` listed as `stated_boundaries`, never folded into a verdict |
| 5 | `FR-24`'s `query` | **RULED 2026-10-22: A — build a minimal `query` now.** This reopens the language gate of 2026-09-18 for the IN-PROCESS `api.query` function only; the concern raised (a surface shaped by one extractor's facts) was put to the user and overruled. Which questions the minimal set holds is the open sub-question below |

## 8. Answers to the builder check (2026-10-22), my calls

| question | answer |
|---|---|
| Which base: PR #61 or `main`? | `main` once PR #61 has merged (it is mergeable, CI running). The `endpoint` kind's condition set and §1a's measurement both assume `endpoint_conditions` exists; the plan starts after the merge, on a branch from `main`, and never extends #61 |
| A workspace side has no `catalog_hash`; the bundle is masked and the workspace is not | §3d: `analyze` writes `catalog_hash`; the diff is an exit and masks both sides through the module's redactor; a `redaction_set_hash` mismatch refuses like the other producer stamps |
| The map needs catalog definitions a manifest does not carry | §4b: `feeds` per skipped catalog and `catalogs_run` per kind recorded at `analyze`; old manifests get a labelled degraded map; the unsupported-language input is dropped because it cannot fire |
| What is side B in the test suite? | The algorithm is pinned on hand-built workspaces (two `DuckDbWorkspace`s with written rows, as `test_endpoint_conditions.py` does); `diff(A, A)` on the session fixture pins the empty change-set (NFR-1); the real-history case is a seventh field pin in `scripts/field_check.py` — petclinic-rest `f957c77` against the pinned `4cd8e1b`, expecting §1b's numbers — because a checked-in second fixture state would cost a compile per run for a shape only real history has |

Settled by the builder, as the document leaves to them: a read-only bundle reader (none
exists today), `both`-direction rows, the per-side `symbols`/`documents` reads evidence and
origin attribution need, and `boundary_vocabulary_version` compared by the diff alone rather
than joining `_stale_stamps`.

## 9. What it closes, predicted

Register rows `FR-21`, `FR-22`, `FR-23`, `FR-24` — the Meridian row empties and the register
is left with `apache-camel`, `smallrye-reactive-messaging`, `quartz`, `akka-pekko-actors`.
`PROJECT.md`'s `module diff` row moves to delivered and its agent-query-surface row records the partial reopening; `REQUIREMENTS.md` FR-21–24 states move and FR-10 reads partial;
D01 gains the vocabulary section and `boundary_vocabulary_version` in §7's stamp table; D06
gains `observability` in the manifest; M00 gains `module diff`; `sextant.api` gains two
operations and two options objects. Checked at the end, not assumed (`verify-what-it-closes`).

**As built, 2026-10-22 (checked, not assumed).** All four register rows closed and the Meridian row
is empty. Measured with both sides built by the field checker (network allowed, so Maven's
classpath is read and `module` reads unchanged): on `spring-petclinic-rest`, `f957c77` against
the pinned `4cd8e1b`, the diff reads endpoint +2 and data-contract +2 and every other kind
zero — §1b's numbers, pinned as a second check (`diff_against`) on the `spring-petclinic-rest` field pin. One divergence worth keeping: a side
built OFFLINE on a machine without the dependencies cached read `module` as changed 1
(`dependency_source` declared → maven), which is the labelled fallback doing its job and is
why the pin states its method. For `query`: `uses` of `PmsProduct` on `mall-admin` reads 21,
where reading only the top level of a signature read 13, because it now follows type arguments
at every depth; the walk is in Python since the DuckDB floor (`>=1.1`) has no `json_tree`.
`impact` of the same type gave 49 definite, none possible and 13 unknown regions over four
hops in 35 ms, and of the most-called method 776 symbols in six reads (76 ms) — one read per
hop of the frontier, §8.7's cost held (the 776-symbol figure was measured before the floor fix of
commit 225e4161; the `PmsProduct` figures are after it). Six of the ten D01 §5 names now have a
reader — `trace_of`, which was already a function, and five that ship in process (`callers_of`,
`callees_of`, `implementations_of`, `uses_of`, `impact_of`) — beside a sixth question, `source`,
that is FR-10's and not one of the ten.
`PROJECT.md`, `REQUIREMENTS.md`, D01, D05, D06, M00, M06 (a cross-reference), M09, the delivery
list and the changelog say so; FR-24's clause table reads four of four operations and the
configuration-object clause met, with "no global state" still never measured.
