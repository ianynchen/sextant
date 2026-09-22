# Temporal workflows and the Vert.x event bus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `temporal-cadence` and `vertx-eventbus` — the register's Group D — so the **Async** column of the delivery block empties, and give `annotation_driven` the one key that lets any catalog record a qualifying attribute.

**Architecture:** No new engine. Temporal is four `annotation_driven` catalogs plus one `single_call` catalog, riding the inheritance walk and the `declared_on` gate partition that `jakarta-jws.yml`/`jakarta-jws-client.yml` already use. Vert.x is one `single_call`, one `fluent` and one `annotation_driven` catalog. Three new `path_fallback` words, one new `members` word, one new `metadata_from` key with its own writer pass, two new `Protocol` members.

**Tech Stack:** Python 3.14, DuckDB, YAML catalogs; Java 21 fixtures built by Maven; `javap` probes.

**Spec:** `docs/superpowers/specs/2026-09-22-temporal-and-eventbus-design.md` — read §0 (the measurements), §0a (the three Major rulings that shaped this plan) and §1f (the path-versus-metadata rule) before Task 1.

## Global Constraints

- **No false positives** (user rule, 2026-09-20). A workflow type, an activity name, an address or a handler is written only where the code states it and the framework honours it. Every ambiguity is an unresolved column or an absent row, never a guess. Misses are acceptable and are stated on the catalog and in COVERAGE.
- **The resolve layer names no framework and no language.** `tests/architecture/test_source_rules.py` and `test_language_confinement.py` enforce this over every `*.py` and `*.sql` file under `src/sextant`. Framework knowledge is catalog data. This is why the protocol member is `eventbus` and not `vertx_eventbus`.
- **Every framework claim carries a probe with §5.4 provenance.** `tests/architecture/test_probe_provenance.py`. A `measured:` block names the artifact, the versions and the probe that read them. A probe that contradicts the spec changes the spec, not the probe (GUIDELINES §1.1).
- **Existing output moves only in Task 9**, and the tests that pin it move in that same task.
- **The gate is** `JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh` — run it whole, read the exit code, never pipe it through `tail`. `scripts/check.sh --guards` runs the mutation guards.
- **No worktrees** (GUIDELINES §13.9). Work on the branch this plan is committed to.
- **Match the surrounding style** (GUIDELINES §3, §13.5): catalogs carry their reasoning and their measurement in comments; do not refactor adjacent code.

---

## File Structure

| file | responsibility |
|---|---|
| `src/sextant/domain/closed_sets.py` | the two new `Protocol` members |
| `src/sextant/egress/render/document.py` | `temporal` into `_VERBED_PROTOCOLS` |
| `src/sextant/application/resolve/engines/annotation_driven.py` | three `_PATH_FALLBACKS` words, `declared_type_methods` in `_MEMBER_RULES`, the `metadata_from` key and its validation |
| `src/sextant/storage/duckdb/derive_endpoints.sql` | the naming words' composition; the `declared_type_methods` conjunct |
| `src/sextant/application/resolve/endpoint_attributes.py` | **new** — the `metadata_from` writer pass |
| `src/sextant/application/resolve/pipeline.py` | one call, below `apply_protocol_hints` |
| `src/sextant/catalogs/temporal-*.yml` (5) | Temporal |
| `src/sextant/catalogs/vertx-eventbus*.yml`, `quarkus-consume-event.yml` (3) | the event bus |
| `src/sextant/catalogs/{spring,micronaut}-{kafka,jms}.yml`, `spring-rabbit.yml` | Task 9's `metadata_from` lines |
| `fixtures/temporal-probe`, `fixtures/orders-eventbus` | the two new fixtures |
| `scripts/probes/cp30_*`, `cp31_*`, `cp32_*` | the measurements |

---

## Task 1: The two `Protocol` members

**Files:**
- Modify: `src/sextant/domain/closed_sets.py:116-163`
- Modify: `src/sextant/egress/render/document.py:206`
- Modify: `tests/architecture/test_source_rules.py:34-46`
- Test: `tests/domain/test_closed_sets.py`, `tests/egress/test_render.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Protocol.TEMPORAL` (`"temporal"`) and `Protocol.EVENTBUS` (`"eventbus"`), which every catalog in Tasks 5–8 names in its `protocol:` key.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/test_closed_sets.py`:

```python
def test_the_two_group_d_protocols_are_members():
    assert Protocol.TEMPORAL.value == "temporal"
    assert Protocol.EVENTBUS.value == "eventbus"
```

In `tests/egress/test_render.py` — the render split, asserted both ways because the verbless set is the complement and a member added to neither list falls silently into it:

```python
def test_a_temporal_row_renders_its_kind_and_an_eventbus_row_does_not():
    from sextant.egress.render.document import _VERBED_PROTOCOLS, _VERBLESS_PROTOCOLS

    assert "temporal" in _VERBED_PROTOCOLS
    assert "eventbus" in _VERBLESS_PROTOCOLS
