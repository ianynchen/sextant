# Phase 2G — Wire Formats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protobuf and Avro schemas — embedded in compiled artifacts and read from source files — land in the existing shapes tables; every endpoint row gains an inferred `format` with its trust level; bytes-only channels bind payloads through parse calls at handler-body + one delegation hop; the undecidable lands in `open_questions` for 2K.

**Architecture:** Dumb extractors emit `embedded_descriptor` facts (verbatim constants, never parsed); one interpreter in ingress (`ingress/interpret/descriptors.py`) is the only code that understands a schema format, running as a fact-stream transform in the analyze stage (2F's config-reader wiring point). A late resolve pass (`resolve/format.py`) owns the six-rung format ladder; a new `resolve/shapes/parse_binding.py` owns the two-rung parse binding. All framework/library names are catalog data.

**Tech Stack:** Python (duckdb, pydantic, **new: protobuf, grpcio-tools**), Java/ASM extractor (no new deps), DuckDB SQL, YAML catalogs, Maven fixture (**new: protobuf-maven-plugin, avro-maven-plugin**).

**Spec:** docs/superpowers/specs/2026-08-31-phase-2g-wire-formats-design.md

## Global Constraints

- **No version bumps**: `SEXTANT_VERSION`/`FACT_SCHEMA_VERSION`/`GRAPH_SCHEMA_VERSION` stay 0.1.0/1.0.0/1.0.0 (gate opens after 2J).
- **Determinism (NFR-1)**: double-run byte-identity over every new table and export; `open_questions` rows ordered by wire identity; descriptor interpretation ordered by symbol.
- **Unresolved is an answer, never an omission**: failures record gaps (`descriptors_not_interpreted`, `schema_sources_not_compiled`, `payload_parsed_beyond_horizon`, `payload_parse_ambiguous`); nothing crashes on bad input, nothing is guessed.
- **An assumed format must never look observed**: framework defaults and payload-hierarchy evidence stamp `format_resolution: narrowed`, never `exact`; declared media always outranks payload type (proto3 JSON encoding).
- **Framework and library names live in catalogs only** — no engine or interpreter branches on a framework name. The one stated exception: the interpreter and extractor recognize the *schema runtimes'* structural types (`com.google.protobuf.GeneratedMessage*`, `org.apache.avro.specific.SpecificRecordBase`) the way D02 §2c already names them — schema formats, not frameworks.
- **Only `ingress/interpret/descriptors.py` imports `google.protobuf`**; only `ingress/read/proto_source.py` imports/invokes `grpc_tools`. Structural test enforces the first.
- **Ingress stays write-only** (import contract): the interpreter transforms fact streams in the analyze stage; it never touches the Workspace port.
- **Exact-list pins from live fixture runs only**: never write an expected endpoint/shape list from reasoning — run the pipeline, read the actual rows, pin those.
- `uv.lock` stays untracked; `.gitignore` changes need the user's explicit nod.
- Match existing patterns (§13.5); no adjacent refactors (§3). Comments state constraints, not narration.

## File Structure

| File | Responsibility |
|---|---|
| `fixtures/orders-service/src/main/proto/{order,common}.proto`, `src/main/avro/audit.avsc` | schema sources (hostile comments pinned) |
| `fixtures/orders-service/pom.xml` | codegen plugins |
| `extractor-jvm/.../DescriptorHarvest.java` (new), `ClassScanner.java`, `MethodFlow.java`, `Main.java` | embedded_descriptor emission; parameter argument kind (checkpoint-gated); 9.9 |
| `src/sextant/domain/facts.py` | `EmbeddedDescriptorFact`, `DeclaredShapeFact`, `DeclaredFieldFact` carrier, `parameter` CallArgument kind |
| `src/sextant/ingress/interpret/descriptors.py` (new) | THE interpreter: two-phase pool, protobuf+avro → declared_shape facts |
| `src/sextant/ingress/read/proto_source.py`, `avsc.py` (new) | source readers → interpreter input |
| `src/sextant/application/stages/analyze.py` | wiring: descriptors collected → interpreted → written |
| `src/sextant/application/ports/detector.py`, `ingress/detect/maven.py` | `schema_roots` |
| `src/sextant/application/resolve/shapes/expansion.py` | declared-shape expansion replaces bytecode expansion |
| `src/sextant/application/resolve/format.py` (new) | the six-rung ladder, nothing else |
| `src/sextant/application/resolve/shapes/parse_binding.py` (new) | rungs A/B, open_questions rows |
| `src/sextant/application/resolve/pipeline.py` | pass ordering: parse_binding → format (both after media stamping) |
| `src/sextant/storage/duckdb/schema.sql`, `merge_endpoints.sql`, `derive_endpoints.sql`, `workspace.py` | columns, carry, open_questions table + queries |
| `src/sextant/catalogs/*.yml` | `format_fixed`, `media_formats`, `format_from`, `parse_calls`, `json_default_markers` |
| `src/sextant/egress/render/document.py`, `metadata.py`, export | Format rendering, Open questions section, counters, bundle artifact |
| `README.md`, `docs/components/{D00,D02,D06}*.md`, `docs/COVERAGE.md`, roadmap | docs + dependency section |

### Task order and why

Fixtures first (generated classes must exist before the extractor can be tested against reality); interpreter next (independent of the extractor — its tests generate descriptors with `grpc_tools`, the spike's proven path); the extractor task is also the **checkpoint** that freezes four bytecode realities before dependent tasks dispatch; then readers/wiring, shapes integration, format, parse binding, egress, docs.

---

### Task 1: Fixture schema sources and codegen build

**Files:**
- Create: `fixtures/orders-service/src/main/proto/order.proto`, `fixtures/orders-service/src/main/proto/common.proto`, `fixtures/orders-service/src/main/avro/audit.avsc`
- Modify: `fixtures/orders-service/pom.xml`

**Interfaces:**
- Produces: generated classes in the fixture jar — `com.example.orders.proto.OrderProto$OrderRequest` (outer class `OrderProtos`), `com.example.orders.avro.AuditEvent` — that Tasks 3/5/6/7 extract, expand, and bind. The `.proto`/`.avsc` files themselves are Task 4's reader inputs.

- [ ] **Step 1: Write the schema sources.** `common.proto` (imported by `order.proto` — pins the two-phase pool):

```proto
// common types — imported by order.proto
syntax = "proto3";
package sextant.orders;
option java_package = "com.example.orders.proto";
option java_outer_classname = "CommonProtos";

message Money {
  string currency = 1;
  int64 amount_minor = 2;  // renames to amountMinor on the JSON wire
}
```

`order.proto` — **the hostile-comment regression pin (user requirement)**: keep every comment below verbatim:

```proto
// Leading file comment — with unicode: héllo, 中文, emoji 🚀
/* Block comment
   spanning lines with weird chars: <>&"'\x00-ish \n literal */
syntax = "proto3";

package sextant.orders;  // trailing comment

import "common.proto";

option java_package = "com.example.orders.proto";  /* another trailing */
option java_outer_classname = "OrderProtos";

// Comment on the message
// with a second line — and a fake directive: option java_package = "evil";
message OrderRequest {
  // comment on a field, containing */ almost-terminators and // nested
  string total_amount = 1;  // trailing: renames to totalAmount on JSON wire
  /* block on field */
  int32 count = 2 [json_name = "explicitCount"];  // explicit override
  sextant.orders.Money price = 3;  // cross-file reference (two-phase pool pin)
  // comment before a nested message
  message Line {
    string sku = 1;  // sku comment
  }
  repeated Line lines = 4;
  map<string, string> tags = 5;
  // enum comment
  enum Status {
    STATUS_UNSPECIFIED = 0;  // zero
    STATUS_OPEN = 1;
  }
  Status status = 6;
  optional string note = 7;  // proto3 optional: nullable
}

message OrderReply {
  string order_id = 1;
}
```

`audit.avsc` (union + default, the two Avro semantics §3 maps):

```json
{
  "type": "record",
  "name": "AuditEvent",
  "namespace": "com.example.orders.avro",
  "fields": [
    {"name": "event_id", "type": "string"},
    {"name": "actor", "type": ["null", "string"], "default": null},
    {"name": "amount", "type": "long", "default": 0}
  ]
}
```

- [ ] **Step 2: Add the codegen plugins to `pom.xml`.** `com.github.ascopes:protobuf-maven-plugin` (downloads protoc by os classifier; goal `generate`) and `org.apache.avro:avro-maven-plugin` (goal `schema`, `sourceDirectory` `src/main/avro`). Add `com.google.protobuf:protobuf-java` and `org.apache.avro:avro` as fixture dependencies (generated code needs the runtimes on the compile classpath — fixture-only, NOT extractor deps). Pin all versions explicitly.
- [ ] **Step 3: Build and verify.** Run the existing fixture build command (see the fixture's README/Makefile — the same invocation the test suite uses). Verify generated classes exist in `target/classes`: `OrderProtos$OrderRequest.class`, `CommonProtos$Money.class`, `AuditEvent.class`. Verify the *full existing test suite still passes* — new classes in the fixture jar must not disturb 2A–2F pins (if endpoint/shape counts move, STOP and report; nothing here declares endpoints, so movement means a pin was fragile).
- [ ] **Step 4: Commit** `feat(fixtures): protobuf and Avro schema sources with codegen`.

### Task 2: Python dependencies, new fact kinds, and the descriptor interpreter

**Files:**
- Modify: `pyproject.toml`, `src/sextant/domain/facts.py`
- Create: `src/sextant/ingress/interpret/__init__.py`, `src/sextant/ingress/interpret/descriptors.py`
- Test: `tests/ingress/interpret/test_descriptors.py`, `tests/architecture/test_protobuf_confinement.py`

**Interfaces:**
- Produces:
  - `EmbeddedDescriptorFact(kind="embedded_descriptor", document_id, symbol, schema_format: Literal["protobuf","avro"], payload: str, origin: Literal["compiled","source"] = "compiled")` — payload base64 for protobuf, verbatim JSON text for avro. Joins the `Fact` union.
  - `DeclaredFieldFact` carrier (pydantic model, not in the union — rides inside DeclaredShapeFact): `name, wire_name, field_number: int | None, wire_type, wire_format, required: bool, nullable: bool, default: str | None, item: dict | None, shape_ref: str | None, enum_symbols: list[str] | None`.
  - `DeclaredShapeFact(kind="declared_shape", document_id, symbol, schema_format, origin, evidence: Literal["compiler","declared"], fields: list[DeclaredFieldFact])` — joins the `Fact` union.
  - `interpret_descriptors(descriptors: Sequence[EmbeddedDescriptorFact]) -> tuple[list[DeclaredShapeFact], list[str]]` — pure function; second element is the failed symbols/paths (the `descriptors_not_interpreted` gap payload). Module-wide two-phase: collect ALL, one pool, dependency-ordered adds; output sorted by `symbol`.

- [ ] **Step 1: Add dependencies.** `protobuf` and `grpcio-tools` to `pyproject.toml` `[project.dependencies]`, both with `>=` floors pinned to the versions `uv add` resolves today. Run `uv sync`. Do NOT commit `uv.lock`.
- [ ] **Step 2: Write the failing structural test** (`tests/architecture/test_protobuf_confinement.py`): walk `src/sextant` ASTs; assert `google.protobuf` is imported only by `src/sextant/ingress/interpret/descriptors.py` and `grpc_tools` only by `src/sextant/ingress/read/proto_source.py` (that file arrives in Task 4 — the assertion is an allowlist, so its absence now passes). Mirror `tests/architecture/test_symbol_grammar_confinement.py`'s walking pattern.
- [ ] **Step 3: Write the failing interpreter tests.** Generate descriptors in-test the spike's way (this is the proven toolchain — compile with `grpc_tools.protoc --descriptor_set_out` in `tmp_path`, split the `FileDescriptorSet` into per-file `FileDescriptorProto` bytes, base64 them into `EmbeddedDescriptorFact`s). Use two `.proto` files where one imports the other (Task 1's exact schemas, duplicated inline here — an implementer may not have the fixture). Assertions:

```python
def test_json_names_read_never_computed(tmp_path):
    shapes, failed = interpret_descriptors(descriptors_from(tmp_path, ORDER_PROTO, COMMON_PROTO))
    assert failed == []
    order = shape_by_symbol(shapes, ".OrderRequest")  # match by suffix; pin exact symbol after first run
    fields = {f.name: f for f in order.fields}
    assert fields["total_amount"].wire_name == "totalAmount"      # computed default
    assert fields["count"].wire_name == "explicitCount"           # explicit override
    assert fields["total_amount"].field_number == 1

def test_cross_file_reference_resolves():           # two-phase pool pin
    # price: sextant.orders.Money from the imported file → shape_ref, not a failure
def test_type_mapping():                            # int64→integer/int64, map→map+item, enum symbols, repeated→array+item
def test_proto3_presence():                         # scalar required+not nullable; optional note nullable; message field nullable; repeated required
def test_avro_union_and_default():                  # ["null","string"]→nullable; default present→required False; amount default "0"
def test_unparseable_payload_is_gap_not_crash():    # garbage base64 → ([], [symbol]); other descriptors still interpret
def test_missing_import_is_gap_for_that_file():     # order without common → order in failed, others fine
def test_output_deterministic():                    # two runs, identical serialization
```

- [ ] **Step 4: Run tests to verify they fail** (`uv run pytest tests/ingress/interpret/ -v` → import errors).
- [ ] **Step 5: Implement.** Facts in `domain/facts.py` (extend the `Fact` union — follow `ConfigEntryFact`'s style). Interpreter: phase one indexes payloads by descriptor file name; phase two builds `descriptor_pool.DescriptorPool()`, adds `FileDescriptorProto`s dependency-first (topological over `.dependency`; a file whose imports never arrive → failed list), then walks message types recursively (nested types too, each its own `DeclaredShapeFact`; the *shape symbol* is the generated class symbol when `origin="compiled"` — derive from `java_package`/`java_outer_classname` options — and the schema full name when source-origin). Field projection per the spec §3 table verbatim (including `map<K,V>` → `wire_type "map"` with `item` describing V, `bytes → string/byte`). Avro: `json.loads`, recurse record fields, unions/defaults per spec. Evidence: `compiler` when origin compiled, `declared` when source.
- [ ] **Step 6: Run tests to verify they pass**, then the full suite (`uv run pytest`).
- [ ] **Step 7: Commit** `feat: descriptor interpreter — embedded schemas into declared_shape facts`.

### Task 3: Extractor 9.9 — embedded_descriptor harvest (CHECKPOINT)

**Files:**
- Create: `extractor-jvm/src/main/java/dev/sextant/extractor/DescriptorHarvest.java`
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/ClassScanner.java`, `MethodFlow.java`, `Main.java` (9.8 → 9.9)
- Test: extractor's existing test tree + a Python-side probe test in `tests/ingress/test_extractor_descriptors.py`

**Interfaces:**
- Consumes: Task 1's fixture jar (generated protobuf/Avro classes).
- Produces: `embedded_descriptor` JSON fact lines matching Task 2's `EmbeddedDescriptorFact` schema exactly (`origin` omitted → defaults `"compiled"`); a **checkpoint report** answering the four reality questions below; possibly a `parameter` CallArgument kind (both sides).

**This task is the phase checkpoint.** Before implementing, probe the *actual fixture bytecode* (javap/ASM dump) and record answers in the report — Tasks 6 and 7 dispatch only after these are frozen:

1. **Protobuf constant shape**: how does protobuf-java embed the descriptor in `OrderProtos`' `<clinit>`? (Expected: one or more `LDC` string constants passed to `internalBuildGeneratedFileFrom` / `descriptorData` — Java string constants cap at 64KB so large descriptors split; the harvest must concatenate in emission order, then encode the *ISO-8859-1 bytes* of the joined string as base64 — protobuf embeds binary as latin-1-mangled strings. Verify the exact charset trick against protobuf-java's own generated-code comment.)
2. **Avro constant shape**: `SCHEMA$` is built via `new Schema.Parser().parse("chunk1", "chunk2", ...)` in newer Avro — harvest = the string arguments of that call, concatenated, emitted verbatim (NOT base64).
3. **Parameter-fed call arguments**: in today's call_site facts, how does an argument that is a bare load of the caller's parameter appear? (Expected: `unresolved`.) If parameters are not identifiable, ADD a `parameter` CallArgument kind — `{kind: "parameter", value: <parameter index>}` — emitted when the dataflow sees `xLOAD` of a parameter's own starting slot, reusing `MethodFlow.parameterSlotsOf`/`indexOfSlot` (they exist for field_write). Python side: add `"parameter"` to `CallArgument.kind`'s Literal. Rung A/B (Task 7) depends on this.
4. **Class literals**: confirm `readValue(x, OrderProto.class)` arrives as the existing `class` argument kind with the type's symbol. (The kind exists since 2C; verify, do not add.)

- [ ] **Step 1: Probe and write the checkpoint report** (answers to 1–4, with javap evidence) to the SDD workspace; adjust the steps below per findings.
- [ ] **Step 2: Failing Python-side probe test**: run the extractor over the fixture jar (the existing subprocess harness other extractor tests use), parse the fact file, assert an `embedded_descriptor` fact exists for the `OrderProtos` holder with `schema_format == "protobuf"` whose payload **round-trips through Task 2's interpreter** (this closes the loop: harvest → interpret → `totalAmount`), and one for `AuditEvent` with `schema_format == "avro"` whose payload `json.loads` to the record.
- [ ] **Step 3: Implement `DescriptorHarvest`**: detection structural per spec §1 (supertype chain reaches `GeneratedMessage`/`GeneratedMessageV3`/`GeneratedMessageLite` → the *outer descriptor holder* it references owns the fact; `SpecificRecordBase` → the class itself). One fact per holder, not per message. Wire into `ClassScanner`; bump `Main` version string to 9.9. Implement finding-3's `parameter` kind if the probe demanded it.
- [ ] **Step 4: Run the probe test and the full suite** (extractor rebuild first — note the build/version coupling the JVM extractor README states).
- [ ] **Step 5: Update D00**: `embedded_descriptor` fact kind (§5, with the cross-language contract sentence from spec §1 — Go `rawDesc`, Python `serialized_pb`, TS protobufjs), `declared_shape` marked "made real, interpreter-emitted, never extractor-emitted", `parameter` argument kind if added (with its own neutral contract sentence: "the argument is the caller's parameter N, any language").
- [ ] **Step 6: Commit** `feat(extractor): 9.9 — embedded descriptor harvest` (+ separate commit if parameter kind added).

### Task 4: Source readers, schema roots, analyze wiring

**Files:**
- Create: `src/sextant/ingress/read/avsc.py`, `src/sextant/ingress/read/proto_source.py`
- Modify: `src/sextant/application/ports/detector.py` (add `schema_roots` beside `resource_roots`), `src/sextant/ingress/detect/maven.py` (`src/main/proto`, `src/main/avro` when present), `src/sextant/application/stages/analyze.py`, `src/sextant/domain/factfile.py` (only if a new target helper is needed — follow `config_fact_target`, keep source extension in the name)
- Test: `tests/ingress/read/test_schema_sources.py`, `tests/application/test_analyze_descriptor_wiring.py`

**Interfaces:**
- Consumes: `ArtifactReader` protocol (`accepts(file_kind)`, `read(ReadRequest) -> list[tuple[Document, list[Fact]]]`), `group_files_by_reader`, Task 2's facts + `interpret_descriptors`.
- Produces: readers registered in analyze; `embedded_descriptor` facts with `origin="source"` flowing into the same interpreter call; interpretation wired ONCE in analyze over compiled + source descriptors together; `declared_shape` facts written to fact files; gaps `schema_sources_not_compiled`, `descriptors_not_interpreted` surfaced through the existing gap plumbing.

- [ ] **Step 1: Failing reader tests.** `.avsc` reader: emits one `EmbeddedDescriptorFact(schema_format="avro", origin="source")` per file, payload verbatim, symbol from `namespace`+`name`. `.proto` reader: given a schema root containing Task 1's two protos, shells `python -m grpc_tools.protoc -I<root> --descriptor_set_out=<tmp>` over ALL files in one invocation (imports must resolve), emits one fact per `FileDescriptorProto`; a broken proto (write one with a syntax error) → that root's files land in the reader's failure list, surfaced as `schema_sources_not_compiled`, other roots unaffected, no exception escapes. Readers claim extensions `avsc`/`proto` via `accepts`; assert they coexist with config readers in `group_files_by_reader` without claiming `.yml`.
- [ ] **Step 2: Failing wiring test.** Build a fake module with a schema root + a compiled `embedded_descriptor` fact for the *same* shape identity; run the analyze stage; assert exactly one `declared_shape` per identity survives with `origin="compiled"` (**compiled beats source — DR-4**; the precedence key is the schema full name, dedup applied after interpretation, deterministic). Assert ingress import contract still KEPT (run the lint gate).
- [ ] **Step 3: Implement.** Readers per the port docstring discipline (a reader never interprets). Analyze: collect compiled `embedded_descriptor` facts from scanner output + reader facts from schema roots, call `interpret_descriptors` once, apply precedence, write `declared_shape` facts into the fact stream (fact-file target named for the schema source, `.jsonl` appended — the 2F collision rule: keep the source extension). The `.proto` reader failure list and interpreter failure list flow to the gaps the way 2F's readers surfaced theirs.
- [ ] **Step 4: Run tests + full suite; run the import-contract gate explicitly.**
- [ ] **Step 5: Commit** `feat: schema source readers and descriptor interpretation wiring`.

### Task 5: Declared shapes into the shapes tables

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql` (`shape_fields.field_number INTEGER`), `src/sextant/storage/duckdb/workspace.py` (declared_shape view/query; export includes field_number), `src/sextant/application/resolve/shapes/expansion.py`
- Test: `tests/resolve/shapes/test_declared_expansion.py`, plus the live-pipeline pins in `tests/test_endpoints.py`-adjacent shape tests

**Interfaces:**
- Consumes: `declared_shape` facts in the workspace (Task 4); the existing expansion entry point that turns a payload type reference into `shapes`/`shape_fields` rows.
- Produces: descriptor-described types expand from declared fields — `wire_name` = declared `wire_name`, `field_number` populated, evidence `compiler`/`declared` — and **never** walk bytecode fields (no blend). Non-generated types unchanged. Later tasks (6 rung 4, 7) read "is this shape descriptor-described" from shape evidence.

- [ ] **Step 1: Failing unit test**: a payload type owning a `declared_shape` expands to exactly the declared fields (pin `totalAmount`, `explicitCount`, `field_number` 1/2, nested `Line` as its own shape, `Money` cross-file ref resolving to a `shape_id`); a type with both bytecode fields and a declared shape takes ONLY the declared fields; a plain DTO expands exactly as before (existing tests stay green untouched).
- [ ] **Step 2: Implement**: `field_number` column (NULL default — annotation-derived shapes never set it); expansion consults declared shapes first (one lookup by type symbol; on hit, project `DeclaredFieldFact` rows into the existing `{wire_type, wire_format, nullable, shape_id?, item?}` grammar and stop).
- [ ] **Step 3: Add fixture surface + live pin**: give an existing fixture REST handler a protobuf payload — add to `OrdersApiController` (or a new small controller) `@PostMapping(value = "/proto-orders", produces = MediaType.APPLICATION_JSON_VALUE)` taking `OrderRequest` (the generated type) and returning `OrderReply`. Run the pipeline on the fixture; pin the new endpoint's shape rows from the live run (exact-list rule). Suite green.
- [ ] **Step 4: Commit** `feat: declared shapes expand from descriptors, field_number lands`.

### Task 6: Format columns, catalog vocabulary, the ladder pass

**Files:**
- Modify: `schema.sql` (`endpoints.format TEXT`, `endpoints.format_resolution TEXT`), `derive_endpoints.sql` (columns default NULL through every union/GROUP BY), `merge_endpoints.sql` (carry), `src/sextant/domain/closed_sets.py` (format set), `src/sextant/application/ports/catalogs.py` (vocabulary), catalogs: `spring-web.yml` + `spring-mvc.yml` (`media_formats`, `json_default_markers`), `spring-kafka-media.yml` (`format_from`), `soap`/`graphql`-owning catalogs if present else the catalogs that first declare those protocols (`format_fixed`)
- Create: `src/sextant/application/resolve/format.py`
- Modify: `src/sextant/application/resolve/pipeline.py` (run after media stamping and after Task 7's pass — see ordering note), `workspace.py` (stamp/update SQL)
- Test: `tests/resolve/test_format_ladder.py`, merge-carry test beside the existing 2F media-carry test

**Interfaces:**
- Consumes: `consumes`/`produces` columns, 2F's serializer media stamps, Task 5's shape evidence.
- Produces: every endpoint row stamped `(format, format_resolution)`; `resolve_format(workspace, catalogs)` invoked from the pipeline; closed set `{json, protobuf, avro, xml, string, bytes}` + reserved `json_schema` (catalog writing it → refused, the 2F reserved-mechanism pattern).

- [ ] **Step 1: Failing ladder tests**, one per rung + the precedence pins:

```python
def test_declared_media_beats_payload_hierarchy():   # protobuf shape + produces application/json → ("json","exact")
def test_fixed_protocol():                           # catalog format_fixed: grpc→protobuf, "exact"
def test_serializer_config():                        # KafkaProtobufSerializer stamp → ("protobuf","exact")
def test_payload_hierarchy_is_narrowed():            # descriptor shape, no media → ("protobuf","narrowed")
def test_framework_default_json():                   # DTO + jackson marker (test BOTH com.fasterxml and tools.jackson) → ("json","narrowed")
def test_nothing_is_unresolved():                    # kafka, no evidence → (NULL,"unresolved")
def test_consumes_produces_conflict():               # media mapping disagrees → (NULL,"unresolved") + open_questions row kind "format_conflict"
def test_reserved_json_schema_refused():             # catalog media_formats value json_schema → catalog validation error
def test_merge_carries_format_weaker_resolution():   # inbound exact + outbound narrowed twins → both-row keeps inbound format, resolution stays per-column rule: format coalesce(inbound, outbound); resolution takes the WEAKER of the two present markers (narrowed < exact; unresolved weakest)
```

- [ ] **Step 2: Implement**: closed set + catalog vocabulary validation (values checked against the set, framework names stay data); `format.py` walks rungs in order per row, first answer wins, ladder logic reads ONLY catalog mappings + row columns + shape evidence (no library names in code); `merge_endpoints.sql` adds the two columns to the twin-select/UPDATE with `coalesce` (media precedent) and the weaker-marker rule stated in Step 1 (implement as a CASE over the two markers; comment states the rule the way the 2F media comment does — precisely what the SQL delivers).
- [ ] **Step 3: Fixture surfaces + live pins**: Kafka listener + producer config rows in `application.yml` (`spring.kafka.producer.value-serializer: io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer` — the class name string is config data, no dependency needed); Task 5's `/proto-orders` endpoint pins rung 2-beats-4; existing JSON endpoints pin rung 5 (`format json (assumed)` rows appear — update the exact-list pins from the live run, expect broad but mechanical pin churn). Double-run byte-identity test over endpoints with the new columns.
- [ ] **Step 4: Commit** `feat: format inference — the six-rung ladder`.

### Task 7: Parse-call binding and open_questions

**Files:**
- Create: `src/sextant/application/resolve/shapes/parse_binding.py`, `src/sextant/catalogs/parse-calls.yml` (or fold vocabulary into the owning catalogs if D02 argues so — implementer reads D02 §2's ownership discipline and follows the 2F `field_sources` precedent for where per-library vocab lives)
- Modify: `schema.sql` (`open_questions` table: `protocol TEXT, method TEXT, path TEXT, question TEXT, candidates JSON, evidence TEXT`; pre-declared empty, replaced whole per resolve), `workspace.py` (queries + reset/insert SQL files per the `resolved_config` pattern), `pipeline.py` (parse_binding runs after shape binding, before `format.py` — format rung 4 reads its output), `metadata.py` gap counters
- Test: `tests/resolve/shapes/test_parse_binding.py`

**Interfaces:**
- Consumes: call_site facts (with Task 3's parameter-argument answer), `parse_calls` catalog vocabulary, Task 5's declared shapes.
- Produces: `request_shape` bound on bytes-only endpoints (evidence `syntax`, resolution `exact`); `open_questions` rows (`question ∈ {payload_binding, format_conflict}` — closed set); gaps `payload_parsed_beyond_horizon`, `payload_parse_ambiguous`; a bound descriptor parse feeds format rung 4.

- [ ] **Step 1: Catalog vocabulary** — `parse_calls` entries: protobuf `parseFrom` matched by **owner hierarchy** (`GeneratedMessage*` supertype — the payload type IS the receiver owner), Jackson 2 `com.fasterxml.jackson.databind.ObjectMapper#readValue` (payload type from the `class` argument), **Jackson 3** `tools.jackson.databind.ObjectMapper#readValue` AND `tools.jackson.databind.json.JsonMapper#readValue`, Avro `org.apache.avro.specific.SpecificDatumReader` construction (`class` argument). Each entry: owner (or hierarchy marker), method, which argument is the bytes, where the payload type lives (`receiver_owner` | `class_arg`). Validate against D02's vocabulary checker.
- [ ] **Step 2: Failing binding tests** (unit-level over synthetic call_site/symbol rows, then live fixture pins):

```python
def test_rung_a_handler_body():         # parse in handler, arg links to payload parameter → bound, syntax/exact
def test_rung_b_one_hop():              # handler passes param to module-local method; callee parses corresponding param → bound
def test_beyond_horizon_gap():          # two hops → unbound + payload_parsed_beyond_horizon + open_questions row w/ candidate
def test_multi_caller_binds_both():     # two listeners → same callee parse → both endpoints bound (truthful flow)
def test_ambiguous_refuses():           # one payload, two different parses → unbound + payload_parse_ambiguous + open_questions row with BOTH candidates
def test_unrelated_parse_ignored():     # parse of a different value in handler → no binding
def test_open_questions_deterministic() # ordered by (protocol, method, path, question); double-run identical
```

- [ ] **Step 3: Implement** `parse_binding.py`: bytes-shaped payload detection (parameter type in `String`/`byte[]`/catalog-named envelopes); rung A join (call argument → parameter index of the handler's payload parameter); rung B join (handler's call passing that parameter → callee symbol → callee's parse whose argument is the *corresponding parameter position*; module-local only; one hop, never recursive). Stamp `request_shape` via an UPDATE that never overwrites a non-NULL (first-writer discipline). open_questions insert per the `resolved_config` reset/insert pattern.
- [ ] **Step 4: Fixture surfaces + live pins**: an SQS listener with rung-A `OrderRequest.parseFrom(body.getBytes())`; a JMS or second SQS listener delegating `body` to a package-local `OrderIngest.process(String)` that parses (rung B); a listener whose body try-parses protobuf then falls back to `tools.jackson` `JsonMapper#readValue` (ambiguous → open_questions, AND the Jackson 3 catalog row exercised); a listener delegating two hops (beyond-horizon). Run live, pin endpoints + open_questions rows exactly.
- [ ] **Step 5: Commit** `feat: parse-call payload binding, one hop, open_questions`.

### Task 8: Egress — rendering, export, metadata

**Files:**
- Modify: `src/sextant/egress/render/document.py`, `src/sextant/egress/render/metadata.py`, the D06 export/manifest module (find via the 2F `environments` change — same files), `workspace.py` export query list (`open_questions` joins it)
- Test: `tests/egress/test_render_format.py`, export round-trip test beside the existing bundle tests

**Interfaces:**
- Consumes: `format`/`format_resolution` columns, `open_questions` table, gap counters from Tasks 4/6/7.
- Produces: rendered docs show Format beside Media — `protobuf` for `exact`, `protobuf (assumed)` for `narrowed`, `unresolved` for NULL (the 2E NULL-renders-unresolved precedent); an "Open questions" document section listing each row's wire identity, question, and candidates (rendered only when rows exist); `open_questions` in the D06 bundle + named in the manifest; metadata.json carries the four new gap counters.

- [ ] **Step 1: Failing render tests**: the three format renderings; the Open questions section renders candidates and is absent when the table is empty; metadata counters present.
- [ ] **Step 2: Implement**; export `open_questions` (Parquet like siblings), manifest entry.
- [ ] **Step 3: Live fixture run**: regenerate rendered-document pins (mechanical churn — every endpoint line gains Format); double-run byte-identity on the bundle.
- [ ] **Step 4: Commit** `feat: format and open questions reach documents, bundle, metadata`.

### Task 9: Docs, README, COVERAGE, roadmap

**Files:**
- Modify: `README.md`, `docs/components/D00-fact-schema.md` (verify Task 3's entries complete; add `declared_shape` §5 wording), `docs/components/D02-catalog-schema.md` (§2c ladder completed; `format_fixed`/`media_formats`/`format_from`/`parse_calls`/`json_default_markers` vocabularies with ownership rules), `docs/components/D06-*.md` (`open_questions` artifact + Format rendering), `docs/COVERAGE.md`, `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md` (2G row → delivered; headline count re-derived from the actual flips)
- Test: none (docs); the suite must stay green

- [ ] **Step 1: README** — the user-required "Dependencies" section: Python (`uv sync`; name `protobuf` — descriptor parsing, `json_name` authority — and `grpcio-tools` — `.proto` source compilation — and why they exist), JVM extractor (unchanged, deliberately no new dependency — the layering argument in one sentence), fixture toolchain (protoc arrives via the Maven plugin; nothing installed by hand).
- [ ] **Step 2: COVERAGE flips + honesty boundaries** — flip the protobuf/Avro/format rows 2G shipped (§4.1 regimes now partially live, §4.2 protobuf/Avro rows, serializer table live via `format_from`); add a Jackson 3 row (both package families catalogued); state boundaries verbatim: parse tracing stops at one hop (`payload_parsed_beyond_horizon` counts the rest, `open_questions` hands them to 2K); embedded-vs-source drift not compared (both recorded); registry subjects not derived (re-derivable); gRPC service extraction deferred; JSON Schema/XSD out (`json_schema` reserved).
- [ ] **Step 3: D02** — the ladder as §2c's completion (six rungs, the media-beats-payload rule and its proto3-JSON rationale, the weaker-marker merge rule); each vocabulary documented with its closed-set validation; the eighth/ninth style count corrected if the engine registry text names a number.
- [ ] **Step 4: Cross-check every doc claim against the shipped code** (the 2F final-review discipline: no doc sentence claims more than the diff delivers).
- [ ] **Step 5: Commit** `docs: 2G — wire formats delivered`.

---

## Plan Self-Review (run before execution)

1. **Spec coverage**: §1→T3 (+T2 facts), §2→T4, §3→T2 (+T5 expansion), §4→T5/T6/T7 schema bits, §5→T6, §6→T7, §7→T6/T7 catalogs, §8→T8/T9, §9→T2/T1 deps, §10→T1 + per-task fixture steps, §11→T9 boundaries. The hostile-comment pin: T1 sources + T2/T3 round-trips. README: T9. Jackson 3: T7 vocab + fixture.
2. **Known plan-vs-spec deltas (rulings, carried into dispatches)**: (a) spec §1's "new argument kind `class_literal`" — the `class` CallArgument kind already exists since 2C; T3 verifies instead of adding. (b) spec §1's `payload_type` on call sites — not a fact change at all; binding reads existing call_site + catalog vocabulary; the only possible extractor change is the `parameter` kind, checkpoint-gated. (c) format merge weaker-marker rule made explicit (spec said "weaker of the two markers"; plan pins the ordering unresolved < narrowed < exact).
3. **Type consistency**: `EmbeddedDescriptorFact`/`DeclaredShapeFact`/`interpret_descriptors` named identically in T2/T3/T4; `resolve_format` T6; open_questions columns T7/T8 match.
