# Phase 2A — Shapes and nullability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An endpoint carries its request and response contract field by field — wire name, wire type, `required` and `nullable` — rooted through framework wrappers, for Java and Kotlin.

**Architecture:** The extractor gains three capabilities it lacks: field symbols, type annotations from **both** retention tables, and Kotlin's `@Metadata`. Language knowledge stays in the extractor, which emits each type reference already projected into D00 §5b's wire-type vocabulary. The derivation stays language-blind: it unwraps declared wrappers to root a shape, expands the rooted type's fields, and populates `required` and `nullable` from whichever source declared them.

**Tech Stack:** Java 21 + ASM 9.7 + kotlinx-metadata-jvm for the extractor; Python 3.12+, DuckDB, pydantic; Maven with `kotlin-maven-plugin` for the fixture; pytest, ruff, mypy, import-linter.

**Spec:** [docs/components/README.md](../../components/README.md) — in particular [D00](../../components/D00-fact-schema.md) §5a and §5b, [D01](../../components/D01-graph-schema.md) §5, [D02](../../components/D02-catalog-schema.md) §2a and §2e, and [M03](../../components/M03-scanner.md). Executors read the spec alongside this plan.

**Roadmap:** [2026-08-28-phase-2-roadmap.md](2026-08-28-phase-2-roadmap.md) — why shapes come before outbound.

## Global Constraints

- **Approved dependencies only** (ARCHITECTURE §9). `kotlinx-metadata-jvm` is already approved and "rides inside the extractor jar". Any other dependency needs approval per `GUIDELINES.md` §7.
- **Determinism (NFR-1).** Same inputs produce byte-identical facts, `metadata.json` and documents. Field order within a shape is the declaration order the class file gives; never a hash-set order.
- **Closed sets are frozen** (NFR-5). The wire-type vocabulary is D00 §5b: `string`, `integer`, `number`, `boolean`, `bytes`, `array`, `map`, `object`, `enum`, each with an optional format qualifier. Adding a value is a schema change.
- **`required` and `nullable` are two independent two-valued flags** (D00 §5a). Neither has an `unknown` value; doubt lives in `resolution` and `evidence`.
- **No framework name outside the catalogs, no language name outside `ingress/extract/jvm`.** Enforced by the source rules in `tests/architecture/`.
- **`application/` performs no file I/O.** Enforced.
- **Every catalog ships a conformance fixture** (D02 §4) — a module that uses the real framework, with the exact expected output.
- **Spec before code** (`GUIDELINES.md` §5). Task 1 amends D02; no task may deviate from a component document without an approved amendment first.

---

## Decisions taken

Approved before implementation. Recorded with their reasoning, because each places knowledge
in a particular layer — and a later change that ignores the reasoning would undo it silently.

**D1 — The extractor projects wire types, into D00 §5b's vocabulary.**
Mapping `java/lang/Long#` to `integer/int64` is language knowledge, and `application/` is
language-blind with an architecture rule enforcing it. Each language adapter converts its own
types; the derivation then compares values it never had to understand.

The target is D00 §5b rather than OpenAPI's set directly. §5b **is** OpenAPI's types plus three
distinctions OpenAPI encodes as modifiers — `map` (object with `additionalProperties`), `enum`
(a type plus a constraint) and `bytes`. Projecting §5b down to OpenAPI is lossless; collapsing
at extraction time is not, and two of the three change matching answers. A `Map<String, X>`
and a DTO are both `object` to OpenAPI, so flattening makes a map look type-compatible with a
record. An enum flattened to `string` makes a consumer accepting any string look compatible
with a producer emitting two values — true in one direction, false in the other, which is
exactly what DR-5 compares.

**D2 — Expand our own code to any depth, map known types, stop at unknown third-party.**
Three cases, not two:

| Origin | Example | Treatment |
|---|---|---|
| Module output or first-party | `com.acme.orders.CustomerRef` | Expand structurally, any depth |
| **Known type with a defined wire form** | `Instant`, `UUID`, `google.protobuf.Timestamp` | **Map to that form; never expand** |
| Unknown third-party | `org.springframework.http.HttpHeaders` | Stop, keep the reference, mark the shape open, **report it** |

Expanding a known type is not merely wasteful, it is wrong: open `BigDecimal` and you get
`intVal`, `scale`, `intCompact`, `precision` — internal machinery, none of which reaches the
wire, producing a shape no real payload could match.

**A type's wire form is serialiser knowledge, so it is catalog data** (§2g). `Instant` is an
ISO string under Jackson's `JavaTimeModule`, epoch millis without it, and anything at all under
a custom serialiser. That draws the line against D1 cleanly: **the extractor projects what the
language leaves no choice about** — primitives, boxes, `String`, arrays, collections — **and
the catalog declares what the serialiser decides.**

Unknown types are not followed on a structural test. "Simple" has no honest definition, and
`BigDecimal` is the trap: few fields, all internal. Instead the coverage report **names every
type expansion stopped at**, so the catalog grows from evidence rather than guesswork — the
same bargain as capability gating.

**D3 — The extractor emits `nullable` and its `resolution`, from its own language's rule.**
The default is a fact about a type system, not about annotations, so it belongs where the
language is understood — the same principle as D1.

| Language | Unannotated default | `resolution` |
|---|---|---|
| **Java** | reference → nullable, primitive → not-null | reference is **`partial`**: the language permits null, but nothing declared intent |
| **Kotlin** | `String` → not-null, `String?` → nullable | `resolved` |
| Go | pointer, slice, map, interface → nullable; value type → not-null | `resolved` |
| Rust | `Option<T>` → nullable, else not-null | `resolved` |
| Swift | `T?` → nullable, else not-null | `resolved` |
| Python | only from an annotation | `unresolved` without one |

**Java is the outlier**, and that reframes the feature: nullability is not a best-effort signal
that happens to suit Kotlin. It is reliable in every language surveyed **except unannotated
legacy Java**, which is the one case needing annotations to recover it.

The catalog still matters, because the extractor does not know that
`org.jspecify.annotations.Nullable` means nullable — that is one of six spellings and is
framework knowledge (§2e). So: **the extractor states the language's answer, the catalog names
the annotations, and the derivation combines them** — a catalog-declared annotation overrides
the language default and raises `resolution` to `resolved`. The derivation stays language-blind
throughout.

---

## File structure

| File | Responsibility |
|---|---|
| `docs/components/D02-catalog-schema.md` | **Amend**: §2f serialisation naming, and §2g types with a known wire form |
| `extractor-jvm/.../ClassScanner.java` | **Modify**: `visitField`, `visitTypeAnnotation` on both tables, wire-type projection |
| `extractor-jvm/.../WireTypes.java` | **Create**: JVM descriptor → D00 §5b wire type and format |
| `extractor-jvm/.../KotlinNullability.java` | **Create**: `@Metadata` → per-property nullability |
| `extractor-jvm/build.gradle.kts` | **Modify**: add `kotlinx-metadata-jvm`, shaded |
| `fixtures/orders-service/pom.xml` | **Modify**: `kotlin-maven-plugin`, JSpecify, Jackson annotations |
| `fixtures/orders-service/.../contracts/` | **Create**: Java DTOs with mixed nullability, a nested object, a collection |
| `fixtures/orders-service/.../KotlinOrder.kt` | **Create**: Kotlin data class with a nullable and a non-null property |
| `src/sextant/domain/facts.py` | **Modify**: `FieldFact`, and `nullable`/`wire_type` on `TypeRef` |
| `src/sextant/storage/duckdb/schema.sql` | **Modify**: `shapes`, `shape_fields`, `fields` view, endpoint shape columns |
| `src/sextant/storage/duckdb/derive_shapes.sql` | **Create**: materialise the computed shape rows (reset + parameterised insert) |
| `src/sextant/application/resolve/shapes.py` | **Create**: wrapper unwrapping and the shape pass (root, expand, project) |
| `src/sextant/catalogs/spring-web.yml`, `spring-mvc.yml` | **Modify**: `wrappers`, `nullability`, `serialization`, `known_types` |
| `src/sextant/egress/render/metadata.py` | **Modify**: report shapes; drop `shape_expansion_not_implemented` |