```

- [ ] **Step 2: Run them to verify they fail**

```bash
.venv/bin/python -m pytest tests/domain/test_closed_sets.py tests/egress/test_render.py -q
```
Expected: FAIL — `AttributeError: TEMPORAL`.

- [ ] **Step 3: Add both members in one edit**

In `closed_sets.py`, after `RSOCKET = "rsocket"`, with a comment in the file's own voice — state the DR-5 argument, state why both arrive together (the 2H/2O blocks' reason: the set is closed), and state the naming constraint:

```python
    # Group D (spec 2026-09-22 §1a). Two members in one edit, for the reason the
    # 2H and 2O blocks above give: the set is closed, so a member a later task
    # needs costs one line here and a schema change if it arrives alone.
    #
    # Each is its own protocol on the same DR-5 argument: linking gates on
    # protocol equality, and a workflow type can only be answered by a worker
    # polling for it, an event-bus address only by a consumer bound to it.
    #
    # `temporal` names a product, as `pulsar` and `rsocket` do, because the wire
    # has no other name. `eventbus` does NOT name the framework whose bus it is
    # (Vert.x): `tests/architecture/test_source_rules.py` forbids that token in
    # every source file here, so the member is named for the KIND of wire — an
    # addressed in-process or clustered event bus — exactly as `amqp` is named
    # for the protocol rather than for Rabbit.
    TEMPORAL = "temporal"
    EVENTBUS = "eventbus"
```

In `document.py`, add `temporal` to `_VERBED_PROTOCOLS`'s literal set (`frozenset({"http", "grpc", "temporal"})`), with a one-line comment: a Temporal row's `method` carries its operation kind, the GraphQL precedent. Leave `_VERBLESS_PROTOCOLS` alone — it is the complement.

In `test_source_rules.py`, add `"temporal"` and `"eventbus"` to `PROTOCOLS`.

- [ ] **Step 4: Run the tests and the architecture suite**

```bash
.venv/bin/python -m pytest tests/domain tests/egress tests/architecture -q
```
Expected: PASS. If `test_no_framework_is_named_anywhere_in_code` fails, a source file names one of the two new words — that is the rule working; rename the offender, do not exempt it.

- [ ] **Step 5: Commit**

```bash
git add src/sextant/domain/closed_sets.py src/sextant/egress/render/document.py tests
git commit -m "feat(schema): temporal and eventbus join the closed Protocol set"
```

---

## Task 2: Probe CP-30 — Temporal's naming rules

**Files:**
- Create: `scripts/probes/cp30_temporal_contract_naming/run.sh`, `scripts/probes/cp30_temporal_contract_naming/probe.py`, `scripts/probes/cp30_temporal_contract_naming.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the measurement rows Tasks 3 and 5 cite in `measured:` blocks, as `scripts/probes/cp30_temporal_contract_naming.md`.

- [ ] **Step 1: Copy the harness shape**

Read `scripts/probes/cp27_spring_integration_wiring/run.sh` and follow it exactly: an `ARTIFACTS` array of `key|groupId|artifactId|version`, `mvn dependency:get` for a missing jar, the version column read from each jar's own manifest `Implementation-Version` with an abort when it disagrees, and the fixture's own compiled classes as the last spec. Artifacts:

```
sdk|io.temporal|temporal-sdk|1.27.0
boot|io.temporal|temporal-spring-boot-autoconfigure|1.27.0
```

The fixture row is added in Task 6; until then the script's last spec is omitted and the `.md` says so.

- [ ] **Step 2: Answer these questions and no others**

Each row is a `javap` read. Nothing is executed.

