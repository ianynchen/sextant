# Phase 2B — Outbound annotation clients and bundle export: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A module's analysis covers both directions of its HTTP surface — inbound endpoints and annotation-declared outbound calls, each carrying its payload contract as a wire descriptor — and exports as a portable D06 bundle; `analyze → render → export` becomes functional end to end.

**Architecture:** The existing `annotation_driven` engine generalises (optional type gate, direction from the catalog, split prefix/peer attribute lists, catalog-declared body rule) so three new outbound catalogs need no new engine. Endpoint shape columns become recursive wire descriptors reusing the `item` grammar and the existing `_described` machinery. The exporter writes Parquet through the Workspace port (DuckDB `COPY TO`) with the manifest assembled in egress — the same layering split `metadata.json` already uses.

**Tech Stack:** Python 3.12 + DuckDB (native Parquet writer — no new dependencies); Maven fixture gains `spring-cloud-openfeign-core` and `retrofit` (annotation jars, one-time online fetch); pytest, ruff, mypy, import-linter.

**Spec:** [docs/superpowers/specs/2026-08-29-phase-2b-outbound-and-export-design.md](../specs/2026-08-29-phase-2b-outbound-and-export-design.md) — the plan argues from it; executors read both. Rulings I1–I3 (identity without direction + `caller`; `prefix_from`/`peer_from`; exhaustive gap rotation) are binding.

## Global Constraints

- **No new dependencies.** Parquet is written by DuckDB's `COPY … TO`; the fixture's new jars are fixture-scope only (ARCHITECTURE §9 untouched).
- **No framework name outside the catalogs; no language name outside `ingress/extract/jvm`** — architecture tests scan every line of `src/`, comments and docstrings included.
- **`application/` performs no file I/O** and outer groups never import one another; the CLI is the composition root (import-linter enforces all four contracts; `scripts/check.sh --lint` runs them and a pre-commit hook enforces them).
- **Determinism (NFR-1):** same inputs → byte-identical facts, tables, `metadata.json`, documents, and now bundles. No set/dict iteration order may reach output rows; every export ordering is explicit.
- **Closed sets stay closed (NFR-5).** The wire vocabulary and `Direction` (`inbound`/`outbound`/`both` — `both` is already in `closed_sets.py`) gain no members.
- **Spec before code (GUIDELINES §5):** Task 1 amends D01/D02/M07/M08/D06; no later task deviates from a component doc without an amendment.
- **No version bumps** — versions stay 0.1.0 / 1.0.0 / 1.0.0 (user's standing gate); the manifest reports them as they are.
- **Every catalog ships conformance coverage** (D02 §4): the fixture uses the real frameworks; stubs are forbidden.
- **Exact-list discipline:** fixture-derived test lists (scanner file lists, route sets, counts) are extended with full membership, never loosened.

## File structure

| File | Responsibility |
|---|---|
| `docs/components/{D01,D02,M07,M08,D06}` | **Amend** (Task 1): identity, caller, descriptors, outbound vocabulary, document blueprint, resolved open decisions |
| `fixtures/orders-service/pom.xml`, `…/clients/{BillingClient,InventoryExchange,LegacyBillingApi}.java` | **Create/modify** (Task 2): the three real client interfaces |
| `src/sextant/storage/duckdb/schema.sql` | **Modify**: `peer`, `caller` columns (Task 3); no other schema change |
| `src/sextant/storage/duckdb/derive_endpoints.sql` | **Modify** (Task 3): optional type gate, prefix/peer split, caller placement |
| `src/sextant/storage/duckdb/merge_endpoints.sql` | **Create** (Task 4): the D02 §3 cross-direction merge |
| `src/sextant/application/resolve/endpoints.py` | **Modify** (Tasks 3–4): new bound params, inbound-first ordering, merge call |
| `src/sextant/application/resolve/shapes.py` | **Modify** (Tasks 5–6): descriptor columns, generalized body rule |
| `src/sextant/catalogs/{spring-cloud-openfeign,spring-http-interface,retrofit}.yml` | **Create** (Task 7); `spring-web.yml`/`spring-mvc.yml` migrate to the new keys (Task 3, 6) |
| `src/sextant/egress/render/{viewmodel.py,diagrams.py}` | **Create** (Task 8): M07 view model + Mermaid classDiagram emitter |
| `src/sextant/egress/render/{document.py,metadata.py}` | **Modify** (Task 8): new sections, gap rotation, outbound counts |
| `src/sextant/application/ports/workspace.py`, `storage/duckdb/workspace.py` | **Modify** (Task 9): `export_tables` / `export_facts` |
| `src/sextant/egress/export/manifest.py` | **Create** (Task 10) |
| `src/sextant/cli/app.py` | **Modify** (Task 10): `module export` command (composition root orchestrates, like `analyze` + `write_metadata` today) |
| `docs/COVERAGE.md`, `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md`, `src/sextant/ingress/extract/jvm/scanner.py` docstring | **Modify** (Task 12): close-out bookkeeping |

One plan-level correction to the spec, made for the layering the import contracts enforce: the spec placed export orchestration in `application/stages/export.py`, but `application` may not import `egress` (layering runs `cli → outer groups → application`), and the established pattern is that the CLI composition root sequences workspace calls and egress writers (`analyze` + `write_metadata`). Export follows that pattern; the spec's intent (storage does Parquet I/O, egress writes the manifest, no I/O in application) is preserved exactly.

---

### Task 1: Spec amendments — D01, D02, M07, M08, D06

**Files:**
- Modify: `docs/components/D01-graph-schema.md` (§3 Contracts, the endpoint-identity paragraph)
- Modify: `docs/components/D02-catalog-schema.md` (§2 `annotation_driven`, the sentence near line 214, §7)
- Modify: `docs/components/M07-renderer.md` (Output/Behaviour: the module document blueprint)
- Modify: `docs/components/M08-exporter.md`, `docs/components/D06-bundle-format.md` (open decisions resolved)

**Interfaces:**
- Produces: the amended spec text every later task implements. No code.

- [ ] **Step 1: Amend D01 §3 Contracts**

Four changes, each traceable to a spec ruling:

1. The endpoint-identity paragraph ("Endpoint identity is minted from…"): change the hash inputs from `hash(module id, protocol, direction, wire identity template)` to `hash(module id, protocol, wire identity template)`, and add a sentence in the paragraph's own style explaining why direction left: D02 §3 merges a path a module both exposes and calls into one endpoint with direction `both`, so direction is mutable state — and mutable state does not belong in identity, by the same argument this paragraph already makes for handlers ("a refactor that moves the handler must not orphan the curations… the wire contract they were about did not change").
2. The Contracts table row for `endpoints`: "Direction, protocol, wire identity, handler **and/or caller**, peer, request and response payload descriptors, trust fields". Add below the table: a `both` row keeps `handler` (the server method) and `caller` (the client method); an outbound-only row carries `caller` with `handler` NULL; `peer` is the outbound target hint (a declared service name or literal authority) the system tier later resolves against participants.
3. The `shape_fields` column prose: after the `item` grammar sentence, state the parked clarification verbatim: **`shape_id` is the payload type's symbol — a local join key into `shapes`, never compared across services; DR-5 matches field structure, not identifiers.** Extend the item enumeration ("NULL for a scalar field, the element descriptor for an `array`, the value descriptor for a `map`") with: "and the full descriptor of the referenced shape for an `object` field — one grammar, so a consumer never detects which variant it holds."
4. Add to the same Contracts section: `endpoints.request_shape` and `endpoints.response_shape` hold the **same recursive descriptor** (`{wire_type, wire_format, nullable, shape_id?, item?}`) rather than a bare shape id — a `List<OrderView>` response is `{"wire_type":"array","item":{"wire_type":"object","shape_id":…}}`, a scalar response is recorded (`{"wire_type":"string"}`), and NULL means exactly *no payload* (a `void` return, no body parameter).

- [ ] **Step 2: Amend D02**

1. In §2 `annotation_driven`, document the generalized catalog vocabulary with a YAML example:

```yaml
matches:
  # Optional: a catalog may declare no type-level gate. Any type containing a
  # matching mapping annotation then participates (a Retrofit interface has no
  # type-level marker at all).
  type_annotation: org/springframework/cloud/openfeign/FeignClient#
  # The body rule is catalog data: which annotation marks the payload
  # parameter, and whether the sole unannotated parameter is the fallback.
  request_body: { annotation: org/springframework/web/bind/annotation/RequestBody#,
                  fallback: sole_unannotated }   # or: none
  mapping:
    prefix_annotation: org/springframework/cloud/openfeign/FeignClient#
    # Type-level and method-level annotations are different roles. On
    # @RequestMapping, value/path are aliases meaning *path*; on @FeignClient,
    # value aliases *name* — the service id — and only path means prefix. One
    # shared alias list conflated the two roles by the luck of @RequestMapping's
    # aliasing; prefix_from and peer_from name them separately.
    prefix_from: [path]
    peer_from: [name, value]
    path_from: [value, path]
    ...
```

2. Replace the sentence near line 214 stating that M04 "records the unwrapping chain on the endpoint" with: the chain is consumed where it is produced — `optional` semantics feed `required`; nothing records the chain on the endpoint row.
3. Add a row to §7 (open decisions): "Precedence between a `known_types` entry's own `nullable` and an enclosing `not_null_by_default` scope — unspecified; as implemented the scope wins. Unreachable with shipped catalogs."

- [ ] **Step 3: Amend M07 with the module document blueprint**

Add a subsection "The module document blueprint" to Behaviour, containing the agreed table (verbatim from the spec §5): Overview (derived), Structure — contract class diagram (derived: nodes are payload types with wire fields, edges are `shape_id` references), Structure — full class diagram (gap: `inherits`/`implements` edges do not exist; call-graph phase), Inbound endpoints with contract field tables (derived), sequence diagram per inbound endpoint (gap `sequence_diagrams_pending_call_graph`), Outbound endpoints (derived), LLM-authored sections (overlay claims at `evidence: llm`, a later phase). Restate NFR-7's corollary: a section whose machinery does not exist is never rendered empty — it is named as a gap, because empty claims "looked and found nothing".

- [ ] **Step 4: Resolve the open decisions in M08 and D06**

In both files' open-decision tables, mark resolved with one line each: bundle is a **directory** (publishing is the caller's business; the archive question waits until publishing exists); `--what` **deferred** — export always carries facts and graph (facts are what make a bundle re-derivable); the full-text index does not travel (none exists). In D06 §2, note the facts-Parquet schema as pinned by this phase: the raw-fact rows *(kind, document_id, payload as a JSON string column)*, partitioned per source file.

