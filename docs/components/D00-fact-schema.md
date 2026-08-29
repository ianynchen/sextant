# D00 — Fact schema and identity

The contract between everything that reads code and everything that derives from it.
Written by [M03](M03-scanner.md). Read by [M04](M04-resolver.md).

This is the most consequential document in the project. A new language, a better scanner,
or a new artifact format is a new producer of these same facts, and touches nothing
downstream. If this schema is right, those additions are additive. If it is wrong, no
interface elsewhere saves us.

---

## 1. Identity

Every symbol is named with the **SCIP symbol grammar**. This is a string format, not a
tool — no indexer is involved. See [ARCHITECTURE.md](../ARCHITECTURE.md) DR-1.

```
<scheme> <package-manager> <package> <version> <descriptors>

sextant-jvm  maven  com.acme/orders  2.1.0  com/acme/OrderService#save().
sextant-jvm  maven  com.acme/orders  2.1.0  com/acme/OrderService#save(+1).
```

**Descriptor grammar**, unchanged from SCIP:

| Suffix | Means |
|---|---|
| `/` | namespace or package |
| `#` | type |
| `.` | term — a field or a value |
| `().` | method |
| `(<disambiguator>).` | one overload among several |
| `local <n>` | a symbol confined to one document |

**Where a field has no meaning, write `.`** — an unpublished service has no package
manager, package or version.

### Rules

**Content-derived.** The identifier is a function of the entity, never of the order in
which it was found. Two runs produce the same string; two modules seeing the same library
type produce the same string. This is what NFR-3 requires and what makes blast radius work
across a system.

**Overloads are disambiguated by descriptor hash**, never by an ordinal. An ordinal changes
when a sibling is added.

**Short forms are prefixed.** Every identifier shown to a person or written into a file a
person edits carries a type prefix — `sym_3f8b`, `ep_7c1a`. Bare hexadecimal is never
emitted, because it is coerced to a number by YAML and by spreadsheets.

---

## 2. The document record

Written once per source file. Every fact points at one.

| Field | Meaning |
|---|---|
| `document_id` | Interned |
| `relative_path` | Within the module |
| `module_id` | From [M02](M02-detector.md) |
| `language` | The language of this document |
| `sextant_version` | **The tool that produced these facts** |
| `fact_schema_version` | **The version of this document's schema** |
| `scanner_id` | Which scanner produced these facts |
| `scanner_version` | |
| `content_hash` | Of the source of truth this was read from |
| `origin` | **The classpath entry this was read from, and that entry's tier** — module output, first-party, third-party |
| `redaction_set_hash` | From [D04](D04-config-and-exclusion.md) |
| `partial` | True when the file was analysed incompletely, with a reason |

**Language, tool and version live here, never on a fact.** A fact that needed its own
language field would mean the schema was not language-neutral (NFR-7). Putting the versions
here rather than on every fact costs one row per source file instead of one field per fact,
and the source file is the unit of incremental reuse, which is exactly where the question
"can I keep this?" is asked.

`scanner_id` exists because multiple scanners per language is a supported operation. It is
what allows two scanners to be compared.

**`origin` is recorded here because this is the moment it is a fact.** The scanner is
holding the jar it read the class from, and [M02](M02-detector.md) already tiered that
classpath entry. Every downstream question of the form "is this symbol first-party?" —
noise filtering in diagrams and answers, the `narrowed`/`partial` boundary — reads this
field. **Package names are never pattern-matched to decide it**: group patterns classify
artifacts in M02, and shaded or oddly-grouped jars would make any name-based inference
silently wrong.

**`sextant_version` and `fact_schema_version` are here because a result can change when the
tool changes, even when the code does not.** A fixed bug in extraction produces different
facts from an identical class file. Every field in this table is part of the cache key; see
[D01](D01-graph-schema.md) §7 for what each one invalidates.

---

## 3. Trust fields

