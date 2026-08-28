# D01 — Graph schema

The derived tables. Written by [M04](M04-resolver.md) at module scope and
[M06](M06-stitcher.md) at system scope. Read by [M07](M07-renderer.md),
[M08](M08-exporter.md) and [M09](M09-query.md).

Facts ([D00](D00-fact-schema.md)) are what was observed. This is what was worked out.

---

## 1. The rule that governs everything here

> **Facts are maintained per source file. Everything in this document is rebuilt whole.**

A derived row is a join across files. Adding one implementation of an interface changes no
fact in any other file, yet invalidates every dispatch edge in every file that called
through that interface. Patching derived tables in place cannot be made correct.

So: base fact tables get a delete-and-reinsert for changed files; derived tables are
recreated. This is affordable because a typical edit touches under one percent of files,
and the derived pass is bounded by the graph, not by the repository.

---

## 2. Base tables

One-to-one with [D00](D00-fact-schema.md) fact kinds, loaded in bulk. Every row carries
`document_id`, so a changed file is one delete and one insert.

`documents`, `symbols`, `relationships`, `occurrences`, `annotations`, `call_sites`,
`constants`, `string_literals`, `config_entries`, `dependencies`, `deployments`,
`declared_contracts`.

**Bulk load only.** Per-row insertion across a fact set is a defect (NFR-11). The
difference is orders of magnitude.

---

## 3. Derived tables

### Structure

| Table | Holds |
|---|---|
| `symbol_index` | Interned identifier to integer, so every other table stores an integer |
| `containment` | Symbol to enclosing symbol |
| `symbol_ancestry` | The transitive closure of containment, for constant-time roll-ups |
| `hierarchy` | The transitive supertype relation |
| `symbol_tokens` | Identifier split on case and underscore, for approximate lookup |

### Edges

One table, `edges`, with `kind`, the trust fields, and `sites` — the file and line of every
occurrence, denormalised so that showing the evidence behind a claim never requires a
second join.

`calls` edges additionally carry the **control-flow position** of their call site,
denormalised from the fact. This is what lets `trace_of` — and therefore every sequence
diagram — run from the graph alone, so a graph-only bundle still renders sequences without
the fact files.

Kinds kept, and why each survives NFR-6:

| Kind | Consumed by |
|---|---|
| `calls` | Traces, sequence diagrams, outbound endpoints, dispatch |
| `contains` | The only route from a symbol to its file |
| `inherits`, `implements` | Class diagrams, dispatch |
| `return_type`, `parameter_type`, `field_type`, `type_use` | **Blast radius and `uses`** |
| `handles` | Endpoint to handler |
| `invokes` | Caller to outbound endpoint |
| `env_var_read` | Configuration surface |

**The four type-reference kinds are here deliberately.** They are a substantial fraction
of the graph, and a diagrams-only tool would drop them as unused. Blast radius is on our
list, and they are its substrate.

Kinds deliberately **absent**: `imports` (restates references and containment),
`field_read` and `field_write` (in JVM code, cross-object field access goes through
accessors, which are already `calls`), and `contains` from class to method (the method's
own identifier already names its class).

### Dispatch

| Table | Holds |
|---|---|
| `dispatch` | Call site, candidate symbol, one row per candidate |
| `dispatch_site` | Call site, `resolution`, `reason`, candidate count |

The tier lives on the **site**, not the candidate. It describes how much is known about the
call, and does not rank candidates against one another.

### Contracts

| Table | Holds |
|---|---|
| `shapes` | Shape identifier, content hash, whether open |
| `shape_fields` | Shape, ordinal, **wire name**, type, required, tags |
| `endpoints` | Direction, protocol, wire identity, handler or caller, request and response shapes, trust fields |
| `resolved_config` | Key, value, source, environment, or unresolved with a reason |

**Declared shapes land in these same two tables**, loaded from `declared_shape` facts with
`evidence: declared`, their field types already in the wire-type vocabulary
([D00](D00-fact-schema.md) §5b). Code-derived shapes project into that vocabulary during
expansion. One representation downstream means the drift report and the stitcher compare
field lists without caring which side came from code.

**`shape_fields.wire_name` is the identity, never the source field name.** After a naming
strategy or an explicit serialisation annotation, `customerId` and `customer_id` may be the
same field. For formats where a number is the identity, the number is stored and the name
is decoration.

