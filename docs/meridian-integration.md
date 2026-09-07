# Meridian integration — proposed requirements

**Status: proposed amendment, 2026-09-03.** Drafted from Meridian's requirements
(meridian `docs/REQUIREMENTS.md` §3.3, FR-3.2/3.2a/3.5/3.6a; `docs/decisions/DEC-0002`)
and verified against this repo's [D00](components/D00-fact-schema.md),
[D06](components/D06-bundle-format.md), [COVERAGE.md](COVERAGE.md), and
REQUIREMENTS.md NFR-1/2/3, FR-10/17/18. Fold into REQUIREMENTS.md as FR-21–FR-24
(with traceability rows) when accepted; until then this file is the statement of record
for what Meridian needs Sextant to produce.

**The consumer in one sentence:** Meridian's blueprints declare intended architecture
changes as typed delta entries; at PR time the gate compares what Sextant *observed
changed* against what the ticket's slice *said would change*; observability decides
which design claims may be reported as machine-verified.

---

## 0. Already satisfied — no new work

- **Stable identity** (NFR-3, D00's content-derived SCIP grammar) is exactly Meridian
  FR-3.2a: two derivations of the same entity produce the same identifier, so a diff
  is a join, not a heuristic. *NFR-3's own note — "what makes comparison between two
  analyses possible later" — is the anticipation this document cashes in.*
- **Determinism** (NFR-1): identical inputs must yield the empty change-set.
- **Honest failure** (NFR-2) and **coverage reporting** (FR-17, the manifest's
  `gaps` / `uncovered` / `skipped_catalogs` / `partial`) are the raw material for
  FR-23 below.
- **The bundle** (FR-18, D06): versioned, self-describing, refuses mixed vintages —
  the right carrier; nothing about it changes.

## 0a. One naming collision, decided before it spreads

Meridian's starter delta-kind `component` collides with this repo's glossary, where a
**component is a judgement** (an enrichment grouping, never a fact). The shared
vocabulary MUST use **`module`** (and `service` where deployment matters) for the
structural unit, reserving `component` for enrichment judgements — which never enter
the diff. *Meridian adopts Sextant's glossary here, not the reverse; recorded as input
to Meridian OQ-3.*

---

## FR-21 — Boundary vocabulary

Sextant defines a **closed, versioned boundary vocabulary** over its derived tables —
the granularity at which architecture is compared and exported:

| Kind | Derived from | Identity |
|---|---|---|
| `module` / `service` | M02 detection | module id (root-relative) |
| `endpoint` | endpoints table | content-derived (`ep_…`) |
| `dependency` | edges/dispatch: outbound calls, consumed endpoints | caller module + callee identity |
| `data-contract` | shapes + shape_fields crossing a boundary | shape symbol |
| `boundary-property` | declared per-environment/config attributes | property key scoped to module |

Each kind declares its attribute set (what `from`/`to` can range over in a change).
The vocabulary carries its own version in the manifest, sibling to
`fact_schema_version` and `graph_schema_version`, and changes to it follow the same
discipline (NFR-5's closed-set rule applies: kinds are a fixed enumerated set).

*`boundary-property` is expected to be the sparsest cell today; FR-23 exists so that
sparseness is declared rather than discovered.* This vocabulary is what seeds
Portolan's catalog; downstream consumers never parse graph tables directly.

## FR-22 — Derivation diff

Given two analyses of the **same module** — workspace or bundle, any mix — Sextant
reports the typed change-set in the boundary vocabulary: per kind, entries
`added | removed | changed`, with `from`/`to` attribute values on `changed`, each
entry carrying evidence pointers (the symbols/documents that ground it).

- **Boundary granularity, deliberately.** Sub-symbol churn that alters no boundary
  fact produces no entry. The diff answers "did the architecture change," not "did
  the code change."
- **Attribution follows origin.** Facts from the module's own output
  (`origin_tier: module_output`) may produce any kind; dependency-origin facts may
  affect only `dependency` and `data-contract` entries. A module is never reported
  as having changed a boundary its own build did not declare.
- **Refusals over guesses** (FR-18's rule extended): differing
  `fact_schema_version` / `graph_schema_version` / boundary-vocabulary versions
  refuse with the mismatch named. Identical inputs produce the empty change-set
  (NFR-1).
- Output is machine-readable per FR-10's conventions; a human rendering MAY exist;
  *no prose about intent — Sextant reports what changed, never why.*

## FR-23 — Observability map

For any analysis, Sextant answers **per boundary kind (and per attribute where they
differ): `observable | partial | not-observable`** — derived from the manifest's
gaps, skipped catalogs, uncovered files, and the shipped coverage cells for the
module's languages and frameworks.

- Ships as a machine-readable file in the bundle, versioned with the boundary
  vocabulary.
- **Partial coverage degrades the answer** (NFR-2 in force): a kind is `observable`
  only where the analysis was complete for the facts that kind reads; an uncovered
  controller file makes `endpoint` at best `partial` for that module.
- *Consumer contract: Meridian derives verification tags from this map (its FR-3.5 —
  tags are derived, never author-chosen); a claim Sextant cannot observe is never
  reported as machine-verified. The map is therefore load-bearing for someone
  else's honesty, which is why it must come from measurement, not documentation.*

## FR-24 — Library embedding

Analyze, query, export, and diff (FR-22) are callable **in-process from Python**: the
CLI becomes a thin wrapper over the same operations. No subprocess required, no
global state, no environment reads — caller supplies configuration as an object
(the pattern Tradewind established). The enrich step's language-model port stays
injected (ARCHITECTURE DR-2 unchanged).

*This is what lets a Portolan-side adapter consume bundles, diffs, and observability
maps without shelling out.*

## Non-goals

- **Sextant does not write to Portolan and does not know Meridian exists.** The
  bundle + diff + observability map are the entire contract; projection into
  Portolan is an adapter on the consumer's side of the boundary (one-writer custody,
  meridian DEC-0001/0002).
- Enrichment judgements (components, prose) never enter the diff or the vocabulary.
- No completeness promise for `boundary-property`; the map states per analysis what
  could be seen.

## Traceability (Meridian ← Sextant)

| Meridian requirement | Satisfied by |
|---|---|
| FR-3.2 (vocabulary seeded from export) | FR-21 |
| FR-3.2a (stable identity across derivations) | NFR-3 (existing) + FR-22's join |
| FR-3.5 (derived verification tags) | FR-23 |
| FR-3.6 / FR-3.6a (diff outcomes at the PR gate) | FR-22 |
| FR-5.2 (ACTUAL facts into Portolan) | D06 bundle + consumer-side adapter (non-goal above) |
