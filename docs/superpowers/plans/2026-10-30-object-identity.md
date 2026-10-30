# Follow the Object — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the eight defects the 2026-10-30 review found, where a value was read without the object or call path it belongs to, before the Vert.x work starts.

**Architecture:** There are eight parts, one per ruling, each landing as its own PR, in the spec's §3 order. Most parts reuse the existing readers that track the call path: `producer_paths`, `resolve_positions(within=)` and the `captured_at` stamp. New pieces:
- a row id on endpoints (part 1);
- a `returns_receiver` catalog flag, read by both walks (part 5);
- a `dispatcher` catalog key (part 7);
- one extractor widening: a field written from `new X(…)` (part 4).

**Tech Stack:** Python 3.12, DuckDB, pytest, Java 21 + ASM extractor (`extractor-jvm/`, Gradle), YAML catalogs.

**Spec:** `docs/superpowers/specs/2026-10-30-object-identity-design.md`. The interface maps behind this plan are in the session scratchpad and are not needed to execute it.

## Global Constraints

- **Gate:** `PATH=.venv/bin:$PATH JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh` passes before every commit.
- **Fixtures:** build them with JDK 21, never 27. The stamp only fingerprints content, so to force a rebuild delete `fixtures/<name>/target` and run `JAVA_HOME=$(brew --prefix openjdk@21) .venv/bin/python tests/fixture_build.py`.
- **Extractor jar:** after any change under `extractor-jvm/`, rebuild with `(cd extractor-jvm && ./gradlew --quiet build)` before pytest.
- **Failing test first** (GUIDELINES §4.1), for every behaviour change.
- **Guards:** every new rule gets a guard in `scripts/guard_check.py` (`Guard(what, why, edits=(Edit(path, find, replace),))`) and a test marked `@pytest.mark.pins("<id>")`. The guard is measured killed: `.venv/bin/python scripts/guard_check.py <id>` reports the test failing under the mutation.
- **Field pins and the value walk:** any task that changes what the walk or an engine reads runs `.venv/bin/python scripts/field_check.py` (all six pins). The walk is also measured with `.venv/bin/python scripts/measure_value_walk.py --json <file>` before and after, on the **same** corpora state, without rebuilding `examples/` in between. Every movement is explained in the PR body.
- **No framework type in an engine.** Catalogs name framework types; engines read catalog keys.
- **Per-item loop.** Implement, gate, review, fix Critical and Major findings, record the rest in Plane and `docs/open-issues.md`'s id map, then commit.
- **One PR per part.** Part 1 goes on `fix/object-identity`, which already carries the spec and this plan. Each later part gets its own branch, `fix/object-identity-<n>`, cut from `main` once the previous part has merged. If it hasn't merged yet, cut from the previous part's branch and use that branch as the PR base. Never push to a PR that is under review.
- **Plain language** in commit messages, PR bodies, docs and catalog comments.
- **`GRAPH_SCHEMA_VERSION` goes 10 → 11 once**, in part 1, which is where the schema changes. Part 4 needs no bump, because it uses the existing `value` slot (see its decisions). The spec expected a bump shared between parts 1 and 4, and one bump in part 1 covers that. This plan does not change `FACT_SCHEMA_VERSION`.

## Review Focus

Each line below names an input that no ruling's own test covers. Every line also has a test in the task named after it.
1. **A builder built twice:** `b.url(a); r1 = b.build(); b.url(c); r2 = b.build();` gives r1 the URL `a` and r2 the URL `c`. Configuration made after a build never reaches the request already built. (Task 8)
2. **A shared request helper called by two callers**, with `"svc-a"` and `"svc-b"`: two rows, each with its own caller's value, never one row holding both values. (Task 11)
3. **Two objects of one class in one method, one of them passed to a helper that sets its field:** a read on that object includes the helper's write, and a read on the other object does not. (Task 6)
4. **A header written at mint time by `fluent` or `single_call`, on a module with a context path:** the header still belongs to its row after the prefix is applied. (Task 2)
5. **One base mapping, two subclasses, one of which overrides it:** the overriding subclass publishes only its own mapping, and the other publishes the inherited one, each under its own prefix. (Task 15)

---

## Task 0: Log the Minor findings

**Files:**
- Modify: `docs/open-issues.md` (id map; next id OI-236)

- [ ] **Step 1:** Create one Plane work item per spec §4 bullet, eight in all, OI-236 to OI-243, in project SEXTANT. Label each `needs-triage`, title it `OI-<n> — <bullet's bold phrase>`, and use the bullet's text as the body.
- [ ] **Step 2:** Add the eight rows to the id map in `docs/open-issues.md`, in the existing `| OI-n | [SEXTANT-x](…) | title |` form, and set the next id to OI-244.
- [ ] **Step 3:** Commit: `docs(issues): OI-236..243 — the review's Minor findings`.

---

## Part 1 — Ruling 7: every endpoint row has a stable id

**The decision:** `endpoints` gains `row_id BIGINT`, which every writer supplies explicitly. It is never a column DEFAULT, because `_add_columns_the_schema_has_gained` copies only the type (`workspace.py:2273`). It is minted as `(SELECT coalesce(max(row_id), 0) FROM endpoints) + row_number() OVER (ORDER BY <the insert's explicit order>)`, which is deterministic (NFR-1). Data attached to a row is bound to its `row_id` **when it is written**, by the identity columns as minted, before any pass has rewritten them. Every later pass matches on `row_id`.

The id lives only for one resolve and names nothing outside it. The parquet export and the bundle therefore leave it out (`SELECT e.* EXCLUDE (row_id) …`), which keeps D06 unchanged.