Three concepts, **two stored fields**. Never collapsed into one. See
[ARCHITECTURE.md](../ARCHITECTURE.md) DR-3.

| Field | Values | Stored |
|---|---|---|
| `resolution` | `resolved`, `narrowed`, `partial`, `unresolved` | Yes |
| `evidence` | `compiler`, `syntax`, `name_match`, `declared`, `human`, `llm` | Yes |
| `precedence` | 90 human, 50 code, 10 model | **No — derived** |

`unresolved` always carries a `reason`. `narrowed` and `partial` always carry
`candidates`.

**Precedence is a pure function of evidence** — `human` → 90, `llm` → 10, everything else →
50 — held as a fixed table in `domain/` and applied by [M01](M01-overlay.md) at
conflict-resolution time. It is policy, not observation: storing it per fact would make
illegal states representable (`evidence: human, precedence: 10`) and would freeze the rank
table into every published bundle, so that a policy change required re-extracting the
estate. This is §9's no-derived-values rule applied to this schema's own fields. Should two
same-evidence sources ever need different ranks, the fix is a richer evidence value — never
a hand-set number per row.

**`narrowed` versus `partial`** is decided by visibility, not by judgement: if nothing
outside the indexed set can extend or implement the type, the candidate set is complete.
The indexed set is defined by [M02](M02-detector.md).

---

## 4. Closed sets

Each is fixed and enumerated here (NFR-5). **Adding a value is a schema change that
invalidates every existing analysis and requires re-extraction.** Language-specific detail
goes in `ext`, never into a widened set.

**`resolution`** — `resolved`, `narrowed`, `partial`, `unresolved`

**`evidence`** — `compiler`, `syntax`, `name_match`, `declared`, `human`, `llm`

**`unresolved_reason`** — `interface_dispatch`, `abstract_dispatch`, `reflection`,
`di_container`, `dynamic_proxy`, `config_placeholder`, `unindexed_dependency`,
`scanner_gap`

**`construct_kind`** — `class`, `interface`, `struct`, `trait`, `protocol`, `enum`,
`record`, `alias`, `method`, `function`, `constructor`, `accessor`, `field`, `module`

**`relationship_kind`** — `extends`, `implements`, `type_of`

**`root_kind`** — `http_inbound`, `soap_inbound`, `grpc_inbound`, `message_inbound`,
`scheduled`, `cli_entry`

**`terminal_kind`** — `outbound_call`, `returns`, `ends_silently`, `persistence`,
`throws`, `unresolved`, `async_handoff`, `cycle`

`persistence` carries `target_kind`: `database`, `cache`, `file`. A sub-field, so that
splitting it later is a rendering choice rather than a re-index.

**`protocol`** — `http`, `soap`, `grpc`, `message`

**`control_flow_kind`** — `sequential`, `conditional`, `alternative`, `loop`, `handler`

**Two values have no version-1 fact producer, deliberately.** `syntax` is the day-one
on-ramp for a second language's tree-sitter tier; `llm` is required by
[M01](M01-overlay.md)'s claim machinery even though model overlays never become facts. Both
are retained by declared intent — this note exists so neither reads as dead and gets
removed.

---

## 5. Fact kinds

Thirteen. Every one exists because a stated requirement consumes it (NFR-6).