- [ ] **Step 5: Commit**

```bash
git add docs/components
git commit -m "docs: amend D01, D02, M07, M08 and D06 for outbound endpoints and export"
```

---

### Task 2: Fixture — the three client interfaces

**Files:**
- Modify: `fixtures/orders-service/pom.xml`
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/clients/BillingClient.java`
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/clients/InventoryExchange.java`
- Create: `fixtures/orders-service/src/main/java/com/acme/orders/clients/LegacyBillingApi.java`
- Test: `tests/ingress/test_asm_scanner.py` (exact lists extended)

**Interfaces:**
- Produces: the compiled client interfaces whose annotation and symbol facts Tasks 3–7 assert on. Wire paths used later: `POST /billing/invoices`, `GET /billing/invoices` (Feign, peer `billing`), `GET /v1/inventory/levels`, `POST /v1/inventory/reserve` (`@HttpExchange`), `GET legacy/invoices/{id}`, `POST legacy/invoices` (Retrofit), and the self-call `POST /v1/orders` (Feign, exercises the merge).

- [ ] **Step 1: Add the dependencies (one-time online fetch)**

Append to `pom.xml`'s `<dependencies>`:

```xml
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-openfeign-core</artifactId>
      <version>4.1.4</version>
    </dependency>
    <dependency>
      <groupId>com.squareup.retrofit2</groupId>
      <artifactId>retrofit</artifactId>
      <version>2.11.0</version>
    </dependency>
```

Then run **once, online**: `cd fixtures/orders-service && mvn -q compile` (no `-o`) to populate `~/.m2`. Every later build is `mvn -q -o compile` again. If the versions above cannot resolve against the cached Spring 6.1.6 line, prefer the nearest `spring-cloud-openfeign-core` 4.1.x that does — record the chosen version in the report.

- [ ] **Step 2: Write the three interfaces**

```java
// BillingClient.java
package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import java.util.List;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

// value aliases *name* on @FeignClient — the service id, never a path. The
// catalog reads peer_from [name, value] and prefix_from [path], which is the
// split Task 3 exists for.
@FeignClient(name = "billing", path = "/billing")
public interface BillingClient {
    // The body parameter is explicit here; sole-unannotated fallback is
    // exercised by createOrder below.
    @PostMapping("/invoices")
    OrderView submitInvoice(@RequestBody OrderRequest invoice);

    // A collection payload: the endpoint descriptor must say "array of
    // OrderView", which is the gap 2A parked and this phase closes.
    @GetMapping("/invoices")
    List<OrderView> invoices();

    // The same wire identity the module itself exposes (OrderController's
    // POST /v1/orders): D02 §3 merges these into one endpoint, direction
    // `both`. The sole unannotated parameter is the body (Feign's contract).
    @PostMapping("/v1/orders")
    OrderView createOrder(OrderRequest order);
}
```

Note: `createOrder`'s path must resolve to exactly `/v1/orders` — Feign's `path = "/billing"` prefix applies to the other two methods, so `createOrder` moves to a second interface if prefixing would break the identity match. **Decide by what the derivation produces:** the merge test (Task 4) asserts the merged row exists; if the prefix applies, move `createOrder` to its own `@FeignClient(name = "orders-loop")` interface with no `path` attribute, and record that in the report.

```java
// InventoryExchange.java
package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

// The type-level annotation is the prefix carrier here; the base URL lives in
// builder code the annotation never sees, so `peer` stays NULL and the named
// gap client_base_addresses_not_resolved covers it.
@HttpExchange("/v1/inventory")
public interface InventoryExchange {
    @GetExchange("/levels")
    OrderView levels();

    @PostExchange("/reserve")
    OrderView reserve(@RequestBody OrderRequest request);
}
```

```java
// LegacyBillingApi.java
package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import retrofit2.http.Body;
import retrofit2.http.GET;
import retrofit2.http.POST;
import retrofit2.http.Path;

// No type-level marker exists in Retrofit: the interface is recognised by its
// method annotations alone, which is why the type gate became optional.
public interface LegacyBillingApi {
    @GET("legacy/invoices/{id}")
    OrderView invoice(@Path("id") String id);

    @POST("legacy/invoices")
    OrderView submit(@Body OrderRequest invoice);
}
```

- [ ] **Step 3: Rebuild offline and update the exact lists**

Run: `cd fixtures/orders-service && mvn -q -o compile` — expected exit 0.
Run: `.venv/bin/pytest tests/ingress -q` — expected: the two exact-list tests FAIL (three new `.jsonl` files, document count 13 → 16). Extend both lists with the three new class names and the count, keeping them exact and sorted. Retrofit methods return `Response`-free types, so no new wrapper facts are expected; verify the interfaces' facts appear with `construct_kind: "interface"` and their method annotations carry args (e.g. `retrofit2/http/GET#` with `{'value': 'legacy/invoices/{id}'}`).

- [ ] **Step 4: Run the full suite, then commit**

Run: `.venv/bin/pytest -q` — expected: all green (no engine work yet; only scanner-list tests changed).

```bash
git add fixtures/orders-service tests/ingress/test_asm_scanner.py
git commit -m "feat: give the fixture real Feign, HttpExchange and Retrofit clients"
```

---

