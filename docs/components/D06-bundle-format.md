# D06 — Bundle format

The artifact that carries one module's analysis to wherever a system is assembled. Written
by [M08](M08-exporter.md). Read by [M05](M05-sync.md).

**This is the only thing that crosses between the two pipelines**, and the two ends of that
crossing are usually different machines on different days. Everything below follows from
that.

---

## 1. Why a bundle rather than the workspace

The workspace is a DuckDB file. It is a poor unit of exchange: opaque to every other tool,
and tied to a storage format that belongs to one dependency.

Copying it also assumes the two ends agree on versions, which across twelve continuous
integration runners they will not.

So a bundle is **columnar files plus a manifest that describes them**, and it is
self-describing precisely so that [M05](M05-sync.md) can refuse a bundle it cannot use
instead of joining it anyway.

---

## 2. Layout

```
<module-id>@<commit>/
  manifest.json
  facts/**/*.parquet        one partition per source file
  graph/*.parquet           the derived tables of D01
```

**Parquet here, JSONL in the workspace.** In the workspace, facts are one small file per
source file, and a columnar footer would cost more than the data. In a bundle the same
facts are one compressed file per table, where columnar layout and compression are exactly
right. The formats differ because the access patterns differ.

**Facts travel as well as the graph.** They are what makes a bundle re-derivable: when the
stitching logic improves, a system can be rebuilt from bundles without re-analysing twelve
repositories. Without facts, every improvement downstream costs a full re-extraction of the
estate. A 2B export always writes both; a `--what graph` mode that omits facts when size
matters more than re-derivability is deferred (§8).

**The facts-Parquet schema is pinned for this phase**: raw-fact rows — *(kind, document_id,
payload as a JSON string column)* — one file per source document, named by its document id (a
content-derived hex digest), flat under `facts/`. The per-file partitioning survives from the
JSONL tree; the directory nesting does not. Honest and barely columnar, sufficient until a
columnar need per fact kind is stated.

---

## 3. The manifest

```json
{
  "module":   { "id": ":services:orders", "kind": "service", "languages": ["java", "kotlin"] },
  "source":   { "repo": "git@github.com:acme/acme-orders.git",
                "commit": "a3f91c…", "module_commit": "a3f91c…" },
  "producer": { "sextant_version": "0.4.0",
                "fact_schema_version": "1.0.0",
                "graph_schema_version": "1.0.0",
                "scanners": [{ "id": "asm", "version": "9.7" }],
                "catalog_hash": "…" },
  "environments": ["dev", "staging", "prod"],
  "coverage": { "documents": 1283, "partial_documents": 0, "partial": false },
  "contents": { "facts": true, "graph": true, "tables": ["symbols", "edges", "endpoints",
                                                          "shapes", "shape_fields", "dispatch", "trace_summary"],
                "facts_files": 1283 },
  "gaps": ["soap_contracts_not_read"],
  "uncovered": ["src/main/java/…/LegacyController.java"],
  "skipped_catalogs": [{ "catalog_id": "spring-webclient", "missing_capabilities": ["string_constants"] }]
}
```

The manifest is **not optional and not advisory**. It is the mechanism by which a wrong
system graph becomes an error instead of a silent result.

**Three fields carry versions, not one.** `fact_schema_version` and `graph_schema_version`
invalidate different things at very different cost, and `sextant_version` changes results
without either of them moving — a fixed bug in dispatch resolution produces a different graph
from identical facts. See [D01](D01-graph-schema.md) §7.

**`redaction_set_hash` does not appear in a produced manifest today.** `analyze` records no
redaction set, so the field is omitted rather than written empty or invented; it joins
`producer` the day redaction ships.

**`module_commit`** is the last commit touching this module's own path, computed locally at
scan time where a clone already exists. It is what lets the system tier judge staleness in a
monorepo without fetching history itself.

**`environments`** lists the profiles this module resolved. Endpoints carry configuration
expressions rather than one environment's values, so a bundle serves every environment and
the system tier selects.

---

## 4. Compatibility

[M05](M05-sync.md) checks every bundle before assembling anything.

| Check | On failure |
|---|---|
| `graph_schema_version` incompatible with this Sextant | **Refuse.** Name the bundle and both versions. |
| `graph_schema_version` differs between two bundles | **Refuse.** Mixed vintages produce a wrong graph with no error. |
| `fact_schema_version` differs between bundles | **Refuse** when facts are read. Federated queries read facts. |
| `producer.sextant_version` differs between bundles | **Warn.** Derivation logic differed, so two participants' graphs were computed by different code. |
| `producer.catalog_hash` differs between bundles | **Warn.** Endpoint coverage differs between participants; a missing link may be a coverage gap rather than an absence. |
| `coverage.partial` is true | **Warn**, and mark every document derived from it as partial |
| A declared participant has no bundle | **Refuse or warn**, and never silently treat it as a service with no links |
| **A bundle is unreachable at query time** | **Fail, naming it.** Federated queries read bundles long after stitching; a moved bundle must not silently shorten an answer. |

The last row is the one most easily got wrong. A missing participant and a participant
nobody calls look identical on a system diagram, and only one of them is a finding about
the architecture.

---

## 5. What a bundle must contain to be useful downstream

[M06](M06-stitcher.md) and [M07](M07-renderer.md) can only work with what travels. Tracing
backwards from the system architecture document:

| Needed for | Table |
|---|---|
| Matching endpoints | `endpoints` with wire identity and direction |
| **Structural payload compatibility** | `shapes` and `shape_fields`, with wire names |
| Resolving a call target to a participant | `deployments`, and aliases |
| **Cross-service sequence diagrams** | `edges` with control-flow position, `dispatch`, `dispatch_site`, `trace_summary` — the inputs `trace_of` walks over |
| Naming things | `symbols` for the symbols those tables reference |
| Honest rendering | The trust fields on every row above |

**The sequence-diagram row is the one to notice.** Traces are a named query, not a table
([D01](D01-graph-schema.md)): they travel implicitly, as the tables `trace_of` walks over.
If `dispatch` or the control-flow positions on `edges` do not travel, the system tier can
draw a service map but not a sequence — so omitting them is not an optimisation.

---

## 6. Naming and location

`<module-id>@<commit>` — sanitised for a filesystem. The commit is in the name so that two
analyses of one module coexist and `system.yml` can pin one.

Sextant writes a bundle to a directory. Publishing it to object storage or a package
registry is the caller's business; Sextant does not talk to artifact stores.

---

## 7. What a bundle must not contain

- **No unredacted values.** Redaction happened during extraction, and a bundle is exactly
  the artifact that leaves the machine.
- **No absolute paths from the producing machine.** Paths are relative to the module root.
- **No workspace database file.** Section 1.
- **No overlay files.** Curations are inputs to the system tier and live in git beside
  `system.yml`, not inside a module's bundle.

---

## 8. Open decisions

All three resolved for 2B:

- A bundle is a **directory**, never a single archive. Publishing is the caller's business;
  the archive question waits until publishing exists.
- `--what graph` is **deferred**. Facts are what make a bundle re-derivable, so a 2B export
  always carries both (§2).
- The full-text index does not travel, because none exists yet to travel.

None remain open for this phase.
