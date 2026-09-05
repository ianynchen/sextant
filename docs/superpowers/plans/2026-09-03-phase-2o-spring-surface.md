# Phase 2O — Spring Surface Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a stock Spring Boot service's whole inbound and outbound surface visible — gRPC, Spring Data REST's controller-less API, AMQP/Pulsar messaging, Actuator, servlets, scheduled work, error contracts and Integration channels — each honestly labelled or honestly refused.

**Architecture:** Five new engine styles and six extensions to shipped ones, all reading facts the extractor already emits plus two new capabilities. gRPC identity comes from either side independently (descriptor, or the `SERVICE_NAME` constants protoc compiles into module output) and merges on the real wire key. Non-wire families (scheduled work, error handlers) get their own tables rather than polluting the wire-true endpoints table. Three closed-set amendments are batched into one task; the three output-changing migrations are batched into one audited golden pass.

**Tech Stack:** Python 3.12+, DuckDB, Pydantic, PyYAML; the JVM extractor (Java/Kotlin, Gradle); protobuf + grpcio-tools (shipped 2G). **No new Python dependencies.**

**Spec:** [docs/superpowers/specs/2026-09-03-phase-2o-spring-surface-design.md](../specs/2026-09-03-phase-2o-spring-surface-design.md)

## Global Constraints

- **NFR-1 determinism**: every pass, reader and derivation is deterministic. **No network in tests, ever.**
- **DR-6 framework mirroring**: predict what the framework actually does, never our own approximation. Every mirrored algorithm is checkpoint-gated and leaves a **durable artifact**: a commit-pinned probe script plus a recorded expectation table the unit tests pin.
- **Unresolved-is-an-answer**: a value that cannot be read statically renders unresolved with its expression verbatim, never guessed.
- **Framework names live in catalogs only.** Engines stay neutral; new D02 vocabulary is neutral, declared, and guarded (validated against closed sets, cross-catalog conflicts refused).
- **NFR-5 closed sets**: three amendments this phase (protocols `amqp`/`pulsar`; `declared_shape.operation`; three `open_questions` kinds). Each is versioned, with the estate cost stated where incurred.
- **No version bumps** (the gate opens after 2J). **`uv.lock` is never committed.**
- **No new Python dependencies** (GUIDELINES §7).
- **COVERAGE.md is a per-task deliverable**: every task shipping a surface updates its rows in the same commit. The headline count is re-derived, never carried forward.
- **ONE audited golden pass** for the three output-changing migrations (Task 2). Later tasks ADD rows, which is not churn.
- Match existing patterns exactly (GUIDELINES §13.5). Do not refactor adjacent code (§3).

## Reference: mechanisms this plan touches

Read these before starting any task that names them:

| Mechanism | Location |
|---|---|
| Style→engine registry | `src/sextant/application/resolve/endpoints.py:140` (`_ENGINES`) |
| Runs-last styles | `endpoints.py:36` (`_RUNS_LAST`), `endpoints.py:45` (`_DERIVES_ROWS`) |
| Engine modules | `src/sextant/application/resolve/engines/` |
| `Catalog` model | `src/sextant/application/ports/catalogs.py:16` |
| Catalog YAML loader | `src/sextant/ingress/catalogs/yaml_source.py` |
| Closed sets | `src/sextant/domain/closed_sets.py` (`Protocol` at :56) |
| Open-questions ledger | `src/sextant/application/resolve/open_questions.py:26` (`QUESTIONS`) |
| Format ladder / rung 5 | `src/sextant/application/resolve/format.py` (`_json_default_marker` ~:445) |
| Shipped catalogs | `src/sextant/catalogs/*.yml` |

---

## Task 1: Closed-set amendments and the two behavioural probes

Foundation. Adding enum members changes no output until a catalog uses them, so this task is golden-neutral by construction — verify that.

**Files:**
- Modify: `src/sextant/domain/closed_sets.py` (`Protocol` gains `AMQP`, `PULSAR`)
- Modify: `src/sextant/application/resolve/open_questions.py:26` (`QUESTIONS` gains three kinds)
- Create: `scripts/probes/cp1_spring_paths.md` (expectation table + probe instructions)
- Create: `scripts/probes/cp6_boot_converter.md` (expectation table + probe instructions)
- Test: `tests/domain/test_closed_sets.py`, `tests/application/test_open_questions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Protocol.AMQP` (`"amqp"`), `Protocol.PULSAR` (`"pulsar"`); `QUESTIONS` containing `"channel_destination"`, `"service_identity"`, `"environment_divergence"`. Tasks 2, 5, 7, 9 depend on these.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_closed_sets.py
def test_amqp_and_pulsar_are_protocols():
    assert Protocol.AMQP == "amqp"
    assert Protocol.PULSAR == "pulsar"


def test_the_broker_families_are_distinct_protocols():
    # D00 §4's reason: linking gates on protocol equality (DR-5), and an AMQP
    # exchange can never be answered by a Pulsar topic.
    assert len({Protocol.AMQP, Protocol.PULSAR, Protocol.JMS, Protocol.KAFKA}) == 4
```

```python
# tests/application/test_open_questions.py
import pytest
from sextant.application.resolve.open_questions import QUESTIONS, record_open_questions


def test_the_three_new_kinds_are_accepted():
    for kind in ("channel_destination", "service_identity", "environment_divergence"):
        assert kind in QUESTIONS


def test_an_unknown_kind_is_still_refused_by_name(workspace):
    with pytest.raises(ValueError, match="not one of"):
        record_open_questions(
            workspace,
            [{"protocol": "http", "method": "GET", "path": "/x",
              "question": "invented_kind", "candidates": "[]", "evidence": "syntax"}],
        )
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/domain/test_closed_sets.py tests/application/test_open_questions.py -v`
Expected: FAIL — `AttributeError: AMQP`, and the kind assertions fail.

- [ ] **Step 3: Amend both closed sets**

In `closed_sets.py`, after `SSE`, following the batching precedent the `Protocol` enum's own comment sets (2H added three members in one edit because the set is closed):

```python
    # 2O design §3a. Two broker families in one edit, for the reason the 2H
    # block above states: the set is closed, so a member a later task needs
    # costs one line here and a schema change if it arrives alone. Each is its
    # own protocol because linking gates on protocol equality (DR-5) — an AMQP
    # exchange can never be answered by a Pulsar topic, and neither is a JMS
    # queue, which is why Stream's `rabbit: jms` stopgap migrates in Task 2.
    AMQP = "amqp"
    PULSAR = "pulsar"
