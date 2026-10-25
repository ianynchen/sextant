# Quarkus Mutiny gRPC and the self-call hop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quarkus's Mutiny gRPC forms resolve to their service identity. A module calling a gRPC service it serves gets no outbound row, and instead gets a traceable hop from the stub call to its own handler.

**Architecture:**
- **Identity:** one framework-neutral helper finds the identity a generated wrapper class delegates to.
- **Quarkus's wiring:** catalog data the two existing engines read, `supertype_derived` and `injected_client`.
- **The fence:** a post-merge pass drops an outbound gRPC row whose service the module handles.
- **The hop:** a new derived table, `rpc_hops`, which the trace walk follows from a stub's client-call site to the handler.

**Tech Stack:** Python 3.13, DuckDB, pytest; Java fixtures built with JDK 21.

**Spec:** `docs/superpowers/specs/2026-10-25-quarkus-mutiny-grpc-design.md`

## Global Constraints

- **Gate:** `PATH=/Users/yining/programming/ai/sextant/.venv/bin:$PATH JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh`. Fixtures are built with JDK 21, never 27.
- **Framework knowledge is catalog data** with a `measured:` probe. No engine names `io.quarkus.*`, and `grpc-java.yml` names no Quarkus type. No rule matches a generated class by name suffix.
- **Versions:** `GRAPH_SCHEMA_VERSION` 7 → 8 (one new derived table, `rpc_hops`). `FACT_SCHEMA_VERSION`, `BOUNDARY_VOCABULARY_VERSION` and `SEXTANT_VERSION` do not move.
- **`evidence` values** come from D00 §4's closed set; `rpc_hops.evidence` is `compiler`. `call_edges` is not modified.
- **Guards:** every new rule gets a guard in `scripts/guard_check.py`, measured killed. A pinned test whose expectation changes is re-pinned, never deleted. The existing fence tests in `tests/application/test_injected_client.py` keep their expectations unchanged.
- **Exits:** every exit masks. `rpc_hops` is exported; check its `path` against D06's rule for path-shaped columns.
- **Issues** are tracked in Plane (project SEXTANT). The next OI id is OI-199. A newly found issue goes to Plane and gets a row in `docs/open-issues.md`'s id map; no body is written into the file.
- **Commit trailer:** `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Plan-level ruling.** Only a catalog that declares `service_supertype` enables §3a's delegation in `supertype_derived`. The new `grpc-quarkus.yml` declares it together with `served_by_annotation: io.quarkus.grpc.GrpcService`; `grpc-java.yml` does not declare it and its behaviour does not change.
- **Why:** this keeps `grpc-java.yml` free of Quarkus types without a skip list across catalogs. Quarkus's own rule (CP-52 row 7: every served bean carries `@GrpcService`) excludes the generated `GreeterBean`, which carries no annotations.
- **Cost if wrong:** reactor-grpc wrappers are not read for free; they would need their own catalog. No corpus carries one.

## Review Focus

- **Two candidates where one is expected.** A wrapper nest whose code reaches TWO marked outer classes, for example a hand-written facade calling two services' stubs, gets no identity. It must not take the first one (Task 2).
- **A client-only Quarkus module.** The generated `<Service>Bean` exists but no `@GrpcService` class implements its delegate. The service is not served, the Mutiny stub client resolves, and no hop is written (Tasks 3, 4, 6).
- **A served client row that names an address:** it stays outbound when the address is not loopback, and is dropped when the peer is NULL or loopback (Task 5).
- **A stub method naming two wire methods.** One that calls two descriptor accessors gets no hop row; picking one would be wrong (Task 6).
- **A cycle among unmarked nests** (A calls B, B calls A) terminates with no identity (Task 2).

---

### Task 1: CP-53 — Quarkus's Mutiny wiring, measured

**Files:**
- Create: `scripts/probes/cp53_quarkus_mutiny_wiring/{probe.py,run.sh}` and `scripts/probes/cp53_quarkus_mutiny_wiring.md`, following `scripts/probes/cp52_quarkus_grpc_annotations/`'s layout, version rule and generated-table convention.

**Interfaces:**
- Produces: the probe record that Tasks 3 and 4 cite in their catalogs' `measured:` blocks, as `{ artifact: io.quarkus:quarkus-grpc-deployment, versions: ["3.17.5"], identity: reported, by: scripts/probes/cp53_quarkus_mutiny_wiring.md }`, plus `io.quarkus:quarkus-grpc-api` for the marker types.

- [ ] **Step 1:** Write `probe.py`. It reads, from the local Maven repository's `quarkus-grpc-deployment` and `quarkus-grpc-api` 3.17.5 jars (versions read from each jar's MANIFEST, as CP-52 does), using `javap -c -p`, and prints one table row per observation:
  - (a) `GrpcClientProcessor.discoverInjectedClients` reads `GrpcDotNames.MUTINY_CLIENT`'s direct implementors and their `interfaceNames`;
  - (b) the injection point is classified by `ABSTRACT_BLOCKING_STUB`, `MUTINY_STUB`, `MUTINY_SERVICE` in its type closure;
  - (c) `GrpcServerProcessor.processGeneratedBeans` reads `MUTINY_BEAN`'s direct implementors, their field named `delegate`, that field's type's implementors, and `GRPC_SERVICE` on each;
  - (d) `io.quarkus.grpc.{MutinyService, MutinyClient, MutinyBean, MutinyStub}` exist in `quarkus-grpc-api`.
- [ ] **Step 2:** Run `bash scripts/probes/cp53_quarkus_mutiny_wiring/run.sh` and paste its output into the `.md`'s Observations, with the version header. Write each verdict (a)–(d), and the spec §2b sentence it supports.
- [ ] **Step 3:** Run `pytest tests/architecture/test_probe_provenance.py -q`. Expected: PASS.
- [ ] **Step 4:** Commit `probe(cp53): Quarkus's Mutiny client and delegating-bean wiring, measured`.