| Kind | Carries | Consumed by |
|---|---|---|
| `module` | Identifier, kind, languages, source sets, output directories, **classpath tiering**, active catalogs | Dispatch tiering, noise filtering, coverage |
| `symbol` | Identifier, construct kind, enclosing symbol, **typed signature** (§5a), visibility, range | Symbol graph, shapes, endpoints, class diagrams |
| `relationship` | Subject, object, relationship kind | Hierarchy, dispatch, class diagrams |
| `occurrence` | Symbol, range, enclosing symbol, role | Type-reference edges, `uses` |
| `annotation` | Target symbol, annotation symbol, **argument values**, retention, and — for a type-use annotation on a field or a type — **`type_path`** locating it within the type reference | Every endpoint engine |
| `call_site` | Caller, target owner, name, descriptor, invoke kind, **control-flow position**, literal arguments | Call edges, dispatch, traces, endpoints |
| — | The invoke-kind set includes **`throw`**: a throw site is a call-site-shaped observation whose target is the thrown exception type. It is what gives traces their `throws` terminal. | Trace terminals, blast radius |
| `constant` | Symbol, value | Topic and URL resolution |
| `string_literal` | Document, range, enclosing symbol, value | Endpoint literals, log-line search |
| `config_entry` | Key, raw value, source file, profile | Configuration resolution |
| `dependency` | Coordinates, scope, tier | Classpath tiering, library identity |
| `deployment` | Service name, ports, kind, source | System linking |
| `declared_contract` | Protocol, wire identity, references to `declared_shape` facts, **whether the build consumes it** | Endpoint catalog, drift |
| `declared_shape` | Shape identity, owning contract, fields — wire name, **field number where the format has one**, wire type, required, default | Drift comparison, gRPC and message matching, DR-4's embedded-descriptor check |

### 5a. Typed signatures and type references

**Signatures are structured, never display strings.** A method symbol carries an ordered
parameter list — each entry holding the parameter's name where the class file provides it,
its **type reference**, and its annotations inline — plus a return type reference. A field
symbol carries its type reference the same way. This is where "the request body is the type
of the parameter annotated `@RequestBody`" becomes a field read rather than a positional
join, and where a parameter's annotations attach without the parameter needing a symbol of
its own. (The SCIP parameter descriptor exists for the rare case of naming one from
outside — a curation, say — and is deferred until something needs it.)

**A type-use annotation attaches to the type reference it annotates, not to a flat fact.**
A method has more than one type reference — the return type, and each parameter — so the
annotation alone does not say which one it belongs to the way a field's single reference
does; only the position it was read from does. A parameter's entry therefore carries a
`type_annotations` list alongside its declaration-level `annotations`, and the signature
carries a `return_type_annotations` list alongside `returns`, each entry holding the
annotation `use`, `retention`, and `type_path` — the same three things a flat `annotation`
fact carries for a type-use annotation on a field, minus the target it would otherwise need
to name. Collapsing "the return type is nullable" and "the parameter is nullable" into one
undifferentiated fact is the ambiguity this placement exists to remove.

**A type reference is a symbol reference plus optional type arguments, recursively.**
`List<OrderLine>` keeps `OrderLine`; `Mono<ResponseEntity<OrderResult>>` keeps the whole
chain, verbatim. **The scanner records what the descriptor says and never unwraps.**
Whose knowledge is it that `Mono<T>`'s wire payload is `T`? Reactor's — framework
knowledge, so unwrapping is catalog data ([D02](D02-catalog-schema.md)) applied by
[M04](M04-resolver.md) at shape-rooting time, never baked into facts. Occurrences keep a
deliberately small role set — `read`, `write`, `import`, `generated`, `type_use` — for
body-level uses only; signature-level type uses come from the structured signatures.

**Presence and nullability are two independent flags, and both are two-valued.** A field
either accepts null or it does not; a field either has to appear or it does not. Neither
carries an `unknown` value — doubt about what we managed to work out is what `resolution` and
`evidence` (§4) are for, and duplicating them inside the value would let one fact disagree
with itself.

| | Means | Decided by |
|---|---|---|
| `required` | The field must be **present** in the payload | The contract |
| `nullable` | If present, its value may be **null** | The type |

**All four combinations are real, which is why one flag cannot serve.** JSON distinguishes a
field that is absent from a field present with value `null` — the same distinction JavaScript
draws between `undefined` and `null` — and OpenAPI models them as separate keywords for that
reason: membership of the `required` array, versus `nullable: true` in 3.0 or
`type: ["string", "null"]` in 3.1, which dropped the keyword to align with JSON Schema. A
field may be required-and-nullable (must appear, may be null) or optional-and-not-null (may be
absent, but never null when present).