**Inbound and outbound share one `endpoints` table** with a `direction` column taking
`inbound`, `outbound` or `both`. Two near-identical tables were the alternative, and were
measured as a mistake.

**Endpoint identity is minted from the wire contract**:
`hash(module id, protocol, direction, wire identity template)` — the path template with
placeholders normalised, the topic expression, the fully-qualified remote method, or **the
operation name where one address carries many operations**. Never
from the handler symbol: a refactor that moves the handler must not orphan the curations,
proposals and links that reference the endpoint, because the wire contract they were about
did not change. Editing the path *is* a new endpoint, correctly. Two handlers declaring
the same wire contract collide into one identity — and that collision is a routing-ambiguity
finding, which per-handler identity would have hidden. Environment expressions hash as
expressions: `${orders.topic}` is the same endpoint in every environment.

**Where one address carries many operations, the operation is the endpoint.** GraphQL puts
every operation behind a single `POST /graphql`; SOAP puts them behind one path with the name
in the envelope; WebSocket puts them behind one connection with the name in each frame. gRPC
already works this way and set the precedent — its wire identity is `package.Service/Method`,
not the HTTP/2 path.

The address is **not** discarded: it stays on the endpoint as `path`, which for REST coincides
with the wire identity and for these protocols does not. So `/graphql` is where the operation
is reachable, and `Query.getOrder` is what it is.

The reason is that aggregation is possible and disaggregation is not. Recording operations
still allows one arrow per service by grouping on `path`; recording only the address can never
answer *who calls `getOrder`* without a second matching mechanism built alongside the first.
The cost is real and lands on rendering rather than on the schema — a service with two hundred
GraphQL fields has two hundred endpoints, and [M07](M07-renderer.md) must group them by `path`
unless asked otherwise, or every diagram of such a service is unreadable.

### Traces — a named query, not a table

A trace is everything reachable from one inbound endpoint. Storing it would copy every
shared subtree once per endpoint that reaches it — a validator on the path of 150 endpoints
would appear 150 times, and the copies would dwarf the `edges` table they were copied from.

And nothing in a trace is original: the call structure is `edges` plus `dispatch`; the
nesting is the control-flow position carried on `calls` edges; the roots are `handles`
edges; and every terminal kind except `cycle` is an intrinsic property of the call site.
The only per-trace information is membership and the cycle marker — both products of the
walk itself.

So the walk **is** the representation: `trace_of` (§5) computes it on demand, detecting
`cycle` as it goes, over the same tables at module scope and over the federation at system
scope. A trace can never disagree with the edges it came from, because it is them.

One table is materialised, because findings need its numbers without walking everything:

| Table | Holds |
|---|---|
| `trace_summary` | Per inbound endpoint: hop counts, services involved, terminal counts by kind, endpoints reached more than once |

A trace is a subgraph with ordering and nesting, not a list of routes. Its size grows with
the code reached, not with the branching — which is why it needs no depth bound. If full
walks ever prove slow at render time, the fix is caching the walk result per run — lazy
materialisation where measurement demands it, not presumed everywhere.

### System scope — two native tables, everything else federated

| Table | Holds | Stored |
|---|---|---|
| `participants` | Service or external, name, aliases, **bundle location**, commit | Natively |
| `links` | Outbound endpoint, inbound endpoint, trust fields, candidates | Natively |
| `symbols`, `edges`, `endpoints`, `shapes`, `shape_fields`, `traces` | Each participant's own graph | **Views over the bundles** |

The system workspace does **not** copy the estate's graphs. Bundles are Parquet, and one
query reads Parquet across many paths, so a view is enough.

**This is what makes cross-service impact answerable.** Impact does not travel along call
edges — services exchange payloads, not method calls — so the traversal is:

```
  Money#amount  →  shape_fields  →  endpoints  →  links
                →  the inbound endpoint on the other side
                →  its handler symbol  →  local edges there
```

Every step after `links` needs another participant's tables. Federating them costs no import
stage and cannot drift from the bundle, because it *is* the bundle.

**The join needs no mapping layer.** A symbol identifier carries package and version, so
`Money#amount` from `shared-domain 2.1.0` is the same string in every participant that
depends on it. Where two services use different versions, the symbols correctly differ —
and that divergence is itself worth reporting.

