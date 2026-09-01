# Phase 2G — Wire formats: declared shapes and format inference

**Status:** approved in brainstorm 2026-08-31; this document records the design.
**Depends on:** 2F (config resolution — serializer stamps, ArtifactReader pattern),
2E (consumes/produces columns), 2A (shapes tables).
**Roadmap row:** protobuf + Avro: format inference, `generated_descriptor` readers,
declared shapes into the same tables, proto3 JSON-name projection.

## The thesis

Format is a property of a channel that has to be inferred, never a protocol and never a
property of a payload *type* (COVERAGE §4). Protobuf and Avro differ from JSON only in
that their schema survives into the compiled artifact — so 2G reads that schema wherever
it appears, lands it in the same `shapes`/`shape_fields` tables 2A built, and records
what is on each wire with the trust level the evidence earns. Two rules bind everything:

1. **An assumed format must never look observed.** A framework default is recorded, but
   at `format_resolution: narrowed`, never `resolved` (user ruling: column + assumed rows).
2. **A protobuf-typed payload does not imply a protobuf wire.** Proto3 defines a JSON
   encoding; declared channel evidence (media, serializer) always outranks payload-type
   evidence (user ruling). The shape rows carry both namings — `name`/`field_number`
   and `wire_name` (= `json_name`) — so the format column decides which columns L
   compares, and an ambiguous format is recorded as ambiguity, not a guess.

User rulings that shaped scope: compiled-first descriptors AND source-file readers
(both in; compiled wins on the same identity per DR-4); parse-call binding at handler
body + one delegation hop, with misses ledgered and undecidable cases handed to 2K;
the "dumb extractor / one interpreter" layering (no protobuf runtime in any extractor;
the Python core owns the single descriptor interpretation); Jackson 3 (`tools.jackson`)
covered as catalog data; a README dependency section; the hostile-comment regression
pin (spike-verified 2026-08-31: default protoc output strips comments entirely —
`source_code_info` absent — and `--include_source_info` output parses cleanly with
comments inert; `json_name` arrives computed for defaults and honored for overrides).

## 1. New facts (D00; extractor 9.8 → 9.9)

Two new fact kinds, both deliberately dumb. `declared_shape` (already reserved in D00)
is **not** emitted by extractors — it is the interpreter's output (§3), which keeps
schema-format knowledge in exactly one place.

**`embedded_descriptor`** — one per generated schema-holder class:

```json
{"kind": "embedded_descriptor", "symbol": "<class symbol>",
 "schema_format": "protobuf" | "avro", "payload": "<string>"}
```

- Protobuf: the descriptor string constants harvested from the generated file's
  descriptor-holder `<clinit>`, concatenated in emission order and base64-encoded.
  The extractor never parses them. Detection is structural: the supertype chain
  reaches `com.google.protobuf.GeneratedMessage` / `GeneratedMessageV3` /
  `GeneratedMessageLite` (the same hierarchy evidence D02 §2c names), or the class is
  the generated outer-class descriptor holder those messages reference.
- Avro: the `SCHEMA$` JSON string verbatim (`schema_format: "avro"`, payload is the
  JSON text, not base64), from classes whose supertype chain reaches
  `org.apache.avro.specific.SpecificRecordBase`.
- Cross-language contract (D00 sentence): the fact is "this artifact embeds this
  schema payload, verbatim." A Go scanner emits it from a `rawDesc` literal, a Python
  scanner from `serialized_pb`, a TS scanner from protobufjs static output. No
  extractor ever links a schema runtime.

**`parse_call`** — the payload evidence on bytes-only channels — is not a new fact,
and 2G adds no pass and no argument kind. 2C's per-method dataflow already emits
linked `call_site` facts, with a `class` argument kind (2C-era) that names a
`Class<T>` literal. `application/resolve/shapes/parse_binding.py` reads those
`call_site` facts extractors already emit and matches them, at resolve time,
against catalog-declared parse shapes (§7) to determine the *type identified by the
call* (the static receiver of `parseFrom`, or the `class`-kind argument for
`readValue`). No fact carries a `payload_type` field; which calls count is catalog
vocabulary (§7), and the type a matched parse identifies is read off the existing
`call_site`/`CallArgument` shape, never stored back onto it.