---

## Task 1: Amend D02 with serialisation naming and known wire forms

[D01](../../components/D01-graph-schema.md) §5 says **`shape_fields.wire_name` is the identity,
never the source field name** — *"after a naming strategy or an explicit serialisation
annotation, `customerId` and `customer_id` may be the same field"*. D02 has no vocabulary for
declaring either, so a correct `wire_name` cannot be produced. Serialisation naming is
framework knowledge, so it is catalog data.

**Files:** Modify `docs/components/D02-catalog-schema.md` (new §2f, and a row in §7).

**Interfaces:**
- Produces: the `serialization` block Task 8 writes and Task 10 reads.

- [ ] **Step 1: Add §2f after §2e**

````markdown
## 2f. Serialisation naming

`shape_fields.wire_name` is the identity ([D01](D01-graph-schema.md) §5), and a source field
name is not it: `customerId` reaches the wire as `customer_id` under a snake-case strategy, or
as whatever `@JsonProperty` says. Which annotation carries the name, and what happens when
none does, is framework knowledge:

```yaml
serialization:
  name_from:
    - { annotation: com.fasterxml.jackson.annotation.JsonProperty, arg: value }
  ignore:
    - com.fasterxml.jackson.annotation.JsonIgnore
  default_strategy: as_declared      # as_declared | snake_case | kebab_case | upper_camel
```

**`default_strategy` is a declaration, not an observation.** A module may configure a strategy
globally, in which case the value the catalog states is a default that configuration overrides
— so a `wire_name` derived from the default carries `evidence: declared`, while one from an
explicit annotation carries the evidence of the code that declared it. Comparing a declared
name against an observed one is how a matcher reports agreement it has not established
(§2c).

**A field the catalog says to ignore produces no `shape_field` at all.** It is absent from the
wire, and a shape carrying it would fail DR-5's directional comparison against a peer that
correctly omits it.
````

- [ ] **Step 2: Add §2g, known types**

````markdown
## 2g. Types with a known wire form

Some types are objects in code and something else entirely on the wire. `java.time.Instant`
is an ISO-8601 string; `java.math.BigDecimal` is a number; `google.protobuf.Timestamp` has
`seconds` and `nanos` fields and serialises to an RFC-3339 string. **Expanding them
structurally produces a shape no payload can match** — `BigDecimal` would contribute
`intVal`, `scale`, `intCompact` and `precision`, none of which exists on the wire.

Which types these are is **serialiser knowledge, not language knowledge**: `Instant` is an ISO
string under Jackson's `JavaTimeModule`, epoch millis without it, and whatever a custom
serialiser says. So a catalog declares them:

```yaml
known_types:
  - { type: java.time.Instant,           wire: string, format: date-time }
  - { type: java.time.LocalDate,         wire: string, format: date }
  - { type: java.math.BigDecimal,        wire: number }
  - { type: java.util.UUID,              wire: string, format: uuid }
  - { type: google.protobuf.Timestamp,   wire: string, format: date-time }
  - { type: google.protobuf.StringValue, wire: string, nullable: true }
```

This is the boundary against the extractor's own projection (§D1 of the Phase 2A plan): the
extractor converts what the **language** leaves no choice about — primitives, their boxes,
`String`, arrays, collections. A catalog converts what the **serialiser** decides.

**A third-party type with no entry here is not guessed at.** Expansion stops, the shape is
marked open, the type reference is kept, and [M04](M04-resolver.md) reports the type that
stopped it — so the catalog grows from observation rather than from a structural guess about
what looks "simple".
````

- [ ] **Step 3: Add the open decision to §7**

```markdown
| Whether a globally configured naming strategy is read from configuration, or only declared per catalog | §2f, and any module that sets one in `application.yml` |
```

- [ ] **Step 4: Commit**

```bash
git add docs/components/D02-catalog-schema.md
git commit -m "design: serialisation naming and known wire forms are catalog data (D02 2f, 2g)"
```

---

## Task 2: Fixture contracts with mixed nullability

Nothing to read means nothing to test. This task adds the Java payloads later tasks assert on,
and no production code.

**Files:**
- Modify: `fixtures/orders-service/pom.xml`
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/contracts/CustomerRef.java`, `OrderRequest.java`, `OrderView.java`
- Test: `tests/e2e/test_fixture_builds.py`

**Interfaces:**
- Produces: `com.acme.orders.contracts.OrderRequest` and `OrderView`, used by Tasks 10–12.

- [ ] **Step 1: Add the annotation dependencies**

```xml
<dependency>
  <groupId>org.jspecify</groupId>
  <artifactId>jspecify</artifactId>
  <version>1.0.0</version>
</dependency>
<dependency>
  <groupId>com.fasterxml.jackson.core</groupId>
  <artifactId>jackson-annotations</artifactId>
  <version>2.17.2</version>
</dependency>
```

- [ ] **Step 2: Write the payloads**

```java
package com.acme.orders.contracts;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.jspecify.annotations.NonNull;
import org.jspecify.annotations.Nullable;

public class OrderRequest {
    // No annotation: nullable by Java's rule, at resolution `partial` (D3).
    public String reference;
    // Declared nullable: resolution `resolved`.
    public @Nullable String note;
    // Declared not-null, overriding Java's permissive default — and renamed,
    // so `wire_name` is `customer_id` and never `customerId`.
    @JsonProperty("customer_id")
    public @NonNull String customerId;
    // Optional is a declared wrapper with `semantics: optional`, so this field
    // is `required: false` while staying `nullable: false`. The only case that
    // separates the two flags D00 §5a insists are independent.
    public Optional<String> note2;
    // Absent from the wire entirely: no shape_field at all.
    @JsonIgnore
    public String internalTrace;
    // A nested object, and a collection of them.
    public CustomerRef customer;
    public List<CustomerRef> alternates;
    // A primitive: not_null by the type system, projected by the extractor.
    public long total;
    // A known type: an object in code, a number on the wire. Expanding it
    // would contribute intVal, scale, intCompact and precision — none of which
    // exists on any payload (D2).
    @JsonProperty("total_amount")
    public BigDecimal totalAmount;
}
```

- [ ] **Step 2b: Write `OrderView` with a field whose type expansion must stop**

```java
package com.acme.orders.contracts;

import org.springframework.http.HttpHeaders;

