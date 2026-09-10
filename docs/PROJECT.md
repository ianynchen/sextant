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
| 2Q — a rendered trace and a machine sequence diagram per root, in `architecture.md` and `architecture.html` | in-progress | [FR-6](REQUIREMENTS.md#fr-6--traces), [FR-7](REQUIREMENTS.md#fr-7--diagrams) — the walk and the rendering ship; FR-6's "not bounded by depth, stops only at a terminal" is MET as of W31 — the walk is an explicit stack, the depth bound is gone and `OI-27` is closed |

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
| [D00](components/D00-fact-schema.md) field lists frozen and expressed as validated models | **delivered** | NFR-5, NFR-10 |
| [D01](components/D01-graph-schema.md) tables and named queries | **in-progress** | [FR-10](REQUIREMENTS.md#fr-10--query-surface) |
| [D02](components/D02-catalog-schema.md) catalog format and conformance harness | **in-progress** | [FR-3](REQUIREMENTS.md#fr-3--endpoint-catalog), NFR-9 |
| [D03](components/D03-overlay-schema.md) overlay formats | planned | [FR-15](REQUIREMENTS.md#fr-15--overlays) |
| [D04](components/D04-config-and-exclusion.md) configuration, exclusion, redaction | **delivered** | [FR-19](REQUIREMENTS.md#fr-19--exclusion-and-redaction), NFR-8 |
| [D05](components/D05-manifest-and-state.md) manifest and state | **in-progress** | [FR-8](REQUIREMENTS.md#fr-8--system-linking), [FR-17](REQUIREMENTS.md#fr-17--coverage-reporting) |
| [D06](components/D06-bundle-format.md) bundle format | **delivered** | [FR-18](REQUIREMENTS.md#fr-18--export) |

## What the statuses rest on (W50)

**Every row in the two tables below read `planned` until W50**, including five that had
shipped for phases — which is C11's finding in one sentence: this file stopped being
maintained and kept being cited as the delivery authority. It is the authority again, and
**where it and the roadmap disagree the STRICTER wins**, because the stale document turned
out to be the right one.

Measured on 2026-09-10, and every figure here is reproducible rather than remembered:

| What | Measured | How to check |
|---|---|---|
| Graph schema objects | **15 tables and 11 views** | `grep -c 'CREATE TABLE' src/sextant/storage/duckdb/schema.sql` |
| D01's named queries | **1 of 10** — `trace_of` exists; `callers_of`, `callees_of`, `implementations_of`, `uses_of`, `impact_of`, `paths_between`, `endpoint_for_address`, `who_uses_shape`, `who_reads_config` do not | `src/sextant/application/query/` |
| …but five of those nine questions ARE answerable | from the index bundle (W35/W36), as NDJSON rather than as a named query: `callers.ndjson`, `implementors.ndjson`, `impact.ndjson`, `addresses.ndjson`, `shape_carriers.ndjson` | `<bundle>/index/` |
| CLI verbs | **4** — `analyze`, `render`, `enrich`, `export` | `src/sextant/cli/app.py` |
| Catalogs | **64** | `ls src/sextant/catalogs/*.yml` |
| Scanner capabilities | **26 of 26 designed implemented**, 3 unshipped: `invokedynamic`, `constant_propagation`, `control_flow` | [M03](components/M03-scanner.md) |
| Absent components | `overlay` (M01/D03), `sync` (M05), `stitcher` (M06), `state.json` (D05's second half) | — |

**Why `in-progress` rather than `delivered` for the five that carry it.** D01 has its tables
and one tenth of its query surface. D02 has 64 catalogs and a conformance harness, and Q4's
declared-slice discipline says outright that a catalog need not cover its whole framework.
D05 ships `manifest.json` and no `state.json`. M00 has four verbs of the noun-verb surface
FR-20 describes. M03 ships 26 capabilities and names the three it does not. M04 derives every
row this project publishes and does not answer FR-11 … FR-14, which W51 moves out of the FR
section for that reason. Each is a real distance from done, stated rather than rounded in
either direction.

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
