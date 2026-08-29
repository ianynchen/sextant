# M08 — Exporter

## Purpose

Write a workspace out as a bundle.

## Interface

```
Exporter
  export(workspace, what, destination) -> BundlePath
```

`what` is `facts`, `graph` or `both`.

## Inputs

The workspace ([D01](D01-graph-schema.md)) and its provenance
([D05](D05-manifest-and-state.md)).

## Output

A bundle ([D06](D06-bundle-format.md)): Parquet files plus a manifest.

## Behaviour

### It is the seam between the two pipelines

A bundle is the only artifact crossing from the service pipeline to the system pipeline, and
the two ends are usually different machines on different days. Everything about this module
follows from that.

**Which is why it exists at all.** Publishing the workspace database instead would tie the
system tier to one storage format and be opaque to every other tool.

### Formats differ because access patterns differ

| | Format | Why |
|---|---|---|
| Workspace facts | JSONL, one file per source file | Overwriting one file is the incremental unit, and a columnar footer would cost more than the data at that size |
| Bundle | Parquet, one file per table | Large, compressed, portable, read by anything |

### Facts travel, and that is not an optimisation

A bundle carries facts as well as the derived graph, because facts are what make it
**re-derivable**. When stitching improves, a system can be rebuilt from bundles without
re-analysing twelve repositories. Without facts, every downstream improvement costs a full
re-extraction of the estate.

### The manifest is not optional

`schema_version`, source commit, producer versions, scanner identities, catalog hash,
redaction pattern hash, coverage, and known gaps.

It is the mechanism by which a wrong system graph becomes an error rather than a silent
result. Twelve bundles from three Sextant versions will join without complaint and produce
an architecture that never existed. **[M05](M05-sync.md) can only refuse what the manifest
lets it see.**

### What must travel for the system tier to work

Tracing backwards from the system architecture document:

| Needed for | Must be in the bundle |
|---|---|
| Matching endpoints | `endpoints`, with wire identity and direction |
| Structural payload compatibility | `shapes`, `shape_fields`, with **wire names** |
| Resolving a call target to a participant | `deployments`, and aliases |
| **Cross-service sequence diagrams** | `edges` carrying control-flow position, `dispatch`, `dispatch_site`, `trace_summary` — the inputs `trace_of` walks over |
| Naming things | `symbols` for everything referenced above |
| Honest rendering | The trust fields on every row |

**The sequence-diagram row is the one to notice.** Traces are a named query, not a table
([D01](D01-graph-schema.md)) — they travel *implicitly*, as the tables the walk runs over.
So the load-bearing requirement moves one level down: `edges` must carry their control-flow
positions and `dispatch` must be present, or the system tier can draw a service map but no
sequence. Omitting either is not a size optimisation, it is a feature removal.

### Deterministic output

Same workspace, same bundle. Rows written in a defined order, no timestamps inside the data,
fixed compression settings. Otherwise two exports of an unchanged module differ, and NFR-1
cannot be checked at this boundary.

### Indexes

The full-text and token indexes that [M09](M09-query.md) uses belong to the **workspace**,
not the bundle. They are derived, cheap to rebuild, and would only add size to an artifact
that travels.

### Resolved for 2B

- A bundle is a **directory**, never a single archive. Publishing is the caller's business;
  the archive question waits until publishing exists.
- `--what` is **deferred**. Export always carries facts and graph — facts are what make a
  bundle re-derivable.
- The full-text index does not travel, because none exists yet to travel.

## What it must not do

- **No analysis.** It writes out what exists.
- **No publishing.** It writes to a directory. Object stores and registries are the caller's
  business; Sextant does not talk to artifact stores.
- **No unredacted values.** Redaction ran during extraction, and this is the artifact that
  leaves the machine.
- **No absolute paths from the producing machine.** Paths are relative to the module root.
- **No workspace database file.**
- **No overlay files.** Curations are inputs to the system tier and live in git beside
  `system.yml`.

## Honesty obligations

- `coverage.partial` set whenever the workspace was partial, so it propagates to every
  document derived from the bundle anywhere.
- Known gaps carried forward, so a catalog that could not be complete does not read as
  complete on another machine.
- Producer versions and scanner identities recorded exactly, because they are what
  [M05](M05-sync.md) refuses on.
- Any table omitted by `--what`, named in `contents`, so a later failure is explained rather
  than mysterious.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether bundles are signed, given they carry an architecture that will be trusted | Security |