```

In `open_questions.py`, replace the `QUESTIONS` tuple:

```python
# 2G design §6's closed question set, extended by 2O design §0. Adding a kind
# is a schema change (both the renderer and the export switch on it), which is
# why all three of this phase's arrive together.
QUESTIONS = (
    "payload_binding",
    "format_conflict",
    # 2O §5: a Spring Integration channel whose destination no configuration
    # key carries. Candidates: the channel name and the handler symbol.
    "channel_destination",
    # 2O §1b: a class a gRPC catalog flagged whose service identity could not
    # be read. Candidates: the class symbol and the reason.
    "service_identity",
    # 2O §2b: a config key whose value differs between environments where one
    # identity needs one value. Candidates: the key and the per-environment values.
    "environment_divergence",
)
```

- [ ] **Step 4: Run to verify they pass, and that nothing else moved**

Run: `uv run pytest tests/domain tests/application -q`
Expected: PASS, with the **same** pass count as before plus the new tests. Adding an unused enum member and an unused question kind must change no derivation.

- [ ] **Step 5: Write the CP-1 probe and its expectation table**

Create `scripts/probes/cp1_spring_paths.md`. It records how to run the probe and what was observed, so a later reader can re-run it rather than trust it:

````markdown
# CP-1 — Spring path combination (2O design §0a)

**Question.** Does Spring serve `@RequestMapping("users")` and `@RequestMapping("/users")`
at the same URL, how does class+method combination insert separators, and is a
trailing slash distinct?

**Version scope.** Framework 6+ / Boot 3+ (where `setUseTrailingSlashMatch` was
removed). Boot 2 / Framework 5 matched a trailing slash to the slashless mapping.

**How to run.** In a scratch directory, `spring init --boot-version=3.3.0 cp1 &&`
add a controller declaring each shape below, start it, and curl each candidate URL.
Record the observed status per URL in the table.

| Class mapping | Method mapping | URL served | Observed |
|---|---|---|---|
| (none) | `"users"` | `/users` | FILL FROM PROBE |
| (none) | `"/users"` | `/users` | FILL FROM PROBE |
| `"/api"` | `"users"` | `/api/users` | FILL FROM PROBE |
| `"/api/"` | `"/users"` | `/api/users` | FILL FROM PROBE |
| `"/api"` | `""` | `/api` | FILL FROM PROBE |
| (none) | `"/users/"` | `/users/` served, `/users` 404 | FILL FROM PROBE |

**Verdict.** Record CONFIRMED or FALSIFIED per row. A falsified row amends the
spec with a ledgered ruling before Task 2's seam is written.
````

Create `scripts/probes/cp6_boot_converter.md` with the same shape, asking: does
`jackson-databind` on the classpath of a Spring MVC app make JSON the response
format for a handler with no `produces` and no Jackson annotation? Record the
observed `Content-Type`.

- [ ] **Step 6: Run the probes and fill in both tables**

Run each probe against a live Boot app. Replace every `FILL FROM PROBE` with the
observation. **This is the durable artifact the Global Constraints require** — a
rule trusted on a run nobody can re-run is an assertion, not evidence.

- [ ] **Step 7: Update COVERAGE and commit**

Add no rows yet (nothing ships a surface in this task), but note in COVERAGE §4's
protocol list that `amqp` and `pulsar` now exist as protocols with catalogs arriving
in Task 7.

```bash
git add src/sextant/domain/closed_sets.py src/sextant/application/resolve/open_questions.py \
        scripts/probes/ tests/domain/test_closed_sets.py tests/application/test_open_questions.py \
        docs/COVERAGE.md
git commit -m "feat: the closed sets 2O amends, and the two behavioural probes"
```

---

## Task 2: The one output-changing migration — paths, protocols, formats

**The spec's hard constraint: these three land together in ONE audited golden pass**, because three separate passes let each hide in the others' noise. Do not split this task.

**Files:**
- Create: `src/sextant/domain/paths.py`
- Modify: every engine that mints an HTTP path identity — `engines/annotation_driven.py`, `engines/combinator.py`, `engines/single_call.py`, `engines/fluent.py` (call the seam at identity minting)
- Modify: `src/sextant/catalogs/spring-cloud-stream.yml` (`binder_protocols: rabbit: jms` → `amqp`)
- Modify: `src/sextant/application/resolve/format.py` (rung 5 marker read)
- Modify: `src/sextant/ingress/catalogs/yaml_source.py` (marker records gain `coordinate` form)
- Modify: `src/sextant/catalogs/spring-web.yml` (`json_default_markers` gains coordinate entries)
- Test: `tests/domain/test_paths.py`, `tests/application/test_format_ladder.py`, `tests/application/test_endpoints.py`
- Goldens: the audited update

**Interfaces:**
- Consumes: `Protocol.AMQP` (Task 1).
- Produces: `sextant.domain.paths.canonical_http_path(raw: str) -> str` — used by Task 6's derived routes and Task 7's servlet/actuator rows.

- [ ] **Step 1: Write the failing test for the seam**

```python
# tests/domain/test_paths.py
import pytest
from sextant.domain.paths import canonical_http_path, is_path_shaped


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("users", "/users"),          # CP-1: Spring serves this at /users
        ("/users", "/users"),
        ("/api//users", "/api/users"),  # one separator per boundary
        ("/users/", "/users/"),         # Framework 6: trailing slash is DISTINCT
        ("", "/"),
    ],
)
def test_canonicalization_matches_what_spring_serves(raw, expected):
    assert canonical_http_path(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://billing.example/orders",   # a whole address, not a path half
        "https://${billing.host}/orders",   # placeholder-bearing composition
        "${service.base}/orders",
    ],
)
def test_whole_addresses_are_not_path_shaped_and_are_never_prefixed(raw):
    # D02 keeps a composed address whole in `path` until the peer join resolves
    # it; prefixing one would publish a URL nobody serves.
    assert not is_path_shaped(raw)
    assert canonical_http_path(raw) == raw
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/domain/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: sextant.domain.paths`.

- [ ] **Step 3: Write the seam**

```python
# src/sextant/domain/paths.py
"""Canonical HTTP path identity (2O design §8).

**Why this exists.** `@RequestMapping("users")` and `@RequestMapping("/users")`
are the same URL to Spring (CP-1), and until this seam they were two endpoint
identities to us — which splits dedup, splits every path-keyed anchor, and
would split L's cross-service joins. Identity therefore becomes THE URL THE
FRAMEWORK SERVES, canonicalized in exactly one place so no engine can drift.

**What this deliberately does not touch.** A `path` holding a whole address or
a placeholder-bearing composition is not a path half — D02 keeps those whole
until the peer join splits them, and prefixing one fabricates a URL nobody
serves. `is_path_shaped` is the guard, and it is conservative: anything
carrying a scheme or a placeholder is left exactly as written.

**Scope.** HTTP only (SSE rows inherit it — `protocol_hint` reclassifies after
identity is minted). GraphQL paths are FIELD NAMES, not URLs; websocket is
deferred until a path-kind marker exists (2O §8).
"""

_SCHEME = "://"
_PLACEHOLDER_OPEN = "${"


def is_path_shaped(raw: str) -> bool:
    """False for anything that is a whole address rather than a path half."""
    return _SCHEME not in raw and _PLACEHOLDER_OPEN not in raw


def canonical_http_path(raw: str) -> str:
    """`raw` as the URL the framework serves, or `raw` untouched when it is
    not a path half. Trailing slashes are PRESERVED: Framework 6 removed
    trailing-slash matching, so `/users/` is a different URL from `/users`."""
    if not is_path_shaped(raw):
        return raw
    if raw == "":
        return "/"
    collapsed = raw
    while "//" in collapsed:
        collapsed = collapsed.replace("//", "/")
    return collapsed if collapsed.startswith("/") else "/" + collapsed
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/domain/test_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Call the seam from every HTTP identity-minting site**

In each of `annotation_driven.py`, `combinator.py`, `single_call.py`, `fluent.py`, find where the row's `path` is finalized and wrap it — only when the catalog's protocol is `http`:

```python
from sextant.domain.paths import canonical_http_path

# at the point the path is finalized, before the row is written:
path = canonical_http_path(path) if catalog.protocol == "http" else path
```

Add a comment at the first such site pointing to `domain/paths.py` for the reasoning; the rest need none.

- [ ] **Step 6: Migrate the Stream binder protocol**