## 2. Source-file readers (ingress/read)

Riding 2F's format-keyed ArtifactReader pattern, two new readers over the repository
(schema files live outside `src/main/resources` too, so detection contributes schema
roots — recorded in the detector the way `resource_roots` was). **As shipped the roots
are the two conventional directories only**, `src/main/proto` then `src/main/avro`,
each contributed when it exists; a loose `*.proto`/`*.avsc` elsewhere under the source
tree is not swept up, and the boundary is recorded in COVERAGE §4.2:

- **`.avsc`** — the file *is* the schema JSON; the reader emits an
  `embedded_descriptor`-shaped input (`schema_format: "avro"`, payload verbatim,
  symbol derived from the record's full name) tagged `origin: source`.
- **`.proto`** — the reader shells to `grpc_tools.protoc` (pip-bundled protoc) with
  `--descriptor_set_out` into a temp file, `-I` rooted at the schema root, and feeds
  the resulting `FileDescriptorProto`s to the same interpreter, tagged
  `origin: source`. No hand-written `.proto` text parser exists anywhere; the
  spike-verified toolchain is the only reader. A `.proto` that fails to compile
  (missing import, syntax error) records the `schema_sources_not_compiled` gap with
  the file path and moves on — never a crash.

**Precedence:** where a compiled embedded descriptor and a source file declare the same
shape identity, **compiled wins** (DR-4: the artifact that runs is the authority);
source-only schemas fill what the jar lacks. Drift *comparison* between the two is
explicitly out of scope (a future DR-4 check), but both origins are recorded, so the
comparison needs no new data when it comes.

## 3. One interpreter (ingress/interpret/descriptors.py)

The only code in the system that understands a schema format. It runs as a **pure
fact-stream transform wired into the analyze stage** — exactly where 2F wired config
readers — consuming `embedded_descriptor` facts (from the extractor) and reader output
(§2) before workspace load, and emitting `declared_shape` facts into the fact files.
It never touches the Workspace port, so the ingress write-only contract holds.

**Two-phase, module-wide** (self-review finding): protobuf descriptors import one
another — a message's field types and `json_name`s may live in a dependency's file.
Phase one collects every descriptor payload in the module; phase two builds one
`DescriptorPool`, adds files in dependency order (the pool API requires dependencies
first; unsatisfiable imports record `descriptors_not_interpreted` for that file), and
walks the resolved types. A per-fact interpreter would crash or fabricate on any
multi-file schema.

Per message/record type, one `declared_shape` fact (nested messages included, each its
own shape); per field:

| descriptor says | `shape_fields` gets |
|---|---|
| `name` | `name` |
| `json_name` (read via `FieldDescriptor.json_name` — computed default or explicit override, never computed by us) | `wire_name` |
| `number` | `field_number` (new column, §4) |
| scalar types | `wire_type`/`wire_format` per the mapping table below |
| `message` type | `object` + `shape_id` reference |
| `repeated` | `array` with `item` descriptor |
| `map<K,V>` | `map` with `item` for V |
| `enum` | `enum` with the symbol list |

Type mapping (protobuf → 2A vocabulary): `int32/sint32/sfixed32 → integer/int32`,
`int64/sint64/sfixed64 → integer/int64`, `uint32 → integer/uint32`,
`uint64 → integer/uint64`, `fixed32 → integer/fixed32`, `fixed64 → integer/fixed64`,
`float → number/float`, `double → number/double`, `bool → boolean`,
`string → string`, `bytes → string/byte`.

Presence/nullability: proto3 scalars always materialize on the wire (defaults), so
`required = true`, `nullable = false`; `optional`-keyword fields and message fields
are `required = false`, `nullable = true`; `repeated`/`map` are `required = true`
(empty, never absent) with non-nullable items. Avro: `["null", T]` unions →
`nullable = true`; fields with defaults → `required = false`; record full name is the
shape identity; defaults recorded in the existing `default` slot.

Evidence: `compiler` for compiled-origin shapes (COVERAGE §4.1's strongest tier),
`declared` for source-origin. Failure is a gap, never a crash:
`descriptors_not_interpreted` with the class symbol / file path.

**Descriptor expansion replaces bytecode expansion.** When the shapes pass meets a
payload type that owns a `declared_shape`, it takes the declared fields and never walks
the class's bytecode fields (no `bitField0_` garbage). Precedence is structural: a
type is descriptor-described or field-described, never a blend.

## 4. Schema changes (frozen versions — no bumps, gate rule)

- `shape_fields.field_number INTEGER` — NULL for annotation-derived shapes.
- Shape-level provenance: the declared-shape origin rides the existing shape
  evidence column (`compiler`/`declared`), no new column.
- `endpoints.format TEXT`, `endpoints.format_resolution TEXT`.
- `open_questions` table (§6): pre-declared empty like `endpoints`/`shapes` so the
  query always answers; replaced whole per resolve.
- **Merge and dedup carry the new columns** (self-review finding): `format` and
  `format_resolution` join `merge_endpoints.sql`'s coalesce exactly as
  `consumes`/`produces` did (2F F-4 precedent — the surviving row keeps its own
  answer, else takes the twin's, because the twin is about to be deleted), and every
  derive-time `GROUP BY`/dedup lists them. When the two halves disagree, the
  inbound half's answer survives (it is the richer, handler side — same rule as
  media); resolution takes the weaker of the two markers so a `narrowed` half can
  never launder to `resolved` through a merge.
- D00 closed sets: `format ∈ {json, protobuf, avro, xml, string, bytes}`
  (`json_schema` reserved, refused if a catalog writes it — the 2F reserved-mechanism
  pattern); `format_resolution` reuses the existing resolution set.

## 5. Format inference — the ladder (resolve/format.py)

A new, late resolve pass owning exactly one job: stamp `format`/`format_resolution`
per endpoint row. It runs after media stamping (config_join) and after parse binding
(§6) — the `_RUNS_LAST` ordering precedent — because its rungs read their outputs.
First rung that answers, wins; every row gets a value or an explicit `unresolved`.

**The strongest tier is written `resolved`, everywhere below.** §4 says
`format_resolution` reuses the existing resolution set, and D00 §4 closes that set at
`resolved`/`narrowed`/`partial`/`unresolved` — so an earlier draft's "exact" was prose
for a value that does not exist, and every rung below states the value actually written
(ruled at Task 6).

1. **Fixed by protocol** — grpc → `protobuf`, soap → `xml`, graphql → `json`;
   `resolved`. (Catalog-declared per protocol, not hardcoded: a `format_fixed` entry in
   the catalog's protocol vocabulary — framework and protocol names stay in catalogs.)
2. **Declared media** — the row's `consumes`/`produces` MIME strings, mapped by
   catalog vocabulary (`application/json → json`, `application/x-protobuf` and
   `application/protobuf → protobuf`, `avro/binary → avro`, `application/xml` and
   `text/xml → xml`); `resolved`. **This rung outranks rung 4 by design**: a
   protobuf-typed payload under `produces: application/json` is `format: json` — the
   proto3 JSON encoding, wire names from `json_name`. A row whose consumes and
   produces map to different formats keeps direction-specific truth: format describes
   the wire identity, so when the two sides disagree the row records `unresolved`
   with an `open_questions` entry (§6) rather than picking a side.
3. **Serializer config** — 2F's config_join already stamps serializer classes into
   media; `format_from` catalog vocabulary maps them (COVERAGE §4.1's table as data:
   `KafkaAvroSerializer → avro`, `KafkaProtobufSerializer → protobuf`,
   `KafkaJsonSchemaSerializer → json` today with the reserved value noted,
   `KafkaJsonSerializer → json`, Spring's `JsonSerializer → json`,
   `StringSerializer → string`, `ByteArraySerializer → bytes`); `resolved` — a
   serializer states the wire outright.
4. **Payload hierarchy** — the bound shape is descriptor-described and nothing above
   answered: `format: protobuf` (or `avro`) at **`narrowed`** — suggestive, never
   conclusive, because negotiation we cannot see may put the JSON encoding on the
   wire. A parse-call binding (§6) also feeds this rung: a bound protobuf parse
   lifts a NULL format to `protobuf` at `narrowed`.
5. **Framework default** — an ordinary DTO payload and a JSON default converter
   present (Jackson 2 `com.fasterxml.jackson` or Jackson 3 `tools.jackson` on the
   classpath — either package family, as catalog-declared hierarchy/presence
   evidence): `format: json`, `narrowed`.
6. **Nothing** — `format` NULL, `format_resolution: unresolved`. Kafka with no
   serializer evidence, WebSocket, raw bytes.

## 6. Parse-call binding (resolve/shapes/parse_binding.py) and open_questions

A new focused module — **not** `arguments.py`, which already carries 2F's field
ladder. For endpoints whose payload parameter is bytes-shaped (`String`, `byte[]`,
a catalog-named envelope type), two rungs:

- **Rung A — handler body:** a catalog-matched parse call in the handler whose linked
  argument traces to the handler's payload parameter (2C dataflow, unchanged) binds
  the parse's `payload_type` as `request_shape`.
- **Rung B — one delegation hop:** the handler passes its payload parameter as an
  argument to a module-local method; the callee's body contains a catalog-matched
  parse whose linked argument traces to the corresponding parameter position. The
  one new join: caller argument position → callee parameter position, within the
  module, one hop, never further.

**Both rungs are syntax-level evidence, and neither writes an evidence column.** The
tier describes what the pass read — a call site in the module's own bytecode, never a
declaration — but the binding's only write is `request_shape` (`bind_request_shape.sql`,
a compare-and-set against the bytes shape it read). `endpoints.evidence` stays what the
derivation that created the row put there: it is that row's provenance, and a payload
rebound afterwards is not a different derivation. A per-column trust field for payloads
would be a schema change, and 2G makes none (ruled at Task 7).

**Multi-caller is not ambiguity:** two listeners delegating to the same callee both
bind its parse — both channels' bytes provably reach it. **Real ambiguity refuses to
bind:** one payload reaching two different parses (try-protobuf-else-JSON; a callee
parsing two types from one parameter) binds nothing.

The ledger (user ruling — every miss recorded, the undecidable handed to 2K):

- Named gaps: `payload_parsed_beyond_horizon` (a catalog-matched parse exists in
  the module past the one-hop line, unreachable by rung), `payload_parse_ambiguous`
  — both entries in `metadata.json`'s `KNOWN_GAPS` (rotated whole, never counted),
  not a counter either one increments.
- **`open_questions`** — a workspace table and D06 bundle artifact; one row per
  undecidable binding: the endpoint's wire identity (protocol/method/path), a closed
  `question` kind (`payload_binding`, `format_conflict`), the candidate answers as a
  JSON array, and the evidence trail. **The candidate keys as shipped**: a
  `payload_binding` candidate carries `payload_type`, `hops`, `seen_in` and `why` —
  `why` holds the matched CALL (`…OrderRequest#parseFrom`), and *why no rung reached
  it* is carried by `hops` together with the row's own `evidence` trail, which names
  the refusal (`payload parsed beyond the one-hop horizon`, `payload parse
  ambiguous — one payload, more than one parse`) rather than repeating it per
  candidate. A `format_conflict` candidate carries `format`, `seen_in` and `why`.
  2K's enrichment seat reads this artifact and answers
  at `evidence: llm` as overlay claims (2B §6 contract). Programmatic passes never
  read `open_questions` — it is a hand-off, not an input. Rows are ordered by wire
  identity for NFR-1 determinism.

## 7. Catalog vocabulary (D02)

All names are data; no engine learns a framework or library name:

- `format_fixed` (per-protocol constant format, rung 1) and `media_formats` (MIME →
  format, rung 2) — shipped in the catalogs that own those protocols.
- `format_from` (serializer class → format, rung 3) — extends the 2F serializer
  vocabulary in `spring-kafka-media.yml`.
- `parse_calls` — the shapes rungs A/B match: owner + method + which argument carries
  the bytes + where the payload type lives (static receiver for
  `parseFrom`, the pre-existing `class`-kind argument for `readValue`). Ships with entries for
  protobuf (`parseFrom` on generated types — matched by hierarchy, not name),
  Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper#readValue`) and
  **Jackson 3** (`tools.jackson.databind.ObjectMapper#readValue`,
  `tools.jackson.databind.json.JsonMapper#readValue`) — the relocation is two
  catalog rows, zero code (user ruling), plus Avro `SpecificDatumReader` construction.
- `json_default_markers` (rung 5): both Jackson package families.

## 8. Rendering, export, docs, README

- **Renderer (D06):** Format joins the endpoint detail beside Media, rendering the
  resolution honestly (`protobuf` vs `protobuf (assumed)` for `narrowed`; NULL
  renders `unresolved` — the 2E precedent). An "Open questions" section renders the
  `open_questions` rows so a human sees the 2K inbox in the document itself.
  Declared shapes render through the existing shape rendering unchanged —
  `field_number` shows where present.
- **Export:** `open_questions` joins the D06 bundle and its manifest;
  `field_number`, `format`, `format_resolution` ride the existing tables' exports.
- **metadata.json:** named `KNOWN_GAPS` entries for `payload_parsed_beyond_horizon`
  and `payload_parse_ambiguous` (§6), plus the two analyze-side gap-name lists,
  `schema_sources_not_compiled` (§2) and `descriptors_not_interpreted` (§3) — every
  one listed in full by name, never counted.
- **README** (user requirement): a Dependencies section — Python side (`uv sync`;
  `protobuf` and `grpcio-tools` now among the pinned dependencies and why), JVM
  extractor build (unchanged — deliberately no new dependency), fixture toolchain
  (protoc arrives via the Maven plugins; nothing installed by hand).
- **Docs:** D00 (two fact kinds, `declared_shape` made real, cross-language contract
  sentences — no argument-kind addition, `class` being 2C-era and unchanged);
  D02 (§2c ladder completed, the four vocabularies of §7); D06 (`open_questions`
  artifact); COVERAGE (protobuf/Avro row flips, Jackson 3 row, honesty boundaries:
  beyond-horizon, drift check deferred, registry subjects deferred, gRPC service
  extraction deferred).

## 9. Dependencies (GUIDELINES §7 — approved in brainstorm)

- Python: `protobuf` (descriptor parsing; `FieldDescriptor.json_name` is the
  authority for wire names — data we read, never an algorithm we implement) and
  `grpcio-tools` (compiling `.proto` source files to descriptors). Both pinned.
- JVM extractor: **no new dependency** — ASM harvests constants; that was the point
  of the layering.
- Fixture build: `protobuf-maven-plugin` + `avro-maven-plugin` in
  `orders-service/pom.xml`, and — fixture-only, user-ruled — the
  `tools.jackson.core:jackson-databind` artifact, so the Jackson 3 `parse_calls` rows
  (§7) are matched against a real relocated call site in compiled bytecode rather than
  only against an invented owner in a unit test. Nothing in `src/` depends on it.

## 10. Fixtures and the proof obligations

`orders-service` gains `src/main/proto/order.proto` — **keeping the hostile-comment
fixture** (unicode, emoji, near-terminator `*/` sequences, comments containing fake
`option` directives) as the regression pin (user requirement; the whole chain protoc →
embedded descriptor → interpreter stays proven) — with `total_amount` (computed
`totalAmount`), an explicit `json_name` override, a nested message, a map, an enum,
an import across two `.proto` files (pinning §3's two-phase pool); and
`src/main/avro/audit.avsc` with a `["null", T]` union and a defaulted field.

New fixture surfaces: a REST handler returning the protobuf type under
`produces = application/json` (rung 2 beats rung 4); a Kafka listener whose
serializer config says `KafkaProtobufSerializer` (rung 3); an SQS handler with a
rung-A `parseFrom`; a delegated rung-B parse; a two-parse ambiguous handler feeding
`open_questions`; a `tools.jackson` readValue site (Jackson 3 pin); a source-only
`.avsc` no generated class references (source-origin shape); and the existing
JSON endpoints untouched (rung 5 assumed rows).

Structural/architecture tests: ingress still write-only; only
`ingress/interpret/descriptors.py` imports `google.protobuf`; determinism
(double-run byte-identity over the new tables); exact-list pins from live fixture
runs only.

## 11. Out of scope, stated

Schema-registry subject derivation (re-derivable later from topic + serializer we
already keep); embedded-vs-source drift comparison (both origins recorded, so the
future check needs no new data); gRPC service extraction from descriptors (a
protocol phase, not a format phase); JSON Schema and XSD (`json_schema` reserved in
the closed set); parse tracing past one hop (ledgered + 2K hand-off instead).