### Task 1: Mint `row_id` on every inserted endpoint row

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql:12-64` (add `row_id BIGINT`)
- Modify: `src/sextant/storage/duckdb/insert_endpoints.sql:37-58`, `src/sextant/storage/duckdb/derive_call_endpoints.sql:34-118`
- Modify: `src/sextant/storage/duckdb/workspace.py:1384-1391` (export: `EXCLUDE (row_id)`)
- Modify: every test that does `INSERT INTO endpoints` directly. They are listed in the map: `tests/storage/test_workspace.py`, `test_request_requirements.py`, `test_endpoints.py`, `test_self_calls.py`, `test_self_exchange.py`, `test_routing_conflicts.py`, `test_rpc_hops.py`, `test_endpoint_attributes.py`, `test_roots.py`. Each supplies `row_id` explicitly.
- Test: `tests/storage/test_workspace.py`

**Interfaces:**
- Produces: column `endpoints.row_id BIGINT NOT NULL` (NOT NULL is enforced by the inserts, not by a constraint, for the migration reason above), unique within a resolve. `workspace.query("endpoints")` returns it on every row.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_endpoint_row_carries_a_unique_row_id(tmp_path): ...
    # derive two catalogs' rows (one annotation_driven via endpoints_insert, one via call_endpoints)
    # assert all(r["row_id"] is not None for r in rows)
    # assert len({r["row_id"] for r in rows}) == len(rows)

def test_row_ids_are_the_same_on_a_second_resolve_of_the_same_facts(tmp_path): ...
    # resolve twice; assert [(r["row_id"], r["path"]) for r in first] == [... second]

def test_the_exported_endpoints_table_has_no_row_id(tmp_path): ...
```

- [ ] **Step 2:** Run `.venv/bin/pytest tests/storage/test_workspace.py -k row_id -q`. Expect a FAIL with `KeyError: 'row_id'`, or with the column missing.
- [ ] **Step 3:** Add the column and mint it in both INSERTs, using the expression from the part 1 decision, ordered by the INSERT's own `ORDER BY`. Add one if it has none: `protocol, direction, method, path, handler, caller, peer`. Update every direct `INSERT INTO endpoints` in the tests.
- [ ] **Step 4:** Run the three tests and the full gate. Expect PASS. `test_pipeline.py`'s "no slow-route retries" assertion must still pass.
- [ ] **Step 5:** Commit: `feat(endpoints): every row is minted with a row id`.

### Task 2: Attached data binds to `row_id`; every rewrite matches on it

**Files:**
- Modify: `reset_route_requirements.sql:10-13`, `insert_route_requirements.sql:6-17` (add `row_id`, bound at insert by joining `endpoints` on `(caller, handler, method, path, catalog_id)`)
- Modify: `src/sextant/application/resolve/request_requirements.py:127-150` (`_from_stash` joins on `row_id`)
- Modify: `schema.sql:629-` `endpoint_metadata` (add `row_id`), `insert_endpoint_metadata.sql:25-50` (bind `row_id` at insert by the identity columns)
- Modify, so each matches on `row_id` (its `$rows` STRUCT carries `row_id` instead of the six identity columns):
  - `prefix_endpoint_paths.sql`, which also updates `endpoint_metadata.path` for the same `row_id`;
  - `reclassify_protocol.sql`;
  - `stamp_format.sql`;
  - `bind_request_shape.sql`;
  - `drop_self_call_endpoints.sql`;
  - the Python builders `path_prefix.py:61,143`, `protocol_hint.py:172,197`, `format.py:124,158`, `shapes/parse_binding.py:126,434` and `self_calls.py:40,90`.
- Modify: `src/sextant/domain/version.py:151` (`GRAPH_SCHEMA_VERSION = 11`, with a numbered history paragraph), `CHANGELOG.md`, `docs/components/D01-graph-schema.md` (versions table and the `endpoint_metadata` "carried rather than joined" paragraph at `schema.sql:630-632`, restated), `tests/application/boundary/test_diff.py`, `tests/application/boundary/test_source.py` (version stamps)
- Modify: `fixtures/orders-contextpath`, adding `RouterConfig.java`: a Spring MVC `RouterFunction` serving `GET /versioned` only with header `X-Ver: 2`
- Test: `tests/application/test_request_requirements.py`, `tests/application/test_path_prefix.py`, `tests/e2e/test_rest_inbound_delivered.py`

**Interfaces:**
- Consumes: `endpoints.row_id` (Task 1).
- Produces: `route_requirements.row_id`, `endpoint_metadata.row_id`. Each rewrite SQL takes `$rows` with `row_id` plus its new value (`prefixed`, `reclassified`, …).

- [ ] **Step 1: Write the failing tests**

```python
def test_a_prefixed_route_keeps_its_header_requirement(tmp_path):
    # stash a requirement X-Ver=2 for GET /x, apply prefix "/shop", record_request_requirements
    # assert entries == [{"path": "/shop/x", "kind": "header", "name": "X-Ver", ...}]

def test_a_header_written_at_mint_time_follows_its_row_through_the_prefix(tmp_path):   # Review Focus 4
    # endpoint_metadata row written for GET /x before apply_path_prefixes("/shop")
    # assert the metadata row's path == "/shop/x" and its row_id == the endpoint's

def test_no_attached_row_is_left_naming_a_path_no_endpoint_has(tmp_path):
    # run the whole pipeline on orders-contextpath; for every table holding endpoint
    # identity columns (endpoint_metadata, route_requirements, open_questions), assert each
    # row's (protocol, method, path) matches a live endpoints row
```

Also an e2e test, `test_a_prefixed_functional_route_keeps_its_header` (in `test_rest_inbound_delivered.py`, using the `context_path_rows` fixture), which asserts that the row for `GET /shop/api/versioned` carries the requirement `X-Ver: 2`.

- [ ] **Step 2:** Run them. Expect FAILs: the requirement and the header are lost.
- [ ] **Step 3:** Bind `row_id` at insert in both attachment tables, then switch every rewrite above to `row_id`. If `test_no_attached_row…` still finds an orphan, `open_questions` included, add `row_id` to that table the same way. The test stays general: it must not name tables one by one in its assertion.
- [ ] **Step 4:** Add the guard `endpoints.a-rewrite-matches-a-row-by-its-ROW-ID`. Its edit makes `prefix_endpoint_paths.sql` match on `path` again, and `test_a_prefixed_route_keeps_its_header_requirement` pins it. Measure the guard killed.
- [ ] **Step 5:** Bump the graph schema to 11 and update the docs and version stamps listed above. Run the gate and `field_check.py`; all six pins must hold unchanged.
- [ ] **Step 6:** Commit: `fix(endpoints): data attached to a row follows it by row id, not by path (ruling 7)`. Open the PR (auto-fix on, per memory) only after the user says go.

---

## Part 2 — Ruling 2: a value id always travels with its method