### Task 2: A wrapper's identity is the one it delegates to

**Files:**
- Modify: `src/sextant/application/resolve/shapes/identity_calls.py`
- Test: `tests/application/test_identity_calls.py` (create if absent; find with `ls tests/application | grep identity`)

**Interfaces:**
- Consumes: `parsed_call_sites`, `caller_outer_class`, `outer_of`, `nest_hosts` (existing).
- Produces: `delegated_outers(call_sites: list[dict[str, Any]], marked: set[str], hosts: dict[str, str]) -> dict[str, str]`. It maps each UNMARKED outer class whose nest's code reaches exactly one marked outer class to that marked outer class.
  - "Reaches" means: a call site whose `caller_outer_class` is the unmarked outer, and whose target `owner`'s `outer_of` is another outer, followed transitively through unmarked outers.
  - Outers are bare descriptors, as `calling_classes` returns them.
  - An outer that reaches zero or more than one marked outer is absent.

- [ ] **Step 1: Write failing tests**:
  - `test_a_wrapper_calling_one_marked_class_takes_its_identity`: `MutinyGreeterGrpc$GreeterImplBase#bindService()` calls `GreeterGrpc#getServiceDescriptor()`, and `GreeterGrpc` is marked → `{"…/MutinyGreeterGrpc#": "…/GreeterGrpc#"}`.
  - `test_delegation_follows_an_unmarked_nest_to_a_marked_one`: `GreeterClient#sayHello` calls `MutinyGreeterGrpc$MutinyGreeterStub#sayHello`, which calls `GreeterGrpc#newStub` → `GreeterClient#` and `MutinyGreeterGrpc#` both map to `GreeterGrpc#`.
  - `test_two_marked_classes_reached_is_no_identity`: a facade calling `AGrpc#newBlockingStub` and `BGrpc#newBlockingStub` → absent.
  - `test_a_cycle_among_unmarked_nests_terminates`: A→B→A, nothing marked → `{}`.
  - `test_a_marked_class_is_never_remapped`: a marked outer that also calls another marked outer is absent from the result.