In `src/sextant/catalogs/spring-cloud-stream.yml`, change `rabbit: jms` to `rabbit: amqp` and replace the stopgap comment:

```yaml
binder_protocols:
  kafka: kafka
  # 2O design §3a: `amqp` is a real protocol now, so the binder names it. The
  # stopgap `jms` was chosen when no AMQP member existed, and leaving it would
  # put a Stream producer and a `@RabbitListener` consumer (Task 7) on
  # different protocols permanently — DR-5 gates linking on protocol equality.
  rabbit: amqp
```

- [ ] **Step 7: Widen rung 5's marker read**

The doc says rung 5's markers are package families whose **presence anywhere in the module** is evidence; the code reads annotation fqns only. Make the code match the documentation, and let a marker also be a classpath coordinate.

In `yaml_source.py`, keep `json_default_markers` a flat list but allow either form:

```python
json_default_markers=raw.get("json_default_markers", []),
```

Each entry is either a bare string (a package family, as today) or a mapping `{coordinate: "group:artifact"}`. In `format.py`, extend `_json_default_marker` to check, in order: annotations (as today), any referenced fqn in the module, then recorded classpath coordinates. Keep the "first marker that answers wins" contract and the set-union merge across catalogs — presence markers cannot conflict, which is why union is safe.

Add to `spring-web.yml`'s `json_default_markers`:

```yaml
  # 2O design §7 (CP-6): Boot auto-configures Jackson's converter from the
  # jar's mere presence, so a module carrying it answers `json` even with no
  # annotation anywhere. A coordinate marker, not a package family, because
  # that is the evidence Boot itself acts on.
  - coordinate: com.fasterxml.jackson.core:jackson-databind
```

- [ ] **Step 8: Run the suite and READ the golden diff line by line**

Run: `uv run pytest -q`
Expected: FAIL, in the goldens only, with three distinguishable classes of change:
1. paths gaining a leading `/` where a catalog wrote a slashless one,
2. Stream rabbit rows moving `jms` → `amqp`,
3. formats moving `unresolved` → `json (narrowed)` in Jackson-bearing modules.

**Audit every changed line and classify it into one of those three.** A change fitting none of them is a defect this task introduced — stop and investigate rather than accepting the golden.

- [ ] **Step 9: Regenerate goldens, re-run, and record the audit**

Regenerate the goldens, re-run the full suite green, and write the audit summary (counts per class, and any line that needed investigation) into the commit message.

- [ ] **Step 10: Update the four consequences and COVERAGE, then commit**

Add to the release-notes section (or create one) the four consequences §8 names: goldens; curation/view overlays naming old endpoint ids are **rejected whole** by M01's rule; 2N enrichment overlays anchored on old paths go **stale** and are dropped at render, with re-enrich as the remedy; `open_questions` snapshots re-derive. Add the D01 amendment note and the D02 overturn note (scoped to `http`; STOMP, websocket and messaging composition keep the old rule). Update COVERAGE's format-regime rows for the widened rung 5.

```bash
git add -A
git commit -m "fix: one migration, three faces — served paths, the amqp binder, presence-evidence json"
```

---

## Task 3: Extractor capabilities — generic superinterfaces, and the gRPC probes

