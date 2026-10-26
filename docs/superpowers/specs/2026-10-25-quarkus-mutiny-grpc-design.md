# Quarkus's Mutiny gRPC forms, and a call a module makes to its own service — design

**Status: BUILT 2026-10-25** ("As built" below). Closes register item `quarkus-grpc-mutiny` (Plane SEXTANT-176)
and `OI-192` (SEXTANT-66), and moves COVERAGE §2c's Quarkus gRPC cell from `◐` to `✅`, which
makes Quarkus's row read `✅` everywhere it is scored — both in the commit after this branch's
CI run (As built). Until then the cell reads `◐ (1 open)`.

## 1. The rulings (2026-10-25)

| # | Question | Ruling |
|---|---|---|
| 1 | Does a module that serves a gRPC service get an outbound row when it calls that same service? | **No.** The user: *"A service that calls its inbound endpoints is not an outbound call. It's just a call hop that's traceable."* One rule for every framework: no outbound row for a service the module serves, whichever form serves it and whichever form calls it. |
| 2 | Is the hop built here, or logged? | **Built here.** A call from a gRPC client stub to a service the module serves continues, in the trace, to that RPC's handler. |
| 3 | W27 (F5 §6.1, `self_exchange.py`) files a question, not a rule, when a module serves and calls one HTTP/SOAP/messaging identity, because the far end may be another deployment. How does ruling 1 meet it? | **C — a hop by default; an outbound row where the call names an address that is not this module.** Built for gRPC only, here. A gRPC client's configured address is not read until OI-186 (SEXTANT-48), so today every gRPC self-call is a hop; when OI-186 lands, a configured address naming another host keeps the row outbound. W27's protocols are re-checked under this rule as their own item. |
| 4 | Can a person correct the pairing? | **Yes, through curation (FR-16, D03 §3).** Curation is designed and unbuilt (phase L, with M06). This spec records the self case in D03 and keeps the hop addressable so a curation can name it; building curation is its own item. |

**My calls**, for review:
- Quarkus's own wiring is mirrored as catalog data (DR-6, "framework knowledge is data"), from
  its build code measured in §2b. Nothing names a generated class by its suffix.
- One framework-neutral step finds an identity that a generated wrapper class does not state
  itself (§3a). It is used only on types an engine already has gRPC evidence for.

## 2. Measured first

### 2a. What Quarkus generates

From `quarkus-quickstarts` @ `81a5844`, `grpc-plain-text-quickstart`, `javap` over
`target/classes`. For `service Greeter` in proto package `helloworld`, the Java package is
`examples`:

| Class | Shape | Where the identity is |
|---|---|---|
| `GreeterGrpc` | grpc-java's own generated class | **here**: `ServiceDescriptor.newBuilder("helloworld.Greeter")`, `generateFullMethodName(SERVICE_NAME, "SayHello")` |
| `Greeter` | `interface … extends io.quarkus.grpc.MutinyService`; `Uni<HelloReply> sayHello(HelloRequest)` | none |
| `GreeterClient` | `implements Greeter, io.quarkus.grpc.MutinyClient<MutinyGreeterGrpc$MutinyGreeterStub>`; calls `MutinyGreeterGrpc.newMutinyStub`, and `sayHello` calls `MutinyGreeterStub#sayHello` | none |
| `GreeterBean` | `extends MutinyGreeterGrpc$GreeterImplBase implements BindableService, io.quarkus.grpc.MutinyBean`; field `delegate` of type `Greeter`; `sayHello` calls `delegate.sayHello`. No annotations | none |
| `MutinyGreeterGrpc$GreeterImplBase` | `implements io.grpc.BindableService`; `bindService` calls `GreeterGrpc.getServiceDescriptor()` and `GreeterGrpc.getSayHelloMethod()` | **delegated** to `GreeterGrpc` |
| `MutinyGreeterGrpc$MutinyGreeterStub` | `extends io.grpc.stub.AbstractStub implements io.quarkus.grpc.MutinyStub`; its constructor calls `GreeterGrpc.newStub`, and `sayHello` reaches `GreeterGrpc$GreeterStub#sayHello` by a method reference | **delegated** to `GreeterGrpc` |

User code, in both quickstarts: `@GrpcService public class HelloWorldService implements Greeter`
and a REST resource holding `@GrpcClient("hello") GreeterGrpc.GreeterBlockingStub` and
`@GrpcClient("hello") Greeter`. **Both quickstarts call the service they serve.**