- [ ] **Step 2:** Run `pytest tests/application/test_identity_calls.py -q`. Expected: FAIL (`delegated_outers` undefined).
- [ ] **Step 3:** Implement. Build the outer→outer call graph once, then do a visited-set walk from each unmarked outer.
- [ ] **Step 4:** Run the new tests, and also `tests/application/test_supertype_derived.py` and `tests/application/test_injected_client.py`. Expected: all PASS, with no expectation edited.
- [ ] **Step 5: Guard** `grpc.a-WRAPPER-takes-the-one-identity-it-delegates-to`. The edit: return the first marked outer reached instead of refusing on two. Pin it and measure: killed.
- [ ] **Step 6:** Commit `feat(grpc): a generated wrapper's identity is the one marked class it delegates to`.

### Task 3: Quarkus's service forms — `supertype_derived` gains `service_supertype` and `delegating_bean`

**Files:**
- Modify: `src/sextant/application/resolve/engines/supertype_derived.py`
- Create: `src/sextant/catalogs/grpc-quarkus.yml`
- Modify: `docs/components/D02-catalog-schema.md` (§`supertype_derived`: the three new optional keys)
- Test: `tests/application/test_supertype_derived.py`

**Interfaces:**
- Consumes: `delegated_outers` (Task 2).
- Produces: three optional `matches` keys on `supertype_derived` catalogs.
  - `service_supertype: <fqn>`: when present, a supertype whose outer is unmarked still matches if `type_hierarchy` shows it implementing `<fqn>` (directly or through ancestors) AND `delegated_outers` maps its outer. Identity and wire names come from the delegated outer.
  - `served_by_annotation: <fqn>`: when present, an implementer must carry that class annotation to match.
  - `delegating_bean: {implements: <fqn>, delegate_field: <name>}`: for each module class B implementing `implements`, read the declared type I of B's field named `delegate_field`. Every module class C that implements I (and carries `served_by_annotation` when set) matches. Its identity and wire names are those of B's supertype (via `service_supertype` delegation). The candidate names are the methods I declares (`_inherited_names(I, …)`), and the correlation is `_correlated`, unchanged. B itself is never an implementer under this catalog.
- `grpc-quarkus.yml`:
  - top level: `style: supertype_derived`, `protocol: grpc`, `direction: inbound`, `detect.coordinates: ["io.quarkus:quarkus-grpc"]`, `measured:` CP-53 + CP-52, `requires: [call_site, string_constants, superclass, annotation_args, typed_signatures]`;
  - `matches`: the same `supertype_marker` and `members` as `grpc-java.yml`, plus `service_supertype: io.grpc.BindableService`, `served_by_annotation: io.quarkus.grpc.GrpcService`, `delegating_bean: {implements: io.quarkus.grpc.MutinyBean, delegate_field: delegate}`. Comments in the file's house style, citing the spec and CP-53.