**The decision:** `_own_parameter` (`chains.py:2141`) becomes `_own_method(argument, site)`. It stamps `caller = site["caller"]` on **every** argument dict, of every kind, recursively through `elements` and `candidates`. Every reader that follows a value id then looks it up in that argument's own method:
- sites through `workspace.once(call_site_index).by_caller[argument["caller"]]`;
- parameters through `declared_parameters_of(workspace)[argument["caller"]]`.

The enclosing chain's `caller_call_sites` is never used for this. `single_call.py:546` already does the same for lambda bodies and is the precedent.

### Task 3: Stamp every lifted argument; switch the four readers

**Files:**
- Modify: `src/sextant/application/resolve/shapes/chains.py:2104-2108,2141` (`_own_method`)
- Modify: `src/sextant/application/resolve/shapes/arguments.py`. The readers are:
  - `_properties_getter_expression` (:1186);
  - `_linked_constructor` (:1654);
  - `_reference_of`'s `parameter` branch (:1532) and its `call_wrappers` branch (:1557).
  Each takes the argument's own sites through a new helper.
- Modify: `scripts/guard_check.py`
- Test: `tests/application/test_call_engines.py` (beside `test_a_url_built_inside_a_uri_lambda_is_read`, :4380), `tests/application/test_fluent_registrations.py`

**Interfaces:**
- Produces: `def sites_of(argument: Mapping[str, Any], reads: _Reads) -> list[dict[str, Any]]` and `def parameters_of(argument: Mapping[str, Any], reads: _Reads) -> tuple[dict[str, Any], ...]` in `shapes/arguments.py`. Each takes the method from `argument["caller"]`. An argument without `caller` raises `ValueError("argument carries no method")`, because every builder now stamps one.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_value_read_in_a_lambda_is_never_looked_up_in_the_enclosing_method(tmp_path):
    # enclosing caller: site ordinal k with result=20 = BillingProperties#getUrl() (bound prefix "billing")
    # lambda body: b.path(<unresolved source=20>) where 20 = other.compute("k")
    # rows = _resolve_fluent(...); assert rows[0]["path"] != "${billing.url}"
    # assert rows[0]["resolution"] != "resolved"

def test_a_lambda_parameter_used_as_a_body_is_typed_by_the_lambdas_signature(tmp_path): ...
    # body: arg0 inside the lambda is lambda parameter 1; enclosing method's parameter 1 is a different type
    # assert request_shape is the lambda's parameter type, not the enclosing one's

def test_every_captured_argument_carries_its_own_method(): ...
    # _resolve_captures over a step with arg0 of each kind (string, unresolved, array of parameter, merge)
    # assert every dict, nested included, has "caller" == site["caller"]
```

- [ ] **Step 2:** Run them. Expect the first two to FAIL: today they publish `${billing.url}` and the enclosing method's type.
- [ ] **Step 3:** Implement `_own_method`, `sites_of` and `parameters_of`, and switch the four readers. Keep the `across_bodies` refusal on the bean hop unchanged: it is already correct.
- [ ] **Step 4:** Add the guard `chains.a-LIFTED-argument-carries-its-own-method`. Its edit makes `_own_method` stamp only `kind == "parameter"`, and it is pinned by the first test. Measure it killed.
- [ ] **Step 5:** Run the gate and `field_check.py`. Expect no movement in the pins.
- [ ] **Step 6:** Commit: `fix(chains): a value id is read in the method it belongs to (ruling 2)`.

---

## Part 3 — Ruling 6: string concatenation keeps every calling context

**The decision:** In `_Walk._joined` (`values.py:1574`), the `settled` filter (:1669-1674) becomes a per-path mapping that drops nothing. For every `(crossed, answer)` an operand reaches, the hole gets one candidate **on that crossed trail**:
- a string `LITERAL` gives its text, which already covers a source-stated `${…}`;
- an `EXPRESSION` for which `carries_expression(text)` holds gives its text;
- anything else gives `None`, so the hole keeps its spelling (`{param}`, or `{}`, which renders as `<host>` when it leads, per OI-152).

The fallback `(trail, None, …)` applies only when the operand reached nothing at all. The early return at :1686 stays.

### Task 4: One template per calling context

**Files:**
- Modify: `src/sextant/application/resolve/values.py:1661-1674`
- Modify: `scripts/guard_check.py`
- Test: `tests/application/test_values.py` (near :2732), `tests/e2e/test_rest_outbound_delivered.py` (near :411)

- [ ] **Step 1: Write the failing tests**

```python
def test_a_concat_hole_keeps_a_calling_context_it_cannot_fill(walked):
    # fetch(String host){ one("http://" + host + "/x"); }  a(){ fetch("svc-a"); }  b(String p){ fetch(p); }
    # assert sorted(_values(walked, fetch, 1)) == [("expression", "http://{host}/x"), ("literal", "http://svc-a/x")]

def test_a_helper_concat_called_with_an_unknown_host_publishes_no_peer(tmp_path):
    # through fluent/single_call: the row's peer is None (authority_of sees two answers)
