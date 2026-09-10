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
  render/                   architecture.md, architecture.html — present only when render ran
  index/*.ndjson            the lookup projection of F8 §9.3 — always written
```

> **Amendment (2026-09-02, Phase 2K design §6b — approved, delivered).** `render/` is new:
> whichever of `architecture.md`/`architecture.html` `sextant module render` (or `enrich`'s
> own auto-assembly, [ARCHITECTURE.md](../ARCHITECTURE.md) DR-2's amendment) already wrote to
> the workspace, copied byte-for-byte into the bundle by the exporter — not re-rendered, so
> the bundle and the workspace can never disagree about what a reader saw. `render` is not a
> prerequisite for `export` ([M08](M08-exporter.md)'s own rule still holds: "**No analysis.**
> It writes out what exists" — satisfied by copying `render/`'s output verbatim, never
> deriving it), so an unrendered workspace exports with no `render/` at all, exactly as it
> always has. `contents.render` in the manifest (§3) names exactly what shipped, so a
> consumer never has to list the directory to find out. **The overlay file itself,
> `.sextant-enrichment.json`, still never travels** — §7's rule is unchanged, and this
> subsection does not relax it: what ships is the already-assembled, already-redacted
> DOCUMENT an overlay produced, never the program artifact that produced it.

> **Amendment (F8 §9.3, W35/W36 — delivered).** `index/` is the bundle's THIRD projection,
> and it is a projection rather than data: eight NDJSON files derived at export from the
> tables already in `graph/`, so nothing in it is a claim the dataset does not already make.
> What it adds is the JOIN a consumer would otherwise perform — symbol to document to source
> root, and the reverse direction of edges the tables store one way round — and a
> `file:line` a reader can open.
>
> `symbols`, `callers`, `implementors`, `annotated`, `shape_carriers` and `addresses` each
> answer one question; `files` and `impact` assemble several. **NDJSON, ruled in §9.3**,
> because a grep hit returns one complete self-describing record, which is what matters when
> an agent opens the file cold with no schema and no engine — a Parquet table is not
> greppable and a DuckDB file must be learned before it answers anything.
>
> **It is an EXIT, so it masks** (D04 §1): the address-bearing fields take the same
> redactor `graph/`'s own address columns take, and a bundle whose index disagreed with its
> tables about one address would be two answers in one directory.
>
> **The accepted cost, stated in the design:** the index cannot be joined against the tables
> in DuckDB. Its job is to reach a `file:line` fast; after that the consumer opens the file,
> or queries the tables by the exact symbol the index handed back — which is why every
> record carries the symbol verbatim. Unlike `render/`, it is written on every export, so
> `contents.index` is never empty for a bundle this version produced.

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
                "fact_schema_version": 2,
                "graph_schema_version": 2,
                "scanners": [{ "id": "sextant-detector" },
                  { "id": "sextant-jvm-extractor",
                    "libraries": ["org.ow2.asm:asm:9.10.1"] }],
                "catalog_hash": "…" },
  "environments": ["dev", "staging", "prod"],
  "coverage": { "documents": 1283, "partial_documents": 0, "partial": false },
  "contents": { "facts": true, "graph": true, "tables": ["annotations", "call_edges", "call_sites",
                                                          "config_entries", "documents", "endpoints",
                                                          "error_handlers", "field_writes", "method_returns",
                                                          "open_questions", "raw_facts", "resolved_config",
                                                          "return_flows", "roots", "scheduled_work",
                                                          "shape_fields", "shapes", "symbols"],
                "facts_files": 1283,
                "render": ["architecture.md", "architecture.html"] },
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

**Two hashes, two moments.** A bundle carries a `redaction_set_hash` on each *document*
(`graph/documents.parquet`, from [D00](D00-fact-schema.md) §2) as well as this one on
`producer`, and they answer different questions. The per-document hash describes **read**
time — what was applied as those facts were produced — and it reads `sha256:none`, honestly,
because nothing is: the workspace, `raw_facts` and the local fact files all stay verbatim so
that resolution can substitute real addresses. `producer.redaction_set_hash` describes
**export** time: the set that masked *this bundle*. A consumer checking what it may
redistribute reads the producer field; a consumer reasoning about cache validity reads the
document field.

**What the bundle masks, precisely:**

| Where | Rule applied |
|---|---|
| `graph/resolved_config.parquet` `value` | key patterns + value patterns + URL userinfo |
| `facts/*.parquet` `config_entry` payload `value` | the same, keyed by the fact's own `key_path` |
| `graph/endpoints.parquet` `path`, `peer` | URL userinfo + value patterns |
| `graph/open_questions.parquet` `path` | the same, through the same map — a question and the row it asks about must mask identically |
| `graph/call_sites.parquet` `arguments`, `graph/annotations.parquet` `args`, `graph/return_flows.parquet` `value`, `graph/method_returns.parquet` `value` | URL userinfo + value patterns, over every string leaf — one map for one grammar, since all four are entries of D00 §5's argument shape built from the same string constants |
| `graph/roots.parquet` `path` | the same address map as `endpoints`, because the column is carried from it — a root masked differently from the endpoint it came from would name two different things |
| `graph/config_entries.parquet` `value` | the raw half of `resolved_config`, masked by the same `redact_value` keyed on the entry's own `key_path` |
| `graph/raw_facts.parquet` `config_entry` payload `value` | the same map the `facts/*.parquet` stream joins, so the two shapes of one table cannot disagree |

The last row is deliberately **not** key-based. A call argument is not a configuration key,
and the path and URL literals inside one are the wire identities the linking tier matches
services on — masking them by key name would gut the bundle to remove a secret that is not
there. What such a string does carry, when it carries anything, is an address with a
credential in front of it, and that is what userinfo stripping removes.

**The residual, stated rather than discovered:** an exotic hardcoded secret in a code
literal — one no key names, no value pattern matches, and that is not a URL with userinfo —
survives into the bundle. Closing it means value patterns, which is exactly what
[D04](D04-config-and-exclusion.md) §2a's `redact:` gives a repository that knows the shape
of its own secrets.

**`module_commit`** is the last commit touching this module's own path, computed locally at
scan time where a clone already exists. It is what lets the system tier judge staleness in a
monorepo without fetching history itself.

**`contents.tables` names what actually travelled**, written from the exporter's own table
list rather than hand-maintained — so `open_questions` (below) appears there beside
`endpoints`, `shapes`, `shape_fields`, `resolved_config`, `documents`, `symbols`,
`annotations` and `call_sites`, and the list is sorted so the manifest is deterministic.

**`contents.render` names what actually shipped under `render/`** (2K Task 8), the same
"declared, never discovered by listing the bundle" rule `tables` follows: `[]` on a
workspace `export` was run against before `render` ever produced anything, `["architecture.md",
"architecture.html"]` once both exist. The key is always present, exactly as
`tables`/`facts_files` are — never absent merely because nothing shipped under it — so a
consumer checking whether a rendered document travelled reads one field rather than probing
the bundle's own directory listing.

**`contents.index` names what shipped under `index/`** (F8 §9.3), by the same rule and for
the same reason. It differs from `render` in one way worth stating: the index is written on
every export, so `[]` means a bundle produced before the index existed rather than a step
somebody skipped.

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
| **The non-wire surfaces** | `scheduled_work` and `error_handlers` — what a service runs on a clock, and what it answers an exception with |

**The sequence-diagram row is the one to notice.** Traces are a named query, not a table
([D01](D01-graph-schema.md)): they travel implicitly, as the tables `trace_of` walks over.
If `dispatch` or the control-flow positions on `edges` do not travel, the system tier can
draw a service map but not a sequence — so omitting them is not an optimisation.

### Nothing is dropped on export

**Ruled by the user (C10): every table and view in the D01 schema travels, with no exclusion
class.** Parquet, DuckDB and the indices exist so an agent or a program can query fast, and
making a consumer re-derive what the workspace already holds is the friction the format
removes.

For four phases the export was a hand-written list of eleven names, and the seven it omitted
— `raw_facts`, `call_edges`, `return_flows`, `roots` and the three views `config_entries`,
`field_writes` and `method_returns` — were dropped from every bundle with nothing saying so.
The row above was therefore false as written: a reader could see a rendered trace and had no
way to recompute or check what it asserted.

**The ratchet runs the direction that catches the defect.** A table in the schema and absent
from the export is a TEST FAILURE, so the list cannot be hand-maintained and cannot fall
behind a new `CREATE TABLE`. Adding a table asks its author exactly two questions, and
neither can be skipped: *does it export?* — automatically, and the ratchet fails the build
otherwise; and *does analysis read its values?* — yes keeps the real value in the workspace
and redacts at this exit, no redacts at the origin instead. There is no third answer to
either.

**`raw_facts` travels twice, and that is not an exemption.** It ships as
`graph/raw_facts.parquet` — the whole table, queryable in one scan beside the derived tables
it explains — and as the per-document `facts/<document_id>.parquet` stream, which is the
shape a reader wanting one document's facts needs. Both join the same redaction map, so the
two cannot disagree about a single value.

**The cost, measured rather than assumed** (`fixtures/orders-service`, 3,588 facts across
118 documents): `graph/` is 214 KiB over 18 files, of which `raw_facts.parquet` is **109
KiB**; `facts/` is **410 KiB** over 118 files. So the second copy adds **21%** to a 625 KiB
bundle — and the whole-table form is *less than a third the size* of the per-document stream
carrying the same rows, because a parquet file's footer and column metadata are paid once
per file. The duplication is real and small; the shape that costs the most is the one that
was already there.

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

## 5a-i. The two non-wire tables

**`scheduled_work` and `error_handlers` ([D01](D01-graph-schema.md) §3) travel like any
other graph table** — `graph/scheduled_work.parquet` and `graph/error_handlers.parquet`,
each exported through its own named query so the row order is the one NFR-1 already fixed,
and each named in `contents.tables`. Neither is masked on the way out, and the reason is
that neither carries a masked column: the export projections mask the columns that can hold
a whole URL (`endpoints.path`/`.peer`, the ledger's `path`) and `resolved_config`'s values,
and a trigger expression, a scope attribute and a status are none of those.

**The rendered module document shows both as their own sections**, "Scheduled work" and
"Error handling", below the endpoint tables. Unlike "Open questions" above, **both render
even when empty**, with the endpoint tables' own "None found." — the difference is what an
absent section would mean. An empty inbox is not a finding; "this service runs no
background work" and "this service declares no error contract" both are, and a section that
simply disappears leaves a reader unable to tell that answer from a Sextant that never
looked.

The error-handling table leads with the exception, because that is what a reader looks a
row up by, and prints `Declared by` beside `Scope` because the two are one claim in two
columns ([D01](D01-graph-schema.md) §3): read alone, either gets a controller's own handler
and an application-wide advice the wrong way round. A NULL in any optional column renders
as an em dash, never a blank cell — the same rule Media already keeps.

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
| `kafka` / `jms` / `sqs` / `pubsub` / `amqp` / `pulsar` / `websocket` / `rsocket` / `soap` | `kafka order-events`, `amqp orders.created`, `websocket /orders/place`, `soap {http://orders.example.com/ws}placeOrderRequest` | verbless: the protocol defines no verb, so there is none to print |
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

- **It keys on the handler wherever there is one, the caller only where there is not.**
  So a path this module HANDLES stays unmarked even when the client calling it came out of
  a jar; marking it would attribute this module's own endpoint to a library. *This rule
  was written for the merged `both` row that kept the handler's own declaration; since
  W27 (F5 §6.1) nothing merges the two directions, and the rule now simply reads whichever
  of the two columns the row carries.*
- **One attribution per wire identity.** A `both` row — which the linking tier may write,
  and no pass here does — is listed in both tables, and the same finding stated twice
  reads as two findings.
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
  `system.yml`, not inside a module's bundle. The rule extends unchanged to 2K's
  `.sextant-enrichment.json` — the program artifact enrich writes never travels; what
  travels is the already-assembled, already-redacted `render/` output it produced (§2).

---

## 8. Open decisions

All three resolved for 2B:

- A bundle is a **directory**, never a single archive. Publishing is the caller's business;
  the archive question waits until publishing exists.
- `--what graph` is **deferred**. Facts are what make a bundle re-derivable, so a 2B export
  always carries both (§2).
- The full-text index does not travel, because none exists yet to travel. (M09's, that is
  — the LOOKUP index of F8 §9.3 does travel, as `index/*.ndjson`; the two are different
  things and this line is about the one that still does not exist.)

None remain open for this phase.