### Task 3: Engine generalisations — optional type gate, prefix/peer split, caller placement

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql` (endpoints table)
- Modify: `src/sextant/storage/duckdb/derive_endpoints.sql`
- Modify: `src/sextant/application/resolve/endpoints.py` (`_run_annotation_driven`)
- Modify: `src/sextant/catalogs/spring-web.yml`, `src/sextant/catalogs/spring-mvc.yml` (add `prefix_from`)
- Test: `tests/application/test_endpoints.py`

**Interfaces:**
- Consumes: annotation/symbol facts (existing views).
- Produces: `endpoints` rows carrying `peer` (TEXT, nullable) and `caller` (TEXT, nullable); an outbound row has `caller` = the client method symbol, `handler` NULL, `handler_signature` filled. Bound-parameter contract for `derive_endpoints.sql`: existing params plus `$prefix_from VARCHAR[]`, `$peer_from VARCHAR[]` (empty list = no peer), `$type_annotation` now nullable.

- [ ] **Step 1: Write the failing tests**

Follow `test_endpoints.py`'s hand-built-fact pattern (`write_fact_file` + `DuckDbWorkspace`). Build an invented outbound catalog the way that file builds inbound ones — a `Catalog(...)` with `direction="outbound"`, `matches` containing `type_annotation`, `request_body`, and a `mapping` with `prefix_from`/`peer_from` — plus facts for a client interface: a type annotated with the marker (`args: {"name": "billing", "path": "/billing"}`), and a method annotated with a mapping annotation (`args: {"value": ["/invoices"]}`) whose symbol fact carries a signature.

```python
def test_an_outbound_catalog_produces_caller_rows_with_peer_and_prefixed_path(tmp_path):
    workspace = _outbound_workspace(tmp_path)   # local helper: facts + derive_endpoints
    [endpoint] = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert endpoint["path"] == "/billing/invoices"          # prefix_from read `path`…
    assert endpoint["peer"] == "billing"                    # …and peer_from read `name`
    assert endpoint["handler"] is None
    assert str(endpoint["caller"]).endswith("#submit(sig_" ) or "#" in str(endpoint["caller"])
    workspace.close()


def test_a_catalog_with_no_type_gate_matches_on_method_annotations_alone(tmp_path):
    """A Retrofit interface has no type-level marker; the mapping annotation
    is the whole evidence."""
    workspace = _ungated_workspace(tmp_path)    # catalog with type_annotation: None
    rows = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert [e["path"] for e in rows] == ["legacy/invoices"]
    workspace.close()


def test_the_service_name_never_leaks_into_the_path(tmp_path):
    """@FeignClient(name=…) with NO path attribute: the prefix is empty, not
    the name — the exact bug the prefix_from/peer_from split exists for."""
    workspace = _outbound_workspace(tmp_path, type_args={"name": "billing"})
    [endpoint] = [e for e in workspace.query("endpoints") if e["direction"] == "outbound"]
    assert endpoint["path"] == "/invoices"
    assert endpoint["peer"] == "billing"
    workspace.close()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/pytest tests/application/test_endpoints.py -q`
Expected: FAIL — no `peer`/`caller` columns, `derive_endpoints.sql` rejects a NULL `$type_annotation`.

- [ ] **Step 3: Schema — the two columns**

In `schema.sql`'s `endpoints` table, after `handler_signature`:

```sql
    -- The client-side method symbol (D01 §3, amended this phase): an
    -- outbound row carries `caller` with `handler` NULL; a `both` row keeps
    -- both. `peer` is the declared target hint — a service name or a literal
    -- authority — that the system tier later resolves to a participant; NULL
    -- where the base address lives in builder code the annotations never see.
    caller            TEXT,
    peer              TEXT,