**Files:**
- Modify: the extractor's class-symbol emission (Java/Kotlin under `extractor-jvm/`), adding generic superinterface references
- Modify: `src/sextant/domain/facts.py` (the class symbol fact's new field)
- Create: `scripts/probes/cp3_cp8_grpc_facts.md`
- Test: `tests/ingress/test_extractor_capabilities.py` (match the existing extractor test file's name and style)

**Interfaces:**
- Consumes: nothing.
- Produces: the class-symbol fact carries `generic_interfaces` — the parameterized superinterface references, erased symbol plus type arguments. Task 6 reads it for the entity type.

- [ ] **Step 1: Write the failing test**

```python
def test_a_generic_superinterface_records_its_type_arguments(extracted_fixture):
    # D00 records generic SUPERCLASS references and erases interfaces, so a
    # repository interface's entity type was unreadable. Data REST cannot
    # derive a route without it (2O design §2a), which is why this capability
    # is certain work rather than a probe.
    fact = extracted_fixture.class_symbol("com.example.orders.OrderRepository")
    assert fact.generic_interfaces == (
        "org.springframework.data.repository.CrudRepository<com.example.orders.Order, java.lang.Long>",
    )


def test_a_non_generic_interface_carries_no_generic_reference(extracted_fixture):
    # Symmetry with D00's generic-superclass rule: nothing generic, nothing
    # captured — the erased `interfaces` list already states the relationship.
    fact = extracted_fixture.class_symbol("com.example.orders.PlainService")
    assert fact.generic_interfaces == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/ingress/test_extractor_capabilities.py -v`
Expected: FAIL — `AttributeError: generic_interfaces`.

- [ ] **Step 3: Emit the capability**

Add capability **9.13** to the extractor's capability list (the extractor declares its capabilities; follow the existing 9.x entries exactly). Emit the parameterized superinterface signature the same way the generic superclass reference is already emitted — same signature reader, applied to the interface list. Add the field to the Python fact model with a docstring stating why it exists and that it mirrors D00's generic-superclass rule.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/ingress -v`
Expected: PASS.

- [ ] **Step 5: Run the CP-3 and CP-8 probes**

Create `scripts/probes/cp3_cp8_grpc_facts.md` recording, against a compiled gRPC fixture:

- **CP-3**: is a plain (non-generic) `extends` relationship present in the fact stream? (2G observed it absent, matching protobuf hierarchy via `implements` instead — this probe settles it.) If absent, capability **9.13b** emits it and this task ships that too.
- **CP-8(a)**: does the generated `<Service>Grpc` class appear in module facts?
- **CP-8(b)**: is its `SERVICE_NAME` constant readable as a constant fact, and is its value `<protoPackage>.<Service>`?
- **CP-8(c)**: is the user class's `extends` edge to `<Service>ImplBase` visible?
- **CP-8(d)**: are the wire method names readable as constants (grpc-java builds each `MethodDescriptor` via `generateFullMethodName(SERVICE_NAME, "GetOrder")`)?

Fill in every observation. **CP-8(b) and (d) decide whether Task 5 can publish full identities from bytecode alone**; a falsification there sends Task 5 to its unresolved branch and must be ledgered.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: extractor 9.13 — generic superinterface references, and the gRPC fact probes"
```

---

## Task 4: gRPC descriptors — the operation record and the schema read

**Files:**
- Modify: `src/sextant/domain/facts.py` (`DeclaredShapeFact` gains the optional `operation` sub-record)
- Modify: the descriptor interpreter (the module reading `FileDescriptorSet`s, shipped 2G)
- Modify: `src/sextant/application/resolve/engines/schema_operations.py`
- Create: `src/sextant/catalogs/grpc-schema.yml`
- Test: `tests/application/test_schema_operations.py`, `tests/interpretation/` descriptor tests (match existing names)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `declared_shape` facts with `role="operation"` and `operation={input_ref, output_ref, client_streaming, server_streaming}`; endpoint rows at `(grpc, NULL, "<protoPackage>.<Service>/<Method>")`. Task 5 merges against these identities.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_descriptor_service_yields_one_operation_shape_per_method(interpreted):
    ops = interpreted.declared_shapes(role="operation")
    assert [o.schema_name for o in ops] == [
        "orders.v1.OrderService/GetOrder",
        "orders.v1.OrderService/StreamOrders",
    ]


def test_the_operation_record_carries_streaming_and_both_refs(interpreted):
    stream = interpreted.declared_shape("orders.v1.OrderService/StreamOrders")
    assert stream.operation.server_streaming is True
    assert stream.operation.client_streaming is False
    # The refs join to the SAME descriptor's message shapes — an
    # intra-descriptor join, never a guess across universes.
    assert stream.operation.input_ref == "orders.v1.OrderRequest"
    assert stream.operation.output_ref == "orders.v1.OrderView"


def test_grpc_operations_derive_verbless_endpoints_at_the_wire_identity(resolved):
    row = resolved.endpoint(protocol="grpc", path="orders.v1.OrderService/GetOrder")
    assert row["method"] is None          # gRPC is verbless, like every non-HTTP protocol
    assert row["handler"] is None         # the descriptor names no code
    assert row["format"] == "protobuf"    # rung 1, format_fixed
    assert row["evidence"] == "compiler"  # an EMBEDDED descriptor's own tier
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/application/test_schema_operations.py -v`
Expected: FAIL — no operation shapes are produced.

- [ ] **Step 3: Add the operation sub-record to the fact model**

```python
@dataclass(frozen=True)
class OperationRecord:
    """What a service operation declares beyond its name (2O design §1a).

    Optional on `DeclaredShapeFact`, populated only when `role == "operation"`.
    Added for gRPC, whose methods carry a request AND a response type plus the
    two streaming flags; 2I's SOAP operations may fill the same record later —
    today their output side is honestly NULL and nothing changes for them.
    """

    input_ref: str | None
    output_ref: str | None
    client_streaming: bool
    server_streaming: bool
```

Bump `fact_schema_version` and record the estate cost (re-analysis of existing workspaces, accepted pre-gate) in the D00 amendment note.

- [ ] **Step 4: Read services in the descriptor interpreter**

For each `service` in a `FileDescriptorSet`, emit one `declared_shape` per method:
`schema_name = f"{file.package}.{service.name}/{method.name}"`, `role="operation"`,
the record filled from the method's own descriptor fields, and input/output refs
as the descriptor's own fully-qualified type names (strip the leading `.`).
Carry the shape's evidence tier from the descriptor's origin exactly as the
existing message read does.

- [ ] **Step 5: Extend the `schema_operations` role branch**

The engine's `role: operation` branch already derives one row per shape at the
shape's own `schema_name`. Extend it to carry streaming into a typed 2M Detail
(`unary | server-streaming | client-streaming | bidi`) — **not** a new endpoints
column. Everything else in that branch is already correct for gRPC.

Create `src/sextant/catalogs/grpc-schema.yml` on `style: schema_operations`,
`protocol: grpc`, `direction: inbound`, with:

```yaml
format_fixed:
  # 2G shipped rung 1; gRPC is the third protocol to own it (after graphql:
  # json and soap: xml) and the one COVERAGE calls the only certain cell —
  # protobuf, always, fixed by the protocol itself.
  grpc: protobuf
```

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest tests/application tests/interpretation -q`
Expected: PASS.

- [ ] **Step 7: Add the fixture, update COVERAGE, commit**

Add `orders.proto` to the orders-service fixture with a unary and a server-streaming
method, compiled by the fixture build. Update COVERAGE §5.7's gRPC rows for the
schema half and re-derive the headline count.

```bash
git add -A
git commit -m "feat: descriptor services become operations — gRPC's identity layer"
```

---

## Task 5: gRPC bytecode — `supertype_derived`, `injected_client`, and the fence

**Files:**
- Create: `src/sextant/application/resolve/engines/supertype_derived.py`
- Create: `src/sextant/application/resolve/engines/injected_client.py`
- Create: `src/sextant/catalogs/grpc-java.yml`, `grpc-spring.yml`, `grpc-net-devh.yml`
- Modify: `src/sextant/application/resolve/endpoints.py` (`_ENGINES` gains both styles)
- Test: `tests/application/test_supertype_derived.py`, `tests/application/test_injected_client.py`

**Interfaces:**
- Consumes: Task 3's extends/constant facts (CP-8), Task 4's operation identities, Task 1's `service_identity` question kind.
- Produces: inbound rows per implemented method; outbound rows per injected stub at service level.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_implementation_derives_one_row_per_overridden_method(resolved):
    rows = resolved.endpoints(protocol="grpc", direction="inbound")
    assert [r["path"] for r in rows] == ["orders.v1.OrderService/GetOrder"]
    # The identity comes from the generated class's SERVICE_NAME constant and
    # its wire method-name constant — never from casing the Java method name,
    # which is not invertible (proto `get_order` and `getOrder` both compile
    # to Java `getOrder`).
    assert rows[0]["handler"] == "com.example.orders.OrderServiceImpl#getOrder"


def test_the_bytecode_row_merges_with_the_descriptor_row(resolved):
    # Both sides derive the same (protocol, direction, method, path) by
    # construction, so D01's only join collapses them — the descriptor
    # contributes the method inventory, the bytecode the handler.
    rows = resolved.endpoints(protocol="grpc", path="orders.v1.OrderService/GetOrder")
    assert len(rows) == 1
    assert rows[0]["handler"] is not None
    assert rows[0]["format"] == "protobuf"


def test_an_injected_stub_derives_one_service_level_outbound_row(resolved):
    rows = resolved.endpoints(protocol="grpc", direction="outbound")
    assert len(rows) == 1
    assert rows[0]["path"] == "billing.v1.BillingService"   # service level
    assert rows[0]["method"] is None                        # not per-method until 2Q


def test_the_fence_refuses_an_outbound_row_for_a_service_this_module_implements(resolved):
    # Stated by SYMBOL NAME, not identity: a module class whose extends target
    # shares an outer class with the stub's type is implementing what it would
    # otherwise appear to call. Works even when a published jar withholds the
    # SERVICE_NAME constant.
    assert not resolved.endpoints(
        protocol="grpc", direction="outbound", path="orders.v1.OrderService"
    )


def test_an_unreadable_identity_files_a_question_rather_than_guessing(resolved):
    q = resolved.open_questions(question="service_identity")
    assert len(q) == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/application/test_supertype_derived.py tests/application/test_injected_client.py -v`
Expected: FAIL — both styles have no engine (`_engine_for` refuses the catalogs).

- [ ] **Step 3: Write `supertype_derived`**

Match the shape of `interface_implementation.py` exactly (module docstring stating what it reads, what it derives, and what it refuses; a `_REQUIRED_MATCHES` tuple). Its `matches` block:

```yaml
style: supertype_derived
matches:
  supertype_marker:
    constant: SERVICE_NAME
  members: overridden_public_methods
```

The match is evidence-shaped: a class whose extends target is itself in the module's facts and declares the marker constant. Service identity is that constant's **value verbatim**; the wire method name comes from the generated class's own method-name constants. Derive one row per overridden public method. When the constants are unreadable **and** no descriptor covers the service, derive with the path unresolved (expression = the supertype fqn verbatim) and file a `service_identity` question naming both absent sources.

- [ ] **Step 4: Write `injected_client`**

```yaml
style: injected_client
matches:
  field_annotation: net.devh.boot.grpc.client.inject.GrpcClient
  identity_marker:
    constant: SERVICE_NAME
```

One row per injected stub at the **service** level (`method` NULL, path from the stub type's outer class constant). Implement the fence as a symbol-name test: skip the row when any module class's `extends` target shares an outer class with the stub's type. Document in the module docstring that a service-level outbound row **links to nothing** until 2Q makes it per-method, because DR-5 matches identities exactly.

- [ ] **Step 5: Register both styles**

In `endpoints.py`, add both to `_ENGINES`. Neither belongs in `_RUNS_LAST` — both derive rows from their own evidence rather than enriching others'.

- [ ] **Step 6: Write the three catalogs**

`grpc-java.yml` (the `supertype_derived` core), `grpc-spring.yml` and `grpc-net-devh.yml` (annotation corroboration rows on `annotation_driven`, plus the `@GrpcClient` `injected_client` rows). Comment in `grpc-spring.yml` that Spring gRPC's `@GrpcService` is **optional** — it exposes any `BindableService` bean — so the supertype match is the reliable one and the annotation only corroborates.

- [ ] **Step 7: Run to verify they pass**

Run: `uv run pytest tests/application -q`
Expected: PASS.

- [ ] **Step 8: Fixture, COVERAGE, commit**

Add to the fixture: a service implementation extending the generated `ImplBase`, and a `@GrpcClient`-injected stub for a *different* service. Update COVERAGE §5.7 (Java rows shipped; FR-3 closed for the surfaces this ships) and add boundary rows for published-stub jars, unannotated Spring gRPC on published stubs, and bare `newBlockingStub`.

```bash
git add -A
git commit -m "feat: gRPC implementations and injected clients, fenced by symbol name"
```

---

## Task 6: Spring Data REST — `derived_resource`

**Files:**
- Create: `src/sextant/application/resolve/engines/derived_resource.py`
- Create: `src/sextant/domain/pluralize.py`
- Create: `src/sextant/catalogs/spring-data-rest.yml`
- Modify: `src/sextant/application/resolve/endpoints.py` (`_ENGINES`, ordering)
- Test: `tests/domain/test_pluralize.py`, `tests/application/test_derived_resource.py`

**Interfaces:**
- Consumes: Task 3's `generic_interfaces`, Task 2's `canonical_http_path`, Task 1's `environment_divergence` kind.
- Produces: derived CRUD + search routes.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_pluralize.py — pinned against CP-2's committed table
@pytest.mark.parametrize(
    "singular, plural",
    [("order", "orders"), ("category", "categories"), ("box", "boxes"),
     ("person", "people"), ("child", "children"), ("sheep", "sheep")],
)
def test_the_port_matches_evo_inflector(singular, plural):
    assert pluralize(singular) == plural
```

```python
# tests/application/test_derived_resource.py
def test_an_exported_repository_derives_the_full_route_set(resolved):
    paths = {(r["method"], r["path"]) for r in resolved.endpoints(catalog_id="spring-data-rest")}
    assert paths == {
        ("GET", "/orders"), ("POST", "/orders"),
        ("GET", "/orders/{id}"), ("PUT", "/orders/{id}"),
        ("PATCH", "/orders/{id}"), ("DELETE", "/orders/{id}"),
        ("GET", "/orders/search/findByStatus"),
    }


def test_exported_false_removes_the_repository_entirely(resolved):
    assert not resolved.endpoints(path="/secrets")


def test_a_predicted_route_never_displaces_an_observed_controller_row(resolved):
    # insert-if-absent, and this style runs after every observed-endpoint style
    row = resolved.endpoint(method="GET", path="/orders")
    assert row["handler"] is not None   # the real controller's, not NULL


def test_derived_rows_publish_at_full_confidence_with_declared_evidence(resolved):
    row = resolved.endpoint(method="GET", path="/orders/search/findByStatus")
    assert row["resolution"] == "resolved"
    assert row["evidence"] == "declared"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/domain/test_pluralize.py tests/application/test_derived_resource.py -v`
Expected: FAIL — no `pluralize` module, no engine for the style.

- [ ] **Step 3: Port the pluralizer**

`src/sextant/domain/pluralize.py`, carrying an **Apache-2.0 attribution header naming Evo Inflector** (a port of its rule set is a derivative of it), the full published rule list, and a docstring stating that Spring HATEOAS selects this provider by classpath presence — so the caller decides whether to use it.

- [ ] **Step 4: Write the engine**

Detection: an interface whose direct superinterfaces match the catalog's enumerated Spring Data list, or reach it through interfaces **declared in this module** (a within-module closure walk; chains through other jars are a stated boundary). Entity/ID from `generic_interfaces`. Base path from `path=` when given, else the CP-2 rule: pluralize when the recorded classpath carries `org.atteo:evo-inflector`, else the uncapitalized simple name verbatim. Emit the six-route table plus one search route per exported query method. Honor `exported=false` at both levels. Read `spring.data.rest.base-path` from `resolved_config` **without** declaring it in `requires` (a config-less run must still derive), and file an `environment_divergence` question when it differs across environments.

- [ ] **Step 5: Register with the right ordering**

Add to `_ENGINES`, and to `_RUNS_LAST` — it must run after every observed-endpoint style so insert-if-absent keeps the real controller. Add to `_DERIVES_ROWS` if the split applies. Add an ordering test pinning the position.

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest tests/domain tests/application -q`
Expected: PASS.

- [ ] **Step 7: Fixture, media, COVERAGE, commit**

Fixture: one exported repository with a query method, one `exported=false`. Implement D02's specified-but-unused `default_produces` on this catalog (`application/hal+json`) and add `application/hal+json → json` to the shared `media_formats` table. Flip COVERAGE's `@RepositoryRestResource` row from **C** and add the boundary rows (projections, excerpts, HAL affordances, QueryDSL).

```bash
git add -A
git commit -m "feat: the API nobody wrote a controller for — Spring Data REST routes"
```

---

## Task 7: Messaging and annotation catalogs

**Rewritten 2026-09-04** after the pre-dispatch audit found three blockers, and
after §9 was dropped and servlets resized. Servlets are **Task 7b** below —
they are engine work, not a catalog file.

**Files:**
- Create: `src/sextant/catalogs/spring-rabbit.yml` (annotation_driven / amqp / inbound), `spring-pulsar.yml` (annotation_driven / pulsar / inbound), `spring-rabbit-template.yml` (single_call / amqp / outbound), `spring-sqs-legacy.yml`, `spring-actuator.yml`
- Create: `scripts/probes/cp5_actuator_paths.md` + its harness
- Modify: `src/sextant/application/resolve/engines/single_call.py` (`address_arg_2`), `engines/annotation_driven.py` (`path_prefix`), `src/sextant/storage/duckdb/derive_endpoints.sql` (the `path_prefix` bind; the unresolved-path gate)
- Test: `tests/application/test_call_engines.py`, `tests/application/test_endpoints.py`

**Three corrections the audit forced — do not revert to the old text:**

1. **THREE catalogs, not one.** A `Catalog` holds exactly one `style`, one
   `protocol`, one `direction` (`application/ports/catalogs.py:18-20`, bound at
   `ingress/catalogs/yaml_source.py:39-41`), and `derive_endpoints` resolves one
   engine per catalog (`resolve/endpoints.py:82`). The shipped convention is one
   file per triple — `spring-kafka.yml` + `spring-kafka-template.yml`.
2. **`yaml_source.py` is the WRONG file for both new keys.** `address_arg_2`
   sits under `matches.methods[]` beside `channel_arg`/`url_arg`, validated in
   `single_call.py` (`_IDENTITY_REQUIRED`, `:57`); `path_prefix` sits under
   `matches.mapping`, validated in `annotation_driven._validate_naming`
   (`:383`) and bound into the SQL. `yaml_source.py` passes `matches` through
   opaquely (`:43`).
3. **Placeholders are PRESERVED, not resolved.** 2F's ladder is a call-site
   mechanism (`engines/single_call.py:143,279,705`, `engines/fluent.py:161,489`
   — `annotation_driven` never calls it), and its product is the expression, not
   a value. `derive_endpoints.sql:629-631` already leaves a composed path
   containing `${` untouched.

- [ ] **Step 0: CP-5 first (spec §12, R7)**

Run CP-5 against a live Actuator app and commit `scripts/probes/cp5_actuator_paths.md`
plus its harness. Establish: `@Endpoint(id="x")` serves under `/actuator/x`;
`@ReadOperation`→GET, `@WriteOperation`→POST, `@DeleteOperation`→DELETE; and
**state the Boot version probed** (§5.4 — the base-path property name and the
`/actuator` default are version-scoped). `@Selector` path segments are a stated
boundary; do not probe them.

If the probe cannot run live, report UNVERIFIED per R5 — never fabricate a table.

- [ ] **Step 1: the unresolved-path gate (do this before any catalog)**

`derive_endpoints.sql:648` hardcodes `'resolved' AS resolution` for every
annotation-derived row, so a SpEL destination would publish a
confidently-wrong address at full confidence — the failure
`derive_endpoints.sql:386-390`'s own guards exist to prevent, and a §8
violation. Add a path-shape gate: a path containing `#{` or `${` publishes
`unresolved`, carrying the expression verbatim.

Write the failing test first, in `tests/application/test_endpoints.py`.

- [ ] **Step 2: `address_arg_2` in `single_call`**

AMQP's wire identity is the exchange+routing-key PAIR, which the one-address
contract refuses (`single_call.py:225`). Add the optional second capture plus a
catalog-declared join format; identity renders `exchange/routingKey`. An
overload without an exchange (the default exchange) captures the routing key
alone — state that in the catalog comment per §9, naming what would falsify it.

- [ ] **Step 3: `path_prefix` in `annotation_driven`**

A catalog-declared constant prefix, validated in `_validate_naming` and bound
into `derive_endpoints.sql`. Guard it the way every other naming key is guarded.

- [ ] **Step 4: the five catalogs**

`spring-rabbit.yml` (`@RabbitListener(queues=…)`, amqp/inbound),
`spring-pulsar.yml` (`@PulsarListener`, pulsar/inbound),
`spring-rabbit-template.yml` (`RabbitTemplate.convertAndSend`, amqp/outbound,
using `address_arg_2`), `spring-sqs-legacy.yml` (the two older `@SqsListener`
spellings — pure data), `spring-actuator.yml` (`@Endpoint` + operation
annotations, `path_prefix: /actuator`).

**Stated boundaries, each with what would falsify it (§9):** `bindings=` nested
annotations are readable only from capability 9.16 onward and no catalog reads
them yet; SpEL `#{…}` has no reader and none is built; `@Selector` segments
cannot be expressed by `mapping`; `management.endpoints.web.base-path` has **no
reader** — `annotation_driven` never touches `resolved_config` (only
`config_join.py:528` and `derived_resource.py:578` do), so the override is a
boundary in this task, not a feature.

- [ ] **Step 5: near-miss tests (§10) — required, one per matcher**

Each asserts **nothing** is produced: a `@RabbitListener`-shaped method on a
class carrying no such annotation; a `convertAndSend` on an owner that is not a
`RabbitTemplate`; an `@Endpoint` class with no operation annotation; a
`@WebFilter` (proving the stated boundary holds).

- [ ] **Step 6: COVERAGE, then commit**

Flip the A-tier rows this ships and add every boundary row above. Commit with an
explicit pathspec (R18). Report states `Deviations: none` or the list (§1.1).

---

## Task 7b: Servlets — `@WebServlet` is engine work

**New task, 2026-09-04.** §3b assumed a catalog file; the audit proved
`annotation_driven` cannot derive it, and the plan previously proposed cutting
servlets entirely. The user ruled: keep them, size them honestly.

**Files:**
- Create: a new engine style (name it for the evidence shape, not the framework), registered in `resolve/endpoints.py`'s `_ENGINES`
- Create: `src/sextant/catalogs/jakarta-servlet.yml`
- Create: `scripts/probes/cp9_servlet_shapes.md` + harness
- Test: a new `tests/application/test_<style>.py`

**Why not `annotation_driven`:** `@WebServlet` carries the address at TYPE
level, and that engine's derivation joins only method symbols — it says so
itself at `derive_endpoints.sql:398-400`. The `members: public_methods` +
`path_fallback` route (the only alternative) would compose `/legacy/*` + `/` +
`doGet`, fabricating four URLs per servlet, none served. That is §8.

**The framework's own rule (§8.1 rule 1), to mirror exactly:** address from the
type annotation; verb from the overridden `doXxx` method name; evidence being
the class extending `HttpServlet`.

- [ ] **Step 0: CP-9 first — measure before building (§8.1)**

Probe and commit: does `@WebServlet` reach the facts as a type-level annotation
with its args? Are array-valued `urlPatterns` readable? Is `value` distinguishable
from `urlPatterns`? Is `protected` visibility recorded? (It is —
`workspace.py:163-168` projects it — confirm rather than assume.) State the
container and servlet-API versions probed.

**Also settle by measurement, not assumption:** does `HttpServlet` serve HEAD and
OPTIONS implicitly from `doGet`? If it does, §8.1 rule 4 says we claim what the
framework serves — but decide it on evidence and record the ruling.

- [ ] **Step 1: the style, with a member selector that admits `protected`**

`supertype_derived` is the nearest shape but filters `visibility == "public"`
(`supertype_derived.py:328`), and servlet handlers are `protected`. Either widen
that selector or write a sibling — your judgement, stated in the report.

- [ ] **Step 2: the four shapes correctness requires**

Multiple `urlPatterns` are multiple endpoints. `value` and `urlPatterns` are
aliases. A class overriding `service()` bypasses `doXxx` dispatch entirely — the
verb map does not apply, so derive nothing rather than a wrong verb set. A
`GenericServlet` subclass has no HTTP verb semantics at all.

- [ ] **Step 3: near-miss tests (§10)**

Nothing produced for: a class extending `HttpServlet` with no `@WebServlet`; a
`@WebServlet` class overriding `service()` (per Step 2); a `GenericServlet`
subclass.

- [ ] **Step 4: COVERAGE and commit**

`web.xml` and programmatic `ServletContext.addServlet` are the other two
registration routes — **stated boundaries**, with the annotation named as one of
three (§8.1 rule 3).

---

## Task 8: The two non-wire families

**File list corrected 2026-09-04** — the original named four documentation
touches and omitted six code registrations per family.

**Files:**
- Create: `engines/scheduled_work.py`, `engines/error_advice.py`; `catalogs/spring-scheduling.yml`, `catalogs/spring-advice.yml`
- Create: two derive SQL + **two reset SQL**
- Modify: `storage/duckdb/schema.sql` (two tables); `storage/duckdb/workspace.py` (`_NAMED_QUERIES`, `_EXPORT_QUERIES`, `_EXPORTED_TABLES`, the derive map); `resolve/pipeline.py` (`ResolveReport` fields **and the two resets**); `application/stages/analyze.py`; `resolve/endpoints.py` (`_ENGINES`); `egress/render/document.py` (two sections); `docs/components/D01-graph-schema.md`, `D06-bundle-format.md`
- Test: `tests/application/test_scheduled_work.py`, `test_error_advice.py`, plus render/export tests

- [ ] **Step 1: the resets go in `pipeline.py`, not the engines**

`derive_endpoints` empties `endpoints` ONCE, outside its per-catalog loop, and
states why (`resolve/endpoints.py:83-88`): a per-catalog rebuild leaves only
whichever ran last. `reset_open_questions` follows the same pattern at
`pipeline.py:62-67`. §4a promises "Quartz: later catalog, same table", which is
exactly the two-catalogs-one-table case that makes this load-bearing.

- [ ] **Step 2: `scheduled_work`**

`@Scheduled` (and `@Schedules`, now readable via capability 9.16 — verify it
reads before relying on it, §5.3). Handler symbol, trigger kind
(`cron | fixedRate | fixedDelay`), expression **verbatim**.

**The docstring must not cite `root_kind` or `trace_of` as existing.** Both are
documented and appear NOWHERE in `src/` (register #7, #11). Write instead:
scheduled handlers are deliberately not endpoints; D00 documents a `root_kind`
set and D01 a `trace_of` walk, neither of which exists today; **this omission
becomes wrong the moment a `root_kind` producer ships** (§9).

- [ ] **Step 3: `error_advice`**

`@ControllerAdvice`, `@RestControllerAdvice`, `@ExceptionHandler` (including
handlers inside controllers, scoped to that controller per Spring's own rule).
Advice class, scope attributes verbatim, exception types (annotation value, else
the parameter type), status from `@ResponseStatus`, **and the response shape
symbol where the return type names one** — spec §4b requires it and the original
plan omitted it.

**Boundaries:** a status computed inside a `ResponseEntity` body is `fluent`
territory and out of scope; `@ResponseStatus` on an exception class is readable
only when that class is in this module's own facts.

- [ ] **Step 4: near-miss tests (§10)**

Nothing produced for: a method named `sweep()` with no `@Scheduled`; an
`@ExceptionHandler` on a class that is neither `@ControllerAdvice` nor a
controller; a `@ControllerAdvice` class with no handler method. (A `status is
None` assertion is a boundary-value test, not a near-miss — §10 distinguishes
them.)

- [ ] **Step 5: byte-identity, COVERAGE, commit**

Extend the byte-identity e2e to both new tables' exports (NFR-1).

---

## Task 9: Spring Integration — the channel join, on measured evidence

**Rewritten 2026-09-04 from `scripts/probes/spring-integration-destinations.md`.**
Every earlier version of this task was built on a guess; the probe replaced all
of them, and capability 9.15 shipped as a result.

**Files:**
- Modify: `engines/config_join.py` (a second binding source)
- Create: `src/sextant/catalogs/spring-integration.yml`
- Test: `tests/application/test_config_join.py`

**What the probe established** (cite it, do not re-derive): the channel join is
REAL in both shapes — `setOutputChannelName("amqpInputChannel")` as a call-site
string argument and `@ServiceActivator(inputChannel="amqpInputChannel")` as an
annotation argument, **the same literal on both sides**. The DSL shape
reconstructs through within-method `result` ↔ `receiver` joins. Destinations for
varargs APIs were unreadable until 9.15; **verify 9.15's elements now reach this
join before designing around them** (§5.3).

- [ ] **Step 1: `from: annotation_value` in `config_join`**

Today the engine refuses anything but `bean_name` (`config_join.py:592-597`,
`_BEAN_NAME` at `:51`) and reads one input, `resolved_config` (`:528`). Add the
second binding source; **the single input is unchanged**.

- [ ] **Step 2: questions ride the `gaps()` seam, never a write inside `run`**

`reset_open_questions` runs at `pipeline.py:62-67`, AFTER `derive_endpoints` at
`:55` — a row written during `run` is **erased**. The three shipped writers
(`format.py`, `shapes/parse_binding.py`, `service_identity.py`) all run after the
reset. Register `config_join.gaps` in `_GAP_ENGINES`
(`resolve/service_identity.py:34-38`).

- [ ] **Step 3: the built-in ships channel enumeration plus questions**

Spring Integration defines no standard configuration key for a destination.
Where 9.15 now makes one readable, derive the wire row; where it is genuinely
not statically knowable, file a `channel_destination` open question carrying the
channel name and handler symbol — **the enrichment seat's inbox** (2K §8),
which is how "we cannot see it" becomes a route to an answer rather than a dead
end. Never a fabricated wire, never `peer: in-process` (the schema refuses it).

**Watch the candidates shape:** every shipped question kind uses a list of
dicts, and `cf3f841`'s renderer arms expect that. An earlier draft of this plan
showed a flat string array — do not follow it.

- [ ] **Step 4: the Task 2 carry**

`config_join.py:451` writes its `direction` column from a per-suffix value that
is neither `catalog.direction` nor a literal — the same shape as the
`single_call` bug Task 2 fixed. Unreachable while its catalogs are kafka-only;
this task makes the engine reachable from a new direction, so fix it here.

- [ ] **Step 5: near-miss (§10), COVERAGE, commit**

An `@ServiceActivator` whose channel no key template covers produces **no
endpoint row and no ghost row** — only the question. DSL flows
(`IntegrationFlow`) and XML config are stated boundaries; XML contributes zero
facts (probe-confirmed).

---

## Task 10: The `@HttpExchange` direction flip

**Rewritten 2026-09-04** — ruling R12 voided its Step 4, and CP-7's original
question was unanswerable.

**Files:**
- Modify: `engines/annotation_driven.py` (`resolves.direction`), `src/sextant/catalogs/spring-http-interface.yml`, `src/sextant/storage/duckdb/derive_endpoints.sql`
- Create: `scripts/probes/cp7_http_exchange.md` + harness
- Test: `tests/application/test_endpoints.py`

**The defect today:** a locally-implemented `@HttpExchange` interface derives an
**outbound** row — the module reported calling a service it actually serves —
and its inbound routes are missed entirely. Both errors in the same rows.

- [ ] **Step 0: CP-7, restated — measure before building (§8.1)**

The original CP-7 asked whether 2E's inheritance walk carries an interface's
annotations onto the implementing class. **It cannot, by design:** the walk runs
only for catalogs declaring a type-level gate (`annotation_driven.py:159-161`)
and `spring-http-interface.yml` declares none, deliberately
(`spring-http-interface.yml:17-18`) — a shipped test pins that a gateless
catalog must never synthesize onto an implementer.

Probe instead: **(a)** Spring's actual server-side handler predicate — is it
`@Controller`, or `@Controller` OR a type-level `@RequestMapping`, and does it
honour meta-annotations (a custom `@ApiController` meta-annotated `@Controller`
is valid usage — §8.1 rule 2)? **(b)** are inherited `default` interface methods
served? **(c)** does an interface's annotation reach us when the interface is in
a dependency jar extracted via `.sextant.yml`? State the Framework/Boot versions.

- [ ] **Step 1: the handler comes from a fact join, not the walk**

`implemented_interfaces` (2E-prep) names the interface a class declares. Join on
it, matching the method by **name + descriptor** (name alone mis-binds
overloads). Known gaps to state, not silently miss: an abstract base implementing
the interface with a concrete controller extending it, and interface
inheritance — both are direct-only reads (`facts.py:129`, `:140`), so a bounded
within-module closure is required or the gap is stated.

- [ ] **Step 2: the flip condition is the CONTROLLER check, not `owner_implemented_in_module`**

Spec §6's original condition is **weaker than Spring's rule** and fabricates: a
`@Service` implementing an `@HttpExchange` interface is served by nothing. Gate
on a catalog-declared controller annotation — the FQNs are already catalog data
(`spring-mvc.yml:13`, `spring-web.yml:13`), so do not hardcode them.

Implement `resolves.direction` alone. **Do NOT also add `declared_on: interface`** —
it subtracts exactly the rows the flip must flip (`derive_endpoints.sql:699-702`),
and shipping both yields no inbound rows at all.

- [ ] **Step 3: merge precedence, not a collision-detector exemption (R12)**

There is **no collision detector and no findings mechanism** in `src/` (register
#9). When both the interface and the implementing class derive one route, the
rows share `(protocol, direction, method, path)` and merge through existing
dedup. Assert the **surviving row's handler is the implementing class's method**.
Delete the plan's old third test — it asserted `not resolved.findings(...)`
against a mechanism that does not exist.

- [ ] **Step 4: near-miss (§10), COVERAGE, commit**

Nothing flipped for: an `@HttpExchange` interface implemented by a non-controller
bean; an unimplemented `@HttpExchange` interface (must stay outbound).

---

## Task 11: The loud-failure pin

**Reduced 2026-09-04.** This task was "module-kind evidence and the loud-failure
pin". §9 was dropped entirely — module `kind` has exactly two consumers
(`api.py:324`'s skip gate and `metadata.py:70`'s label), only `library` ever
caused a skip, and nothing returns `library` any more. Adding *service* evidence
would have changed a manifest string and nothing else, at the cost of a
build-script change and an architectural conflict. What remains is the pin.

**Files:** `tests/agents/test_tradewind_loop.py` (or the sibling matching its convention — **not** `tests/agents/test_tradewind.py`, which does not exist)

- [ ] **Step 1: pin the loud failure, both auth paths**

A Tradewind invocation error propagates named and immediate — no retry loop, no
silent wait. The path is already correct (`agents/tradewind.py:281-287`,
`:342-349` → `api.py:1042` → `cli/app.py:76`); this pins it. Use the shipped
test seam `backend_factories` (`tradewind.py:247-250`).

**Scope the claim honestly (§5.4):** Sextant adds no retry and no wait; the
backend SDK's own behaviour is unmeasured and the docstring says so.

`api.enrich`'s real signature takes `agent` as a **string name** resolved through
the registry (`api.py:1136-1144`) — not an object, whatever the old plan showed.

---

## Task 12: The documentation sweep

**Corrected 2026-09-04** — three of its items are already done and one is void.

**Files:** `docs/components/D00`–`D02`, `D06`, `M02`, `M07`, `M08`; `docs/COVERAGE.md`; `docs/documented-not-implemented.md`; `README.md`; the roadmap

- [ ] **Step 1: the D02 style sections that remain**

`derived_resource`, `scheduled_work`, `error_advice`, and Task 7b's servlet
style. **Already written by Task 5: `supertype_derived` (D02:1287) and
`injected_client` (D02:1384)** — do not redo them.

- [ ] **Step 2: the live schema divergence**

`D00:190`'s protocol list still omits `amqp` and `pulsar` while
`closed_sets.py:86-87` ships both — a §5.1 violation dating from Task 1. Fix it.

**Already done, do not redo:** `declared_shape.operation` and the
`fact_schema_version` bump (D00:505-520); gRPC's two identity forms
(D01:340-341); the renderer/export arms for the three question kinds (`cf3f841`).

**Void — do not write it:** "§6's collision-detector interface/implementor
exemption". No detector exists (R12). Record merge precedence instead.

- [ ] **Step 3: the register**

Add every entry this phase found and did not close, each with its consumer
`file:line` (§5.3). Entries 10 (project catalogs) and 11 (`trace_of`) came from
the pre-dispatch audit; 12 (the unread `publishing` boolean) from the user
ruling.

- [ ] **Step 4: capabilities 9.15 and 9.16, and their consumers**

Document both in the extractor's capability list and D00. **State which
consumers read them and which do not** — `spring-webflux-router.yml`'s
`media_values` and `kafka-consumer.yml`'s `all_strings` read positional
arguments, not `elements`, so their output is unchanged until the wiring task
lands. A capability whose consumers are unwired must not be documented as
delivering output.

- [ ] **Step 5: re-derive the COVERAGE headline, lint, commit**

The count is re-derived from the flips, never carried (2H/2I discipline). Run
`uv run python scripts/coverage_matrix.py --check` and make it pass.

---

## Task 13: Wire the consumers 9.15 and 9.16 unblocked

**New task, 2026-09-04.** Both capabilities emit facts nothing reads yet. Without
this, 2O ships two capabilities with no visible output — the outcome the phase
exists to avoid.

**Files:** `src/sextant/catalogs/spring-webflux-router.yml`, `kafka-consumer.yml`, `spring-websocket.yml`, and whichever engine reads their keys

- [ ] **Step 1: `media_values`, `all_strings` and `channel_of` read `elements`**

All three read positional arguments today, so WebFlux media columns are NULL even
though `MediaType.APPLICATION_JSON` is now in the facts, and Kafka's multi-topic
arity is readable but unread. Their comments and a COVERAGE row asserted the
extractor could not read varargs — 9.15 corrected the claim in place; this makes
the behaviour match it.

`channel_of` is the third consumer, added 2026-09-05: the descriptor sweep
measured that `WebSocketHandlerRegistry.addHandler`'s varargs paths collapse
into ONE `kind: "array"` argument, so `spring-websocket.yml`'s `channel_arg: 1`
resolves nothing for any call — single- or multi-path. Both that file and
`docs/COVERAGE.md` name this step as the closer of that boundary, so it is named
here. `channel_of` resolves only `kind: "string"` today
(`shapes/arguments.py`); reading an `array`'s own `elements` turns the row's
NULL into one row per registered path, the way each `urlPatterns` entry is
already its own row.

- [ ] **Step 2: a nested-annotation consumer, if one is honest**

9.16 makes `@RabbitListener`'s `bindings = @QueueBinding(@Queue(…))` readable.
If Task 7's rabbit catalog can now read the queue name from the binding, do it
and retire that boundary. **If it cannot, leave the boundary and say why** —
do not invent a consumer to justify the capability.

- [ ] **Step 3: golden churn, near-miss, commit**

Expect recorded output to move — WebFlux media columns gain values. Audit every
changed line; a change that is not explained by one of these two reads is a
defect. Near-miss: a single-argument call must not gain an `elements` read.

---

## Self-review

**Spec coverage.** §3b→Tasks 7+7b; §4→Task 8; §5→Task 9; §6→Task 10; §7 shipped
in Task 2; §9 dropped by ruling; §10→Task 11; §12→Task 12; capabilities
9.15/9.16 shipped, their consumers→Task 13.

**Every mechanism cited carries a consumer `file:line`** (§5.3) — the plan no
longer asserts that anything is shipped without pointing at the code that reads
it.

**Every task that matches or classifies has a near-miss step** (§10), asserting
nothing is produced.

**Every framework rule is probed before it is built on** (§8.1) — CP-5 in Task 7,
CP-9 in Task 7b, CP-7 restated in Task 10, and Task 9 built on a probe that has
already run.

**Known gaps stated rather than assumed away:** Task 7's Actuator base-path has
no reader; Task 10's abstract-base and interface-inheritance indirection;
Task 13's Step 2, which may honestly find no consumer.
