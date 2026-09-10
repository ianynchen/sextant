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
| [D00](components/D00-fact-schema.md) field lists frozen and expressed as validated models | planned | NFR-5, NFR-10 |
| [D01](components/D01-graph-schema.md) tables and named queries | planned | [FR-10](REQUIREMENTS.md#fr-10--query-surface) |
| [D02](components/D02-catalog-schema.md) catalog format and conformance harness | planned | [FR-3](REQUIREMENTS.md#fr-3--endpoint-catalog), NFR-9 |
| [D03](components/D03-overlay-schema.md) overlay formats | planned | [FR-15](REQUIREMENTS.md#fr-15--overlays) |
| [D04](components/D04-config-and-exclusion.md) configuration, exclusion, redaction | planned | [FR-19](REQUIREMENTS.md#fr-19--exclusion-and-redaction), NFR-8 |
| [D05](components/D05-manifest-and-state.md) manifest and state | planned | [FR-8](REQUIREMENTS.md#fr-8--system-linking), [FR-17](REQUIREMENTS.md#fr-17--coverage-reporting) |
| [D06](components/D06-bundle-format.md) bundle format | planned | [FR-18](REQUIREMENTS.md#fr-18--export) |

## Modules

| Item | Status | Satisfies |
|---|---|---|
| [M00](components/M00-cli.md) command line | planned | [FR-20](REQUIREMENTS.md#fr-20--command-surface) |
| [M01](components/M01-overlay.md) overlay | planned | [FR-15](REQUIREMENTS.md#fr-15--overlays), [FR-16](REQUIREMENTS.md#fr-16--curation-and-proposals) |
| [M02](components/M02-detector.md) detector | planned | [FR-1](REQUIREMENTS.md#fr-1--module-discovery) |
| [M03](components/M03-scanner.md) scanner | planned | [FR-2](REQUIREMENTS.md#fr-2--fact-extraction) |
| [M04](components/M04-resolver.md) resolver | planned | FR-3 … FR-6, FR-11 … FR-14 |
| [M05](components/M05-sync.md) sync | planned | [FR-8](REQUIREMENTS.md#fr-8--system-linking) |
| [M06](components/M06-stitcher.md) stitcher | planned | [FR-8](REQUIREMENTS.md#fr-8--system-linking) |
| [M07](components/M07-renderer.md) renderer | planned | [FR-7](REQUIREMENTS.md#fr-7--diagrams) |
| [M08](components/M08-exporter.md) exporter | planned | [FR-18](REQUIREMENTS.md#fr-18--export) |
| [M09](components/M09-query.md) query | planned | [FR-9](REQUIREMENTS.md#fr-9--blast-radius), [FR-10](REQUIREMENTS.md#fr-10--query-surface) |

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
