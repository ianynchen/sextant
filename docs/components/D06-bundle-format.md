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
  "gaps": ["call_graph_not_implemented"],
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

**`redaction_set_hash` is written by the exporter**, beside `catalog_hash` and for the same
reason: it is what the exporter itself applied, not what `analyze` recorded. Under 2K design
§1 the workspace stays verbatim and masking happens at the exits, so `analyze` applies no
rule set and its provenance could not honestly claim one; this field names the effective set
— the built-ins widened by the module's `.sextant.yml` `redact:` section — that masked
**these** bytes. It is the sha256 of that set canonically serialized, so it is stable across
however a file happened to order its additions and moves the moment one changes.

What it covers, precisely: `graph/resolved_config.parquet`'s `value` column and
`graph/endpoints.parquet`'s `path`/`peer` address columns. **`facts/` is not covered** — a
`config_entry` payload still carries its value verbatim there. Ledgered, not silently
omitted: masking a fact payload changes what a fact means (a document's own
`redaction_set_hash` would have to stop reading `sha256:none`), which is a schema decision
rather than an export projection.

**`module_commit`** is the last commit touching this module's own path, computed locally at
scan time where a clone already exists. It is what lets the system tier judge staleness in a
monorepo without fetching history itself.

**`contents.tables` names what actually travelled**, written from the exporter's own table
list rather than hand-maintained — so `open_questions` (below) appears there beside
`endpoints`, `shapes`, `shape_fields`, `resolved_config`, `documents`, `symbols`,
`annotations` and `call_sites`, and the list is sorted so the manifest is deterministic.

**`documents` carries `origin`** — the coordinate of the library a document was extracted
from ([D00](D00-fact-schema.md) §2), NULL for the module's own output. Opting a library in
is the reader's own assertion that it is part of the module's runtime surface
([D04](D04-config-and-exclusion.md) §2a), and an assertion visible in the rendered document
but invisible in the published bundle would be laundered into module-observed evidence
exactly where it travels furthest from the person who made it. A consumer joins a symbol's
`document_id` to tell a library-contributed row from a module one.

**`environments`** lists the profiles this module resolved. Endpoints carry configuration
expressions rather than one environment's values, so a bundle serves every environment and
the system tier selects. **Live since Phase 2F**: populated from `resolved_config`'s own
distinct environments into `metadata.json` (`egress/render/metadata.py`), and carried
straight through into this manifest by the exporter — never re-derived, the same
never-re-analyze rule every other field here follows.

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
| **The enrichment tier's inbox** | `open_questions` — what no programmatic pass could answer |

**The sequence-diagram row is the one to notice.** Traces are a named query, not a table
([D01](D01-graph-schema.md)): they travel implicitly, as the tables `trace_of` walks over.
If `dispatch` or the control-flow positions on `edges` do not travel, the system tier can
draw a service map but not a sequence — so omitting them is not an optimisation.

## 5a. Open questions, and how a wire format is shown

**`open_questions` ([D01](D01-graph-schema.md) §3) travels like any other graph table** —
`graph/open_questions.parquet`, exported through its own named query so the row order is
the one NFR-1 already fixed, and named in `contents.tables`. It is the enrichment tier's
inbox: the questions a programmatic pass refused to guess at, each with its wire identity,
its kind, the candidates that were on the table, and the trail that reached the impasse.
It travels because the tier that answers it runs against the bundle, not against the
workspace that produced it.

**The rendered module document shows the same rows in an "Open questions" section**, one
line per row, each candidate rendered in the same prose the writing pass put in its own
trail — so a human reads the identical fact in the ledger and in the document. The section
is **absent** on a run with no rows, following the "catalogs skipped" precedent rather than
the "looked and found nothing" one: this is an inbox, and an empty inbox is not a finding.

**Format joins the endpoint tables beside Media**, on both the inbound and the outbound
table, and it is the **only** place a reader meets `format_resolution` — the document
carries no separate trust column. So the rendering hedges everything that is not the top
tier:

