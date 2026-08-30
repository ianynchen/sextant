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

Written once per class file. Every fact points at one.

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

**One class file is one document — a nested or anonymous class's own `.class` file
included.** `document_id` stays the sha256 of the **class-relative path**
(`com/acme/orders/OrderResult$Detail.class`), so `OrderResult` and its nested `Detail`
never collide on one id. `relative_path` instead points at the **outer source file** —
`OrderResult$Detail.class` produces a document whose `relative_path` is
`com/acme/orders/OrderResult.java`, because that is the file a human edited and the file
`content_hash` fingerprints. The two fields answer different questions on purpose: one
keeps ids unique per class file, the other keeps source mapping honest.

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

**`protocol`** — `http`, `soap`, `grpc`, `kafka`, `jms`, `sqs`, `pubsub`. `message` is
retired: it was reserved and never declared by any shipped catalog, so nothing migrates.
The broker family is the protocol because linking gates on protocol equality (DR-5), and
a Kafka topic can never be answered by an SQS queue.

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
| `symbol` | Identifier, construct kind, enclosing symbol, **typed signature** (§5a), visibility, **declaration modifiers** (§5a), range | Symbol graph, shapes, endpoints, class diagrams |
| `relationship` | Subject, object, relationship kind | Hierarchy, dispatch, class diagrams |
| `occurrence` | Symbol, range, enclosing symbol, role | Type-reference edges, `uses` |
| `annotation` | Target symbol, annotation symbol, **argument values**, retention, and — for a type-use annotation on a field or a type — **`type_path`** locating it within the type reference | Every endpoint engine |
| `call_site` | Caller, target (owner, name, descriptor), `invoke_kind`, `ordinal` — the v1 control-flow position — `receiver`/`result` value ids, structured `arguments` | Call edges, dispatch, traces, endpoints |
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

**A field symbol also carries the declaration modifiers that decide whether it reaches a
payload at all**, as `modifiers.static` and `modifiers.transient` — a value bound to the type
rather than to an instance, and a declaration the language marks as not serialized. Neither
is visibility and neither is nullability: a public constant is as public as any field and is
on no payload, so a shape pass filtering on what it already had would have to guess. Both
flags are always written on a field fact, because an absent one cannot be told apart from a
scanner that does not report the modifier. **A compiler-synthesized field is not a
declaration and produces no fact at all** — a modifier would say "somebody wrote this and it
stays off the wire", where the truth is that no source file contains it.

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

**A class symbol fact also carries its generic supertype reference, when the superclass
signature is generic.** `new ParameterizedTypeReference<List<OrderView>>() {}` compiles to
an anonymous class whose signature names that parameterized supertype, and the fact records
it as a type reference (above), never as a string — the same recursive shape a field or a
parameter carries, run once more here. This is the PTR carrier: a catalog-declared
`type_carrier` ([D02](D02-catalog-schema.md) §2h) resolves `List<OrderView>` through this
field rather than through the anonymous class's own declared type, which names nothing. An
ordinary, non-generic superclass carries no such field — there is nothing generic to
capture, and the relationship is still stated once, at `relationship_kind: extends` (§4).
This also pre-feeds `inherits` edges ([D01](D01-graph-schema.md)).

**A class symbol fact also carries the erased symbols of every interface it implements, in
declaration order, as `interfaces` — emitted only when non-empty** (the `implemented_interfaces`
capability, [M03](M03-scanner.md)): a receiver registered by its declared type (`new
PubSubReceiver(subscription, new RawPubSubReceiver())`) names no method by itself, and
`interfaces` is what lets a catalog join that type back to the single method the interface
declares.

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

**An enumeration reaches the wire as `enum`, never as a record.** A type reference cannot say
which of the two it points at, so the answer comes from the referenced type's own
`construct_kind` (§4) — generic fact data, which is why the language-blind half may read it.
Expanded structurally the constants backing it become fields of a payload nobody sends; left
as the `object` its reference calls it, it marks its owner open and is reported as a gap in a
catalog that is missing nothing.

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

The full shape, verbatim:

```json
{"kind": "call_site", "document_id": "…", "caller": "<method symbol>",
 "target": {"owner": "org/springframework/web/client/RestTemplate#",
            "name": "postForObject", "descriptor": "(…)…"},
 "invoke_kind": "virtual",
 "ordinal": 14,
 "receiver": 3, "result": 7,
 "arguments": [
   {"kind": "string", "value": "/billing/invoices"},
   {"kind": "unresolved", "source": 7},
   {"kind": "class", "symbol": "com/acme/orders/contracts/OrderView#"}]}
```

**`target.descriptor`** makes the target unambiguous. `owner.name` alone collides; two
methods named `execute` are not the same method.

**An `invokedynamic` has no receiver, so its `target.owner` names the bootstrap method's
owner** — `LambdaMetafactory`, `StringConcatFactory` — because that is the thing that says
what the site means, where the instruction's own name and descriptor describe only the call
site's signature. A `dynamic` site is recorded like any other: skipping it would leave every
`source` pointing at it dangling, and a string concatenation is a real producer.

**`invoke_kind`** is one of `virtual`, `static`, `interface`, `special`, `dynamic` — the
five JVM dispatch forms — plus `throw`, which the row above already names: a throw site is
a call-site-shaped observation whose target is the thrown exception type, and it is what
gives traces their `throws` terminal.

**`ordinal`** is the invoke's index within its method, assigned in instruction order and
therefore deterministic (NFR-1). It is **the v1 of the control-flow position** this schema
has always reserved a field for — enough for the call-graph phase to start from these
facts. It is not the richer context a sequence diagram needs to show a `loop` or an `alt`
without lying about it (§8 of `GUIDELINES.md`): that structure — region, branch, depth —
remains an **enrichment of this same field in a later phase**, and [D01](D01-graph-schema.md)
§7's schema versioning prices that re-extraction openly rather than pretending it is free.

**`receiver` / `result`** are per-method value ids from a dataflow pass over the method's
bytecode — `receiver` is null for a static call, `result` is null for a void one. They are
**deliberately meaningless across methods**: chain reconstruction is a within-method join,
and a chain that crosses a method boundary stops honestly rather than being stitched by
proximity.

**`arguments`** carries one entry per argument slot, resolved by walking the frame back to
each slot's source instruction. Without it, every endpoint path is unresolved — this is why
annotation arguments and call literals are first-class fields rather than something
recovered later. Kinds:

| Kind | Source instruction | Notes |
|---|---|---|
| `string` | LDC (incl. javac-folded constants) | the URL/topic carrier |
| `int` / `long` / `boolean` | constant instructions | |
| `enum` | GETSTATIC of a **named constant of its own type** | symbol reference — `HttpMethod.POST`. Structural, not `ACC_ENUM`: an enum-like — a closed set of static final constants typed as their own owner — reads as `enum` here too, deliberately, because libraries move between the two spellings without changing what a constant means. A Kotlin `object`'s `INSTANCE` and constants such as `BigDecimal.ZERO` match the same shape; the referenced type's own `construct_kind` settles true enum-ness (§5b), so the distinction is a join away rather than a guess made where the answer is not available |
| `class` | LDC of a class constant | symbol reference — the shape root |
| `lambda` | invokedynamic via `LambdaMetafactory` | symbol reference to the lambda's synthetic body method — method references resolve the same way |
| `instance` | NEW/constructor result | the concrete type's symbol — feeds PTR (§5a) and the one-hop body follow ([D02](D02-catalog-schema.md) §2h). Always carries `source`: the constructed value's id, which is also the `receiver` of that object's own `<init>` call site, so the follow is a join on one number rather than a search for a nearby constructor |
| `null` | ACONST_NULL | |
| `unresolved` | anything else | a first-class honest answer, never an omission |

Every entry additionally carries an optional **`source`** value id when the argument is
itself another call's result — the join that makes OkHttp's `build()` → `newCall(request)`
split reconstructable, and the `HttpEntity` one-hop follow possible. One grammar, three
consumers: the argument's own kind, the chain join, and the wrapper follow all read the
same entry.

**Producing all of this from bytecode is real work** — see [M03](M03-scanner.md), which
owns the problem and its scope.

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