### 2b. What Quarkus itself does

From `io.quarkus:quarkus-grpc-deployment:3.17.5`, `javap -c`. To be recorded as probe CP-53
with its `measured:` provenance:

- **Client (`GrpcClientProcessor.discoverInjectedClients`).** It maps each service interface to
  its client by taking every direct implementor of `io.quarkus.grpc.MutinyClient` and keying
  it by the other interfaces that class declares. An injection point's type is then
  classified by its own type closure: `AbstractBlockingStub` gives a blocking stub,
  `MutinyStub` a Mutiny stub, and `MutinyService` the mapped client class.
- **Server (`GrpcServerProcessor.processGeneratedBeans`).** For each direct implementor of
  `io.quarkus.grpc.MutinyBean`, it reads the field named `delegate`, takes its type, and finds
  that type's implementors that carry `io.quarkus.grpc.GrpcService`. The bean is served as
  delegating to such a class. A bean with no such implementor is not served.
- CP-52 row 7 (already recorded): every Quarkus service bean must carry `@GrpcService`, or the
  build fails.

### 2c. What Sextant derives today, and what a trace reaches

Same module (all measured):

| Written | Today |
|---|---|
| `@GrpcClient GreeterGrpc.GreeterBlockingStub` | outbound `helloworld.Greeter`, resolved |
| `@GrpcClient Greeter` | outbound `examples/Greeter#`, unresolved, plus a `service_identity` question |
| `@GrpcService HelloWorldService implements Greeter` | inbound `helloworld.Greeter/SayHello` from the `.proto` alone, handler NULL, plus a `service_identity` question |
| `@GrpcClient MutinyGreeterGrpc.MutinyGreeterStub` (no quickstart writes one) | nothing: `GreeterBean`'s extends edge fences `MutinyGreeterGrpc` |

Traces from the two REST methods (`call_edges`):
- `helloBlocking` → `GreeterBlockingStub#sayHello` → `GreeterGrpc#getSayHelloMethod`, then
  `io.grpc.stub.ClientCalls#blockingUnaryCall`, a boundary. The trace never reaches
  `HelloWorldService#sayHello`.
- `helloMutiny` → `Greeter#sayHello`, narrowed to two bodies: `GreeterClient#sayHello` and
  `HelloWorldService#sayHello`. The first continues to `MutinyGreeterStub#sayHello` → (dynamic)
  `GreeterStub#sayHello` → `ClientCalls#asyncUnaryCall`, a boundary.

`type_hierarchy` carries library supertypes too (`GreeterBlockingStub → AbstractBlockingStub →
AbstractStub`, `scanned: false`), so "is a gRPC client stub" is readable from stored facts.

## 3. What changes

### 3a. A wrapper's identity is the identity it delegates to (framework-neutral)

`shapes/identity_calls.py` gains one rule:

- **The rule.** The identity of an outer class that makes no marker call is the identity of
  the single marked outer class that its nest's own code calls into, directly or through
  other unmarked nests.
  - "Its nest" means the class and every class nested in it, by the nest hosts the facts
    state (`nest_hosts`).
  - "Calls into" means any call site whose target's owner is in that nest.
- **Two marked classes reached means no identity.** Nothing is guessed: the same refusal
  `_correlated` makes.
- **Termination:** a visited set, so a cycle ends the walk.
- **Wire names delegate with the identity.** A delegating ImplBase's RPCs are the marked
  class's `generateFullMethodName` names.

