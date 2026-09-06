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
| `shapes` | `shape_id`, content hash, whether open |
| `shape_fields` | Shape, ordinal, **wire name**, **field number**, wire type and format, required, nullable, trust fields, tags, item descriptor |
| `endpoints` | Direction, protocol, wire identity, handler and/or caller, peer, request and response payload descriptors, declared media types, **wire format and its resolution**, trust fields |
| `resolved_config` | Key, value, source, environment, or unresolved with a reason |
| `open_questions` | One question a programmatic pass refused to guess at: wire identity, question kind, the candidate answers, the trail that reached the impasse |

**A `both` row keeps both `handler` and `caller`.** A wire identity a module both exposes and
calls merges into one endpoint row rather than two — `handler` names the server method,
`caller` names the client method, and both are populated. An outbound-only row carries
`caller` with `handler` NULL, mirroring an inbound-only row's NULL `caller`. `peer` is the
outbound target hint — a declared service name, a literal authority, or **a whole address
expression where an operation-carrying protocol leaves nothing for the address to be split
on** — that the system tier later resolves against `participants`; it carries no meaning on
an inbound-only row.

**The whole-address case is Phase 2I's, and it is a widening of this column rather than a
new one.** A SOAP row's `path` carries the operation (below), so the url an outbound call
states is only ever a peer: it is recorded WHOLE — `${soap.billing.uri}`, or a literal
`http://billing.example.com/ws` — rather than split into an authority and a path the way an
HTTP client's base address is. Two reasons, both refusals: a configuration expression has no
authority half to take, and two deployments behind one host are two peers. `resolved_peers`
substitutes such an expression per environment exactly as it does for any other, because it
reads a placeholder out of `peer` and does not care what shape the rest of the string is.

**A merged `both` row is the ordinary outcome where a module serves and calls one
operation.** The fixture's `{http://orders.example.com/ws}placeOrderRequest` is derived
twice — once from the handler's own `@PayloadRoot`, once from the payload type the client
hands to a template call — and the two meet because both engines compose the same QName
string from two different annotations. The handler's row survives with the caller and the
caller's `peer` carried onto it, per [D02](D02-catalog-schema.md) §3. One consequence is
worth stating because a real fixture shows it: **`peer` is not part of wire identity**, so
two calls to one operation at two different addresses are one endpoint row carrying one
address — the first derived, in the order the call sites were read. Recording both would
mean putting the address into the identity of a protocol whose identity is the operation,
which is the aggregation the rest of this section refuses.

**`endpoints.catalog_id` is provenance, not identity.** It names the catalog whose rules
produced the row, so a catalog describing an endpoint's request/response contract can
scope itself to exactly the rows its own derivation wrote rather than reasoning about
direction, protocol or row-level overrides. It plays no part in endpoint identity — the
hash below never includes it, and a refactor of the catalog files themselves must not
orphan an endpoint — and it is never compared across services: it is a local fact about
which catalog derived this graph's own row, not a cross-service correlation key.

**The merge keeps only the handler's request and response payload descriptors.** Where the
module both exposes a path and calls it through a client with its own declared contract, the
two declarations can differ — the handler's survives on the `both` row and the client's is
discarded. This is a named gap (`merged_endpoints_keep_only_the_handlers_contract`), not a
silent loss.

**Declared shapes land in these same two tables**, loaded from `declared_shape` facts with
`evidence: declared`, their field types already in the wire-type vocabulary
([D00](D00-fact-schema.md) §5b). Code-derived shapes project into that vocabulary during
expansion. One representation downstream means the drift report and the stitcher compare
field lists without caring which side came from code.

