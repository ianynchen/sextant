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
| `fact_schema_version` | **The version of this document's schema** — a single monotonically increasing INTEGER, not semver (Step 0). Compared for equality and nothing else; it is never parsed or ordered, so the dotted form carried two extra numbers that meant nothing and let four producers of the stamp disagree unnoticed |
| `scanner_id` | **Which FACILITY produced these facts** — never the library it used. There is no `scanner_version` beside it: a facility Sextant ships moves with `sextant_version` above, and the third-party libraries that CAN move on their own (ASM, kotlin-metadata-jvm) are recorded once per workspace in `metadata.json`, not repeated on every document one scanner wrote |
| `class_release` | **Which COPY of an overlaid class this is** (JEP 238): `base` for the archive root — and for anything that is not a class in a multi-release jar — or the release its `META-INF/versions/N/` prefix declares. A TAG, never a selection: which copy actually loads depends on the release the DEPENDING module targets, so one scan of a jar serves modules targeting different ones and the choice is made downstream |
| `annotation_default` | **What an annotation type's element falls back to** when a use omits it (JVMS 4.7.22). A `LiteralValue` — the same grammar an annotation's arguments use, because a default can be an array, an enum reference or a nested annotation. Present only on such an element and only where it has a default; absent everywhere else, and an absent key must not read as "defaults to nothing" |
| `class_name` | **The class file's own name with any overlay prefix removed** — what the JVM knows the class by, and the key two copies of one class are recognised as copies on. `relative_path` cannot serve: it is the SOURCE path, and a nested class shares its outer's |
| `content_hash` | Of the source of truth this was read from |
| `origin_entry` | **The classpath entry this was read from** — the module's own output directory, or a library archive |
| `origin_tier` | That entry's tier (§4) — module output, a declared dependency, first-party, third-party, platform |
| `origin` | The **library** this document was extracted from, as its coordinate (`com.example:orders-soap-client`). Absent for the module's own output |
| `redaction_set_hash` | From [D04](D04-config-and-exclusion.md) |
| `partial` | True when the file was analysed incompletely, with a reason. **Real since Step 1** — the JVM extractor wrote the literal strings `false`/`null` with no code path able to set either, so every class document claimed a complete analysis whether or not it had one. Three producers: an ARCHIVE ENTRY that could not be read, a class this build cannot parse, and a class whose language-metadata a newer compiler wrote in a form it cannot decode (scanned, facts emitted, nullability missing) |
| `class_major` | **The class-file format version this document was read from** (JVMS 4.1's `major_version`, bytes 6-7). Read from the FILE, never from ASM's constant set — that set runs ahead of the reader shipped beside it, so it would answer for a class this build cannot parse, which is the one case this field exists to describe. `0` where the source is not a class file: the format starts at 45, so 0 cannot be mistaken for a real version |

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

**Origin is recorded here because this is the moment it is a fact.** The scanner is
holding the jar it read the class from, and [M02](M02-detector.md) already tiered that
classpath entry. Every downstream question of the form "is this symbol first-party?" —
noise filtering in diagrams and answers, the `narrowed`/`partial` boundary — reads this
field. **Package names are never pattern-matched to decide it**: group patterns classify
artifacts in M02, and shaded or oddly-grouped jars would make any name-based inference
silently wrong.

**`origin` is written only where there is a library to name**, and it is then the
coordinate M02 resolved the archive from — never a path, so it survives being read on a
machine whose local repository lives somewhere else. A document from the module's own
output carries **no `origin` key at all** rather than one spelled null: a module with no
library extraction configured produces exactly the fact files it produced before opt-in
library extraction existed, which is what makes "did enabling this change my module's
facts?" answerable by comparing bytes.

**`origin_tier` moves with it, to `dependency`.** A class this module did not build is
not `module_output`, and saying so would be a claim known to be false. `dependency` is
what the analysis actually observed — the class came out of a declared dependency's
archive — and deliberately not `first_party` or `third_party`, which answer a different
question (*whose* dependency) from the group patterns [D04](D04-config-and-exclusion.md)
§2 declares and nothing yet implements. A tier is a factual origin; it is never a trust
guess.

**A version is recorded only where the thing can move INDEPENDENTLY of Sextant** (Step 1).
`sextant-config-reader` and `sextant-detector` ship inside the wheel, so they carry no
version of their own — `sextant_version` beside them is it, and the `"0.1.0"` each used to
stamp was a hand-maintained copy of that number which had never once differed from it. The
JVM extractor is the exception that proves the rule: it runs ASM and kotlin-metadata-jvm in
a subprocess, those move on someone else's release cycle, and their RESOLVED coordinates are
what `metadata.json` records. The field that used to sit here read `"9.18"` — capability 9.18
wearing a library version's name, while the pinned ASM was 9.10.1 — which is exactly what a
version field means when it names something that cannot independently move.

**What a scanner can READ is likewise declared by the scanner, never by the caller**
([D02](D02-catalog-schema.md) §3). The JVM extractor answers `--capabilities` over the same
subprocess contract it answers a scan on, so a jar built by an older `./gradlew build`
reports fewer capabilities and the catalogs needing them are reported skipped — the visible
degradation [M04](M04-resolver.md) already defines — instead of running against fact kinds
that jar never emitted.

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

**`method_resolution`** — `declared_here`, `inherited`, `ancestor_not_scanned`,
`owner_not_scanned`, `no_declaration_found`. Why a call site's target does or does not
reach a body (JVMS 5.4.3.3, F3 §4.2). Distinct from `unresolved_reason` above, which
says why a TRACE stopped; this says what the method lookup itself found. One word used
to do the first four jobs at once, and the third of them — a method declared on a
superclass the workspace HAS scanned — was false rather than imprecise.

**`construct_kind`** — `class`, `interface`, `annotation`, `struct`, `trait`, `protocol`, `enum`,
`record`, `alias`, `method`, `function`, `constructor`, `accessor`, `field`, `module`

**`origin_tier`** — `module_output`, `dependency`, `first_party`, `third_party`,
`platform`. Where a document's class file was read from (§2). `dependency` is the tier
of a declared dependency's own archive, read because the module opted into it
([D04](D04-config-and-exclusion.md) §2a); it says the class came out of a dependency and
nothing about whose. `first_party`/`third_party` answer that second question from
declared group patterns, and until those are read no producer writes either — a tier is
an observation, never a trust judgement.

**`relationship_kind`** — `extends`, `implements`, `type_of`

**`root_kind`** — `inbound_endpoint`, `scheduled`, `entry_point`. What kind of thing a
trace starts from, and the set is `CONTEXT.md`'s own three: "an inbound endpoint, a
scheduled job, or a program entry point". Produced by `application/resolve/roots.py` into
[D01](D01-graph-schema.md) §3's `roots` since 2Q's `I1` — before which this set had no
producer at all and was entry #7 of
`open-issues.md` OI-83.

*It read `http_inbound`, `soap_inbound`, `grpc_inbound`, `message_inbound`, `scheduled`,
`cli_entry` until `I1`, and four of those six were one member spelled once per protocol.*
**Protocol is a property of an endpoint, not a second kind of root** (`CONTEXT.md`): an
inbound `endpoints` row already carries it, so a per-protocol root kind is the same value
in two places with nothing keeping them equal — and it does not even cover the set, since
`message_inbound` names a `message` protocol family this schema **retired**, leaving a
broker listener's root kind naming nothing in `protocol` at all. `cli_entry` became
`entry_point` because a `main` is a program entry point whether or not anything about it
is a command-line interface, and `cli` claimed a surface no producer measured.

**`entry_point` has no producer, and that is stated rather than left to a reader.** Which
signature starts a program is a fact about a LANGUAGE, and [ARCHITECTURE](../ARCHITECTURE.md)
§10 keeps language knowledge out of the language-blind half — so its producer is a catalog,
and none declares one (`docs/open-issues.md`, OI-22). The member stays in the set because
the traversal that reads `roots` branches on no kind at all: a root of this kind traces
exactly as the other two do the day something writes one.

**`terminal_kind`** — `outbound_call`, `returns`, `ends_silently`, `persistence`,
`throws`, `unresolved`, `async_handoff`, `cycle`

> **PRODUCED SINCE W30** (F7 §8.2), on `call_edges`. This note said "nothing produces a
> `terminal_kind`" for two phases and gave the right reason: the set CLASSIFIES what a call
> reaches, and `persistence` in particular "is `persistence` only to something that knows
> the callee is one". That framework knowledge is now catalog data
> ([D02](D02-catalog-schema.md) §2j) — an owner type, a supertype the owner implements, or
> the packages a scan annotation registers — so the classification is READ rather than
> guessed, which is what §5.3's second corollary asked for.
>
> **NULL and `unresolved` are different answers.** NULL means the edge is not a terminal at
> all: its callee's body was read and the walk expanded it. `unresolved` means this IS a
> terminal, it was examined, and no catalog claimed it — which on the measured corpora is
> 94-96% of them, almost all `StringBuilder`, `Object` and `List`.
>
> **Still not `TraceStop`.** That vocabulary (`domain/closed_sets.TraceStop`,
> [D01](D01-graph-schema.md) §3's Traces) answers why the WALK stopped and is decided
> entirely from what the walk did. One edge carries both and they say different things:
> `boundary` because this workspace read no body, `persistence` because a catalog knows
> what the callee is. **Six of the eight have no producer, for two different reasons**
> (`OI-75`): `outbound_call`, `throws` and `async_handoff` are one catalog rule away and
> none is declared, while `cycle`, `returns` and `ends_silently` are unreachable by any
> rule — a cyclic edge has a non-NULL `callee` so the classification is NULL for it, and
> the other two describe how a BODY exits while every catalog route is a predicate on the
> callee's TYPE.

`persistence` carries `target_kind`: `database`, `cache`, `file`. A sub-field, so that
splitting it later is a rendering choice rather than a re-index. Measured on `mall-admin`:
199 `database` terminals and 41 `cache` ones, the second being `RedisTemplate` — which is
the distinction the sub-field exists to make, and the question "does this call hit a
database or a cache" could not be asked without it.

**`direction`** — `inbound`, `outbound`, `both`. Which way a wire identity is used:
served here, called from here, or both. **Twelve citations pointed at this entry before it
existed** — the set lived only in `domain/closed_sets.py`, and W27's review found every
"stays in D00 §4 for the linking tier" reference dangling.

**`both` has no producer, and that is stated rather than left to a reader** (§5.3, the
`entry_point` precedent below). W27 deleted `merge_endpoints.sql`, the only pass that ever
wrote it: that merge folded a declaration this module can fully see together with an
observation it fundamentally cannot, and a module serving an address it also calls is now
two rows plus a `self_exchange` question. `both` stays in the set because the LINKING tier
is where a schema match or a human can justify one — a claim about two modules, made where
both are visible, which is exactly what a single module's analysis cannot make.

**`protocol`** — `http`, `soap`, `grpc`, `kafka`, `jms`, `sqs`, `pubsub`, `graphql`,
`websocket`, `sse`, `amqp`, `pulsar`, `rsocket`. `message` is
retired: it was reserved and never declared by any shipped catalog, so nothing migrates.
The broker family is the protocol because linking gates on protocol equality (DR-5), and
a Kafka topic can never be answered by an SQS queue.

**`graphql`, `websocket` and `sse` are HTTP-ADJACENT and are still their own protocols,
not flavours of `http`** (Phase 2H). [D01](D01-graph-schema.md) §3's wire identity is
protocol-scoped, and none of the three *is* an HTTP route: a GraphQL schema is N boundaries behind one
POST path, a WebSocket connection fans into N destinations, and an SSE stream is a route
whose return type turned it into something a request/response comparison cannot match
against. They were declared in one edit because the set is closed (NFR-5) and all three
are live today: `graphql` from the annotation and schema catalogs, `websocket` from the
WebSocket/STOMP catalogs, `sse` only ever by RECLASSIFICATION — no catalog derives an
`sse` row, `protocol_hint` moves one there ([D02](D02-catalog-schema.md) §2).

**`amqp` and `pulsar` were added in one edit** (Phase 2O Task 1, `domain/closed_sets.py`),
for the reason the three HTTP-adjacent members above were: the set is closed (NFR-5), so a
member a later task needs costs one line now and a schema change if it arrives alone. Each
is its own protocol on the same DR-5 argument — an AMQP exchange can never be answered by a
Pulsar topic, and neither is a JMS queue, which is why Spring Cloud Stream's `rabbit: jms`
stopgap migrated to `rabbit: amqp` in the same phase. Both are live: `amqp` from
`@RabbitListener` and `RabbitTemplate`, `pulsar` from `@PulsarListener`. *This list omitted
both from Task 1 until the 2O documentation sweep — a §5.1 violation, recorded rather than
quietly corrected, because the code shipped the members and the schema document did not say
so.*

**`rsocket` was added alone** (F2 §3.6), which the paragraph above says costs a schema
change: this is it, and the member, this list, [D06](D06-bundle-format.md)'s verbless table
and `docs/COVERAGE.md` moved in one edit. Its DR-5 argument is the same — an RSocket route
can never be answered by a STOMP destination — and until it existed, an RSocket controller
was published as `websocket`, a wrong-PROTOCOL fabrication `docs/COVERAGE.md` had stated in
place since `A-C1`. What kept it open was that **Spring does not distinguish the two on the
class at all**: measured
(`scripts/probes/w16_rsocket_versus_stomp.md`), `SimpAnnotationMethodMessageHandler.isHandler`
and the reactive handler's default bean predicate both test `@Controller`, so no fact about
the class could ever separate them. The fact that does is which handler auto-configuration
would register, which is a dependency fact.

**`control_flow_kind`** — `sequential`, `conditional`, `alternative`, `loop`, `handler`

**`format`** — `json`, `protobuf`, `avro`, `xml`, `string`, `bytes`. What is on a
channel's wire ([D01](D01-graph-schema.md) §3's `endpoints.format`), inferred and never
a property of a payload *type*. `json_schema` is **reserved**: the value is named here
so a catalog cannot quietly claim it, and a catalog that writes it is refused by name
rather than read as something adjacent — JSON Schema and XSD are out of scope, and the
refusal is what keeps "we do not do this yet" from arriving as a silent `json`.
`format_resolution` beside it takes no set of its own: it reuses `resolution` above.

**Two values have no version-1 fact producer, deliberately.** `syntax` is the day-one
on-ramp for a second language's tree-sitter tier; `llm` is required by
[M01](M01-overlay.md)'s claim machinery even though model overlays never become facts. Both
are retained by declared intent — this note exists so neither reads as dead and gets
removed.

---

## 5. Fact kinds

Fifteen. Every one exists because a stated requirement consumes it (NFR-6).

| Kind | Carries | Consumed by |
|---|---|---|
| `module` | Identifier, kind, languages, source sets, output directories, **classpath tiering**, active catalogs | Dispatch tiering, noise filtering, coverage |
| `symbol` | Identifier, construct kind, enclosing symbol, **typed signature** (§5a), visibility, **declaration modifiers** (§5a), range | Symbol graph, shapes, endpoints, class diagrams |
| `relationship` | Subject, object, relationship kind | Hierarchy, dispatch, class diagrams |
| `occurrence` | Symbol, range, enclosing symbol, role | Type-reference edges, `uses` |
| `annotation` | Target symbol, annotation symbol, **argument values**, retention, and — for a type-use annotation on a field or a type — **`type_path`** locating it within the type reference | Every endpoint engine |
| `call_site` | Caller, target (owner, name, descriptor), `invoke_kind`, `ordinal` — the v1 control-flow position — `receiver`/`result` value ids, structured `arguments` | Call edges, dispatch, traces, endpoints |
| — | The invoke-kind set includes **`throw`**: a throw site is a call-site-shaped observation whose target is the thrown exception type. It is what gives traces their `throws` terminal. | Trace terminals, blast radius |
| `field_write` | Constructor symbol, the assigned field's symbol, the source parameter's ordinal | The field resolution ladder (2F) |
| `constant` | Symbol, value | Topic and URL resolution. **`value` keeps the type the class file recorded** — a JSON string, number or boolean — because a consumer resolving an address needs the string and one reading a port needs the number, and flattening either to text would put a re-parse between the reader and the class file. **A non-finite double or float arrives as its Java spelling in a STRING** (`"NaN"`, `"Infinity"`, `"-Infinity"`): RFC 8259 has no literal for them, so writing one unquoted makes the fact file invalid for a conforming reader. The field's own descriptor distinguishes that from a String constant reading `NaN` |
| `string_literal` | Document, range, enclosing symbol, value | Endpoint literals, log-line search |
| `config_entry` | `key_raw`, `key_path`, `value`, source document, `doc_index` (§5c) | Configuration resolution |
| `dependency` | Coordinates, scope, tier | Classpath tiering, library identity |
| `deployment` | Service name, ports, kind, source | System linking |
| `declared_contract` | Protocol, wire identity, references to `declared_shape` facts, **whether the build consumes it** | Endpoint catalog, drift |
| `embedded_descriptor` | The schema holder's symbol, the schema format, and the payload **verbatim and unparsed** (§5d) | The descriptor interpreter, which is the only thing that reads it |
| `declared_shape` | Shape identity, owning contract, fields — wire name, **field number where the format has one**, wire type, required, default | Drift comparison, gRPC and message matching, DR-4's embedded-descriptor check |
| — | **Interpreter-emitted, never extractor-emitted** (§5d): the one place that understands a schema format turns `embedded_descriptor` payloads and schema files into these, so no scanner in any language links a schema runtime. | — |

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
payload at all**, as `modifiers.static` and `modifiers.transient` — joined in W7 by
`modifiers.final` and `modifiers.volatile`, which say whether the value can change at all
and whether the language was asked to publish that change across threads — a value bound to the type
rather than to an instance, and a declaration the language marks as not serialized. Neither
is visibility and neither is nullability: a public constant is as public as any field and is
on no payload, so a shape pass filtering on what it already had would have to guess. Both
flags are always written on a field fact, because an absent one cannot be told apart from a
scanner that does not report the modifier. **A compiler-synthesized field is not a
declaration and produces no fact at all** — a modifier would say "somebody wrote this and it
stays off the wire", where the truth is that no source file contains it.

**A method symbol carries the same `modifiers` slot with a different set of keys** —
`modifiers.static` and `modifiers.synthetic`, and from W7 `abstract`, `varargs`, `final`,
`native` and `synchronized`. Two of those answer questions nothing could ask before:
`abstract` tells an interface's `default` method from its declared ones, which emitted
IDENTICAL modifiers until it existed; and `varargs` is the only thing separating
`f(String...)` from `f(String[])`, which compile to one descriptor — so a call passing three
strings and one passing an array read as the same declaration. `native` is not `abstract`:
both mean "no body here", one says the code is elsewhere in this language and the other
outside it. **A TYPE symbol carries the slot too**, with `abstract` and `final`. The pairs
differ because the constructs do not share a vocabulary — because the two constructs do not share a
vocabulary. `transient` is deliberately absent: its class-file bit is `ACC_VARARGS` on a
method, so writing it would report every varargs method as not-serialized. The pair answers
one question, asked by any rule that enumerates a class's EXPOSED members (D02's
`mapping.members`): `static` is bound to the type rather than to an instance, and
`synthetic` is compiler machinery nobody wrote — a covariant-return bridge (`ACC_BRIDGE` is
folded in, since javac sets the two together), a lambda body, an accessor minted for a
nested class's private member. **Unlike a synthetic field, a synthetic METHOD does produce a
fact**, on purpose: the effective-annotations inheritance walk's bridge rule can only
recognise a bridge by seeing it, so the flag — not omission — is what lets a later pass tell
one from a method a human declared. Both keys are always written, for the field rule's
reason, and a reader supplies `false` for a scanner that reports neither. A Kotlin
`$default` bridge — the `static synthetic <fn>$default(receiver, <fn's slots…>, int mask,
Object marker)` kotlinc emits beside a function with default arguments — is emitted with
`modifiers.synthetic: true` AND `bridge_of: "<fn>"`, and its return and the function's own
slots carry the types the FUNCTION declared rather than Java's rule (`OI-81`). **A Kotlin
`DefaultImpls` holder carries the same key on each body** (`kotlin-defaultimpls`): an
interface with a default method body compiles to a nested `<Iface>$DefaultImpls` class —
`public final`, NOT synthetic, no fields, no constructor, every method `static` with the
interface at descriptor slot 0 — and that class's TYPE fact carries
`implements_default_of: "<Iface>#"` (spelled as `enclosing` spells a type, and for the
holder naming the same type `enclosing` does; the key is the statement), while each of its
methods carries `bridge_of: "<interface method's name>"`, which for the `$default` bridge
kotlinc puts inside the holder is the function's name, as it is anywhere else. The holder is
recognised from all three of its name, the `InnerClasses` entry naming the interface as its
outer class, and every method having that shape with at least one present — a hand-written
nested class of that name fails at its own constructor. A method's `bridge_of` states that
method's own shape and the type's `implements_default_of` states every method's, so a
consumer reads the first beside the second. The holder's own `@Metadata` is a
synthetic-class kind and declares no function, so a body's slots and return keep Java's
rule: the declared types are in the INTERFACE's metadata, and the scanner reads one class
at a time. `bridge_of` appears on no fact but those two shapes, and `implements_default_of`
on no fact but the holder's; `resolve/dispatch.py` reads the pair, making a holder body the
candidate for an interface method that declares no body of its own (COVERAGE §5.13). A Kotlin extension function's receiver (`fun String.shout()`) —
descriptor slot 0 of the static method a top-level extension compiles into in its file
facade, and of a member extension's instance method alike, and the first slot after the
owner in its `$default` bridge — is published as a parameter carrying `receiver: true`, with
the declared value parameters laid from the slot after it; absent means false, as
`bridge_of` is absent rather than null, and the receiver slot's own type keeps Java's rule
(`kotlin-extension-functions`).

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

