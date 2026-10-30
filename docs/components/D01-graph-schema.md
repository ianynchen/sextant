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

> **What ships is `call_edges`, the `calls` kind alone** (2Q's `G4`,
> `application/resolve/call_edges.py`). The single `edges` table above, its eight kinds and
> its `sites` column remain designed and unbuilt; a trace needs one of the eight, and
> building the other seven for a walk that does not read them would be seven derivations
> costing time on every run with no consumer (§6's own rule). The rest arrives when
> something asks for it.

**`type_hierarchy`** carries `child`, `ancestor`, `kind` (`extends`/`implements`),
`position` and `scanned`. One row per direct supertype, in JVMS 5.4.3.3's SEARCH order —
`position` 0 is the superclass, then each declared interface as the class file lists
them. `scanned` says whether this workspace read the ancestor's own class file, and it is
the column that separates a genuine third-party boundary from a body we simply did not
open.

**`method_resolution`** carries `class`, `name`, `descriptor`, `declaring_class` and
`reason` — one row per distinct triple an EFFECTIVE CALL SITE names, not per method
declared and not per triple the bytecode wrote: a compiler-emitted `$default` bridge is
re-targeted to the sibling it stands for before this is asked, so the triple here is the
one the author's call resolves through (spec 2026-09-22 §1a). The
reason is always present and comes from D00 §4's `method_resolution` set. Read
`declaring_class IS NULL` with the reason beside it: three different kinds of "no body
here" used to be one word, and one of the three was false.

> Both are computed in the pass that writes `call_edges`, from the same `Dispatch` —
> "which method can this site run" is answered once (§3's dispatch rule), and a second
> pass would be a second answer free to disagree. Neither is read by another table
> today; their consumer is the exported bundle, which is what lets a reader recompute a
> trace's terminals rather than take them on trust.

**`call_edges`** carries `caller`, `ordinal` (the call site's control-flow position, which
is what gives a walk its nesting), `invoke_kind`, `target`, `callee`, `result`,
`resolution`, `evidence`, and — since W30 — `terminal_kind` and `target_kind`. One row per
(call site, candidate callee); a site whose dispatch narrowed to several bodies is several
rows, none picked.

- **`terminal_kind`/`target_kind` are [D00](D00-fact-schema.md) §4's classification of what
  the call REACHES**, and both are NULL on a row that is not a terminal — an edge whose
  callee's body was read is expanded by the walk, so there is nothing to classify and
  `unresolved` there would say a terminal was examined and could not be named. A terminal
  no catalog claims reads `unresolved`, which on the measured corpora is most of them:
  `StringBuilder`, `Object`, `List`. See `resolve/terminals.py`.
- **`evidence` describes the EDGE, not those two columns.** The call site, the descriptors
  and the hierarchy are what the compiler wrote into the class files, and `compiler` says
  so. The classification beside them is read from catalog YAML ([D02](D02-catalog-schema.md)
  §2j) — every non-`unresolved` value in `terminal_kind` is a catalog's statement about a
  library type, never something a class file said. One column cannot carry two provenances,
  and the edge is the primary fact, so `evidence` stays the edge's and this is where the
  other half is written down.

- **`target` is bare and `callee` is module-prefixed, on purpose.** `target` is what the
  compiler wrote at that line — what a reader sees in the source — and `callee` is the
  symbol of the body it reaches, spelled so a walk joins it straight to that method's own
  rows and takes the next hop. Both spellings on one row is OI-4 answered rather than
  risked.
- **`callee IS NULL` is the third-party boundary, and it is the answer.** The workspace
  read no body, so the call IS the terminal. The row is still written, because "this call
  leaves the module here" and "this method makes no calls" are different answers and a
  table recording neither would report them identically. Measured on `macrozheng/mall`'s
  `mall-admin`: 1,966 of 2,608 rows.
- **A `dynamic` row's `target` is the body the site CREATES**, from
  `call_site.implementation` (capability 9.17) — never the bootstrap factory the site's own
  target names, which would make every lambda in every module a platform terminal.
  `invoke_kind` rides on the row so a reader is never told the body runs at that line: it
  is created there and runs later, elsewhere, if at all. A `dynamic` site that creates no
  body — string concatenation compiles to one — contributes no row at all.
- **It is not `return_flows` with more columns.** That table is the VALUE chain and exists
  only where a call produced one; this is the CONTROL chain, and a write, a publish or a
  delete is frequently the whole point of the work a trace is about. Which method a site
  can run is answered once, in `application/resolve/dispatch.py`, and both read it.
- **Not exported** ([D06](D06-bundle-format.md) §5's table list is unchanged), for
  `return_flows`' reason: the bundle is a published surface, and freezing this shape into
  one before anything outside the workspace reads it makes every later change breaking.

**`rpc_hops`** carries `caller`, `ordinal`, `protocol`, `path`, `handler` and `evidence`
(spec `2026-10-25-quarkus-mutiny-grpc-design.md` §3d, ruling 2): where a gRPC client stub's
call to an RPC this module serves lands. `call_edges` stops at the client-call API, a library
whose body no workspace reads, so a trace through `GreeterBlockingStub#sayHello` ended at
`ClientCalls#blockingUnaryCall` and never reached the module's own `HelloWorldService#sayHello`.
`caller` is a method of a class whose `type_hierarchy` reaches the catalog's
`client_stub_supertype` (library rows included); `ordinal` is its first call whose target
belongs to `client_call_owner`, where the call leaves for the wire, so `(caller, ordinal)`
joins the `call_edges` row; `path` is `<service identity>/<wire method>`, the wire method read
off the one accessor the stub method calls in the generated class's nest
(`getSayHelloMethod`, whose body names `SayHello`). Exactly one wire method and a client-call
site, or no row.

- **Only for a service the module serves** (§3c: an inbound `grpc` row with a handler). One
  row per handler of the path; a served service's RPC with no handler here gets one row with
  `handler` NULL, so the trace still carries the wire path when the outbound row is fenced.
  A call to a service the module does not serve keeps its outbound row and gets no hop.
- **`evidence` is `compiler`**, the endpoint rows' convention: a catalog's rule over
  compiled facts. `call_edges` is untouched; the hop lives in its own table, which is also
  what a curation names (ruling 4).
- **Exported**, `path` through the address map, as `roots.path` is ([D06](D06-bundle-format.md)
  §3). A derived table rather than a view, because the rule is Python
  (`resolve/rpc_hops.py`); replaced whole per resolve by that one writing pass.

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

**Neither table exists yet.** 2Q's `G3` needed the dispatch QUESTION answered — which
method a call can run — before either existed, so it applied the JVM's own rule directly,
without [M04](M04-resolver.md) §4's RTA narrowing. `G4` needed the identical answer for
`call_edges`, so the rule now lives in ONE place — `application/resolve/dispatch.py` — and
both derived tables read it. That is still a duplicate of the designed pass the day
`dispatch` ships, recorded as such (`docs/open-issues.md`, OI-16) rather than left for a
reader to discover from two tables that disagree; what it is not is a duplicate of itself.
The `edges` layer beside it is the `call_edges` note above.

### Return flows

2Q's `G3`. One table, and one sentence per row: **the value this call produced in the
caller is what that method hands back.**

| Table | Holds |
|---|---|
| `return_flows` | Call site (`caller`, `ordinal`), the caller's `result` value id, the `callee`, which of its returns (`return_ordinal`), what that return hands back (`value`, D00 §5's argument grammar), and the site's `resolution`/`evidence` |

**It is the only thing licensed to cross a method boundary.** [D00](D00-fact-schema.md) §5's
value ids are per-method and meaningless outside it, deliberately — a chain that crossed a
boundary by proximity would be a guess. This table crosses it by naming both sides, so a
`source` inside `value` is a value id in the CALLEE and joins to that callee's own
`call_sites`, never to the caller's.

**Derived, never a fact**, and it is a table rather than a view because the join is
arithmetic — the callee's descriptor is `owner` + `name` + the first four bytes of the
SHA-256 of the call target's descriptor ([D00](D00-fact-schema.md) §5a's `sig_`
disambiguator) — plus a bounded hierarchy walk. Neither belongs in SQL.

**Absence is the third-party boundary and is the common case.** A call whose callee this
workspace never scanned contributes no row: a mapper, a repository, a driver, anything in
the JDK — the call IS the terminal, and a row would claim a body nobody read. Measured on
`macrozheng/mall`'s `mall-admin`: 1,411 of 2,065 value-producing call sites.

**Not exported** ([D06](D06-bundle-format.md) §5's table list is unchanged). The bundle is a
published surface, and freezing this shape into one before `G4` reads it would make every
later change to it breaking. It moves into the bundle when something outside the workspace
needs it.

### Contracts

| Table | Holds |
|---|---|
| `shapes` | `shape_id`, content hash, whether open |
| `shape_fields` | Shape, ordinal, **wire name**, **field number**, wire type and format, required, nullable, trust fields, tags, item descriptor |
| `endpoints` | Direction, protocol, wire identity, handler and/or caller, peer, request and response payload descriptors, declared media types, **wire format and its resolution**, trust fields |
| `resolved_config` | Key, value, source, environment, or unresolved with a reason |
| `open_questions` | One question a programmatic pass refused to guess at: wire identity, question kind, the candidate answers, the trail that reached the impasse |
| `endpoint_conditions` | **A VIEW, not a table** (since `GRAPH_SCHEMA_VERSION` 4, spec `2026-10-22-conditional-beans-design.md`): the conditions an endpoint row carries, found by joining it to the bean its code lives in — [Conditional beans](#conditional-beans) below. Columns: PR #61's (`protocol`, `direction`, `method`, `path`, `handler`, `kind`, `expression`, `environment`, `holds`, `resolution`, `evidence`), then `caller`, `via`, `bean_kind`, `bean`. Rows of BOTH directions now (an outbound row's code is its `caller`); condition-less route rows (`kind` NULL) are left out. Structured for a machine; the architecture document is the one verbose rendering. The matcher never reads it — an endpoint is an endpoint — and a link states each end's conditions beside it. Whether the row EXISTS in an environment is `bean_presence`'s answer, never "every row here holds" |
| `endpoint_metadata` | One entry an outbound call carries beside its address and payload — a header, and in principle a key or an attribute — with the endpoint it belongs to, the caller, its kind, name and **redacted** value, and its own resolution and evidence; and, on an inbound row, **`requirement`** — what the framework enforces (`required`/`optional`/`absent`), NULL where the code states nothing; `caller` on an inbound row is the handler. Two routing alternatives that collapse to one address keep only the requirements they share — a demand one alternative makes and another does not is not one the framework enforces there |
| `channel_bindings` (temp) | One edge between an in-process CHANNEL and a method at one of its ends: `channel`, `role` (`fed_by`, `read_by`, `sends_to`), `symbol`, `protocol`, `direction`, `destination`, `catalog_id`, `resolution`. Working state of one resolve — replaced whole beside `endpoints`, never in a bundle — joined into `endpoints` rows by `resolve/channel_bindings.py` and read by `config_join.gaps` |

**`both` is reserved for the linking tier, and no pass here produces it** (F5 §6.1, W27).
A wire identity a module both exposes and calls stays TWO rows; the shape of a `both` row is
still defined — `handler` names the server method, `caller` names the client method, and both
are populated — because the tier that can justify the claim will write one. An outbound-only
row carries
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

**Serving and calling one identity is a QUESTION, and it used to be a merge.** The
fixture's `{http://orders.example.com/ws}placeOrderRequest` is derived twice — once from the
handler's own `@PayloadRoot`, once from the payload type the client hands to a template call
— and the two compose the same QName from two different annotations. They were merged into
one row on that basis, and the merged row carried `peer: ${soap.billing.uri}`: the module's
own served operation and a call to the BILLING service, published as one endpoint. They share
a QName because they share a payload TYPE, which is not identity.

The reason the merge could not tell is stated right here and is why it had to go: **`peer` is
not part of wire identity** (RC-5). So a path this module serves collided with the same path
anywhere in the world, and `POST /v1/orders` merged the module's own handler with a call to
`orders-loop`. Both rows now stand and `resolve/self_exchange.py` files a `self_exchange`
question naming each side and its address, because both readings are real: a service that
publishes to a topic and reads it back genuinely is one identity in both directions, and a
client calling another service's copy of a shared path genuinely is two. Curation or the
linking tier decides; a pass that decided here would be guessing at the far end of a call,
which is the one thing a module's own bytecode cannot show.

**`endpoint_metadata` carries the `caller`, and `endpoints` does not carry the metadata**
(F5 §6.2, W29). Two calls to one path with different headers are two calls, so the entry
names which one it came from — without that column the table would state one call's headers
about another's, which is the identity defect W27 removed from `endpoints` reintroduced one
table over. It is a side table rather than columns because the count is unbounded and each
entry needs its own trust pair: a header whose value could not be read is visibly
unresolved, and *sends a header we could not read* is a different claim from *sends no
header*.

**An entry names its endpoint twice: by the row's identity columns, and by `row_id`**
(spec 2026-10-30-object-identity, ruling 7). The identity columns are what a reader outside
the run joins on, which is why they are carried rather than replaced by a key: `row_id`
numbers a row for one resolve, names nothing outside it, and the export leaves it out. Inside
the run the id is what holds an entry to its row. It is bound when the entry is written, by
the row's identity as minted, before any pass has moved the row; the path prefix and a
protocol reclassification then move the row by its id, and the entry's identity columns are
copied from the row again (`follow_endpoint_rows.sql`). An entry whose row the self-call pass
removes is removed with it. Matched by address instead, an entry written as its row was
minted stayed at the address the prefix had just moved the row away from.

**The same table holds what an inbound endpoint's framework DEMANDS of a request** (spec
2026-09-19 §5a). An inbound row's entries are the headers, query parameters and cookies the
framework's binder or routing tree enforces — `direction = inbound`, `caller` the handler
symbol, `kind ∈ {header, query, cookie, param}` (`param` only for the two APIs that cannot
tell query from form) — and **`requirement`** states what is enforced: `required` (the
framework rejects a request without it), `optional` (it serves one without it), `absent`
(it requires it to be missing). The column states what the FRAMEWORK enforces, never what
the handler body does with the value. An inbound row's `value` is the framework's OWN
spelling of the demanded value, or NULL: a literal for Ktor's `header(name, value)` and
Spring's `params = "view=summary"`, and the regex AS WRITTEN for Spring Cloud Gateway's
`header("X-Request-Id", "\\d+")`, which the framework matches as a whole-string regex
(`Pattern.asMatchPredicate` for `header`, `String.matches` for `query`/`cookie` —
spring-cloud-gateway-server-webflux 5.0.0, CP-26 row 6) — so a consumer compares two
values for equality only where the spelling is a literal
([M06](M06-stitcher.md)). NULL on an inbound row means the code states nothing
— a bare read in a handler body says only that the handler reads the value — and NULL on
every outbound row is the existing meaning: an entry sent has no requirement. The insert is
insert-if-absent on the full row, because two catalogs can describe one handler and their
identical entries are one entry. Written after `apply_protocol_hints`, for the reason every
pass below that line gives: an entry names its row by the row's identity columns, and
`protocol` is final only there.

**`channel_bindings` is the channel EDGE as data** (spec 2026-09-21 §3b). A Spring
Integration channel is an in-process pipe with no wire identity of its own; what has a wire is
the adapter or flow that FEEDS it, and what has a handler is the annotated method that READS
it, and the two are declared in different methods by different frameworks' words. So neither
side writes an `endpoints` row alone. The fluent engine, walking a registration or a DSL flow,
writes a `fed_by` row — `channel` the name it captured (a literal, or a channel bean's name
through the bean fold), `symbol` the constructing method, `protocol` its catalog's,
`direction` the row's, `destination` the wire it captured; `config_join`, indexing the
channel each annotation names, writes a `read_by` row — `symbol` the handler, `direction` the
one the annotation means, `protocol` and `destination` NULL because a reader knows nothing
about the wire; and a `channel_link` a flow captures AFTER its handler is that handler's
OUTPUT channel, a `sends_to` row (no reader yet, `OI-107`). Once per resolve, after the
engine loop, `resolve/channel_bindings.py` joins inbound `fed_by` to resolved inbound
`read_by` on `channel` and mints one inbound `endpoints` row per pair — `path` and `protocol`
the feeder's, `handler` the reader, `caller` the feeder's method — one per reader however
many catalogs wrote it, and one with `handler` NULL for a feeder nobody reads; a reader
nobody feeds keeps its `channel_destination` question, and `config_join.gaps` asks only for
those. **`resolution` is role-dependent**: on `fed_by` it is the WIRE's — the edge stands in
for the row the chain would have written, so an unread destination is an `unresolved` edge
and mints an `unresolved` row; on `read_by` it is the NAME's — a channel spelled as a
configuration placeholder is resolved through `resolved_config` before it is written, and
one no environment answers stays as written, `unresolved`, and joins nothing. A TEMP table
for `route_requirements`' reason: it lives for the one resolve that reads it, is replaced by
the next, and never reaches the workspace file or an export bundle
(`DuckDbWorkspace.schema_objects` leaves it out by name).

**Its `value` is redacted at the ORIGIN, alone among value columns.** Every other one is
masked at export, because analysis reads it — substituting `REDACTED` into an address would
publish a fabricated peer. Nothing reads a metadata value, so the masked string is the only
one ever written down and there is no export query to add. The rows are a SET: two values
under one name are two rows and their written order is not preserved.

**`endpoints.catalog_id` is provenance, not identity.** It names the catalog whose rules
produced the row, so a catalog describing an endpoint's request/response contract can
scope itself to exactly the rows its own derivation wrote rather than reasoning about
direction, protocol or row-level overrides. It plays no part in endpoint identity — the
hash below never includes it, and a refactor of the catalog files themselves must not
orphan an endpoint — and it is never compared across services: it is a local fact about
which catalog derived this graph's own row, not a cross-service correlation key.

**Each side keeps its own request and response payload descriptors** (W27). Where the module
both exposes a path and calls it through a client with its own declared contract, the two
declarations can differ — and both are now recorded, one per row, because there is no merge
to discard either. The gap this closes was named
`merged_endpoints_keep_only_the_handlers_contract`.

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

**What "failed to resolve" means for a BODY capture narrowed with `OI-77`.** The rule above
turned on a payload column that stayed NULL either way, which made the row the only place a
read failure could be recorded. A body or response capture reading a bare `parameter` now
resolves to the type the caller's own signature declares, so it fills that column and no
longer drops the row — `_capture_resolved` asks what a capture PRODUCED, not what kind it
read. A capture that produced nothing still drops the row **where its argument is one of the
kinds that names no value** — an `unresolved`, a `field`, a `concat`, or a `parameter` whose
declared type roots to no payload at all. A `class` or `instance` argument that roots to no
payload has never dropped a row and still does not, which is a residue of the older rule
rather than something this change introduced. An ADDRESS capture is unchanged: a destination is its VALUE, and the value lives in
whatever called the method. So the consequence stated above holds — an `unresolved` row's
NULL column is still not a claim of no payload — while the converse is now also true: a row
carrying a payload no longer calls itself unresolved on account of it.

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
finding, which per-handler identity would have hidden. **Built in W28** (F5 §6.1) as the
`routing_conflict` question, and only where the deriving catalog says the framework refuses
it: two handlers on one address is ordinary wherever the framework dispatches on something
else, such as `@KafkaHandler` on payload type. Environment expressions hash as
expressions: `${orders.topic}` is the same endpoint in every environment.

**Direction is not a hash input.** An earlier draft hashed *(module, protocol, direction,
wire identity)*, and the reason it must not is that direction was mutable: D02 §3's
inbound/outbound merge could turn a path a module only exposed into a `both` row when it
gained a client, without its wire contract changing at all. *That merge is gone (W27), so
the mutation no longer happens here — but the argument stands on its own and direction stays
out: the linking tier writes `both`, and an identity that changed when a peer was discovered
would orphan every curation about it.* Mutable state does not belong in identity, by the same argument
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
| RSocket route | `rsocket` | NULL | the route the handler answers (`/orders/place`), or the class-level prefix alone for a `@ConnectMapping` naming none | the Spring RSocket catalog (F2 §3.6). Verbless for STOMP's reason: an RSocket route declares no verb. It shares `@MessageMapping` with STOMP and is told apart by the build, or by a `@ConnectMapping` anywhere in the module |
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

### Conditional beans

A bean whose registration Spring decides per environment — a class carrying `@Profile` or an
`@ConditionalOn…`, a `@Bean` method carrying one, a `@Bean` method inside a conditional
configuration class — has its conditions stated ONCE, on the bean, and everything derived
from it finds them by a join (spec `2026-10-22-conditional-beans-design.md`, decision 3: the
key is the bean). Nothing here ever decides whether a row exists: the conditions are data
the documents state, and no row, link or call edge is dropped or added for one.

| Object | Kind | Holds |
|---|---|---|
| `bean_conditions` | table, exported | One row per (bean, registration route, condition, environment the module resolves), written for a class with at least one conditional route, and replaced whole per resolve |
| `bean_presence` | view, exported | Where each bean exists, per environment: `(bean, environment, holds, resolution, evidence)` |
| `symbol_beans` | view, exported | `(symbol, bean)` — the ONE rule mapping code to its bean |
| `candidate_presence` | view, exported | Which candidates of a call site exist in each environment |
| `interface_beans` | table, exported | Every interface the framework registers and implements at run time, one row per type it is assignable to |
| `endpoint_conditions` | view, exported | The contracts table above |

**`bean_conditions` columns.** `bean`, the class whose code runs, spelled as `symbols.symbol`
spells a type (the spelling `symbols.enclosing` uses); `bean_kind`; `via`; `kind`;
`expression`; `environment`; `holds`; `resolution`; `evidence`.

* **`bean_kind`** is the registration route the row belongs to. `class` — a scanned class
  (a stereotype, direct or composed). `factory` — the `@Bean` method that constructs and
  returns the class; and the method itself, and any lambda body it creates, as beans of
  their own on the factory's route (a row whose code is the method's own body — an inline
  adapter flow it builds and returns — exists only where the factory registers). `configuration` — the enclosing configuration class's condition, applied to a
  `@Bean` method's bean. `constructed` — a plain `new` outside any bean factory: one
  condition-less row per environment, `unresolved`, evidence naming the constructing method.
  `proxy` — an interface the framework implements at run time (Spring Data repositories); the
  bean is the interface. A body declared in an abstract class or as an interface default
  method is written as a bean of its own whose rows are COPIES of the rows of the beans that
  run it (its heirs), each keeping the heir's `bean_kind` and `via` — the heir class standing
  in for a `via` the heir's row does not have, so two heirs stay two routes. `inherited`
  appears only on the rows of a body NO bean runs: one condition-less `unresolved` row per
  environment, evidence "no bean of this module runs this inherited body".
* **`via`** is the factory method for `factory` and `configuration` and the constructing
  method for `constructed`; NULL for `class`, `proxy` and `inherited` — except on a copied
  heir row of an inherited body, where it is the heir's own `via` or, for a heir with none,
  the heir class, so such a `class` or `proxy` row carries a non-NULL `via`. It tells two
  routes of one bean apart: two mutually exclusive factories are two routes.
* **`kind`** is `profile`, `property`, `presence` or `other`; NULL on a condition-less route
  row (an unconditional scan or factory of a class that also has a conditional route, `true`
  in every environment, `resolved`). `profile` and `property` hold or fail by the framework's
  own rule (CP-42, CP-43), against the environment's active profiles (CP-45, see below) and
  its resolved configuration. `presence` is `@ConditionalOnMissingBean` /
  `@ConditionalOnBean`, judged from the module's own beans, always `resolution = partial` when
  decided, the reason and the competitors in `evidence`. `other` is any condition this
  analysis names and does not evaluate, verbatim, `unresolved`.
* **`expression`** is JSON typed per `kind`: `{"expressions": […]}` for a profile;
  `{"keys": […], "having_value", "match_if_missing"}` for a property; `{"annotation", "mode":
  "missing"|"present", "types": […], "names": […], "annotations": […]}` for a presence
  condition; `{"annotation", "args"}` for `other`.
* **`evidence`** is `compiler` where the framework's rule decided. On a profile row, where the
  verdict is `unresolved`, it is the reason (an activation the deployment decides; "the
  active profiles here come from `${apollo_profile}`, which this module does not fill"). On a
  `presence` row it is the stated reason, then `; competitors: ` and a sorted JSON list of
  `{bean, via, holds}` (and a `note` where a competitor's conditions name a profile no
  environment of the module is).

**`bean_presence`** folds the rows by bean, route (`via`) and environment: a route holds
where every condition of it holds, fails where any fails, and is `unresolved` otherwise; the
bean then holds where ANY route holds (OR across routes, AND within one — each scan, import
or `@Bean` registers its own definition), fails where every route fails, and is `unresolved`
otherwise. `resolution` is the weakest of what decides the outcome (`unresolved`, then
`partial`, then `resolved`); `evidence` is `compiler` when decided, otherwise the reasons that
left a route open or the `partial` rows' reason. A bean with no row here is unconditional.

**`symbol_beans`** answers "which conditional bean does this code belong to": the symbol itself
where the pass wrote rows for it (a factory lambda, an inherited body), otherwise its owner
class. Only symbols whose bean has rows in `bean_conditions` appear; a symbol absent from the
view belongs to no conditional bean. It is built as two equi-joins (GUIDELINES §8.7).

**`candidate_presence`** `(caller, ordinal, callee, bean, environment, holds, resolution,
evidence)` states, per call site and per environment, which candidates exist. A site is listed
where a NARROWED candidate's bean is conditional, or where a framework-generated
implementation answers it (an `interface` call naming a type some `interface_beans` row is
assignable to), whatever its resolution; then every candidate of it is listed. A body of a
conditional bean carries its `bean_presence` verdict; a body with none carries `bean` NULL and
`true`, `resolved` in every environment; a framework-generated implementation has `callee`
NULL and `bean` the interface. `call_edges` and its `resolution` values are untouched — no
candidate is dropped.

**`interface_beans`** `(bean, type)` is written beside `bean_conditions` and replaced whole
with it, for every such interface, conditional or not, because an unconditional repository is
a candidate too and `bean_conditions` holds only classes with a conditional route.

**Environments, and active profiles.** The environments are the module's profile FILES, as
`resolved_config` has them (`default` where there are none). A profile condition holds against
the environment's ACTIVE profiles (CP-45): in `default`, the literal profiles of the base's
`spring.profiles.active` and `.include` (else `.default`'s, else `default`); in a profile-file
environment `p`, `p` plus the base's `.include`; a profile named only in the base's `active`
list is `unresolved` there, and a placeholder nothing fills in either key leaves every profile
condition not decided by the environment's own name `unresolved`. A profile the base's
`active` list never names is `false` in a profile-file environment. A profile group
(`spring.profiles.group.<name>`) makes its members active wherever `<name>` is, transitively,
each member as certain as the profile activating it.

**Exported.** All six travel in the bundle, by the export
ratchet ([D06](D06-bundle-format.md), "Nothing is dropped on export"). `symbol_beans` and
`interface_beans` hold symbols only. The other four are masked on export: the outbound rows
of `endpoint_conditions` carry the endpoint's `path`, which can hold an address with URL
userinfo, so it masks through the address map `endpoints.path` uses (`_REDACTED_ADDRESSES`);
`expression` quotes a condition's annotation arguments verbatim and passes through
`redact_json`, as `annotations.args` does; `evidence`, free text repeating an expression or a
placeholder's raw spelling, passes through `redact_text`.

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

**Built by 2Q's `G4`/`I3`** — `application/query/trace.py`, over `call_edges`, `roots`,
`return_flows` and `rpc_hops`. Module scope only; the federation half is `Bundle`/`Link`
work and unbuilt.

**It takes a ROOT, not an endpoint** (`I3`, ruled by the user): a scheduled job contains
business logic and gets the same trace a request does, so the walk reads `Root.kind` for
exactly one purpose — carrying it back on the answer — and branches on it nowhere. That is
what makes `entry_point` free on the day it gains a producer.

**Each step says why it was not expanded**, from a four-member closed set
(`domain/closed_sets.TraceStop`; a step with no reason was expanded, and an expanded step
with no children is a method that calls nothing):

| Stop | Means |
|---|---|
| `boundary` | The workspace read no body for the callee — the ruled third-party boundary, where a trace stops |
| `cycle` | The callee is already on the path from the root. Recursion is real code: it is stated, not followed |
| `revisited` | The callee was expanded elsewhere in this trace; its subtree is shown at its first occurrence |

**A gRPC call to this module's own service is a hop, not a stop** (spec
`2026-10-25-quarkus-mutiny-grpc-design.md` §3d, ruling 2). At a `call_edges` row whose
`(caller, ordinal)` has `rpc_hops` rows, the walk takes one step per hop instead of the
`boundary` step: the row's `target`, `invoke_kind` and `resolution`, `callee` the hop's
`handler`, and `via` the wire path (`grpc helloworld.Greeter/SayHello`). The handler is then
any callee, so it is expanded, `revisited` or a `cycle` by the table above, and a hop whose
`handler` is NULL is still `boundary`, carrying its wire path. The step leaves
`Trace.terminals`, so a trace through a stub has one terminal fewer. The document's arrow ends
at the handler's lifeline, labelled `blockingUnaryCall (declared ClientCalls) via grpc
helloworld.Greeter/SayHello`, and the step table's `Reaches` reads `via` and the wire path.

**This is deliberately not [D00](D00-fact-schema.md) §4's `terminal_kind`.** That set
CLASSIFIES what a call reaches — `persistence`, `async_handoff`, an `outbound_call` in the
sense of a matched outbound endpoint — and three of its members need framework knowledge no
pass could apply at a call site on its own: a data-access call is `persistence` only to
something that knows the callee is one. W30 supplied that knowledge as catalog data (D02
§2j), so `terminal_kind` HAS a producer now and this paragraph's older claim that it never
would is struck. The two still answer different questions on one row: `TraceStop` says why
the WALK stopped, decided entirely from what the walk did, and `terminal_kind` says what
the CALLEE is, decided entirely from what a catalog declares. A JDK call and a MyBatis
mapper call both stop the walk at `boundary`; only one of them is `persistence`.

**Reachability, never execution**, and the walk is weaker than it looks in three specific
ways a reader must be told: branches are not distinguished (two `return` statements are two
possible answers, an `if` contributes both sides); a `narrowed` step walks every candidate
and picks none; and a `dynamic` step names a body created at that line rather than called
at it.

**Finite without a bound, and it was bounded twice until W31** (F7 §8.1). A method is
expanded at most once per trace, which makes the walk finite on its own; the one shape that
did not cover — a long chain of distinct methods — used to be handled by a depth bound of
64, which also kept the recursion off the interpreter's stack. The walk is an explicit
stack now, so neither job is left: it terminates where the evidence does, which is what
FR-6 asks for. Measured before the bound went, the deepest trace is **9 edges** across
`mall-admin` (160 traces), `spring-petclinic-rest` (37) and `jhipster-sample-app` (38) —
it was inert on every repository available.

**Cross-module depth reads as `boundary` and is incompletely so.** A call into a sibling
build module leaves for a workspace this one does not hold, so no body was read here —
correct — while a body exists somewhere. Joining the two is `Bundle`/`Link` work, not this
walk's; `docs/COVERAGE.md` §7 carries the measurement.

One table is DESIGNED and materialised, and it is not built:

| Table | Holds | State |
|---|---|---|
| `trace_summary` | Per inbound endpoint: hop counts, services involved, terminal counts by kind, endpoints reached more than once | **designed, never built** — `grep -n trace_summary src/sextant/storage/duckdb/schema.sql` returns nothing |

> **Amendment (2026-09-10, W52 review).** This read *"One table is materialised, because a
> consumer computing the refactor or performance-risk scenario needs its numbers without
> walking everything"* — present tense for a table that has never existed, and justified by
> two scenarios that [REQUIREMENTS.md](../REQUIREMENTS.md#usage-scenarios) has since ruled
> are a consumer's to derive rather than requirements of Sextant (they were FR-11 and FR-14).
> The design stands: if those numbers are ever wanted without a walk, this is their shape.
> What is corrected is the tense. `G-70` recorded the same defect against D06 — whose §3
> example manifest once listed `trace_summary` among `contents.tables`, and therefore described
> a bundle that could not be produced. **That half is already fixed**: commit `a184a0d`
> (2026-09-07) removed it, and §3's manifest now lists eighteen tables that all exist. D06 §4's
> cross-service row still names `trace_summary` among the inputs `trace_of` walks over, which
> is a statement about a DESIGNED input and reads correctly beside this one.

A trace is a subgraph with ordering and nesting, not a list of routes. Its size grows with
the code reached, not with the branching — which is why it needs no depth bound. If full
walks ever prove slow at render time, the fix is caching the walk result per run — lazy
materialisation where measurement demands it, not presumed everywhere.

### System scope — two native tables, everything else federated

| Table | Holds | Stored |
|---|---|---|
| `participants` | Service or external, name, aliases, **bundle location**, commit | Natively |
| `links` | Outbound endpoint, inbound endpoint, trust fields, candidates | Natively |
| `symbols`, `edges`, `endpoints`, `shapes`, `shape_fields`, `traces`, `endpoint_conditions`, `bean_presence` | Each participant's own graph — `endpoint_conditions` as `system_endpoint_conditions` and `bean_presence` as `system_bean_presence`, the conditions each end of a link carries and where its bean exists, which a link states beside itself (spec `2026-10-21-conditional-controllers-design.md`, ruling 2; `2026-10-22-conditional-beans-design.md`) | **Views over the bundles** |

The system workspace does **not** copy the estate's graphs. Bundles are Parquet, and one
query reads Parquet across many paths, so a view is enough.

**Amendment 2026-10-19 (user decision 1, spec `2026-10-19-reactor-linking-design.md`): where
the participant set is a REACTOR, the views read each module's own WORKSPACE instead of a
bundle.** The half of this rule that matters is untouched — the system workspace still copies
nothing, holds the same two native tables, and reads every participant's graph through a
view. What is given up is the anti-drift half: a workspace is not the bundle, so it cannot
claim "it IS the bundle".

**That trade is sound for one build and for nothing larger.** A reactor's module workspaces
all come from the same run of the same build, so there is no second artefact for one to drift
from; requiring bundles there would add a `module export` per module for a guarantee the
single build already provides. As soon as participants come from separate runs of separate
repositories — [M05](M05-sync.md)'s actual subject — the bundle rule is the right one and
this exception must not be carried across. The obligation below holds either way: the
location is recorded in `participants`, and one unreachable at query time fails naming it.

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
| ~~`findings`~~ | **Never built, and no longer planned as a table Sextant writes** (W51). Kind, subject, severity, evidence sites — for FR-11 … FR-14, which are usage scenarios rather than requirements: Sextant publishes the rows a consumer derives them from, and the judgement is the consumer's |
| `open_questions` | The endpoint's wire identity, the question kind, the candidate answers, the evidence trail |

`open_questions` is not an error log. It is output: a recorded disagreement a person should
settle.

**As built it is the hand-off ledger for the enrichment tier** — one row per question a
programmatic pass could not answer and refused to guess at. Columns: `protocol`, `method`,
`path` (the wire identity, **carried rather than joined** — the row is an artifact a human
and the enrichment tier read, and a foreign key into a table rebuilt every resolve would
name nothing outside this run); `question`; `candidates`, a JSON array; and `evidence`.

`question` is a **closed THIRTEEN-value set — `payload_binding`, `format_conflict`,
`channel_destination`, `service_identity`, `environment_divergence`, `binder_protocol`,
`unselected_binding`, `handler_protocol`, `registration_activation`, `self_exchange`,
`routing_conflict`, `routing_depth` and `web_stack`** — checked by the single owning module before any row is inserted,
because the value is bound straight into a published artifact where a typo is
indistinguishable from a kind of question nobody implemented. Adding a kind is a schema
change (NFR-5): the RENDERER switches on it, and the export carries the rows through
unread. *This sentence said "both the renderer and the export" until F2 §3.4 added the
last two; `open_questions.py`'s own comment had already corrected that and this paragraph
had not caught up.* *It then said SEVEN while the module enforced eight, F2 §3.6 having
added `handler_protocol` without touching this file — the third time this count has drifted,
which is why §3.6's review made the drift itself the finding rather than the number.*
*`registration_activation` (`OI-64`) is the ninth, and it was added to this sentence in the
same change that added it to the module — the drift above is why that is now the habit
rather than an afterthought.* *And then it said NINE while the module enforced twelve:
`self_exchange` (F5 §6.1, W27) and `routing_conflict` (W28) were added to the module without
this sentence, and `routing_depth` (spec 2026-09-19 §4a) is the twelfth — corrected 2026-09-20
in the change that closed that spec's register items, the fourth drift of this one count.*
*`web_stack` (ruling 3 of the 2026-10-30 object-identity design) is the thirteenth, added
here in the same change as the module.* *This paragraph said "two-value set" and named the first two
alone through the whole of Phase 2O, while the module enforced five; the last of the three
2O kinds gained its writer in Task 9, and the sentence is corrected here rather than left
as a document a reader would have to disbelieve (§5.3).*

`candidates` carries the answers that were on the table, and its keys depend on the kind:
a `payload_binding` candidate holds `payload_type`, `hops`, `seen_in` and `why` (the
matched call); a `format_conflict` candidate holds `format`, `seen_in` and `why`; a
`channel_destination` candidate holds `channel` and `handler`; a `service_identity`
candidate holds `class` and `reason`; an `environment_divergence` candidate holds `key`
and `values`; a `registration_activation` candidate holds `registration`, `enclosing` and `activated_by`
— the construction call, the method that returns it without starting it, and the chain
the framework requires before anything is delivered; a `handler_protocol` candidate holds `class`, `annotation` and `protocol` —
the wire ONE framework would publish that class on, one candidate per framework in play,
because the question is which of them serves it; a `routing_depth` candidate holds `callee`,
`caller` and `depth` — the first helper the combinator's walk did not follow, the routing
entry's own caller (where a reader opens the file) and the bound that stopped it — and ONE
row per run carries every such chain, its `method` and `path` NULL because both genuinely are
unread (spec 2026-09-19 §4a); a `web_stack` candidate holds `stack` and `keys` — one stack the
module might run on and the configured prefix keys that stack's server-model entries would
have applied — on ONE row per protocol, `method` and `path` NULL because the question is the
module's, filed where a module configures a prefix, has rows a dispatcher serves, and carries
none of the server model's `stacks` coordinates (D02 §1h). Each array is sorted by the pass that writes it, so two runs produce the
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
| `resolved_schedules` | A scheduled job whose expression holds a placeholder — its handler, trigger and expression — with its value per environment, or unresolved with a reason |
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
rather than one of [D00](D00-fact-schema.md) §4's closed sets), `name` (the trigger's own
name where the framework gives one, part of the identity beside `handler` and `trigger`;
EMPTY for `@Scheduled`, which gives none), `expression` (the declared
schedule **verbatim** — a cron string normalised or a delay re-spelled names a different
schedule from the one that runs), `expression_source` (the bare descriptor ([D00](D00-fact-schema.md) §5a) of the method or
field the walk to the expression stopped at — bare because a method in a jar has no module
coordinates; set only when `expression` is NULL),
`resolution`, `evidence`, `catalog_id` and `untied` (the parts — `handler`, `name`,
`expression`, in that order — that are NULL because the paths reaching the trigger disagree
on them, not because the code states none; NULL where no part is). `handler`, `trigger`,
`name`, `expression` and `expression_source` are nullable. **Each empty cell says why it is
empty** (ruled 2026-10-29): a NULL the row's `untied` names is a value the code states and
no one path ties to this row, printed `not tied down`; any other NULL is a fact the code
does not state, printed `not in the code`; an EMPTY name is a part the framework does not
have, printed `—`. A row with no `handler` is not a root.
`resolution` is `resolved`, `unresolved`, `partial` (part of the schedule is read, part is
not; a `partial` row with no expression is rendered with `the schedule is read at runtime
from <expression_source>`, or `the schedule differs between the calls that reach
<expression_source>` where the expression is untied) or `narrowed` (one of several candidates). It is `unresolved` where the expression is a property placeholder this analysis did not
substitute, with the placeholder carried exactly as written; the value comes from
configuration a deployment overwrites, so substituting one would publish a schedule the
repository cannot know.

**`resolved_schedules`** is what the repository's own configuration says instead, beside
the job rather than in it (spec 2026-10-23-configured-schedules, option A): one row per
(`scheduled_work` row whose expression holds the config model's placeholder opener,
environment of `resolved_config`), carrying `handler`, `trigger`, `name`, `expression`,
`environment`, `keys`, `value` and `unresolved_reason` — the last one of the closed set
`resolved_config` uses, `value` NULL exactly when it is set. `keys` is a JSON array of every
key the substitution asked that environment's configuration for, in the order it asked: a
schedule is the value of the key that configures it, so every exit masks `value` whole where
one of them names a secret, as `resolved_config` masks that key's own value. The first four are the job's
`scheduled_work` columns verbatim and together are its identity: a method with two
schedules of one kind (`@Schedules`) is two jobs sharing the others, and only
`expression` attributes a value to its own. The expression is substituted by the same placeholder rule
`resolved_config` itself is (`:default` included, relaxed or exact matching as the model
says), looked up in that one environment's resolved rows. A literal or a SpEL `#{…}`
expression gets no rows, and with no resolved environment the table is empty. A derived
table rather than a view, because that rule is Python; replaced whole per resolve by its
one writing pass.

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

**`scheduled_work` now feeds the root set, and `error_handlers` deliberately does not.**
That paragraph read "neither feeds a root set" until 2Q's `I1` shipped the `root_kind`
producer this section named as the condition that would make it wrong — so a scheduled row
IS a root now, and `roots` below carries one per scheduled handler. An error handler is
not: it runs INSIDE work something else already started, so a trace beginning at one would
report an exception path as though a request or a clock had begun it.

### Roots

2Q's `I1`, and the thing that made a scheduled method first-class rather than a row in a
table nobody walked.

| Table | Holds |
|---|---|
| `roots` | One row per (`handler`, `root_kind`, wire address): the method a trace starts at, what starts it, and the address that reaches it |

**Written by `application/resolve/roots.py`** from two tables the catalog-driven half has
already finished with: every `endpoints` row the module EXPOSES and names a handler for
(`direction <> outbound`, the `resolved_peers` test rather than `= inbound`, so a `both`
row from the linking tier would keep its trace — no pass here writes one since W27), and
every `scheduled_work` row's handler.
[D00](D00-fact-schema.md) §4's third member, `entry_point`, has no producer — which
signature starts a program is a LANGUAGE rule and [ARCHITECTURE](../ARCHITECTURE.md) §10
keeps those out of the resolver, so its producer is a catalog nobody has written
(`docs/open-issues.md`, OI-22).

**One ROOT per handler and kind; one ROW per address that reaches it.** A method serving
three paths is ONE root: the walk that runs from it is the same walk whichever address
invoked it, and three traces would be three copies of one answer — `roots_of` collapses the
rows into one `Root` carrying all of them, and the traversal never sees more than one. A
method that is both exposed and scheduled is two roots, because those are two different
answers to "what starts this". On the orders-service fixture, 77 handler-bearing endpoint
rows are 77 root rows and 66 roots.

**The row grain moved from (handler, kind) to (handler, kind, address) at 2Q's close, and
the reason is a reader.** A trace named by a handler descriptor and a kind puts
`GET /order/list` nowhere in the rendered document: the section is searchable only by the
one thing a reader looking up a URL does not have. The join back to `endpoints` is the
answer, and it cannot be made in `egress` — a renderer that joins is deriving, which the
"Egress is read-only" contract exists to forbid — so it is made here, once, by the pass
that already reads both tables.

**A root nothing addresses carries three NULLs, and that is an answer.** A scheduled job is
started by a clock. `roots_of` reads such a row as an EMPTY identity set rather than as an
address whose every half went unread, and the renderer prints `no wire address` rather than
the em dash it uses for "nothing recorded". The third shape — an exposed address whose
handler no chain reader named — has no root at all and is `docs/open-issues.md` OI-23,
unchanged by any of this.

**It carries the WIRE columns and not the trust ones, and the distinction is not
arbitrary.** `protocol`/`method`/`path` are this row's own identity — which address starts
this walk — while `resolution` and `evidence` are judgements about a different row, and
every one of them already lives on the `endpoints` row with nothing keeping two copies
equal (§6's "no fact that was merely copied"). The addresses cannot drift from their source
for a structural reason rather than a hopeful one: one pass writes them, from one read of
`endpoints`, replacing the table whole — and that pass runs BELOW `apply_protocol_hints`,
because a copy taken above the reclassification is a copy taken mid-write
(`roots.the-address-is-the-one-the-endpoint-row-ends-with`, measured on the fixture's two
SSE routes).

**Not exported** ([D06](D06-bundle-format.md) §5's table list is unchanged), for
`return_flows`' reason: the bundle is a published surface, and a root is trivially
recomputable from two tables that ARE exported, so freezing this shape into one buys a
consumer nothing it could not derive.

**Why a table and not an argument to the walk.** A traversal that took an endpoint handler
would have to be reopened the first time something else started work, and every question
the walk asks — which method, how deep, where it stops — is identical for a request and for
a clock. So the walk takes a row from here and branches on the kind nowhere at all, which
is also what makes the third kind free the day it gains a producer.

### Value resolutions — a review list, and the only table nothing derives from

Spec [2026-09-22](../superpowers/specs/2026-09-22-value-resolution-design.md) §3d and §7a.

| Table | Holds |
|---|---|
| `value_resolutions` | One row per (catalog, position, path): what the backward value walk WOULD resolve at a position a catalog asked about, or the §1d reason it could not |

**Written by `application/resolve/shadow.py`, and only when the analysis asked for it**
(`sextant module analyze --shadow`). Every other analysis empties the table and leaves it
empty — rows describing a walk this run did not perform would be a review list about
another workspace.

**Its whole purpose is that nothing reads it.** This project's standing rule is *misses are
acceptable, fabrications are not*, and the value-resolution work inverts the usual risk: it
converts misses into ANSWERS, so every conversion is a new assertion, across fourteen
shipped catalogs at once. A before/after diff of `endpoints` catches MOVEMENT and not
WRONGNESS — a wrong address looks exactly like a right one in a diff — so the walk runs in
shadow first, writes its candidate conversions here, and publishes none of them. Each
engine is then migrated with its diff already read.

**Bounded by what catalogs ASK, never by the facts**, which is what makes it a list a person
can read rather than a second copy of the argument grammar. How narrow that bound is —
positions asked, against the ceiling of every argument and receiver of every call site — was
measured across twenty-seven corpora including the 48 MB one, and is reported in
[the value-walk measurement](../research/2026-09-23-value-walk-measurement.md) §2. It is
cited here rather than restated: that figure has moved once already, and the copies of it
did not move with it.

**`value` masks by the ADDRESS map on export**, not by the argument-grammar one: a
`would_resolve` row carries the string an engine WOULD publish as `endpoints.path`, so it is
the same value one table along, and a bundle that masked the two by different rules would
spell one address two ways.

### The boundary vocabulary — seven kinds, and which columns identify an entry

Spec [2026-10-22](../superpowers/specs/2026-10-22-boundary-vocabulary-and-diff-design.md) §2
(FR-21), built in `application/boundary/vocabulary.py`.

The tables above say what Sextant derives. This is the closed, versioned list of the WORDS a
diff and an observability map use for it: seven kinds, in this order, each naming the table
its rows come from, the columns that IDENTIFY an entry (two analyses' entries with equal
identity are the same entry), the columns that are its ATTRIBUTES (what a `changed` entry's
`from` and `to` range over) and the columns that are EVIDENCE (carried on every entry,
compared by nothing).

| Kind | Derived from | Identity | Attributes | Evidence |
|---|---|---|---|---|
| `module` | `metadata.json`'s `module` | the module id | kind, languages, `dependency_source` | none |
| `endpoint` | `endpoints`, inbound | protocol, method, path: the exposed address, which is a topic for a broker, the operation name for GraphQL, the operation's QName for SOAP | the request and response body as field sets by wire name, the same two bodies as descriptors with every type symbol erased, consumes, produces, format, the requirement set (`endpoint_metadata`), the condition set (`endpoint_conditions`), resolution | handler symbols, documents |
| `dependency` | `endpoints`, outbound | protocol, method, path, peer | the two bodies as for `endpoint`, format, the header set (`endpoint_metadata`), the condition set (`endpoint_conditions`, through the caller's bean), resolution | caller symbols, documents |
| `data-contract` | `shapes` and `shape_fields` | the shape symbol (`shape_id`) | `content_hash`, and the field set as wire name to wire type, format, required, nullable | the declaring document, `origin_tier` |
| `boundary-property` | `resolved_config` | key, environment | value (as the exit masks it), `unresolved_reason` | source file |
| `schedule` | `scheduled_work` | handler, trigger, name | expression, resolution | catalog |
| `error-handler` | `error_handlers` | handler, exception | advice, scope, status, response shape | catalog |

**The wire is the identity; the handler is evidence.** Measured on six months of
`spring-petclinic-rest` (spec §1b): the architecture gained two routes and lost none, and
keyed on the wire the diff reads `+2 −0`; keyed on the wire plus the handler it reads `+44
−42`, because a refactor moved every controller into a `v1` package and renamed it. The user
ruled it (decision 1, 2026-10-22): *implementation should never matter, only the exposed
visible parts*. It holds for every protocol, not HTTP alone — a topic, an operation name, a
QName — and four handlers behind `GET /**` are ONE endpoint with four pieces of evidence.
`dependency` keeps `peer` in its identity because `POST /v1/orders` on `billing` and on
`ledger` are two dependencies. A `schedule` or `error-handler` has no wire, so its handler
symbol IS its identity and a renamed job reads removed-and-added: the one stated
inconsistency (decision 2).

**`data-contract` is identified by the shape symbol, never by `content_hash`.** The hash is
what CHANGES when a field is added, which is the `changed` entry the drift scenario exists
for; a bare-name shape (`AuditEntry`, a declared schema) is identified by that name, as
`shapes` already does.

**A body is an attribute twice.** Once as the field set by wire name, so a field added to a
response reads `changed` with the field named and not gone-and-back; and once as the raw
`request_shape`/`response_shape` descriptor compared structurally, with every type symbol
erased. The field set alone cannot tell an `OrderView` from a list of them, so `OrderView`
becoming `List<OrderView>` is one `breaking` change, and a DTO renamed with the same
structure is no change at all.

**A `both`-direction row belongs to both kinds** — it is one address on each side — and a
catalog that declares no direction feeds both, because which one a row has is known only per
row.

**Rows grouped under one identity that DISAGREE on an attribute keep every value.** Where
four handlers behind one wire carry different request shapes, or one method has two
`@Scheduled(cron=...)`, the attribute is `{"several": [the distinct values, sorted]}` and
never whichever row the query happened to order first — M06's no-silent-choice rule, applied
to a reader instead of a stitcher. Sets (`requirements`, `conditions`, `headers`) are unions.

**A condition set is what the code DECLARES** (spec
[2026-10-23](../superpowers/specs/2026-10-23-deployment-set-conditions-design.md), rulings 2
and 3; vocabulary 2). Conditions belong to beans, so an `endpoint` and a `dependency` both
carry the `{kind, expression}` of the bean their code lives in — a dependency's matched on its
row and its `caller`, since an outbound row has no handler. Each environment's verdict
(`environment`, `holds`) stays in the workspace, the bundle and the documents, outside the
boundary row, so a configuration change is reported once, as the `boundary-property` change
it is, and only a code change is a `conditions` change.

**Enrichment never enters.** Components, prose and overlays are judgements, not facts
(`meridian-integration.md` §0a), and `open_questions` and `roots` are Sextant's working state.

**The vocabulary is DATA.** One registry is read by the diff, the observability map and
`analyze` (which records the kinds each skipped catalog feeds, from the catalog's own `style`,
`direction` and whether it declares a shape model), so no reader keeps its own list of kinds.
A catalog that declares no `direction` — the `config_join` catalogs `spring-integration` and
`spring-kafka-media`, whose rows are either direction, known only per row — feeds both
`endpoint` and `dependency`. Each kind's rows come from ONE named
query in `storage/duckdb/workspace.py`'s registry (`boundary_endpoint`, `boundary_dependency`,
`boundary_contract`, `boundary_property`, `boundary_schedule`, `boundary_error_handler`;
`module` is read off `metadata.json`), written as plain `SELECT`s over the exported tables'
columns so the same query serves a workspace and a bundle's Parquet. `boundary_vocabulary_version`
(currently `2`) moves with any edit that adds a kind or moves a column between the three
sets, which changes what a comparison means without changing a table — §7 says where it is
stamped and who compares it.

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

> **PARTLY BUILT — six of the ten below have a reader, five of them new and under shorter
> names; four do not.** `callers_of`, `callees_of`, `implementations_of`, `uses_of` and `impact_of` ship as
> `question_callers`, `question_callees`, `question_implementations`, `question_uses` and
> `question_impact_step` in `storage/duckdb/workspace.py`'s `_NAMED_QUERIES`, answered at MODULE
> scope by `application/query/questions.py` and reached through `api.query` (spec
> [2026-10-22](../superpowers/specs/2026-10-22-boundary-vocabulary-and-diff-design.md) §5,
> FR-24). A sixth question that was never in the list, `source` (the file and line range
> declaring a symbol), ships beside them — six questions in all. `trace_of` exists as
> `application/query/trace.py`, a Python walk over `call_edges`/`roots`/`return_flows` that
> takes a ROOT rather than an endpoint, at module scope only, with no rendered output reading
> it yet (`docs/open-issues.md`, OI-25). `paths_between`, `endpoint_for_address`,
> `who_uses_shape` and `who_reads_config` do NOT exist. There is no CLI noun and no plugin
> over any of them: the agent query surface stays gated on language coverage (the 2026-09-18
> ruling, reopened on 2026-10-22 for the in-process function alone).
>
> The same `_NAMED_QUERIES` registry also holds the resolver-internal set (`documents`,
> `endpoints`, `shapes`, `annotations`, …) reached through `Workspace.query`, serving M04,
> and the `boundary_*` reads the diff uses (§3, "The boundary vocabulary"). The 2O
> documentation sweep recorded the original gap as entry #11 of `open-issues.md` OI-83,
> having found five documents citing `trace_of` as though it were built. §5.3's second corollary: where a document deliberately describes something
> ahead of its implementation, it must say so in words a reader cannot mistake for a shipped
> feature.

Shipped as part of the schema, not left to each consumer to write. [M09](M09-query.md) and
[M07](M07-renderer.md) both use them, and neither should be writing its own reachability
query.

`callers_of`, `callees_of`, `implementations_of`, `uses_of`, `impact_of`,
`paths_between`, `endpoint_for_address`, `trace_of`, `who_uses_shape`, `who_reads_config`.

`impact_of` returns three partitions — definite, possible, and the unknown regions reached
— never one count. `paths_between` returns the union subgraph of all routes, never a list
of routes.

**As built for `impact`** (`application/query/questions.py`): the walk goes upstream over
`callers` and `uses` and answers `{"definite", "possible", "unknown_regions"}`. A symbol is
`definite` when some path to it crossed only `resolved` call edges and type references, and
`possible` when every path crossed at least one `narrowed` dispatch; the strongest path
wins, so a symbol met first through a narrowed call and later through a resolved chain is
`definite`. `unknown_regions` is where the walk cannot see, listed and never walked: a
`call_edges` row whose `target` names the walked symbol and whose `callee` is NULL (reason
*callee body not read — dispatch unconfirmed*, `symbol` the caller), and a DIRECT ancestor
in `type_hierarchy` with `scanned = false` (reason *ancestor not scanned*). The impact of a
TYPE seeds its walk with the type's members, because a change to the type is a change to what
its members' callers depend on.

**`uses` reads type arguments at every nesting depth**, so `List<Money>` and `Map<String,
Money>` both use `Money`; it also returns the type's direct subtypes, which `type_hierarchy`
records. Measured on `mall-admin`, `PmsProduct` went from 13 uses to 21 once
it did. The depth is walked in Python, not SQL: the dependency floor (`duckdb>=1.1`) has no
`json_tree`, so `question_uses` selects every member whose signature TEXT contains the bare
type, which a true match always does, and the parsed signature confirms each — the text test
can only admit, the walk decides.

**Cost (§8.7), decided in the spec:** one read places the subject, every other question is
one read, and `impact` is one read per hop of the whole frontier — never one per symbol
reached. A symbol rejoins the frontier only when its classification improves, which happens
once, so the walk ends on any graph, cycles included. Measured on `mall-admin` (25,377 symbols, 24,511
call edges): the impact of its most-called method reached 776 symbols in six reads and 76 ms
(measured before the floor fix to the `uses` query, commit 225e4161), and the impact of
`PmsProduct`, after it, gave 49 definite, no possible and 13 unknown regions over
four hops in 35 ms.

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
| Each **document** | `sextant_version`, `fact_schema_version`, `scanner_id`, `content_hash`, `redaction_set_hash` |
| Each **workspace** | The above, plus `graph_schema_version`, `catalog_hash` (written by `analyze` since the diff, below, reads it long after the catalogs are gone) and `boundary_vocabulary_version` |
| Each **bundle** | The workspace stamp, in its manifest |
| Each **system workspace** | Its own stamp, plus the stamp of every bundle it used |

The document record is per **source file**, which is where incremental reuse happens — so
this is where the stamp makes cache invalidation exact rather than approximate.

### Two schema versions, not one

Facts and derived tables version separately, because their invalidation costs differ by an
order of magnitude.

**Both are single monotonically increasing INTEGERS (Step 0), not semver, and both start at
`2`.** Neither is ever parsed, ordered or compared for compatibility — the comparison below
is equality and always has been — so a dotted triple carried two numbers that meant nothing
and gave the value a text type, which is what let four hand-maintained producers of
`fact_schema_version` hold two different values with the suite green. Each increases by one
for a change to the thing it stamps. `sextant_version` keeps semver: it is the tool's
release, read from `pyproject.toml` through the installed distribution, and it moves on its
own cadence.

| Change | Invalidates | Cost |
|---|---|---|
| `fact_schema_version` | Facts, and everything after | **Re-extraction.** The expensive one. |
| `graph_schema_version` | Derived tables only | Re-derivation. Minutes. |
| `scanner_id`, or a change to a scanner's declared libraries | That scanner's facts | Re-extraction, for those documents. The libraries live on the workspace (`metadata.json`'s `provenance.scanners`), not the document — every document one scanner wrote in a run shares them, so repeating the pair per document stored one fact many thousands of times |
| `redaction_set_hash` | Facts | Re-extraction. A new pattern cannot clean values already written. |
| `catalog_hash` | Endpoints and everything after | Re-derivation |
| `boundary_vocabulary_version` | Nothing is rebuilt | **Comparison only.** No table changes; a diff across two values refuses, because the same words were not used on both sides. See below |
| `sextant_version` | Derived tables | Re-derivation — **conservative by default** |

**What moved `graph_schema_version`, recently** (the full comment-table is in
`src/sextant/domain/version.py`, which owns the number):

| Version | Change | What a stale workspace does |
|---|---|---|
| 3 | `endpoint_conditions`, a derived table the system tier federates (spec `2026-10-21-conditional-controllers-design.md`) | refused by name by `system analyze`, never a bare `Catalog Error` |
| 4 | `bean_conditions` (a new derived table) and the views `bean_presence`, `symbol_beans`, `candidate_presence`; `endpoint_conditions` stops being a table and becomes a view gaining `caller`, `via`, `bean_kind`, `bean`; the table `interface_beans` (spec `2026-10-22-conditional-beans-design.md`) | `module analyze` replaces the old table with the view when it opens the workspace (DuckDB refuses `CREATE OR REPLACE VIEW` over a table); `system analyze` refuses a participant that still holds the old table, by name |
| 5 | No table change: what `endpoints.peer` may hold. Before 2026-10-23 `split_url` kept a URL's userinfo in the peer (`svc:s3cret@billing.internal`), which no exit could tell from a Spring-WS `mailto:` peer, so a workspace of that vintage is refused rather than masked by a guess (user ruling) | `render`, `enrich`, `export` and `query` refuse it by its stamp; `system analyze` now refuses a participant by the same stamps, naming it and the command; `module diff` refuses two such sides unless the producer change is allowed, and then masks each scheme-less peer with an `@` whole (user ruling) |
| 6 | No table change: condition verdicts a deployment can change are no longer decided (spec `2026-10-23-deployment-set-conditions-design.md`). A `profile` or `property` condition is `unresolved` unless the environment's own name decides it, and the module's own reading is its evidence | refused by its stamp exactly as at 5, so a workspace holding the older decided verdicts is re-analysed rather than read beside new ones (user ruling, spec §6) |
| 7 | `resolved_schedules`, a new derived table: a scheduled job's placeholder expression per environment, read from the module's configuration through the one placeholder rule (spec `2026-10-23-configured-schedules-design.md`); `scheduled_work` keeps one row per job and its `unresolved` | refused by its stamp exactly as at 5 and 6, so a workspace without the table is re-analysed rather than read as one whose jobs have no configured values |
| 8 | `rpc_hops`, a new derived table: where a gRPC client stub's call to an RPC this module serves lands, its handler named (spec `2026-10-25-quarkus-mutiny-grpc-design.md` §3d); `call_edges` is untouched | refused by its stamp exactly as at 5 to 7, so a workspace without the table is re-analysed rather than read as one whose self-calls stop at the gRPC library |
| 9 | `scheduled_work` gains `name` and `expression_source`; `handler`, `trigger` and `expression` may be NULL; `resolution` may be `partial` or `narrowed`; `resolved_schedules` gains `name` (spec `2026-10-28-quartz-design.md` §3e) | refused by its stamp exactly as at 5 to 8, so a workspace without the columns is re-analysed rather than read as one whose schedules have no names |
| 10 | `scheduled_work` gains `untied`; an `@Scheduled` row's `name` is EMPTY rather than NULL (spec `2026-10-28-quartz-design.md`, "Empty cells", ruled 2026-10-29) | refused by its stamp exactly as at 5 to 9, so every NULL of the older vintage — which could mean any of the three — is re-derived rather than printed as `not in the code` |
| 11 | `endpoints` and `endpoint_metadata` gain `row_id`: an endpoint row is numbered when it is written, and an entry attached to it is bound to that number when it is written and follows the row through the path prefix and a protocol reclassification (spec `2026-10-30-object-identity-design.md`, ruling 7). The export leaves the id out, so no bundle column changes | refused by its stamp exactly as at 5 to 10, so rows with no id — which no pass could find again — are re-derived rather than read beside numbered ones |

**The last row is deliberately blunt.** Any Sextant version change re-derives, because
derivation logic may have changed and there is no cheap way to know. Re-derivation is the
cheap half. If that becomes painful, the answer is a separate version bumped only when
derivation behaviour changes — not a weaker default.

**A mismatch never produces a mixed-vintage graph.** It forces the affected rebuild. That is
what keeps per-row stamping unnecessary: the guard is complete, so a workspace can only
contain one vintage.

### Where the comparison happens

**`api._stale_stamps`, at the read gate `render`, `enrich` and `export` all share**
(`_refuse_if_unanalyzed`). Three stamps are compared against the build now running —
`schema_version` (the graph stamp, written at `metadata.json`'s top level),
`provenance.sextant_version` and `provenance.fact_schema_version` — and any disagreement is
a refusal naming the stamp that moved, not a silent re-analysis: a `render` that quietly
re-ran the pipeline would be the one verb that promises to read what `analyze` left behind
([M00](M00-cli.md)'s "no analysis" rule) doing the opposite. An **absent** stamp counts as a
mismatch; `egress/render/metadata.py` has always written all three.

**`boundary_vocabulary_version` is not one of the three.** It versions the WORDS
(§3, "The boundary vocabulary") and not a table, so a workspace with an older value is still
a perfectly good graph for `render`, `enrich` and `export`, and `_stale_stamps` does not
compare it. The one comparison is `sextant module diff`'s, which refuses across two values
and names both ([M00](M00-cli.md)); `export` copies the value into the manifest's `producer`
rather than stamping its own, since the vocabulary the entries were named in is the one
current when the workspace was built. **`catalog_hash` is the other change:** `analyze` now
writes it into `metadata.json`, because the catalogs are in hand then and not when a diff
reads the workspace, and the exporter COPIES it, recomputing from the catalogs installed
only for a workspace analysed before `analyze` recorded one.

*Recorded because it was documentation for four phases.* Until 2Q gave the walk a reader,
every one of these versions was written and compared by nothing (`OI-24`) — harmless only
while no rendered output read a derived table that a stale workspace would answer EMPTY.
`roots` and `call_edges` are exactly that shape: an empty table and a table that did not
exist yet are the same bytes, so `## Traces` on a 1.0.0 workspace would have said
`None found.` about a module with 160 endpoints.

The same stamp travels in the bundle ([D06](D06-bundle-format.md)) so that
[M05](M05-sync.md) can refuse to assemble a system from incompatible parts.

---

## 8. Open decisions

| Decision | Blocks |
|---|---|
| Whether `trace_steps` stores nesting as a path or as parent references | M07's sequence emitter |
| ~~Whether `findings` is one table with a kind column or one table per family~~ — **moot, W51**: there is no `findings` table and none is planned | M04 |
| Whether the full-text index lives in the workspace only, or also in a bundle | M08 |