**`shape_fields`'s columns are `shape_id`, `ordinal`, `wire_name`, `field_number`, `wire_type`,
`wire_format`, `required`, `nullable`, `resolution`, `evidence`, `tags`, `item`.** An earlier draft of this
table said "type" where the vocabulary ([D00](D00-fact-schema.md) §5b) actually carries two
parts — a base type plus an optional qualifier, `integer` and `int64` answering different
questions — so `wire_type` and `wire_format` are separate columns rather than one string a
consumer would have to re-split (decision D1 of the shapes-and-nullability plan). `nullable`
sits beside `required` because [D00](D00-fact-schema.md) §5a makes them independent
two-valued flags: a field may be required-and-nullable or optional-and-not-null, and one
column cannot hold two answers. `resolution` and `evidence` accompany it per decision D3 of
that plan and the general trust-field rule ([D00](D00-fact-schema.md) §3) — a `nullable` read
off a language default and one confirmed by an explicit annotation are different claims, and
DR-5's comparison must be able to tell them apart rather than trusting both equally. `tags` is
unchanged from the original column list; dropping it silently would be the same defect as
adding columns without saying so.

**`item` is JSON, holding the same recursive descriptor a fact-level type reference already
uses: `{wire_type, wire_format, nullable, shape_id?, item?}`.** `shape_id` is the payload
type's symbol — a local join key into `shapes`, never compared across services; DR-5 matches
field structure, not identifiers. A single `wire_type` cannot describe a collection —
`List<String>` and `List<CustomerRef>` are both `array` — and without an element descriptor,
DR-5 would match a caller sending an array of strings against a callee expecting an array of
records: a fabricated link, which is exactly what DR-5's payload comparison exists to
prevent. `item` is `NULL` for a scalar field, the element descriptor for an `array`, the
**value** descriptor for a `map` — a JSON object's keys are always strings, so a key
descriptor would carry no information — and the full descriptor of the referenced shape for
an `object` field — one grammar, so a consumer never detects which variant it holds. Nesting
recurses through `item`, so `Map<String, List<String>>` needs no special case beyond this one
column.

**`shape_fields.wire_name` is the identity, never the source field name.** After a naming
strategy or an explicit serialisation annotation, `customerId` and `customer_id` may be the
same field. For formats where a number is the identity, the number is stored and the name
is decoration.