```

(Column order in the table declaration is free; the INSERT below names its columns.)

- [ ] **Step 4: Rewrite `derive_endpoints.sql`**

The full derivation, replacing the current file — the `mapping_catalog`/`declared`/`mappings` CTEs are unchanged in substance; `controllers` becomes optional, `prefixes` splits off with its own alias lists, and the final SELECT places the symbol by direction:

```sql
INSERT INTO endpoints (
    protocol, direction, method, path, handler, caller, peer,
    handler_signature, resolution, evidence
)
WITH mapping_catalog AS (
    SELECT s.fqn AS fqn, s.methods AS methods
    FROM (SELECT UNNEST(
        $mapping_annotations::STRUCT(fqn VARCHAR, methods VARCHAR[])[]
    ) AS s)
),
-- The type-level gate is optional (D02 §2, amended): a catalog that declares
-- none matches on method annotations alone — a Retrofit interface has no
-- type-level marker at all.
controllers AS (
    SELECT DISTINCT target AS type_symbol
    FROM annotations
    WHERE annotation = $type_annotation
),
declared AS (
    SELECT
        a.target AS target,
        coalesce(list_extract(list_filter(list_transform(
            $path_from::VARCHAR[],
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1), '') AS path,
        coalesce(
            CASE WHEN len(coalesce(
                TRY_CAST(a.args -> $method_from AS VARCHAR[]),
                CASE WHEN a.args ->> $method_from IS NOT NULL
                     THEN [a.args ->> $method_from] END,
                []::VARCHAR[]
            )) > 0
            THEN list_transform(
                coalesce(
                    TRY_CAST(a.args -> $method_from AS VARCHAR[]),
                    [a.args ->> $method_from]
                ),
                v -> regexp_extract(v, '#([A-Za-z0-9_]+)\.$', 1)
            ) END,
            mc.methods,
            $all_methods::VARCHAR[]
        ) AS methods
    FROM annotations a
    JOIN mapping_catalog mc ON mc.fqn = a.annotation
),
-- Type-level and method-level annotations are different roles: on
-- @RequestMapping value/path both mean *path*, on @FeignClient value aliases
-- *name* — the service id — and only path means prefix. prefix_from and
-- peer_from keep the roles apart (spec ruling I2).
prefixes AS (
    SELECT
        a.target AS type_symbol,
        coalesce(list_extract(list_filter(list_transform(
            $prefix_from::VARCHAR[],
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1), '') AS prefix,
        list_extract(list_filter(list_transform(
            $peer_from::VARCHAR[],
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1) AS peer
    FROM annotations a
    WHERE a.annotation = $prefix_annotation
),
mappings AS (
    SELECT d.target AS method_symbol,
           UNNEST(d.methods) AS wire_method,
           d.path AS path_suffix
    FROM declared d
),
derived AS (
    SELECT
        $protocol   AS protocol,
        $direction  AS direction,
        m.wire_method AS method,
        coalesce(p.prefix, '') || m.path_suffix AS path,
        -- The symbol lands by direction (D01 §3, amended): the server side
        -- handles, the client side calls, and a later merge may hold both.
        CASE WHEN $direction = 'outbound' THEN NULL ELSE s.symbol END AS handler,
        CASE WHEN $direction = 'outbound' THEN s.symbol END AS caller,
        p.peer      AS peer,
        s.signature AS handler_signature,
        'resolved'  AS resolution,
        'compiler'  AS evidence
    FROM mappings m
    JOIN symbols s ON s.symbol = m.method_symbol
    LEFT JOIN controllers c ON s.enclosing = c.type_symbol
    LEFT JOIN prefixes p ON p.type_symbol = s.enclosing
    WHERE $type_annotation IS NULL OR c.type_symbol IS NOT NULL
)
SELECT * FROM derived d
WHERE NOT EXISTS (
    SELECT 1 FROM endpoints existing
    WHERE existing.protocol  = d.protocol
      AND existing.direction = d.direction
      AND existing.method    = d.method
      AND existing.path      = d.path
);
```

Preserve the file's existing header comment, updated for the new parameters.

- [ ] **Step 5: Pass the new parameters and migrate the inbound catalogs**

In `endpoints.py`'s `_run_annotation_driven`, the mapping reads become:

```python
    mapping = catalog.matches["mapping"]
    workspace.derive(
        "endpoints",
        protocol=catalog.protocol,
        direction=catalog.direction,
        # Optional (D02 §2, amended): absence means "no type-level gate".
        type_annotation=catalog.matches.get("type_annotation"),
        prefix_annotation=mapping["prefix_annotation"],
        mapping_annotations=[
            {"fqn": m["fqn"], "methods": m.get("method")} for m in mapping["annotations"]
        ],
        path_from=list(mapping["path_from"]),
        prefix_from=list(mapping["prefix_from"]),
        peer_from=list(mapping.get("peer_from", [])),
        method_from=mapping["method_from"],
        all_methods=list(mapping["all_methods"]),
    )
```

In `spring-web.yml` and `spring-mvc.yml`, add to `mapping:` (both files, same line):

```yaml
    prefix_from: [value, path]
```

- [ ] **Step 6: Run the new tests, then the full suite**

Run: `.venv/bin/pytest tests/application/test_endpoints.py -q` — expected PASS.
Run: `.venv/bin/pytest -q` — expected: all green (inbound behaviour unchanged: same paths, `caller`/`peer` NULL on every inbound row).

- [ ] **Step 7: Commit**

```bash
git add src/sextant tests/application/test_endpoints.py
git commit -m "feat: generalise the annotation engine for outbound catalogs"
```

---

### Task 4: The cross-direction merge and inbound-first ordering

**Files:**
- Create: `src/sextant/storage/duckdb/merge_endpoints.sql`
- Modify: `src/sextant/application/resolve/endpoints.py`, `src/sextant/storage/duckdb/workspace.py` (`_NAMED_DERIVATIONS`)
- Test: `tests/application/test_endpoints.py`

**Interfaces:**
- Consumes: the rows Task 3 writes.
- Produces: after `derive_endpoints`, no (protocol, method, path) appears once per direction — a wire identity present in both directions is one row, `direction='both'`, with `handler`, `caller`, and `peer` all retained. Named derivation `"endpoints_merge"`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_path_the_module_both_exposes_and_calls_is_one_endpoint_with_both(tmp_path):
    """D02 §3: inbound runs first so the merged row keeps the server's handler
    and gains the client's caller — appearing twice would make every consumer
    re-implement the merge."""
    workspace = _two_direction_workspace(tmp_path)   # inbound + outbound catalogs, same POST path
    rows = [e for e in workspace.query("endpoints") if e["path"] == "/v1/orders"]
    assert len(rows) == 1
    [merged] = rows
    assert merged["direction"] == "both"
    assert merged["handler"] is not None and merged["caller"] is not None
    workspace.close()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/application/test_endpoints.py -q`
Expected: FAIL — two rows, one per direction.

- [ ] **Step 3: Write `merge_endpoints.sql`**

No bound parameters, so multiple statements are safe in one file:

```sql
-- D02 §3: a wire identity a module both exposes and calls is one endpoint,
-- direction `both`, keeping the server's handler and gaining the client's
-- caller (D01 §3 as amended — identity is minted without direction, so this
-- merge changes a property, never an identity). Runs once per resolve, after
-- every catalog. min() picks deterministically when several callers reach one
-- exposed path (NFR-1); the surviving signature is the handler's, which is
-- the richer side — the shapes pass reads it from this row.
UPDATE endpoints e
SET direction = 'both',
    caller = twins.caller,
    peer   = coalesce(e.peer, twins.peer)
FROM (
    SELECT protocol, method, path, min(caller) AS caller, min(peer) AS peer
    FROM endpoints
    WHERE direction = 'outbound'
    GROUP BY protocol, method, path
) twins
WHERE e.direction = 'inbound'
  AND e.protocol = twins.protocol
  AND e.method   = twins.method
  AND e.path     = twins.path;

DELETE FROM endpoints o
WHERE o.direction = 'outbound'
  AND EXISTS (
    SELECT 1 FROM endpoints b
    WHERE b.direction = 'both'
      AND b.protocol = o.protocol
      AND b.method   = o.method
      AND b.path     = o.path
  );
```

Register in `workspace.py`: `"endpoints_merge": "merge_endpoints.sql",`.

- [ ] **Step 4: Order the engines inbound-first and run the merge**

In `derive_endpoints` (endpoints.py), replace the loop's list with a sorted one and add the merge after the loop:

```python
    # D02 §3: inbound engines run before outbound so the merge below finds the
    # exposed row already present. Filename breaks the tie, which is the
    # loader's own order (NFR-1).
    ordered = sorted(engines, key=lambda pair: (pair[0].direction != "inbound", str(pair[0].source)))
    skipped = []
    for catalog, engine in ordered:
        ...
    # Once per resolve, after every catalog: a wire identity present in both
    # directions collapses to one row, direction `both` (D02 §3).
    workspace.derive("endpoints_merge")
    return skipped
```

(`pair[0].source` — `Catalog.source` — is the path the loader sorted by.)

- [ ] **Step 5: Run the tests, the full suite, commit**

Run: `.venv/bin/pytest -q` — expected: all green.

```bash
git add src/sextant tests/application/test_endpoints.py
git commit -m "feat: merge a path a module both exposes and calls into one endpoint"
```

---

### Task 5: Endpoint payload descriptors

**Files:**
- Modify: `src/sextant/application/resolve/shapes.py` (`_contracts_of`, `_payload_root` → descriptor form, `derive_endpoint_shapes`)
- Modify: `src/sextant/storage/duckdb/derive_endpoint_contracts.sql` (comment + keying only)
- Modify: `src/sextant/egress/render/metadata.py`, `document.py` (retire the collection gap), `tests/egress/test_render.py`
- Test: `tests/application/test_shapes.py`, `tests/application/test_pipeline.py`

**Interfaces:**
- Consumes: `RootedType`, `_described`, `_rules_of`, `_enum_symbols` (all existing in shapes.py).
- Produces: `request_shape`/`response_shape` hold descriptor JSON (`{wire_type, wire_format, nullable, shape_id?, item?}`, `sort_keys`, compact separators — same serialisation `_item_of` uses) or SQL NULL for *no payload*. `derive_endpoint_contracts.sql` keys on `coalesce(handler, caller)` so outbound rows get contracts too (consumed by Task 6).

- [ ] **Step 1: Write the failing tests**

In `test_shapes.py`, alongside the existing endpoint-contract tests (which hand-build facts and an invented catalog — reuse `_resolved_handler` and its neighbours):

```python
def test_a_collection_response_records_what_the_array_holds(tmp_path):
    """List<OrderView> was 2A's parked gap: the endpoint said nothing at all.
    The descriptor keeps the array-ness — it IS the wire contract — and points
    at the element's shape."""
    endpoint = _resolved_list_handler(tmp_path)   # handler returning List<OrderView>-shaped facts
    descriptor = json.loads(endpoint["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/contracts/OrderView#"


def test_a_scalar_response_is_recorded_rather_than_dropped(tmp_path):
    endpoint = _resolved_string_handler(tmp_path)
    assert json.loads(endpoint["response_shape"]) == {
        "nullable": True, "wire_format": "", "wire_type": "string"}


def test_no_payload_stays_null_and_means_exactly_that(tmp_path):
    """NULL stops being ambiguous: it is `void`/no-body, never 'a payload we
    could not describe'."""
    endpoint = _resolved_void_handler(tmp_path)
    assert endpoint["response_shape"] is None
```

Update the existing positive assertions in `test_shapes.py` and `test_pipeline.py` from bare symbols to descriptors — e.g. in `test_pipeline.py`'s detailed-endpoint test:

```python
    assert json.loads(endpoint["request_shape"]) == {
        "nullable": True, "shape_id": "com/acme/orders/contracts/OrderRequest#",
        "wire_format": "", "wire_type": "object"}
    assert json.loads(endpoint["response_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderView#")
```

The NULL-preserving tests (`…leaves_the_request_shape_null`, raw-wrapper, no-signature) keep their assertions unchanged — those cases stay NULL.

- [ ] **Step 2: Run and watch the new tests fail** (`pytest tests/application -q`).

- [ ] **Step 3: Implement the descriptor**

In `shapes.py`, replace `_payload_root` with a descriptor builder that reuses `_described` (so known types, enums, collections, and shape references all behave exactly as they do for fields), and thread `rules`/`enums`/`referenced` through `_contracts_of`:

```python
def _payload_descriptor(
    reference: dict[str, Any] | None,
    rules: _Rules,
    enums: set[str],
    referenced: list[str],
) -> str | None:
    """The wire descriptor a signature-level reference roots at, or None for
    *no payload* — a `void` return, an absent body. Scalars are recorded: a
    String response is a real contract, and NULL must keep exactly one meaning.

    Rooting can stop *on* a declared envelope when the reference carries
    nothing at the payload position (a raw `ResponseEntity`, every erased
    parameter). That is no payload either: describing the envelope would
    report a type the catalog already declares as one nobody could expand — a
    gap pointing at an entry that is already there. An envelope *nobody*
    declared still becomes a shape and is still reported.
    """
    if reference is None:
        return None
    rooted = root_type(reference, rules.wrappers)
    if _matching_wrapper(rooted.symbol, rules.wrappers) is not None:
        return None
    if rooted.reference.get("wire_type") in (None, ""):
        return None
    described = _described(rules, rooted.reference, enums, referenced)
    return json.dumps(described, sort_keys=True, separators=(",", ":"))
```

`_contracts_of` gains `rules`, `enums`, `referenced` parameters; its `columns` become:

```python
        columns = {
            _REQUEST: _payload_descriptor(_body_type(signature, catalog), rules, enums, referenced),
            _RESPONSE: _payload_descriptor(signature.get("returns"), rules, enums, referenced),
        }
```

and it keys each row on `owner = str(endpoint["handler"] or endpoint["caller"] or "")`, skipping empty. In `derive_endpoint_shapes`, per catalog:

```python
        rules = _rules_of(catalog)
        enums = _enum_symbols(workspace)
        referenced: list[str] = []
        found = _contracts_of(endpoints, catalog, settled, rules, enums, referenced)
        roots = list(dict.fromkeys(referenced))
        unexpanded.extend(derive_shapes(workspace, catalog, roots).unexpanded_types)
```

(The old per-column root collection goes away: `_described` already appended every object it met — including a collection's element — to `referenced`, which is strictly more complete than the 2A roots.) In `derive_endpoint_contracts.sql`, change the keying line to

```sql
WHERE coalesce(endpoints.handler, endpoints.caller) = c.handler;
```

and update its header comment: the two columns now hold the full wire descriptor (D01 §3 as amended), NULL meaning *no payload*.

- [ ] **Step 4: Retire the collection gap**

Remove `"collection_payloads_carry_no_shape"` from `metadata.py`'s gap list and its paired first sentence from `document.py`'s `_GAPS`. The lockstep test (`test_every_machine_readable_gap_has_a_sentence_a_person_can_read`) passes by construction; update `test_document_lists_every_endpoint_and_names_its_gaps` if it mentions the collection sentence.

- [ ] **Step 5: Run the full suite** (`.venv/bin/pytest -q`) — expected all green; fix any 2A assertion still expecting a bare symbol (they are all in `test_shapes.py`/`test_pipeline.py`).

- [ ] **Step 6: Commit**

```bash
git add src/sextant tests
git commit -m "feat: endpoint payloads become wire descriptors, closing the collection gap"
```

---

### Task 6: The catalog-declared body rule

**Files:**
- Modify: `src/sextant/application/resolve/shapes.py` (`_body_type`)
- Modify: `src/sextant/catalogs/spring-web.yml`, `spring-mvc.yml` (migrate `request_body_annotation` → `request_body`)
- Test: `tests/application/test_shapes.py`

**Interfaces:**
- Consumes: `catalog.matches["request_body"]` = `{"annotation": <SCIP fqn>, "fallback": "sole_unannotated" | "none"}` (Task 1's D02 grammar; SCIP form like every `matches` value).
- Produces: `_body_type(signature, catalog)` honouring the marker first, then the fallback.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_sole_unannotated_parameter_is_the_body_when_the_catalog_says_so(tmp_path):
    """Feign's contract: no annotation marks the body; being the only bare
    parameter does. The rule is catalog data — inferring it for a catalog that
    declares no fallback would be a guess presented as an observation."""
    endpoint = _resolved_bare_body_handler(tmp_path)   # catalog with fallback: sole_unannotated
    assert json.loads(endpoint["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderRequest#")


def test_two_bare_parameters_mean_no_body_at_all(tmp_path):
    """'Sole' is load-bearing: with two candidates, picking either is a coin
    flip recorded as fact."""
    endpoint = _resolved_two_bare_handler(tmp_path)
    assert endpoint["request_shape"] is None
```

- [ ] **Step 2: Watch them fail**, then implement:

```python
def _body_type(signature: dict[str, Any], catalog: Catalog) -> dict[str, Any] | None:
    """The type of the parameter the catalog's body rule marks (D02 §2 as
    amended). The marker wins; the sole-unannotated fallback exists because
    one contract (Feign's) marks the body by being the only bare parameter.
    A catalog declaring neither contributes no request shapes."""
    declared = catalog.matches.get("request_body")
    if declared is None:
        return None
    parameters = signature.get("parameters", [])
    for parameter in parameters:
        if any(
            use["annotation"] == declared["annotation"]
            for use in parameter.get("annotations", [])
        ):
            return dict(parameter["type"])
    if declared.get("fallback") == "sole_unannotated":
        bare = [p for p in parameters if not p.get("annotations")]
        if len(bare) == 1:
            return dict(bare[0]["type"])
    return None
```

- [ ] **Step 3: Migrate the two inbound catalogs** — in `spring-web.yml` and `spring-mvc.yml`, replace `request_body_annotation: org/springframework/web/bind/annotation/RequestBody#` with:

```yaml
  request_body: { annotation: org/springframework/web/bind/annotation/RequestBody#, fallback: none }
```

Grep for any remaining `request_body_annotation` reader (`_body_type` was the only one) and remove the old key everywhere.

- [ ] **Step 4: Full suite, commit**

```bash
git add src/sextant tests/application/test_shapes.py
git commit -m "feat: the request-body rule becomes catalog data with a sole-parameter fallback"
```

---

### Task 7: The three outbound catalogs, end to end

**Files:**
- Create: `src/sextant/catalogs/spring-cloud-openfeign.yml`, `spring-http-interface.yml`, `retrofit.yml`
- Test: `tests/application/test_pipeline.py` (the exact route set), `tests/e2e/test_vertical_slice.py`

**Interfaces:**
- Consumes: everything Tasks 2–6 built.
- Produces: the fixture's outbound endpoint rows, asserted exactly.

- [ ] **Step 1: Write the catalogs**

```yaml
# spring-cloud-openfeign.yml
id: spring-cloud-openfeign
displayName: Spring Cloud OpenFeign
style: annotation_driven
protocol: http
direction: outbound

detect:
  coordinates: ["org.springframework.cloud:spring-cloud-openfeign-core"]

requires: [annotation_args, typed_signatures]

matches:
  type_annotation: org/springframework/cloud/openfeign/FeignClient#
  request_body: { annotation: org/springframework/web/bind/annotation/RequestBody#,
                  fallback: sole_unannotated }
  mapping:
    path_from: [value, path]
    method_from: method
    all_methods: [GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS, TRACE]
    prefix_annotation: org/springframework/cloud/openfeign/FeignClient#
    # value aliases *name* on @FeignClient — the service id — so the prefix
    # reads only `path` and the peer reads the name (spec ruling I2).
    prefix_from: [path]
    peer_from: [name, value]
    annotations:
      - { fqn: org/springframework/web/bind/annotation/RequestMapping# }
      - { fqn: org/springframework/web/bind/annotation/GetMapping#,    method: [GET] }
      - { fqn: org/springframework/web/bind/annotation/PostMapping#,   method: [POST] }
      - { fqn: org/springframework/web/bind/annotation/PutMapping#,    method: [PUT] }
      - { fqn: org/springframework/web/bind/annotation/DeleteMapping#, method: [DELETE] }
      - { fqn: org/springframework/web/bind/annotation/PatchMapping#,  method: [PATCH] }

wrappers:
  - { type: org.springframework.http.ResponseEntity, payload_arg: 0, semantics: http_envelope }
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

```yaml
# spring-http-interface.yml
id: spring-http-interface
displayName: Spring HTTP Interface
style: annotation_driven
protocol: http
direction: outbound

# spring-web ships the annotation package, so this coordinate matches every
# Spring module — a weak discriminator, moot while catalog-module matching is
# unimplemented; the annotation match below is what actually gates.
detect:
  coordinates: ["org.springframework:spring-web"]

requires: [annotation_args, typed_signatures]

matches:
  # No type gate: @HttpExchange at type level is optional — methods alone may
  # carry the exchange annotations.
  request_body: { annotation: org/springframework/web/bind/annotation/RequestBody#,
                  fallback: none }
  mapping:
    path_from: [value, url]
    method_from: method
    all_methods: [GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS, TRACE]
    prefix_annotation: org/springframework/web/service/annotation/HttpExchange#
    prefix_from: [value, url]
    annotations:
      - { fqn: org/springframework/web/service/annotation/HttpExchange# }
      - { fqn: org/springframework/web/service/annotation/GetExchange#,    method: [GET] }
      - { fqn: org/springframework/web/service/annotation/PostExchange#,   method: [POST] }
      - { fqn: org/springframework/web/service/annotation/PutExchange#,    method: [PUT] }
      - { fqn: org/springframework/web/service/annotation/DeleteExchange#, method: [DELETE] }
      - { fqn: org/springframework/web/service/annotation/PatchExchange#,  method: [PATCH] }

wrappers:
  - { type: org.springframework.http.ResponseEntity, payload_arg: 0, semantics: http_envelope }
  - { type: reactor.core.publisher.Mono,             payload_arg: 0, semantics: async }
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

```yaml
# retrofit.yml
id: retrofit
displayName: Retrofit
style: annotation_driven
protocol: http
direction: outbound

detect:
  coordinates: ["com.squareup.retrofit2:retrofit"]

requires: [annotation_args, typed_signatures]

matches:
  # No type gate and no prefix: a Retrofit interface is its method
  # annotations, and the base URL lives in builder code (call-site phase).
  request_body: { annotation: retrofit2/http/Body#, fallback: none }
  mapping:
    path_from: [value]
    method_from: method
    all_methods: [GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS]
    prefix_annotation: null
    prefix_from: []
    annotations:
      - { fqn: retrofit2/http/GET#,    method: [GET] }
      - { fqn: retrofit2/http/POST#,   method: [POST] }
      - { fqn: retrofit2/http/PUT#,    method: [PUT] }
      - { fqn: retrofit2/http/DELETE#, method: [DELETE] }
      - { fqn: retrofit2/http/PATCH#,  method: [PATCH] }
      - { fqn: retrofit2/http/HEAD#,   method: [HEAD] }

# Shipped Jackson-converter-shaped (the common Spring Boot configuration);
# Gson/Moshi naming annotations are a later catalog addition.
wrappers:
  - { type: retrofit2.Call, payload_arg: 0, semantics: async }

serialization:
  name_from:
    - { annotation: com.fasterxml.jackson.annotation.JsonProperty, arg: value }
  ignore: [com.fasterxml.jackson.annotation.JsonIgnore]
  default_strategy: as_declared

known_types:
  - { type: java.time.Instant,    wire: string, format: date-time }
  - { type: java.math.BigDecimal, wire: number }
```

(`prefix_annotation: null` must load as `None` and the SQL's `prefixes` CTE then matches nothing — verify, don't assume; if the engine chokes on NULL here, make `prefix_annotation` optional via `mapping.get("prefix_annotation")` in `endpoints.py` instead, mirroring the type gate.)

- [ ] **Step 2: Extend the exact route set and watch it fail first**

In `test_pipeline.py`'s `test_resolve_finds_every_fixture_endpoint_exactly_once_when_run_end_to_end`, the route set gains the outbound routes (run once to see the actual derived set, then assert it exactly — expected additions, given Task 2's fixture):

```python
        # Outbound (Phase 2B): the client interfaces' declared calls.
        ("POST", "/billing/invoices"),
        ("GET", "/billing/invoices"),
        ("GET", "/v1/inventory/levels"),
        ("POST", "/v1/inventory/reserve"),
        ("GET", "legacy/invoices/{id}"),
        ("POST", "legacy/invoices"),
```

and the count assertion updates accordingly. Add direction assertions:

```python
    directions = {(e["method"], e["path"]): e["direction"] for e in report.endpoints}
    assert directions[("POST", "/billing/invoices")] == "outbound"
    assert directions[("POST", "/v1/orders")] == "both"      # the self-call merged
    peers = {e["path"]: e["peer"] for e in report.endpoints if e["direction"] != "inbound"}
    assert peers["/billing/invoices"] == "billing"
    assert peers["/v1/inventory/levels"] is None             # base URL is builder code
```

Note the `/v1/orders` route stays in the set once (it merges), and `POST /v1/orders/detailed` remains inbound-only.

- [ ] **Step 3: Run, fix, and verify the descriptor end to end**

```python
    invoices = next(e for e in report.endpoints
                    if e["method"] == "GET" and e["path"] == "/billing/invoices")
    descriptor = json.loads(invoices["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/contracts/OrderView#"
```

- [ ] **Step 4: Full suite (`.venv/bin/pytest -q`), commit**

```bash
git add src/sextant/catalogs tests
git commit -m "feat: Feign, HttpExchange and Retrofit catalogs derive the fixture's outbound calls"
```

---

### Task 8: The document — contract class diagram, contract tables, outbound section, gap rotation

**Files:**
- Create: `src/sextant/egress/render/viewmodel.py`, `src/sextant/egress/render/diagrams.py`
- Modify: `src/sextant/egress/render/document.py`, `src/sextant/egress/render/metadata.py`
- Test: `tests/egress/test_diagrams.py` (new), `tests/egress/test_render.py`, `tests/e2e/test_vertical_slice.py`

**Interfaces:**
- Consumes: `ResolveReport.shapes`, `workspace.query("shape_fields")` — `render_module_document` gains a `shape_fields: list[dict]` parameter (the CLI passes `workspace.query("shape_fields")`; `write_metadata` needs no new inputs).
- Produces: `viewmodel.ClassNode(name, fields: tuple[tuple[str, str], ...], open: bool)`, `viewmodel.ClassEdge(source, target)`, `diagrams.class_diagram(nodes, edges) -> str` (Mermaid). Document sections: `## Structure`, `## Inbound endpoints` (now with per-endpoint contract tables), `## Outbound endpoints`.

- [ ] **Step 1: Write the failing emitter test (no workspace — M07's split)**

```python
from sextant.egress.render.diagrams import class_diagram
from sextant.egress.render.viewmodel import ClassEdge, ClassNode


def test_the_emitter_draws_nodes_fields_and_references():
    nodes = [
        ClassNode("com/acme/orders/contracts/OrderRequest#",
                  (("customer_id", "string"), ("alternates", "array")), False),
        ClassNode("com/acme/orders/contracts/CustomerRef#", (("id", "string"),), False),
    ]
    edges = [ClassEdge("com/acme/orders/contracts/OrderRequest#",
                       "com/acme/orders/contracts/CustomerRef#")]
    text = class_diagram(nodes, edges)
    assert "classDiagram" in text
    assert "class OrderRequest" in text
    assert "customer_id: string" in text
    assert "OrderRequest --> CustomerRef" in text


def test_an_open_shape_is_marked_in_the_diagram():
    text = class_diagram([ClassNode("a/B#", (), True)], [])
    assert "open" in text  # rendered as a stereotype/note — exact form is the emitter's
```

- [ ] **Step 2: Implement view model and emitter**

`viewmodel.py` — two frozen dataclasses exactly as in the Interfaces block, plus `simple_name(symbol)` (`symbol.rsplit("/", 1)[-1].rstrip("#")`) used by the emitter. `diagrams.py` — a pure function assembling Mermaid `classDiagram` text line by line, deterministic order = input order, open shapes annotated `<<open>>`. No imports beyond `viewmodel`.

- [ ] **Step 3: Project and assemble the document**

In `document.py`, `render_module_document` gains `shape_fields: list[dict[str, object]] = ()`-style parameter, and the body gains, after Coverage:

```python
        "## Structure",
        "",
```

followed by the projection (a private `_contract_nodes(report.shapes, shape_fields)` building `ClassNode`s in `shapes` order with each shape's fields `(wire_name, wire_type)` in ordinal order, and `ClassEdge`s from each field's `item` JSON `shape_id` where present), emitted inside a ` ```mermaid ` fence — or, when there are no shapes, the line `None derived.`. The Inbound endpoints section keeps its summary table and adds, per endpoint with a non-NULL descriptor, an indented contract table of the referenced shape's fields (`wire_name`, `wire_type/format`, `required`, `nullable`); a descriptor with no `shape_id` renders inline (`array of object OrderView` / `string`). Add after it:

```python
        "## Outbound endpoints",
        "",
```

with a table `| Endpoint | Peer | Caller | Resolution |` over rows where `direction in ("outbound", "both")` (`peer` rendered as `unresolved` when NULL), else `None found.` — an *empty* outbound section is now a real statement, because outbound derivation exists (NFR-7).

- [ ] **Step 4: Rotate the gaps (spec ruling I3 — exhaustive, never narrowing)**

In `metadata.py`, rename the list to `KNOWN_GAPS` (it no longer describes phase 1; grep for the two references — `write_metadata` and `test_render.py`) and set:

```python
KNOWN_GAPS = [
    "call_site_clients_not_read",
    "messaging_endpoints_not_read",
    "http_exchange_inbound_use_not_detected",
    "client_base_addresses_not_resolved",
    "sequence_diagrams_pending_call_graph",
    "structure_diagram_limited_to_contracts",
    "call_graph_not_implemented",
    "maven_parent_and_profile_resolution_not_implemented",
    "catalog_module_matching_not_implemented",
    "nested_and_anonymous_classes_not_read",
    "module_classification_evidence_incomplete",
]
```

(`outbound_endpoints_not_implemented` retires — it is now false; the first two carry its remainder. The two new document-blueprint gaps make the missing diagram kinds visible per M07's amendment.) In `document.py`'s `_GAPS`, replace the outbound sentence and add matching sentences, one per new key, in the same order — e.g. "HTTP calls made through RestTemplate, WebClient or OkHttp are not read: the URL and verb live in method calls, which the scanner does not yet record."; "Messaging endpoints — listeners and producers alike — are not read: Kafka, JMS and SQS annotations have no catalog yet."; "An @HttpExchange interface implemented server-side is still reported outbound."; "Outbound base addresses configured in builder code are not resolved: those endpoints carry no peer."; "Sequence diagrams await the call graph."; "The structure diagram covers contract types only: inheritance edges are not extracted." The lockstep test enforces the pairing count.

- [ ] **Step 5: Update callers and e2e**

`cli/app.py`: both `module_analyze`'s document write path (none — analyze doesn't render) and `module_render` pass `shape_fields=workspace.query("shape_fields")`. Extend `tests/e2e/test_vertical_slice.py`'s document test:

```python
    assert "## Outbound endpoints" in document
    assert "/billing/invoices" in document
    assert "classDiagram" in document
```

- [ ] **Step 6: Full suite, commit**

```bash
git add src/sextant tests
git commit -m "feat: the document draws contracts, lists outbound calls, and rotates its gaps"
```

---

### Task 9: Workspace export — Parquet through the port

**Files:**
- Modify: `src/sextant/application/ports/workspace.py`, `src/sextant/storage/duckdb/workspace.py`
- Test: `tests/storage/test_workspace.py`

**Interfaces:**
- Produces: port methods
  `export_tables(destination: Path) -> list[str]` — writes `graph/<name>.parquet` per exported table, returns the table names written, deterministic order;
  `export_facts(destination: Path) -> int` — writes `facts/<relative_path>.parquet` per document (the raw-fact rows `kind, document_id, payload`), returns files written.
  Consumed by Task 10's CLI command.

- [ ] **Step 1: Write the failing tests**

```python
def test_exported_tables_read_back_equal_to_the_workspace_query(tmp_path: Path):
    workspace = _loaded_workspace(tmp_path)      # reuse the file's existing fact-loading helper
    written = workspace.export_tables(tmp_path / "bundle")
    assert written == ["annotations", "documents", "endpoints", "shape_fields", "shapes", "symbols"]
    back = duckdb.sql(
        f"SELECT * FROM read_parquet('{tmp_path / 'bundle' / 'graph' / 'endpoints.parquet'}')"
    ).fetchall()
    assert len(back) == len(workspace.query("endpoints"))
    workspace.close()


def test_two_exports_of_one_workspace_are_byte_identical(tmp_path: Path):
    """NFR-1 at the bundle boundary (M08). A failure here on one machine and
    not another is DuckDB's Parquet writer differing between versions —
    environment drift, not code."""
    workspace = _loaded_workspace(tmp_path)
    workspace.export_tables(tmp_path / "one")
    workspace.export_facts(tmp_path / "one")
    workspace.export_tables(tmp_path / "two")
    workspace.export_facts(tmp_path / "two")
    one = {p.relative_to(tmp_path / "one"): p.read_bytes()
           for p in sorted((tmp_path / "one").rglob("*.parquet"))}
    two = {p.relative_to(tmp_path / "two"): p.read_bytes()
           for p in sorted((tmp_path / "two").rglob("*.parquet"))}
    assert one == two and one
    workspace.close()
```

- [ ] **Step 2: Watch them fail**, then implement in `workspace.py`:

```python
    # The tables a bundle carries (D06 §5), each exported through its named
    # query so the row order is the one NFR-1 already fixed. Sorted by name so
    # the manifest's contents list is deterministic too.
    _EXPORTED_TABLES = ("annotations", "documents", "endpoints", "shape_fields", "shapes", "symbols")

    def export_tables(self, destination: Path) -> list[str]:
        graph = destination / "graph"
        graph.mkdir(parents=True, exist_ok=True)
        for name in self._EXPORTED_TABLES:
            sql = _EXPORT_QUERIES[name]
            self._connection.execute(
                f"COPY ({sql}) TO '{graph / name}.parquet' (FORMAT parquet, COMPRESSION zstd)"
            )
        return list(self._EXPORTED_TABLES)

    def export_facts(self, destination: Path) -> int:
        rows = self._connection.execute(
            "SELECT DISTINCT document_id FROM raw_facts ORDER BY document_id"
        ).fetchall()
        for (document_id,) in rows:
            target = destination / "facts" / f"{document_id}.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            self._connection.execute(
                "COPY (SELECT kind, document_id, payload FROM raw_facts "
                "WHERE document_id = ? ORDER BY rowid) "
                f"TO '{target}' (FORMAT parquet, COMPRESSION zstd)",
                [document_id],
            )
        return len(rows)
```

with `_EXPORT_QUERIES` mapping the six names to ordered SELECTs — reuse `_NAMED_QUERIES` for `documents`/`endpoints`/`shapes`/`shape_fields`, and add ordered exports for the two views: `"symbols": "SELECT * FROM symbols ORDER BY symbol"`, `"annotations": "SELECT target, annotation, args, type_path, retention FROM annotations ORDER BY target, annotation, type_path"`. `document_id` values contain no path separators beyond what the fact writer already sanitised — verify with the fixture's ids (`com/acme/orders/…`) that the partition tree mirrors the fact tree; if an id contains characters the filesystem rejects, sanitise exactly the way the fact writer does (read `factfile.py` first). Add both methods to the `Workspace` Protocol with one-line docstrings.

- [ ] **Step 3: Full suite, commit**

```bash
git add src/sextant tests/storage/test_workspace.py
git commit -m "feat: the workspace exports its tables and facts as deterministic Parquet"
```

---

### Task 10: The manifest and `sextant module export`

**Files:**
- Create: `src/sextant/egress/export/__init__.py`, `src/sextant/egress/export/manifest.py`
- Modify: `src/sextant/cli/app.py`
- Test: `tests/egress/test_manifest.py` (new), `tests/cli/test_app.py`

**Interfaces:**
- Consumes: Task 9's port methods; `metadata.json` (already written by analyze: gaps, coverage, uncovered, skipped_catalogs, module identity, scanner identity).
- Produces: `write_manifest(path, metadata: dict, source: dict, catalog_hash: str, module_commit: str, tables: list[str], facts_files: int) -> None` writing D06 §3's JSON; CLI command `sextant module export PATH [--workspace DIR] [--out DIR]` producing `<sanitised module id>@<commit>/` with `manifest.json`, `graph/`, `facts/`.

- [ ] **Step 1: Write the failing manifest test**

```python
def test_the_manifest_carries_provenance_coverage_and_contents(tmp_path: Path):
    metadata = {
        "module": {"id": "com.acme:orders-service", "kind": "service", "languages": ["java"]},
        "provenance": {"commit": "a3f91c", "sextant_version": "0.1.0",
                        "fact_schema_version": "1.0.0",
                        "scanners": [{"id": "asm", "version": "9.7"}]},
        "coverage": {"documents": 4, "partial_documents": 0},
        "gaps": ["call_site_clients_not_read"],
        "uncovered": [],
        "skipped_catalogs": [],
        "shapes": {"count": 2, "unexpanded_types": []},
    }
    write_manifest(tmp_path / "manifest.json", metadata,
                   source={"repo": "git@github.com:acme/orders.git", "commit": "a3f91c"},
                   catalog_hash="sha256:abc", module_commit="a3f91c",
                   tables=["endpoints", "shapes"], facts_files=4)
    written = json.loads((tmp_path / "manifest.json").read_text())
    assert written["producer"]["catalog_hash"] == "sha256:abc"
    assert written["source"]["module_commit"] == "a3f91c"
    assert written["contents"] == {"facts": True, "graph": True,
                                    "tables": ["endpoints", "shapes"], "facts_files": 4}
    assert written["environments"] == []          # nothing resolves profiles yet — honest
    assert written["gaps"] == ["call_site_clients_not_read"]
    assert written["coverage"]["partial"] is False
```

- [ ] **Step 2: Implement `manifest.py`**

A single `write_manifest` in `metadata.py`'s style: assemble the dict (module, source + `module_commit`, producer — versions copied from `metadata["provenance"]` plus `graph_schema_version` from `domain.version`, scanners, `catalog_hash`, `redaction_set_hash` read from `metadata["provenance"]` if present else omitted — check what analyze writes and carry exactly what exists), `environments: []`, coverage with a computed `partial` bool (`partial_documents > 0` or the metadata's own flag), `gaps`/`uncovered`/`skipped_catalogs` carried verbatim, `contents` as asserted above; `json.dumps(..., indent=2, sort_keys=True) + "\n"`.

- [ ] **Step 3: The CLI command**

In `cli/app.py`:

```python
@module.command("export")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def module_export(path: Path, workspace_dir: Path | None, out_dir: Path | None) -> None:
    """Writes the analysis out as a D06 bundle: Parquet plus a manifest. Reads
    what `analyze` left — it never re-analyzes (M08). Publishing the directory
    anywhere is the caller's business; Sextant does not talk to artifact
    stores."""
    workspace_dir = _workspace_dir_of(path, workspace_dir)
    metadata_path = workspace_dir / "metadata.json"
    db_path = workspace_dir / "workspace.duckdb"
    if not metadata_path.is_file() or not db_path.is_file():
        raise click.ClickException(
            f"no analysis found at {workspace_dir} — run `sextant module analyze {path}` first."
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    commit = str(metadata["provenance"]["commit"])
    bundle_name = re.sub(r"[^A-Za-z0-9._-]", "-", str(metadata["module"]["id"])) + "@" + commit
    bundle = (out_dir or workspace_dir / "bundles") / bundle_name

    workspace = DuckDbWorkspace(db_path)
    try:
        tables = workspace.export_tables(bundle)
        facts_files = workspace.export_facts(bundle)
    finally:
        workspace.close()
    write_manifest(
        bundle / "manifest.json",
        metadata,
        source={"repo": _remote_of(path), "commit": commit, "module_commit": _module_commit_of(path)},
        catalog_hash=_catalog_hash(catalogs_dir()),
        module_commit=_module_commit_of(path),
        tables=tables,
        facts_files=facts_files,
    )
    click.echo(str(bundle))
```

with three small helpers beside `_commit_of` (same `subprocess.run` shape, `check=False`, empty-safe): `_remote_of` (`git -C path remote get-url origin`, `"unknown"` fallback), `_module_commit_of` (`git -C path log -1 --format=%H -- .`), and `_catalog_hash` (sha256 over sorted `(p.name, p.read_bytes())` of `catalogs_dir().glob("*.yml")`, returned as `"sha256:" + hexdigest`). Add a CLI test in `tests/cli/test_app.py` following its existing CliRunner pattern: analyze the fixture into tmp, run export, assert the bundle directory exists with `manifest.json`, `graph/endpoints.parquet`, and a non-empty `facts/` tree.

- [ ] **Step 4: Full suite, commit**

```bash
git add src/sextant tests
git commit -m "feat: sextant module export writes the D06 bundle"
```

---

### Task 11: Export end to end and the determinism gate

**Files:**
- Test: `tests/e2e/test_vertical_slice.py`

**Interfaces:**
- Consumes: Tasks 9–10.

- [ ] **Step 1: Extend the double-run e2e**

In `test_output_is_byte_identical_when_the_pipeline_runs_twice`, add `"export"` to the command loop (it takes the same `path`/`--workspace` arguments) and extend `_fingerprint`'s suffix set with `".parquet"` — the fingerprint then covers both bundles' Parquet and manifests, so one assertion guards facts, metadata, document, and bundle at once.

- [ ] **Step 2: Add the read-back and manifest assertions**

```python
def test_the_bundle_answers_what_the_workspace_answered(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)          # analyze + render
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["producer"]["catalog_hash"].startswith("sha256:")
    assert "call_site_clients_not_read" in manifest["gaps"]
    assert "endpoints" in manifest["contents"]["tables"]
    rows = duckdb.sql(
        f"SELECT direction, count(*) AS n FROM read_parquet('{bundle / 'graph' / 'endpoints.parquet'}') "
        "GROUP BY direction ORDER BY direction"
    ).fetchall()
    assert ("outbound", ANY_POSITIVE := rows) is not None  # replace with the exact counts observed
```

Replace the last assertion with the exact per-direction counts once observed (exact-list discipline — the fixture is fixed, so the counts are too; expected: inbound from the existing set, six-ish outbound minus the merged one, one `both`).

- [ ] **Step 3: Full suite, commit**

```bash
git add tests/e2e/test_vertical_slice.py
git commit -m "test: the bundle is deterministic and answers what the workspace answered"
```

---

### Task 12: Close-out bookkeeping — COVERAGE, roadmap, stale docstring

**Files:**
- Modify: `docs/COVERAGE.md` (§5.2 rows + regenerate §2), `docs/superpowers/plans/2026-08-28-phase-2-roadmap.md`, `src/sextant/ingress/extract/jvm/scanner.py` (docstring only)

- [ ] **Step 1: COVERAGE** — in §5.2, split the combined Java outbound annotation row (`Feign @FeignClient, Retrofit @GET, Spring @HttpExchange, Micronaut @Client, MicroProfile @RegisterRestClient`) so the three shipped libraries carry `✅ shipped` and Micronaut/MicroProfile keep tier A; update the "What ships today" prose (outbound annotation clients + export now ship). Run `python3 scripts/coverage_matrix.py && python3 scripts/coverage_matrix.py --check`.
- [ ] **Step 2: Roadmap** — mark 2A and 2B delivered, insert the call-site clients phase between 2B and 2C (user priority: functional Spring Boot before messaging), and add the enrich phase with a pointer to the spec's §6.
- [ ] **Step 3: Scanner docstring** — `AsmScanner`'s class docstring still says "Phase 1 declares two capabilities"; correct to the four it declares (the set literal two lines above it is the source of truth). Doc-accuracy only; no behaviour.
- [ ] **Step 4: Full gates and commit**

Run: `scripts/check.sh` — expected: all green, including gradle (no Java changes this phase, but the gate is the gate).

```bash
git add docs src/sextant/ingress/extract/jvm/scanner.py
git commit -m "docs: record what Phase 2B shipped"
```

---

## Self-review against the spec

**Coverage.** Spec §1 (engine generalisations, catalogs, peer/caller/merge) → Tasks 3, 4, 7. §2 (descriptors, shape reuse, D01/D02 amendments) → Tasks 1, 5, 6. §3 (exporter, manifest, determinism, layout, resolved open decisions) → Tasks 1, 9, 10, 11. §4 (fixtures, testing, gap rotation, outbound counts) → Tasks 2, 7, 8, 11. §5 (document blueprint, M07, emitter split) → Tasks 1, 8. §6 (later phases) → Task 12's roadmap entry; no code, by design. Spec rulings I1/I2/I3 → Tasks 1+3+4, 3, 8 respectively; I4/I5 pins → Tasks 9, 10; I6/I7 notes → Tasks 9 (test message), 7 (catalog comment).

**Known deviations, argued:** export orchestration lives in the CLI composition root, not `application/stages` (layering: application may not import egress — the `analyze`+`write_metadata` precedent; spec intent preserved). `metadata.py`'s list renames to `KNOWN_GAPS` because it no longer describes phase 1 — mechanical, two references.

**Type consistency checked:** `_payload_descriptor` consumes `_described`'s dict and serialises with the same `sort_keys`/separators as `_item_of`; `export_tables` returns the same list the manifest's `contents.tables` asserts; `render_module_document`'s new parameter is threaded through both CLI paths; the merge SQL's `min(caller)` matches the determinism constraint; Task 7's route additions match Task 2's fixture paths (including Retrofit's un-prefixed `legacy/…` form and the `createOrder` relocation caveat, which Task 2 resolves and Task 7 must re-check against the report).

**Placeholder scan:** the one deliberately deferred value is Task 11's exact per-direction counts, which the exact-list discipline requires be read off the first real run and then frozen — stated as such, not TBD.