| Row holds | Renders |
|---|---|
| `format_resolution: resolved` | `protobuf` — unhedged, and this is the only case that is |
| any other non-NULL resolution (`narrowed`, and anything schema-valid but off today's live surface) | `protobuf (assumed)` |
| `format` NULL | `unresolved` — the same NULL-renders-`unresolved` rule the handler column keeps |

The hedge covers the merge exception too ([D01](D01-graph-schema.md) §3): a merged row
keeping a non-NULL `format` beside the weaker of its two halves' markers reads
`protobuf (assumed)`, never plain. Printing it plain would make an unsettled value
typographically identical to an observed one, which is exactly what "an assumed format must
never look observed" forbids. **No row reaches the renderer that way today** — the ladder
runs after the merge and answers every row, so the pair holds live — but the rendering rule
is written against the column's contract rather than against today's data, which is what
makes it still correct on the day a format is stamped before the merge.

**Declared shapes render through the existing shape tables unchanged**, with one addition:
a field's `field_number` rides beside its wire name as `totalAmount (1)` where the format
has one, and fields without one — every Avro field, every bytecode-derived field — render
exactly as before.

---

## 5b. How a wire identity is rendered

The endpoint tables print one string per row, and the shape of that string is decided by
the row's `protocol` — never by the catalog that derived it.

| Row | Renders | Why |
|---|---|---|
| `http` / `grpc` | `GET /v1/orders` | the verb implies its own protocol |
| `kafka` / `jms` / `sqs` / `pubsub` / `websocket` / `soap` | `kafka order-events`, `websocket /orders/place`, `soap {http://orders.example.com/ws}placeOrderRequest` | verbless: the protocol defines no verb, so there is none to print |
| `graphql` root operation | `graphql query orders` | verbed, and PREFIXED — a bare `query orders` names nothing in particular |
| `graphql` resolver (`method` NULL) | `graphql Order.lines` | the NULL is an absence by design, not an unread verb |
| `sse` | `sse GET /events/stream` | verbed with a real HTTP verb, and prefixed so it does not read as an ordinary REST route |
| any half unread | `(unresolved)` in that half | never a bare `None` |

**`soap` is verbless and was carried in the verbed half by mistake until Phase 2I.** The
protocol joined [D00](D00-fact-schema.md)'s closed set in 2H, when no catalog owned it, so
the misclassification rendered nothing and nobody could see it; 2I's first live SOAP rows
inherited it, and every one of them — `method` NULL by design, one POST shared by every
operation on a port — rendered `(unresolved)` beside a fully `resolved` address. Recorded
because the shape of the bug is the argument for the derived set below: a protocol placed
in the wrong half of a hand-listed pair says nothing at all until something derives a row.

**The verbless set is DERIVED — every protocol minus the verbed ones — so a protocol added
to [D00](D00-fact-schema.md)'s closed set renders verblessly by default.** That is right for
a broker family and it is why `websocket` needed no renderer change at all; it is wrong for
a route that really has a verb, which is why `sse` is named in the verbed half explicitly.
The protocol-qualified set is UNIONED into the verbed set rather than listed twice, so
"every qualified protocol is a verbed one" is structural: stating it in two places is what
would let a protocol be added to one list and fall silently out of the other, rendering
`sse /events/stream` and dropping a verb the row does have.

**A NULL verb is only excusable for the protocols that say so.** `graphql` is the one such
protocol today: a resolver implements a FIELD and answers no operation. An HTTP row with no
method genuinely is unread and must still say `(unresolved)`, and so must an SSE row —
which is exactly why the verb-optional set is its own set rather than the qualified one
reused.

**The Handler column tells apart two different NULLs.** Until Phase 2H every inbound row
with no handler was one whose address could not be read either, so one word covered both.
`schema_operations` ([D02](D02-catalog-schema.md) §2) makes the second case real: a schema
declares an operation outright — `resolution` is `resolved`, the identity is complete — and
names no code at all, because a schema never does and the wiring that would is explicitly
not read. Such a row renders **`none recorded`**, not `unresolved`, which would report a gap
that does not exist. `none recorded` rather than `none`: the claim is about what this
evidence carries, never that the service implements nothing. The discriminator is the row's
own columns — neither a handler nor a caller, and an address that resolved — not its
protocol or its catalog.

**A row a library contributed is marked, as a `Via: `<coordinate>`` detail line** under the
identity, in the same `Label: value` style the `Request:`/`Response:` lines use (Phase 2I).
Such a row is otherwise indistinguishable from one this repository declares — same table,
same columns, same resolution — and the difference is what a reader needs: the operation is
real, and the place to go and look is the library's source, not this module's. Three rules
make the marking honest rather than decorative:

- **It keys on the SURVIVING evidence — the handler wherever there is one, the caller only
  where there is not.** A merged `both` row keeps the handler's own declaration
  ([D02](D02-catalog-schema.md) §3), so a path this module HANDLES stays unmarked even when
  the client calling it came out of a jar; marking it would attribute this module's own
  endpoint to a library.
- **One attribution per wire identity.** A `both` row is listed in both tables, and the same
  finding stated twice reads as two findings.
- **A row naming neither handler nor caller is left unmarked** rather than guessed at.

The coordinate itself comes back through the document a symbol was declared in — an
endpoint row names a symbol and nothing more — which is the same `origin` the bundle's
`documents` table carries (§3), so the page and the published data cannot disagree.

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