- [ ] **Step 1: Write failing tests**, with facts built the way the file's existing tests build them, mirroring §2a's shapes:
  - `test_a_quarkus_service_implementing_the_mutiny_interface_is_its_rpcs_handler`: `@GrpcService HelloWorldService implements Greeter`; `GreeterBean implements MutinyBean extends MutinyGreeterGrpc$GreeterImplBase` with field `delegate: Greeter`; the Mutiny ImplBase implements `io.grpc.BindableService` and calls `GreeterGrpc#getServiceDescriptor`; `GreeterGrpc` makes the two marker calls (`"helloworld.Greeter"`, `"SayHello"`) → one inbound row, `path` `helloworld.Greeter/SayHello`, `handler` `HelloWorldService#sayHello(…)`, resolved.
  - `test_the_generated_bean_is_never_a_handler`: the same facts → no row whose handler is on `GreeterBean`.
  - `test_a_bean_with_no_annotated_implementor_serves_nothing`: drop `@GrpcService` from `HelloWorldService` → no rows, no gaps.
  - `test_a_quarkus_service_extending_the_mutiny_base_directly_is_served`: `@GrpcService X extends MutinyGreeterGrpc$GreeterImplBase` overriding `sayHello` → row with handler `X#sayHello`. This is the fourth form.
  - `test_grpc_java_catalog_does_not_delegate`: the same facts under `grpc-java.yml`'s matches (no `service_supertype`) → no Mutiny-form rows. Its existing rows are unchanged.
  - `test_a_delegating_base_reaching_two_services_is_no_match`: the ImplBase calls into two marked outers → no row, no gap.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. The new keys are optional, and `_validate_matches` checks their shape when present, in the `_validate_call` style. Write the catalog and the D02 rows.
- [ ] **Step 4:** Run `pytest tests/application/test_supertype_derived.py tests/application/test_service_identity*.py -q`, then the full gate. Expected: PASS. Every catalog-count pin moves by one (`tests/architecture/test_shipped_counts.py` and anything it names); re-pin them.
- [ ] **Step 5: Guards:**
  - `grpc.a-QUARKUS-service-implementing-its-interface-is-the-handler`, edit: skip `delegating_bean`;
  - `grpc.the-GENERATED-bean-is-never-a-handler`, edit: let B match as an implementer.
  Pin and measure both: killed.
- [ ] **Step 6:** Commit `feat(quarkus): a @GrpcService implementing the Mutiny interface is its RPCs' handler`.

### Task 4: Quarkus's client forms — `injected_client` gains delegation, `interface_client`, `served_by_annotation`

**Files:**
- Modify: `src/sextant/application/resolve/engines/injected_client.py`, `src/sextant/catalogs/grpc-quarkus-client.yml`, `docs/components/D02-catalog-schema.md` (§`injected_client`)
- Test: `tests/application/test_injected_client.py`

