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

## Task 7: The annotation catalog batch

Four catalogs, one engine extension. Batched because each is a small same-shape change.

**Files:**
- Create: `src/sextant/catalogs/spring-rabbit.yml`, `spring-sqs-legacy.yml`, `spring-actuator.yml`, `jakarta-servlet.yml`
- Modify: `src/sextant/application/resolve/engines/single_call.py` (secondary address capture)
- Modify: `src/sextant/ingress/catalogs/yaml_source.py` (`path_prefix`, `address_arg_2`)
- Test: `tests/application/test_call_engines.py`, `tests/application/test_endpoints.py`

**Interfaces:**
- Consumes: `Protocol.AMQP`/`PULSAR` (Task 1), `canonical_http_path` (Task 2).
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_rabbit_listener_derives_an_amqp_inbound_row(resolved):
    row = resolved.endpoint(protocol="amqp", direction="inbound")
    assert row["path"] == "orders.incoming"


def test_a_spel_destination_is_unresolved_and_verbatim(resolved):
    # No SpEL reader exists and none is built (2O design §3b).
    row = resolved.endpoint(protocol="amqp", path="#{queueNameBean.name}")
    assert row["resolution"] == "unresolved"


def test_rabbit_template_identity_is_the_exchange_and_routing_key_pair(resolved):
    row = resolved.endpoint(protocol="amqp", direction="outbound")
    assert row["path"] == "orders.exchange/order.created"


def test_an_actuator_endpoint_serves_under_the_declared_prefix(resolved):
    row = resolved.endpoint(protocol="http", path="/actuator/orders-health")
    assert row["method"] == "GET"      # @ReadOperation
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/application/test_call_engines.py -v`
Expected: FAIL — the catalogs do not exist; `single_call` refuses two address positions.

- [ ] **Step 3: Extend `single_call` with a secondary address**

AMQP's wire identity is the exchange+routing-key **pair**, which the one-address contract refuses (declaring two is a `CatalogError`). Add optional `address_arg_2` plus a catalog-declared join format, rendering `exchange/routingKey`. An overload without an exchange (the default exchange) captures the routing key alone — state that in the catalog comment.

- [ ] **Step 4: Write the four catalogs**

- **`spring-rabbit.yml`** — `@RabbitListener(queues=…)` inbound at `amqp`; `@PulsarListener` at `pulsar`; `RabbitTemplate.convertAndSend` outbound. Comment the two boundaries: `bindings=` nested annotations (D00's literal model has no nested annotations) and SpEL.
- **`spring-sqs-legacy.yml`** — the two older `@SqsListener` spellings. Pure data.
- **`spring-actuator.yml`** — `@Endpoint(id=…)` + operation annotations per CP-5, with the new guarded `path_prefix: /actuator` key and the `management.endpoints.web.base-path` override read from `resolved_config`. Comment that `@Selector` segments are a stated boundary (the only parameter-annotation read is `request_body`, and `mapping` cannot express append-per-parameter) and that built-in endpoints are dependency+property driven.
- **`jakarta-servlet.yml`** — `@WebServlet` inbound; `@WebFilter`/`FilterRegistrationBean`/`ServletRegistrationBean` as stated boundaries.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/application -q`
Expected: PASS.

- [ ] **Step 6: Fixtures, COVERAGE, commit**

Fixture code exercising each row shape. Flip COVERAGE's A-tier rows for `@RabbitListener`, `@PulsarListener`, legacy `@SqsListener`, Actuator and servlets; add every boundary row.

```bash
git add -A
git commit -m "feat: rabbit, pulsar, legacy sqs, actuator and servlets"
```

---

## Task 8: The two non-wire families

**Files:**
- Create: `src/sextant/application/resolve/engines/scheduled_work.py`, `engines/error_advice.py`
- Create: `src/sextant/catalogs/spring-scheduling.yml`, `spring-advice.yml`
- Modify: `endpoints.py` (`_ENGINES`), the D01 tables, D06 bundle artifacts, `egress/render/` (two sections), `egress/export/` (two slots)
- Test: `tests/application/test_scheduled_work.py`, `tests/application/test_error_advice.py`, render/export tests