**Nullability sits on the type reference**, so it reaches parameters and class members through
the same route their types do (§5a) — `@Nullable List<String>` is not `List<@Nullable String>`,
and only a per-reference value distinguishes them.

**In most languages the type system already answers it.** Kotlin's `String?`, Rust's
`Option<T>`, Swift's `T?`, TypeScript's `T | null`, and a Go pointer versus a value all decide
it outright. **Java is the awkward one**: every reference type is nullable by language rule, so
the ecosystem uses annotations to say "actually not" — and the same concept is spelled
`org.jspecify.annotations.Nullable`, `org.springframework.lang.Nullable`,
`javax.annotation.Nullable`, `jakarta.annotation.Nullable`,
`org.jetbrains.annotations.Nullable` and `androidx.annotation.Nullable`. Which spelling counts
is framework knowledge, so it is catalog data ([D02](D02-catalog-schema.md) §2e), never a list
in the scanner.

**Where the language's type system decides, the fact records that answer at `resolution:
resolved`.** Java's type system settles nullability outright: every reference type permits
null and every primitive forbids it. An unannotated Java reference field is `nullable: true`
at `resolution: resolved`, exactly as a primitive is `nullable: false` at `resolution:
resolved` — a consumer must handle null whether or not anyone wrote `@Nullable`, so the fact
is certain, not a weaker claim awaiting confirmation. `resolution` is not a stand-in for "was
this declared": [CONTEXT.md](../../CONTEXT.md) defines it as how certain a fact's *target* is,
with candidate-set semantics (`narrowed` — several targets, set complete; `partial` — several
targets, set incomplete) that a boolean has no analogue for, and `unresolved` is reserved for
a language where no type exists to answer the question at all — it does not arise on the JVM.
Whether anyone *declared* intent is a real, separate question, answered by counting annotated
fields against unannotated ones — it does not need its own per-fact flag, and one would make
every unannotated Java field look uncertain and downgrade every link built on it.

**Kotlin's nullability is in its type system, not an annotation**, so it arrives through
`ext.kotlin.nullable` (§6) — but the adapter **projects it into the shared field** rather than
leaving it in the extension. Nullability crosses languages; anything DR-5 compares cannot live
behind an extension read boundary.

**Literal values have a typed model**: string, number, boolean, enum reference, **class
reference — captured as a symbol reference, not a string** — and arrays of these. This is
what lets a catalog's `response_arg: 2` on `postForObject(url, req, OrderResponse.class)`
resolve to a real shape root.

### 5b. The wire-type vocabulary

Shapes from code and shapes from contracts must be comparable field by field, so both
project into one small vocabulary — **the set of things serialisation actually
distinguishes**: `string`, `integer`, `number`, `boolean`, `bytes`, `array`, `map`,
`object` (a reference to another shape), `enum` — each with an optional format qualifier
(`int64`, `date-time`, …). Code shapes project into it from typed signatures (§5a);
declared shapes arrive in it already, because it is what schema formats natively say. A
Java `long` and an OpenAPI `integer/int64` meet in the middle as `integer/int64`. This
vocabulary is a closed set, and it is the comparison level of DR-5's structural matching
and FR-11's drift report — never Java types against spec types directly.

**A code shape's `required` is derived from presence rules, not from nullability.**
`declared_shape` fields carry it because schema formats state it outright — OpenAPI's
`required` array, protobuf field presence, an Avro union carrying a default. A shape rooted
from code works it out from the presence machinery its language offers: a `wrapper` declared
`optional` such as `java.util.Optional`, a TypeScript `?`, a Pydantic or Kotlin default
argument, `serde`'s `skip_serializing_if`, Go's `omitempty`, Jackson's
`@JsonProperty(required = true)`.

**Do not read a nullability annotation as a presence rule.** They answer different questions,
and Bean Validation's `@NotNull` is the trap: it constrains the *value* at validation time and
says nothing about whether the field may be omitted from the payload.

**DR-5 compares both flags, and must report a comparison that leaned on a partial one.** A
request contract missing a field the callee requires is a real defect; a contract whose
`required` we only inferred from a language default is not evidence that it is safe. That is
the general `resolution` rule, not a special case for nullability.

### Why `module` is a fact and not a passing argument

[M02](M02-detector.md) works out the module inventory and the classpath tiering, and
[M03](M03-scanner.md) uses them. It would be easy to leave that in memory between the two.

It cannot be. **Three later components need it and never see [M02](M02-detector.md).**
[M04](M04-resolver.md) needs the indexed-set boundary to decide `narrowed` against
`partial`. [M07](M07-renderer.md) needs origin tiers to filter noise.
[M08](M08-exporter.md) must carry it in a bundle so [M06](M06-stitcher.md) can use it on
another machine. A stage resumed with `--from-stage` never runs the detector at all.

So the detector's conclusions are facts like any other, and travel like any other.

### `call_site` is the load-bearing one

Three of its fields deserve emphasis:

**`descriptor`** makes the target unambiguous. `owner.name` alone collides; two methods
named `execute` are not the same method.

**`literal_arguments`** carries the argument values a scanner could resolve — the URL, the
topic name. Without it, every endpoint path is unresolved. This is why annotation arguments
and call literals are first-class fields rather than something recovered later.

**`control_flow`** carries the position of the call within the method's control flow:

```
{ kind: alternative, region: 3, branch: 1, depth: 2 }
```

Two calls sharing a region with different branch numbers are alternatives; they never both
happen. A call inside a `loop` region happens zero or more times. Without this field a
sequence diagram lists four calls in source order and claims all four occur, which is the
lying diagram `GUIDELINES.md` §8 forbids.

**Producing it from bytecode is real work** — see [M03](M03-scanner.md), which owns the
problem and its scope.

---

## 6. The extension namespace

Any fact may carry `ext.<lang>`:

```
ext.jvm    { descriptor, retention, access_flags }
ext.kotlin { nullable, is_data_class, default_arguments }
```

**Read boundary:** only the adapter owning a language may read that language's namespace.
Enforced by an architecture test, not by convention.

This is the pressure valve that keeps the closed sets closed.

---

## 7. Storage

Facts are written as JSONL, one file per **source file**, mirroring the source path under
the workspace. Inner and anonymous classes produce separate class files but always change
together, so the source file is the unit of change.

A class file with no source attribution cannot be partitioned this way. It goes to a
reserved partition and is counted, never dropped silently.

Module-level facts — the `module` kind, and any other fact that corresponds to no source
file — go to a reserved `_module.jsonl` partition, cache-keyed by the build inputs that
produced them rather than by a source file's content hash.

---

## 8. Validation

The schema is expressed as validated definitions and enforced **when a fact is written**,
not when it is read (NFR-10). This document is generated from those definitions.

A fact that fails validation is an error that stops the run. It is never written, and never
skipped with a warning.

---

## 9. What this schema must not contain

- **No language names outside `ext`.** A field meaning one thing for Java and another for
  Go is a schema defect.
- **No tool names on facts.** They live on the document.
- **No derived values.** If it can be computed from other facts, it is [D01](D01-graph-schema.md)'s
  concern, not this one.
- **No prose.** Summaries and purposes are overlays.
- **No unredacted secret values.** Redaction runs before a fact is written; see
  [D04](D04-config-and-exclusion.md).

---

## 10. Open decisions

| Decision | Blocks |
|---|---|
| The exact field list and types of each kind — §5a settles signatures, type references, occurrence roles and the literal value model; the remainder is detail | Freezing the schema |
| Whether `control_flow.region` is a flat integer or a nested path | M03 and sequence diagram fidelity |