**Interfaces:**
- Consumes: `delegated_outers` (Task 2).
- Produces: `injected_client` behaviour changes in three places.
  - **Identity:** an injected type's identity is `service_names[outer]`, else `service_names[delegated_outers(...)[outer]]`.
  - **`interface_client: {implements: <fqn>}` (optional):** where the injected type is an interface, the type read is the single module class implementing both that interface and `<fqn>`. Two or more such classes means unresolved, with a question (today's fallback).
  - **`served_by_annotation: <fqn>` (optional):** in `_fenced_outer_classes`, an extends edge counts only when the subclass carries that annotation.
- `grpc-quarkus-client.yml` gains `interface_client: {implements: io.quarkus.grpc.MutinyClient}` and `served_by_annotation: io.quarkus.grpc.GrpcService`, with CP-53 in `measured:`.

- [ ] **Step 1: Write failing tests:**
  - `test_a_client_typed_by_the_mutiny_interface_resolves_through_its_generated_client`: `@GrpcClient Greeter` with `GreeterClient implements Greeter, MutinyClient` reaching `GreeterGrpc` → outbound `helloworld.Greeter`, resolved.
  - `test_a_mutiny_stub_client_resolves_and_is_not_fenced_by_the_generated_bean`: `@GrpcClient MutinyGreeterGrpc$MutinyGreeterStub`, plus `GreeterBean extends MutinyGreeterGrpc$GreeterImplBase` with no annotation → outbound `helloworld.Greeter`, resolved.
  - `test_an_annotated_quarkus_implementer_still_fences`: `@GrpcService X extends GreeterGrpc$GreeterImplBase` → no row.
  - `test_two_mutiny_clients_for_one_interface_is_unresolved`: two `MutinyClient` implementors of `Greeter` → today's unresolved row and question.
  - The existing fence tests run under the net.devh catalog, unchanged.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Read the class annotations the way `annotation_driven` does, and the interface implementors from `implementations`.
- [ ] **Step 4:** Run `pytest tests/application/test_injected_client.py -q`, then the gate. Expected: PASS, with no existing expectation edited.
- [ ] **Step 5: Guards:**
  - `grpc.an-INTERFACE-client-resolves-through-the-generated-client`, edit: ignore `interface_client`;
  - `grpc.an-UNANNOTATED-generated-bean-does-not-fence`, edit: ignore `served_by_annotation`.
  Pin and measure both: killed.
- [ ] **Step 6:** Commit `feat(quarkus): Mutiny clients resolve to the service their generated classes delegate to`.

### Task 5: A served service gets no outbound row (rulings 1 and 3)

**Files:**
- Create: `src/sextant/application/resolve/self_calls.py`, and a named statement in `src/sextant/storage/duckdb/` that deletes the chosen `endpoints` rows (the `apply_protocol_hints` precedent for a pass that edits merged rows)
- Modify: `src/sextant/application/resolve/pipeline.py` (call it immediately after `derive_endpoints_with_runs`, before `record_service_identity_gaps`)
- Test: `tests/application/test_self_calls.py`

**Interfaces:**
- Produces: `record_self_calls(workspace: Workspace) -> None` and `served_services(workspace: Workspace) -> dict[str, set[str]]`.
  - `served_services` maps an `<identity>` to its served wire paths, from inbound `grpc` rows whose `handler` IS NOT NULL. Task 6 imports it.
  - `record_self_calls` deletes every outbound `grpc` row whose `path` is a key of `served_services` and whose `peer` is NULL or loopback.
- `_is_this_module(peer: str | None) -> bool`: True for `None`, and for a peer whose host (scheme and port stripped) is `localhost`, `127.0.0.1`, `::1`, `[::1]` or `0.0.0.0`. The module docstring says a configured name of the module itself is not recognized until OI-186 (SEXTANT-48).
- A module constant `_PROTOCOLS = ("grpc",)`, with a comment naming OI-198 for the rest.

- [ ] **Step 1: Write failing tests**, using workspaces with `endpoints` rows built as the self-exchange tests build them:
  - `test_a_client_of_a_service_this_module_handles_is_dropped`: inbound `helloworld.Greeter/SayHello` with a handler, plus outbound `helloworld.Greeter` with peer NULL → the outbound row is gone and the inbound row stays.
  - `test_a_descriptor_only_inbound_row_serves_nothing`: the same, with inbound handler NULL → the outbound row stays.
  - `test_a_client_naming_another_host_stays_outbound`: peer `pricing.internal:9000` → stays.
  - `test_a_loopback_peer_is_this_module`: peer `localhost:9000` → dropped.
  - `test_another_protocol_is_untouched`: an `http` pair sharing a path → both rows stay.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement, and wire it into the pipeline.
- [ ] **Step 4:** Run the new tests, `tests/application/test_self_exchange.py`, and the gate. Expected: PASS. Re-pin any vertical-slice count that moves; there should be none outside gRPC fixtures.
- [ ] **Step 5: Guards:**
  - `grpc.a-SELF-call-is-not-an-outbound-row`, edit: the pass drops nothing;
  - `grpc.a-call-naming-ANOTHER-host-stays-outbound`, edit: `_is_this_module` always returns True.
  Pin and measure both: killed.
- [ ] **Step 6:** Commit `feat(grpc): a call to a service this module serves is not an outbound row`.

### Task 6: `rpc_hops` — a stub call to a served RPC lands on its handler

**Files:**
- Create: `src/sextant/application/resolve/rpc_hops.py`
- Modify:
  - `src/sextant/storage/duckdb/schema.sql` (the table, with a comment in the file's style);
  - reset and insert SQL alongside the other derived tables;
  - `src/sextant/storage/duckdb/workspace.py` (`_NAMED_QUERIES["rpc_hops"]` ordered by `caller, ordinal, handler`; `_EXPORT_QUERIES["rpc_hops"]`);
  - `src/sextant/application/resolve/pipeline.py` (after `record_self_calls`);
  - `src/sextant/catalogs/grpc-java.yml` (`client_stub_supertype: io.grpc.stub.AbstractStub`, `client_call_owner: io.grpc.stub.ClientCalls`);
  - `src/sextant/domain/version.py` (`GRAPH_SCHEMA_VERSION = 8`, with the comment row);
  - `docs/components/D01-graph-schema.md` (the table, and the version row);
  - D06 (the export);
  - tests hard-coding schema version 7 (`grep -rn '"schema_version": 7\|schema_version=7\|this build is 7' tests`).
- Test: `tests/application/test_rpc_hops.py`, `tests/storage/test_workspace.py`

**Interfaces:**
- Consumes:
  - `served_services` (Task 5);
  - `call_edges`, `type_hierarchy`, `parsed_call_sites`;
  - `first_string_arguments` / `all_string_arguments`;
  - the catalog keys above, read from whichever declared catalog carries them. Several catalogs carrying them is a `CatalogError`.
- Produces: `record_rpc_hops(workspace: Workspace, catalogs: list[Catalog]) -> None` and the table `rpc_hops(caller VARCHAR, ordinal INTEGER, protocol VARCHAR, path VARCHAR, handler VARCHAR, evidence VARCHAR)`, where `caller` and `handler` are module-prefixed and `evidence` is `'compiler'`. One row is written per (stub method, handler); `handler` is NULL for an RPC of a served service that has no handler here.
- **The algorithm.** The spec §3d is binding; this states it once:
  - **Stub classes:** classes whose `type_hierarchy` ancestry, followed through `scanned: false` library rows, reaches `client_stub_supertype`.
  - **Stub methods:** for each caller method M in a stub class, take M's `call_edges` callees that lie in the nest of a marked outer O (marked = `calling_classes` of the `method_name_call`), and whose own call sites include that call with a string argument 1.
  - **Wire method:** exactly one such wire name W, else no row.
  - **Ordinal:** the first of M's `call_edges` rows whose `target` owner is `client_call_owner`; none means no row.
  - **Path:** `"<service_names[O]>/<W>"`.
  - **Rows:** if `<service_names[O]>` is in `served_services`, one row per inbound handler of that path, or one row with handler NULL when the path has none.

- [ ] **Step 1: Write failing tests**, with workspaces carrying the §2c shapes (the blocking stub calling `GreeterGrpc#getSayHelloMethod`, whose body calls `generateFullMethodName(SERVICE_NAME, "SayHello")`, then `ClientCalls#blockingUnaryCall`):
  - `test_a_blocking_stub_call_to_a_served_rpc_lands_on_its_handler` → one row `(…GreeterBlockingStub#sayHello(…), 3, grpc, helloworld.Greeter/SayHello, …HelloWorldService#sayHello(…), compiler)`.
  - `test_an_async_stub_method_gets_its_own_hop`: `GreeterStub#sayHello` with `ClientCalls#asyncUnaryCall` at ordinal 4 → a row at 4.
  - `test_an_unhandled_rpc_of_a_served_service_gets_a_row_with_no_handler`.
  - `test_a_service_not_served_here_gets_no_hop`.
  - `test_a_stub_method_naming_two_wire_methods_gets_no_hop`.
  - `test_a_class_that_is_not_a_stub_gets_no_hop`: an `AsyncService` default method calling `getSayHelloMethod` → none.
  - The export ratchet test, and a `tests/storage/test_workspace.py` case that the bundle carries `rpc_hops.parquet`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Bump the version, write the docs, update the hard-coded `7`s.
- [ ] **Step 4:** Run the new tests and the gate. Expected: PASS.
- [ ] **Step 5: Guards:**
  - `grpc.a-STUB-call-to-a-served-rpc-is-a-hop`, edit: write no rows;
  - `grpc.a-stub-naming-TWO-wire-methods-gets-no-hop`, edit: take the first wire name.
  Pin and measure both: killed.
- [ ] **Step 6:** Commit `feat(grpc): rpc_hops — a stub call to a served RPC names the handler it lands on`.

### Task 7: The trace walks the hop; the document draws it

**Files:**
- Modify:
  - `src/sextant/application/query/trace.py` (`_Index.hops`, `Step.via`, `_walk`, the module docstring's "Where it stops");
  - `src/sextant/egress/render/document.py` (`_message_label`, the step table's `Reaches` cell, `_TRACE_PREAMBLE` if it enumerates stop behaviour);
  - D01's Traces section.
- Test: `tests/application/test_trace.py`, `tests/egress/test_render.py`

**Interfaces:**
- Consumes: the `rpc_hops` named query (Task 6).
- Produces:
  - `Step.via: str | None = None`, spelled `"<protocol> <path>"`, for example `"grpc helloworld.Greeter/SayHello"`.
  - `_Index.hops: dict[tuple[str, int], list[dict[str, object]]]`, keyed `(caller, ordinal)`.
  - The behaviour in `_walk`: at a `call_edges` row whose `(caller, ordinal)` has hops, the walk emits one step per hop row INSTEAD of the boundary step. Each step keeps the row's `target`, `invoke_kind` and `resolution`, has `callee` = the hop's handler (NULL where the hop's handler is NULL), and has `via` set. `_stop` is unchanged, so a handler is expanded, revisited or a cycle as any callee is, and a NULL handler is still `boundary`.
  - In the document: `_message_label` appends ` via <via>` before the stop marker, and the step table's `Reaches` cell for a step with `via` reads `via <via>`.

- [ ] **Step 1: Write failing tests:**
  - `test_a_walk_crosses_a_hop_into_the_served_handler`: build an `_Index` with a root calling a stub method, the stub's `ClientCalls` row, and a hop to a handler that calls one more method. The handler's step has `via` `"grpc helloworld.Greeter/SayHello"` and `stop` None, its own call is the next step at depth+1, and `trace.terminals` does not contain the `ClientCalls` step.
  - `test_a_hop_with_no_handler_stays_a_boundary_with_its_wire_path`.
  - `test_a_hop_into_a_method_already_on_the_path_is_a_cycle`.
  - Render: `test_a_hop_arrow_names_the_wire_path`, where the label is `blockingUnaryCall (declared ClientCalls) via grpc helloworld.Greeter/SayHello`, and the step table's `Reaches` reads `via grpc helloworld.Greeter/SayHello`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `pytest tests/application/test_trace.py tests/egress -q`, then the gate. Expected: PASS. `record_reachability` reads traces, so check that its tests still pass and re-pin what the hop legitimately adds.
- [ ] **Step 5: Guard** `trace.the-walk-CROSSES-a-hop-into-the-handler`, edit: ignore `_Index.hops`. Pin and measure: killed.
- [ ] **Step 6:** Commit `feat(trace): a gRPC call to this module's own service is followed to its handler`.

### Task 8: Fixture, real-input measurement, and the record

**Files:**
- Create, under `fixtures/orders-quarkus/src/main/java/com/acme/quarkus/`, hand-written stand-ins in `hello/HelloGrpc.java`'s style (Strings with the `Utf8` marshaller, no protoc):
  - `quotes/`: `QuotesGrpc` (service `acme.quotes.Quotes`, rpc `GetQuote`, with `QuotesBlockingStub`, `QuotesStub`, `AsyncService`, `QuotesImplBase`); `Quotes` (`extends io.quarkus.grpc.MutinyService`); `QuotesClient` (`implements Quotes, MutinyClient<MutinyQuotesGrpc.MutinyQuotesStub>`); `QuotesBean` (`extends MutinyQuotesGrpc.QuotesImplBase implements BindableService, MutinyBean`, field `delegate: Quotes`); `MutinyQuotesGrpc` (`QuotesImplBase implements BindableService`, whose `bindService` calls `QuotesGrpc.getServiceDescriptor()`/`getGetQuoteMethod()`; and `MutinyQuotesStub extends AbstractStub implements MutinyStub`, delegating by method reference to `QuotesGrpc.QuotesStub`). User classes: `QuotesService` (`@GrpcService implements Quotes`) and `QuotesResource` (JAX-RS: `GET /quotes/mutiny/{symbol}` through `@GrpcClient("quotes") Quotes`, and `GET /quotes/blocking/{symbol}` through `@GrpcClient("quotes") QuotesGrpc.QuotesBlockingStub`).
  - `hello/HelloResource.java`: `GET /hello/{name}` through `@GrpcClient("hello") HelloGrpc.HelloBlockingStub`. This is the grpc-java self-call.
  - `pricing/`: `MutinyPricingGrpc`, `Pricing` and its generated `PricingClient`, delegating to the existing `hello/PricingGrpc`, plus a user class with `@GrpcClient("pricing") Pricing` and `@GrpcClient("pricing") MutinyPricingGrpc.MutinyPricingStub`. Pricing is not served.
- Modify: `tests/e2e/test_grpc_quarkus_delivered.py`, `docs/COVERAGE.md` (§5.7's Mutiny row → ✅ shipped, citing spec, CP-53 and pins; regenerate §2c with `scripts/coverage_matrix.py`), `docs/java-kotlin-delivery-list.md` (`quarkus-grpc-mutiny` and OI-192 leave the ```delivery block and enter ```closed with test node and CI run URL once CI is green; §3 gRPC prose), `CHANGELOG.md` (Unreleased), the spec's Status → BUILT and its "As built" section.

- [ ] **Step 1: Write failing e2e pins** in `tests/e2e/test_grpc_quarkus_delivered.py`, on the rebuilt fixture:
  - inbound `acme.quotes.Quotes/GetQuote`, handler `QuotesService#getQuote(…)`, no `service_identity` question on `QuotesService`;
  - no outbound row with path `acme.quotes.Quotes` or `acme.hello.Hello`;
  - outbound `acme.pricing.Pricing`, resolved;
  - the traces of `GET /quotes/blocking/{symbol}`, `GET /quotes/mutiny/{symbol}` and `GET /hello/{name}` each contain a step with `via` naming the RPC, landing on its handler;
  - the rendered document's trace diagram for `/quotes/blocking/{symbol}` contains `via grpc acme.quotes.Quotes/GetQuote`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Write the fixture, rebuild with `JAVA_HOME=/opt/homebrew/opt/openjdk@21`, and re-pin every count the new classes move (vertical slice, root and edge counts).
- [ ] **Step 4:** Run the pins and the gate. Expected: PASS.
- [ ] **Step 5: Measure real input.** Re-analyze `examples/quarkus-quickstarts/grpc-plain-text-quickstart` and `grpc-tls-quickstart`, and record the table under the spec's "As built". Expected, per spec §6:
  - inbound `helloworld.Greeter/SayHello` with handler `HelloWorldService#sayHello` (or `HelloWorldTlsService#sayHello`), and no question;
  - no gRPC outbound row;
  - both REST traces reaching the handler.
  If anything differs, it is a finding: grade it, fix it if Critical or Major, log it in Plane otherwise.
- [ ] **Step 6:** Run `scripts/field_check.py` (six `ok`) and the full guard sweep (`0 survived`).
- [ ] **Step 7: Record:** COVERAGE, the §2c regeneration (quote the regenerated Quarkus line in the report: gRPC reads `✅`), CHANGELOG, the spec's As built.
- [ ] **Step 8:** Commit `feat(quarkus): Mutiny gRPC forms delivered; self-calls are hops (orders-quarkus, quickstarts)`.