Where it is used, and nowhere else:
- `injected_client`: the identity of an injected type that is already a `@GrpcClient` point.
- `supertype_derived`: the gate and the identity of a supertype that implements
  `io.grpc.BindableService`, as catalog data, `service_supertype: io.grpc.BindableService`,
  a grpc-java API type. *Amended 2026-10-25 (plan ruling):* the key is declared by
  `grpc-quarkus.yml`, together with `served_by_annotation`, and not by `grpc-java.yml`, which
  is unchanged. So reactor-grpc-style wrappers do not come along for free (below); each would
  need a catalog of its own.
  - The BindableService condition is what stops a user base class that merely calls
    `GreeterGrpc.newBlockingStub` from becoming a "service" (the C-1 gate's reason, kept).
  - A marked supertype does not need it, so today's matches are unchanged.

This covers `MutinyGreeterGrpc$GreeterImplBase` and `MutinyGreeterStub`. It also covers a
user's `@GrpcService class X extends MutinyGreeterGrpc.GreeterImplBase`, the fourth Quarkus
form, which nothing reads today. Wrapper generators with the same shape (reactor-grpc's
`Reactor<Service>Grpc`) would be read by the same rule, given a catalog that declares
`service_supertype` (amended above); no corpus here carries one.

### 3b. Quarkus's wiring, as catalog data

`grpc-quarkus-client.yml` gains Quarkus's client rule:
```yaml
  interface_client:
    implements: io.quarkus.grpc.MutinyClient
```
An injected type that is an interface is answered by the module class that implements both it
and `MutinyClient` (§2b). Its identity is that class's, by §3a. More than one such class means
no identity, giving today's unresolved row plus question.

A Quarkus inbound catalog (`grpc-quarkus.yml`, style `supertype_derived`, detected by
`io.quarkus:quarkus-grpc`) carries the server rule:
```yaml
  served_by_annotation: io.quarkus.grpc.GrpcService
  delegating_bean:
    implements: io.quarkus.grpc.MutinyBean
    delegate_field: delegate
```
- **Who is served.** For each module class B implementing `MutinyBean`, take its `delegate`
  field's type I. Every module class C that implements I and carries `@GrpcService` is
  served.
- **Identity and handlers.** The identity and wire names are those of B's supertype (§3a). The
  handlers are C's public methods that I declares, correlated to wire names exactly as
  `overridden_public_methods` correlates them today (decapitalized lookup; ambiguity refused;
  uncorrelated methods filed as a gap).
- **B itself is never a handler and never a fence.** *As built (plan ruling):* there is no skip
  list. `grpc-java.yml` does not delegate, and `grpc-quarkus.yml` requires
  `served_by_annotation` on the class itself, which the generated bean never carries. The
  fence gets the same key (Task 4).

*Amended 2026-10-25 by CP-53* (`scripts/probes/cp53_quarkus_mutiny_wiring.md`), mirroring
Quarkus exactly:
- **The client map** keys an implementor by its FIRST declared interface other than
  `MutinyClient`.
- **The delegate form applies only when** the bean's superclass has exactly one subclass in
  the module, and no module class extends a class nested in the marked outer the bean's base
  delegates to. That is Quarkus's own gate, stated structurally rather than by its "name with
  `Mutiny` removed".
- **`served_by_annotation` must be declared on the class itself.**
- **Two or more such classes for one delegate interface:** Quarkus picks one in index order,
  which cannot be derived. So neither is a handler: the unresolved row is written (the
  engine's existing ambiguity precedent), with one question naming both.

### 3c. The fence is by service: a module that serves S gets no outbound row for S

The rule is ruling 1, as ruling 3 bounds it. "Serves" means one of two things, and either
blocks the outbound row:
- some class of this module is the handler of S's inbound row, by any catalog: grpc-java's
  extends form, §3a's delegating base, or §3b's delegate form;
- or, as today, a module class extends a class nested in the stub type's outer class. This is
  the symbol rule, kept so the existing fence tests keep their expectations, and so are an
  implementer that overrides nothing and one whose identity is unreadable.

**Ruling 3's exception:** a client whose row carries a peer, an address read from
configuration, that is not this module keeps its outbound row. No gRPC catalog reads a peer
today (OI-186), so the exception is written and tested on a row built with a peer, and it is
inert on real input until OI-186.
- **A descriptor-only inbound row does not count.** A `.proto` row from `grpc-schema` with
  handler NULL serves nothing: a client module compiles the `.proto` too.
- **Where the stub's identity is unreadable,** today's symbol rule stands: an extends edge by a
  module class into the stub's outer class, not counting edges nested inside one outer class
  (OI-191's fix). A `MutinyBean` implementer is not counted, for the reason in §3b.

Consequences:
- Quarkus's generated `GreeterBean` no longer fences anything. In a client-only Quarkus module,
  a `@GrpcClient MutinyGreeterStub` resolves to `helloworld.Greeter`.
- In both quickstarts, every gRPC client row goes, including the blocking-stub row that
  resolves today. They serve `helloworld.Greeter`.
- The existing fence tests in `tests/application/test_injected_client.py` keep their
  expectations. Their implementers extend the generated base, which still serves.

### 3d. The hop: a stub call to a served RPC continues to its handler

A new derived table, `rpc_hops (caller, ordinal, protocol, path, handler, evidence)`, written
after `call_edges` and the endpoint pass, reset whole per resolve:

- **`caller`** is a method of a class whose `type_hierarchy` reaches `io.grpc.stub.AbstractStub`.
  New catalog data in `grpc-java.yml`: `client_stub_supertype: io.grpc.stub.AbstractStub`.
- **The wire method** is the one this method reaches by calling a method of the marked outer
  class whose own body makes the `method_name_call` (`GreeterBlockingStub#sayHello` calls
  `GreeterGrpc#getSayHelloMethod`, whose body names `SayHello`). Exactly one, or no row.
- **`ordinal`** is the call site in `caller` whose target's owner is the client-call API, where
  the call leaves for the wire. New catalog data: `client_call_owner: io.grpc.stub.ClientCalls`.
  None means no row.
- **`path`** is `<identity>/<wire method>`, and **`handler`** is that inbound row's handler.
  - Rows are written only for a service the module serves (§3c). A call to a service it does
    not serve keeps its outbound row and gets no hop.
  - For a served service, an RPC with no handler here still gets a row, with `handler` NULL.
    The trace then stops at the boundary but carries the wire path, so the call is not lost
    when the outbound row is fenced.
  - A path with several handlers gives one row per handler, as a narrowed call gives several
    candidates.
- **`evidence`** is `compiler` (D00 §4's closed set). That is the convention endpoint rows
  already follow: a catalog's rule over compiled facts. `call_edges` itself is untouched; the
  hop lives in its own table.
- **The table is what a curation names** (ruling 4): the pair (this call, this module's
  handler) is addressable by module and wire path, though the outbound row is fenced.

The trace walk (`application/query/trace.py`) reads `rpc_hops`. At a step whose `(caller,
ordinal)` has a row, it expands into `handler` instead of stopping at `boundary`. The step
carries the wire path (a new `Step` field, e.g. `via`), so a reader sees both the call into
`ClientCalls` and where it arrives. The step is no longer a terminal, so the trace's terminal
count drops by one. The sequence diagram draws the arrow to the handler's lifeline, labelled
with the wire path. The step table says the same in words.

Measured consequence on `grpc-plain-text-quickstart`:
- **Blocking path:** `helloBlocking` reaches `HelloWorldService#sayHello` through
  `GreeterBlockingStub#sayHello`.
- **Mutiny path:** `helloMutiny`'s `GreeterClient` branch reaches it through `MutinyGreeterStub`
  and `GreeterStub`.
- **The narrowed call stays narrowed.** `Greeter#sayHello` still lists both bodies, and both
  now end at the handler. Narrowing an injected field to the bean Quarkus injects is not done
  here (§4).

### 3e. Versions, exits, docs

- `GRAPH_SCHEMA_VERSION` 7 → 8 (a new derived table). D01 gains the table and its row in "What
  moved `graph_schema_version`". The trace section gains the hop.
- `rpc_hops` is exported (the export ratchet). Its columns are symbols and a wire path, nothing
  masked. The builder confirms against D06's rule for `path`-shaped columns.
- `FACT_SCHEMA_VERSION`, `BOUNDARY_VOCABULARY_VERSION` and `SEXTANT_VERSION` do not move. The
  boundary diff sees fewer outbound rows on a self-calling module, which is a content change,
  not a vocabulary one.
- CP-53: the probe of §2b, as `scripts/probes/cp53_quarkus_mutiny_wiring.md`, cited in both
  Quarkus catalogs' `measured:` blocks.
- D03 §3 records the self case (done in this spec's commit): a person may assert that a call
  is to this module's own endpoint, or delete a hop because the call goes elsewhere, and it
  names the pair by module and wire path. D03 §8 carries the open syntax decision.

### 3f. Fixture

`fixtures/orders-quarkus` gains hand-written stand-ins of the §2a shapes for a second service,
in the style `HelloGrpc.java` already uses. For example `acme.quotes.Quotes`: `QuotesGrpc`,
`Quotes`, `QuotesClient`, `QuotesBean`, `MutinyQuotesGrpc` with its ImplBase and stub. Plus:
- `@GrpcService QuotesService implements Quotes`: the Mutiny server form;
- a REST method calling Quotes through `@GrpcClient Quotes`, and one through
  `@GrpcClient QuotesGrpc.QuotesBlockingStub`: self-calls, so hops and no outbound rows;
- a REST method calling the existing `HelloService` through `HelloGrpc.HelloBlockingStub`:
  the grpc-java self-call hop;
- `@GrpcClient MutinyPricingGrpc.MutinyPricingStub` and `@GrpcClient Pricing` for the
  not-served `Pricing` service (stand-ins `MutinyPricingGrpc`, `Pricing` and its generated
  client beside the existing `PricingGrpc`): outbound `acme.pricing.Pricing`, resolved. The
  fixture already has a user class `hello/PricingClient.java`, which is the generated client's
  name. So the generated Pricing classes go in their own package, as protoc would place them
  in the proto's `java_package`, and the existing `PricingGrpc` moves with them if it must;
- `@GrpcService QuotesLegacy extends MutinyQuotesGrpc.QuotesImplBase` is **not** added. One
  service with two implementations fails a Quarkus build. The fourth form is pinned in a unit
  test of `supertype_derived` instead.

Rebuilt with JDK 21. Re-pin any count the new classes move.

## 4. What it does NOT do

- **Narrowing an injected interface call to the bean the framework injects.** `Greeter#sayHello`
  through an `@GrpcClient Greeter` field stays narrowed to every implementor. Logged as OI-196:
  it needs the field's receiver on the call site, which `call_edges` does not carry.
- **Curation** (FR-15, FR-16, M01, D03): designed, unbuilt, phase L. Logged as OI-197 with the
  self case as part of what it must do.
- **W27's protocols under ruling 3.** HTTP, SOAP and messaging keep their `self_exchange`
  question. Logged as OI-198.
- **The client's configured address as its peer** (OI-186, SEXTANT-48) is unchanged.
- **A hop across modules.** A stub call to a service another module of the system serves is
  the linking tier's (GAP-2), not this.
- **Streaming forms** (`Multi`, client and bidi streaming). They reach the same `ClientCalls`
  family. Each hop row is pinned only where a test exercises it; the builder decides whether
  the fixture's unary RPCs are enough, and logs the rest.

## 5. Cost (§8.7)

- **§3a:** one pass over `parsed_call_sites`, already read by both engines; a dictionary walk
  per unmarked nest.
- **§3d:** one read of `call_edges` filtered in SQL to callers in stub classes, one read of
  `endpoints` (inbound gRPC), one read of `type_hierarchy`. Rows written: stub methods ×
  served handlers, a handful per module.
- **The trace walk:** one more index read, shared across `traces_of`.

## 6. Verify what it closes

- Re-measure both quickstarts after the build, and record the table in this spec under "As
  built". Expected:
  - inbound `helloworld.Greeter/SayHello` with handler `HelloWorldService#sayHello` and no
    `service_identity` question;
  - no gRPC outbound row;
  - both REST traces reaching the handler.
- `tests/e2e/test_grpc_quarkus_delivered.py` pins the fixture's forms (§3f).
- COVERAGE §5.7's Mutiny row moves to ✅ shipped. After this branch's CI run, the delivery
  list's `quarkus-grpc-mutiny` moves to the `closed` block with its test and that run, and §2c
  is regenerated with `scripts/coverage_matrix.py`, the Quarkus gRPC cell reading `✅` (As
  built).
- In Plane, SEXTANT-176 and SEXTANT-66 move to Done with the PR. OI-196, OI-197 and OI-198
  (§4) were created with this spec.
- `scripts/field_check.py`: six `ok`. No pinned corpus has gRPC self-calls, so this is to be
  confirmed, not assumed.

## As built — measured on quarkus-quickstarts

`quarkusio/quarkus-quickstarts` @ `81a5844` (Quarkus 3.40.1.1), the two gRPC modules as built for
the 2026-10-24 spec, each analysed with `sextant module analyze` and `render` after Task 8:

| | `grpc-plain-text-quickstart` | `grpc-tls-quickstart` |
|---|---|---|
| inbound gRPC | `helloworld.Greeter/SayHello`, handler `HelloWorldService#sayHello`, resolved (`grpc-quarkus`) | `helloworld.Greeter/SayHello`, handler `HelloWorldTlsService#sayHello`, resolved (`grpc-quarkus`) |
| open questions | none | none |
| gRPC outbound rows | none | none |
| `rpc_hops` | 4: `GreeterBlockingStub`, `GreeterBlockingV2Stub`, `GreeterFutureStub`, `GreeterStub` `#sayHello` → the handler | the same 4 → the handler |
| `GET /hello/blocking/{name}` | one hop step, `via grpc helloworld.Greeter/SayHello` → `HelloWorldService#sayHello`, expanded (92 steps, 50 terminals) | the same → `HelloWorldTlsService#sayHello` (82 steps, 46 terminals) |
| `GET /hello/mutiny/{name}` | one hop step through `GreeterClient` → `MutinyGreeterStub` → `GreeterStub`, → `HelloWorldService#sayHello`, expanded (101 steps, 55 terminals) | the same → `HelloWorldTlsService#sayHello` (90 steps, 51 terminals) |
| document arrows | `blockingUnaryCall (declared ClientCalls) via grpc helloworld.Greeter/SayHello`, `asyncUnaryCall (declared ClientCalls) via grpc helloworld.Greeter/SayHello` | the same |
| `reachability` rows | 181 | 165 |

That is §6's expectation on both modules. `Greeter#sayHello` stays narrowed to its two bodies
(§4, OI-196): the `HelloWorldService` branch is `revisited`, having been reached through the hop
first.

`fixtures/orders-quarkus` (§3f) carries the stand-ins as specified, with three choices made in
building them:
- **`PricingGrpc` moved** from `hello/` to `pricing/`, beside `MutinyPricingGrpc`, `Pricing`, the
  generated `PricingClient` and `PricingBean`. It had to: the Mutiny stub's constructor calls the
  delegate stub's protected `build`, which compiles only from the same package, as protoc places
  them. `PricingBean` is kept because Quarkus's generator emits a bean for every service of a
  compiled `.proto`; it serves nothing and fences nothing.
- **`quarkus-grpc-stubs` 3.40.1.1** is the one dependency not at the BOM's 3.17.5: the Mutiny
  stand-ins call its `ClientCalls.oneToOne`/`ServerCalls.oneToOne` as the measured generated
  classes do, and that is the version those classes were generated against.
- Each Mutiny `Pricing` client form was also checked on its own (a scratch copy with the other
  forms removed): each resolves `acme.pricing.Pricing` with no question. The e2e pin sees one
  deduplicated row.

**Deviations from §3, each ruled during the build:**
- **`service_supertype` is per catalog** (plan ruling, §3a's amendment): `grpc-quarkus.yml`
  declares it with `served_by_annotation`, and `grpc-java.yml` is unchanged. The generated bean
  is excluded because it carries no `@GrpcService`, not by a skip list (§3b).
- **CP-53's gates** (§3b's amendment): the client map keys an implementor by its first other
  interface; the delegate form applies only when the bean's superclass has exactly one subclass
  in the module and no module class extends a class nested in the delegated outer; two
  `@GrpcService` implementors of one delegate interface leave both unjoined, with one question.
- **`rpc_hops.path` is masked on export** through the address map, as `roots.path` is (D06 §3),
  against §3e's "nothing masked": it carries `endpoints.path`'s value. The document masks the
  same path in a hop's arrow label and `Reaches` cell with the render redactor, as it masks a
  root's path.
- **The register close lands after CI** (controller ruling, "done means green in CI"):
  this branch leaves COVERAGE §2c's Quarkus gRPC cell at `◐ (1 open)`, `quarkus-grpc-mutiny`
  in the delivery list's open block and OI-192 open. The commit after this branch's CI run
  moves the item to `closed` with that run, marks OI-192 closed and regenerates the cell to
  `✅`.

**Stated boundaries found during the build**, each logged:
- `OI-199` — a delegated identity is read only where the marker call sits on the outer class.
- `OI-200` — a `MutinyBean` implementor with no `delegate` field is skipped without a question.
- `OI-201` — a gRPC identity that is contended, not unreadable, still files the "SERVICE_NAME
  unreadable" question.
- `OI-202` — a gRPC service reaching the generated `ImplBase` through an intermediate class is
  not named as its RPC's handler (grpc-java's extends form, before this branch). Real input
  can do this: an abstract base class between the service and the generated base.