```

- [ ] **Step 2:** Run them. Expect FAILs: today there is one literal answer only.
- [ ] **Step 3:** Implement the decision above. Existing hole tests (:2695-2732) and `test_call_engines.py:1326-1414` must still pass. If one moves, stop and say why in the commit body.
- [ ] **Step 4:** Add the guard `values.a-concat-hole-REPLACES-what-it-cannot-fill-never-drops-it`, which restores the `if answer.kind == LITERAL …` filter. Pin it to the first test and measure it killed.
- [ ] **Step 5:** Run `measure_value_walk.py` before (on `main`) and after, on the same corpora state, then `field_check.py`. List every site that gained a second answer in the PR body, with the reason. A gained answer is expected; a lost answer is a defect.
- [ ] **Step 6:** Commit: `fix(values): a concatenation hole keeps every calling context (ruling 6)`.

---

## Part 4 — Ruling 1: a field is read per object

**The decisions:**
1. **The fact.** For `this.f = new X(…)` (PUTFIELD) and `F = new X(…)` (PUTSTATIC), the extractor emits a `field_write` whose existing `value` slot holds the grammar's own `instance` entry, `{kind: instance, symbol: X, source: <NEW's index in the full InsnList>}`. This uses the existing `value` slot rather than a new `from_value` key, which deviates from the letter of the sixth-edge spec but carries the same information: the index of the stored value. `FieldWriteFact._one_source`, the `field_writes` view and the fact-additivity probe stay as they are, and `FACT_SCHEMA_VERSION` does not move (an additive value of an existing key).
   - Python routes the entry into `ValueIndex.produced`, because it has a `source` and a `written_by`. The walk already answers it through `_entry`'s `instance` arm, so the field holds the construction.
2. **The read.**
   - **When it applies:** the walk entered a getter of field `F` through call site `S`, the same test `_unseen_object` uses (`frames[-1]`). The rule is skipped for a `static` field.
   - **Finding the objects:** run `producer_paths(index, S, RECEIVER, {(owner_of(F), "<init>")})` to get the constructions the receiver can be.
   - **Fallback:** if any end is not a construction of `F`'s owner, the read answers as it does today.
   - **Each construction `C = (caller, ordinal)` answers only its own object's writes:**
     - (a) **constructor writes:** writes `<init>` makes without a parameter, plus `<init>`'s parameter writes, read as the argument at `C`'s own site;
     - (b) **setter writes:** every call to a method that writes `F` (a `writers` or `constants` entry whose writer is not `<init>`) whose receiver's constructions include `C`, again from `producer_paths` with the same declared set. Its parameter write is read as that site's argument, its constant write as the literal.
     - A setter site whose receiver has an end that is **not** a construction (an unbound parameter, a library call) may be any object. It is included for every `C`, marked `inexact`.
   - **Caching:** the setter sites per field are cached on the walk, keyed on `F`.
3. **Coherence.**
   - Every answer from (a) or (b) is on the step `_Step((_OBJECT_OF, owner_of(F)), f"{C[0]}@{C[1]}")`, so `pair(a.getCron(), a.getZone())` never crosses objects.
   - Every write answer, on any route including today's, is also on `_Step((_WRITE_OF, F), f"{writer}@{site or '-'}")`, so two reads of one field never pair two different writes.

A direct `other.f` read, which carries no receiver in the grammar, is out of scope and keeps today's answer. It is recorded below as a residual.

### Task 5: The extractor reports a field written from `new`

**Files:**
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java:379-404` (in the `else` branch, before `callBefore`: if the value at the PUTFIELD/PUTSTATIC is a `NEW` in the same basic block, found through the frame's `singleSource`, the write is `fieldWriteJson(..., -1, producerJson(newInsn, …))`. Always use `method.instructions.indexOf(newInsn)`, never an index into `real`. Update the comment at :385-387.)
- Modify: `extractor-jvm/src/test/java/dev/sextant/extractor/FieldWriteScanTest.java:402-405`
- Modify: `docs/components/D00-fact-schema.md:1166-1240` (the `field_write` paragraph: a value built with `new` now reports its `instance` entry; this is the fourth widening in History)
- Test: `FieldWriteScanTest.java`, `tests/scripts/test_fact_additivity.py`

- [ ] **Step 1: Write the failing test.** Rename `emits_nothing_for_a_value_built_with_new` to `emits_the_constructed_instance_for_a_value_built_with_new`. It asserts one `field_write` line containing `"kind":"instance"` and a `source` equal to the `NEW`'s `indexOf`. Add `emits_the_constructed_instance_for_a_static_field_built_with_new` with a `static final Api A = new Api("/a")` sample.
- [ ] **Step 2:** Run `(cd extractor-jvm && ./gradlew --quiet test --tests '*FieldWriteScanTest*')`. Expect a FAIL.
- [ ] **Step 3:** Implement it, then rebuild the jar.
- [ ] **Step 4:** Run the Gradle tests and `.venv/bin/pytest tests/scripts/test_fact_additivity.py -q`. Expect PASS, with `FACT_KEYS` unchanged.
- [ ] **Step 5:** Commit: `feat(extractor): a field written from new X(…) reports the instance it holds`.

### Task 6: A field read answers its own object's writes

**Files:**
- Modify: `src/sextant/application/resolve/values.py`. In `_binding` (:2430), a new `_object_writes(symbol, site, trail, frames)`, called before `_binding_writes` when the decision 2 condition holds. Add the step labels `_OBJECT_OF = "object-of"` and `_WRITE_OF = "write-of"` next to `_CALLER_OF` (:226). Add the `_WRITE_OF` step in `_binding_writes` (:2516).
- Modify: `scripts/guard_check.py`
- Test: `tests/application/test_values.py`, as a new block beside the OI-222 block (:3246), with its own fixture built like `unseen` (:3495)

**Interfaces:**
- Consumes: Task 5's facts (an `instance` entry in `produced`).
- Produces: `_Walk._object_writes(self, symbol: str, site: tuple[str, int], trail: _Trail, frames: _Frames) -> tuple[_Reached, ...] | None`. `None` means "not object-scoped, answer as today".

- [ ] **Step 1: Write the failing tests** (facts built with `_site`, `_setter`, `_returns`, `_declared`):

```python
def test_a_setter_value_is_read_only_on_the_object_it_was_set_on(objects):
    # Row a=new Row(); a.setCron("A"); Row b=new Row(); b.setCron("B"); one(a.getCron())
    assert _values_and_reasons(objects, make, ONE_A) == [("A", "None")]

def test_two_fields_of_one_object_never_pair_with_another_objects(objects):
    # pair(a.getCron(), a.getZone()) with a: ("A","ZA"), b: ("B","ZB")
    assert _pairs(objects, make, PAIR) == [("A", "ZA")]

def test_a_field_written_in_two_methods_and_read_twice_pairs_one_write(objects):
    # m1(){this.host="h1";} m2(){this.host="h2";} rd(){pair(this.host, this.host);}
    assert sorted(_pairs(objects, rd, PAIR)) == [("h1", "h1"), ("h2", "h2")]

def test_an_object_built_into_a_field_is_read_through_its_own_construction(objects):
    # ruoyi shape: Props#<init>{ admin = new Api("/admin-api"); app = new Api("/app-api"); }
    # one(props.getAdmin().getPrefix())
    assert _values_and_reasons(objects, reader, ONE_PREFIX) == [("/admin-api", "None")]

def test_a_setter_called_by_a_helper_on_the_object_counts_for_that_object_only(objects):  # Review Focus 3
    # Row a=new Row(); Row b=new Row(); fill(a); one(b.getCron()); one(a.getCron())
    # fill(Row r){ r.setCron("F"); }   Row#<init> sets cron="D"
    assert _values_and_reasons(objects, make, ONE_B) == [("D", "None")]
    assert sorted(_values_and_reasons(objects, make, ONE_A)) == [("D", "None"), ("F", "None")]

def test_a_setter_on_an_object_of_unknown_origin_stays_possible_and_inexact(objects): ...
```

- [ ] **Step 2:** Run them. Expect FAILs: today they return the field-wide union.
- [ ] **Step 3:** Implement decision 2 and decision 3. The OI-222 tests (:3515-3559) and `test_a_binding_read_follows_the_writer_the_facts_name` (:1976) must still pass.
- [ ] **Step 4:** Add the guards and measure each killed:
  - `values.a-field-read-answers-ITS-OWN-OBJECTS-writes`: the edit makes `_binding` skip `_object_writes`. Pinned by the first test.
  - `values.two-reads-of-one-field-pair-ONE-write`: the edit drops the `_WRITE_OF` step. Pinned by the third test.
- [ ] **Step 5:** Commit: `fix(values): a field read answers its own object's writes (ruling 1)`.

### Task 7: Fixtures, pins and the measurement for part 4

**Files:**
- Modify: every fixture's `target/` (deleted and rebuilt with JDK 21), and goldens if an expected value moves
- Modify: `docs/superpowers/specs/2026-10-18-the-sixth-edge-design.md` §8 (the second half of step 2 is built, with the measured result), `CHANGELOG.md`
- Test: `tests/e2e/test_kafka_delivered.py` (`orders-fieldheld`)

- [ ] **Step 1:** Run `measure_value_walk.py --json /…/scratchpad/walk-before.json` on `main`'s jar and code.
- [ ] **Step 2:** Rebuild the fixtures with JDK 21, then run the gate. Expect PASS. Any expected value that moves is either a correction with a stated reason, or a defect to fix now.
- [ ] **Step 3:** Run `measure_value_walk.py --json …/walk-after.json` on the same corpora, then `field_check.py`. In the PR body, report:
  - sites with fewer answers (the point of this part);
  - sites with more answers;
  - the change in `bindings max` and visits, which must not regress past the sixth-edge spec §7 figures by more than 10% (§8.7). A larger regression is a Major finding to fix.
- [ ] **Step 4:** Check the spec §5 prediction on ruoyi-vue-pro: the `getAdminApi().getPrefix()` sites answer `/admin-api` only. Write a one-off read with `resolve_site` on its built module, and record the result in the PR body.
- [ ] **Step 5:** Update the sixth-edge spec §8 and the CHANGELOG. Record two residuals in Plane as the next OIs:
  - "a direct `other.f` read carries no receiver";
  - the sixth-edge spec §4 case, `setTopic("a"); setTopic("b")` on one object. Both writes belong to the same object, so part 4 does not reduce them to the last write; this is a matter of statement order, not object identity.
- [ ] **Step 6:** Commit: `docs(values): the sixth edge's step 2 is built — measured`.

---

## Part 5 — Ruling 4: a call that returns its own receiver configures it

**The decision:** A step declared `returns_receiver: true`, or a terminal written in dict form `{method: m, returns_receiver: true}`, folds into the chain the way a void call does. Its result is the same object, so the walk also folds what is called on that result, in place. This holds in the forward walk, in `_prefix_captures`, and in the backward walk, which takes the set of flagged calls as a new argument. A flag goes on a method only after `javap`, or the method's Javadoc, shows it returns `this`. The evidence is quoted in a catalog comment beside the flag.

### Task 8: The forward walk folds a flagged call

**Files:**
- Modify: `src/sextant/application/resolve/shapes/chains.py`:
  - in `_declared_entries` (:382-428), read `"returns_receiver": _validated_returns_receiver(step, catalog)`. It refuses anything but a bool, following the pattern of `_validated_receiver_arg` (:1006);
  - extend `_terminal_index` (:1631) to return the flagged terminal names as a third value;
  - in `_walk` (:787), fold when `_chain_key(next_site) is None or _configures(next_site, context)`, then fold the flagged site's own result chain in ordinal order before going on;
  - in `_prefix_captures` (:631), also fold flagged siblings on the root's receiver.
- Modify: `docs/components/D02-catalog-schema.md` (the `returns_receiver` key)
- Modify: `scripts/guard_check.py`
- Test: `tests/application/test_call_engines.py`

**Interfaces:**
- Produces: the step key `returns_receiver: bool` (default false), and `def _configures(site: dict[str, Any], context: _ChainContext) -> bool`, which is true when the matching step, or the terminal entry, is flagged.

- [ ] **Step 1: Write the failing tests** (an invented catalog via `_fluent_catalog`, the OkHttp shape):

```python
def test_a_builder_configured_over_several_statements_is_one_chain(tmp_path):
    # b = new Builder(); b.url("https://h/orders"); b.post(body); newCall(b.build())
    assert rows == [("POST", "/orders", "h", "resolved")]

def test_configuration_after_a_build_never_reaches_the_built_request(tmp_path):   # Review Focus 1
    # b.url(a); r1=b.build(); newCall(r1); b.url(c); r2=b.build(); newCall(r2)
    assert sorted(paths) == ["a-path", "c-path"]

def test_an_unflagged_call_returning_a_value_still_forks(tmp_path): ...   # today's behaviour, held

def test_a_base_set_as_a_statement_on_a_held_builder_reaches_the_row(tmp_path):
    # b = WebClient.builder(); b.baseUrl("http://a"); c = b.build(); c.get().uri("/x").retrieve()
    assert row["peer"] == "a" and row["path"] == "/x"

def test_a_non_bool_returns_receiver_is_refused(): ...   # CatalogError
```

- [ ] **Step 2:** Run them. Expect FAILs.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Add the guard `chains.a-call-returning-its-RECEIVER-configures-it`. Its edit removes `or _configures(next_site, context)`, and it is pinned by the first test. Measure it killed.
- [ ] **Step 5:** Commit: `feat(chains): a call that returns its own receiver configures the chain (ruling 4, forward)`.

### Task 9: The backward walk gathers flagged calls on the same value

**Files:**
- Modify: `src/sextant/application/resolve/values.py`:
  - `producers_of` (:841) and `producer_paths` (:942) gain `configuring: AbstractSet[tuple[str, str]] = frozenset()`, which is passed to `_Walk.__init__` (:1079);
  - in `_through` (:1806-1810), a call in the window whose `(owner, name)` is in `configuring` is not an escape;
  - `_along` (:2172) prepends those calls, in ordinal order, to `Producer.chain` after the receiver's own chain.
- Modify: `src/sextant/application/resolve/engines/scheduled_chain.py:226-228,934-936`, which builds `configuring` from the catalog's flagged steps the same way it builds `builder_calls`
- Modify: `scripts/guard_check.py`
- Test: `tests/application/test_scheduled_chain.py` (beside :195), `tests/application/test_values.py`

**Interfaces:**
- Produces: `producer_paths(index, site, slot, declared, along_receivers=False, past_accessors=None, configuring=frozenset())`. `Producer.chain` now includes the flagged siblings, each `(caller, ordinal)`, root first, in execution order.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_trigger_built_over_several_statements_keeps_its_name_and_cron(tmp_path):
    # tb=newTrigger(); tb.withIdentity("x"); tb.withSchedule(cronSchedule("0 0 * * * ?")); scheduleJob(job, tb.build())
    assert rows == [("DEFAULT.x", "cron", "0 0 * * * ?", "resolved")]

def test_an_unflagged_call_on_the_value_is_still_an_escape(walked): ...   # held
```

- [ ] **Step 2:** Run them. Expect FAILs (today the result is `simpleSchedule`, `partial`).
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Add the guard `values.a-CONFIGURING-call-is-not-an-escape`, pinned by the first test. Measure it killed.
- [ ] **Step 5:** Commit: `feat(values): the backward walk gathers configuring calls on the same value (ruling 4, backward)`.

### Task 10: Flag the shipped builders, with evidence, and pin them on a fixture

**Files:**
- Modify the catalogs:
  - `okhttp.yml`: `url get head post put patch delete method`;
  - `jdk-httpclient.yml`: `uri GET HEAD DELETE POST PUT method`;
  - `quartz.yml`: `TriggerBuilder#withIdentity withSchedule forJob`, `JobBuilder#withIdentity`;
  - `aws-sqs-sdk.yml`: `queueUrl messageBody`;
  - `spring-kafka-message.yml`: `setHeader`;
  - `step-models/spring-integration.yml`, and the three `spring-integration-*.yml` spec steps;
  - `spring-webclient.yml`: `uri header bodyValue body`, plus a new step `ResponseSpec#onStatus` with no captures;
  - `spring-restclient.yml`: `uri body`.

  Each flag gets a comment quoting the `javap` return type, or the Javadoc's "@return this …". A method whose evidence is missing stays unflagged, and its comment says so.
- Create: `fixtures/orders-heldbuilders`, a Java 21 Maven module with one class per catalog, each written in the variable style, plus the two builder-helper classes Task 11 uses.
- Modify: `fixtures/orders-quartz`, adding `HeldTriggerScheduler.java` (Task 9's shape, compiled)
- Modify: `tests/fixture_build.py` (`PRIMED_FIXTURES` gains `orders-heldbuilders`)
- Create: `tests/e2e/test_held_builders_delivered.py`
- Test: that file, plus `tests/e2e/test_async_delivered.py` (the Quartz counts move by one row)

- [ ] **Step 1:** Collect the evidence: for each class, `javap -cp <the jar in ~/.m2 at the catalog's measured version> <class>`. Paste the relevant signature lines into the catalog comment.
- [ ] **Step 2: Write the failing e2e test.** One assertion per class gives the true row:
  - OkHttp `POST https://h/orders`;
  - JDK `POST`;
  - SQS queue `orders`;
  - MessageBuilder topic `orders`;
  - WebClient `GET /x` with a response shape, where `onStatus` is a separate statement;
  - RestClient;
  - one Spring Integration spec;
  - Quartz `DEFAULT.x` with its cron.
- [ ] **Step 3:** Run it. Expect FAILs.
- [ ] **Step 4:** Add the flags, then run the e2e test, the gate and `field_check.py`. No pinned corpus row may move, since those corpora write their builders chained.
- [ ] **Step 5:** Commit: `fix(catalogs): every shipped builder that returns itself is read as one object (ruling 4)`. Open the part 5 PR on the user's go.

---

## Part 6 — Ruling 5: a builder returned from a helper is followed across the return

**The decision:** The new walk lives in `chain_ends` (`chains.py:205`). After the root walks of a caller, a terminal site that no root walk reached is walked **backwards** with `producer_paths(walk_index, site, RECEIVER, declared, along_receivers=True, configuring=flagged)`. Its parts:
- **`declared`:** every `(owner, name)` in the index whose name is a root or step method, matched on owner where the catalog states owners (the `scheduled_chain.py:226-228` pattern).
- **Which results count:** only a `rooted` result whose `chain[0]` matches a catalog root becomes a `ChainEnd`.
- **Captures:** the root's own captures, then each chain site's step captures in chain order, then the terminal's. Every capture is stamped with its own method (part 2).
- **The path:** `ChainEnd` gains `path: Path | None`, and fluent's value reads use `resolve_positions(..., within=path)` when it is set. This way each caller of a shared helper reads its own arguments.

### Task 11: Walk a rootless terminal back across methods

**Files:**
- Modify: `src/sextant/application/resolve/shapes/chains.py`:
  - `ChainEnd` (:190) gets `path: Path | None = None`;
  - `chain_ends`' per-caller loop (:298-356) runs the rootless pass after the root loop;
  - a visited set holds the terminal site keys the root walks reached.
- Modify: `src/sextant/application/resolve/shapes/arguments.py:1802` (`_walked_with` gains `within: Path | None = None`; when set it reads through `resolve_positions`), `src/sextant/application/resolve/engines/fluent.py` (passes `end.path`)
- Modify: `scripts/guard_check.py`
- Test: `tests/application/test_call_engines.py` (using `_sqs_built_by_a_helper`, :6617, and `_resolve_fluent_walked`, :6671), `tests/e2e/test_held_builders_delivered.py`

**Interfaces:**
- Consumes: `configuring` (Task 9), `_own_method` stamps (Task 3).
- Produces: `ChainEnd.path`, and `_walked_with(..., within=None)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_request_started_in_a_helper_and_sent_by_its_caller_is_one_row(tmp_path):
    # base(){ return SendMessageRequest.builder().queueUrl(Q); }  send(m){ sqs.sendMessage(base().messageBody(m).build()); }
    assert rows == [("/acme/orders", "resolved")]

def test_each_caller_of_a_request_helper_gets_its_own_value(tmp_path):     # Review Focus 2
    # req(String svc){ return new Request.Builder().url("http://" + svc + "/x"); }
    # a(){ newCall(req("svc-a").build()); }  b(){ newCall(req("svc-b").build()); }
    assert sorted((r["caller"], r["peer"]) for r in rows) == [(A, "svc-a"), (B, "svc-b")]

def test_a_terminal_a_root_walk_reached_is_never_walked_twice(tmp_path): ...  # one row, not two
```

Add the e2e rows for the two helper classes in `orders-heldbuilders`: an SQS helper and an OkHttp helper.

- [ ] **Step 2:** Run them. Expect FAILs.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Add the guard `chains.a-ROOTLESS-terminal-walks-back-across-methods`, pinned by the first test. Measure it killed. Then run the gate and `field_check.py`.
- [ ] **Step 5:** Commit: `feat(chains): a builder returned from a helper is followed to its send (ruling 5)`. Open the PR on the user's go.

---

## Part 7 — Ruling 3: a configured prefix applies to its own dispatcher's rows

**The decisions:**
- **Catalog key.** An inbound catalog may declare `dispatcher:`, one of `spring`, `servlet` or `jaxrs`.
  - `spring` means Spring's own dispatcher: DispatcherServlet on the servlet stack, DispatcherHandler on the reactive stack. It is used by `spring-web`, `spring-mvc`, `spring-mvc-router`, `spring-webflux-router`, `spring-actuator` and `spring-data-rest` (served by the DispatcherServlet).
  - `servlet` is used by `jakarta-servlet` and `javax-servlet`.
  - `jaxrs` is used by `jakarta-jaxrs` and `javax-jaxrs`.
  - A catalog without the key takes no configured prefix. **No silent losses:** every inbound
    `http`/`sse` catalog that takes a prefix today either gets a tag backed by CP-57, or is named in
    the PR body as losing its prefix, with the reason. `spring-cloud-gateway` and
    `spring-cloud-gateway-properties` run on WebFlux and are added to CP-57's reactive variant to
    decide this.
- **Server model.**
  - Each `prefixes` entry gains `stack: servlet | reactive`.
  - Its `keys` items become `{key, applies_to: [dispatcher…]}`, still composing left to right.
  - A key/dispatcher pairing is declared only once probe CP-57 has measured it.
- **The module's stack** mirrors Spring Boot's `WebApplicationType.deduceFromClasspath`, read off `module_dependencies` coordinates:
  - **reactive** when `org.springframework:spring-webflux` is present and neither `org.springframework:spring-webmvc` nor `org.glassfish.jersey.containers:jersey-container-servlet-core` is;
  - **servlet** when either of those two is present;
  - otherwise none.

  Only the entries whose `stack` matches apply.
- **Applying.** A row takes the prefixes its catalog's dispatcher appears in (`endpoints.catalog_id` → Catalog → `dispatcher`).

### Task 12: Probe CP-57 — which prefix reaches which dispatcher

**Files:**
- Create: `scripts/probes/cp57-dispatcher-prefixes/`, a Boot 3.5 app with:
  - an MVC controller;
  - a `RouterFunction`;
  - a `@WebServlet` under `@ServletComponentScan`;
  - a Jersey resource;
  - `server.servlet.context-path=/c`, `spring.mvc.servlet.path=/m` and `spring.jersey.application-path=/j`;
  - a `run.sh` that starts the app and curls each candidate path.
  - A second variant with WebFlux plus a leftover `server.servlet.context-path`, `spring.webflux.base-path=/w`, and one Spring Cloud Gateway route.
- Create: `scripts/probes/cp57-dispatcher-prefixes/RESULT.md`

- [ ] **Step 1:** Build and run both variants under JDK 21. Record in `RESULT.md` the path that answered 200 for each handler.
- [ ] **Step 2:** Commit: `probe(CP-57): which configured prefix each dispatcher takes`.

### Task 13: Prefixes by dispatcher and by stack

**Files:**
- Modify: `src/sextant/catalogs/server-models/spring-boot.yml`, from CP-57's result
- Modify: `src/sextant/ingress/catalogs/yaml_source.py:69-180` (validate `stack` and `keys[].{key, applies_to}`), and `:328-421` (read `dispatcher` with `_closed_or_absent`)
- Modify: `src/sextant/application/ports/catalogs.py:15` (`Catalog.dispatcher: str | None = None`)
- Modify: `src/sextant/application/resolve/path_prefix.py:76-148`. Prefixes are keyed by dispatcher and filtered by `_web_stack(workspace)`; the row loop looks the dispatcher up by `catalog_id`.
- Modify: the eight catalogs listed in the decision (add `dispatcher:`), and `docs/components/D02-catalog-schema.md`
- Modify: `fixtures/orders-contextpath`, adding `LegacyServlet.java` (`@WebServlet("/legacy")` and `@ServletComponentScan` on the app)
- Modify: `scripts/guard_check.py`
- Test: `tests/application/test_path_prefix.py`, `tests/e2e/test_rest_inbound_delivered.py`

**Interfaces:**
- Produces: `def _web_stack(workspace: Workspace) -> str | None` (`"servlet"`, `"reactive"` or `None`), and `Catalog.dispatcher`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_mvc_servlet_path_never_reaches_a_plain_servlet(context_path_rows):
    assert ("GET", "/shop/legacy") in {(r["method"], r["path"]) for r in context_path_rows}

def test_a_reactive_module_ignores_a_leftover_servlet_context_path(tmp_path): ...  # unit, via module_dependencies

def test_a_catalog_without_a_dispatcher_takes_no_configured_prefix(tmp_path): ...

def test_an_unknown_dispatcher_word_is_refused(): ...   # CatalogError
```

The existing `test_a_configured_context_path_and_servlet_path_reach_the_published_rows` and Task 2's `GET /shop/api/versioned` must still pass.

- [ ] **Step 2:** Run them. Expect FAILs.
- [ ] **Step 3:** Implement it.
- [ ] **Step 4:** Add the guard `path_prefix.a-prefix-applies-to-ITS-OWN-dispatchers-rows`. Its edit restores `prefixes.get(protocol, "")`, and it is pinned by the first test. Measure it killed. Then run the gate and `field_check.py`; the petclinic pins must hold.
- [ ] **Step 5:** Commit: `fix(path-prefix): a configured prefix applies to the rows its dispatcher serves (ruling 3)`. Open the PR on the user's go.

---

## Part 8 — Ruling 8: a controller's inherited, non-overridden mappings are its rows

**The decision:** `inherited_rows_over` (`effective_annotations.py:379`) adds candidates for each class carrying the catalog's type gate.
- **Which methods:** every method of its superclasses, transitively, and every interface **default** method, whose member key (name plus descriptor) the class does not declare, and which has its own mapping (`_own_mapping`).
- **What each emits:** a synthetic row `{target: <declaring method>, annotation, args, inherited: True, gate_type: <the class>}`.
- **SQL:** the struct `STRUCT(target, annotation, args, inherited, gate_type)` carries `gate_type` through `annotations_effective` and `declared` (`derive_endpoints.sql:350,405-415,551`). The row's prefix and controller gate then come from the subclass, through the existing `coalesce(m.gate_type, s.enclosing)` (:1751-1784), and the handler stays the declaring method (:1684).
- **Opting in:** a catalog opts in with `matches.mapping.inherit_unoverridden: true`, a closed-set word validated beside `_INHERIT_SIBLINGS` (`annotation_driven.py:1400`). It is switched on only for frameworks probe CP-58 shows serving inherited methods.

### Task 14: Probe CP-58 — which frameworks serve an inherited, non-overridden mapping

**Files:**
- Create: `scripts/probes/cp58-inherited-mappings/`. Each app has `abstract class CrudController { @GET-style "/list" list() }` and two concrete subclasses with prefixes `/orders` and `/products`, one of which overrides `list` with its own mapping. There is one app per framework: Spring MVC (Boot 3.5), Jersey (JAX-RS 3), Quarkus REST and Micronaut 4. Each has a `run.sh` that curls the four candidate paths.
- Create: `scripts/probes/cp58-inherited-mappings/RESULT.md`

- [ ] **Step 1:** Run each app under JDK 21, and record which paths answer, per framework.
- [ ] **Step 2:** Commit: `probe(CP-58): which frameworks serve an inherited mapping`.

### Task 15: Inherited mappings become the subclass's rows

**Files:**
- Modify: `src/sextant/application/resolve/effective_annotations.py:379-543` (the new candidates)
- Modify: `src/sextant/application/resolve/engines/annotation_driven.py:1833-1962` (pass `gate_type`; read `inherit_unoverridden`), `src/sextant/storage/duckdb/derive_endpoints.sql`
- Modify: the catalogs CP-58 confirms (add `inherit_unoverridden: true`), and `docs/components/D02-catalog-schema.md`
- Create: `fixtures/orders-inherited`, a Spring Boot module with `CrudController<T>` mapping `GET /list` and `POST`, plus:
  - `OrderController` with `/orders`, which does not override;
  - `ProductController` with `/products`, which overrides `list` with `@GetMapping("/all")`.
- Modify: `tests/fixture_build.py`, `scripts/guard_check.py`
- Test: `tests/application/test_effective_annotations.py` (helpers `_method`, `_extends`, `inherited_rows`), `tests/e2e/test_rest_inbound_delivered.py`

**Interfaces:**
- Produces: synthetic rows with a `gate_type: str | None` key, and the mapping word `inherit_unoverridden`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_mapping_a_subclass_inherits_without_overriding_is_its_own_row():
    rows = inherited_rows(...)  # Base#list mapped, A extends Base, A declares nothing
    assert {"target": BASE_LIST, "annotation": GET, "args": {...}, "gate_type": A} in rows

def test_inherited_and_overridden_mappings_each_take_their_own_subclass_prefix(inherited_rows_e2e):  # Review Focus 5
    paths = {(r["method"], r["path"], r["handler"]) for r in inherited_rows_e2e}
    assert ("GET", "/orders/list", CRUD_LIST) in paths
    assert ("POST", "/orders", CRUD_CREATE) in paths
    assert ("GET", "/products/all", PRODUCT_LIST) in paths
    assert ("GET", "/products/list", CRUD_LIST) not in paths
    assert ("POST", "/products", CRUD_CREATE) in paths

def test_a_catalog_that_does_not_opt_in_inherits_nothing_new(): ...
```

- [ ] **Step 2:** Run them. Expect FAILs.
- [ ] **Step 3:** Implement it. `test_a_gateless_catalog_never_synthesizes_onto_an_implementing_class` (`test_endpoints.py:5299`) and every existing inheritance test must still pass. The two `/orders` and `/products` rows that share a handler stay distinct through shapes and dedup, because they have different paths and different `row_id`s.
- [ ] **Step 4:** Add the guard `effective_annotations.an-INHERITED-unoverridden-mapping-is-the-subclasses-row`, pinned by the first test. Measure it killed. Then run the gate and `field_check.py`.
- [ ] **Step 5:** Commit: `feat(annotations): a controller's inherited mappings are its own rows (ruling 8)`. Open the PR on the user's go.

---

## Task 16: Close out

**Files:**
- Modify: `docs/superpowers/specs/2026-10-30-object-identity-design.md` (status: BUILT, a short "as built" per ruling with its PR link)
- Modify: `docs/superpowers/specs/2026-10-30-vertx-web-design.md` on `cov/vertx` (§3a item 5 and §3d now say "built by rulings 4 and 5", and §5's cost drops those items). Commit on `cov/vertx`, not here.
- Modify: `docs/COVERAGE.md`, only where a cell moved

- [ ] **Step 1:** Write the "as built" notes and the Vert.x spec update.
- [ ] **Step 2:** Commit each on its own branch.