**Interfaces:**
- Consumes: nothing.
- Produces: `scheduled_work` and `error_handlers` tables.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_scheduled_method_lands_in_its_own_table_not_endpoints(resolved):
    assert not resolved.endpoints(handler="com.example.orders.Sweeper#sweep")
    row = resolved.scheduled_work()[0]
    assert row["trigger_kind"] == "cron"
    assert row["expression"] == "0 0 * * * *"


def test_an_advice_records_its_exception_types_and_status(resolved):
    row = resolved.error_handlers()[0]
    assert row["advice_class"] == "com.example.orders.ApiExceptionHandler"
    assert row["exception_type"] == "com.example.orders.OrderNotFound"
    assert row["status"] == "404"        # from @ResponseStatus


def test_a_status_computed_inside_a_response_entity_is_not_guessed(resolved):
    row = resolved.error_handlers(advice_class="com.example.orders.DynamicHandler")[0]
    assert row["status"] is None         # stated boundary, never invented
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/application/test_scheduled_work.py tests/application/test_error_advice.py -v`
Expected: FAIL — no tables, no engines.

- [ ] **Step 3: Build both families**

Each gets: the engine, the D01 table, the D06 bundle artifact, the M07 rendered section ("Scheduled work", "Error handling") using 2M's typed machine sections, and the M08 export slot with deterministic total ordering. `@Scheduled`/`@Schedules` carry handler + trigger kind + expression verbatim (placeholders through the shipped ladder; unresolvable → unresolved). `@ControllerAdvice`/`@RestControllerAdvice`/`@ExceptionHandler` (including handler methods inside controllers, scoped to that controller per Spring's rule) carry advice class, scope attributes verbatim, exception types (annotation value, else the parameter type — Spring's own rule), and `@ResponseStatus` where present.

State in `scheduled_work.py`'s docstring that D00's `root_kind: scheduled` stays unfed this phase — `trace_of` roots on inbound endpoints, and scheduled roots come alive with 2Q's traversal.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Extend byte-identity e2e, COVERAGE, commit**

Extend the byte-identity end-to-end test to both new tables' exports. Flip COVERAGE's `@Scheduled` and `@ControllerAdvice` rows; add the `ResponseEntity`-status and Quartz boundary rows.

```bash
git add -A
git commit -m "feat: scheduled work and error contracts, beside the wire-true table"
```

---

## Task 9: Spring Integration — channels, and honest questions

**Files:**
- Modify: `src/sextant/application/resolve/engines/config_join.py` (`from: annotation_value`)
- Create: `src/sextant/catalogs/spring-integration.yml`
- Create: a project-catalog fixture proving the wire-half pattern
- Test: `tests/application/test_config_join.py`

**Interfaces:**
- Consumes: Task 1's `channel_destination` kind.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_bean_wired_channel_files_a_question_and_derives_no_endpoint(resolved):
    # Spring Integration defines NO standard configuration key for a channel's
    # destination — real apps wire them in bean definitions. The question IS
    # the product for those flows.
    assert not resolved.endpoints(catalog_id="spring-integration")
    q = resolved.open_questions(question="channel_destination")[0]
    assert q["candidates"] == '["orders.inbound", "com.example.orders.Activator#handle"]'


def test_a_project_catalog_declaring_its_own_key_template_derives_the_wire_row(resolved_with_project_catalog):
    row = resolved_with_project_catalog.endpoint(protocol="amqp", direction="inbound")
    assert row["path"] == "orders.queue"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/application/test_config_join.py -v`
Expected: FAIL — `binding.from` accepts only `bean_name`.

- [ ] **Step 3: Add the second binding source**