**A symbol fact's `line_start` and `line_end` are the extent of its CODE, and `0` means the
class file states no line.** They come from `LineNumberTable` (JVMS 4.7.12), which maps
bytecode offsets to source lines — so the first line a method can state is its first
STATEMENT, with its signature and any annotations above it. A construct with no code states
nothing: a class carries no such table, an abstract or native method has no `Code` attribute
to hold one, and a field has neither. Source lines are numbered from 1, so `0` can never
collide with a real answer. Deriving a class's line from the minimum over its members would
land on whichever member sorts first rather than on the declaration, and is not done — though
a compiler that maps a class's IMPLICIT constructor to its declaration line, as javac does,
makes the answer reachable through that constructor.

**A parameter's `name` is whatever the class file states, and absent when nothing does.** Two
attributes can state it and they are not equals: `MethodParameters` (JVMS 4.7.24) describes
PARAMETERS and wins, while `LocalVariableTable` (4.7.13) describes every local and happens to
cover them, so it fills only what the first left empty. A local's slot is not a parameter
index — a `long` or `double` takes two slots (JVMS 2.6.1) and an instance method's slot 0 is
the receiver — and a slot is reused once a variable leaves scope, so the entry taken is the
one whose scope begins at the method's first instruction, which only a parameter's does.