public class OrderView {
    public String id;
    // Third-party, an object, and in no `known_types` entry — so expansion
    // stops here, the shape is marked open, and the type is reported.
    public HttpHeaders headers;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd fixtures/orders-service && mvn -q -o compile`
Expected: exit 0, `target/classes/com/acme/orders/contracts/OrderRequest.class` exists.

- [ ] **Step 4: Extend the fixture-build test to name the new classes**

```python
def test_fixture_produces_class_files_when_built():
    ...
    assert (classes / "com/acme/orders/contracts/OrderRequest.class").is_file()
```

- [ ] **Step 5: Commit**

```bash
git add fixtures/orders-service tests/e2e/test_fixture_builds.py
git commit -m "test: fixture payloads covering every nullability and naming case"
```

---

## Task 3: Field symbols, with the wire type and the language's nullability

**Implements D1 and the Java half of D3.** The extractor never overrides `visitField`, so
there are no field symbols and a shape has nothing to expand. Two pieces of language knowledge
stay here rather than leaking into the language-blind derivation: the **wire type**, and the
**language's own nullability rule** — in Java, every reference may hold null and no primitive
can.

**Files:**
- Create: `extractor-jvm/src/main/java/dev/sextant/extractor/WireTypes.java`
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/ClassScanner.java`
- Test: `extractor-jvm/src/test/java/dev/sextant/extractor/FieldScanTest.java`

**Interfaces:**
- Produces: a `symbol` fact with `construct_kind: "field"`, an `enclosing` naming the owning
  type, a `signature.returns` type reference carrying `wire_type`, `wire_format`, `nullable`
  and `nullable_resolution`. Consumed by Tasks 7, 10 and 11.

- [ ] **Step 1: Write the failing test**

```java
@Test
void emits_a_field_symbol_with_its_wire_type_when_a_class_has_fields() throws Exception {
    assertTrue(scan("OrderRequest").stream().anyMatch(line ->
        line.contains("\"construct_kind\":\"field\"")
            && line.contains("OrderRequest#total.")
            && line.contains("\"wire_type\":\"integer\"")
            && line.contains("\"wire_format\":\"int64\"")));
}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd extractor-jvm && ./gradlew test --tests '*FieldScanTest*'`
Expected: FAIL — no field facts are emitted at all.

- [ ] **Step 3: Write the projection**

```java
/** JVM descriptor to D00 §5b's wire vocabulary. Lives here because it is
 *  language knowledge: `J` means int64 to a JVM reader and to nobody else. */
final class WireTypes {
    static String of(Type type) {
        return switch (type.getSort()) {
            case Type.BOOLEAN -> "boolean";
            case Type.BYTE, Type.SHORT, Type.INT, Type.LONG, Type.CHAR -> "integer";
            case Type.FLOAT, Type.DOUBLE -> "number";
            case Type.ARRAY -> "array";
            default -> objectLike(type);
        };
    }

    static String format(Type type) {
        return switch (type.getSort()) {
            case Type.LONG -> "int64";
            case Type.INT, Type.SHORT, Type.BYTE -> "int32";
            case Type.DOUBLE -> "double";
            case Type.FLOAT -> "float";
            default -> "";
        };
    }
}
```

- [ ] **Step 4: Override `visitField`, mirroring `visitMethod`'s existing shape**

The field symbol ends in `.` like any member, carries its declaring type as `enclosing`, and
collects its annotations through the visitor `visitMethod` already uses.

- [ ] **Step 5: Emit Java's nullability rule on the type reference**

```java
// The language's own answer, not an annotation's. A primitive cannot hold null
// and the type system settles it; a reference may, but nothing declared that it
// should — so the claim is weaker and says so, rather than a third enum value
// existing (D00 §5a).
boolean nullable = type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY;
String resolution = nullable ? "partial" : "resolved";
```

- [ ] **Step 6: Write the failing test for it, run, implement, run again**

```java
@Test
void states_javas_own_nullability_rule_without_reading_any_annotation() throws Exception {
    List<String> lines = scan("OrderRequest");
    assertTrue(lines.stream().anyMatch(l -> l.contains("OrderRequest#reference.")
        && l.contains("\"nullable\":true") && l.contains("\"nullable_resolution\":\"partial\"")));
    assertTrue(lines.stream().anyMatch(l -> l.contains("OrderRequest#total.")
        && l.contains("\"nullable\":false") && l.contains("\"nullable_resolution\":\"resolved\"")));
}
```

- [ ] **Step 7: Run the whole extractor suite**

Run: `cd extractor-jvm && ./gradlew test`
Expected: PASS, and every existing test still green.

- [ ] **Step 8: Commit**

```bash
git add extractor-jvm
git commit -m "feat: emit field symbols with wire type and Java's nullability rule"
```

---

## Task 4: Type annotations, from both retention tables

JSpecify is `TYPE_USE` with `RUNTIME` retention, so it lands in
`RuntimeVisibleTypeAnnotations`. The older spellings — `javax.annotation.Nullable`, the
JetBrains ones — are mostly `CLASS` retention and land in the **Invisible** table.
[M03](../../components/M03-scanner.md) names only the Invisible one, and the scanner overrides
`visitTypeAnnotation` at neither level, so **today neither is read**.

**Files:**
- Modify: `extractor-jvm/.../ClassScanner.java`, `extractor-jvm/build.gradle.kts`,
  `extractor-jvm/src/test/java/dev/sextant/extractor/FieldSample.java`,
  `docs/components/M03-scanner.md`
- Test: `extractor-jvm/src/test/java/dev/sextant/extractor/TypeAnnotationScanTest.java`

**Two things Task 3 settled that this task inherits:**

- Extractor tests load a **committed** fixture via `getResourceAsStream`, never the sibling
  Maven module's gitignored build output. `./gradlew test` must pass on a fresh checkout with
  `fixtures/orders-service/target` absent — verify that, do not assume it.
- `extractor-jvm` has no JSpecify dependency, so a committed fixture cannot carry `@Nullable`
  until one is added. Add it **test-scope only**, so it stays out of the shaded jar:
  `testImplementation("org.jspecify:jspecify:1.0.0")`.

**Interfaces:**
- Produces: type annotations attached to the type reference they annotate, with `retention`
  recorded as `runtime` or `class` exactly as ordinary annotations already do.

- [ ] **Step 1: Give the committed fixture annotated fields**

Add to `FieldSample.java`:

```java
public @org.jspecify.annotations.Nullable String note;
public @org.jspecify.annotations.NonNull String required;
// The distinction D00 §5a says only a per-reference value can express:
// the outer type is nullable here, the element type below.
public @org.jspecify.annotations.Nullable java.util.List<String> maybeList;
public java.util.List<@org.jspecify.annotations.Nullable String> listOfMaybe;
```

- [ ] **Step 2: Write the failing tests, covering both tables and both positions**

```java
@Test
void records_a_type_use_annotation_on_a_field() throws Exception {
    assertTrue(scan().stream().anyMatch(l ->
        l.contains("FieldSample#note.") && l.contains("org/jspecify/annotations/Nullable#")));
}

@Test
void distinguishes_an_annotation_on_the_outer_type_from_one_on_a_type_argument() throws Exception {
    // `@Nullable List<String>` and `List<@Nullable String>` are different
    // contracts, and ASM tells them apart only through the TypePath. Without
    // it both collapse to "this field has a Nullable somewhere on it", which
    // is the ambiguity D00 §5a says the per-reference value exists to remove.
    List<String> lines = scan();
    assertTrue(lines.stream().anyMatch(l ->
        l.contains("FieldSample#maybeList.") && l.contains("\"type_path\":\"\"")));
    assertTrue(lines.stream().anyMatch(l ->
        l.contains("FieldSample#listOfMaybe.") && l.contains("\"type_path\":\"0;\"")));
}
```

- [ ] **Step 3: Run them and watch them fail**

Expected: FAIL — `visitTypeAnnotation` is never called back into.

- [ ] **Step 4: Override `visitTypeAnnotation` on the field and method visitors**

Signature is `visitTypeAnnotation(int typeRef, TypePath typePath, String descriptor,
boolean visible)`. Three things must be recorded, not two:

- the annotation itself, through the existing `useCollectingVisitor` so an enum or class
  argument is captured exactly as elsewhere;
- `retention`, from `visible` — `runtime` or `class`. **Both tables must be read.** JSpecify is
  `RUNTIME`; `javax.annotation.Nullable` and the JetBrains spellings are mostly `CLASS`, and a
  decade-old module carries several at once;
- **`type_path`**, as `String.valueOf(typePath)` (`null` renders as the empty string, meaning
  the outer type). Dropping it makes `@Nullable List<String>` and `List<@Nullable String>`
  indistinguishable, and Task 11 cannot then attach nullability to the right reference.

- [ ] **Step 4: Correct M03's capability row**

The row for `type_annotations` says the Invisible attribute; it must say both, and say why:
a codebase compiled over a decade carries several spellings at different retentions.

- [ ] **Step 5: Correct M03's capability row**

The row for `type_annotations` names the Invisible attribute; it must name both, and say why —
a codebase compiled over a decade carries several spellings at different retentions.

- [ ] **Step 6: Verify, including the fresh-checkout case**

```bash
cd extractor-jvm && ./gradlew clean build
rm -rf ../fixtures/orders-service/target && ./gradlew clean test   # must pass
cd ../fixtures/orders-service && mvn -q -o compile                 # restore for later tasks
cd ../.. && .venv/bin/pytest -q                                    # the FULL suite
```

The full Python suite matters: new fact output has broken stale assertions before. **If a
Python test fails, correct the assertion to the new truth — never loosen it — and say in the
report exactly what changed and why.**

- [ ] **Step 7: Commit**

```bash
git add extractor-jvm docs/components/M03-scanner.md
git commit -m "feat: read type annotations from both retention tables"
```

---

## Task 5: Kotlin nullability from `@Metadata`

**Implements the Kotlin half of D3.** Same rule as Task 3, different language: Kotlin's
nullability is in its type system, so it is `resolved` rather than `partial` — the type
declared it. No amount of annotation reading finds it. [D00](../../components/D00-fact-schema.md) §5a requires the adapter to
**project it into the shared field** rather than leave it in `ext.kotlin`, because anything
DR-5 compares cannot sit behind an extension read boundary.

**Files:**
- Create: `extractor-jvm/.../KotlinNullability.java`, `fixtures/orders-service/src/main/kotlin/com/acme/orders/contracts/KotlinOrder.kt`
- Modify: `extractor-jvm/build.gradle.kts`, `fixtures/orders-service/pom.xml`
- Test: `extractor-jvm/src/test/java/dev/sextant/extractor/KotlinMetadataTest.java`

**Interfaces:**
- Produces: `nullable` and `nullable_resolution: "resolved"` on the type reference of a Kotlin
  property, and `ext.kotlin.nullable` alongside it, so the shared field is populated and the
  raw fact is still recoverable.

- [ ] **Step 1: Add the metadata library, and Kotlin to the test source set**

```kotlin
plugins {
    java
    // Test-only: the committed Kotlin fixture below must be compiled by Gradle,
    // so `./gradlew test` stays self-contained on a fresh checkout. No Kotlin
    // reaches the shaded jar.
    kotlin("jvm") version "2.0.21"
    id("com.gradleup.shadow") version "9.6.1"
}

dependencies {
    implementation("org.jetbrains.kotlin:kotlin-metadata-jvm:2.0.21")
}
```

⚠️ **The artifact was renamed at Kotlin 2.0** — `org.jetbrains.kotlinx:kotlinx-metadata-jvm`
became `org.jetbrains.kotlin:kotlin-metadata-jvm`, **and the package changed from
`kotlinx.metadata` to `kotlin.metadata`**. ARCHITECTURE §9 still names the old artifact; the
coordinate above is the current one. Import `kotlin.metadata.jvm.KotlinClassMetadata`, not
`kotlinx.metadata.*`, or nothing resolves.

- [ ] **Step 2: Commit a Kotlin fixture Gradle compiles**

`extractor-jvm/src/test/kotlin/dev/sextant/extractor/KotlinSample.kt`:

```kotlin
package dev.sextant.extractor

data class KotlinSample(val id: String, val note: String?)
```

Loaded with `getResourceAsStream("/dev/sextant/extractor/KotlinSample.class")`, exactly as
`FieldSample` is — **not** from the Maven fixture, whose `target/` is gitignored and which
Gradle has no dependency on.

- [ ] **Step 2b: Also add the Kotlin fixture to the Maven module, for the end-to-end path**

`fixtures/orders-service/pom.xml` needs `kotlin-maven-plugin` bound so `mvn compile` builds
`src/main/kotlin` alongside `src/main/java`:

```xml
<plugin>
  <groupId>org.jetbrains.kotlin</groupId>
  <artifactId>kotlin-maven-plugin</artifactId>
  <version>2.0.21</version>
  <executions>
    <execution>
      <id>compile</id>
      <phase>process-sources</phase>
      <goals><goal>compile</goal></goals>
      <configuration>
        <sourceDirs>
          <sourceDir>${project.basedir}/src/main/kotlin</sourceDir>
          <sourceDir>${project.basedir}/src/main/java</sourceDir>
        </sourceDirs>
      </configuration>
    </execution>
  </executions>
</plugin>
```

with `fixtures/orders-service/src/main/kotlin/com/acme/orders/contracts/KotlinOrder.kt`:

```kotlin
package com.acme.orders.contracts

data class KotlinOrder(val id: String, val note: String?)
```

The Kotlin plugin must run **before** `maven-compiler-plugin` for mixed sources. Fetch the
plugin once with `mvn -q compile` (no `-o`), then confirm `mvn -q -o compile` works.

- [ ] **Step 3: Write the failing test against the committed Kotlin fixture**

```java
@Test
void projects_kotlin_type_system_nullability_onto_the_shared_field() throws Exception {
    List<String> lines = scan("KotlinSample");
    // Resolved, not partial: unlike Java, the Kotlin type itself declares it.
    assertTrue(lines.stream().anyMatch(l -> l.contains("KotlinSample#note.")
        && l.contains("\"nullable\":true")
        && l.contains("\"nullable_resolution\":\"resolved\"")));
    assertTrue(lines.stream().anyMatch(l -> l.contains("KotlinSample#id.")
        && l.contains("\"nullable\":false")
        && l.contains("\"nullable_resolution\":\"resolved\"")));
}
```

Note what this test would catch: a Kotlin field reaching Java's `partial` default means the
`@Metadata` read silently did nothing, which is the failure mode worth guarding.

- [ ] **Step 4: Read `@Metadata` and map property nullability**

- [ ] **Step 5: Verify the shaded jar actually carries the new dependency**

```bash
cd extractor-jvm && ./gradlew clean build
unzip -l build/libs/sextant-extractor.jar | grep -c "kotlin/metadata"   # must be > 0
```

The jar Gradle builds is at `extractor-jvm/build/libs/sextant-extractor.jar`. **Do not run it
with `--help`** — `Main` parses `--key value` pairs, so a flag with no value walks off the end
of `args`. Listing the jar's contents is the check that matters here: whether shading pulled
the dependency in.

- [ ] **Step 6: Verify the fresh-checkout case and the full Python suite**

```bash
cd extractor-jvm && rm -rf ../fixtures/orders-service/target && ./gradlew clean test  # must pass
cd ../fixtures/orders-service && mvn -q -o compile                                    # restore
cd ../.. && .venv/bin/pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add extractor-jvm fixtures/orders-service
git commit -m "feat: project Kotlin type-system nullability onto the shared field"
```

---

## Task 6: Declare and report the new capabilities

A capability that is not declared cannot gate a catalog, and
[FR-17](../../REQUIREMENTS.md#fr-17--coverage-reporting) requires every skip to trace to a
cause.

**Files:** Modify `src/sextant/ingress/extract/jvm/scanner.py`; Test `tests/ingress/test_asm_scanner.py`.

- [ ] **Step 1: Write the failing test**

```python
def test_scanner_declares_the_capabilities_phase_2a_implements():
    assert {"type_annotations", "kotlin_metadata"} <= AsmScanner(JAR).capabilities()
```

- [ ] **Step 2: Run it, watch it fail, add the two values, run again**

- [ ] **Step 3: Commit**

```bash
git add src/sextant/ingress/extract/jvm/scanner.py tests/ingress/test_asm_scanner.py
git commit -m "feat: declare the type-annotation and Kotlin-metadata capabilities"
```

---

## Task 7: The shapes tables

[D01](../../components/D01-graph-schema.md) §5 declares `shapes` (identifier, content hash,
whether open) and `shape_fields` (shape, ordinal, wire name, type, required, tags). Neither
exists.

**Files:** Modify `src/sextant/storage/duckdb/schema.sql`; Test `tests/storage/test_workspace.py`.

**Interfaces:**
- Produces: `shapes(shape_id, content_hash, open)`, `shape_fields(shape_id, ordinal,
  wire_name, wire_type, wire_format, required, nullable, resolution, evidence, tags, item)`,
  and `request_shape` / `response_shape` on `endpoints`.

**`item` exists because a single `wire_type` cannot describe a collection.** `List<String>`
and `List<CustomerRef>` are both `array`; without an element descriptor they are
indistinguishable, and DR-5 would match a caller sending an array of strings against a callee
expecting an array of records. Since Task 3's fix, the facts carry the element type — this is
where it lands.

`item` is JSON holding the same recursive descriptor a fact-level type reference uses:
`{wire_type, wire_format, nullable, shape_id?, item?}`. One shape in two places, so a reader
learns it once. It is `NULL` for a scalar, the element descriptor for an `array`, and the
**value** descriptor for a `map` — a JSON object's keys are always strings, so a key
descriptor would carry no information. Nesting recurses through `item`, so
`Map<String, List<String>>` needs no special case.

- [ ] **Step 1: Amend D01 §5 first — the column set differs from what it declares**

D01 §5 currently says `shape_fields` holds *"Shape, ordinal, wire name, type, required,
tags"*. The set above splits `type` into `wire_type` and `wire_format`, and adds `nullable`,
`resolution` and `evidence`. Those additions are required by decisions D1 and D3 — nullability
is two flags, and each carries its own trust — but **a schema differing from its spec is a
deviation, not an implementation detail** (`GUIDELINES.md` §1.1, §5.1). Amend D01 §5 to state
the full column list and why, before writing the DDL. `tags` stays: it is in the spec, and
dropping it silently would be the same defect in the other direction.

- [ ] **Step 2: Write the failing test**

```python
def test_the_shape_tables_answer_an_empty_query_rather_than_raising(tmp_path: Path):
    """Pre-declared for the same reason `endpoints` is: a scanner too weak to
    populate them must degrade visibly through skipped_catalogs, not crash."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    assert workspace.query("shapes") == []
    assert workspace.query("shape_fields") == []
    workspace.close()


def test_endpoints_carry_the_two_shape_columns(tmp_path: Path):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.derive("endpoints_reset")
    columns = workspace.query("endpoints")
    workspace.close()
    # Empty result, so assert on the declared schema rather than on rows.
    assert columns == []
```

Add `shapes` and `shape_fields` to `_NAMED_QUERIES` with a deterministic `ORDER BY`
(`shape_id` and `shape_id, ordinal` respectively) — an ordering with ties is an ordering that
can change between runs (NFR-1).

- [ ] **Step 3: Run, watch it fail, add the tables and named queries, run again**
- [ ] **Step 4: Run the full suite and commit**

```bash
.venv/bin/pytest -q && git commit -m "feat: shapes and shape_fields tables, and endpoint shape columns"
```

---

## Task 8: Declare wrappers, nullability, serialisation and known types in the Spring catalogs

[D02](../../components/D02-catalog-schema.md) §2a's `wrappers` block exists in the spec and in
**neither catalog**; §2e's `nullability` and §2f's `serialization` are new.

**Files:** Modify `src/sextant/catalogs/spring-web.yml`, `spring-mvc.yml`; Test `tests/application/test_endpoints.py`.

- [ ] **Step 1: Add the three blocks**

```yaml
wrappers:
  - { type: org.springframework.http.ResponseEntity, payload_arg: 0, semantics: http_envelope }
  - { type: reactor.core.publisher.Mono,             payload_arg: 0, semantics: async }
  - { type: reactor.core.publisher.Flux,             payload_arg: 0, semantics: streaming }
  - { type: java.util.concurrent.CompletableFuture,  payload_arg: 0, semantics: async }
  - { type: java.util.Optional,                      payload_arg: 0, semantics: optional }

nullability:
  nullable: [org.jspecify.annotations.Nullable, org.springframework.lang.Nullable,
             javax.annotation.Nullable, jakarta.annotation.Nullable,
             org.jetbrains.annotations.Nullable]
  not_null: [org.jspecify.annotations.NonNull, org.springframework.lang.NonNull,
             org.jetbrains.annotations.NotNull]
  scope:
    - { annotation: org.jspecify.annotations.NullMarked, means: not_null_by_default }

serialization:
  name_from:
    - { annotation: com.fasterxml.jackson.annotation.JsonProperty, arg: value }
  ignore: [com.fasterxml.jackson.annotation.JsonIgnore]
  default_strategy: as_declared

known_types:
  - { type: java.time.Instant,    wire: string, format: date-time }
  - { type: java.time.LocalDate,  wire: string, format: date }
  - { type: java.math.BigDecimal, wire: number }
  - { type: java.util.UUID,       wire: string, format: uuid }
```

**The JetBrains entries are not only for JetBrains-annotated Java.** Verified with `javap`
against the compiled fixture: the Kotlin compiler emits
`org.jetbrains.annotations.NotNull` / `@Nullable` directly onto fields as **CLASS-retention**
annotations, for Java interop — `val id: String` gets `@NotNull`, `val note: String?` gets
`@Nullable`. Task 4 already reads the invisible retention table where those land.

So **Kotlin nullability arrives through the ordinary annotation path**, and `@Metadata`
stops being the only source for it. That matters operationally: `kotlin-metadata-jvm`'s
supported version always trails the compiler's, and a module built with a newer Kotlin makes
the metadata read fail. With these two entries present, such a module still gets correct
nullability from the annotations — the metadata read becomes a cross-check rather than a
single point of failure.

- [ ] **Step 2: Raise `requires` to match what the catalog now depends on**

```yaml
requires: [annotation_args, type_annotations]
```

Without this a scanner lacking `type_annotations` runs the catalog anyway and silently
produces no nullability — the exact bypass capability gating exists to prevent, and
[FR-17](../../REQUIREMENTS.md#fr-17--coverage-reporting) requires every skip to trace to a
cause.

- [ ] **Step 3: Test that the catalog loads, declares all five wrappers, and requires the new capability**
- [ ] **Step 4: Commit**

---

## Task 9: Unwrap to root a shape

`Mono<ResponseEntity<OrderView>>` roots at `OrderView`. **An unfamiliar wrapper is not
unwrapped** — the shape roots at the wrapper and records that no rule matched, so an
incomplete catalog degrades visibly rather than guessing (D02 §2a).

**Files:** Create `src/sextant/application/resolve/shapes.py`,
`tests/application/shape_helpers.py`; Test `tests/application/test_shapes.py`.

**Interfaces:**
- Produces: `root_type(type_ref: dict, wrappers: list[dict]) -> RootedType`, a frozen
  dataclass with `symbol: str`, `chain: tuple[str, ...]` (the `semantics` values removed,
  outermost first) and `unmatched_wrapper: bool`.
- Produces `tests/application/shape_helpers.py`, used by Tasks 10, 11 and 12.

**The test helpers Tasks 9–12 share must be written here, once.** They are referenced by name
in every later task, and each defines them differently if left implicit:

```python
# tests/application/shape_helpers.py
def type_ref(symbol: str, *arguments: dict) -> dict:
    """A D00 §5a type reference: a symbol plus recursive type arguments."""
    return {"symbol": symbol, "arguments": list(arguments)}


ORDER_VIEW = type_ref("com/acme/orders/contracts/OrderView#")


def mono_of(inner: dict) -> dict:
    return type_ref("reactor/core/publisher/Mono#", inner)


def response_entity_of(inner: dict) -> dict:
    return type_ref("org/springframework/http/ResponseEntity#", inner)


def unknown_box_of(inner: dict) -> dict:
    return type_ref("com/acme/UnknownBox#", inner)


SPRING_WRAPPERS = [
    {"type": "reactor.core.publisher.Mono", "payload_arg": 0, "semantics": "async"},
    {"type": "org.springframework.http.ResponseEntity", "payload_arg": 0,
     "semantics": "http_envelope"},
    {"type": "java.util.Optional", "payload_arg": 0, "semantics": "optional"},
]


def shape_fields_of(workspace, shape_id: str) -> list[dict]:
    """Every field of one shape, in ordinal order."""
    return [f for f in workspace.query("shape_fields") if f["shape_id"] == shape_id]


def field_of(workspace, shape_id: str, wire_name: str) -> dict:
    """One field, **keyed by its wire name — never the source field name.**

    D01 §5 makes `wire_name` the identity, so `customerId` is looked up as
    `customer_id`. Keying on the source name here would quietly reintroduce
    the thing that section exists to forbid.
    """
    return next(f for f in shape_fields_of(workspace, shape_id) if f["wire_name"] == wire_name)
```

- [ ] **Step 1: Write the failing tests**

```python
def test_unwraps_recursively_to_the_payload_type():
    rooted = root_type(mono_of(response_entity_of(order_view)), SPRING_WRAPPERS)
    assert rooted.symbol == "com/acme/orders/contracts/OrderView#"
    assert rooted.chain == ("async", "http_envelope")


def test_stops_at_an_unfamiliar_wrapper_and_says_so():
    """An incomplete catalog must degrade visibly. Rooting at the payload of a
    wrapper nobody declared would be a guess presented as an observation."""
    rooted = root_type(unknown_box_of(order_view), SPRING_WRAPPERS)
    assert rooted.symbol == "com/acme/UnknownBox#"
    assert rooted.unmatched_wrapper is True
```

- [ ] **Step 2: Run, watch both fail, implement, run again**
- [ ] **Step 3: Commit**

---

## Task 10: Expand a rooted type into fields

**Implements D2.** Expand types with field facts to any depth. A type with a
`known_types` entry is mapped to its wire form and never expanded. Any other type without
field facts stops expansion: the reference is kept, the shape is marked open, and the type is
reported so the catalog can grow from evidence.

**Files:** Create `src/sextant/storage/duckdb/derive_shapes.sql`; Modify `shapes.py`,
`src/sextant/storage/duckdb/schema.sql`, `workspace.py`, `tests/application/shape_helpers.py`;
Test `tests/application/test_shapes.py`.

**Where the pass runs (pre-flight ruling F5).** The expansion pass is computed in
`shapes.py` — it must reuse Task 9's `root_type` and `_catalog_symbol` for field-level
wrappers and dotted→SCIP conversion, and the recursive `item` descriptor cannot be assembled
bottom-up in one SQL statement. `derive_shapes.sql` is the materialisation step: it resets
`shapes`/`shape_fields` (`CREATE OR REPLACE TABLE`) and inserts the rows the pass computed,
handed over as bound JSON parameters. Language-blindness still holds — the architecture tests
already scan `shapes.py`, and the grep test on `derive_shapes.sql` stays in Task 11. The
pass reads field facts through the workspace port: add a `fields` named query (or view) to
`schema.sql`/`workspace.py` exposing, per field symbol fact, its symbol, its defining
document, its `signature.returns` JSON, and a `seq` column from `rowid` — declaration order
within a document, the `ordinal` source. Add an `annotations_of` route for the pass to read
serialisation annotations by target.

**Shape identity (pre-flight ruling F1).** `shape_id` **is** the type's descriptor symbol —
`com/acme/orders/contracts/OrderRequest#` — the same grammar type references already use.
`content_hash` is md5 over the ordered projected field rows and is the change-detection
value, never the identity: `item` descriptors reference other shapes by `shape_id`, so a
content-derived *identity* for `Node { Node parent; }` would depend on itself.

**Entry point.** `derive_shapes(workspace, catalog, roots: Sequence[str])` — the roots are
type-descriptor symbols, handed in explicitly. Task 12 computes them from endpoints; this
task's tests pass them directly. Two catalogs may both run (D02 §5): the reset happens once
per resolve, and a shape already present for the same `shape_id` is not inserted twice —
the same insert-if-absent discipline `derive_endpoints.sql` uses.

- [ ] **Step 1: Write the failing tests**

Hand-build the fact files with `write_fact_file`, following `test_endpoints.py`'s pattern —
never read the gitignored Maven `target/classes` from a unit test (Task 3's lesson). Mirror
the fixture's contracts classes verbatim (same symbols, same annotations, the
`signature.returns` JSON exactly as the extractor emits it: `symbol`, `arguments`,
`wire_type`, `wire_format`, `nullable`, `nullable_resolution` at every level). Add to
`shape_helpers.py`: `ORDER_REQUEST = "com/acme/orders/contracts/OrderRequest#"`, and
`shape_of(workspace, shape_id)` returning the one `shapes` row. `shape_id_of` is not needed
— a shape's id IS the descriptor symbol (ruling F1).

```python
def test_expands_a_rooted_type_into_its_wire_fields(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])   # local helper: facts + catalog + derive_shapes
    fields = shape_fields_of(ws, ORDER_REQUEST)
    names = [f["wire_name"] for f in fields]
    assert "customer_id" in names          # @JsonProperty wins over the source name
    assert "customerId" not in names       # the source name is never the identity
    assert "internalTrace" not in names    # @JsonIgnore produces no field at all
    assert next(f for f in fields if f["wire_name"] == "total")["wire_format"] == "int64"


def test_a_collection_field_records_what_it_holds(tmp_path):
    """`List<String>` and `List<CustomerRef>` are both `array`. Without the
    element descriptor DR-5 matches a caller sending strings against a callee
    expecting records — a fabricated link, which is the failure the whole
    payload-comparison rule exists to prevent."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "alternates")

    assert field["wire_type"] == "array"
    assert json.loads(field["item"])["shape_id"] == "com/acme/orders/contracts/CustomerRef#"
```

- [ ] **Step 2: Run, watch it fail, write the pass, run again**

The pass takes the catalog data below (dotted names converted through `_catalog_symbol` at
the binding seam, exactly where Task 9 converts wrapper names):

| Input | From |
|---|---|
| `known_types` | D02 §2g — `{type, wire, format, nullable}` rows |
| `name_from` | D02 §2f — `{annotation, arg}` rows supplying a wire name |
| `ignore` | D02 §2f — annotations meaning "absent from the wire" |
| `default_strategy` | D02 §2f |
| `wrappers` | D02 §2a — for field-level envelopes (rule 3 below) |

and produces `shapes` and `shape_fields` rows. Per field, in this order:

1. **Ignored?** If the field carries an `ignore` annotation, emit nothing. Not a field marked
   absent — *no row*, or DR-5 compares it against a peer that correctly omits it.
2. **Wire name.** First `name_from` annotation whose argument is present, else the source
   name under `default_strategy`. A name from the default carries `evidence: declared`; one
   from an annotation carries the evidence of the code that declared it (D02 §2f).
3. **Unwrap.** Root the field's type reference through the catalog's `wrappers` with Task 9's
   `root_type` and continue from the rooted type. The semantics chain is recorded for Task 11
   — `optional` in the chain is the presence machinery that makes `required: false`. Without
   this rule, `Optional<String>` falls to rule 5 as an unknown generic and wrongly marks the
   shape open.
4. **Wire type.** `known_types` first — a known type is mapped and **never expanded**. Then
   the `wire_type`/`wire_format` the extractor already put on the type reference (D1).
   **For an `array` or a `map`, recurse into the type reference's `arguments` and build the
   `item` descriptor**, applying rules 4 and 5 to the element exactly as to any other type
   (the **value** argument for a map — a JSON object's keys are always strings): a known
   element type is mapped, an element with field facts expands to its own shape and `item`
   carries that `shape_id`, and an unknown one stops and marks the shape open. Without this,
   `List<CustomerRef>` and `List<String>` are the same field.
5. **Expand or stop.** An `object` **with field facts** expands to its own shape,
   recursively. Anything else stops: the referenced type still gets a `shapes` row — open,
   zero fields — so the reference is kept (D2) and the report can name it; the shape holding
   the field is marked `open` too (direct, not transitive). **An `object` field's `item`
   carries the reference either way**: `{"wire_type": "object", "shape_id": <ref>}` —
   without it, nothing links the field to the shape it holds (pre-flight ruling F3).
   `unexpanded_types` = the open shapes with zero fields, exposed by the pass's return value
   so [M04](../../components/M04-resolver.md) can report it (D2).

There is no origin test: expansion needs field facts, and only scanned types have them — a
first-party type from a jar stops exactly as a third-party one does (pre-flight ruling F4).

**Cycles terminate by construction** — `object` is a *reference* to another shape, never an
inlining, so `Node { Node parent; }` needs no depth counter. Expand each `shape_id` at most
once per pass.

**Determinism (NFR-1):** `ordinal` is declaration order — the `seq` (rowid) order of the
field facts within their defining document — and `content_hash` is md5 over the ordered
field list. Neither may come from a set or a dictionary iteration order, or two runs differ.

Columns this task leaves for Task 11: `required`, `nullable`, `resolution` may carry the
extractor's raw answer (or NULL) until Task 11 applies the catalog; `tags` stays NULL.

- [ ] **Step 3: Add the three boundary tests**

```python
def test_a_known_type_is_mapped_to_its_wire_form_and_never_expanded(tmp_path):
    """Expanding BigDecimal yields intVal, scale, intCompact and precision —
    internal machinery, none of it on the wire, producing a shape no real
    payload could match."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "total_amount")
    assert field["wire_type"] == "number"
    # Mapped, never expanded: no shape exists for it, open or otherwise.
    assert not any(s["shape_id"] == "java/math/BigDecimal#" for s in ws.query("shapes"))


def test_expansion_stops_at_an_unknown_third_party_type_and_marks_the_shape_open(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=["com/acme/orders/contracts/OrderView#"])
    assert shape_of(ws, "com/acme/orders/contracts/OrderView#")["open"] is True


def test_the_report_names_the_type_that_stopped_expansion(tmp_path):
    """The catalog grows from observation. A gap nobody can see is a gap
    nobody closes."""
    result = _expand(tmp_path, roots=["com/acme/orders/contracts/OrderView#"])
    assert "org/springframework/http/HttpHeaders#" in result.unexpanded_types
```

- [ ] **Step 4: Run the full suite and commit**

---

## Task 11: Apply the catalog's nullability and presence rules

**Implements the derivation half of D3.** Tasks 3 and 5 already emitted each language's own
answer. This task stays **language-blind**: it applies catalog-declared annotations on top of
whatever the extractor said, and never contains a rule about Java or Kotlin.

Two independent two-valued flags (D00 §5a). `nullable` comes from the language, overridden by
a declared annotation. `required` comes from **presence machinery only** — an `optional`
wrapper, a Jackson `required` attribute, a default argument — and never from a nullability
annotation, because they answer different questions.

**Files:** Modify `derive_shapes.sql`, `shapes.py`; Test `tests/application/test_shapes.py`.

**Interfaces:**
- Consumes: `nullable` / `nullable_resolution` on type references (Tasks 3, 5); the
  `nullability` block (Task 8); the per-field wrapper chain rule 3 of Task 10 recorded.
- Produces: `shape_fields.nullable`, `.required`, `.resolution`, `.evidence`.

Tests hand-build facts exactly as Task 10's do, mirroring the fixture classes. The
`annotations` view does not yet project `type_path` or `retention` — extend it (pre-flight
ruling F7): **only an annotation whose `type_path` is NULL or `''` speaks about the field's
own type**; `List<@Nullable String>` annotates the element, not the field, and must not flip
the field's `nullable`. Catalog `nullability` names are dotted and convert through
`_catalog_symbol` at the binding seam, like every other catalog block.

- [ ] **Step 1: Write the failing tests — the language answer, the override, and the scope**

Under ruling B (ledgered; D00 §5a as amended), the JVM extractor emits `resolution:
resolved` for every field — Java's type system settles nullability outright. The override
rule "a catalog-declared source sets `resolution` to `resolved`" stays, because it is what
lifts a genuinely weaker answer (unannotated Python, later) — on the JVM it is a no-op.

```python
def test_the_language_answer_survives_when_no_catalog_annotation_applies(tmp_path):
    """The extractor already decided. The derivation must not re-derive it, or
    the same rule ends up in two places and they will diverge."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "reference")
    assert field["nullable"] is True
    assert field["resolution"] == "resolved"    # ruling B: Java answers outright


def test_a_not_null_annotation_overrides_javas_permissive_default(tmp_path):
    # Looked up by WIRE name: the field is `customerId` in Java and
    # `customer_id` on the wire, and D01 §5 makes the wire name the identity.
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "customer_id")
    assert field["nullable"] is False
    assert field["resolution"] == "resolved"


def test_a_declared_nullable_annotation_agrees_with_the_language_default(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "note")
    assert field["nullable"] is True
    assert field["resolution"] == "resolved"


def test_kotlin_arrives_already_resolved_and_is_not_downgraded(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[KOTLIN_ORDER])
    assert field_of(ws, KOTLIN_ORDER, "note")["nullable"] is True
    assert field_of(ws, KOTLIN_ORDER, "id")["nullable"] is False


def test_a_null_marked_scope_inverts_the_default_for_everything_inside_it(tmp_path):
    """The scope is itself a declaration, so absence carries meaning."""
    ws = _expanded_workspace(tmp_path, roots=[SCOPED_REQUEST])
    field = field_of(ws, SCOPED_REQUEST, "code")
    assert field["nullable"] is False
    assert field["resolution"] == "resolved"


def test_presence_is_never_read_from_a_nullability_annotation(tmp_path):
    """`required` and `nullable` answer different questions (D00 §5a). Bean
    Validation's @NotNull is the trap: it constrains a value at validation time
    and says nothing about whether the field may be omitted."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    assert field_of(ws, ORDER_REQUEST, "note")["required"] is True


def test_an_optional_wrapper_makes_a_field_not_required(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    assert field_of(ws, ORDER_REQUEST, "note2")["required"] is False


def test_the_derivation_names_no_language():
    """Language-blind by test, not by intention. The per-language rules live in
    the extractors; this file must contain none of them. (The pass itself lives
    in shapes.py, which the architecture tests already scan.)"""
    source = (SQL_DIR / "derive_shapes.sql").read_text().lower()
    assert not {"java", "kotlin", "jvm"} & set(re.findall(r"[a-z]+", source))
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/application/test_shapes.py -v`
Expected: FAIL — `shape_fields` carries no nullability yet.

- [ ] **Step 3: Add a `ScopedRequest` to the fixture under `@NullMarked`**

```java
@org.jspecify.annotations.NullMarked
package com.acme.orders.scoped;
```

The fixture addition keeps the conformance fixture honest (D02 §4) and feeds Task 12's
end-to-end run; the unit tests above hand-build the same facts. The scope rule is symbol
**prefix** matching: a scope annotation's target claims every field symbol it prefixes — a
type-level target (`com/acme/X#`) is naturally a prefix of its members (`com/acme/X#code.`),
and a package-scope target claims the package after its trailing file-class name is
stripped. No language name appears: it is string prefixing over one symbol grammar.

- [ ] **Step 4: Implement the override, then run again**

The order is: the extractor's answer, then a scope rule if one encloses the field, then an
explicit annotation on the field's own type (`type_path` NULL or `''`). Last wins, and any
catalog-declared source sets `resolution` to `resolved`. `required` is `True` unless
presence machinery says otherwise — in this phase, the `optional` wrapper semantics recorded
by Task 10's rule 3.

- [ ] **Step 5: Commit**

```bash
git add src/sextant tests/application/test_shapes.py fixtures/orders-service
git commit -m "feat: apply catalog nullability over the language's own answer"
```

---

## Task 12: Endpoints carry their contract

**Files:** Modify `derive_endpoints.sql`, `pipeline.py`, `egress/render/metadata.py`, `document.py`; Test `tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py`.

- [ ] **Step 1: Give the fixture an endpoint that actually carries these shapes**

The fixture's existing `POST /v1/orders` takes `OrderCommand` and returns a bare
`OrderResult`. **Nothing in the fixture takes `OrderRequest`, and nothing returns a wrapped
type** — so Task 9's unwrapping has no end-to-end coverage and the test below cannot be
written against what exists. Add to `OrderController`:

```java
// The one endpoint that exercises the whole chain: a request payload covering
// every nullability and naming case, and a response wrapped twice, so rooting
// has something real to unwrap.
@PostMapping("/detailed")
public ResponseEntity<OrderView> createDetailed(@RequestBody OrderRequest request) {
    return ResponseEntity.ok(new OrderView());
}
```

Rebuild: `cd fixtures/orders-service && mvn -q -o compile`.

- [ ] **Step 2: Write the failing end-to-end test**

The pipeline-level test follows `test_pipeline.py`'s existing end-to-end pattern (compile
the fixture, scan, `resolve`); `workspace.query("shape_fields")` reads the fields.

```python
def test_an_endpoint_carries_the_request_and_response_shapes_it_declares(tmp_path: Path):
    report = _resolved_fixture(tmp_path)     # the module-level e2e helper pattern
    endpoint = next(e for e in report.endpoints
                    if e["method"] == "POST" and e["path"] == "/v1/orders/detailed")

    assert endpoint["request_shape"] == "com/acme/orders/contracts/OrderRequest#"
    ws_fields = shape_fields_of(workspace, endpoint["request_shape"])
    assert "customer_id" in [f["wire_name"] for f in ws_fields]
    # The response is ResponseEntity<OrderView>; the shape must root at
    # OrderView, or the wrapper declarations in Task 8 did nothing.
    assert endpoint["response_shape"] == "com/acme/orders/contracts/OrderView#"
```

- [ ] **Step 3: Join endpoints to shapes through the `@RequestBody` parameter and the rooted return type**

The roots are computed in the resolve pass (Python), not re-derived in SQL: for each
endpoint's handler signature, the request root is the type of the parameter annotated with
the catalog's `request_body_annotation` (already in `matches`), and the response root is the
return type unwrapped through Task 9's `root_type`. Hand the collected roots to Task 10's
`derive_shapes`, then set each endpoint's `request_shape`/`response_shape` — a small
parameterised UPDATE derivation is fine; `derive_endpoints.sql` itself need not change. **A
scalar root produces no shape and leaves the column NULL** — a `String` response has no
field list to compare, and an invented shape row would be noise presented as fact. A rooted
type that stopped expansion still gets its open, zero-field shape row (Task 10 rule 5), so
the endpoint's column still points at a real row.

`ResolveReport` gains `shapes` and `unexpanded_types`; `metadata.json` carries the shape
count and the full unexpanded list (a count cannot be acted on — same rule as `uncovered`).

- [ ] **Step 4: Stop declaring the gap that no longer exists**

`shape_expansion_not_implemented` comes out of `metadata.py`'s omission list **and its paired
sentence out of `document.py`'s `_GAPS`** — the two are kept in lockstep by that file's own
comment. **Any part still unimplemented keeps its own named omission** — removing the label
without removing the gap is the failure FR-17 exists to prevent.

- [ ] **Step 5: Verify determinism**

Run the pipeline twice into different workspaces and diff `metadata.json`. Field order must
be declaration order, and `content_hash` must be derived from the ordered field list
(`shape_id` is the rooted type's symbol — pre-flight ruling F1), or the two runs differ.
The existing byte-identical double-run e2e test is the net; extend its assertions only if
shapes do not already flow into the compared files.

- [ ] **Step 6: Run every gate**

Run: `scripts/check.sh`
Expected: all green, including the architecture source rules — no framework name has leaked
into the derivation, and `application/` still performs no file I/O.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat: endpoints carry their request and response contracts"
```

---

## Self-review against the spec

**Coverage.** D00 §5a typed signatures → Tasks 3–5. D00 §5b wire vocabulary → Task 3 (D1).
D00 §5a presence and nullability → Task 11. D01 §5 shapes tables and `wire_name` identity →
Tasks 7, 10. D02 §2a wrappers → Tasks 8, 9. D02 §2e nullability → Tasks 8, 11. D02 §2f
serialisation → Tasks 1, 8, 10. D02 §2g known types → Tasks 1, 8, 10. M03 capabilities → Tasks 3–6. FR-17 reporting → Task 12.

**Not covered, deliberately.** `constant_propagation`, `chain_reconstruction`, `control_flow`
and `invokedynamic` belong to 2D and 2E. Declared shapes loaded from `declared_shape` facts
(OpenAPI, protobuf) are a tier-2 artifact reader, not this plan — but Task 7's tables are the
ones they land in, so no second schema is created for them.

**Known risk.** Task 5 adds the first non-ASM dependency to the extractor jar. If shading
`kotlinx-metadata-jvm` conflicts, the fallback is to read the `@Metadata` annotation's
`d1`/`d2` arrays directly — more work, no new dependency — and that changes the task, not the
plan.
