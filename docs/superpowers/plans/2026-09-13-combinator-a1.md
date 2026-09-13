# Combinator PR A1 Implementation Plan — the two fact fields, overload discrimination, the builder form, the corrected DSL rules

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `G-37`, `W44-verb-overloads` and `GAP-1b` — the `RouterFunctions.route().GET(…).build()` builder form derives every route on both Spring stacks, the seven Kotlin `RouterFunctionDsl` verb rules stop publishing a lambda or a predicate as a URL, the WebFlux non-coroutine `router { }` derives — and land the two call-site fact fields Part II needs, proven to move nothing that exists.

**Architecture:** The extractor gains two optional keys on a call-site fact (`receiver_parameter`, and `captures` on a `lambda` argument), projected as nullable columns and read by nothing in this PR. `combinator` (`src/sextant/application/resolve/engines/combinator.py`) keeps `verbs`/`prefixes` as scanned lists keyed on owner + name + `arity` + `arg_types` instead of a dict that lets a second overload overwrite the first; a verb may extend its receiver (a builder chain), an `origins` role marks where a chain starts without poisoning it, and a pass-through continuation carries a chain without reading its arguments. Catalog data on both router catalogs then declares the builder and the five-per-verb DSL overloads.

**Tech Stack:** Java 21 + ASM (extractor, Gradle), Python 3.14 + pydantic + DuckDB (resolve), YAML catalogs, pytest with `-n 4 --dist loadfile`, Maven fixtures.

**Spec:** `docs/superpowers/specs/2026-09-11-combinator-overload-discrimination-design.md` — Part I (§1–§8) and Part II §10–§11 and §16 items 1–4. Read the spec before any task; every rule below argues from it.

## Global Constraints

- **Nothing that works today may move** (spec header, §11). Task 2's double-scan proof and both-corpora table diff run and pass before Task 3 starts; the full suite is green after every task.
- **No stamp bump.** `FACT_SCHEMA_VERSION` stays `5` (`src/sextant/domain/version.py:41`, "FROZEN UNTIL RELEASE"). No `pyproject.toml` version change.
- **Never a wrong row.** A site the vocabulary names but no rule accepts derives one row with `resolution: unresolved` — never silence, never a value read off the wrong position (spec §3 "The G-13 guard").
- **Never file order.** Two rules that could both accept one call are a `CatalogError` at load naming both (spec §3c).
- **Language confinement:** no language or framework name as a whole word in `src/**` prose (`tests/architecture/test_language_confinement.py`) — say "the extractor", "a body method", "the reactive stack"; catalog YAML files are exempt.
- **Plain language** in comments, docstrings, commit messages: say what was done; no "mutations caught", "blast radius", "battle-tested".
- **Per-item loop:** every task ends with the full gate in the foreground — `JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh` — then one commit. `git add`/`git commit` only: never `stash`, `checkout --`, `reset`, `push`, worktrees, or branches.
- **Fact trees are not committed** (`.sextant/` is gitignored). Nothing in `fixtures/**/.sextant` or `target/` is ever `git add`ed.
- **Catalog discipline:** every new `combinator` rule states its owner as a dotted fqn; `measured` blocks and the w19 probe are regenerated, not hand-edited, where a number changes.
- **Tests that pin a fixture total move with the fixture** — `tests/application/test_pipeline.py::test_resolve_finds_every_fixture_endpoint_exactly_once_when_run_end_to_end` and `tests/e2e/test_vertical_slice.py::test_the_document_names_every_fixture_endpoint_and_its_gaps` list every route; a new fixture source adds rows to both, and the plan says which.

---

## File map

| file | responsibility in this plan |
|---|---|
| `extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java` | writes `receiver_parameter` on a call site and `captures` on a `lambda` argument (Task 1) |
| `extractor-jvm/src/test/java/dev/sextant/extractor/CallSample.java`, `MethodFlowTest.java`, `extractor-jvm/src/test/kotlin/dev/sextant/extractor/KotlinCaptureSample.kt`, `KotlinCaptureTest.java` | pin the six capture shapes (Task 1) |
| `src/sextant/domain/facts.py` | `CallSiteFact.receiver_parameter`, `CallArgument.captures` (Task 2) |
| `src/sextant/storage/duckdb/schema.sql` | `call_sites.receiver_parameter` column (Task 2) |
| `scripts/probes/fact_additivity/run.py` | the double-scan proof: scan every fixture with two jars, strip the two keys, byte-compare; table-diff both corpora (Task 2) |
| `src/sextant/domain/symbols.py` | `descriptor_parameter_types` — a JVM descriptor's parameter list as dotted names (Task 3) |
| `src/sextant/application/resolve/engines/combinator.py` | scanned-list vocabulary, `arity`/`arg_types`, the unrecognised-overload row, load-time ambiguity refusal (Task 3); `extends_receiver`, `origins`, pass-through continuations, handler-less resource verbs (Task 4) |
| `tests/application/test_combinator_engine.py` | engine tests on hand-built facts (Tasks 3, 4) |
| `scripts/guard_check.py` | two new guards: `combinator.unrecognised-overload-is-a-row`, `combinator.origin-is-declared` (Tasks 3, 4) |
| `src/sextant/catalogs/spring-webflux-router.yml`, `spring-mvc-router.yml` | builder rules, `RouterFunctionDsl` five-per-verb rules, `RouterFunctionDslKt.router` entry, slice moves (Tasks 4, 5) |
| `fixtures/orders-service/src/main/java/com/acme/orders/routes/BuilderRoutes.java`, `…/mvcroutes/MvcBuilderRoutes.java`, `…/src/main/kotlin/com/acme/orders/routes/KotlinWebFluxRoutes.kt`, `…/mvcroutes/KotlinMvcRoutes.kt` | the fixture sources (Tasks 4, 5) |
| `tests/e2e/test_rest_inbound_delivered.py`, `tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py` | live rows and the moved fixture totals (Tasks 4, 5) |
| `scripts/probes/w19_catalog_surface.md` | regenerated: `RouterFunctions$Builder` 20 of 20 on both stacks (Task 4) |
| `docs/java-kotlin-delivery-list.md`, `docs/COVERAGE.md` | the three ids move to `closed` with the CI run; matrix regenerated (Task 6, after CI) |

---

### Task 1: the extractor writes `receiver_parameter` and `captures`

**Files:**
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java` (the call-site loop near line 103, `argumentJson`'s indy branch near line 656, `sourceId` at line 926, `callSiteJson` at line 948, the `argument(...)` helpers near line 900)
- Modify: `extractor-jvm/src/test/java/dev/sextant/extractor/CallSample.java`
- Modify: `extractor-jvm/src/test/java/dev/sextant/extractor/MethodFlowTest.java`
- Create: `extractor-jvm/src/test/kotlin/dev/sextant/extractor/KotlinCaptureSample.kt`
- Create: `extractor-jvm/src/test/java/dev/sextant/extractor/KotlinCaptureTest.java`

**Interfaces:**
- Produces: on every call-site JSON line, an optional integer key `receiver_parameter` (present only when the receiver is the enclosing method's parameter N, D00 §5 numbering); on every `{"kind":"lambda"}` argument, an integer key `captures` = the `invokedynamic`'s argument count minus one when the implementation handle is an instance kind. `-1` therefore means "the interface's first parameter is the body's receiver". Absent on every other argument kind. Key order inside an object is alphabetical (the writer uses a `TreeMap`), so `captures` sorts before `kind`.

- [ ] **Step 0: keep the jar built BEFORE this change, for Task 2's proof**

```bash
mkdir -p /tmp/a1-proof && cp src/sextant/extractor-jvm/sextant-extractor.jar /tmp/a1-proof/before.jar && ls -la /tmp/a1-proof/before.jar
```

(`/tmp/a1-proof` is scratch; nothing under it is ever added to git.)

- [ ] **Step 1: add the receiver shapes and the capture shapes to `CallSample.java`**

Append inside the class, next to `parameterReceiver` (line ~202):

```java
    /** The receiver is a STATIC method's parameter 0 — local slot 0, where the instance
     *  rule would read `this`. The fact must say parameter 0. */
    public static void staticParameterReceiver(Link supplied) {
        supplied.third();
    }

    /** {@code long id} takes slots 0-1 after {@code this}, so {@code supplied} is slot 3
     *  and parameter 1. The fact names the parameter's index, never its slot. */
    public void wideParameterReceiver(long id, Link supplied) {
        supplied.third();
    }

    /** A lambda that captures a LOCAL. javac compiles it to a static synthetic method
     *  whose first parameter is the captured value and whose second is the interface's:
     *  {@code lambda$lambdaCapturingLocal$N(String, String)}. The indy carries one
     *  argument (the capture), the handle is static, so {@code captures} is 1. */
    public static void lambdaCapturingLocal(java.util.List<String> values, String prefix) {
        values.forEach(value -> helper(prefix + value));
    }

    /** A lambda that captures nothing at all: a static synthetic with the interface's
     *  parameter alone. Zero indy arguments, static handle, {@code captures} 0. */
    public static void lambdaCapturingNothing(java.util.List<String> values) {
        values.forEach(value -> helper(value));
    }
```

(`lambdaArgument` — `value -> sink(value)`, which captures `this` — and `methodReferenceArgument` — `this::sink` — and `jdkMethodReferenceArgument` — `String::trim` — already exist and are the other three shapes.)

- [ ] **Step 2: write the failing Java tests**

In `MethodFlowTest.java`, replace `leaves_the_receiver_null_when_it_is_a_method_parameter` (line ~493) with the three below and add the four capture tests after `captures_a_lambda_argument_as_the_symbol_of_the_body_javac_lifted_out` (line ~286):

```java
    /** A receiver that arrives as a parameter still has no producing instruction, so
     *  `receiver` stays null — and the fact now also says WHICH parameter it is, the
     *  same index the argument grammar has carried since capability 9.8. */
    @Test
    void names_the_parameter_a_receiver_was_handed_straight_from() throws Exception {
        List<String> lines = callSites("parameterReceiver");
        assertEquals(1, lines.size());
        assertTrue(lines.get(0).contains("\"receiver\":null"), lines.get(0));
        assertTrue(lines.get(0).contains("\"receiver_parameter\":0"), lines.get(0));
    }

    @Test
    void counts_a_static_methods_parameter_receiver_from_slot_zero() throws Exception {
        String line = callSites("staticParameterReceiver").get(0);
        assertTrue(line.contains("\"receiver_parameter\":0"), line);
    }

    @Test
    void maps_a_receiver_after_a_two_slot_parameter_to_the_right_index() throws Exception {
        String line = callSites("wideParameterReceiver").get(0);
        assertTrue(line.contains("\"receiver_parameter\":1"), line);
    }

    /** A receiver produced by a call carries `receiver` and NO `receiver_parameter`:
     *  the key is written only where there is a parameter to name. */
    @Test
    void writes_no_receiver_parameter_where_the_receiver_is_a_calls_result() throws Exception {
        String line = last(callSites("chained"));
        assertFalse(line.contains("receiver_parameter"), line);
    }

    /** `value -> sink(value)` reads `this` (sink is an instance method), so javac makes
     *  an INSTANCE synthetic method and passes `this` as the indy's one argument: one
     *  captured value, and it became the receiver, not a parameter — `captures` is 0. */
    @Test
    void counts_a_captured_this_as_no_leading_parameter() throws Exception {
        String line = last(callSites("lambdaArgument"));
        assertTrue(line.contains("\"captures\":0,\"kind\":\"lambda\""), line);
    }

    @Test
    void counts_a_captured_local_as_one_leading_parameter() throws Exception {
        String line = last(callSites("lambdaCapturingLocal"));
        assertTrue(line.contains("\"captures\":1,\"kind\":\"lambda\""), line);
    }

    @Test
    void counts_nothing_for_a_lambda_that_captures_nothing() throws Exception {
        String line = last(callSites("lambdaCapturingNothing"));
        assertTrue(line.contains("\"captures\":0,\"kind\":\"lambda\""), line);
    }

    /** `this::sink`: the bound receiver is the indy's one argument and the handle is
     *  `H_INVOKEVIRTUAL`, so it becomes the body's `this` — `captures` 0, and `sink`'s
     *  own parameter is the interface's parameter 0. */
    @Test
    void counts_a_bound_method_references_receiver_as_no_leading_parameter() throws Exception {
        String line = last(callSites("methodReferenceArgument"));
        assertTrue(line.contains("\"captures\":0,\"kind\":\"lambda\""), line);
    }

    /** `String::trim` is UNBOUND: the indy carries no argument and the handle is an
     *  instance kind, so the interface's first parameter becomes the body's receiver.
     *  `captures` is -1 — the interface's parameter k is the body's parameter k-1, and
     *  parameter 0 is no parameter of the body at all. */
    @Test
    void reports_minus_one_for_an_unbound_instance_method_reference() throws Exception {
        String line = last(callSites("jdkMethodReferenceArgument"));
        assertTrue(line.contains("\"captures\":-1,\"kind\":\"lambda\""), line);
    }