`config_join` today reads one input (`resolved_config`) and one binding source (`bean_name`); anything else is refused. Add `annotation_value`: the binding key comes from an annotation attribute (`@ServiceActivator`'s `inputChannel`, `@InboundChannelAdapter`'s `channel`, `@Transformer`, `@Router`). **The engine's single input is unchanged** — destinations still come from `resolved_config` alone.

- [ ] **Step 4: Write the built-in catalog as questions-only**

`spring-integration.yml` files a `channel_destination` question per activator/adapter and derives no wire rows, because any destination key template would be a project convention — which D02 places in a repo's own `sextant.yml`, never in a built-in. Document the project-catalog pattern in the catalog's comment and prove it with the fixture project catalog. Never fabricate a wire; never `peer: in-process`.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/application -q`
Expected: PASS.

- [ ] **Step 6: COVERAGE and commit**

Flip the Spring Integration row to shipped-with-boundaries and add the DSL boundary row.

```bash
git add -A
git commit -m "feat: Integration channels made visible, their destinations honestly unanswered"
```

---

## Task 10: The `@HttpExchange` direction flip

**Files:**
- Modify: `src/sextant/application/resolve/engines/annotation_driven.py` (implement `resolves.direction`)
- Modify: `src/sextant/catalogs/spring-http-interface.yml`
- Modify: the routing-ambiguity collision detector
- Test: `tests/application/test_endpoints.py`

**Interfaces:**
- Consumes: CP-7's verdict.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_locally_implemented_http_exchange_interface_serves_rather_than_calls(resolved):
    rows = resolved.endpoints(path="/orders/{id}", catalog_id="spring-http-interface")
    assert len(rows) == 1
    assert rows[0]["direction"] == "inbound"
    assert rows[0]["handler"] == "com.example.orders.OrderApiImpl#get"   # the IMPLEMENTATION


def test_an_unimplemented_http_exchange_interface_still_reads_as_a_client(resolved):
    row = resolved.endpoint(path="/billing/{id}", catalog_id="spring-http-interface")
    assert row["direction"] == "outbound"


def test_the_interface_implementor_pair_raises_no_routing_ambiguity(resolved):
    assert not resolved.findings(kind="routing_ambiguity")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/application/test_endpoints.py -k http_exchange -v`
Expected: FAIL — the interface derives an outbound row.

- [ ] **Step 3: Implement `resolves.direction`**

D02 specifies `resolves.direction` with `when: {owner_implemented_in_module: true}` and nothing implements it. Implement it and declare it on `spring-http-interface.yml`. **Do not also add `declared_on: interface`** — that subtracts exactly the rows this flips, and shipping both yields no inbound rows at all. `jakarta-jws-client.yml`'s subtraction stays as it is; its SEI story is different.

- [ ] **Step 4: Rule on double derivation**

If CP-7 shows 2E's inheritance walk carries the interface's annotations to the implementing class, both derive the same route. The implementing class's row **stands**; the interface's yields. Exempt the interface/implementor pair in the collision detector — a real second implementor must still trip it.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: COVERAGE and commit**

```bash
git add -A
git commit -m "fix: a locally implemented @HttpExchange interface serves, not calls"
```

---

## Task 11: Module-kind evidence and the loud-failure pin

**Files:**
- Modify: M02's module-kind determination (Gradle plugin evidence)
- Test: `tests/application/test_detector.py` (match the existing name), `tests/agents/test_tradewind.py`

**Interfaces:**
- Consumes: 2M's harvested Gradle plugin ids.
- Produces: nothing.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_gradle_application_plugin_is_service_evidence(detected):
    assert detected.module("gradle-app").kind == "service"


def test_the_boot_gradle_plugin_is_service_evidence(detected):
    assert detected.module("gradle-boot").kind == "service"


