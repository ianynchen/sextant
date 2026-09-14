# Archify compared with Sextant

Research date: 2026-09-12. Sextant snapshot:
`7c4554fbfa5297f3ac07073496e330c19d162763`.

## Disambiguation

This comparison uses [tt-a1i/archify](https://github.com/tt-a1i/archify), the active
project whose current release is v2.16.0. There is also
[Aryan1718/Archify](https://github.com/Aryan1718/Archify), an early `0.1.3`
repository-analysis and document-generation CLI. That project is closer to Sextant in
product wording, but tt-a1i/archify is the likely intended “Archify” and the more mature
GitHub project.

## Honest verdict

Archify is not a better Sextant, and Sextant is not a better Archify. They own adjacent
halves:

- **Sextant discovers architecture facts.** It detects modules, scans compiled
  Java/Kotlin bytecode, reads configuration and schemas, applies framework-specific
  catalogs, resolves endpoints, calls, and data shapes, and preserves evidence and
  uncertainty (`src/sextant/application/stages/analyze.py:148-205`,
  `src/sextant/ingress/extract/jvm/scanner.py:55-112`).
- **Archify authors and verifies an architecture story.** An agent or person supplies
  typed JSON IR; Archify deterministically validates and renders it as an interactive
  technical map. Its product definition says the input is “repository evidence or a
  bounded system description,” not that Archify extracts that evidence itself
  ([PRODUCT.md](https://github.com/tt-a1i/archify/blob/main/PRODUCT.md#product-purpose)).

Archify is far ahead in visual communication, artifact UX, deterministic visual
validation, and agent-oriented packaging. Sextant is far ahead in automatic architecture
extraction, language/framework semantics, explicit gaps, and machine-queryable evidence.
The strongest opportunity is a small, evidence-preserving export from Sextant into
Archify's typed IR, not copying Archify's renderer.

## Side-by-side

| Dimension | Archify | Sextant | Assessment |
| --- | --- | --- | --- |
| Scope | Five authored diagram types: architecture, workflow, sequence, data flow, and lifecycle ([README](https://github.com/tt-a1i/archify/blob/main/README_EN.md#choose-the-right-diagram)). | One derived system model covering exposed and called boundaries, crossing data, and reachability (`README.md:1-4`). | Archify is broader as a communication medium; Sextant is deeper as an analyzer. |
| Input | Typed, intentionally bounded JSON authored from a prompt, system description, or evidence gathered by an agent. The recommended first diagram has 8–12 nodes and one primary path ([cookbook](https://github.com/tt-a1i/archify/blob/main/docs/authoring-cookbook.md#3-author-one-bounded-source-file)). | Compiled classes, build metadata, configuration, schemas, framework catalogs, and an optional human/LLM overlay. Facts are written before resolution (`src/sextant/application/stages/analyze.py:1-10`, `src/sextant/application/stages/analyze.py:194-205`). | Archify's topology is authored; Sextant's is derived. |
| Languages/frameworks | Language-agnostic because it renders IR. Its agent may inspect any repository, but Archify itself does not claim framework-semantic extraction. | The shipped scanner supports Java/Kotlin (`src/sextant/ingress/extract/jvm/scanner.py:8-35`). Coverage tracks REST, SOAP, GraphQL, WebSocket, SSE, gRPC, Kafka, JMS/AMQP, SQS, Pub/Sub, and async boundaries (`docs/COVERAGE.md:35-56`). | Archify can depict anything the author knows; Sextant can prove only implemented coverage. |
| Outputs | Self-contained HTML plus PNG, SVG, WebM, and share cards; interactive search/tracing; Before/Delta/After comparison ([README](https://github.com/tt-a1i/archify/blob/main/README_EN.md), [changelog](https://github.com/tt-a1i/archify/blob/main/CHANGELOG.md)). | DuckDB workspace and fact files, Markdown and HTML, enrichment overlay, export bundle, CLI, and typed Python API (`src/sextant/api.py:209-258`, `pyproject.toml:42-60`). | Sextant has stronger machine outputs; Archify has stronger human-facing outputs. |
| Accuracy/evidence | Validates authored schema, topology references, layout/composition, artifact integrity, and optionally revision-pinned Git origin, commit, blobs, and lines ([cookbook](https://github.com/tt-a1i/archify/blob/main/docs/authoring-cookbook.md#3-author-one-bounded-source-file)). A valid diagram can still omit or invent architecture if its author did. | Separates resolution from evidence, derives precedence, and records uncovered compiled sources and failed schema/library interpretation (`src/sextant/domain/closed_sets.py:7-37`, `src/sextant/domain/closed_sets.py:387-393`, `src/sextant/application/stages/analyze.py:121-145`). | Archify proves faithful rendering of typed input and anchors; Sextant tries to prove runtime claims from artifacts. |
| Operations | Agent skill with zero-install validation, `doctor`, examples, preview, validation, inspection, and atomic delivery. | Python 3.12 plus a separately built JVM extractor jar; not on PyPI and has a git-pinned dependency (`pyproject.toml:5-36`, `pyproject.toml:53-67`). | Archify is substantially easier to try and distribute. |
| Maturity | v2.16.0 has immutable signed releases, multiple contributors, CI and reproducibility work, with main at v2.17 development ([releases](https://github.com/tt-a1i/archify/releases)). | Still `0.1.0` and unreleased (`pyproject.toml:5-8`), though the inspected history has 729 commits and extensive tests, fixtures, and architecture gates. | Archify is more mature as a shipped product; Sextant is substantial but pre-release operationally. |

## What Sextant should borrow

### 1. Export to Archify

Prototype one narrow, versioned projection:

`Sextant facts → explicit projection → Archify JSON IR → Archify validate/deliver`

Start with one existing Sextant trace and the `architecture` IR only. Carry stable
Sextant IDs, source anchors, resolution, evidence, and unresolved status. Never turn an
unresolved Sextant relationship into an ordinary confident edge.

### 2. Revision-verified source anchors

Archify verifies Git origin, commit, blobs, and source ranges. Sextant already records
source locations and producer/schema versions; binding exported links to an exact revision
would make shared artifacts more trustworthy.

### 3. Atomic validate-then-deliver

Archify renders a candidate, runs deterministic checks, records byte count and SHA-256,
and replaces the target only after success
([CHANGELOG](https://github.com/tt-a1i/archify/blob/main/CHANGELOG.md#unreleased)).
Sextant should consider the same last-good behavior for HTML and export bundles.

### 4. Machine-readable validation receipts

Archify validation reports a failure stage, diagnostics, supported fixes, and composition
summary, with non-zero exit on failure
([cookbook](https://github.com/tt-a1i/archify/blob/main/docs/authoring-cookbook.md#4-validate-before-rendering-a-handoff)).
Sextant's typed exceptions are good for library callers
(`src/sextant/api.py:170-201`); a stable JSON CLI receipt would improve agent repair
loops.

### 5. Bounded views over a complete model

Archify's 8–12-node, one-primary-story discipline is excellent for presentation. Sextant
should preserve its complete model while offering named projections: one request path,
protocol, subsystem, unresolved-boundary set, or cross-service route.

### 6. First-run polish

The highest-value product lessons are `doctor`, one reproducible demo, and a status
command that names the exact next action. Sextant need not adopt Archify's implementation
or every UI feature.

## What Sextant should not follow

- Do not make agent-authored topology the source of truth.
- Do not add all five diagram types without facts that justify them.
- Do not confuse visual/layout validation with semantic correctness.
- Do not turn the 8–12-node presentation guideline into an extraction limit.
- Do not embed or fork Archify prematurely; prefer an optional file-level adapter.

## Recommended experiment

Use one existing Sextant fixture to emit an Archify architecture JSON file, run standard
and showcase validation, and inspect whether uncertainty and evidence remain visible.
Record every conversion loss. If unresolved relationships cannot be represented without
misleading the reader, stop. If they can, an optional `module export --format archify`
or separate adapter package is the clearest high-leverage borrowing.

Deviations: none.