```

If no method named `chained` exists in `CallSample`, use whichever existing sample method has a receiver produced by a call (grep `MethodFlowTest.java` for `"receiver":` to find one) — the assertion is only that the key is absent.

Create `extractor-jvm/src/test/kotlin/dev/sextant/extractor/KotlinCaptureSample.kt`:

```kotlin
package dev.sextant.extractor

import java.util.function.Consumer

/** A Kotlin lambda that captures `this` compiles — unlike javac's — to a STATIC
 *  synthetic method whose first parameter is the captured receiver, so the captured
 *  value is a leading parameter and `captures` is 1. `forEach` is inline in the
 *  standard library and would compile to no lambda at all; `Consumer` is a Java
 *  interface, so the conversion goes through the same LambdaMetafactory indy javac
 *  uses. */
class KotlinCaptureSample(private val tag: String) {
    fun note(value: String): String = tag + value

    fun run(values: List<String>) {
        values.stream().forEach(Consumer { note(it) })
    }
}
```

Create `extractor-jvm/src/test/java/dev/sextant/extractor/KotlinCaptureTest.java`, modelled on `KotlinMetadataTest.java`'s `scan(...)` helper (read that file first and copy its scan helper verbatim):

```java
package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class KotlinCaptureTest {

    @Test
    void a_kotlin_lambda_capturing_this_has_one_leading_parameter() throws Exception {
        List<String> lines = KotlinMetadataTest.scan("KotlinCaptureSample");
        String site = lines.stream()
            .filter(line -> line.contains("\"kind\":\"call_site\"") && line.contains("\"name\":\"forEach\""))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no forEach call site in " + lines));
        assertTrue(site.contains("\"captures\":1,\"kind\":\"lambda\""), site);
    }
}
```

(If `KotlinMetadataTest.scan` is private, make it package-private static — it is a test helper, and the one-line visibility change is part of this task.)

- [ ] **Step 3: run the extractor tests to see them fail**

Run: `cd extractor-jvm && ./gradlew --quiet test --tests 'dev.sextant.extractor.MethodFlowTest' --tests 'dev.sextant.extractor.KotlinCaptureTest'`
Expected: the eight new tests FAIL (the keys are not written); the replaced test is gone.

- [ ] **Step 4: implement in `MethodFlow.java`**

(a) The receiver's parameter index, in the call-site loop (line ~113), beside `receiver`:

```java
            Integer receiver = target.hasReceiver()
                ? sourceId(frame.getStack(base - 1), instructions)
                : null;
            // The other half of what `sourceId` cannot say. A receiver that arrives as a
            // parameter has no producing instruction, so `receiver` is null — the same
            // null a field receiver and an unreadable one get. The parameter marker the
            // interpreter mints is right there, and the argument grammar has read it as
            // `{"kind":"parameter"}` since 9.8; this reads it for the receiver slot and
            // names the index, so a walk can tell "the lambda's own parameter" from
            // "something I cannot see". Written only where there is an index to write.
            Integer receiverParameter = target.hasReceiver()
                ? parameterIndex(frame.getStack(base - 1), parameterSlots)
                : null;
            Integer result = Type.getReturnType(target.descriptor()).getSort() == Type.VOID ? null : i;
            lines.add(callSiteJson(documentId, callerSymbol, target, ordinal++, receiver,
                                   receiverParameter, result, implementationOf(insns[i]), arguments));
```

and the helper, placed next to `sourceId`:

```java
    /** The parameter index a value arrives as, or null: the same test `argumentJson`
     *  makes for a `parameter`-kind argument — a `VarInsnNode` producer is the
     *  interpreter's parameter marker and nothing else — applied to the receiver slot.
     *  `this` and the second half of a wide parameter are no numbered parameter and
     *  stay null, exactly as they do for an argument. */
    private static Integer parameterIndex(SourceValue value, int[] parameterSlots) {
        AbstractInsnNode producer = singleSource(value);
        if (!(producer instanceof VarInsnNode parameter)) return null;
        int index = indexOfSlot(parameterSlots, parameter.var);
        return index < 0 ? null : index;
    }