**A parameter's type reference comes from the `Signature` attribute wherever the
declaration has one**, exactly as a return type's and a field's already did. The erased
descriptor has lost every type argument and every type variable by the time it is read:
`accept(List<String> names, T item)` is written `(Ljava/util/List;Ljava/lang/Comparable;)V`,
where the elements are gone and `T` has become its own bound. The attribute is the only
place either survives, so a parameter reads from it and falls back to the descriptor for a
declaration that carries no attribute at all — which is precisely a declaration with nothing
generic to lose. A type reference's `symbol` may therefore be a bare **type variable** (`T`),
which is not a class and is recorded by the name the signature gives it, never resolved to
its bound; the return position has always been able to yield one.

**The descriptor's own symbol is kept beside the signature's, as `erased_symbol`.** The two
differ only for a type VARIABLE: the signature names the variable, which is what a generic
substitution binds, while the descriptor names what it erases to. **A type variable's name is
scoped to the declaration that introduced it** — an interface may call it `E` where its
implementation calls it `T`, for one method — so it can never be compared BETWEEN two
declarations, and every consumer that keys or looks a type up by a parameter reads
`erased_symbol` instead. It is written on every parameter rather than only where the two
differ, because a JSON path wildcard drops elements whose key is absent and a shorter list
silently misaligns against the parameters it describes.