| row | question | expected (spec §0) |
|---|---|---|
| 1 | `javap -c -p io.temporal.common.metadata.POJOWorkflowMethodMetadata` — which name does the `WORKFLOW` branch take? | `Class.getSimpleName()` on the interface at offset 101; `Method.getName()` at 122 for the other kinds (M1) |
| 2 | `javap -c -p io.temporal.common.metadata.POJOActivityMethodMetadata` — what happens when `@ActivityMethod.name()` is non-empty? | `isEmpty()` tested at 50, the annotation's own value returned at 58, the prefix composed only on the empty branch (M2) |
| 3 | the same class's `getActivityNameFromMethod` | `substring(0,1).toUpperCase()` + `substring(1)` (M3) |
| 4 | `javap -c -p io.temporal.common.metadata.POJOActivityInterfaceMetadata` — `validateAndQualifiedForActivityMethod` | `true` at 73 for an unannotated method; `false` only for static or synthetic (M4) |
| 5 | the same question for `POJOWorkflowInterfaceMetadata.validateAndQualifiedForWorkflowMethod` | an unannotated method qualifies for nothing (M4's other half) |
| 6 | `javap io.temporal.spring.boot.{WorkflowImpl,ActivityImpl,NexusServiceImpl}` | each declares `String[] workers()` and `String[] taskQueues()` (M5) |
| 7 | `javap -s io.temporal.client.WorkflowClient` / `io.temporal.client.WorkflowStub` | `newUntypedWorkflowStub(String, …)` names the workflow type at argument 0; `signal`/`query`/`update` name a member at argument 0 (M10) |
| 8 | `javap -s` on `WorkerFactory`, and the three `*Options$Builder` classes | the task queue's only declaration sites (M5) |

- [ ] **Step 3: Write the `.md` with §5.4 provenance**

Follow `scripts/probes/cp27_spring_integration_wiring.md`'s structure: the questions, the version scope, the generated table, and a **verdict per row** in words. Every claim a catalog will cite must appear as a row here.

- [ ] **Step 4: Run it and check provenance**

```bash
bash scripts/probes/cp30_temporal_contract_naming/run.sh
.venv/bin/python -m pytest tests/architecture/test_probe_provenance.py -q
```
Expected: the table prints with a version column from the jars' own bytes; the provenance test passes.

- [ ] **Step 5: Commit**

```bash
git add scripts/probes/cp30_temporal_contract_naming*
git commit -m "probe(cp30): Temporal's four naming branches and the activity qualification rule"
```

---

## Task 3: The three `path_fallback` words and `declared_type_methods`

**Files:**
- Modify: `src/sextant/application/resolve/engines/annotation_driven.py:560` (`_PATH_FALLBACKS`), `:811` (`_MEMBER_RULES`)
- Modify: `src/sextant/storage/duckdb/derive_endpoints.sql` (the fallback composition; the member rule's declaring-type conjunct near line 776 and line 916)
- Test: `tests/application/test_endpoints.py`

**Interfaces:**
- Consumes: Task 2's CP-30 rows (cited in the code comments).
- Produces: the four catalog words Task 5 writes — `path_fallback: declaring_type_simple_name`, `prefixed_capitalized_construct_name`, `declaring_type_qualified_name`, and `members: declared_type_methods`.

- [ ] **Step 1: Write the failing tests**

Five tests in `tests/application/test_endpoints.py`, beside the existing `path_fallback` tests. Use the file's own harness for building a workspace from fact rows. The naming tests:

```python
def test_declaring_type_simple_name_names_the_interface_not_the_implementor():
    """M1: the default workflow type is the ANNOTATED INTERFACE's simple name, while
    the row's handler is the implementor's override. The two differ, and reading the
    handler's own class would publish `OrderWorkflowImpl` — a type no client starts."""
    # interface com.acme.OrderWorkflow declares @Marker on run(); class OrderWorkflowImpl
    # implements it and overrides run() carrying no annotation of its own.
    rows = derive(catalog=_catalog(path_fallback="declaring_type_simple_name"), facts=...)
    assert [(r["path"], r["handler"]) for r in rows] == [
        ("OrderWorkflow", "com/acme/OrderWorkflowImpl#run().")
    ]


def test_prefixed_capitalized_construct_name_composes_the_prefix_and_capitalizes():
    """M2, M3: `chargeCard` under namePrefix `billing_` is `billing_ChargeCard`."""
    ...
    assert paths == ["billing_ChargeCard"]


def test_an_explicitly_named_member_never_reaches_the_prefix():
    """M2: the fallback composes the prefix, so a member carrying its own name skips it
    by construction — `@Marker(name = "Charge")` under `billing_` is `Charge`, NOT
    `billing_Charge`. This is the edge that tells the rule from every paraphrase."""
    ...
    assert paths == ["Charge"]


def test_declaring_type_qualified_name_keeps_the_package():
    """M8: Quarkus's default address is the bean class's FULLY-QUALIFIED name."""
    ...
    assert paths == ["com.acme.OrderConsumer"]
```

And the member fence, whose negative half is the point:

```python
def test_declared_type_methods_skips_a_member_the_gate_class_declares_itself():
    """M-3: the gate fires on the implementor because the type annotation is INHERITED
    onto it, so `public_methods` would publish its own helpers. `declared_type_methods`
    enumerates only members whose declaring type carries the annotation DIRECTLY."""
    # interface BillingActivities (@Marker) declares chargeCard();
    # class BillingActivitiesImpl implements it, overrides chargeCard(), and declares
    # its own public reloadRates().
    assert paths == ["ChargeCard"]          # reloadRates is absent
```

- [ ] **Step 2: Run them to verify they fail**

```bash
.venv/bin/python -m pytest tests/application/test_endpoints.py -q -k "declaring_type or prefixed or declared_type_methods or explicitly_named"
```
Expected: FAIL — `CatalogError: ... is not one of construct_name, read_accessor_property, write_accessor_property`.

- [ ] **Step 3: Add the words**

`_PATH_FALLBACKS` maps a word to the accessor prefixes it strips, which is the wrong shape for these three. Widen it as the file's own `OI-5` comment widened it before — a mapping whose value is a small rule object — or keep the dict and add a second mapping beside it; either is acceptable, but **the new word must be refused when unknown exactly as today** (that refusal is what `_PATH_FALLBACKS`'s comment calls load-bearing). Add, with comments citing CP-30 rows 1–3 and spec §2b:

- `declaring_type_simple_name` — the simple name of the type that DECLARED the annotated member. Under the inheritance walk that is the interface, while the row's handler is the implementor's override: say so in the comment, because the two coming apart is the whole of M1.
- `prefixed_capitalized_construct_name` — the declaring type's prefix attribute (named by `mapping.prefix_from` read off `type_annotation`) + the construct name with its first character upper-cased. State in the comment that composing the prefix INSIDE the fallback is what makes M2 free: an explicitly named member never reaches a fallback, so the prefix is skipped by construction rather than by a flag.
- `declaring_type_qualified_name` — the declaring type's fully-qualified name, nothing stripped.

Add `declared_type_methods` to `_MEMBER_RULES`, with a comment in the voice of the existing one (this vocabulary is the sharpest in the engine — a word read as something it is not mints endpoints out of ordinary methods) citing CP-30 row 4 and the helper-method example from spec §2c.

- [ ] **Step 4: Implement the composition in SQL**

In `derive_endpoints.sql`:

- The three naming words compose where the construct's own name is read, beside the `getURL -> uRL` edge the accessor rule already pins. The declaring type is the annotation row's own target's enclosing type — the same join the inheritance walk already produces; do not re-derive it from the handler.
- `declared_type_methods` is the `public_methods` rule with one conjunct: the member's declaring type must carry the catalog's type annotation as a **real** annotation row, never a synthetic one. `annotations_effective` already distinguishes them — a synthetic row carries the catalog's own `catalog_id`, a real row carries NULL — so the conjunct reads the real rows only. Put the reason in the comment: an inherited gate is what makes the implementor a gate type, and enumerating its own declarations is exactly the fabrication this word exists to remove.

- [ ] **Step 5: Run the tests**

```bash
.venv/bin/python -m pytest tests/application/test_endpoints.py -q
```
Expected: PASS, including every pre-existing test in the file — `public_methods` must behave exactly as before.

- [ ] **Step 6: Run the gate**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
```
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add src/sextant/application/resolve/engines/annotation_driven.py src/sextant/storage/duckdb/derive_endpoints.sql tests
git commit -m "feat(annotation_driven): three declaring-type naming words and the declared_type_methods member fence"
```

---

## Task 4: `metadata_from` — the key and its writer

**Files:**
- Modify: `src/sextant/application/resolve/engines/annotation_driven.py` (the key's validation, beside `_validate_naming`)
- Create: `src/sextant/application/resolve/endpoint_attributes.py`
- Modify: `src/sextant/application/resolve/pipeline.py:230` (the call, below `record_request_requirements`)
- Test: `tests/application/test_endpoint_attributes.py` (new)

**Interfaces:**
- Consumes: `Catalog.matches["metadata_from"]`, `effective_annotation_uses(workspace, catalog)` from `engines/annotation_driven.py`, the `endpoint_metadata_insert` derivation.
- Produces: `record_endpoint_attributes(workspace, catalogs) -> None`, called from the pipeline. Tasks 5, 8 and 9 write `metadata_from` blocks against it.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_attribute_named_by_metadata_from_becomes_a_metadata_row():
    """One `{annotation, attribute, kind}` triple, one present attribute, one row against
    the endpoint that declaration minted — `caller` the handler, the `_entry` convention
    `request_requirements` already keeps for an inbound entry."""
    rows = _run(catalog=_catalog(metadata_from=[{"annotation": "com.acme.Impl",
                                                 "attribute": "taskQueues",
                                                 "kind": "task_queue"}]), ...)
    assert [(r["kind"], r["name"], r["value"], r["resolution"]) for r in rows] == [
        ("task_queue", None, "orders", "resolved")
    ]


def test_an_array_attribute_is_one_row_per_element():
    assert values == ["billing", "billing-retry"]


def test_a_placeholder_value_stays_unresolved():
    """§8.2: this repository never guesses a deployed value."""
    assert (value, resolution) == ("${orders.queue}", "unresolved")


def test_an_absent_attribute_writes_absent_value_when_declared_and_nothing_otherwise():
    """M8: `@ConsumeEvent.local()` defaults to true, and a default never reaches the
    annotation USE — so the catalog states the default and cites the AnnotationDefault
    it measured. A triple with no `absent_value` writes nothing for an absent attribute:
    silence is the honest answer when nobody measured the default."""


def test_a_metadata_row_names_only_an_endpoint_its_own_catalog_minted():
    """Two catalogs can match one handler. An entry against another catalog's row would
    state one framework's attribute about another's endpoint."""


def test_an_unknown_metadata_from_shape_is_refused_by_file():
    with pytest.raises(CatalogError, match="metadata_from"):
        ...
```

- [ ] **Step 2: Run them to verify they fail**

```bash
.venv/bin/python -m pytest tests/application/test_endpoint_attributes.py -q
```
Expected: FAIL — module not found.

- [ ] **Step 3: Validate the key**

In `annotation_driven.py`, beside the other `_validate_*` helpers: `metadata_from` is a list of mappings with required `annotation` (str), `attribute` (str) and `kind` (str), plus an optional `absent_value` (str). Anything else is a `CatalogError` naming the catalog source and the offending entry — the shape every other catalog key is refused by. `kind` is NOT checked against a closed set: `endpoint_metadata.kind`'s own comment says the vocabulary is per protocol and the catalog names it.

- [ ] **Step 4: Write the pass**

`endpoint_attributes.py`, modelled on `request_requirements.py::_from_mapping_attributes` — read that function before writing this one; it is the same join with a different payload.

```python
def record_endpoint_attributes(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Spec 2026-09-22 §1f. Every attribute a catalog's `metadata_from` names, written as
    an `endpoint_metadata` row against the endpoint that declaration minted.

    INBOUND ONLY, and that is a claim rather than a limit not yet lifted: the rule §1f
    states is that a qualifying attribute belongs to the side that declares it, and every
    attribute this key reads sits on a listener or an implementation — the receiving side.
    An outbound catalog declaring the key would be stating a peer's configuration as its
    own, so `_validate_metadata_from` refuses it there.
    """
```

The body: for each catalog declaring the key, take the inbound endpoints whose `catalog_id` is the catalog's and whose `handler` is not NULL; read `effective_annotation_uses(workspace, catalog)` once (it carries every real annotation plus this catalog's synthetic ones, so a composed or inherited mapping's attributes count here exactly as they count in the derivation — `_from_mapping_attributes`'s own reason); for each endpoint look for the named annotation on the handler **and** on the handler's enclosing type (`owner_of(bare_descriptor(handler))`, the `@WorkflowImpl`-on-the-class case); emit one row per value with `kind` from the triple, `name` NULL, `value` the element, `resolution` `unresolved` when the value carries a `${`, `evidence` `compiler`, `requirement` NULL.

Reuse `request_requirements._entry`'s column shape exactly — move it to a shared helper only if both files end up importing it; a second literal dict with the same keys is acceptable and is what the codebase already does across passes.

- [ ] **Step 5: Wire it into the pipeline**

In `pipeline.py`, immediately below `record_request_requirements`, inside its own `_timed` block, with a comment giving the order's reason: below `apply_protocol_hints` because an entry names its row by identity columns and `protocol` is one of them; below the reset because it writes `endpoint_metadata`; its order against `record_request_requirements` does not matter (disjoint kinds, insert-if-absent).

- [ ] **Step 6: Run the tests and the gate**

```bash
.venv/bin/python -m pytest tests/application -q
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
```
Expected: PASS, exit 0. **No shipped catalog declares the key yet, so no existing row may move** — a diff in any e2e assertion here means the pass is writing rows nobody asked for.

- [ ] **Step 7: Commit**

```bash
git add src/sextant/application/resolve/endpoint_attributes.py src/sextant/application/resolve/engines/annotation_driven.py src/sextant/application/resolve/pipeline.py tests
git commit -m "feat(resolve): metadata_from — an annotation attribute becomes an endpoint_metadata entry"
```

---

## Task 5: The five Temporal catalogs

**Files:**
- Create: `src/sextant/catalogs/temporal-workflow.yml`, `temporal-workflow-client.yml`, `temporal-activity.yml`, `temporal-activity-client.yml`, `temporal-untyped.yml`
- Test: `tests/ingress/test_yaml_source.py` (loading and refusal), plus every `tests/architecture/test_catalog_*.py` gate (descriptors, measurement coverage, one-fqn notation)

**Interfaces:**
- Consumes: Task 1's members, Task 3's four words, Task 4's `metadata_from`, Task 2's CP-30 rows for every `measured:` entry.
- Produces: the catalogs Task 7's e2e test asserts against.

- [ ] **Step 1: Write the two workflow catalogs**

`temporal-workflow.yml` — `style: annotation_driven`, `protocol: temporal`, `direction: inbound`, `detect.coordinates: ["io.temporal:temporal-sdk"]`, `requires: [annotation_args, typed_signatures]`. The full `matches` block is in spec §2d; copy the values verbatim. Beyond them, the file must carry in comments:

- why `declared_on: class` (the `jakarta-jws.yml` partition: the interface is either a client contract or an implementor's contract, and the two are opposite directions of one identity);
- CP-30 row 1 for `declaring_type_simple_name`, stating that the name comes from the interface while the handler is the implementor's override;
- CP-30 rows 6 and 8 for the `metadata_from` block, and — the honest part — that a **programmatic** worker's queue (`WorkerFactory.newWorker`) is not read at all, with the open-issue id Task 11 files;
- the `measured:` block naming `io.temporal:temporal-sdk` 1.27.0 and `io.temporal:temporal-spring-boot-autoconfigure` 1.27.0, `by: scripts/probes/cp30_temporal_contract_naming.md`.

`temporal-workflow-client.yml` — the same file with `direction: outbound`, `declared_on: interface`, and **no** `metadata_from` (a client states no queue). Its comment carries `jakarta-jws-client.yml`'s own argument: `declared_on: interface` on an outbound catalog already subtracts every interface the module implements, so a hand-written interface implemented here derives inbound once and outbound never.

- [ ] **Step 2: Write the two activity catalogs**

`temporal-activity.yml` / `temporal-activity-client.yml`, the same partition, plus:

- `members: declared_type_methods` with CP-30 rows 4–5 quoted: every non-static, non-synthetic method of an `@ActivityInterface` is an activity, and a workflow interface is the opposite — which is why the word is here and not in the workflow files;
- `path_fallback: prefixed_capitalized_construct_name` with CP-30 rows 2–3 and the `Charge` vs `billing_ChargeCard` pair written out.

- [ ] **Step 3: Write `temporal-untyped.yml`**

`style: single_call`, `direction: outbound`, one row: `newUntypedWorkflowStub` with its measured descriptor and `channel_arg: 0`. The comment states what is NOT declared and why (spec §2f): `WorkflowStub.signal/query/update`'s argument 0 is a member name with no workflow type at the call site, so its path would be a bare `cancel` colliding with every other workflow's signal — under-reporting is honest, a colliding identity is not.

- [ ] **Step 4: Run the catalog-loading tests**

```bash
.venv/bin/python -m pytest tests/ingress/test_yaml_source.py tests/architecture -q
```
Expected: PASS. A `CatalogError` here is the validation from Tasks 3 and 4 doing its job — fix the catalog.

- [ ] **Step 5: Commit**

```bash
git add src/sextant/catalogs/temporal-*.yml
git commit -m "feat(catalogs): Temporal workflows and activities, inbound and outbound"
```

---

## Task 6: The `temporal-probe` fixture

**Files:**
- Create: `fixtures/temporal-probe/pom.xml` and its sources under `src/main/java/com/acme/tp/`
- Modify: `tests/fixture_build.py:53` (`PRIMED_FIXTURES`)
- Modify: `scripts/probes/cp30_temporal_contract_naming/run.sh` (the fixture spec row)

**Interfaces:**
- Consumes: Task 5's catalogs (this fixture is what proves them).
- Produces: `FIXTURES / "temporal-probe"`, compiled by `compile_fixture`, read by Task 7.

- [ ] **Step 1: Write the pom**

Copy `fixtures/orders-pekko/pom.xml`'s shape — `com.acme`, version `1.0.0`, `maven.compiler.release` 21, `maven.compiler.parameters` true, and every dependency with a blanket `<exclusions>` so only API jars resolve. Dependencies: `io.temporal:temporal-sdk:1.27.0` and `io.temporal:temporal-spring-boot-autoconfigure:1.27.0`. A comment saying what the module is for and that it never runs.

- [ ] **Step 2: Write the sources — every arm spec §4 lists**

```java
@WorkflowInterface
public interface OrderWorkflow {
    @WorkflowMethod void processOrder(String id);      // -> OrderWorkflow
    @SignalMethod   void cancel(String reason);        // -> OrderWorkflow/cancel
    @QueryMethod    String status();                   // -> OrderWorkflow/status
    @UpdateMethod   String amend(String patch);        // -> OrderWorkflow/amend
    default String helper() { return "x"; }            // NO annotation -> nothing
}

@WorkflowInterface
public interface ShipmentWorkflow {
    @WorkflowMethod(name = "ShipOrder") void ship(String id);   // -> ShipOrder
}

@ActivityInterface(namePrefix = "billing_")
public interface BillingActivities {
    @ActivityMethod(name = "Charge") void charge(String id);    // -> Charge
    void refundCard(String id);                                  // -> billing_RefundCard
}

@WorkflowImpl(taskQueues = "orders")
public class OrderWorkflowImpl implements OrderWorkflow { /* every method overridden */ }

@ActivityImpl(taskQueues = {"billing", "billing-retry"})
public class BillingActivitiesImpl implements BillingActivities {
    public void charge(String id) { }
    public void refundCard(String id) { }
    public void reloadRates() { }        // declared HERE -> must derive nothing
}
```

Plus a client package declaring `PaymentsWorkflow` (a `@WorkflowInterface` this module does **not** implement) for the outbound rows, and a `OrderClient` class containing, each with a comment naming what it proves:

```java
WorkflowStub stub = client.newUntypedWorkflowStub("OrderWorkflow");   // -> one outbound row
stub.signal("cancel", "late");                                        // -> nothing (§2f)
OrderWorkflow running = client.newWorkflowStub(OrderWorkflow.class, "wf-123");  // -> nothing
```

- [ ] **Step 3: Register and compile it**

Add `"temporal-probe"` to `PRIMED_FIXTURES`. Then:

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home .venv/bin/python -c "import sys; sys.path.insert(0,'tests'); from fixture_build import FIXTURES, compile_and_stamp; compile_and_stamp(FIXTURES/'temporal-probe', offline=False)"
```
Expected: class files under `fixtures/temporal-probe/target/classes`.

- [ ] **Step 4: Add the fixture row to CP-30 and re-run it**

```bash
bash scripts/probes/cp30_temporal_contract_naming/run.sh
```
Expected: the last table row reads the fixture's own compiled classes.

- [ ] **Step 5: Commit**

```bash
git add fixtures/temporal-probe tests/fixture_build.py scripts/probes/cp30_temporal_contract_naming
git commit -m "test(fixtures): temporal-probe — every naming branch, both partitions, four variance arms"
```

---

## Task 7: Temporal end to end

**Files:**
- Modify: `tests/e2e/test_async_delivered.py`

**Interfaces:**
- Consumes: Tasks 5 and 6.
- Produces: the pins the register's ```intention-test-missing``` rules read.

- [ ] **Step 1: Write the test**

Follow the file's own `derived` fixture pattern — `compile_fixture`, `CliRunner().invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", …])`, assert `result.exit_code == 0`, then read the workspace. One module-scoped fixture over `temporal-probe`, two tests:

```python
def test_temporal_shapes_rows(derived):
    """Every naming branch and both partitions, as rows."""
    assert rows == {
        ("temporal", "inbound", "workflow", "OrderWorkflow", ".../OrderWorkflowImpl#processOrder"),
        ("temporal", "inbound", "signal",   "OrderWorkflow/cancel", ...),
        ("temporal", "inbound", "query",    "OrderWorkflow/status", ...),
        ("temporal", "inbound", "update",   "OrderWorkflow/amend",  ...),
        ("temporal", "inbound", "workflow", "ShipOrder", ...),
        ("temporal", "inbound", "activity", "Charge", ...),
        ("temporal", "inbound", "activity", "billing_RefundCard", ...),
        ("temporal", "outbound", "workflow", "PaymentsWorkflow", ...),
        ("temporal", "outbound", "workflow", "OrderWorkflow", ...),   # the untyped stub
    }


def test_temporal_derives_nothing_from_the_four_variance_arms(derived):
    """Each of these would be a fabricated boundary, and each has its own reason:
    a helper on an activity impl (§2c), a helper on a workflow interface carrying no
    member annotation, `stub.signal` (§2f, a colliding identity), and a stub naming a
    running execution (§2g, it starts nothing)."""
    assert "billing_ReloadRates" not in paths
    assert not [p for p in paths if p.endswith("/helper")]
    assert paths.count("OrderWorkflow") == 2       # the impl's row and the untyped stub's
```

Also assert the `endpoint_metadata` rows: `task_queue` `orders` against the workflow rows, and `billing` + `billing-retry` against the activity rows.

- [ ] **Step 2: Run it**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home .venv/bin/python -m pytest tests/e2e/test_async_delivered.py -q
```
Expected: PASS. A row that is present and should not be is a false positive — fix the catalog or the word, never the assertion.

- [ ] **Step 3: Run the whole gate**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
```
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_async_delivered.py
git commit -m "test(e2e): Temporal rows, both directions, and the four arms that derive nothing"
```

---

## Task 8: The event bus — probe, catalogs, fixture, test

This is one task rather than four because the three catalogs share one measurement and one fixture, and no reviewer could approve one of them without the others.

**Files:**
- Create: `scripts/probes/cp31_eventbus_surface/{run.sh,probe.py}`, `scripts/probes/cp31_eventbus_surface.md`
- Create: `src/sextant/catalogs/vertx-eventbus.yml`, `vertx-eventbus-chain.yml`, `quarkus-consume-event.yml`
- Create: `fixtures/orders-eventbus/` (pom + sources)
- Modify: `tests/fixture_build.py` (`PRIMED_FIXTURES`), `tests/e2e/test_async_delivered.py`

**Interfaces:**
- Consumes: Task 1's `EVENTBUS`, Task 3's `declaring_type_qualified_name`, Task 4's `metadata_from`.
- Produces: the event-bus rows.

- [ ] **Step 1: Probe CP-31**

Artifacts: `io.vertx:vertx-core:4.5.10`, `io.vertx:vertx-core:5.0.0`, `io.smallrye.reactive:smallrye-mutiny-vertx-core:3.16.0`, `io.quarkus:quarkus-vertx:3.17.5`, `io.quarkus:quarkus-vertx-deployment:3.17.5`. Rows: every declared descriptor of `EventBus`, `MessageConsumer`, `MessageProducer` **per version**; `EventBusImpl.consumer(String, Handler)`'s delegation to `consumer(String)` then `MessageConsumer.handler` (M6); `MessageConsumerOptions.setAddress` (M7); `@ConsumeEvent`'s `AnnotationDefault` values (M8); `VertxProcessor`'s `withDefaultValue("value", BeanInfo.getBeanClass().toString())` (M8); the Mutiny facade's own descriptors (M9). Write the `.md` with a verdict per row.

- [ ] **Step 2: Write the three catalogs**

Per spec §3a–§3c. The rules that must appear as comments, because getting either backwards publishes something false:

- **every row declares its own erased descriptor** — `spring-rabbit-template.yml`'s overload-collision reason, restated;
- **4.5-only and 5.0-only rows live in one file**; a declared overload absent from the module's version never matches, the "undeclared arity" shape turned around;
- **M6 is why `vertx-eventbus-chain.yml` has a terminal**: `consumer(String, Handler)` IS `consumer(String).handler(h)`, so a consumer never given a handler receives nothing and must derive nothing — the `registration.started_by` judgement (`OI-64`) one engine over;
- **`quarkus-consume-event.yml`'s two measured rules**: the default address is the bean class's fully-qualified name, and `local()` defaults to `true` so the `metadata_from` triple carries `absent_value`.

- [ ] **Step 3: Write the `orders-eventbus` fixture**

Per spec §4: raw `send`/`publish`/`request`; `consumer(addr, handler)`; `localConsumer`; a two-step `consumer(addr)` … `.handler(…)`; `sender(addr).write(…)`; **a `consumer(addr)` never given a handler**; and a Quarkus arm with `@ConsumeEvent("orders.created")`, a bare `@ConsumeEvent`, `@ConsumeEvent(value = …, local = false)`, `@ConsumeEvent("${orders.address}")`, and one `(MultiMap, Order)` method. Add to `PRIMED_FIXTURES` and compile as Task 6 Step 3 does.

- [ ] **Step 4: Write `test_eventbus_shapes_rows`**

Assert the rows — addresses, directions, handlers — plus: the bare `consumer` derives **nothing**; the bare `@ConsumeEvent` derives the declaring class's FQN; the `${…}` address is `unresolved`; the `delivery` metadata is `local` for the bare annotation and `clustered` for `local = false`.

- [ ] **Step 5: Run the gate**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
.venv/bin/python -m pytest tests/architecture/test_probe_provenance.py -q
```
Expected: exit 0; provenance passes.

- [ ] **Step 6: Commit**

```bash
git add scripts/probes/cp31_eventbus_surface* src/sextant/catalogs/vertx-eventbus*.yml src/sextant/catalogs/quarkus-consume-event.yml fixtures/orders-eventbus tests
git commit -m "feat(catalogs): the Vert.x event bus — raw calls, the two-step consumer, and Quarkus @ConsumeEvent"
```

---

## Task 9: `metadata_from` on the shipped listener catalogs

**This is the only task that moves existing output.** The user ruled (spec §0a, M-2 option b) that it lands here rather than as a follow-up. Every test that reads `endpoint_metadata` moves in this task, never in a later one.

**Files:**
- Create: `scripts/probes/cp32_listener_attributes/{run.sh,probe.py}`, `scripts/probes/cp32_listener_attributes.md`
- Modify: `src/sextant/catalogs/spring-kafka.yml`, `micronaut-kafka.yml`, `spring-jms.yml`, `micronaut-jms.yml`, `spring-rabbit.yml`
- Modify: `tests/e2e/test_vertical_slice.py`, `tests/e2e/test_rest_inbound_delivered.py`, `tests/application/test_combinator_engine.py`, `test_call_engines.py`, `test_config_join.py`, `test_pipeline.py`, `test_request_requirements.py` — whichever actually move

**Interfaces:**
- Consumes: Task 4's `metadata_from`.
- Produces: `consumer_group`, `selector`, `subscription` and `delivery` entries on shipped endpoints.

- [ ] **Step 1: Probe CP-32 first — the criterion decides the list, not the annotation's attribute list**

For each attribute below, read on spring-kafka 3.1.4, spring-jms 3.1.4, spring-rabbit 3.1.4 and the Micronaut equivalents: its declared type, its `AnnotationDefault`, and **what the framework's own post-processor does with it** — so that `kind` names what the framework means rather than what the attribute is called.

The criterion, stated so the list is not open-ended: **an attribute a peer would care about** — whether and how a message reaches this handler. Recorded: `groupId` (`consumer_group`), `selector` (`selector`), `subscription` (`subscription`), `exclusive` (`delivery`). **Not** recorded, and the catalogs say so: `concurrency`, `ackMode`, `containerFactory`, `errorHandler`, `autoStartup`, `clientIdPrefix` — tuning knobs, invisible to a peer.

If the probe finds an attribute does not mean what the criterion assumed, **change the list, not the probe**, and say so in the `.md`.

- [ ] **Step 2: Add one `metadata_from` block per catalog**

Each block cites its CP-32 row. Each catalog also gains a sentence naming the attributes it deliberately does not record, and why — the same "stated boundaries" discipline every other catalog keeps.

- [ ] **Step 3: Run the full suite and see exactly what moved**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
```
Expected: failures **only** in assertions over `endpoint_metadata`, and every one of them an ADDED row. A failure of any other shape means a metadata entry is landing on the wrong endpoint — stop and fix the pass, not the test.

- [ ] **Step 4: Update each failing assertion**

Add the new rows to the expected sets. Where a test spells out a complete metadata set for an endpoint, keep it complete. Do not relax an assertion to a subset check to make it pass — that is the pin those tests exist to be.

- [ ] **Step 5: Re-run the gate and the guards**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh --guards
```
Expected: exit 0 for both.

- [ ] **Step 6: Commit**

```bash
git add scripts/probes/cp32_listener_attributes* src/sextant/catalogs tests
git commit -m "feat(catalogs): the listener attributes a peer cares about — consumer group, selector, durable subscription, exclusivity"
```

---

## Task 10: The register, COVERAGE and the open issues

**Files:**
- Modify: `docs/java-kotlin-delivery-list.md`, `docs/COVERAGE.md`, `docs/open-issues.md`, `scripts/coverage_matrix.py`
- Test: `tests/architecture/test_feature_delivery.py`, `test_feature_intention.py`, `test_coverage_matrix.py`

**Interfaces:**
- Consumes: every task above.
- Produces: the closed Async row.

- [ ] **Step 1: Empty the Async column**

In the ```delivery``` block, remove `temporal-cadence` and `vertx-eventbus`; the Async cell becomes empty and the row closes. Remove their `ITEM_FRAMEWORKS` entries from `scripts/coverage_matrix.py` — an entry for an id the register no longer carries is data pointing at nothing. Update §0's "Moved to spec work" note for `temporal-cadence` to say where it landed, and §4's Category C to say it is empty.

- [ ] **Step 2: Write the COVERAGE rows**

Two new shipped framework lines in §5.12, each in the section's own column shape, each naming its catalogs, its probe, its measured versions and **its stated boundaries in words** — spec §2g and §3d are the source; do not paraphrase them into something vaguer. Update §§5.8–5.9 for the attributes Task 9 now records, and the `Temporal / Cadence` and `Vert.x` rows of the framework matrix.

Regenerate and check:

```bash
.venv/bin/python scripts/coverage_matrix.py --check
```

- [ ] **Step 3: File the open issues**

`docs/open-issues.md`, each in the file's own format: the linking-tier refinement rule (§1f); a Cadence re-measurement trigger (§1b); the programmatic worker's unread task queue with the mechanism it would need (§2g); a `MessageConsumer` handed across methods (§3d); `registerWorkflowImplementationFactory` (§2g). Cite each id from the catalog comment that states the boundary.

- [ ] **Step 4: Run the gate**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
```
Expected: exit 0 — `test_feature_delivery.py` is what proves the row actually closed.

- [ ] **Step 5: Commit**

```bash
git add docs scripts/coverage_matrix.py
git commit -m "docs(register): Group D closes — the Async row empties"
```

---

## Task 11: Delete the plan's workspace and finish the branch

- [ ] **Step 1: Full gate, guards included**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh --guards
```

- [ ] **Step 2: Amend the spec's §0a with anything implementation forced**

The 2026-09-21 spec's own convention: where the built code differs from the section as approved, the section carries a dated note and §0's table lists it with the task that forced it. Do this before the PR, not after.

- [ ] **Step 3: Use superpowers:finishing-a-development-branch**

Present the menu. **Do not merge without the user.**

---

## Self-Review

**Spec coverage.** §1a → Task 1. §1b → Task 5 (the catalogs name `io.temporal.*` only) and Task 10 (the COVERAGE words). §1c → Task 1. §1d → Tasks 3, 5, 7. §1e → Task 8. §1f → Task 4 (the mechanism) and Tasks 5, 8, 9 (its users). §2a–§2c → Task 3. §2d → Tasks 4, 5. §2e → Task 9. §2f → Task 5 Step 3, Task 7. §2g → Task 5 Step 1, Task 10 Step 3. §3a–§3d → Task 8. §4 → Tasks 6, 8. §5 → Tasks 3, 4, 7, 8, 9. §6 → Tasks 2, 8, 9. §7 → all. §8 → Task 10.

**Placeholders.** None: every word, key and row is spelled with its value. The one place a task says "or" is Task 3 Step 3's choice of how to widen `_PATH_FALLBACKS`, where both shapes are acceptable and the invariant that matters (an unknown word is refused) is stated.

**Type consistency.** `record_endpoint_attributes(workspace, catalogs)` is named identically in Task 4's creation, its pipeline call and the File Structure table. `metadata_from`'s triple — `{annotation, attribute, kind}` plus optional `absent_value` — is spelled identically in Tasks 4, 5, 8 and 9. The four catalog words are spelled identically in Tasks 3 and 5.

**Ordering.** Task 3 before 5 (the catalogs use the words); Task 4 before 5 and 8 (both declare `metadata_from`); Task 6 before 7 (the test reads the fixture); Task 9 after 4 and deliberately last of the code tasks, so that the one change which moves shipped output lands alone and its diff is readable.