```

`parameterSlots` is already in scope in `callSites` (line 50: `int[] parameterSlots = parameterSlotsOf(...)`).

(b) `callSiteJson` gains the parameter and writes the key only when present, in the same spirit as `implementation`:

```java
    private static String callSiteJson(String documentId, String callerSymbol, Target invoke,
                                       int ordinal, Integer receiver, Integer receiverParameter,
                                       Integer result, String implementation, List<String> arguments) {
        …
        fact.put("receiver", receiver == null ? "null" : String.valueOf(receiver));
        // Absent rather than null on every site whose receiver is not a parameter — the
        // rule `implementation` follows two lines up, for the same reason.
        if (receiverParameter != null) fact.put("receiver_parameter", String.valueOf(receiverParameter));
        fact.put("result", result == null ? "null" : String.valueOf(result));
```

Update every other caller of `callSiteJson` (grep for it — `throwSiteJson` may share a helper; pass `null`).

(c) The lambda branch of `argumentJson` (line ~656). Replace the two lines that compute `implementation` and return with:

```java
            // A lambda's code is not here: the compiler lifted the body into a method
            // of its own and the call site only names it, in the bootstrap's second
            // argument. A method reference bootstraps identically and names the
            // referenced method itself.
            Handle implementation = lambdaHandle(indy);
            if (implementation == null) {
                return argument("unresolved", null, null, String.valueOf(instructions.indexOf(producer)));
            }
            // How many of the body's LEADING parameters are captured values. The
            // metafactory lays the body's parameters out as captured values first, then
            // the interface's, so the interface's parameter k is the body's parameter
            // `captures + k` — a walk into the body needs this number, and it is written
            // here, on the indy, where it is known exactly. The indy's own descriptor
            // lists the captured values; when the handle is an instance kind the first of
            // them becomes the body's receiver rather than a parameter, so it is not
            // counted. An unbound instance reference (no captured value, instance handle)
            // reads -1: the interface's FIRST parameter is the receiver, and parameter k
            // is the body's parameter k-1.
            int captured = Type.getArgumentTypes(indy.desc).length;
            int captures = isInstanceHandle(implementation) ? captured - 1 : captured;
            return lambdaArgument(lambdaSymbol(implementation),
                                  String.valueOf(instructions.indexOf(producer)), captures);
```

with the helpers (replace the existing `lambdaSymbol(InvokeDynamicInsnNode)`):

```java
    private static Handle lambdaHandle(InvokeDynamicInsnNode indy) {
        if (!"java/lang/invoke/LambdaMetafactory".equals(indy.bsm.getOwner())) return null;
        if (indy.bsmArgs.length < 2 || !(indy.bsmArgs[1] instanceof Handle implementation)) return null;
        return implementation;
    }

    private static String lambdaSymbol(Handle implementation) {
        return JsonOut.string(implementation.getOwner() + "#" + implementation.getName()
            + "(" + ClassScanner.disambiguatorOf(implementation.getDesc()) + ").");
    }

    private static boolean isInstanceHandle(Handle handle) {
        return handle.getTag() == Opcodes.H_INVOKEVIRTUAL
            || handle.getTag() == Opcodes.H_INVOKESPECIAL
            || handle.getTag() == Opcodes.H_INVOKEINTERFACE;
    }

    /** The `lambda` kind's own writer: the four keys every argument may carry, plus
     *  `captures`, which only a lambda has. */
    private static String lambdaArgument(String symbol, String source, int captures) {
        TreeMap<String, String> entry = new TreeMap<>();
        entry.put("kind", JsonOut.string("lambda"));
        entry.put("symbol", symbol);
        entry.put("source", source);
        entry.put("captures", String.valueOf(captures));
        return JsonOut.object(entry);
    }
```

Check every other caller of the old `lambdaSymbol(InvokeDynamicInsnNode)` (grep; `implementationOf` near the call-site loop uses it for the `implementation` key) and route it through `lambdaHandle` + `lambdaSymbol(Handle)`.

- [ ] **Step 5: run the extractor build and tests**

Run: `cd extractor-jvm && ./gradlew --quiet build`
Expected: BUILD SUCCESSFUL, every test green including the eight new ones. The shaded jar is copied to `src/sextant/extractor-jvm/sextant-extractor.jar` by the build (verify: `ls -la src/sextant/extractor-jvm/sextant-extractor.jar` shows a new timestamp).

- [ ] **Step 6: run the Python suite against the new jar — nothing may move**

Run: `JAVA_HOME=… bash scripts/check.sh`
Expected: `all gates passed`. Nothing in Python reads the keys yet; the pydantic models accept unknown keys? — **check**: `CallArgument` and `CallSiteFact` are `BaseModel` with `model_config = {"frozen": True}`; pydantic v2 ignores extra keys by default unless `extra="forbid"`. If a round-trip test fails on the new keys, Task 2's model change is needed first — in that case do Task 2 Step 2 (the two fields) before this step and say so in the report.

- [ ] **Step 7: commit**

```bash
git add extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java extractor-jvm/src/test/java/dev/sextant/extractor/CallSample.java extractor-jvm/src/test/java/dev/sextant/extractor/MethodFlowTest.java extractor-jvm/src/test/kotlin/dev/sextant/extractor/KotlinCaptureSample.kt extractor-jvm/src/test/java/dev/sextant/extractor/KotlinCaptureTest.java src/sextant/extractor-jvm/sextant-extractor.jar
git commit -m "feat(extractor): a call site says which parameter its receiver is, and a lambda argument says how many captured values lead its body's parameters (A1 Task 1, spec §10)"
```

(Confirm whether the shaded jar under `src/sextant/extractor-jvm/` is tracked — `git ls-files src/sextant/extractor-jvm/` — and add it only if it is.)

---

### Task 2: the fields reach the fact model and the projection, and the proof that nothing moved

**Files:**
- Modify: `src/sextant/domain/facts.py:338-372` (`CallArgument`), `:412-425` (`CallSiteFact`)
- Modify: `src/sextant/storage/duckdb/schema.sql:847-865` (`call_sites` view)
- Create: `scripts/probes/fact_additivity/run.py`
- Test: `tests/domain/test_facts.py` (or the existing fact round-trip test file — `grep -ln "CallSiteFact(" tests/domain/*.py`), `tests/storage/test_workspace.py`

**Interfaces:**
- Produces: `CallSiteFact.receiver_parameter: int | None = None`; `CallArgument.captures: int | None = None`; `call_sites.receiver_parameter` (nullable INTEGER). `captures` stays inside the decoded `arguments` JSON (`_DECODED_COLUMNS` already decodes `call_sites.arguments`), so an engine reads `argument.get("captures")`.

- [ ] **Step 1: write the failing round-trip and projection tests**

In the fact model test file:

```python
def test_a_call_site_round_trips_its_receiver_parameter_and_a_lambdas_captures(tmp_path: Path):
    """The two keys Part II reads (spec §10): a receiver that is the method's parameter
    N, and the number of captured values that lead a lambda body's parameters. Both
    optional, both absent by default — a fact written before them reads exactly as it
    did."""
    site = CallSiteFact(
        document_id="doc_1",
        caller="com/example/Routes#lambda$routes$0(sig_1).",
        target=CallTarget(owner="com/example/Spec#", name="path", descriptor="(Ljava/lang/String;)Lcom/example/Spec;"),
        invoke_kind="virtual",
        ordinal=0,
        receiver=None,
        receiver_parameter=1,
        result=0,
        arguments=[CallArgument(kind="lambda", symbol="com/example/Routes#lambda$routes$0(sig_1).", source=3, captures=1)],
    )
    line = json.loads(_line(site))
    assert line["receiver_parameter"] == 1
    assert line["arguments"][0]["captures"] == 1
    assert CallSiteFact.model_validate_json(_line(site)) == site
    plain = CallSiteFact(
        document_id="doc_1",
        caller="c",
        target=CallTarget(owner="o", name="n", descriptor="()V"),
        invoke_kind="static",
        ordinal=0,
    )
    assert plain.receiver_parameter is None
    assert "receiver_parameter" not in json.loads(_line(plain)) or json.loads(_line(plain))["receiver_parameter"] is None
```

(`_line` is `sextant.domain.factfile._line`; import it. If the file's existing round-trip tests use a different helper, use that one.)

In `tests/storage/test_workspace.py`:

```python
def test_call_sites_projects_the_receiver_parameter_and_keeps_captures_inside_arguments(tmp_path: Path):
    site = CallSiteFact(
        document_id="doc_1",
        caller="com/example/Routes#lambda$routes$0(sig_1).",
        target=CallTarget(owner="com/example/Spec#", name="path", descriptor="(Ljava/lang/String;)Lcom/example/Spec;"),
        invoke_kind="virtual",
        ordinal=0,
        receiver_parameter=0,
        arguments=[CallArgument(kind="lambda", symbol="s", source=1, captures=2)],
    )
    write_fact_file(tmp_path / "facts" / "a.jsonl", _document(), [site])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    (row,) = workspace.query("call_sites")
    assert row["receiver_parameter"] == 0
    assert row["arguments"][0]["captures"] == 2
```

(Reuse the file's own `_document()` helper; every workspace test file has one.)

- [ ] **Step 2: run them to see them fail**

Run: `.venv/bin/pytest tests/domain tests/storage -q -k "receiver_parameter" -p no:cacheprovider`
Expected: FAIL — `CallSiteFact` has no field `receiver_parameter` / `CallArgument` has no field `captures`.

- [ ] **Step 3: the two fields**

`facts.py`, in `CallArgument` after `elements`:

```python
    # How many of a lambda body's LEADING parameters are captured values (spec §10b):
    # the indy's argument count, minus one when the implementation handle is an
    # instance kind, because that first captured value becomes the body's receiver.
    # The metafactory lays the body's parameters out as captured values first, then
    # the interface's, so the interface's parameter k is the body's parameter
    # `captures + k`. `-1` means the interface's first parameter IS the receiver (an
    # unbound instance reference). Only a `lambda`-kind argument carries it.
    captures: int | None = None
```

In `CallSiteFact` after `receiver`:

```python
    # Which of the enclosing method's parameters the receiver is, when it is one (D00 §5
    # numbering: `this` is not a parameter). `receiver` is the producing call's id and is
    # null for a parameter, a field and an unreadable receiver alike; this is the half of
    # that answer the argument grammar has carried as `{"kind": "parameter"}` since 9.8,
    # for the receiver slot. Absent everywhere else.
    receiver_parameter: int | None = None
```

`schema.sql`, in the `call_sites` view after `receiver`:

```sql
       -- Spec §10a: the receiver as the enclosing method's parameter N, where it is one.
       -- `->>` on an absent key is SQL NULL, which is today's meaning for every site
       -- that carries no such parameter.
       (payload ->> 'receiver_parameter')::INTEGER AS receiver_parameter,
```

`captures` needs no column: `arguments` is projected whole and decoded by `_DECODED_COLUMNS`.

- [ ] **Step 4: run the two tests, then the whole suite**

Run: `.venv/bin/pytest tests/domain tests/storage -q -p no:cacheprovider` then `JAVA_HOME=… bash scripts/check.sh`
Expected: green. If `tests/architecture/test_known_types_mirror_the_projection.py` fails, it is the ratchet that keeps a known-types list in step with `schema.sql`'s columns — add `receiver_parameter` where it lists `call_sites` columns and say so in the report.

- [ ] **Step 5: the double-scan proof script**

Create `scripts/probes/fact_additivity/run.py`:

```python
"""Spec §11 steps 1 and 2: the two new call-site keys are the ONLY difference.

Scans every fixture root with two extractor jars — the one built before the change and
the one built after — into two trees, strips `receiver_parameter` from every call-site
payload and `captures` from every argument in the second, and requires the two trees to
be byte-identical. Then analyses each named corpus copy with the current build and diffs
every workspace table against a baseline workspace produced by the `before` jar.

    .venv/bin/python scripts/probes/fact_additivity/run.py /tmp/a1-proof/before.jar

Read-only on the repository; writes only under /tmp/a1-proof. Exit 1 on any difference.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AFTER_JAR = REPO / "src" / "sextant" / "extractor-jvm" / "sextant-extractor.jar"
FIXTURES = sorted(p for p in (REPO / "fixtures").iterdir() if (p / "target" / "classes").is_dir())
OUT = Path("/tmp/a1-proof")
STRIPPED = ("receiver_parameter",)
ARGUMENT_STRIPPED = ("captures",)


def scan(jar: Path, classes: Path, out: Path) -> None:
    sys.path.insert(0, str(REPO / "src"))
    from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION

    subprocess.run(
        ["java", "-jar", str(jar), "--module-id", "proof", "--coordinates", "proof/" + classes.parents[1].name,
         "--version", "0", "--classes", str(classes), "--out", str(out),
         "--fact-schema-version", str(FACT_SCHEMA_VERSION), "--sextant-version", SEXTANT_VERSION],
        check=True, capture_output=True, text=True,
    )


def stripped(line: str) -> str:
    fact = json.loads(line)
    if fact.get("kind") != "call_site":
        return line
    for key in STRIPPED:
        fact.pop(key, None)
    for argument in fact.get("arguments", []):
        for key in ARGUMENT_STRIPPED:
            argument.pop(key, None)
    return json.dumps(fact, sort_keys=True, separators=(",", ":"))


def compare_trees(before: Path, after: Path) -> list[str]:
    problems: list[str] = []
    before_files = sorted(p.relative_to(before) for p in before.rglob("*.jsonl"))
    after_files = sorted(p.relative_to(after) for p in after.rglob("*.jsonl"))
    if before_files != after_files:
        problems.append(f"file sets differ: {set(before_files) ^ set(after_files)}")
    for relative in before_files:
        old = (before / relative).read_text(encoding="utf-8").splitlines()
        new = [stripped(l) for l in (after / relative).read_text(encoding="utf-8").splitlines()]
        old = [stripped(l) for l in old]  # normalises key order the same way on both sides
        if old != new:
            problems.append(f"{relative}: differs after stripping the two keys")
    return problems


def main(before_jar: Path) -> int:
    problems: list[str] = []
    for root in FIXTURES:
        before = OUT / "before" / root.name
        after = OUT / "after" / root.name
        for tree in (before, after):
            shutil.rmtree(tree, ignore_errors=True)
            tree.mkdir(parents=True)
        scan(before_jar, root / "target" / "classes", before)
        scan(AFTER_JAR, root / "target" / "classes", after)
        found = compare_trees(before, after)
        print(f"{root.name}: {'identical after stripping' if not found else 'DIFFERS'}")
        problems.extend(f"{root.name}: {p}" for p in found)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
```

The `stripped` normalisation is applied to both sides so a byte comparison is not defeated by key order — the extractor writes sorted keys already, so the `before` tree round-trips unchanged; assert that too if you want a stronger claim (`json.dumps(json.loads(line)) == line` on the before tree).

- [ ] **Step 6: run the proof on the fixtures**

Run: `JAVA_HOME=… .venv/bin/python scripts/probes/fact_additivity/run.py /tmp/a1-proof/before.jar`
Expected: every fixture root prints `identical after stripping`, exit 0. Every fixture's `target/classes` must exist first: `tests/fixture_build.py`'s `main()` compiles them (`.venv/bin/python tests/fixture_build.py`, which is what CI runs) or the suite already did in Step 4.

- [ ] **Step 7: the corpus table diff**

Copy `examples/mall/mall-admin` (with `mall-common`, `mall-mbg`, `mall-security` beside it) and `examples/spring-petclinic-rest` (or the repo's `orders-service` fixture) to `/tmp/a1-proof/corpora/`; analyse each with the current build into its `.sextant`; then temporarily point the scanner at `before.jar` — `SEXTANT_EXTRACTOR_JAR` if `sextant.resources.extractor_jar` honours an override (read `src/sextant/resources.py:50-62`; if it does not, copy the corpus twice and swap the jar file under `src/sextant/extractor-jvm/` between the two analyses, restoring it after) — analyse again into a second copy, and run `.superpowers/perf/table_diff.py <before.duckdb> <after.duckdb>` (usage at the top of that file). Expected: `VERDICT: identical` for every table except the fact tables, where the only differences are the two keys — confirm by re-running the diff with the `stripped` transform applied to the `payload` column (add a `--strip-keys receiver_parameter,captures` option to `table_diff.py` if it has none; it is a scratch tool under `.superpowers/`, not shipped code). Record the exact commands and the output in the task report.

- [ ] **Step 8: full gate, commit**

Run: `JAVA_HOME=… bash scripts/check.sh` → `all gates passed`.

```bash
git add src/sextant/domain/facts.py src/sextant/storage/duckdb/schema.sql scripts/probes/fact_additivity/run.py tests/domain tests/storage
git commit -m "feat(facts): a call site carries its receiver's parameter index and a lambda argument its capture count — proven additive by a double scan of every fixture and a table diff of both corpora (A1 Task 2, spec §10–§11)"
```

---

### Task 3: `verbs`/`prefixes` become scanned lists — `arity`, `arg_types`, the unrecognised-overload row, ambiguity refused at load

**Files:**
- Modify: `src/sextant/domain/symbols.py` (after `parameter_types`, line ~240)
- Modify: `src/sextant/application/resolve/engines/combinator.py` (`_TreeContext` line ~186, `_context_of` ~225, `_by_owner_method` ~309, `_claimed` ~346, `_routes_of` ~433, `_constraints_of` ~475, `_validate_matches` ~959)
- Modify: `scripts/guard_check.py` (new entry in `GUARDS`)
- Test: `tests/domain/test_symbols.py`, `tests/application/test_combinator_engine.py`

**Interfaces:**
- Consumes: `call_sites.descriptor` (already projected — `schema.sql`, `payload -> 'target' ->> 'descriptor'`).
- Produces: `descriptor_parameter_types(descriptor: str) -> tuple[str, ...]` in `domain/symbols.py`; catalog keys `arity: int` and `arg_types: {<position>: <dotted type>}` on any `verbs`/`prefixes` rule; `_TreeContext.verbs`/`.prefixes` as `tuple[dict, ...]`, plus `verb_names`/`prefix_names: frozenset[tuple[str, str]]`; `_matching_rule(site, rules) -> dict | None`. Task 4 and Task 5 write rules with these keys.

**What the spec says (§2, §3):** one rule per name is the wall; `arity` first, `arg_types` to split same-arity overloads; a rule applies when owner, name and arity match and every typed position carries that type in the call's own erased descriptor; two rules that could both accept one call are refused at load, naming both; a site the vocabulary names but no rule accepts derives one unresolved row (the G-13 guard).

**Design decision recorded here (spec §3c allows it):** ambiguity is refused at LOAD by a rule stronger than "most specific wins": two rules sharing owner, method and arity must disagree on the type of at least one position both of them type. That guarantees at most one rule ever matches a call — a call has one type per position — so no tie-break is needed at match time and no order-dependence can creep in.

- [ ] **Step 1: the descriptor splitter, test first**

`tests/domain/test_symbols.py`:

```python
def test_descriptor_parameter_types_splits_a_descriptor_into_dotted_names():
    assert descriptor_parameter_types("()V") == ()
    assert descriptor_parameter_types("(Ljava/lang/String;)V") == ("java.lang.String",)
    assert descriptor_parameter_types(
        "(Ljava/lang/String;ILorg/springframework/web/servlet/function/RequestPredicate;J)V"
    ) == ("java.lang.String", "int", "org.springframework.web.servlet.function.RequestPredicate", "long")
    assert descriptor_parameter_types("([Ljava/lang/String;[[IZ)Ljava/lang/Object;") == (
        "java.lang.String[]", "int[][]", "boolean"
    )
    assert descriptor_parameter_types("(Lkotlin/jvm/functions/Function1;)V") == ("kotlin.jvm.functions.Function1",)
```

Run: `.venv/bin/pytest tests/domain/test_symbols.py -q -k descriptor_parameter_types -p no:cacheprovider` → FAIL (ImportError).

Implement in `domain/symbols.py` after `parameter_types`:

```python
_PRIMITIVES = {
    "B": "byte", "C": "char", "D": "double", "F": "float",
    "I": "int", "J": "long", "S": "short", "Z": "boolean",
}


def descriptor_parameter_types(descriptor: str) -> tuple[str, ...]:
    """A JVM method descriptor's parameter types, one dotted name each — the form a
    catalog spells a type in (`java.lang.String`, `int`, `java.lang.String[]`), so a
    rule's `arg_types` compares to a call's own erased descriptor without either side
    learning the other's spelling.

    Reads the parameter list `parameter_types` isolates, one type at a time: a
    primitive letter, `L…;` for a class, and any number of `[` before either for an
    array. The return type is not read — it is not part of method identity (JLS 8.4.2).
    """
    inside = parameter_types(descriptor)[1:-1]
    types: list[str] = []
    position = 0
    while position < len(inside):
        dimensions = 0
        while inside[position] == "[":
            dimensions += 1
            position += 1
        if inside[position] == "L":
            end = inside.index(";", position)
            name = inside[position + 1 : end].replace("/", ".")
            position = end + 1
        else:
            name = _PRIMITIVES[inside[position]]
            position += 1
        types.append(name + "[]" * dimensions)
    return tuple(types)
```

Run the test → PASS.

- [ ] **Step 2: the engine tests, first and failing**

Add a `descriptor` keyword to `_site` in `tests/application/test_combinator_engine.py`:

```python
def _site(
    caller: str,
    ordinal: int,
    owner: str,
    name: str,
    *,
    arguments: list[CallArgument] | None = None,
    receiver: int | None = None,
    result: int | None = None,
    invoke_kind: str = "static",
    descriptor: str = "(...)V",
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        ...
```

Then, after the existing body-linked tests (line ~1840), add. `DSL`, `DSL_FACADE`, `INLINE_BODY`, `LIST_ORDERS` and `_body_linked_facts` are the file's own constants — read `_body_linked_facts` (line 1682) first and mirror its facts (the entry call in the declaring method, the body's sites keyed on the bare body symbol).

```python
# --- overload discrimination (spec §3) ---------------------------------------

_HANDLER_TYPE = "kotlin.jvm.functions.Function1"
_PREDICATE_TYPE = "com.example.web.Predicate"
_STRING = "java.lang.String"
_DSL_GET_FIVE = [
    # The five overloads the servlet DSL declares (`javap -p -s RouterFunctionDsl`),
    # each pinned to what its positions carry. `arity` splits 1/2/3; `arg_types` splits
    # the two arity-2 forms on position 0.
    {"owner": "com.example.web.RouterDsl", "method": "GET", "verb": "GET",
     "arity": 1, "handler_arg": 0},
    {"owner": "com.example.web.RouterDsl", "method": "GET", "verb": "GET",
     "arity": 2, "arg_types": {0: _STRING}, "path_arg": 0, "handler_arg": 1},
    {"owner": "com.example.web.RouterDsl", "method": "GET", "verb": "GET",
     "arity": 2, "arg_types": {0: _PREDICATE_TYPE}, "predicate_arg": 0, "handler_arg": 1},
    {"owner": "com.example.web.RouterDsl", "method": "GET", "verb": "GET",
     "arity": 3, "path_arg": 0, "predicate_arg": 1, "handler_arg": 2},
]


def _overload_matches() -> dict[str, object]:
    matches = _matches()
    vocabulary = dict(matches["vocabulary"])  # type: ignore[arg-type]
    vocabulary["verbs"] = [
        rule for rule in vocabulary["verbs"] if rule["owner"] != "com.example.web.RouterDsl"  # type: ignore[index]
    ] + _DSL_GET_FIVE
    vocabulary["prefixes"] = list(vocabulary["prefixes"]) + [  # type: ignore[arg-type]
        {"owner": "com.example.web.RouterDsl", "method": "path", "path_arg": 0},
    ]
    return {**matches, "vocabulary": vocabulary}


def _four_get_overloads_in_one_body() -> list:
    """`router { GET(h); GET("/two", h); GET(path("/three"), h); GET("/four", path("/p"), h) }`
    as the facts arrive: the entry in the declaring method, four verb calls in the body,
    each `path(...)` a call of its own whose result the verb consumes through `source`."""
    entry = _site(
        DECLARER + "routes(sig_r).", 0, DSL_FACADE, "router",
        arguments=[CallArgument(kind="lambda", symbol=INLINE_BODY, source=0)], result=1,
    )
    body = [
        _site(INLINE_BODY, 0, DSL, "GET", invoke_kind="virtual",
              descriptor=f"(L{_HANDLER_TYPE.replace('.', '/')};)V",
              arguments=[CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0)]),
        _site(INLINE_BODY, 1, DSL, "GET", invoke_kind="virtual",
              descriptor=f"(Ljava/lang/String;L{_HANDLER_TYPE.replace('.', '/')};)V",
              arguments=[CallArgument(kind="string", value="/two"),
                         CallArgument(kind="lambda", symbol=LIST_ORDERS, source=1)]),
        _site(INLINE_BODY, 2, DSL, "path", invoke_kind="virtual", result=2,
              descriptor="(Ljava/lang/String;)Lcom/example/web/Predicate;",
              arguments=[CallArgument(kind="string", value="/three")]),
        _site(INLINE_BODY, 3, DSL, "GET", invoke_kind="virtual",
              descriptor=f"(Lcom/example/web/Predicate;L{_HANDLER_TYPE.replace('.', '/')};)V",
              arguments=[CallArgument(kind="unresolved", source=2),
                         CallArgument(kind="lambda", symbol=LIST_ORDERS, source=3)]),
        _site(INLINE_BODY, 4, DSL, "path", invoke_kind="virtual", result=4,
              descriptor="(Ljava/lang/String;)Lcom/example/web/Predicate;",
              arguments=[CallArgument(kind="string", value="/p")]),
        _site(INLINE_BODY, 5, DSL, "GET", invoke_kind="virtual",
              descriptor=f"(Ljava/lang/String;Lcom/example/web/Predicate;L{_HANDLER_TYPE.replace('.', '/')};)V",
              arguments=[CallArgument(kind="string", value="/four"),
                         CallArgument(kind="unresolved", source=4),
                         CallArgument(kind="lambda", symbol=LIST_ORDERS, source=5)]),
    ]
    return [*_handler_symbols(), _method_symbol(INLINE_BODY), entry, *body]


def test_the_four_verb_overloads_each_derive_what_their_positions_carry(tmp_path: Path):
    """Spec §8 test 1, and it failed against the shipped one-rule-per-name grammar in
    exactly the three ways §1b's measured table records: the catch-all read
    `unresolved`, the three-argument form lost its handler, the predicate form lost its
    predicate. `arity` + `arg_types` make each overload its own rule."""
    workspace = _resolve(tmp_path, _four_get_overloads_in_one_body(), _catalog(_overload_matches()))
    handler = _MODULE + LIST_ORDERS
    assert _identities(_rows(workspace)) == [
        ("GET", None, handler, "resolved"),          # GET(h): a catch-all, deliberately open
        ("GET", "/four/p", handler, "resolved"),     # GET("/four", path("/p"), h)
        ("GET", "/three", handler, "resolved"),      # GET(path("/three"), h)
        ("GET", "/two", handler, "resolved"),        # GET("/two", h)
    ]


def test_a_named_call_no_overload_accepts_derives_one_unresolved_row(tmp_path: Path):
    """Spec §3's G-13 guard: a site whose owner and name the vocabulary knows, at an
    arity no rule declares, is one honest unresolved row — never silence, never a
    position read off the wrong overload."""
    facts = _four_get_overloads_in_one_body()
    facts.append(
        _site(INLINE_BODY, 6, DSL, "GET", invoke_kind="virtual",
              descriptor="(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V",
              arguments=[CallArgument(kind="string", value="/a")] * 4)
    )
    workspace = _resolve(tmp_path, facts, _catalog(_overload_matches()))
    unresolved = [row for row in _rows(workspace) if row["resolution"] == "unresolved"]
    assert [(row["method"], row["path"]) for row in unresolved] == [(None, None)]


def test_two_rules_that_could_accept_one_call_are_refused_at_load(tmp_path: Path):
    """Spec §3c: never file order. Two arity-2 rules typing DIFFERENT positions could
    both accept `GET(String, Predicate)`, so the catalog is refused naming both; two
    rules typing the SAME position with different types cannot both match, so that
    pair loads."""
    matches = _overload_matches()
    vocabulary = matches["vocabulary"]
    vocabulary["verbs"] = [r for r in vocabulary["verbs"] if r.get("arity") != 2] + [  # type: ignore[index]
        {"owner": "com.example.web.RouterDsl", "method": "GET", "verb": "GET",
         "arity": 2, "arg_types": {0: _STRING}, "path_arg": 0, "handler_arg": 1},
        {"owner": "com.example.web.RouterDsl", "method": "GET", "verb": "GET",
         "arity": 2, "arg_types": {1: _HANDLER_TYPE}, "predicate_arg": 0, "handler_arg": 1},
    ]
    with pytest.raises(CatalogError, match=r"GET.*arity 2.*both") as refused:
        _resolve(tmp_path, _four_get_overloads_in_one_body(), _catalog(matches))
    assert _STRING in str(refused.value) and _HANDLER_TYPE in str(refused.value)


def test_a_rule_typing_a_position_beyond_its_arity_is_refused(tmp_path: Path):
    matches = _overload_matches()
    matches["vocabulary"]["verbs"].append(  # type: ignore[index]
        {"owner": "com.example.web.RouterDsl", "method": "HEAD", "verb": "HEAD",
         "arity": 1, "arg_types": {1: _STRING}, "handler_arg": 0}
    )
    with pytest.raises(CatalogError, match=r"HEAD.*position 1.*arity 1"):
        _resolve(tmp_path, _four_get_overloads_in_one_body(), _catalog(matches))
```

`predicate_arg` is a new rule key this task introduces: the position whose producing call's constraints are folded into the verb's route (the `GET(predicate, h)` and `GET(path, predicate, h)` forms). `path_arg` stays the literal-path position. A rule may carry either, both, or neither (the catch-all).

Run: `.venv/bin/pytest tests/application/test_combinator_engine.py -q -k "overload or named_call or refused_at_load or beyond_its_arity" -p no:cacheprovider`
Expected: all four FAIL (the first with wrong identities — the shipped grammar's three defects; the others with no `CatalogError`).

- [ ] **Step 3: the engine change**

In `combinator.py`:

(a) `_TreeContext` fields:

```python
    verbs: tuple[dict[str, Any], ...]
    prefixes: tuple[dict[str, Any], ...]
    # Every (owner, name) any verb or prefix rule names — what makes a call CLAIMED
    # even when no overload rule accepts it (spec §3's G-13 guard).
    verb_names: frozenset[tuple[str, str]]
    prefix_names: frozenset[tuple[str, str]]
```

(b) `_context_of` — replace the two `_by_owner_method(...)` calls:

```python
    verbs = _rules_of(vocabulary.get("verbs", []))
    prefixes = _rules_of(vocabulary.get("prefixes", []))
    ...
        verbs=verbs,
        prefixes=prefixes,
        verb_names=frozenset((rule["owner"], rule["method"]) for rule in verbs),
        prefix_names=frozenset((rule["owner"], rule["method"]) for rule in prefixes),
```

and replace `_by_owner_method` with:

```python
def _rules_of(rules: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """A list, not a dict keyed on (owner, name) — the shape `single_call` moved to
    for the same reason (its `methods` block, Task 6): a dict lets a second rule for
    the same name silently overwrite the first, and a builder declares four `GET`s."""
    return tuple({**rule, "owner": _catalog_symbol(rule["owner"])} for rule in rules)


def _matching_rule(site: dict[str, Any], rules: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    """The one rule that accepts this call: owner and name equal, `arity` equal where
    the rule declares one, and every position in `arg_types` carrying that type in
    the call's own erased descriptor. Positions a rule does not type are unconstrained.
    At most one rule can accept a call — `_validate_overloads` refused any catalog
    where two could — so the first found is the only one."""
    owner, name = str(site["owner"]), str(site["name"])
    arguments = site["arguments"]
    types: tuple[str, ...] | None = None
    for rule in rules:
        if rule["owner"] != owner or rule["method"] != name:
            continue
        if rule.get("arity") not in (None, len(arguments)):
            continue
        wanted: dict[int, str] = rule.get("arg_types") or {}
        if wanted:
            if types is None:
                types = descriptor_parameter_types(str(site["descriptor"]))
            if any(position >= len(types) or types[position] != typed for position, typed in wanted.items()):
                continue
        return rule
    return None
```

(import `descriptor_parameter_types` from `sextant.domain.symbols`).

(c) `_claimed`: replace `key in context.verbs or key in context.prefixes` with `key in context.verb_names or key in context.prefix_names`.

(d) `_routes_of` — the prefix and verb branches become:

```python
    key = (str(site["owner"]), str(site["name"]))
    if key in context.prefix_names:
        prefix = _matching_rule(site, context.prefixes)
        if prefix is None:
            return [_Route(poisons=_IDENTITY_POISON)]
        return _nested_routes(site, prefix, scope)
    if key in context.verb_names:
        verb = _matching_rule(site, context.verbs)
        if verb is None:
            # Spec §3, the G-13 guard: the vocabulary names this call and no overload
            # rule accepts it. One row that says so, never silence — silence is the
            # one outcome this engine's doctrine forbids, and reading positions off a
            # sibling overload is the wrong row it forbids next.
            return [_Route(poisons=_IDENTITY_POISON)]
        # The declaring forms carry a handler position; a bare predicate factory
        # becomes a route only once some entry attaches a handler to it.
        return _verb_routes(site, verb, scope) if "handler_arg" in verb else []
```

`_constraints_of` likewise: `if key in context.verb_names: verb = _matching_rule(...); return _verb_constraints(...) if verb else [_Route(poisons=_IDENTITY_POISON)]`, and the same for prefixes.

(e) `_verb_constraints` reads the new `predicate_arg` and a path-less verb:

```python
def _verb_constraints(site: dict[str, Any], rule: dict[str, Any], scope: _Scope) -> list[_Route]:
    """The verb, merged with whatever its declared positions contribute: a literal path
    at `path_arg`, a predicate's own constraints at `predicate_arg`, both, or neither —
    a verb naming no position at all is a catch-all, and it is RESOLVED: nothing was
    poisoned, the author wrote the route open (spec §7 case 3)."""
    branches = [_Route(verb=str(rule["verb"]))]
    arguments = site["arguments"]
    if "path_arg" in rule:
        paths = _argument_constraints(_arg_at(arguments, rule["path_arg"]), scope, (_PATH,))
        branches = [_merged(branch, path) for branch in branches for path in paths]
    if "predicate_arg" in rule:
        predicates = _argument_constraints(_arg_at(arguments, rule["predicate_arg"]), scope, (_PATH,))
        branches = [_merged(branch, predicate) for branch in branches for predicate in predicates]
    return branches
```

Check `_merged` concatenates `path_parts` in argument order (`left` first) so `GET("/four", path("/p"), h)` reads `/four/p`; if it does not, order the merge so the literal path comes first.

(f) Load validation, called from `_validate_matches`:

```python
def _validate_overloads(catalog: Catalog) -> None:
    """Spec §3c: never file order. Two rules that could both accept one call are
    refused here, naming both. Two rules sharing owner, method and arity are
    distinguishable only if some position BOTH of them type carries a different type
    in each — a call has one type per position, so then at most one can match. A rule
    with no `arity` accepts every arity and so collides with every other rule of its
    name; `arg_types` without `arity`, or a typed position at or beyond the arity, is a
    rule that cannot mean what it says."""
    vocabulary = catalog.matches.get("vocabulary", {})
    for role in ("verbs", "prefixes"):
        rules = list(vocabulary.get(role, []))
        for rule in rules:
            typed = rule.get("arg_types") or {}
            arity = rule.get("arity")
            if typed and arity is None:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{rule.get('method')}` declares "
                    f"`arg_types` without `arity` (D02 §2's `combinator` style)"
                )
            for position in typed:
                if not isinstance(position, int) or arity is not None and position >= arity:
                    raise CatalogError(
                        f"loading catalog {catalog.source}: `{rule.get('method')}` types "
                        f"position {position} but declares arity {arity} "
                        f"(D02 §2's `combinator` style)"
                    )
        for index, left in enumerate(rules):
            for right in rules[index + 1 :]:
                if (left["owner"], left["method"]) != (right["owner"], right["method"]):
                    continue
                if None not in (left.get("arity"), right.get("arity")) and left["arity"] != right["arity"]:
                    continue
                shared = set(left.get("arg_types") or {}) & set(right.get("arg_types") or {})
                if any(left["arg_types"][p] != right["arg_types"][p] for p in shared):
                    continue
                raise CatalogError(
                    f"loading catalog {catalog.source}: two `{role}` rules for "
                    f"`{left['method']}` at arity {left.get('arity')} could both accept one "
                    f"call — {left.get('arg_types') or {}} and {right.get('arg_types') or {}} "
                    f"type no shared position differently; a rule must type enough "
                    f"positions to be unambiguous (spec §3c)"
                )
```

- [ ] **Step 4: run the four tests, then the whole combinator file, then the suite**

Run: `.venv/bin/pytest tests/application/test_combinator_engine.py -q -p no:cacheprovider` → every test green, the four new ones included. Existing tests still pass because a rule without `arity` matches every arity (the permissive branch), exactly as before.
Run: `JAVA_HOME=… bash scripts/check.sh` → `all gates passed`. The shipped catalogs have no `arity` on any `combinator` rule yet, so no live row moves — confirm by running `tests/e2e/test_rest_inbound_delivered.py` and `tests/application/test_pipeline.py` and reading their pass.

- [ ] **Step 5: the guard**

In `scripts/guard_check.py`, add `_COMBINATOR = "sextant/application/resolve/engines/combinator.py"` beside the other paths and:

```python
    # --- `combinator` -------------------------------------------------------
    "combinator.unrecognised-overload-is-a-row": Guard(
        what="a call the vocabulary names but no overload rule accepts derives one "
        "unresolved row",
        why="the alternative is silence — the G-13 failure this engine's doctrine forbids: "
        "a router whose verb call happens to be an overload the catalog did not declare "
        "has its whole route absent from the export with nothing saying so",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="        if verb is None:\n            # Spec §3, the G-13 guard",
                replace="        if verb is None and False:  # guard disabled by scripts/guard_check.py\n            # Spec §3, the G-13 guard",
            ),
        ),
    ),
```

(The `find` text must occur exactly once — adjust it to the exact lines you wrote in Step 3(d).) Mark `test_a_named_call_no_overload_accepts_derives_one_unresolved_row` with `@pytest.mark.pins("combinator.unrecognised-overload-is-a-row")` — it needs no `declines` marker, since it is an engine test on an invented catalog, unless `tests/architecture/test_guard_pins.py` requires both; read that test and follow it.

Run: `bash scripts/check.sh --guards` → the new guard reports `1 killed, 0 survived`.

- [ ] **Step 6: commit**

```bash
git add src/sextant/domain/symbols.py src/sextant/application/resolve/engines/combinator.py scripts/guard_check.py tests/domain/test_symbols.py tests/application/test_combinator_engine.py
git commit -m "feat(resolve): combinator tells same-name overloads apart by arity and argument types, refuses an ambiguous catalog at load, and derives one unresolved row for an overload it does not know (A1 Task 3, spec §3)"
```

---

### Task 4: the builder chain — `extends_receiver`, `origins`, pass-throughs, static resources; both stacks' catalogs; live fixture

**Files:**
- Modify: `src/sextant/application/resolve/engines/combinator.py` (`_TreeContext`, `_context_of`, `_Continuation`, `_continuations_of`, `_claimed`, `_is_root_candidate`, `_routes_of`, `_chained_routes`, `_verb_routes`, `_validate_matches`)
- Modify: `src/sextant/catalogs/spring-webflux-router.yml`, `src/sextant/catalogs/spring-mvc-router.yml`
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/routes/BuilderRoutes.java`, `fixtures/orders-service/src/main/java/com/acme/orders/mvcroutes/MvcBuilderRoutes.java`
- Modify: `tests/application/test_combinator_engine.py`, `tests/application/test_pipeline.py:141-…`, `tests/e2e/test_vertical_slice.py:89-…`, `tests/e2e/test_rest_inbound_delivered.py`, `scripts/guard_check.py`
- Regenerate: `scripts/probes/w19_catalog_surface.md` via `scripts/probes/w19_catalog_surface/run.sh`

**Interfaces:**
- Consumes: Task 3's `arity`/`arg_types`/`predicate_arg`, `_matching_rule`.
- Produces: rule key `extends_receiver: true` on a verb (or prefix); `matches.origins: [{owner, method}]`; continuation key `pass_through: true`; verb key `handler: none` for a resource rule (spec §6: a served route with no handler method). Task 5 relies on none of these; Part II's plan relies on all of them.

**What the spec says (§4, §4b, §5, §6, §7):** the chain roots at `build()`; a verb must be able to extend its receiver; zero routes from a receiver poisons unless the receiver's producing site is a declared origin; an undeclared mid-chain call poisons the whole chain, so `filter`, `before`, `after`, `onError`, `withAttribute(s)` are declared; `resources`/`resource` derive rows with a NULL handler; `resources(Function)` derives `path` NULL `unresolved`.

- [ ] **Step 1: engine tests, first and failing** — add to `tests/application/test_combinator_engine.py`:

```python
# --- the builder chain (spec §4) ----------------------------------------------

BUILDER = "com/example/web/RouterBuilder#"
BUILDER_TYPE = "com.example.web.RouterBuilder"
_BUILDER_DESC = "Lcom/example/web/RouterBuilder;"


def _builder_matches() -> dict[str, object]:
    matches = _overload_matches()
    vocabulary = matches["vocabulary"]
    vocabulary["verbs"] = list(vocabulary["verbs"]) + [  # type: ignore[arg-type]
        # `builder.GET("/x", h)`: declares a route AND carries the chain on.
        {"owner": BUILDER_TYPE, "method": "GET", "verb": "GET", "arity": 2,
         "arg_types": {0: _STRING}, "path_arg": 0, "handler_arg": 1, "extends_receiver": True},
        {"owner": BUILDER_TYPE, "method": "GET", "verb": "GET", "arity": 1,
         "handler_arg": 0, "extends_receiver": True},
        {"owner": BUILDER_TYPE, "method": "POST", "verb": "POST", "arity": 2,
         "arg_types": {0: _STRING}, "path_arg": 0, "handler_arg": 1, "extends_receiver": True},
        # `builder.resources("/static/**", location)`: served, no handler method (§6).
        {"owner": BUILDER_TYPE, "method": "resources", "verb": "GET", "arity": 2,
         "arg_types": {0: _STRING}, "path_arg": 0, "handler": "none", "extends_receiver": True},
    ]
    return {
        **matches,
        "vocabulary": vocabulary,
        "origins": [{"owner": "com.example.web.Routers", "method": "route"}],
        "continuations": list(matches["continuations"]) + [  # type: ignore[arg-type]
            {"name": "build", "owner": BUILDER_TYPE},
            {"name": "filter", "owner": BUILDER_TYPE, "pass_through": True},
        ],
    }


def _builder_chain(*, with_filter: bool, declared_origin: bool = True) -> list:
    """`Routers.route().GET("/a", h).filter(f).POST("/b", h).build()` — each call's
    receiver is the previous call's result, `route()` produces the first one, `build()`
    is returned and so consumed by nothing."""
    caller = DECLARER + "routes(sig_r)."
    origin = "route" if declared_origin else "routeFrom"
    sites = [
        _site(caller, 0, ROUTERS, origin, result=0, descriptor=f"(){_BUILDER_DESC}"),
        _site(caller, 1, BUILDER, "GET", invoke_kind="virtual", receiver=0, result=1,
              descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
              arguments=[CallArgument(kind="string", value="/a"),
                         CallArgument(kind="lambda", symbol=LIST_ORDERS, source=1)]),
    ]
    last = 1
    if with_filter:
        sites.append(_site(caller, 2, BUILDER, "filter", invoke_kind="virtual", receiver=1, result=2,
                           descriptor=f"(Lcom/example/web/Filter;){_BUILDER_DESC}",
                           arguments=[CallArgument(kind="lambda", symbol=HEALTH, source=2)]))
        last = 2
    sites.append(_site(caller, last + 1, BUILDER, "POST", invoke_kind="virtual", receiver=last, result=last + 1,
                       descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
                       arguments=[CallArgument(kind="string", value="/b"),
                                  CallArgument(kind="lambda", symbol=CREATE_ORDER, source=last + 1)]))
    sites.append(_site(caller, last + 2, BUILDER, "build", invoke_kind="virtual", receiver=last + 1, result=last + 2,
                       descriptor="()Lcom/example/web/Router;"))
    return [*_handler_symbols(), *sites]


def test_a_builder_chain_derives_every_verb_it_carries_rooted_at_build(tmp_path: Path):
    """Spec §4: `build()` is the outermost unconsumed call, so it roots; each verb both
    declares its route and extends its receiver; `route()` is a declared origin, so the
    chain's head contributes zero routes WITHOUT poisoning (§4b)."""
    workspace = _resolve(tmp_path, _builder_chain(with_filter=False), _catalog(_builder_matches()))
    assert _identities(_rows(workspace)) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_a_declared_pass_through_carries_the_chain_and_reads_no_argument(tmp_path: Path):
    """Spec §8 test 5: a `filter(f)` mid-chain neither declares a route nor reads its
    lambda as a handler; the routes on both sides of it survive."""
    workspace = _resolve(tmp_path, _builder_chain(with_filter=True), _catalog(_builder_matches()))
    assert _identities(_rows(workspace)) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_an_undeclared_chain_head_poisons_the_whole_chain(tmp_path: Path):
    """Spec §4b's consequence, pinned in the refusing direction: a chain whose head is
    NOT a declared origin is one unresolved row — the engine cannot tell "the chain
    starts here" from "I could not read the receiver", and does not guess."""
    workspace = _resolve(
        tmp_path, _builder_chain(with_filter=False, declared_origin=False), _catalog(_builder_matches())
    )
    rows = _rows(workspace)
    assert [row["resolution"] for row in rows] == ["unresolved"] * len(rows) and rows


def test_a_static_resource_rule_derives_a_served_route_with_no_handler(tmp_path: Path):
    """Spec §6: `resources("/static/**", location)` is an inbound boundary a client can
    GET; the row carries the pattern, the verb, and a NULL handler — the row shape
    `derived_resource` and `schema_operations` already ship."""
    caller = DECLARER + "routes(sig_r)."
    facts = [
        *_handler_symbols(),
        _site(caller, 0, ROUTERS, "route", result=0, descriptor=f"(){_BUILDER_DESC}"),
        _site(caller, 1, BUILDER, "resources", invoke_kind="virtual", receiver=0, result=1,
              descriptor=f"(Ljava/lang/String;Lcom/example/web/Resource;){_BUILDER_DESC}",
              arguments=[CallArgument(kind="string", value="/static/**"),
                         CallArgument(kind="unresolved")]),
        _site(caller, 2, BUILDER, "build", invoke_kind="virtual", receiver=1, result=2,
              descriptor="()Lcom/example/web/Router;"),
    ]
    workspace = _resolve(tmp_path, facts, _catalog(_builder_matches()))
    assert _identities(_rows(workspace)) == [("GET", "/static/**", None, "resolved")]
```

Run: `.venv/bin/pytest tests/application/test_combinator_engine.py -q -k "builder_chain or pass_through or chain_head or static_resource" -p no:cacheprovider`
Expected: FAIL — `route` at the head poisons today (no `origins`), the chain stops at `POST` (a verb does not extend its receiver), `filter` reads its lambda as a handler.

- [ ] **Step 2: the engine change**

(a) `_Continuation` gains `pass_through: bool`; `_continuations_of` reads `entry.get("pass_through", False)`; `_validate_continuations` accepts the key (add `"pass_through"` to the mapping's allowed keys wherever it enumerates them, and refuse `pass_through` combined with `path_arg`/`subtree_arg`).

(b) `_TreeContext.origins: frozenset[tuple[str, str]]`, built in `_context_of` from `matches.get("origins", [])` as `(_catalog_symbol(o["owner"]), o["method"])`. `_validate_matches` refuses an origin lacking either key.

(c) `_claimed` also returns True when `key in context.origins` (the origin's result is consumed by the chain; it must count as claimed so its own result-consumption bookkeeping is right — and an origin is never a root candidate: it declares nothing).

(d) `_chained_routes`:

```python
def _chained_routes(site: dict[str, Any], scope: _Scope) -> list[_Route]:
    """The routes of the chain a continuation or a receiver-extending verb carries on.
    A receiver naming no routing call this method can see is one honest unresolved row
    rather than a silently shorter route set; a receiver produced by a DECLARED ORIGIN
    contributes nothing and poisons nothing — that is the difference between "the
    chain starts here" and "I could not read the receiver", which nothing could draw
    until a builder made every chain start somewhere (spec §4b)."""
    if site["receiver"] is None:
        return []
    extended = _producing_site(site["receiver"], scope, exclude=site)
    if extended is not None and (str(extended["owner"]), str(extended["name"])) in scope.context.origins:
        return []
    chained = _routes_of(extended, scope) if extended is not None else []
    return chained or [_Route(poisons=_IDENTITY_POISON)]
```

(e) `_verb_routes` extends the receiver when the rule says so:

```python
def _verb_routes(site: dict[str, Any], rule: dict[str, Any], scope: _Scope) -> list[_Route]:
    handler = (
        None
        if rule.get("handler") == "none"
        else _handler_of(site["arguments"], frozenset({rule["handler_arg"]}), scope.context.method_symbols)
    )
    own = [replace(constraint, handler=handler) for constraint in _verb_constraints(site, rule, scope)]
    if rule.get("extends_receiver"):
        # A builder verb declares its own route AND carries the chain onward — the
        # routes to its left are as much its tree as its own (spec §4).
        return [*_chained_routes(site, scope), *own]
    return own
```

and `_routes_of`'s verb branch returns `_verb_routes(...)` when the rule has `handler_arg` **or** `handler: none`. `_validate_matches` refuses a verb declaring both, or neither while declaring `extends_receiver`.

(f) `_routes_of`'s continuation branch:

```python
    continuation = _matching_continuation(site, context)
    if continuation is not None:
        if continuation.pass_through:
            # Declared to carry the chain and read nothing: its arguments are filters,
            # attributes, error handlers — never a route (spec §4b, §5).
            return _chained_routes(site, scope)
        if continuation.subtree_arg is not None:
            return _nest_continuation_routes(site, continuation, scope)
        return _declared_routes(site, context.continuation_handlers, scope, extends_receiver=True)
```

(g) `_is_root_candidate` is unchanged: `build` and `filter` are owner-declaring continuations and root when unconsumed, which is what a returned `build()` — or a `RouterFunction.filter(...)` after a `build()` — needs.

Run the four tests → PASS; run the whole file → PASS.

- [ ] **Step 3: the catalogs, both stacks**

In `spring-webflux-router.yml` (and the same block with `org.springframework.web.servlet.function` owners in `spring-mvc-router.yml`), under `matches`:

```yaml
  # Spec §4–§6 (Group A, PR A1): the builder form. `route()` with no argument returns
  # a `RouterFunctions$Builder`; every verb on it declares a route and returns the
  # builder; `build()` ends the chain. MEASURED: `javap -p` at spring-webflux 6.1.6 and
  # 7.0.2 — 20 method names, 48 overloads, identical on both stacks (spec §1).
  origins:
    - { owner: org.springframework.web.reactive.function.server.RouterFunctions, method: route }
```

and in `vocabulary.verbs`, for EACH of `GET HEAD POST PUT PATCH DELETE OPTIONS` (28 rules per stack):

```yaml
      # `RouterFunctions$Builder.GET` — four overloads (spec §3b): arity splits 1/2/3,
      # `arg_types` splits the two arity-2 forms on position 0.
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: GET
        verb: GET
        arity: 1
        handler_arg: 0
        extends_receiver: true
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: GET
        verb: GET
        arity: 2
        arg_types: { 0: java.lang.String }
        path_arg: 0
        handler_arg: 1
        extends_receiver: true
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: GET
        verb: GET
        arity: 2
        arg_types: { 0: org.springframework.web.reactive.function.server.RequestPredicate }
        predicate_arg: 0
        handler_arg: 1
        extends_receiver: true
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: GET
        verb: GET
        arity: 3
        path_arg: 0
        predicate_arg: 1
        handler_arg: 2
        extends_receiver: true
```

plus the builder's other route-declaring members, verified against `javap -p -s` before writing each (record the exact overload list in the catalog comment):

```yaml
      # `route(RequestPredicate, HandlerFunction)` on the builder — the predicate form.
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: route
        verb: null          # no verb of its own: the predicate supplies one, or none
        arity: 2
        predicate_arg: 0
        handler_arg: 1
        extends_receiver: true
      # Static resources (spec §6): served, handler-less. `resources(String, Resource)`
      # reads the pattern; `resources(Function)` has no readable address and derives
      # `path` NULL `unresolved` — a verb rule with neither position and no handler
      # would read as a resolved catch-all, which is the lie in the wrong direction,
      # so that overload is a rule whose `path_arg` names its unreadable argument.
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: resources
        verb: GET
        arity: 2
        arg_types: { 0: java.lang.String }
        path_arg: 0
        handler: none
        extends_receiver: true
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: resources
        verb: GET
        arity: 1
        path_arg: 0
        handler: none
        extends_receiver: true
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: resource
        verb: GET
        arity: 2
        predicate_arg: 0
        handler: none
        extends_receiver: true
```

`verb: null` needs `_verb_constraints` to start from `_Route()` when the rule's verb is None — add that one line in the engine (`_Route(verb=rule.get("verb"))` already yields None; confirm `_row_of` then writes `method` NULL and `_METHOD` is not poisoned).

`prefixes` gains the builder's nesting forms:

```yaml
      # `nest(RequestPredicate, Consumer<Builder>)` and `path(String, Consumer<Builder>)`:
      # a lambda-bodied subtree (spec §5). `nest`/`path(…, Supplier<RouterFunction>)` are
      # the second overloads at the same arity, split on position 1's type.
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: path
        arity: 2
        arg_types: { 1: java.util.function.Consumer }
        path_arg: 0
        body_arg: 1
        extends_receiver: true
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: path
        arity: 2
        arg_types: { 1: java.util.function.Supplier }
        path_arg: 0
        body_arg: 1
        extends_receiver: true
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: nest
        arity: 2
        arg_types: { 1: java.util.function.Consumer }
        predicate_arg: 0
        body_arg: 1
        extends_receiver: true
      - owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder
        method: nest
        arity: 2
        arg_types: { 1: java.util.function.Supplier }
        predicate_arg: 0
        body_arg: 1
        extends_receiver: true
```

A prefix with `extends_receiver` needs `_nested_routes` to prepend `_chained_routes(site, scope)` when the rule says so, and `predicate_arg` on a prefix folds the predicate's constraints as the prefix (`_argument_constraints` on that position) — the same two lines Step 2 gave verbs. Inside a `Consumer<Builder>` body, the builder is the lambda's parameter and the body's verbs are `builder.GET(...)` calls with `receiver_parameter` set and `receiver` null: their `_chained_routes` returns `[]` (receiver None), so the body's routes fold cleanly under the prefix. Say so in a comment where the body is folded.

`continuations` gains:

```yaml
    - { name: build, owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder }
    - { name: add, owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder }
    # Pass-throughs (spec §4b): declared so a chain through them keeps every route to
    # its left. Each reads NO argument — a filter, an attribute, an error handler is
    # never a route.
    - { name: filter,         owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder, pass_through: true }
    - { name: before,         owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder, pass_through: true }
    - { name: after,          owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder, pass_through: true }
    - { name: onError,        owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder, pass_through: true }
    - { name: withAttribute,  owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder, pass_through: true }
    - { name: withAttributes, owner: org.springframework.web.reactive.function.server.RouterFunctions$Builder, pass_through: true }
```

(`add(RouterFunction)` folds its argument's routes through the existing plain-continuation argument fold — `_declared_routes` with `extends_receiver=True` — which is what spec §5 asks; confirm with a hand-built test if in doubt.)

Then the slice: remove the `RouterFunctions$Builder` entries and the argument-less `RouterFunctions.route` entry from `slice.outside` in both files (they are read now), and move the static `RouterFunctions.resource/resources/resourceLookupFunction` entry per spec §6: `resources(String, Resource)` and `resource(RequestPredicate, Resource)` become verb rules on the `RouterFunctions` owner with `handler: none`; `resourceLookupFunction` stays outside with a corrected `why` (it builds a lookup function, it serves nothing itself). Rewrite the "0 of the 20" header comment (line ~346) to say 20 of 20, citing the regenerated probe.

- [ ] **Step 4: the fixture sources**

`fixtures/orders-service/src/main/java/com/acme/orders/routes/BuilderRoutes.java`:

```java
// The builder form of WebFlux functional routing (G-37, spec §1): the form Spring's own
// reference recommends, and the one that derived NOTHING until the combinator engine
// could root a walk at `build()` and extend a verb's receiver. Every shape spec §8
// names: all four verb overloads, `nest`, `path`, a filter MID-chain, a static
// resource, and `build()`.
package com.acme.orders.routes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class BuilderRoutes {

    @Bean
    public RouterFunction<ServerResponse> builderRoutes(RouteHandlers h) {
        return RouterFunctions.route()
            .GET("/bld/orders", h::listOrders)                                            // GET(String, HandlerFunction)
            .GET("/bld/orders/{id}", RequestPredicates.accept(MediaType.APPLICATION_JSON),
                 h::listOrders)                                                           // GET(String, RequestPredicate, HandlerFunction)
            .GET(RequestPredicates.path("/bld/health"), h::health)                        // GET(RequestPredicate, HandlerFunction)
            .filter((request, next) -> next.handle(request))                              // mid-chain pass-through
            .POST("/bld/orders", h::createOrder)
            .PUT("/bld/orders/{id}", h::createOrder)
            .path("/bld/nested", builder -> builder
                .GET("/inner", h::health)                                                 // GET inside a Consumer<Builder> body
                .DELETE("/inner/{id}", h::health))
            .resources("/bld/static/**", new ClassPathResource("static/"))                // served, handler-less (spec §6)
            .build();
    }

    @Bean
    public RouterFunction<ServerResponse> catchAll(RouteHandlers h) {
        return RouterFunctions.route().GET(h::health).build();                            // GET(HandlerFunction): a catch-all
    }
}
```

`MvcBuilderRoutes.java` in `com.acme.orders.mvcroutes` is the same file with `org.springframework.web.servlet.function` imports, `MvcRouteHandlers h`, and paths under `/mvcbld/…`. Check `RouteHandlers`/`MvcRouteHandlers` for the handler method names that exist (`listOrders`, `createOrder`, `health` / `listInvoices`, `createInvoice`, `archive`) and use those.

Compile: `cd fixtures/orders-service && mvn -q -o compile` — fix any import against the pinned Spring version (`fixtures/orders-service/pom.xml`).

- [ ] **Step 5: the live expectations move with the fixture**

`tests/application/test_pipeline.py::test_resolve_finds_every_fixture_endpoint_exactly_once_when_run_end_to_end` gains, with a comment naming `BuilderRoutes`/`MvcBuilderRoutes` and spec §8:

```python
        ("GET", "/bld/orders"), ("GET", "/bld/orders/{id}"), ("GET", "/bld/health"),
        ("POST", "/bld/orders"), ("PUT", "/bld/orders/{id}"),
        ("GET", "/bld/nested/inner"), ("DELETE", "/bld/nested/inner/{id}"),
        ("GET", "/bld/static/**"),
        (None, ...)  # see below
```

The catch-all `GET(h::health)` is `("GET", None)` — check how the test's set treats a NULL path (other catch-all rows may already exist; if the set comprehension drops `None` paths, add a separate assertion that exactly one `spring-webflux-router` row has `method == "GET"`, `path is None`, `resolution == "resolved"`). Same for the MVC twin under `/mvcbld/…`. `tests/e2e/test_vertical_slice.py::test_the_document_names_every_fixture_endpoint_and_its_gaps` lists the same routes for the rendered document — add them there too. Then in `tests/e2e/test_rest_inbound_delivered.py`: the file's `http_routes` fixture (line 21) yields `(catalog_id, method, path)` for every inbound HTTP row of the session's one `orders-service` analysis. Add a sibling module fixture beside it that yields the whole rows, built the same way (same `analyzed_orders_service` workspace, same `try/finally`):

```python
@pytest.fixture(scope="module")
def http_rows(analyzed_orders_service: Path) -> list[dict]:
    """Every inbound HTTP row of the session's one `orders-service` analysis, whole —
    for the tests that read `resolution` and `handler`, not only the address."""
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return [
            dict(row)
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "http" and str(row["direction"]) == "inbound"
        ]
    finally:
        workspace.close()
```

and the tests:

```python
def test_the_builder_form_derives_every_route_on_both_stacks(http_routes):
    """`G-37`, spec §8: the builder DSL, every overload, both stacks, with the mid-chain
    filter, the nested body, the static resource and the catch-all."""
    flux, mvc = "spring-webflux-router", "spring-mvc-router"
    expected = {
        (flux, "GET", "/bld/orders"), (flux, "GET", "/bld/orders/{id}"),
        (flux, "GET", "/bld/health"), (flux, "POST", "/bld/orders"),
        (flux, "PUT", "/bld/orders/{id}"), (flux, "GET", "/bld/nested/inner"),
        (flux, "DELETE", "/bld/nested/inner/{id}"), (flux, "GET", "/bld/static/**"),
        (mvc, "GET", "/mvcbld/orders"), (mvc, "GET", "/mvcbld/orders/{id}"),
        (mvc, "GET", "/mvcbld/health"), (mvc, "POST", "/mvcbld/orders"),
        (mvc, "PUT", "/mvcbld/orders/{id}"), (mvc, "GET", "/mvcbld/nested/inner"),
        (mvc, "DELETE", "/mvcbld/nested/inner/{id}"), (mvc, "GET", "/mvcbld/static/**"),
    }
    missing = expected - http_routes
    assert missing == set(), f"builder routes missing: {sorted(missing)}"


def test_every_builder_route_is_resolved_including_the_one_past_the_filter(http_rows):
    builder_rows = [row for row in http_rows if str(row["path"]).startswith(("/bld/", "/mvcbld/"))]
    assert builder_rows and {row["resolution"] for row in builder_rows} == {"resolved"}, [
        (row["path"], row["resolution"]) for row in builder_rows
    ]


def test_the_builder_catch_all_is_resolved_with_no_path(http_rows):
    catch_alls = [
        row for row in http_rows
        if row["catalog_id"] in ("spring-webflux-router", "spring-mvc-router")
        and row["method"] == "GET" and row["path"] is None
    ]
    assert {row["resolution"] for row in catch_alls} == {"resolved"} and len(catch_alls) == 2
```

(The second test is spec §8 test 5 live: the routes past the mid-chain `filter` are resolved.)

Also the declining test spec §8 test 6 asks for: in `tests/application/test_endpoints.py` beside the other `declines` tests, a near-miss against the SHIPPED `spring-webflux-router` catalog — a chain whose head is a call named `route` on a different owner (`com.example.NotRouters#route()`), verbs on `RouterFunctions$Builder`, `build()` — asserting one unresolved row and no resolved one:

```python
@pytest.mark.declines("spring-webflux-router")
@pytest.mark.pins("combinator.origin-is-declared")
def test_a_builder_chain_headed_by_an_undeclared_call_derives_one_unresolved_row(tmp_path: Path):
    ...
```

with the guard in `scripts/guard_check.py`:

```python
    "combinator.origin-is-declared": Guard(
        what="a chain head contributes zero routes without poisoning ONLY when its producing "
        "call is a declared origin",
        why="without the check every unreadable receiver — a field, a helper's result, a "
        "parameter — would read as a clean chain start, and a router whose head the walk "
        "cannot see would publish every route to its right as resolved",
        edits=(Edit(path=_COMBINATOR,
                    find='    if extended is not None and (str(extended["owner"]), str(extended["name"])) in scope.context.origins:',
                    replace='    if extended is not None and not _routes_of(extended, scope):  # guard disabled by scripts/guard_check.py'),),
    ),
```

- [ ] **Step 6: probe, gate, commit**

Run: `bash scripts/probes/w19_catalog_surface/run.sh` — `RouterFunctions$Builder` reports **20 of 20** on both stacks in the regenerated `scripts/probes/w19_catalog_surface.md`; every other line unchanged (`git diff --stat scripts/probes/w19_catalog_surface.md` touches only those rows and the totals). If the sweep counts `resourceLookupFunction` as unread, that is correct and stated in the slice.
Run: `bash scripts/check.sh --guards` → both combinator guards `killed`.
Run: `JAVA_HOME=… bash scripts/check.sh` → `all gates passed`.

```bash
git add src/sextant/application/resolve/engines/combinator.py src/sextant/catalogs/spring-webflux-router.yml src/sextant/catalogs/spring-mvc-router.yml fixtures/orders-service/src/main/java/com/acme/orders/routes/BuilderRoutes.java fixtures/orders-service/src/main/java/com/acme/orders/mvcroutes/MvcBuilderRoutes.java tests/application/test_combinator_engine.py tests/application/test_pipeline.py tests/application/test_endpoints.py tests/e2e/test_vertical_slice.py tests/e2e/test_rest_inbound_delivered.py scripts/guard_check.py scripts/probes/w19_catalog_surface.md
git commit -m "feat(resolve): the builder form of functional routing derives every route on both stacks — a verb extends its receiver, a declared origin starts a chain without poisoning it, pass-throughs carry it, static resources serve handler-less (G-37; A1 Task 4, spec §4–§6)"
```

---

### Task 5: the corrected `RouterFunctionDsl` rules on both stacks, and the WebFlux `router { }` fixture

**Files:**
- Modify: `src/sextant/catalogs/spring-mvc-router.yml:101-140` (the seven `RouterFunctionDsl` rules and their comment), `src/sextant/catalogs/spring-webflux-router.yml` (a `RouterFunctionDslKt.router` entry, seven×five `RouterFunctionDsl` rules, a `RouterFunctionDsl.path` prefix, `RouterFunctionDsl` composers `and`/`or`)
- Create: `fixtures/orders-service/src/main/kotlin/com/acme/orders/routes/KotlinWebFluxRoutes.kt`, `fixtures/orders-service/src/main/kotlin/com/acme/orders/mvcroutes/KotlinMvcRoutes.kt`
- Modify: `tests/application/test_pipeline.py`, `tests/e2e/test_vertical_slice.py`, `tests/e2e/test_rest_inbound_delivered.py`

**Interfaces:**
- Consumes: Task 3's `arity`/`arg_types`/`predicate_arg`; Task 4's engine as shipped.
- Produces: `W44-verb-overloads` and `GAP-1b` closed by live rows.

**What the spec says (§1b, §5 "Also in scope"):** the seven shipped rules are replaced by five-per-verb rules on both stacks (the fifth, `GET(String)`, is a predicate factory — a rule with `path_arg: 0` and no handler, the same shape the Java `RequestPredicates.GET` rules have), and `spring-webflux-router.yml` gains the `RouterFunctionDslKt.router` body-linked entry its MVC twin has carried since W44. The two cannot be sequenced apart (§1b).

- [ ] **Step 1: measure the five overloads on BOTH stacks before writing a rule**

```bash
javap -p -s -cp $(find ~/.m2 -name 'spring-webmvc-6*.jar' | head -1) org.springframework.web.servlet.function.RouterFunctionDsl | grep -A1 -E " (GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|path|and|or|nest)\("
javap -p -s -cp $(find ~/.m2 -name 'spring-webflux-6*.jar' | head -1) org.springframework.web.reactive.function.server.RouterFunctionDsl | grep -A1 -E " (GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|path|and|or|nest)\("
```

Record the descriptors in the catalog comment. The rules below assume the servlet shapes spec §1b lists; the reactive `RouterFunctionDsl` (not `CoRouterFunctionDsl`) declares the same five per verb with `Function1<ServerRequest, Mono<ServerResponse>>` — confirm, and if any verb differs, the rule follows `javap`, not this plan.

- [ ] **Step 2: the fixtures, first**

`fixtures/orders-service/src/main/kotlin/com/acme/orders/mvcroutes/KotlinMvcRoutes.kt` — all four declaring `GET` overloads in one router (spec §8 test 1's live instance), plus one nested prefix:

```kotlin
// The servlet-stack Kotlin router DSL, every `GET` overload it declares in one file
// (W44-verb-overloads, spec §1b): the shipped rules read one of five and mis-graded the
// rest. Paths under /ktmvc so the reactive twin's rows cannot be mistaken for these.
package com.acme.orders.mvcroutes

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.MediaType
import org.springframework.web.servlet.function.RequestPredicates
import org.springframework.web.servlet.function.ServerResponse
import org.springframework.web.servlet.function.router

@Configuration
class KotlinMvcRoutes {

    @Bean
    fun ktMvcRoutes(h: MvcRouteHandlers) = router {
        "/ktmvc".nest {
            GET("/invoices", h::listInvoices)                                             // GET(String, handler)
            GET("/invoices/{id}", accept(MediaType.APPLICATION_JSON), h::listInvoices)    // GET(String, RequestPredicate, handler)
            GET(path("/health"), h::listInvoices)                                         // GET(RequestPredicate, handler)
            POST("/invoices", h::createInvoice)
        }
        GET(h::listInvoices)                                                              // GET(handler): a catch-all
    }
}
```

`fixtures/orders-service/src/main/kotlin/com/acme/orders/routes/KotlinWebFluxRoutes.kt` — the reactive, NON-coroutine `router { }` (`GAP-1b`), mirroring `KotlinOrderRoutes.kt`'s `coRouter` shapes under `/ktflux`:

```kotlin
// The reactive Kotlin router DSL WITHOUT coroutines (`GAP-1b`): `router { }` from
// `RouterFunctionDslKt`, the twin of the `coRouter { }` in KotlinOrderRoutes.kt. Derived
// nothing until this file's catalog entry existed; the corrected verb rules land with it
// because this is their first reactive live instance (spec §1b).
package com.acme.orders.routes

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.MediaType
import org.springframework.web.reactive.function.server.ServerResponse
import org.springframework.web.reactive.function.server.router
import reactor.core.publisher.Mono

@Configuration
class KotlinWebFluxRoutes {

    @Bean
    fun ktFluxRoutes() = router {
        "/ktflux".nest {
            GET("/orders") { ServerResponse.ok().build() }                                // GET(String, handler)
            GET("/orders/{id}", accept(MediaType.APPLICATION_JSON)) { ServerResponse.ok().build() }
            POST("/orders") { ServerResponse.ok().build() }
        }
        GET { ServerResponse.ok().build() }                                               // catch-all
    }
}
```

Compile: `cd fixtures/orders-service && mvn -q -o compile`. Confirm with `javap -p target/classes/com/acme/orders/routes/KotlinWebFluxRoutes.class` that the lambdas are `invokedynamic` bodies (static synthetic `ktFluxRoutes$lambda$…` methods), as `KotlinOrderRoutes` shows — the fixture's Kotlin is 2.x. If they compiled to classes, the fixture's Kotlin compiler flags changed and this task stops with `NEEDS_CONTEXT`.

- [ ] **Step 3: the live test, first and failing (spec §8 test 1)**

In `tests/e2e/test_rest_inbound_delivered.py`, using the same fixtures as Task 4's builder test:

```python
def test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks(http_rows):
    """`W44-verb-overloads` and `GAP-1b`, spec §1b's measured table turned into rows: on
    the servlet stack the four declaring `GET` overloads each derive their route, the
    catch-all is RESOLVED with no path, and the three-argument form keeps its handler;
    on the reactive stack the non-coroutine `router { }` derives at all."""
    rows = {
        (row["catalog_id"], row["method"], row["path"], row["resolution"], row["handler"] is not None)
        for row in http_rows
        if row["path"] is None or str(row["path"]).startswith(("/ktmvc", "/ktflux"))
    }
    assert {
        ("spring-mvc-router", "GET", "/ktmvc/invoices", "resolved", True),
        ("spring-mvc-router", "GET", "/ktmvc/invoices/{id}", "resolved", True),
        ("spring-mvc-router", "GET", "/ktmvc/health", "resolved", True),
        ("spring-mvc-router", "POST", "/ktmvc/invoices", "resolved", True),
        ("spring-mvc-router", "GET", None, "resolved", True),
        ("spring-webflux-router", "GET", "/ktflux/orders", "resolved", True),
        ("spring-webflux-router", "GET", "/ktflux/orders/{id}", "resolved", True),
        ("spring-webflux-router", "POST", "/ktflux/orders", "resolved", True),
        ("spring-webflux-router", "GET", None, "resolved", True),
    } <= rows, sorted(rows)
```

Run it: `.venv/bin/pytest tests/e2e/test_rest_inbound_delivered.py -q -k kotlin_dsl_verb -p no:cacheprovider`
Expected: FAIL — the `/ktmvc` catch-all reads `unresolved`, `/ktmvc/invoices/{id}` has no handler, `/ktmvc/health` is absent, and nothing under `/ktflux` exists (no `router` entry). Record the actual failure in the task report: it is the measured defect.

- [ ] **Step 4: the rules**

`spring-mvc-router.yml`: replace the seven `RouterFunctionDsl` rules (and rewrite their comment: the measured five overloads, the corrected reading, and the live instance this task adds) with, per verb:

```yaml
      - owner: org.springframework.web.servlet.function.RouterFunctionDsl
        method: GET
        verb: GET
        arity: 1
        arg_types: { 0: kotlin.jvm.functions.Function1 }
        handler_arg: 0
      - owner: org.springframework.web.servlet.function.RouterFunctionDsl
        method: GET
        verb: GET
        arity: 1
        arg_types: { 0: java.lang.String }
        path_arg: 0                              # the predicate FACTORY: no handler, a route once an entry attaches one
      - owner: org.springframework.web.servlet.function.RouterFunctionDsl
        method: GET
        verb: GET
        arity: 2
        arg_types: { 0: java.lang.String }
        path_arg: 0
        handler_arg: 1
      - owner: org.springframework.web.servlet.function.RouterFunctionDsl
        method: GET
        verb: GET
        arity: 2
        arg_types: { 0: org.springframework.web.servlet.function.RequestPredicate }
        predicate_arg: 0
        handler_arg: 1
      - owner: org.springframework.web.servlet.function.RouterFunctionDsl
        method: GET
        verb: GET
        arity: 3
        path_arg: 0
        predicate_arg: 1
        handler_arg: 2
```

and add a `RouterFunctionDsl.path` prefix (`{owner: …RouterFunctionDsl, method: path, arity: 1, path_arg: 0}` — the DSL's own predicate factory, so `GET(path("/health"), h)` reads `/health`), plus `accept`/`contentType` media rules on the DSL owner if they are not there, and `and`/`or` composers on `…servlet.function.RequestPredicate` (already present as the Java composers — check). The same five-per-verb block on `spring-webflux-router.yml` with the `org.springframework.web.reactive.function.server` owners, plus the entry:

```yaml
    # The reactive `router { }` WITHOUT coroutines (`GAP-1b`): the file-facade class,
    # exactly as the servlet twin has declared since W44 and `coRouter` above does.
    - owner: org.springframework.web.reactive.function.server.RouterFunctionDslKt
      method: router
      body_arg: 0
```

and `RouterFunctionDsl.nest` as a body-linked prefix (`path_arg: 0, body_arg: 1`, arity 2 — measure whether `nest` has a `RequestPredicate` overload too and declare it with `predicate_arg`).

Then remove `RouterFunctionDsl`'s now-read members from the WebFlux `slice.outside` block if any are listed there (the list at line ~361 names `CoRouterFunctionDsl`; a `RouterFunctionDsl` line may not exist — check `grep -n "RouterFunctionDsl$" src/sextant/catalogs/spring-webflux-router.yml`).

Run the live test → PASS. Run `tests/application/test_combinator_engine.py` → the `_shipped_router_catalog()`-based tests at line ~2096 still pass (they hand-build Java routes; read them and adjust only if a rule they exercised changed shape).

- [ ] **Step 5: the fixture totals move**

`tests/application/test_pipeline.py` and `tests/e2e/test_vertical_slice.py` gain the `/ktmvc/…` and `/ktflux/…` routes, with a comment naming the two Kotlin files. The two catch-alls join Task 4's separate assertion (now four resolved `GET`/NULL rows across the two router catalogs: two builder, two DSL) — update that count.

- [ ] **Step 6: version-scope discipline**

Both catalogs' `measured` blocks cite `scripts/probes/cp12_sweep_round1b.md` for the DSL surface. The five-overload measurement in Step 1 is new evidence: add a `**Version scope**` sentence to that probe file's section on `RouterFunctionDsl` stating the versions the five overloads were counted at (6.1.6 and 7.0.2 for both stacks — run the Step 1 `javap` against the 7.x jar too: `find ~/.m2 -name 'spring-webmvc-7*.jar'`), or, if the probe is regenerated by a script, add the count to the script. `tests/architecture/test_catalog_measurement_coverage.py::test_every_cited_probe_states_a_version_scope_at_all` is the gate.

- [ ] **Step 7: gate, commit**

Run: `JAVA_HOME=… bash scripts/check.sh` → `all gates passed`.

```bash
git add src/sextant/catalogs/spring-mvc-router.yml src/sextant/catalogs/spring-webflux-router.yml fixtures/orders-service/src/main/kotlin/com/acme/orders/routes/KotlinWebFluxRoutes.kt fixtures/orders-service/src/main/kotlin/com/acme/orders/mvcroutes/KotlinMvcRoutes.kt tests/application/test_pipeline.py tests/e2e/test_vertical_slice.py tests/e2e/test_rest_inbound_delivered.py scripts/probes/cp12_sweep_round1b.md
git commit -m "feat(catalogs): the Kotlin router DSL's five verb overloads each derive what they declare on both stacks, and the reactive router { } derives at all (W44-verb-overloads, GAP-1b; A1 Task 5, spec §1b, §5)"
```

---

### Task 6: the register, after CI is green

**Files:**
- Modify: `docs/java-kotlin-delivery-list.md` (the ```delivery, ```closed and severity blocks; the REST inbound section rows for the three ids; §4 Category B), `docs/COVERAGE.md` (regenerated), `scripts/probes/w19_catalog_surface.md` (already regenerated in Task 4)

This task runs **after the PR's CI run passes**, because the ```closed block needs the run URL (`id | test node | CI URL`, enforced by `tests/architecture/test_feature_delivery.py`).

- [ ] **Step 1: move the three ids**

In the ```delivery block, remove `G-37`, `W44-verb-overloads` and `GAP-1b` from the `REST inbound` row. In the ```closed block add:

```
G-37 | tests/e2e/test_rest_inbound_delivered.py::test_the_builder_form_derives_every_route_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/<run id>
W44-verb-overloads | tests/e2e/test_rest_inbound_delivered.py::test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/<run id>
GAP-1b | tests/e2e/test_rest_inbound_delivered.py::test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks | https://github.com/ianynchen/sextant/actions/runs/<run id>
```

In §1's REST inbound table, each of the three rows gets a leading **closed** note naming the commit and the run, in the style of the `G-44` row. In §4 Category B, the sentence "The spec is written … awaiting your review" becomes "PR A1 shipped items 1–4 (commits …); PR A2 is the six of Part II", and the group-A row of the "eight specs" table gains "A1 shipped".

- [ ] **Step 2: regenerate**

Run: `.venv/bin/python scripts/coverage_matrix.py && .venv/bin/python scripts/coverage_versions.py` — the REST inbound cell reads `◐ (6 open)` (from 9); nothing else moves. Run `.venv/bin/pytest tests/architecture -q -p no:cacheprovider` → green.

- [ ] **Step 3: commit and push to the same PR** (the user's standing rule allows a doc commit that closes what the PR delivered; it is not new work)

```bash
git add docs/java-kotlin-delivery-list.md docs/COVERAGE.md
git commit -m "docs(register): G-37, W44-verb-overloads and GAP-1b close on run <run id> — REST inbound 9 → 6 open"
```

---

## Self-review against the spec

| spec requirement | task |
|---|---|
| §10a `receiver_parameter`, §10b `captures` with the instance-handle subtraction and `-1` | Task 1 (extractor), Task 2 (model, projection) |
| §11 steps 1–4: double scan, both corpora, suite, six shapes pinned | Task 1 Steps 1–2 (six shapes), Task 2 Steps 5–7 |
| §3a lists, §3b `arity` + `arg_types`, §3c ambiguity refused at load, the G-13 guard | Task 3 |
| §4 rooting at `build()`, `extends_receiver`; §4b `origins`, pass-throughs mandatory | Task 4 |
| §5 catalog surface both stacks; slice moves; probe 20 of 20; `RouterFunctionDslKt.router` on WebFlux | Task 4 (builder), Task 5 (DSL) |
| §6 static resources handler-less; `resources(Function)` path NULL unresolved | Task 4 (rules; the `Function` overload is the arity-1 rule with `path_arg: 0` on an unreadable argument) |
| §7 cases 1–5 | Task 3 (1, 2, 3), Task 4 (4 by the existing rule, 5) |
| §8 tests 1–7 | 1: Task 3 (hand-built) + Task 5 (live); 2, 4: Task 3; 3: Task 3's first test (`GET(h)` resolved) + Task 4's live catch-all; 5: Task 4; 6: Task 4 (`declines` + `pins`); 7: Task 4 Step 6 |
| §16 items 1–4 in order | Tasks 1+2, 3, 4, 5 |
| spec §7 case 3 wording — a catch-all is `resolved` | Task 3 `_verb_constraints`, pinned by the first overload test and the live catch-all test |

**Type consistency:** `_matching_rule(site, rules)` (Task 3) is what Task 4's `_routes_of` branches call; `predicate_arg` (Task 3) is used by Task 4's builder rules and Task 5's DSL rules; `pass_through` on `_Continuation` (Task 4) is read only in `_routes_of`; `handler: none` (Task 4) is read in `_verb_routes`. `descriptor_parameter_types` returns dotted names, and every `arg_types` value in Tasks 3–5 is spelled dotted.

**Known judgement calls, for the executor:** (1) the exact `find` strings of the two guards must be the lines as written in the engine — set them after the engine edit, not before; (2) `_merged`'s path order decides whether `GET("/four", path("/p"), h)` reads `/four/p` — the plan asserts that order; if `_merged` puts the right operand first, merge the literal path first and say so; (3) Step 6 of Task 1 may need Task 2's model fields first if pydantic forbids extra keys — the plan says how to handle it.