**Two obligations follow.** Bundle locations are recorded in `participants` and in
`system.state.json` ([D05](D05-manifest-and-state.md)); and a bundle that is unreachable **at
query time** fails with a message naming it, never a shorter answer.

### Observations

| Table | Holds |
|---|---|
| `findings` | Kind, subject, severity, evidence sites |
| `open_questions` | Kind, the claims that disagreed, their sources and ranks |

`open_questions` is not an error log. It is output: a recorded disagreement a person should
settle.

---

## 4. Search

| Table | Holds |
|---|---|
| Full text over `symbols.display_name`, `documentation`, `string_literals.value`, `endpoints.path` | Word search, because people search in words before they query in structure |

**The string-literal index is the root-cause path.** Paste a log line, find the literal,
find its enclosing symbol, walk upward to the endpoints that reach it. Three queries. The
literals are already extracted for endpoint paths; storing all of them is nearly free.

---

## 5. Named queries

Shipped as part of the schema, not left to each consumer to write. [M09](M09-query.md) and
[M07](M07-renderer.md) both use them, and neither should be writing its own reachability
query.

`callers_of`, `callees_of`, `implementations_of`, `uses_of`, `impact_of`,
`paths_between`, `endpoint_for_address`, `trace_of`, `who_uses_shape`, `who_reads_config`.

`impact_of` returns three partitions — definite, possible, and the unknown regions reached
— never one count. `paths_between` returns the union subgraph of all routes, never a list
of routes.

---

## 6. What this schema must not contain

- **No fact that was merely copied.** If a row adds nothing to [D00](D00-fact-schema.md), it
  is a view, not a table.
- **No materialised blast radius.** It is a query. Storing it for every symbol would be
  enormous and always stale.
- **No table with no consumer.** NFR-6 applies here more strongly than to facts, because
  derived tables cost time on every run.
- **No prose columns.** Names and purposes arrive as overlays and are joined at render.

---

## 7. Stamping and invalidation

**A result can change when Sextant changes, even when nothing about the code does.** A fixed
bug in dispatch resolution produces a different graph from identical facts. So every result
records what produced it, and any change forces the affected work to be redone.

### What is recorded

| On | Fields |
|---|---|
| Each **document** | `sextant_version`, `fact_schema_version`, `scanner_id`, `scanner_version`, `content_hash`, `redaction_set_hash` |
| Each **workspace** | The above, plus `graph_schema_version` and `catalog_hash` |
| Each **bundle** | The workspace stamp, in its manifest |
| Each **system workspace** | Its own stamp, plus the stamp of every bundle it used |

The document record is per **source file**, which is where incremental reuse happens — so
this is where the stamp makes cache invalidation exact rather than approximate.

### Two schema versions, not one

Facts and derived tables version separately, because their invalidation costs differ by an
order of magnitude.

| Change | Invalidates | Cost |
|---|---|---|
| `fact_schema_version` | Facts, and everything after | **Re-extraction.** The expensive one. |
| `graph_schema_version` | Derived tables only | Re-derivation. Minutes. |
| `scanner_version` or `scanner_id` | That scanner's facts | Re-extraction, for those documents |
| `redaction_set_hash` | Facts | Re-extraction. A new pattern cannot clean values already written. |
| `catalog_hash` | Endpoints and everything after | Re-derivation |
| `sextant_version` | Derived tables | Re-derivation — **conservative by default** |

**The last row is deliberately blunt.** Any Sextant version change re-derives, because
derivation logic may have changed and there is no cheap way to know. Re-derivation is the
cheap half. If that becomes painful, the answer is a separate version bumped only when
derivation behaviour changes — not a weaker default.

**A mismatch never produces a mixed-vintage graph.** It forces the affected rebuild. That is
what keeps per-row stamping unnecessary: the guard is complete, so a workspace can only
contain one vintage.

The same stamp travels in the bundle ([D06](D06-bundle-format.md)) so that
[M05](M05-sync.md) can refuse to assemble a system from incompatible parts.

---

## 8. Open decisions

| Decision | Blocks |
|---|---|
| Whether `trace_steps` stores nesting as a path or as parent references | M07's sequence emitter |
| Whether `findings` is one table with a kind column or one table per family | M04 |
| Whether the full-text index lives in the workspace only, or also in a bundle | M08 |
