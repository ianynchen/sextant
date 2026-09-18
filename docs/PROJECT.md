# PROJECT

Delivery status only. Each entry links to what it satisfies. Design lives in
[REQUIREMENTS.md](REQUIREMENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md) and
[components/](components/README.md); nothing is described here.

Status values: `planned` · `in-progress` · `delivered` · `deferred` · `cancelled`

---

## Design

| Item | Status | Satisfies |
|---|---|---|
| [CONTEXT.md](../CONTEXT.md) — ubiquitous language | delivered | `GUIDELINES.md` §5 |
| [REQUIREMENTS.md](REQUIREMENTS.md) — 20 FR, 11 NFR | delivered | `GUIDELINES.md` §5 |
| …and the SET changed in W51 while the count did not: FR-11 … FR-14 left as usage scenarios, FR-21 … FR-24 folded in as real requirements | delivered | `GUIDELINES.md` §5 |
| [ARCHITECTURE.md](ARCHITECTURE.md) — structure and DR-1 … DR-5 | delivered | `GUIDELINES.md` §5, §5.2 |
| [components/](components/README.md) — 7 data definitions, 10 modules | delivered | `GUIDELINES.md` §5.1 |
| Requirement-to-component traceability | delivered | NFR-6 |
| Adversarial design review — nine issues found and resolved | delivered | `GUIDELINES.md` §1, §6 |
| Schema closure audit — four gaps found and resolved | delivered | NFR-6 |
| Tool capability audit — matrix in ARCHITECTURE §9a, four decisions | delivered | `GUIDELINES.md` §7 |
| [COVERAGE.md](COVERAGE.md) — framework and protocol reach, gaps tiered A/B/C | delivered | [FR-3](REQUIREMENTS.md#fr-3--endpoint-catalog), NFR-9 |
| [coverage/](COVERAGE.md#9-beyond-the-jvm) — Go, Rust, Python, TypeScript, Android, iOS | delivered | REQUIREMENTS § Scope |
| Phase 1 vertical slice — fixture repo to endpoint catalog, byte-identical | delivered | [FR-1](REQUIREMENTS.md#fr-1--module-discovery), [FR-2](REQUIREMENTS.md#fr-2--fact-extraction), [FR-3](REQUIREMENTS.md#fr-3--endpoint-catalog), [FR-17](REQUIREMENTS.md#fr-17--coverage-reporting), [FR-20](REQUIREMENTS.md#fr-20--command-surface), NFR-1, NFR-5, NFR-10, NFR-11 |
| 2Q — a rendered trace and a machine sequence diagram per root, in `architecture.md` and `architecture.html` | in-progress | [FR-6](REQUIREMENTS.md#fr-6--traces), [FR-7](REQUIREMENTS.md#fr-7--diagrams). **Both deliverables ship**, and FR-6's "not bounded by depth, stops only at a terminal" is MET as of W31 — the walk is an explicit stack, the depth bound is gone, `OI-27` is closed. **What keeps the PHASE open is `OI-29`**, a Major its own close introduced: `analyze` over a workspace whose graph schema gained a column crashes instead of rebuilding. That is a phase's loose end, not a gap in FR-7 — which is why [M07](components/M07-renderer.md) below reads `delivered` for the same requirement. A phase and a component are different objects and may hold different statuses |

## Approvals

| Item | Status | Note |
|---|---|---|
| Technology choices in [ARCHITECTURE.md](ARCHITECTURE.md) §9, §9a | **approved 2026-08-27** | Core stack wholesale; audit-round tools decided individually |
| Control-flow scope for version 1 | **approved 2026-08-27** | Loops, optionality, grouped alternatives; unnamed branches recorded as a known gap |
| Rapid type analysis in version 1 | **approved 2026-08-27** | On top of hierarchy analysis, from the start |
| Repository initialisation under version control | delivered | `GUIDELINES.md` §11 — done; the branch `feat/phase-1-vertical-slice` carries the Phase 1 history |

## Data definitions

| Item | Status | Satisfies |
|---|---|---|
| [D00](components/D00-fact-schema.md) field lists frozen and expressed as validated models | **in-progress** | NFR-5, NFR-10 |
| [D01](components/D01-graph-schema.md) tables and named queries | **in-progress** | [FR-10](REQUIREMENTS.md#fr-10--query-surface) |
| [D02](components/D02-catalog-schema.md) catalog format and conformance harness | **in-progress** | [FR-3](REQUIREMENTS.md#fr-3--endpoint-catalog), NFR-9 |
| [D03](components/D03-overlay-schema.md) overlay formats | planned | [FR-15](REQUIREMENTS.md#fr-15--overlays) |
| [D04](components/D04-config-and-exclusion.md) configuration, exclusion, redaction | **in-progress** | [FR-19](REQUIREMENTS.md#fr-19--exclusion-and-redaction), NFR-8 |
| [D05](components/D05-manifest-and-state.md) manifest and state | **in-progress** | [FR-8](REQUIREMENTS.md#fr-8--system-linking), [FR-17](REQUIREMENTS.md#fr-17--coverage-reporting) |
| [D06](components/D06-bundle-format.md) bundle format | **delivered** | [FR-18](REQUIREMENTS.md#fr-18--export) |

## What the statuses rest on (W50)

**Every row in the two component tables — data definitions above, modules below — read
`planned` until W50**, including five that had
shipped for phases — which is C11's finding in one sentence: this file stopped being
maintained and kept being cited as the delivery authority. It is the authority again, and
**where it and the roadmap disagree the STRICTER wins**, because the stale document turned
out to be the right one.

Measured on 2026-09-10, and every figure here is reproducible rather than remembered:

| What | Measured | How to check |
|---|---|---|
| Graph schema objects | **15 tables and 11 views** | `grep -c 'CREATE TABLE' src/sextant/storage/duckdb/schema.sql` |
| D01's named queries | **1 of 10** — `trace_of` exists; `callers_of`, `callees_of`, `implementations_of`, `uses_of`, `impact_of`, `paths_between`, `endpoint_for_address`, `who_uses_shape`, `who_reads_config` do not | `src/sextant/application/query/` |
| …but four of those nine questions ARE answerable | from the index bundle (W35/W36), as NDJSON rather than as a named query: `callers.ndjson` → `callers_of`, `implementors.ndjson` → `implementations_of`, `addresses.ndjson` → `endpoint_for_address`, `shape_carriers.ndjson` → `who_uses_shape` | `<bundle>/index/` |
| …and `impact.ndjson` is NOT the fifth | it answers a narrower question than `impact_of`, which [D01](components/D01-graph-schema.md) designs, under `impact_of`, as three partitions — definite, possible, and the unknown regions reached. The file carries a shape, its fields and the endpoints that carry it, with no partitioning and no unknown regions at all | `src/sextant/egress/export/index.py:579` |
| CLI verbs | **4** — `analyze`, `render`, `enrich`, `export` | `src/sextant/cli/app.py` |
| Catalogs | **64** | `ls src/sextant/catalogs/*.yml` |
| Scanner capabilities | **23 of 26 designed implemented**; the 3 unshipped are `invokedynamic`, `constant_propagation`, `control_flow` | `Capabilities.ALL` in `extractor-jvm/src/main/java/dev/sextant/extractor/Capabilities.java` — 23 entries; [M03](components/M03-scanner.md):77 says the same |
| Absent components | `overlay` (M01/D03), `sync` (M05), `stitcher` (M06), `state.json` (D05's second half) | — |

**Component statuses, counted rather than remembered: 4 `delivered`, 9 `in-progress`,
4 `planned`** — seventeen rows, and the count is `grep` on the two tables, not a memory of
what W50 wrote. `delivered` is D06, M02, M07 and M08. `planned` is D03, M01, M05 and M06 — three of the four the "absent components" row above
names. Its fourth, `state.json`, is not a component row at all: it is half of D05, which is
`in-progress` because its other half, `manifest.json`, ships.

**Why `in-progress` rather than `delivered`, for each of the nine that carry it.** No row
here is rounded in either direction; each names the specific distance left.

| Component | What ships | What does not |
|---|---|---|
| D00 | the validated models — `src/sextant/domain/facts.py` | **freezing the schema**, which D00 §10 and [ARCHITECTURE.md](ARCHITECTURE.md)'s own open-decisions table both still carry as OPEN. The row's first three words are the half that has not landed |
| D01 | 15 tables and 11 views | 9 of its 10 named queries |
| D02 | 64 catalogs and a conformance harness | whole-framework cover — and deliberately: Q4's declared-slice discipline says outright that a catalog need not have it |
| D04 | redaction (`src/sextant/domain/redaction.py`) and the per-module `.sextant.yml` reader | **two of the three configuration files D04 §2 designs.** Neither `~/.sextant/config.yml` nor a repository-root `sextant.yml` has a reader anywhere in `src/`; the 2026-09-05 amendment calls the precedence chain and the merge rule "designed and never built" |
| D05 | `manifest.json` | `state.json` — the second half of the component's own name |
| M00 | four verbs: `analyze`, `render`, `enrich`, `export` | the noun-verb surface FR-20 describes |
| M03 | 23 capabilities | 3 — `invokedynamic`, `constant_propagation`, `control_flow` — which it names rather than hides |
| M04 | every row this project publishes | FR-11 … FR-14, which is why W51 moved them out of the FR section: they were never Sextant's to answer |
| M09 | `trace_of` | the other 9 named queries. Four of them are reachable from the index bundle as NDJSON, which is a different surface, not this one |

## Modules

| Item | Status | Satisfies |
|---|---|---|
| [M00](components/M00-cli.md) command line | **in-progress** | [FR-20](REQUIREMENTS.md#fr-20--command-surface) |
| [M01](components/M01-overlay.md) overlay | planned | [FR-15](REQUIREMENTS.md#fr-15--overlays), [FR-16](REQUIREMENTS.md#fr-16--curation-and-proposals) |
| [M02](components/M02-detector.md) detector | **delivered** | [FR-1](REQUIREMENTS.md#fr-1--module-discovery) |
| [M03](components/M03-scanner.md) scanner | **in-progress** | [FR-2](REQUIREMENTS.md#fr-2--fact-extraction) |
| [M04](components/M04-resolver.md) resolver | **in-progress** | FR-3 … FR-6 |
| [M05](components/M05-sync.md) sync | planned | [FR-8](REQUIREMENTS.md#fr-8--system-linking) |
| [M06](components/M06-stitcher.md) stitcher | planned | [FR-8](REQUIREMENTS.md#fr-8--system-linking) |
| [M07](components/M07-renderer.md) renderer | **delivered** | [FR-7](REQUIREMENTS.md#fr-7--diagrams) |
| [M08](components/M08-exporter.md) exporter | **delivered** | [FR-18](REQUIREMENTS.md#fr-18--export) |
| [M09](components/M09-query.md) query | **in-progress** | [FR-9](REQUIREMENTS.md#fr-9--blast-radius), [FR-10](REQUIREMENTS.md#fr-10--query-surface) |

## Deferred to a later version

| Item | Status | Note |
|---|---|---|
| Python, Go, Rust, TypeScript scanners | deferred | Recorded in REQUIREMENTS § Scope |
| WSDL reading | **delivered** | Phase 2I — a reader and a stdlib-XML interpreter branch; SOAP operations derive at their QName. Cross-service *matching* is the linking tier's, not this row's |
| Avro schema reading | **delivered** | Phase 2G, both origins — `.avsc` and the `SCHEMA$` a generated class embeds — with its two limits recorded in [COVERAGE.md](COVERAGE.md) §4.2 |
| Terraform, JSON Schema, docker-compose | deferred | Tier 3 artifacts. XSD delivered with WSDL (2I) and GraphQL SDL in 2H — both read as the same declared shapes |
| `module diff`, `system diff` | deferred | Stable identity is designed in for it |
| VTA dispatch narrowing | deferred | **Expected to be needed.** The per-call-site candidate shape in D01 is already VTA-ready, so it lands as better `dispatch` rows with nothing downstream touched. |
| Architecture-drift enforcement in CI | deferred | Needs measured false-positive rates first |
| Runtime-trace overlay for real performance data | deferred | Would make FR-14 measurement rather than structure |
| Agent query surface — the graph answers structural questions so an agent reads less source | deferred | **Gated on language coverage** (ruled 2026-09-18): built only after Java/Kotlin, Go, Rust, Python and TypeScript/JavaScript are fully supported. The idea is [M09](components/M09-query.md) delivered as a CLI verb plus a coding-agent plugin, in the shape Spotify's `shunt` plugin uses — see [research/spotify-portal-shunt.md](research/spotify-portal-shunt.md). |
| Business-rule extraction — EARS rules at trace terminals, a `rules` overlay, a refutation pass | deferred | **Same gate.** Answers "what business logic applies at checkout" from rules anchored to the endpoint's trace. Design direction and what not to copy are in [research/codetospec-comparison.md](research/codetospec-comparison.md) §What Sextant should borrow. No design has been done; brainstorming starts when the gate opens. |