**`shape_fields.field_number` is that number, and it is NULL wherever the format has
none.** A protobuf field carries it; an Avro field does not (Avro matches by name against
the writer's schema), and neither does any bytecode-derived field — an annotation-derived
shape has no schema to number it. So a NULL here is "this format does not number fields",
never "the number was not read": only a `declared_shape`'s own fields ever populate it.

**`endpoints.request_shape` and `endpoints.response_shape` hold the same recursive
descriptor** (`{wire_type, wire_format, nullable, shape_id?, item?}`) rather than a bare
shape id — the grammar `shape_fields.item` uses above, reused rather than duplicated. A
`List<OrderView>` response is
`{"wire_type":"array","item":{"wire_type":"object","shape_id":…}}`; a scalar response is
recorded rather than dropped (`{"wire_type":"string"}`); and `NULL` means exactly *no
payload* — a `void` return, or no body parameter — the one meaning it has always had. On a
row whose own `resolution` is `unresolved` ([D02](D02-catalog-schema.md) §2's `single_call`:
any declared capture — url, body or response — that failed to resolve drops the row's
`resolution`, checkpoint ruling I1), a `NULL` payload column *may* mean the payload could not
be read — the flag says some declared capture failed, without naming which, so a `NULL`
column on such a row is not by itself a claim of no payload.

**`endpoints.consumes` and `endpoints.produces` hold the declared media types**, each a JSON
array of MIME strings verbatim, or `NULL`. `NULL` means no declaration is derivable from any
evidence source — never a guessed default: an undeclared mapping is negotiated at runtime
against the caller's `Accept` header, which is a different fact from a declared
`["application/json"]`. A declared restriction rejects a mismatched request with 406; an
undeclared one negotiates. Four evidence kinds fill the lists — mapping attributes and route
options; catalog-declared framework-contract defaults; call- and type-evidence such as a typed
response wrapper; and config-declared defaults. 2E implements the first kind, for Spring's own
mapping attributes; the framework-default and config-declared kinds are specified for later
phases to fill. MIME strings are the comparison vocabulary because they are byte-comparable
across languages: DR-5's rule over them is conservative — `NULL` is compatible with anything,
and two declared lists must otherwise intersect. Which evidence kind produced a declaration (an
enforced `produces=` attribute versus an observed response-wrapper type) is not distinguished by
these two columns; that strictness is deferred to L, where `catalog_id` above already names each
row's provenance. Dedup and merge treat `consumes`/`produces` as carried data, never identity —
wire identity is `(protocol, direction, method, path)` regardless of what either column holds.
Rows that differ only in declared media are one endpoint: the union of their lists happens
engine-side, within a single derivation batch, order-normalised (NFR-1); across batches the
existing first-writer dedup stands unchanged.

**Amendment (2O design §8, Phase 2O Task 2, as narrowed by ruling R8): for an INBOUND
`http` row, `path` holds THE URL THE FRAMEWORK SERVES, not the characters the declaration
spelled.** Identity is minted through one canonicalization (`sextant.domain.paths`) —
leading separator guaranteed, exactly one separator per combine boundary, trailing separator
preserved as **distinct**, because Framework 6 removed trailing-slash matching (checkpoint
CP-1, confirmed live against Boot 4.0.1). `@RequestMapping("users")` and
`@RequestMapping("/users")` were two identities for one URL, which split dedup and every
path-keyed anchor built on this column — the export, the overlay anchors, and L's
cross-service joins.

**Scoped to INBOUND `http`, and to path-shaped values.** A `path` holding a whole address or
a placeholder-bearing composition (`https://${billing.host}/orders`, kept whole here until
the peer join splits it) is untouched, GraphQL's `path` is a field name rather than a URL,
and STOMP/websocket and every broker destination keep the character-for-character rule
above. SSE rows inherit the canonicalization without being named by it, because
`protocol_hint` reclassifies them after identity is minted. **OUTBOUND `http` is excluded
(R8)**: CP-1 is evidence about what a server SERVES, and a client's slashless path is
resolved against its configured base address's own PATH while a leading separator is
root-relative — against `https://host/v1/` those are two different URLs, so canonicalizing
one would rewrite an address rather than normalize a spelling, the approximation DR-6
forbids. This amendment's purpose is one identity per route the module SERVES; an outbound
row's identity is a composed address the peer join governs, and it keeps the half the
declaration wrote. **This migration moves already-recorded rows**; its four consequences —
goldens, overlays rejected whole, enrichment claims gone stale, `open_questions` snapshots
re-deriving — are in `CHANGELOG.md`.

**`endpoints.format` and `endpoints.format_resolution` hold what is on this channel's
wire, and how much that answer is worth.** `format` is one of [D00](D00-fact-schema.md)
§4's format values or NULL; `format_resolution` is the same `resolution` set every other
column uses. Both are stamped by **one late pass over every row** — the six-rung ladder
([D02](D02-catalog-schema.md) §2c) — never by a derivation: a mapping annotation declares
a MEDIA type, and turning one into a wire format is a question about the whole finished
row. `resolved` means declared evidence named the wire outright (a protocol whose format
is constant, a declared MIME string, a configured serializer); `narrowed` means only a
framework default or the payload's own type suggested it; `unresolved` means nothing did.

**`format_resolution` is the authority on trust, and `format` is an answer that may be
worth showing beside it.** As the ladder writes them the two are paired: `format` is NULL
exactly when `format_resolution` is `unresolved`. **One statement breaks that pair on
purpose.** The inbound/outbound merge ([D02](D02-catalog-schema.md) §3) carries `format`
the way it carries the media columns — the surviving row's own answer, else the twin's —
but `format_resolution` takes the **weaker** of the two halves' markers, ordering
`unresolved` < `narrowed` < `resolved`, so a half that only guessed can never launder
into an observation by being merged with a half that knew. A merged row may therefore
read `(protobuf, unresolved)`: *this is the format one direction declared, and this
identity as a whole is not settled*. A reader must consult `format_resolution` before
believing `format`, and a renderer must not print a non-`resolved` format unhedged
([D06](D06-bundle-format.md) §5a).

**The exception is shipped semantics with no live surface today**, and both halves of that
matter. The merge is the last statement of the endpoint derivation and the ladder is the
last pass of a resolve, so both format columns are still NULL when the merge runs and every
row is answered afterwards — on every live row the pair holds, `format` NULL exactly when
`format_resolution` is `unresolved`. The rule is written down, and readers and renderers
must honour it, because the branch becomes reachable the day anything stamps a format
before the merge — a derivation that reads one off a declaration, or a reordered pipeline —
and the failure mode then is a silently discarded half, indistinguishable from a module
that declared no format.

**Inbound and outbound share one `endpoints` table** with a `direction` column taking
`inbound`, `outbound` or `both`. Two near-identical tables were the alternative, and were
measured as a mistake.

**Endpoint identity is minted from the wire contract**:
`hash(module id, protocol, wire identity template)` — the path template with
placeholders normalised, the topic expression, the fully-qualified remote method, or **the
operation name where one address carries many operations**. Never
from the handler symbol: a refactor that moves the handler must not orphan the curations,
proposals and links that reference the endpoint, because the wire contract they were about
did not change. Editing the path *is* a new endpoint, correctly. Two handlers declaring
the same wire contract collide into one identity — and that collision is a routing-ambiguity
finding, which per-handler identity would have hidden. Environment expressions hash as
expressions: `${orders.topic}` is the same endpoint in every environment.

**Direction is not a hash input.** An earlier draft hashed *(module, protocol, direction,
wire identity)*, but [D02](D02-catalog-schema.md) §3's inbound/outbound merge makes direction
mutable: a path a module only exposed can gain a client and become `both` without its wire
contract changing at all. Mutable state does not belong in identity, by the same argument
this paragraph already makes for the handler symbol — a refactor, or here a new call site,
must not orphan the curations, proposals and links built against the endpoint, because the
wire contract they were about did not change.

**Where one address carries many operations, the operation is the endpoint.** GraphQL puts
every operation behind a single `POST /graphql`; SOAP puts them behind one path with the name
in the envelope; WebSocket puts them behind one connection with the name in each frame. gRPC
already works this way and set the precedent — its wire identity is `package.Service/Method`,
not the HTTP/2 path.

The reason is that aggregation is possible and disaggregation is not. Recording operations
still allows one arrow per service by grouping on the operation's own scope; recording only
the address can never
answer *who calls `getOrder`* without a second matching mechanism built alongside the first.
The cost is real and lands on rendering rather than on the schema — a service with two hundred
GraphQL fields has two hundred endpoints, and [M07](M07-renderer.md) must group them
before drawing, or every diagram of such a service is unreadable.

**The operation identity forms, as built (Phase 2H).** An earlier draft of this section
said the transport address stays on the row as `path` (`/graphql`) with the operation
recorded beside it. **That is not what shipped, and the `path` column carries the
OPERATION.** There is nowhere else for it: `path` is the identity column, the merge and
the dedup key are `(protocol, direction, method, path)`, and parking the transport
address there would collapse every field of a schema into one endpoint — the exact
aggregation this section refuses. The HTTP address a GraphQL or STOMP service listens
on is not derived at all today, by any engine; where a phase needs it, it is a new
column with its own evidence, never this one.

| Form | `protocol` | `method` | `path` | Derived by |
|---|---|---|---|---|
| GraphQL root operation | `graphql` | `query` / `mutation` / `subscription` | the field name (`orders`) | the annotation catalogs, and `schema_operations` from the SDL |
| GraphQL non-root resolver | `graphql` | NULL | `Type.field` (`Order.lines`) | the annotation catalogs |
| WebSocket / STOMP | `websocket` | NULL | the connection path or destination (`/live`, `/orders/place`) | the WebSocket and STOMP catalogs |
| SSE | `sse` | the HTTP verb (`GET`) | the route path (`/events/stream`) | an HTTP row, reclassified ([D02](D02-catalog-schema.md) §2's `protocol_hint`) |
| SOAP operation | `soap` | NULL | the input element's QName in W3C notation (`{http://orders.example.com/ws}placeOrderRequest`) | the SOAP annotation catalogs, `single_call` off the payload type, and `schema_operations` from the WSDL |
| SOAP action | `soap` | NULL | the action URI verbatim (`http://orders.example.com/action/cancelOrder`) | the Spring-WS catalog |
| gRPC operation | `grpc` | NULL | `<protoPackage>.<Service>/<Method>` | the `.proto` descriptor (`schema_operations`, Phase 2O Task 4) and the generated class's own bytecode (`supertype_derived`, Task 5) — the SAME identity, independently derived, merging on it by construction |
| gRPC service (outbound) | `grpc` | NULL | `<protoPackage>.<Service>` — the SERVICE alone, no method | an injected client stub (`injected_client`, Task 5) |

**SOAP is verbless, and it carries TWO identity forms on one protocol** (Phase 2I). The
verb goes because every operation on a port shares the transport binding's own POST, so a
method column would distinguish nothing — the 2D messaging answer, reached by a different
route. The two forms are a real split rather than a spelling difference: a QName is the
identity of the payload's root element, which is what an annotation, a client's payload
type and a WSDL input element all independently state and therefore what they meet on,
while an action URI is a header the transport dispatches on. **The notation is W3C's own**
(`{namespace}localPart`, `javax.xml.namespace.QName.toString`) precisely because it is
framework-neutral: rows derived from a Spring-WS annotation, from a JAX-WS one and from a
`.wsdl` file have to be one string to merge at all. An action row links only where a client
states the same action, which code rarely does — a stated boundary
([COVERAGE](../COVERAGE.md) §5.3), not a defect in the form.

**gRPC carries TWO identity forms on one protocol too** (Phase 2O). Both are verbless, for
the same reason SOAP's are: gRPC has no HTTP-shaped verb to distinguish rows by, and every
RPC dispatches by name, not by method. The `<protoPackage>.<Service>/<Method>` form is a real
operation — one row per RPC method, `method` NULL, `path` the full method identity — derived
two independent ways that merge on the identical string (D02 §5's own join, no new rule): the
`.proto` descriptor states it outright, and the compiled `<Service>Grpc` class's own
identity-building call sites state the SAME string from bytecode alone (R11:
`ServiceDescriptor.newBuilder`'s and `MethodDescriptor.generateFullMethodName`'s own literal
arguments, never a field value).

**What each side CONTRIBUTES to the merged row is different, and the row keeps both** — a
correction, because for one revision it did not. The bytecode side contributes the `handler`
symbol and the proof that the method is actually implemented; the descriptor side
contributes `request_shape`, `response_shape` and the
`unary | server-streaming | client-streaming | bidi` Detail that rides the response
descriptor's own `shape_id`. The bytecode row is inserted first and the descriptor's insert
at the same identity is then a no-op under insert-if-absent — so the descriptor's half
reaches the row by STAMP, not by insert
(`stamp_declared_request.sql`/`stamp_declared_response.sql`, each guarding its own column on
`IS NULL`, run by the `schema_operations` engine from the runs-last group for exactly this
purpose). Without those stamps a gRPC endpoint that BOTH halves proved would publish
strictly less than the descriptor alone would have, which is the redundancy this design is
built on running backwards. The `<protoPackage>.<Service>` form — SERVICE-level, no
method — is deliberately coarser: an injected client stub (`@GrpcClient`) proves the module
TALKS TO a service, not which of its methods it calls, and minting one row per service method
from that evidence alone would fabricate a boundary nobody observed. **This row links to
nothing today** — DR-5 matches identities exactly, and `package.Service` never equals
`package.Service/Method` — until a later phase's call graph can name the actual method calls
and derive the finer form instead ([COVERAGE](../COVERAGE.md) §5.7).

Three things follow, and each is a real distinction rather than a shading of one rule.
**A GraphQL row's `method` is an OPERATION TYPE, not a verb** — a caller sending a
mutation must not match a query, so it is part of the identity exactly as `GET` is — and
a resolver's NULL there is an ABSENCE BY DESIGN: it implements a field, it answers no
operation, and `Type.field` is the whole address. **A WebSocket row is verbless
outright**, the 2D messaging precedent unchanged. **An SSE row keeps its HTTP verb**,
because an SSE stream really is a route a client GETs; only its protocol changed.
[D06](D06-bundle-format.md) §5b renders each of these.

**`resolved_config` is one row per key per environment.** A resolved row carries `key`,
`value`, `source` — the file that won precedence for that key in that profile's layering
([D02](D02-catalog-schema.md)'s `config_model`) — and `environment`. An unresolved row
carries the same `key` and `environment` with `value` NULL and a `reason` from a closed
five-value set: `missing_key`, `environment` (the value comes from an environment variable
or a launch flag — universal across ecosystems, and never resolvable from files alone),
`remote_source` (a config-server or `spring.config.import` URL), `placeholder_cycle`, and
`multi_placeholder` — used only by the peer-resolution join below, never by the resolution
pass itself, for an outbound expression carrying more than one placeholder, substitutable
only piecewise. "Unresolved for `prod`, resolved for `dev`" is expressible and meaningful:
the same key carries a resolved row in one environment and an unresolved one in another,
never one row forced to answer for both.

**Peer resolution is a join, never a write.** A named query joins outbound endpoint rows'
`${...}`-bearing `peer`/`path` expressions against `resolved_config`, per environment,
substituting single-placeholder expressions and answering `multi_placeholder` for the rest.
Endpoint rows are untouched — `resolved_config` carries values, endpoints keep expressions,
and nothing rewrites an endpoint row per environment.

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
| `open_questions` | The endpoint's wire identity, the question kind, the candidate answers, the evidence trail |

`open_questions` is not an error log. It is output: a recorded disagreement a person should
settle.

**As built it is the hand-off ledger for the enrichment tier** — one row per question a
programmatic pass could not answer and refused to guess at. Columns: `protocol`, `method`,
`path` (the wire identity, **carried rather than joined** — the row is an artifact a human
and the enrichment tier read, and a foreign key into a table rebuilt every resolve would
name nothing outside this run); `question`; `candidates`, a JSON array; and `evidence`.

`question` is a **closed five-value set — `payload_binding`, `format_conflict`,
`channel_destination`, `service_identity` and `environment_divergence`** — checked by the
single owning module before any row is inserted, because the value is
bound straight into a published artifact where a typo is indistinguishable from a kind of
question nobody implemented. Adding a kind is a schema change (NFR-5): both the renderer
and the export switch on it. *This paragraph said "two-value set" and named the first two
alone through the whole of Phase 2O, while the module enforced five; the last of the three
2O kinds gained its writer in Task 9, and the sentence is corrected here rather than left
as a document a reader would have to disbelieve (§5.3).*

`candidates` carries the answers that were on the table, and its keys depend on the kind:
a `payload_binding` candidate holds `payload_type`, `hops`, `seen_in` and `why` (the
matched call); a `format_conflict` candidate holds `format`, `seen_in` and `why`; a
`channel_destination` candidate holds `channel` and `handler`; a `service_identity`
candidate holds `class` and `reason`; an `environment_divergence` candidate holds `key`
and `values`. Each array is sorted by the pass that writes it, so two runs produce the
same bytes.

`evidence` here is **deliberately not one of [D00](D00-fact-schema.md) §4's evidence
tiers.** It is the trail in prose — which columns and configuration keys were actually
read to reach the impasse. An unanswered question has no tier, and the reader of this
table needs to know where to look, not how much to trust an answer nobody gave.

**The table is replaced whole per resolve, and emptied once per resolve rather than by
either writer** — more than one pass contributes rows, so a reset owned by one would erase
the other's depending on which ran first, and a ledger merely shorter than it should be
reads exactly like a run with fewer questions. It is pre-declared empty for the same reason
`endpoints` and `shapes` are: the query answers with an empty result, never an error.

**Programmatic passes never read it.** It is a hand-off, not an input; a pass that read its
own unanswered questions back would be answering them.

**Ordering is total, because "ordered by wire identity" is not** (NFR-1): rows sort by
`protocol, method, path`, then `question` where one endpoint raises both kinds, then
`candidates` as text — two listeners on one destination share all four leading columns and
differ only in their answers — and finally `evidence`. Two rows agreeing on all six are the
same question asked twice and may appear in either order without changing a byte.

### Non-wire surfaces

| Table | Holds |
|---|---|
| `scheduled_work` | The scheduled method, the trigger kind, the declared expression |
| `error_handlers` | The handler, its container and scope, the exception, the status, the response shape |

**Two tables rather than two more `endpoints` rows, and that is the whole design**
(Phase 2O design §4). `endpoints` is wire-true: every row is a boundary something can
address, and its identity is `(protocol, direction, method, path)`. A method the framework
calls on a clock speaks no protocol and has no address; an exception handler is not a
boundary at all — it is what happens inside one that already exists. Giving either a wire
identity would invent a route nothing serves, which is the failure this schema exists to
prevent. So both families get their own table, with no protocol, direction, method or path
column between them.

**`scheduled_work`** carries `handler` (the method's own symbol), `trigger` (the framework's
own word for the schedule kind — `cron`, `fixedRate`, `fixedDelay`, catalog vocabulary
rather than one of [D00](D00-fact-schema.md) §4's closed sets), `expression` (the declared
schedule **verbatim** — a cron string normalised or a delay re-spelled names a different
schedule from the one that runs), `resolution`, `evidence` and `catalog_id`. `resolution`
is `unresolved` where the expression is a property placeholder this analysis did not
substitute, with the placeholder carried exactly as written; the value comes from
configuration a deployment overwrites, so substituting one would publish a schedule the
repository cannot know.

**`error_handlers`** carries `handler`, `advice` (the type that declares it), `declared_by`,
`scope`, `exception`, `status`, `response_shape`, `resolution`, `evidence` and `catalog_id`.
One row per `(handler, exception)` pair: each is separately answerable, and an array in one
cell joins against nothing. `declared_by` — the class-level annotation that made `advice` a
handler container — is load-bearing rather than provenance: an advice class declaring no
narrowing attributes applies to **every** controller in the application, while a
controller's own handler applies to **that** controller, and both carry a NULL `scope`. A
reader with only `scope` would read the second as the first and widen one controller's
error contract across the estate. `status` and `response_shape` are NULL where nothing
declared them, and NULL is an answer: a status computed inside a response-entity body is a
stated boundary, never a gap the column fills in.

**Both are replaced whole per resolve, and emptied once per resolve rather than by the
engine that writes them** — the `open_questions` rule, for the same reason: more than one
catalog may describe the same family (a second scheduler, a second framework's advice
mechanism), and a reset owned by the engine would run once per catalog and leave only
whichever ran last. Both are pre-declared empty like `endpoints` and `shapes`, so the query
answers with an empty result rather than an error on a module that schedules nothing.

**Neither feeds a root set.** [D00](D00-fact-schema.md) §4 documents a `root_kind` set whose
members include `scheduled`, and §5 below documents a `trace_of` walk. Neither exists in the
implementation, so a scheduled row is not a root today and nothing traverses from one.
**That becomes wrong the moment a `root_kind` producer ships**, at which point these rows
must be re-examined as roots rather than left as a table nobody walks.

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
