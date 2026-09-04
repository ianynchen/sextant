# Phase 2O — Spring surface completeness

**Status: revision 4 for user review, 2026-09-03.** Revision 1 claimed broad engine
reuse; adversarial round 1 (33 findings, 10 Critical) proved the documented
engines refuse most of it. Round 2 verdicted the redesign architecturally sound
with 15 local defects; round 3 verdicted those 15 closed with 9 residuals
(whole-address slash guard, wire method names from generated constants not
casing, the published-stubs-jar boundary, the interface/implementor
double-derivation ruling, Integration's built-in scoped to
enumeration-plus-questions). All folded in here, and a controller self-review then closed nine more
(the identity-authority contradiction CP-8 introduced, §5's tableless "channel
row", the fence/published-jar interaction, COVERAGE deliverables, the
Framework-version scope CP-1 needs, Evo Inflector's Apache-2.0 attribution).

**The real work this phase names:** ONE certain extractor capability (9.14,
generic superinterface references — Data REST cannot read an entity type
without it) plus ONE probe-gated candidate (9.13, extends relationships);
one fact-schema amendment; three closed-set amendments; five new engine
styles; and six engine extensions — `config_join`'s `annotation_value`
binding source, `single_call`'s secondary address capture,
`schema_operations` reading the operation sub-record, `resolves.direction`
implemented at last, `annotation_driven`'s `path_prefix`, and rung 5's marker
read. 2O is the largest phase yet — the user chose full gRPC, full Data REST,
and Spring Integration kept aboard, twice affirmed.

Closes gap B of the 2026-09-02 gap program. Branch `feat/phase-2o-spring-surface`,
stacked on `feat/phase-2n-enrichment-polish` (PR #16) — retarget when it merges.

**User rulings folded in (2026-09-03):** gRPC FULL (descriptors too); Data REST
FULL route set; Spring Integration STAYS in 2O; `@Scheduled` and
`@ControllerAdvice` each render as their OWN section (the endpoint table stays
wire-true); leading-slash identity follows WHATEVER SPRING ITSELF SERVES (DR-6);
NO `--timeout` — an LLM invocation failure errors out loudly, retrying is the
operator's re-run.

---

## 0. Constraints carried from the program

- **NFR-1 determinism**; no network in tests, ever.
- **DR-6 framework mirroring**: predict what the framework actually does.
  Mirrored algorithms are CHECKPOINT-GATED (§0a), and every checkpoint leaves a
  DURABLE artifact in the repo: the probe script commit-pinned (2M's
  `field_check.py` precedent) plus a recorded expectation table the unit tests
  then pin — a rule trusted on a run nobody can re-run is an assertion, not
  evidence.
- **Unresolved-is-an-answer**; framework names live in catalogs only; new D02
  vocabulary is neutral, declared, and guarded (validated against closed sets,
  cross-catalog conflicts refused — the format-table discipline of D02 §rung
  machinery applies to every new key).
- **No version bumps**; `uv.lock` never committed; NO new Python dependencies
  (descriptor machinery shipped in 2G).
- **NFR-5 closed sets**: this phase amends closed sets in THREE places — §3's
  protocols, §1's declared-shape operation record, and the
  `open_questions.question` kind set, which is closed at two values
  (`payload_binding`, `format_conflict`) and gains THREE: **`channel_destination`**
  (candidates: channel name + handler symbol — §5's product),
  **`service_identity`** (candidates: class symbol + reason — §1b's missing
  descriptor / flagged-but-unmatched class), and **`environment_divergence`**
  (candidates: config key + per-environment values — §2b's divergent base
  path). Each kind gets its renderer and export switch arms (§12). Every
  amendment is a versioned schema change with the estate cost stated where it
  is incurred.

## 0a. Checkpoint register

Execution front-loads these; falsification amends the spec with a ledgered
ruling. Each CP commits its probe + expectation table.

- **CP-1 Spring path combination.** `@RequestMapping("users")` and `"/users"`
  serve the same URL; class+method combine inserts exactly one `/`; empty method
  path adds nothing; a trailing slash is DISTINCT since Framework 6. Verified
  against a live Boot app before §8's seam is written. **Version scope, stated
  because DR-6 demands it:** the mirrored rule is Framework 6+ / Boot 3+ (where
  `setUseTrailingSlashMatch` was removed), which is what Sextant's fixtures and
  field validations run. Boot 2 / Framework 5 matched a trailing slash to the
  slashless mapping, so on such a project our trailing-slash distinctness
  over-reports — the probe records both behaviors, COVERAGE states the version
  scope, and a per-version rule waits until a Boot 2 corpus is a real
  requirement rather than a hypothetical.
- **CP-2 Data REST derivation.** Two-part prediction: (a) with
  `org.atteo:evo-inflector` on the app's classpath, the collection path is the
  Evo Inflector pluralization of the uncapitalized entity simple name; WITHOUT
  it, the uncapitalized simple name stands unpluralized (Spring HATEOAS selects
  the provider by classpath presence). (b) `path=` overrides; `exported=false`
  removes; query methods surface at `/search/{methodName}` with `@RestResource`
  overrides; item routes honor which CRUD interface is extended. Both halves
  verified against live apps, one per classpath state.
- **CP-3 extends-relationship presence.** D00 §4 declares
  `relationship_kind: extends`, but 2G's execution observed plain `extends`
  ABSENT from the live fact stream (protobuf hierarchy matched via an
  `implements` instead). Probe the extractor's actual output for a plain class
  extension. If absent: extractor capability 9.13 (emit the erased superclass
  reference / extends relationship) — §1 needs it.
- **CP-4 protoc naming, computable direction.** From a DESCRIPTOR's
  `java_package` (or proto package when unset), `java_outer_classname`, and
  `java_multiple_files`, predict the generated `<Service>Grpc` class fqn and its
  `<Service>ImplBase` / `<Service>{,Blocking,Future}Stub` nested names. Verify
  by compiling the fixture's `.proto` and diffing predicted vs. actual. (The
  REVERSE direction — proto package from a bytecode name — is NOT available and
  nothing in this spec uses it; the proto package differs from `java_package`
  routinely.)
- **CP-5 Actuator paths.** `@Endpoint(id="x")` under `/actuator/x`;
  `@ReadOperation`→GET, `@WriteOperation`→POST, `@DeleteOperation`→DELETE;
  `management.endpoints.web.base-path` relocates the prefix. (`@Selector`
  path segments are a stated boundary — §3b.)
- **CP-6 Boot's default converter.** `jackson-databind` on the classpath of a
  Spring MVC/WebFlux app makes JSON the default format for unannotated handlers.
- **CP-7 interface inheritance reach.** 2E's effective-annotations pre-pass
  (composed + inherited, gated to type-annotated catalogs) — does its walk carry
  an INTERFACE's annotations onto the implementing class? §6's inbound half
  needs it; if not, §6 states the extension.
- **CP-8 generated gRPC classes in module facts.** protoc-generated classes
  compile INTO the module's own output, so the workspace scans them: probe that
  (a) the generated `<Service>Grpc` class appears in module facts, (b) its
  `SERVICE_NAME` constant (`"<protoPackage>.<Service>"`) is readable as a
  constant fact (D00's `constant`), (c) the user class's extends relationship
  to its `ImplBase` is visible (CP-3), and (d) the WIRE METHOD NAMES are
  readable from the same generated class — grpc-java builds each
  `MethodDescriptor` via `generateFullMethodName(SERVICE_NAME, "GetOrder")`,
  so the proto-cased method name is a string constant there too. (d) matters
  because the reverse derivation is NOT available: proto `get_order` and
  `getOrder` both compile to Java `getOrder` — method names are never derived
  by casing.

---

## 1. gRPC — the FR-3 closure

`grpc` is ALREADY in the closed protocol set (D00 §4) — no protocol change here.
What is missing is everything above it.

**Where identity comes from, stated once** (revision 4's CP-8 discovery changed
this, and the rest of §1 now follows it): the wire identity D01's identity table
requires — `<protoPackage>.<Service>/<Method>` — is available from EITHER side
independently. The descriptor knows it because it declares it; the generated
bytecode knows it because protoc compiles `SERVICE_NAME` and the wire method
names into the generated class as string constants, and that class compiles into
the module's own output. Neither side is the sole authority, and that redundancy
is the design's strength: each derives the same identity, so where both exist
they merge exactly on it, and where only one exists the rows still publish a
true identity rather than a degraded one. What each side contributes ALONE is
different — the descriptor contributes the full method inventory and the
request/response shapes; the bytecode contributes the handler symbols and proves
which methods are actually implemented.

### 1a. Descriptor services — the identity layer

2G's harvest already parses `FileDescriptorSet`s (embedded and
`.proto`-compiled) and reads only message types. The interpreter's descriptor
branch grows a SERVICE read. Landing zone: `declared_shape` gains an OPTIONAL
`operation` sub-record — `{input_ref, output_ref, client_streaming,
server_streaming}` — populated when `role: operation`. This is a fact-schema
amendment (NFR-5: `fact_schema_version` bumps; the estate cost is re-analysis of
existing workspaces, accepted pre-gate; 2I's SOAP operations may later fill the
same record — today their output side stays NULL and nothing changes for them).

- Each descriptor `service` method yields a `declared_shape` with
  `role: operation`, `schema_name = <protoPackage>.<Service>/<Method>`, the
  operation sub-record filled, input/output refs linking to the SAME
  descriptor's message shapes (intra-descriptor join, no guessing).
- The `schema_operations` engine's existing `role: operation` branch extends to
  read the sub-record: operation identity **(`grpc`, NULL verb,
  `package.Service/Method`)**, evidence carrying the declaring shape's OWN tier
  as the engine already does — `compiler` for an embedded descriptor,
  `declared` for a `.proto`-sourced one. Streaming renders as
  `unary | server-streaming | client-streaming | bidi` in the operation's detail
  section (a typed 2M Detail — NOT a new endpoints column).
- **`format_fixed: {grpc: protobuf}`** ships on the gRPC catalogs — the third
  protocol on rung 1 (after `graphql: json`, `soap: xml`), and the union/conflict
  guards already shipped apply.

### 1b. Implementation detection — the new `supertype_derived` style

No shipped engine derives from a SUPERCLASS: `interface_implementation` is
registration-gated (its own contract: "the registration is the evidence") and
joins direct `implemented_interfaces` only — and gRPC's Spring/net.devh starters
register by bean scanning, so there is no registration call to gate on. New
engine style, neutral, small — and pattern-free: protoc compiles the generated
classes INTO the module, so the supertype's own facts are in the workspace
(CP-8). No glob grammar, no JVM-form names — both would break D02's naming
rules and neither is needed:

```yaml
style: supertype_derived
matches:
  supertype_marker:
    constant: SERVICE_NAME     # the generated class declares it (CP-8)
  members: overridden_public_methods
```

- The match is EVIDENCE-shaped: a class whose extends target is itself in the
  module's facts and declares the marker constant. The service identity is the
  constant's VALUE verbatim — `<protoPackage>.<Service>`, exact, from bytecode
  alone. One row PER OVERRIDDEN PUBLIC METHOD, wire method name from the
  generated class's own method-name constants (CP-8(d) — never derived by
  casing, which is not invertible) — ONE identity form, no simple-name
  fallback (revision 2's second form is withdrawn).
- With a descriptor present, the 1a row and this row carry the same
  `(protocol, direction, method, path)` by construction and MERGE on the real
  key — D01's only join. The bytecode side contributes the handler symbol.
- If CP-8(b) or (d) falsifies (the generated constants are unreadable) AND no
  descriptor covers the service, rows derive with the path UNRESOLVED
  (expression = the supertype fqn verbatim) and a gap names BOTH absent
  sources — never a fabricated package, never a half identity. When a
  descriptor IS present it supplies the identity by itself, so the falsified
  constants cost only the standalone case.
- **Stated boundary — stubs from a PUBLISHED jar:** a module consuming
  `*-grpc-stubs` as a dependency has no generated classes in its own output.
  Precisely what is lost is the IDENTITY, not the edge: the class's own
  `extends` fact still names its supertype symbol, but the jar holding that
  supertype is unscanned, so its `SERVICE_NAME` constant — the only honest
  source of `<protoPackage>.<Service>` — cannot be read, and nothing else
  proves the supertype is a gRPC service at all (name-shape guessing is
  exactly the glob grammar this style refuses).
  The escape is the shipped `.sextant.yml` library opt-in (D02 §4a — extract
  the stubs coordinate, and the generated classes' facts arrive under
  `facts/lib`); without the opt-in, COVERAGE states the boundary. For the
  ANNOTATED starters, silence is not an outcome — the `@GrpcService`
  corroboration rows (below) still surface the class as a `service_identity`
  open question when the supertype match sees nothing. An UNANNOTATED Spring
  gRPC service consuming published stubs (the annotation is optional there)
  does go unseen — COVERAGE carries that cell explicitly.
- `@GrpcService` (Spring gRPC, net.devh spellings) rows ride `annotation_driven`
  as corroboration only — the annotation carries no service name, cannot mint
  identity, and a class it flags that the supertype match missed renders as an
  open question, not an endpoint.
- CP-3 decides whether the extends relationship is already in the fact stream;
  if not, extractor capability 9.13 is IN SCOPE for this phase.

### 1c. Outbound — `@GrpcClient` injection, its own style, service-level

A second new style — injection is a different SHAPE of evidence than
supertype-plus-members, and D02's "a style is a shape of evidence" rule forbids
fusing them into one engine:

```yaml
style: injected_client
matches:
  field_annotation: net.devh.boot.grpc.client.inject.GrpcClient   # per catalog
  identity_marker:
    constant: SERVICE_NAME   # the stub type's OUTER class constant — declared
                             # here too so the read stays catalog data (the
                             # neutral key name: no supertype in this style)
```

- **One row per injected stub, at the SERVICE level** (method NULL, path =
  `<protoPackage>.<Service>` from the stub type's outer class marker constant,
  CP-8 — or unresolved when unreadable). The injection declares that the module
  TALKS TO the service; it does not declare which methods, and deriving one row
  per service method would fabricate boundaries (revision 2 did exactly that —
  withdrawn). Per-method outbound rows arrive with 2Q's call graph, which can
  read the actual stub calls; COVERAGE states the coarseness until then.
- **This is a SECOND gRPC identity form** — `package.Service`, method NULL —
  and it earns its own D01 identity-table row beside `package.Service/Method`
  (SOAP's two forms are the precedent), a §12 schema-touch line, and the
  honest sentence that a service-level outbound row LINKS TO NOTHING until 2Q
  makes it per-method — DR-5 matches identities exactly.
- **The fence** (SEI precedent): outbound rows derive only for services NOT
  locally implemented (no local class extends that service's `ImplBase`).
  **The fence and §1b's published-jar boundary interact, and the ruling is
  explicit:** stated by IDENTITY ("that service's `ImplBase`"), the fence
  cannot fire where §1b says the identity is unreadable — so a module
  implementing a service against PUBLISHED stubs would pass it and derive a
  self-directed outbound row. The fence is therefore stated by SYMBOL NAME
  instead, which the jar cannot withhold: a module class whose `extends`
  target shares an OUTER CLASS with the injected stub's type
  (`…OrderServiceGrpc$OrderServiceImplBase` against
  `…OrderServiceGrpc$OrderServiceBlockingStub`) is implementing the service
  it would otherwise appear to call. The extends RELATIONSHIP is a fact of the
  module's own class even when its target lives in an unscanned jar — what the
  jar withholds is the `SERVICE_NAME` constant, i.e. the identity, not the
  edge. Where the module genuinely calls a service it does not implement, no
  such sibling exists and the outbound row derives normally.
- **Bare `newBlockingStub(channel)` without `@GrpcClient` is a STATED BOUNDARY
  this phase**: no engine derives from a type reference alone, and the call's
  argument is a Channel object, not an address. COVERAGE gets the row.

### 1d. Boundaries

gRPC-over-REST transcoding (gRPC-Gateway, Connect); server reflection,
health/channelz built-ins — runtime rows, descope-checkpoint list.

## 2. Spring Data REST — the invisible API made visible

New catalog `spring-data-rest.yml` on a new engine style **`derived_resource`**.
Why not `annotation_driven` with `members:`: that style derives rows FROM member
signatures (path/verb read off each member); Data REST's table is fixed BY
FRAMEWORK RULE per repository — six verb/route combinations whose existence
depends on which CRUD interface is extended, not on any member's own annotations
— plus per-query-method search routes. The rule-table shape is genuinely new.

### 2a. Detection

- A repository is an interface whose DIRECT superinterfaces (erased, as D00
  records them) match the catalog's enumerated Spring Data list
  (`Repository`, `CrudRepository`, `JpaRepository`,
  `PagingAndSortingRepository`, `ListCrudRepository`, reactive variants —
  catalog data, framework names where they belong), OR reach that list through
  interfaces DECLARED IN THIS MODULE (a within-module closure walk over module
  facts — `@NoRepositoryBean` base-repo pattern; chains through OTHER jars are
  a stated boundary).
- Entity and ID types come from the generic superinterface reference. D00
  records generic SUPERCLASS references only and interfaces erased — so
  **extractor capability 9.14 (generic superinterface references) is CERTAIN
  work in this phase**, not contingent. (Revision 1's CP-3 mislabeled this;
  the docs already answer it.)
- The catalog gates on `detect.coordinates` naming the Data REST artifacts —
  the SHIPPED jar-presence mechanism; when no `ClasspathEntry` carries a
  readable coordinate, the catalog reports SKIPPED in the manifest (the
  existing, visible degradation — not silence).
- `@RepositoryRestResource` is optional; `exported=false` removes a repository;
  per-method `@RestResource` removes or renames one route.

### 2b. Route derivation (CP-2)

| Route | Verb | Condition |
|---|---|---|
| `/{basePath}` | GET | collection read |
| `/{basePath}` | POST | `save` exposed |
| `/{basePath}/{id}` | GET | item read |
| `/{basePath}/{id}` | PUT, PATCH | `save` exposed |
| `/{basePath}/{id}` | DELETE | `delete` exposed |
| `/{basePath}/search/{query}` | GET | one per exported query method |

- `basePath` = `path=` when given; else the CP-2-mirrored derivation: Evo
  Inflector pluralization when the app's recorded classpath carries
  `org.atteo:evo-inflector` (`domain/pluralize.py`, the FULL published
  algorithm ported, deterministic), else the uncapitalized simple name
  verbatim. **Attribution:** Evo Inflector is Apache-2.0, and a port of its
  rule set is a derivative of it — `domain/pluralize.py` carries the Apache-2.0
  attribution header naming the origin project, and the repo's dependency/
  licence documentation gains the row. (Porting rather than depending is still
  right: the rules are English pluralization, we take no new Python dependency,
  and the port must mirror the exact library the JVM app resolved.) All rows publish at resolution **`resolved`** with evidence
  **`declared`** — endpoints use only `resolved`/`unresolved` today, `narrowed`
  and `partial` are defined by candidate-set semantics this column does not
  carry, and DR-6's precedent is exactly this shape: 2I's `reversed_package`
  QName prediction publishes at full confidence because the mirrored rule IS
  the framework's rule, checkpoint-pinned. The pluralizer's divergence risk on
  exotic nouns is recorded in the catalog's D02 section and fenced by CP-2's
  committed expectation table, not smuggled into resolution semantics.
- `spring.data.rest.base-path`: read-if-present from `resolved_config` (default
  is empty — a config-less run derives everything at `/`); the catalog does NOT
  `require` the capability, so no silent skip. A base path that DIFFERS between
  environments follows `config_join`'s cross-environment rule by analogy: one
  row, prefix unresolved, open question filed.
- **Engine order:** `derived_resource` runs AFTER every observed-endpoint style
  and BEFORE `config_join`, with insert-if-absent semantics — a predicted route
  never displaces an observed controller row (the guard's whole purpose).
- Media: implement D02's specified-but-unused `default_produces` on this
  catalog (`application/hal+json`), and add `application/hal+json → json` to
  the shared `media_formats` table (union/conflict guards apply). NOT
  `format_fixed` — that key is protocol-wide and would claim all of HTTP.

### 2c. Boundaries

Projections/excerpts, HAL affordances, `@CrossOrigin`, event handlers, QueryDSL
web support: out, stated.

## 3. Messaging + annotation batch

### 3a. Protocol closed-set amendment (NFR-5)

The closed protocol set gains **`amqp`** and **`pulsar`** (D00 §4 amendment,
versioned; estate cost = re-analysis, accepted pre-gate). With `amqp` real,
Spring Cloud Stream's stopgap `binder_protocols: {rabbit: jms}` MIGRATES to
`{rabbit: amqp}` in the SAME phase — one broker, one protocol, consistently.
(Honesty note: this consistency does NOT yet buy producer↔consumer linking —
AMQP producers address exchange+routing-key while consumers address queues, and
the join between them is the broker's binding table, whose annotation form
`bindings=` is boundaried below. The link is a COVERAGE boundary; the migration
is still right because two protocols for one broker would foreclose it forever.)
The migration is an identity change with §8's full four-part blast radius —
protocol is in the id hash and the enrichment anchor tuple, so old-id overlays
reject whole and 2N verdicts on rabbit rows go stale — handled and released
alongside §8's, one audited golden update, one release-notes callout.

### 3b. The catalogs

- **`spring-rabbit.yml`** — `@RabbitListener(queues=…)` inbound (protocol
  `amqp`; queue names verbatim; `${…}` placeholders through the shipped ladder;
  SpEL `#{…}` renders UNRESOLVED verbatim — no SpEL reader exists and none is
  built; `bindings=` nested annotations are a STATED BOUNDARY — D00's literal
  model has no nested annotations). `@PulsarListener` sibling rows (protocol
  `pulsar`). Outbound `RabbitTemplate.convertAndSend(exchange, routingKey, …)`:
  AMQP's wire identity is the exchange+routing-key PAIR, which `single_call`'s
  one-address contract refuses — `single_call` gains an optional
  **secondary-address capture** (`address_arg_2` + a catalog-declared join
  format), a small neutral extension; identity renders as
  `exchange/routingKey`. Overloads without an exchange (default exchange)
  capture the routing key alone, stated.
- **`spring-sqs-legacy.yml`** — the two older `@SqsListener` spellings, joining
  the shipped catalog. Pure data.
- **`spring-actuator.yml`** — `annotation_driven`: class `@Endpoint(id=…)` +
  member operation annotations per CP-5. The `/actuator` prefix is a
  catalog-declared constant prefix (new neutral key `path_prefix`, guarded);
  `management.endpoints.web.base-path` overrides read-if-present via
  `resolved_config`. **`@Selector` parameters are a STATED BOUNDARY**: the only
  parameter-annotation read the engine has is `request_body`, and `mapping`
  cannot express append-per-parameter — selector-bearing operations render at
  the base operation path with the boundary stated (CP-5 trimmed accordingly).
  Built-in endpoints (health/info/metrics — dependency + property, no user
  code): stated boundary.
- **`jakarta-servlet.yml`** — `@WebServlet` inbound via `annotation_driven`
  (urlPatterns verbatim). `@WebFilter`, `FilterRegistrationBean`,
  `ServletRegistrationBean`: stated boundaries.

## 4. Non-wire sections — two new styles, two new tables

The endpoint table stays wire-true (user ruling). Each family gets a small
dedicated engine style (neutral; annotation names from catalogs), a D01 table, a
D06 bundle artifact, an M07 section, and an M08 export slot — the full
derive→render→export pattern, stated as four schema/doc touches per family.

### 4a. `style: scheduled_work` → `scheduled_work` table

`spring-scheduling.yml` (`@Scheduled`, `@Schedules`): handler symbol, trigger
kind (`cron | fixedRate | fixedDelay`), expression verbatim (placeholders through
the ladder; unresolvable → unresolved). Renders as a "Scheduled work" section.
**Stated consequence:** D00's `root_kind: scheduled` closed-set member stays
unfed this phase — `trace_of` roots on inbound endpoints and scheduled handlers
are deliberately not endpoints; the 2Q call-graph phase, which builds traversal,
is where scheduled roots come alive. Quartz: later catalog, same table.

### 4b. `style: error_advice` → `error_handlers` table

`spring-advice.yml` (`@ControllerAdvice`, `@RestControllerAdvice`,
`@ExceptionHandler` — including handler methods inside controllers, scoped to
that controller per Spring's own rule): advice class, scope attributes verbatim
(`annotations=`, `basePackages=`, `assignableTypes=`), exception types (from the
annotation value, else the parameter type — Spring's rule, DR-6), status from
`@ResponseStatus` (on handler or exception class). **A status inside a
`ResponseEntity` body is a STATED BOUNDARY this phase** — reading it is
`fluent`-style body analysis that derives no endpoint, deferred. Response shape
symbol where the return type names one. Renders as an "Error handling" section.

## 5. Spring Integration — a `config_join` extension, honestly priced

COVERAGE's own row says these adapters have "no catalog yet" and the shape is
channel indirection, "not a bean's own functional shape" — revision 1 read that
row backwards. `config_join` today reads exactly one input (`resolved_config`)
and one binding source (`bean_name`). The honest mechanism is an ENGINE
EXTENSION, kept in 2O per the user's ruling with its cost now stated:

- `config_join` gains a second binding source: **`from: annotation_value`** —
  the binding key comes from an annotation attribute (`@ServiceActivator`'s
  `inputChannel`, `@InboundChannelAdapter`'s `channel`, `@Transformer`/`@Router`
  rows) instead of a bean name. The catalog declares the join key template the
  way every `config_join` catalog must; destinations are read from
  `resolved_config` ONLY — the engine's single input is unchanged.
- **The deliverable, stated plainly:** Spring Integration defines NO standard
  configuration key for a channel's destination — real apps wire destinations
  in BEAN DEFINITIONS (`AmqpInboundChannelAdapter` beans), and any key
  template would be a PROJECT convention, which D02 places in a repo's own
  `sextant.yml` project catalog, never in a built-in. So the BUILT-IN
  `spring-integration.yml` ships open questions ONLY: every activator/adapter
  files a `channel_destination` **open question** carrying the channel name and
  the handler symbol, and that visibility IS the product. **There is no
  "channel row" and no third table** — the open-questions ledger already has a
  table, a bundle artifact and a rendered section, and a channel with no
  resolved destination is precisely the "something no pass could answer" that
  ledger exists for. (Revision 4 said "derives its channel row", implying
  storage this spec never specified; withdrawn.) The wire
  half is documented as a project-catalog PATTERN (a project whose config does
  carry destinations declares its own key template and rides the same
  `annotation_value` extension); the fixture proves the pattern end to end
  through a project catalog. Never a fabricated wire, never
  `peer: in-process` (which the schema rightly refuses).
- DSL flows (`IntegrationFlow`/`IntegrationFlows.from(…)`): stated boundary.

## 6. The `@HttpExchange` fence — shipping two specified mechanisms

ONE mechanism, not two — revision 2 named both of D02's specified-unimplemented
options, and they cancel: `declared_on: interface` SUBTRACTS exactly the rows
`resolves.direction` must FLIP, so shipping both yields no inbound rows at all.
The ruling: implement **`resolves.direction` with
`when: {owner_implemented_in_module: true}`** alone on
`spring-http-interface.yml`. The flip does both jobs — the locally-implemented
interface's rows become INBOUND at the implementing class (no subtraction line
needed; the fabricated outbound row ceases to exist because the same row now
IS the inbound one). `jakarta-jws-client.yml`'s subtraction stays as it is —
its SEI story is different (the stub is generated, never locally served by the
same rows). CP-7 decides whether 2E's inheritance walk already carries the
interface's annotations to the implementation; if not, the walk extends
(scoped to type-annotated catalogs, as 2E gated it), and the handler symbol on
the flipped row is the IMPLEMENTING method, not the interface method.
**Double-derivation ruling:** when the walk makes BOTH the interface and the
implementing class derive the same route, the implementing class's row STANDS
and the interface's row yields — one wire identity, one handler, and no
routing-ambiguity finding for this pattern (the collision detector exempts an
interface/implementor pair; a real second implementor still trips it).

## 7. Media rung 5 — close the doc/code divergence, no new rung

D02 documents rung 5's markers as package families whose PRESENCE ANYWHERE in
the module is evidence; the shipped pass reads only annotation fqns. The fix is
to make the code match its documentation, not to add a rung: rung 5's marker
read extends to (a) imported/referenced fqns module-wide and (b)
catalog-declared marker COORDINATES on the recorded classpath
(`jackson-databind` etc.). The marker table's entries become
`{package | coordinate}` records; the cross-catalog merge rule is SET UNION —
presence markers cannot conflict by construction, and the D02 sentence
justifying the bare list updates with the structure. Result: an unannotated
Spring MVC handler in a Jackson-bearing module answers `json` at `narrowed` —
same rung, same word, now on the evidence the doc always claimed. **Stated
golden churn:** modules that reference Jackson without annotating flip from
unresolved to `json (narrowed)` — expected, audited in the same golden pass.
CP-6 verifies the Boot behavior the rung mirrors. No `default_format_evidence`
key; revision 1's seventh rung is withdrawn (it duplicated rung 5
unobservably).

## 8. Leading-slash — an identity MIGRATION, not a golden diff

Endpoint path identity becomes the URL Spring serves (user ruling), per CP-1.
Revision 1 understated this; the honest scope:

- **One seam, one truth:** new `domain/paths.py` canonicalizes at identity
  minting; the `path` COLUMN and the id hash both carry the canonical form
  (column-vs-hash divergence would split dedup from every path-keyed anchor).
  Leading slash guaranteed, exactly one `/` per combine boundary, trailing
  slash preserved as distinct.
- **Applicability: protocol `http` only, and PATH-SHAPED values only.** SSE
  rows inherit canonicalization automatically — `protocol_hint` reclassifies
  AFTER the merge, so every SSE row was an `http` row when its identity was
  minted. Two hard exclusions inside `http`: (a) a row whose `path` holds a
  WHOLE ADDRESS or a placeholder-bearing composition
  (`https://${billing.host}/orders` stays whole until the peer join resolves
  it — D02's own rule; prefixing it would fabricate a URL nobody serves) is
  untouched — the seam applies only after the path HALF is separated from any
  base; (b) GraphQL is OUT — its `path` is a FIELD NAME (`orders`,
  `Type.field`), not a URL path, and canonicalizing it would corrupt every
  GraphQL identity and desynchronize the annotation rows from their SDL twins.
  Websocket is OUT this phase — the STOMP catalogs share `protocol: websocket`
  with handshake-path rows, so protocol cannot separate URL paths from STOMP
  destinations there; that ruling waits for a path-kind marker and is
  ledgered, not implied. Queue/topic/gRPC identities untouched.
- **This OVERTURNS a shipped rule for those protocols:** D02's "an empty half
  takes no separator — a slashless name does not gain a leading `/`" was
  written for address composition generally; for HTTP-served paths it predicts
  the wrong URL (CP-1). The overturn is recorded in D02 beside the old rule,
  scoped to `http`; STOMP, websocket, and messaging composition keep the
  old rule.
- **Blast radius, stated and handled:** (a) goldens — one audited update, 2M
  discipline; (b) curation/view overlays naming old endpoint ids are REJECTED
  WHOLE by M01's existing rule — release-notes callout; fixture overlays
  regenerate; (c) 2N enrichment overlays anchored on old paths go STALE and are
  dropped honestly at render (`stale_claims`) — re-enrich is the documented
  remedy; (d) `open_questions` ledger snapshots re-derive on the next analysis.
  The migration ships with all four consequences in the release notes and the
  D01 amendment note.

## 9. Module-kind evidence (2M carry)

Gradle's `application` and Spring Boot plugins (already harvested as plugin ids
by 2M's init script) become SERVICE evidence in M02's module-kind determination,
symmetric with the Maven boot-plugin evidence. Data plus one join; 2M's
skip-gate semantics unchanged.

## 10. Loud invocation failure (the no-timeout ruling)

No `--timeout`. 2O PINS the failure path: a Tradewind invocation error (auth,
network, backend) propagates to the CLI loudly and immediately — named
exception, nonzero exit, no retry loop, no silent wait. One test per auth path
against the fake seam. Retrying is the operator's re-run, by design.

## 11. Out of scope / forward pointers

- **Meridian integration (FR-21–24) is 2P scope** (user ruling 2026-09-03):
  boundary vocabulary, derivation diff, observability map join Spring Cloud in
  2P; 2N's facade already covers FR-24's shape. `docs/meridian-integration.md`
  is currently untracked (another session's draft) — it enters history with
  2P's spec, not this one. Roadmap row updated with this spec.
- Runtime-only rows (FilterRegistrationBean, built-in actuator endpoints, gRPC
  reflection/health, Integration DSL, `newBlockingStub` without `@GrpcClient`):
  descope-checkpoint list, each with a COVERAGE row.
- Quartz, `@Async`, Data REST projections: later catalogs into this phase's
  structures.

## 12. Testing and verification

- Every catalog: fixture code exercising each row shape; goldens updated once
  per task (2M discipline). The orders-service fixture grows a gRPC service +
  `@GrpcClient` client (with `.proto`), a Data REST repository, a scheduled
  method, an advice class, a `@RabbitListener`, an Integration activator.
- CP gates run FIRST in their tasks; each commits probe + expectation table;
  falsification amends the spec with a ledgered ruling.
- New styles (`supertype_derived`, `injected_client`, `derived_resource`,
  `scheduled_work`, `error_advice`) each get the full D02 style documentation
  section, engine unit tests, and an architecture-order test pinning their
  pipeline position.
- Schema changes (`declared_shape.operation`, protocols `amqp`/`pulsar`, the
  binder migration, the §8 identity migration, §1c's service-level gRPC
  identity form in D01's identity table, the three new `open_questions` kinds
  with their candidates shapes and renderer/export switch arms, and §6's
  collision-detector interface/implementor exemption in D01's
  routing-ambiguity rule) each carry a D00/D01 amendment note and a migration
  line in the manifest discipline.
- **COVERAGE.md is a first-class deliverable of this phase, not an
  afterthought** — the spec defers to it a dozen times and gap B's whole point
  is the ratings it carries. Every task that ships a surface updates its rows
  in the same commit: the A-tier rows this phase closes (`@RabbitListener`,
  `@PulsarListener`, gRPC's Java rows, Actuator, `@Scheduled`, servlets,
  legacy `@SqsListener`, Spring Integration), the C-tier rows it closes
  (`@RepositoryRestResource`, `@ControllerAdvice`), the §5.7 gRPC section
  rewritten around what actually ships, and a NEW row for every boundary this
  spec states (published-stub jars, unannotated Spring gRPC on published
  stubs, bare `newBlockingStub`, `bindings=`, SpEL destinations, `@Selector`
  segments, `ResponseEntity` statuses, Integration DSL and its bean-wired
  destinations, AMQP producer↔consumer non-linking, the Framework-version
  scope of §8). The headline count is re-derived, never carried forward
  (2H/2I discipline), and `scripts/coverage_matrix.py --check` passes.
- **The golden churn is ONE audited pass, not three.** §3a's protocol
  migration, §7's format flips and §8's path canonicalization all change
  recorded output; they land in a single reviewed golden update whose diff is
  read line by line (2M's discipline), because three separate passes would let
  each hide in the others' noise.
- The final review re-runs the petclinic real-example validation both flavors,
  plus a gRPC-bearing example if present in `examples/`; byte-identity e2e
  extends to the two new tables' exports.