**The two lists are matched by the class file's own parameter flags, never by counting.**
JVMS 4.7.9.1 permits a signature to omit parameters that are implicitly declared, and a
compiler may also omit ones it synthesised — so the two lists can be different lengths, and
**the difference in length does not say which entries are missing**. Measured: an inner
class's constructor carries the enclosing instance FIRST and an enum's constructor carries
its name and ordinal FIRST, but a local class that captures carries its captures LAST, all
against a signature naming only what was written in source. Any rule based on the counts
alone is right for two of those and wrong for the third — and wrong there in the worst way,
putting a collection's element type onto an `int` in a fact that is perfectly well formed.

`MethodParameters` (JVMS 4.7.24) is what distinguishes them: the signature's entries go to
the slots flagged neither `ACC_MANDATED` nor `ACC_SYNTHETIC`, in order. **The flags are
evidence, not a definition** — `ACC_MANDATED` means *implicitly declared*, which is not the
same as *omitted from the tables*: a record's COMPACT canonical constructor flags every slot
mandated and omits nothing, so where the flags account for no slot at all they are saying
nothing rather than saying the method has no parameters.
The signature's entries are laid onto the slots flagged as neither, in order. **Where that
attribute is absent, or where the flags do not account for the difference, every parameter
keeps its erased type** — less specific, never wrong. A local class declared inside a static
method is the real case: it has captures at the end and no `MethodParameters` at all.