def test_an_invocation_failure_surfaces_immediately_and_names_itself(fake_failing_agent):
    # No retry loop, no silent wait — retrying is the operator's re-run.
    with pytest.raises(SextantError, match="authentication"):
        api.enrich(module, agent=fake_failing_agent)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/application/test_detector.py tests/agents -v`
Expected: FAIL — Gradle modules get the default kind.

- [ ] **Step 3: Join the plugin evidence, pin the failure path**

2M's init script already harvests plugin ids. Join `application` and the Spring Boot plugin as service evidence, symmetric with the Maven boot-plugin evidence; 2M's skip-gate semantics (skip only `library` + packaging-pom) are unchanged. Add one test per auth path proving a Tradewind invocation error propagates unchanged.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: Gradle plugins as service evidence; pin the loud invocation failure"
```

---

## Task 12: The documentation sweep

Every task carried its own COVERAGE rows. This task closes what spans them.

**Files:**
- Modify: `docs/components/D00-fact-schema.md`, `D01-graph-schema.md`, `D02-catalog-schema.md`, `M02-detector.md`, `M07-renderer.md`, `M08-exporter.md`
- Modify: `docs/COVERAGE.md` (headline re-derivation), `README.md`, `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md`

- [ ] **Step 1: Write the D02 style sections**

One full section per new style — `supertype_derived`, `injected_client`, `derived_resource`, `scheduled_work`, `error_advice` — matching the depth of the shipped style sections, each stating what it reads, what it derives, what it refuses, and its pipeline position.

- [ ] **Step 2: Write the schema amendment notes**

D00: `declared_shape.operation`, protocols `amqp`/`pulsar`, `fact_schema_version` bump with the estate cost. D01: the two new tables, gRPC's **two** identity forms (`package.Service/Method` and the service-level `package.Service`, the SOAP precedent), the three `open_questions` kinds with their candidate shapes, the path-identity migration, and the routing-ambiguity interface/implementor exemption. D02: the `binder_protocols` migration, the leading-slash overturn scoped to `http`, and every new catalog key (`path_prefix`, `address_arg_2`, `identity_marker`, `supertype_marker`, marker coordinates).

- [ ] **Step 3: Re-derive the COVERAGE headline**

Count the flipped rows and any rows the phase ADDED to the denominator (2H/2I discipline: the count is re-derived, never carried). Run `uv run python scripts/coverage_matrix.py --check` and make it pass.

- [ ] **Step 4: Update the roadmap and README**

Mark 2O delivered with what actually shipped and what it deliberately did not. Update README's catalog/dependency sections if any new mechanism is user-visible.

- [ ] **Step 5: Full suite, lint, commit**

Run: `uv run pytest -q && ./scripts/check.sh --lint`
Expected: PASS, all four import contracts kept.

```bash
git add -A
git commit -m "docs: 2O — the Spring surface, its schema amendments and its boundaries"
```

---

## Self-review

**Spec coverage.** §0a's eight checkpoints: CP-1/CP-6 in Task 1, CP-2 in Task 6, CP-3/CP-8 in Task 3, CP-4 in Task 4, CP-5 in Task 7, CP-7 in Task 10. §1a→Task 4; §1b/§1c→Task 5; §1d→Task 5's COVERAGE rows. §2→Task 6. §3a→Tasks 1+2; §3b→Task 7. §4→Task 8. §5→Task 9. §6→Task 10. §7→Task 2. §8→Task 2. §9/§10→Task 11. §11 is out-of-scope pointers. §12's verification is distributed, with the docs remainder in Task 12. **No gaps.**

**Placeholder scan.** The `FILL FROM PROBE` markers in Task 1 are deliberate — they are the probe's output slots, and Step 6 requires filling them before the task completes. No other placeholders.

**Type consistency.** `canonical_http_path`/`is_path_shaped` (Task 2) are used by name in Tasks 6 and 7. `generic_interfaces` (Task 3) is read in Task 6. `OperationRecord`'s four fields (Task 4) are asserted in Task 4's tests and merged against in Task 5. The three question kinds (Task 1) are used in Tasks 5, 6 and 9 under those exact names.

**Ordering risk worth naming for the executor.** Task 2 changes recorded output before most surfaces exist, which is deliberate: the migration's diff stays readable. Tasks 4–11 then ADD rows, which is not churn.