**A class or method symbol fact carries the formal type parameters it declares, as
`type_parameters`** — each an ordered `{name, bounds}` entry, the bounds being type
references like any other. The name and the position are what a generic substitution binds a
variable by: without them the `T` a parameter or return type now names refers to nothing.
Bounds are recorded exactly as the signature states them, `java.lang.Object` included —
javac writes `T:Ljava/lang/Object;` for a parameter declared `<T>`, so there is no
distinction between `<T>` and `<T extends Object>` to preserve, and an empty bound list would
otherwise mean either "unbounded" or "the scanner did not read it". Multiple bounds stay
multiple, in declaration order. **Emitted only where the declaration has any** — the same
"nothing generic, nothing captured" rule the generic supertype follows below, since most
classes and nearly every method declare none.

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

**A nested type carries `nest_host`, and a nest host carries `nest_members`** (JVMS
4.7.28/4.7.29). `nest_host` is not `enclosing`: for `A$B$C` the immediate encloser is `A$B`
and the nest host is `A`, and both are real answers to different questions. The top-level one
matters because `$` is a legal identifier character, so splitting a binary name on it reports
a top-level class genuinely named `Foo$Bar` as nested inside a `Foo` that does not exist.

**A type carries `unread_attributes`** — the names of attributes this scanner SAW and did not
read, a vendor's or one from a newer class-file version. By name only: reading the bytes would
mean guessing at a layout nobody published. It exists so "seen and not read" can be
distinguished from "not present", which is the distinction §2.3's ledger is built on.

**Two reserved file classes produce no type symbol.** `module-info.class` and
`package-info.class` have a class file's shape and a `this_class` naming no type any source
declares, so emitting a symbol for either put a phantom into the graph. `module-info` is not
read at all — module identity comes from the build's own coordinates, and `requires`/`exports`
say less than the build file already does. `package-info` IS still read, because it is where a
compiler puts a package's ANNOTATIONS and a package-level nullability scope (D02 §2e) is
declared through exactly that target; only its invented symbol is dropped.

**A SEALED type carries `permits`** — the complete set of types the language allows to
extend it (JVMS 4.7.31), emitted only where the declaration is sealed. It is the one place
"every implementation of this" is a closed answer rather than whatever a scan happened to
reach, which is what every other implementation question here is.

**A method's signature carries `throws`** — the types it DECLARES it can fail with (JVMS
4.7.5), in declaration order, and inside the signature rather than beside it because it is
part of what a caller must handle in order to call it. Omitted where a method declares none.

**A class symbol fact also carries the erased symbols of every interface it implements, in
declaration order, as `interfaces` — emitted only when non-empty** (the `implemented_interfaces`
capability, [M03](M03-scanner.md)): a receiver registered by its declared type
(`Subscriber.newBuilder(subscription, new RawPubSubReceiver())`) names no method by itself, and
`interfaces` is what lets a catalog join that type back to the single method the interface
declares.

**Interface satisfaction is extractor-computed, not a JVM-only notion.** A structural-interface
language (Go) has no `implements` keyword to read off the class file — its extractor derives
the same `interfaces` facts from method-set satisfaction instead. The
`interface_implementation` engine's join stays unchanged either way: it reads `interfaces`,
never how the extractor arrived at it.

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
behind an extension read boundary. The projection reaches a method's `returns` (`G-63`) and,
since `OI-82`, each of a function's and a constructor's `parameters` — at every level of the
type reference, so `List<String?>` and `List<String>?` carry different `nullable` values on
different levels where the descriptor and the `Signature` attribute spell them the same.
Where the declared type and the signature disagree on shape, the reference keeps Java's rule
at that level and below: less specific, never wrong.

**Literal values have a typed model**: string, number, boolean, enum reference, **class
reference — captured as a symbol reference, not a string** — and arrays of these. This is
what lets a catalog's `response_arg: 2` on `postForObject(url, req, OrderResponse.class)`
resolve to a real shape root.

**An annotation is a literal value too** (capability 9.16). An annotation-valued argument
carries **its own `annotation` and its own `args`, recursively** — the same
`{annotation, args}` shape the enclosing use has, rather than a second vocabulary beside
it — so `@InboundChannelAdapter(poller = @Poller(fixedDelay = "1000"))` keeps the poller,
and `@RabbitListener(bindings = @QueueBinding(value = @Queue("orders")))` keeps the queue
name two levels down. It composes with arrays in both directions: an array of annotations
is how a `@Repeatable` annotation arrives at all, because **two or more of one repeatable
annotation on the same declaration are folded by the compiler into a single container
annotation holding an array of them** (JLS 9.7.5). `@Scheduled` twice on a method is one
`@Schedules({…, …})`, so before 9.16 a method with one schedule was readable and a method
with two carried no trigger at all.

The recursion is **bounded**, and says so where it stops. The language bounds it already —
javac rejects a cyclic annotation element type, so a chain cannot revisit a type — but a
class file need not have come from javac, and an unbounded descent is a stack overflow
mid-scan rather than a fact. The JVM mapping (capability 9.16) allows **five levels of
nesting below the outermost annotation**, comfortably past the deepest shape in the estate
(`@RabbitListener` → `@QueueBinding` → `@Queue` → `@Argument`, depth 3). Past it the value
is `{annotation: <fqn>, unresolved: "depth_limit"}`: the type was read off the descriptor
and is real, the arguments were never read and get **no `args` key** — an empty `args`
would be indistinguishable from an annotation genuinely written with none, which is the
silent truncation §8 forbids. Strictly additive: an engine that does not consult a nested
use sees exactly the keys it saw before, since a nested value previously produced no key
at all.

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

### 5c. Configuration entries

**One `config_entry` fact per key, one per configuration file.** The neutral pieces of a
config file, and nothing more:

- `key_raw` — exactly as written;
- `key_path` — normalized dot-joined segments; a YAML list normalizes to indexed segments
  (`foo[0]`, Spring's own canonical form and a neutral one);
- `value` — verbatim, always a string, never coerced — a value is a claim to resolve, not
  a typed answer;
- the source document and `doc_index` — the source file's YAML document index, which a
  multi-document file's `on-profile` activation needs to tell its documents apart.

**Entries are emitted in declaration order within their document, and that order is the
fact's implicit sequence.** No field carries it explicitly — a fact file is written in
declaration order (§7), so the load order the workspace already keeps (`rowid`)
reconstructs it losslessly, the same rowid-carried ordering `symbols` already relies on
for its own `seq`. This is what lets the layering pass see a file's keys in the order the
file wrote them, the same NFR-1 role `call_site.ordinal` states for instructions.

**The document's `language` column carries the FORMAT** (`yaml`, `properties`) for a
config file, never a language name. This is the same discipline that keeps `language`
itself off individual facts (§2): a field meaning one thing for a config format and
another for a programming language would be exactly the schema defect NFR-7 forbids, so
format reuses the one column rather than earning a field of its own.

**A reader is neutral: it never layers, never resolves, and never interprets a profile.**
Which files matter, in what order, and what a placeholder means, is the resolution side's
question, answered from catalog data ([D02](D02-catalog-schema.md)) — ingestion only
reads what is on disk into these fields.

### 5d. Embedded descriptors, and the one interpreter that reads them

```json
{"kind": "embedded_descriptor", "symbol": "com/example/orders/proto/OrderProtos#",
 "schema_format": "protobuf", "payload": "Cgtvcm…", "origin": "compiled"}
```

**The fact says one thing: "this artifact embeds this schema payload, verbatim."** The
emitter never parses it, which is what keeps schema-format knowledge out of every
scanner: a Go scanner emits it from a generated `rawDesc` literal, a Python scanner from
`serialized_pb`, a TypeScript scanner from protobufjs static output, and none of them
links a schema runtime to do it.

- **`symbol`** names the **holder** — the generated class a compiled payload was found
  in, the record's own name for one read off a schema file — in the bare type-descriptor
  grammar (§1). It is what a gap names when a payload cannot be interpreted, and one
  holder emits one fact: a protobuf file's messages all share their file's descriptor, so
  a fact per message would be one payload copied once per type.
- **`schema_format`** is `protobuf`, `avro`, `graphql` or `wsdl`. It names the schema
  LANGUAGE that described the payload, which is not the same question as what is on the
  wire: protobuf and Avro define an encoding, GraphQL defines a type system and leaves the
  encoding to the transport. [D02](D02-catalog-schema.md) §2c's rung 4 turns on exactly
  that distinction. `wsdl` covers both `.wsdl` and `.xsd` files, because they are one type
  universe and not two formats: a WSDL declares its payload types by embedding XSD in its
  `<types>` element, and an `.xsd` beside it is the same schema split across a file
  boundary by an `xsd:import`.
- **`payload`** is base64 for a binary format and the text itself for a textual one — a
  protobuf `FileDescriptorProto`'s bytes are base64; an Avro schema is JSON that was
  always JSON and travels verbatim, because re-encoding readable text costs a reader
  something and buys nothing.
- **`origin`** is `compiled` (the default, and what an extractor always emits) or
  `source` (a schema file in the repository). Where both declare the same shape, the
  compiled one wins: the artifact that runs is the authority (DR-4).

**`declared_shape` is the interpreter's output, never a scanner's.** One component reads
these payloads, and it is the only code in the system that understands a schema format —
so a format's rules are stated once, and a new language's extractor gains schema support
by emitting `embedded_descriptor` and nothing else.

Each such fact carries, beside its `fields`:

- **`symbol`** — the name the shape is *joined* by: the generated class a compiled
  payload travels as, so a payload type reference in any other fact meets it; the
  schema's own full name for a source-origin shape, which compiles to no class.
- **`schema_name`** — the schema's own full name (`sextant.orders.OrderRequest`),
  written for **both** origins, because `symbol` cannot be the identity across them.
  It is the one field on which a compiled and a source shape can meet, and therefore
  what DR-4's compiled-beats-source precedence compares.
- **`schema_format`** and **`origin`** — as on the `embedded_descriptor` this came
  from.
- **`evidence`** — `compiler` for a compiled origin, `declared` for a source one. The
  shape's whole field list carries the one tier; a schema does not state some of its
  fields more confidently than others.
- **`role`** — `query`, `mutation` or `subscription` where the schema names this type as
  the entry point every operation of that kind is addressed against; `operation` where
  the schema names the type as *being* an operation rather than a root operations hang
  off; and NULL for the ordinary payload types, which is nearly all of them. It is a fact
  and not a derivation because a schema may *rename* its roots, so which type holds the
  role cannot be recovered from the type's own name by anything downstream — and only the
  interpreter may read a schema format at all.
- **`operation`** — optional, populated only where `role` is `operation`: `{input_ref,
  output_ref, client_streaming, server_streaming}`. A gRPC descriptor `service` method
  fills every field, `input_ref`/`output_ref` naming the SAME descriptor's message shapes
  by their own `schema_name` (an intra-descriptor join, never a guess across universes);
  a WSDL operation (2I) leaves it NULL today, its output side unrecorded until a later
  task fills it. **Amendment (2O Task 4, `fact_schema_version` 1.0.0 → 1.1.0):** this
  field is new. The estate cost is re-analysis of every already-scanned workspace to gain
  it — accepted pre-gate, because every fact file already on disk still validates
  unchanged, with the field simply absent (D01 §7's cache-key rule already treats a
  `fact_schema_version` change as one reason a cached result may no longer be reused).

  **Correction (Step 0).** That bump was applied to ONE of the stamp's four producers —
  `domain/version.py`, which stamps `metadata.json` — and this field is written by
  `ingress/read/*`, which was left at `1.0.0`. So every `.proto`, WSDL, Avro and GraphQL
  document written since carries `operation` while stamping the version that predates it,
  and nothing detected the disagreement because the staleness gate reads `metadata.json`
  and never the documents. Step 0 removes the cause rather than the symptom: the stamp
  becomes an integer, the Java copy is deleted (the extractor is HANDED the value as a
  required option), and the two Python restatements import the one constant that owns it.

Per field: the schema's own `name` and the encoded `wire_name` (a protobuf `json_name`,
**read from the descriptor, never computed** — protoc puts the computed default and an
explicit override in the same place), `field_number` where the format numbers its fields
and NULL where it does not, the [§5b](#5b-the-wire-type-vocabulary) wire type and format,
`required`, `nullable`, the declared `default`, and the `item`/`shape_ref` references
that reach other shapes.

**The file is the failure boundary, and a failed file's CONTENT never publishes.** A
schema file the interpreter cannot read — text that does not parse, a name two
declarations claim, a construct the branch has no word for — publishes *none* of its
declarations rather than the ones read before the trouble, is named in the run's
`descriptors_not_interpreted` list, and never stops a sibling from being interpreted.
What differs between formats is only what a sibling is left holding, and it follows from
how that format's projection reaches another file rather than from a policy choice: **a
pointer to a shape this run did not publish stays an open reference** — a GraphQL field's
`shape_ref` into a file that parsed but could not be projected reads downstream as a
reference nothing answered — while a projection that **copies** what it names cannot
leave a pointer at all, so the failed file's declarations leave the type universe and a
sibling naming one becomes a dangling reference and its own gap. An XSD element typed by
a named `complexType` carries that type's *fields*, which is exactly the copying case: an
open reference there would have meant republishing a failed file's content under another
file's name. A file whose text never parsed declared nothing the module can see in any
format, so its names are not in the universe to be pointed at either.

### Why `module` is a fact and not a passing argument

[M02](M02-detector.md) works out the module inventory and the classpath tiering, and
[M03](M03-scanner.md) uses them. It would be easy to leave that in memory between the two.

It cannot be. **Three later components need it and never see [M02](M02-detector.md).**
[M04](M04-resolver.md) needs the indexed-set boundary to decide `narrowed` against
`partial`. [M07](M07-renderer.md) needs origin tiers to filter noise.
[M08](M08-exporter.md) must carry it in a bundle so [M06](M06-stitcher.md) can use it on
another machine. A stage resumed with `--from-stage` never runs the detector at all.

So the detector's conclusions are facts like any other, and travel like any other.

**What is CONSTRUCTED today, since Phase 2O Task 6** (before it, this record was defined
and written nowhere): the module's identity, kind, languages, source roots, output
directories, and **`dependency_coordinates`** — the `groupId:artifactId` coordinates the
module's build declares, which is what a catalog whose framework rule is conditional on a
library reads ([D02](D02-catalog-schema.md) §1's `detect.coordinates`). **Classpath
TIERING is still not written**: `classpath`'s own `ClasspathEntry` names a resolved
archive per entry, which the Gradle report carries and a parsed POM does not, and filling
it from Maven would mean inventing a path. The coordinate half is its own field for that
reason, rather than a half-filled entry list.

The two build systems also differ in REACH, and the difference is carried rather than
smoothed over: Gradle reports the resolved compile classpath, transitives included; Maven
reports the POM's direct declarations only. A coordinate absent from this list means "not
declared here", never "not on the classpath" — and an ABSENT module fact (an older
workspace) is a third answer again, which is why a gate reading it distinguishes empty
from missing.

The module fact's own `document` record is SYNTHESIZED rather than read from a file: the
stage that writes it may not touch the filesystem, so its `content_hash` is the hash of
the module identity it records and its `origin_entry` is the module's own coordinates
(never a machine path — §2's portability rule, which a filesystem root would break for two
checkouts of one module).

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

**`implementation` is the optional symbol of the function this site's DISPATCH will run,
written only where the target does not already name it** (capability 9.17). It is the
canonical cross-language answer to "the call site names a mechanism, not the code" — a JVM
`invokedynamic`, and whatever another language's extractor finds in the same position. The
JVM mapping: an indy bootstrapped by `LambdaMetafactory` (`metafactory` or
`altMetafactory` — the gate is the OWNER) carries the implementation handle in
`bootstrapMethodArguments[1]`, and that handle's owner, name and descriptor become the
lambda body's symbol. It is a **bare** descriptor path, exactly like the `lambda` argument
kind and for the same §1 stability reason: a method reference is very often into a library,
and stamping the caller's coordinates onto `java/lang/String` would mint a different symbol
for `String::trim` in every module. **An in-module body therefore joins to its own method
fact by stripping that fact's module prefix**, which is the join every consumer of these
symbols already performs.

Absent on every other call site, and that is a claim rather than a shrug: a
`StringConcatFactory` site's bootstrap arguments are a format recipe, not a method, so
there is no implementation to name and writing one would assert a call to code that does
not exist. Strictly additive — an engine that does not read `implementation` sees exactly
the facts it saw before 9.17.

**Why it is a field and not a better `target`.** Overwriting `target` with the handle would
make one column mean two things — a real method at a lambda site, a bootstrap class and a
call-site signature at a concat site — so a consumer joining `target` to method symbols
would silently match the first and silently miss the second. The bootstrap owner is also
load-bearing in its own right (it is what says the site is a lambda at all), and the SAM
name and descriptor on the instruction are the only record of the interface being
implemented. Both are kept; the body is added beside them.

**`invoke_kind`** is one of `virtual`, `static`, `interface`, `special`, `dynamic` — the
five JVM dispatch forms — plus `throw`, which the row above already names: a throw site is
a call-site-shaped observation whose target is the thrown exception type. It carries no
`name` and no `descriptor`, because there is no method: a throw dispatches to no body, and
an empty name would match nothing while looking like one.

**It gives traces their `throws` terminal by a path this paragraph used to misname.**
Until `G-52` was built it said the throw site is "what gives traces their `throws`
terminal" as if the catalog path did it, and measuring `resolve/terminals.py` showed that
path never could: `rules.of(target)` keys on `owner_of(target)` — the callee's TYPE —
through direct owner, then supertype, then scanned package, and never reads `invoke_kind`.
A catalog rule naming an exception type would have classified the CONSTRUCTOR call, not
the exit. So `classify()` reads the site's `invoke_kind` first and returns `throws` for a
throw site directly, before any rule: how a method exits is a property of the instruction,
not of any library. The catalog path is unchanged and still produces no `throws`. The
false sentence was written when neither half existed and nobody could notice.

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
| `field` | GETFIELD/GETSTATIC that is not the enum-constant shape | symbol reference — the field's own bare descriptor |
| `parameter` | a load of the caller's own parameter | `value` is the parameter's **index**, never the local slot holding it |
| `array` | an array construction reaching the slot (JVM: `ANEWARRAY`/`NEWARRAY` plus its `xASTORE`s) | `elements` carries one entry per element, each an argument of this same grammar. **One slot, not N** — a varargs call passes one array |
| `null` | ACONST_NULL | |
| `concat` | invokedynamic via `StringConcatFactory` | **an address the code ASSEMBLES rather than states.** `"/api/" + version + "/orders"` is not built in the bytecode: javac emits one instruction plus a RECIPE holding the literal parts with a marker per runtime value. `value` is the template — `/api/{}/orders` — and the hole is deliberately UNNAMED: a path variable's name was never part of the address (a server routes `/api/owners/42` to `/api/owners/{ownerId}` by POSITION and may rename the variable freely), so `{}` is what both sides share and naming it would invent one the class file often does not carry. What FILLS the hole is the concat site's own call-site fact, reached by `source` → `result` |
| `unresolved` | anything else | a first-class honest answer, never an omission |

**`<init>` is the canonical constructor call-site name every extractor normalizes to** —
Python's `__init__` maps in, and a language without constructors (Go has none) simply
never emits it. Readers already tolerate absence: it is a name compared, not a field
whose presence is assumed.

**`lambda` is the canonical cross-language kind for "this argument is that function"** —
every extractor normalizes its own mechanism into it: a JVM `invokedynamic`, a Go closure
or function value, a Python nested function or reference, a JS arrow or function
expression. `symbol` names the function's own method/function symbol — the bare
descriptor, exactly as the JVM extractor emits.

**`field` is the canonical cross-language kind for "this argument reads a declared
field"** — an argument that reads a declared field, carrying that field's symbol. The
JVM mapping: a GETFIELD/GETSTATIC that is not the enum-constant shape (the `enum` row
above) becomes `{kind: field, symbol: <the field's bare descriptor>}` instead of
`unresolved`; a Python attribute read or a Go struct-field read normalizes into the same
kind. Strictly additive: an engine that does not consult `field` treats it exactly as it
always treated `unresolved`.

**`parameter` is the canonical cross-language kind for "the argument is the caller's
parameter N, any language"** — the value was handed to this method, so it is knowable
only where the method was called, and `value` carries the index every language numbers
its parameters by. The JVM mapping: a load of a parameter's own starting slot becomes
`{kind: parameter, value: N}` instead of `unresolved`, joinable to the same index
`field_write.from_parameter` uses and to that position in the method's own signature
(§5a). It carries no `source` — a parameter is produced by no call in this method — and
it is deliberately **not** the local slot: a `long` parameter occupies two slots, so
index and slot diverge, and a slot is a JVM detail no other language shares. Strictly
additive: an engine that does not consult `parameter` must treat it exactly as it always
treated `unresolved` — the value is still unread, only its origin is now stated.

**`array` is the canonical cross-language kind for "this argument is an array built
here"** — a varargs call in any language that has one, and an explicitly written array
literal, which are the same call. `elements` carries the element arguments, each of them
an entry of this same grammar, so an element reads exactly as it would have read as a
single argument in the same position: a literal is `string`, a `@Value` field is `field`,
an unreadable expression is `unresolved` **with its `source`**. The shape is deliberately
**self-describing rather than unpacked**: one argument that happens to be an array, never
N arguments — unpacking would renumber every slot after it and make arity unreadable, the
same reason `unresolved` is an answer rather than an absence.

The JVM mapping (capability 9.15): an argument slot whose producing instruction is an
`ANEWARRAY`/`NEWARRAY` reads its `xASTORE`s and becomes `{kind: array, elements: […]}`.
It fires **only where the whole construction is readable** — a constant length, every
index a distinct constant, every index written, no store outside the window between the
construction and this invoke, and the array reaching no other invoke that might mutate it.
An array built in a loop, populated on a branch, left partly unwritten, or handed to
another method first is `unresolved` with no element list at all; an array arriving from
elsewhere keeps the `parameter`/`field`/`unresolved` answer its own producer gives it.
A **zero-length** varargs call is `{kind: array, elements: []}` — the empty list is the
fact, and it is the one place in this grammar where an empty value says something an
absent key would not, because "called with no values" is a different statement from "the
array could not be read". A **varargs call and an explicitly written array are reported
identically**, deliberately: javac erases the sugar at the call site and the callee's
`ACC_VARARGS` flag lives on a class the pass has not read, so they are the same call and
`elements` states what the callee receives either way. Strictly additive: an engine that
does not consult `array` treats it exactly as it always treated `unresolved`, which is
what every varargs slot read as before 9.15.

**`method_return` is a fact of its own, one per return instruction** (capability 9.18) —
what a method hands back:

```json
{"kind": "method_return", "document_id": "…", "method": "<method symbol>",
 "ordinal": 0, "value": {"kind": "unresolved", "source": 13}}
```

It is the last link in a round trip whose every other hop was already extracted. An
argument carries the `source` id of the call that produced it, so
`OmsOrderService#list` → `CommonPage#restPage` → `CommonResult#success` is a chain of
facts today; nothing said that `success`'s result is the value the METHOD returns.
`method` is the returning method's own symbol, spelled exactly as `call_site.caller` is —
**module-prefixed**, because it names a declaration this module made, where the bare
spelling is reserved for references that must be identical across modules.

**`value` is an entry of §5's argument grammar**, not a bare value id, and the two answers
that shape keeps apart are the reason:

| What the bytecode does | `value` |
|---|---|
| returns nothing (a `void` return pops nothing) | `null` — an ANSWER, not a failure |
| returns something this pass cannot name | `{"kind": "unresolved"}` |
| returns another call's result | `{"kind": "unresolved", "source": N}` — the join |
| returns a literal, a field, a parameter, a lambda, a constructed value | that kind, exactly as it would read in an argument slot in the same position |

A bare id would have collapsed the first two into one absence. The declared return type is
read alongside the value for the same reason a call site reads its argument types: a
boolean and an int both arrive as `ICONST_*`, and only the descriptor tells them apart.

**Several returns are several facts, and are not collapsed.** A method with two `return`
statements has two possible answers and no single one, distinguished by `ordinal` — the
return's index among this method's returns, in instruction order. Picking one would be a
fact about code that may never run, the same refusal §5 makes for a value merged on a
branch. The JVM mapping covers all six return opcodes; `ATHROW` is deliberately **not** one
of them — it leaves the method without handing a value back, and putting an exception where
a caller reads a returned value would be a wrong answer rather than a missing one.

**Its consumer does not exist yet.** The reader is 2Q's cross-method propagation, which
joins a `method_return` to the caller's own `result` id; the fact ships ahead of it because
that is what it will consume. Recorded plainly here rather than implied: `docs/open-issues.md`
carries it as `OI-15`.

**`field_write` is a fact of its own, constructors only, direct traces only** — a
constructor assigns parameter N directly to field F. The JVM mapping: a PUTFIELD inside
`<init>` whose value traces straight to a parameter produces `{kind: field_write, field:
<symbol>, from_parameter: N}`; a computed assignment — concatenation, a default
expression, anything but a direct load of the parameter — emits nothing, and the
resolution that would have followed it degrades honestly rather than guessing a source.
Setter injection is deliberately out of this fact's reach — a named gap, not an
omission.

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
