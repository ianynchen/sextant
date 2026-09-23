# Value Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the resolve layer one operation that answers *what is this value?* — a backward walk over six edge kinds, resolved per calling path — and retire the seven catalog words that each describe one hop.

**Architecture:** A SQL view normalises six edge kinds out of three tables that already exist. A Python walk resolves a call site per path, returning one `Binding` per distinct calling context. Engines call it instead of carrying private one-hop follows. The existing hop declarations are hoisted into a shared `value-models/` identity table, then deleted, then refused by the loader.

**Tech Stack:** Python 3.14, DuckDB, YAML catalogs; Java 21 + ASM for capability 9.19; `javap` probes.

**Spec:** `docs/superpowers/specs/2026-09-22-value-resolution-design.md` — read §0c (what the adversarial review changed), §1b–§1c (the path primitive), §2a (hoist/delete/refuse) and §5 (language neutrality) before Task 1.

## Global Constraints

- **No false positives** (standing user rule). Every ambiguity is an `unresolved(reason)`, never a guess. **This plan's specific danger is the inverse of the usual one:** its purpose is converting misses into answers, so every conversion is a new assertion. A diff shows movement, not wrongness.
- **The path is the unit of resolution, never the position.** Memoisation is keyed on `(position, path)`. Memoising per position alone reintroduces the fabrication §0c M-1 records — a helper called twice with different arguments yielding 2×2 rows instead of 2.
- **The resolve layer names no framework and no language** (`tests/architecture/test_source_rules.py`, `test_language_confinement.py`). The six edge kinds say `binding`, never `field`; `identified_by.owner` is optional.
- **Every framework claim carries a probe with §5.4 provenance** (`tests/architecture/test_probe_provenance.py`).
- **Existing output moves only in the tasks that say so** (1, 7, 8, 9, 12), and the tests that pin it move in that same task.
- **The gate is** `JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh` — run it whole, read the exit code, never pipe it through `tail` or `head`. `scripts/check.sh --guards` runs the mutation guards.
- **No worktrees** (GUIDELINES §13.9). Work on the branch this plan is committed to.
- **Match the surrounding style** (GUIDELINES §3, §13.5); do not refactor adjacent code.

---

## File Structure

| file | responsibility |
|---|---|
| `src/sextant/application/resolve/return_flow.py`, `call_edges.py` | Task 1 — read the projection, not raw sites |
| `src/sextant/storage/duckdb/value_edges.sql` | **new** — the edge view |
| `src/sextant/application/resolve/values.py` | **new** — the walk, `resolve_site`, `Binding`, `Answer` |
| `src/sextant/storage/duckdb/schema.sql` | `value_resolutions` (Task 5) |
| `src/sextant/ingress/catalogs/yaml_source.py` | the hoist, then the refusal (Tasks 6, 10) |
| `src/sextant/catalogs/value-models/*.yml` | **new** — `identified_by`, one entry per producing callable |
| `src/sextant/application/resolve/engines/{interface_implementation,single_call,fluent}.py` | Tasks 7–9 |
| `extractor-jvm/…` | capability 9.19 (Task 11) |
| `scripts/probes/cp33_binding_writes/` | the capability's measurement |
| `docs/components/D00-fact-schema.md`, `D02-catalog-schema.md` | the capability and the model |

---

## Task 1: Re-point `return_flows` and `call_edges` at the projection

The spec's §9 leaves this open; **the ruling is that it happens first and alone.** Both passes need it on their own merits — a Kotlin `$default` bridge and a class-compiled lambda are invisible to both today — and doing it inside a later task would mix its moved rows with the walk's.

**Files:**
- Modify: `src/sextant/application/resolve/return_flow.py:103`
- Modify: `src/sextant/application/resolve/call_edges.py:107`
- Test: `tests/application/test_call_edges.py`, `tests/application/test_return_flow.py`

**Interfaces:**
- Consumes: `effective_call_sites(workspace)` from `resolve/effective_calls.py`.
- Produces: `return_flows` and `call_edges` rows built over projected sites — what Task 2's view reads.

- [ ] **Step 1: Write the failing test**

In `tests/application/test_return_flow.py`, using that file's existing fact-building harness:

```python
def test_a_default_bridge_call_flows_from_the_sibling_it_stands_for():
    """A Kotlin `$default` bridge is re-targeted by `effective_call_sites` to the sibling it
    stands for. Reading raw `call_sites` files the flow against the BRIDGE, whose own body
    returns nothing a caller wants — so the round trip breaks at exactly the hop this pass
    exists to record."""
    flows = _flows(facts_with_a_default_bridge_call())
    assert [(f["callee"], f["return_ordinal"]) for f in flows] == [(SIBLING_SYMBOL, 0)]
```

And the matching one in `tests/application/test_call_edges.py` asserting the edge `reaches` the sibling's body rather than the bridge's.

- [ ] **Step 2: Run them to verify they fail**

```bash
.venv/bin/python -m pytest tests/application/test_return_flow.py tests/application/test_call_edges.py -q
```
Expected: FAIL — the flow names the bridge.

- [ ] **Step 3: Read the projection in both passes**

Replace `workspace.query("call_sites")` with `effective_call_sites(workspace)` in both. Add a comment at each site giving the reason in the file's own voice: the pass records a hop, and a hop recorded against a bridge names a body no caller reads.

- [ ] **Step 4: Measure what moved, before believing the tests**

```bash
.venv/bin/sextant module analyze fixtures/orders-ktor --workspace /tmp/t1a
.venv/bin/sextant module analyze fixtures/orders-service --workspace /tmp/t1b
```
Query `return_flows`, `call_edges`, `roots` and `reachability` in each, before and after the change. **Every row that moves must be a bridge or lambda row.** Anything else is a finding: stop and report it.

- [ ] **Step 5: Run the gate**

```bash
JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh
```
Expected: exit 0. Any e2e assertion that moves is updated in THIS task, with the moved row named in the commit message.

- [ ] **Step 6: Commit**

```bash
git add src/sextant/application/resolve/return_flow.py src/sextant/application/resolve/call_edges.py tests
git commit -m "fix(resolve): return flows and call edges read the projection, not raw call sites"
```

---

## Task 2: The `value_edges` view

**Files:**
- Create: `src/sextant/storage/duckdb/value_edges.sql`
- Modify: `src/sextant/storage/duckdb/workspace.py` (register the named query)
- Test: `tests/storage/test_workspace.py`

**Interfaces:**
- Consumes: `call_sites` (projected by Task 1's consumers), `return_flows`, `call_edges`.
- Produces: a named query `value_edges` yielding `(kind, from_method, from_value, to_symbol, to_ordinal, to_index)`. Task 3 is its only reader.

- [ ] **Step 1: Write the failing test**

```python
def test_the_edge_view_normalises_five_kinds_from_three_tables():
    """One shape out of three sources. `written_by` is absent until capability 9.19 (Task 11),
    and its absence is an answer: a workspace with no binding-write facts yields no such edge
    rather than an empty-but-present one."""
    kinds = {row["kind"] for row in workspace.query("value_edges")}
    assert kinds == {"produced_by", "returned_by", "read_from_binding",
                     "bound_to_parameter", "names_declaration"}
```

- [ ] **Step 2: Run it to verify it fails**

Expected: FAIL — no such named query.

- [ ] **Step 3: Write the view**

A `CREATE VIEW` (not a table — spec §3b: three tables already hold this data and a copy can drift). One `SELECT … UNION ALL` arm per edge kind, each with a comment naming the fact and the projection behind it, in `schema.sql`'s voice. The columns are nullable per kind and the file says which kind fills which — a `to_index` is meaningful only for `bound_to_parameter`.

- [ ] **Step 4: Run the test and the storage suite**

```bash
.venv/bin/python -m pytest tests/storage -q
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(storage): value_edges — six edge kinds normalised out of three existing tables"
```

---

## Task 3: The walk

**Files:**
- Create: `src/sextant/application/resolve/values.py`
- Test: `tests/application/test_values.py` (new)

**Interfaces:**
- Consumes: the `value_edges` named query.
- Produces, and every later task depends on these exact names:

```python
@dataclass(frozen=True)
class Answer:
    kind: str          # "literal" | "expression" | "unresolved"
    value: Any         # str | int | bool for literal; str for expression; None otherwise
    literal_kind: str | None   # "string" | "int" | "bool" — None unless kind == "literal"
    reason: str | None         # one of _REASONS — None unless kind == "unresolved"

@dataclass(frozen=True)
class Binding:
    path: tuple[str, ...]           # the calling contexts reached, outermost first
    slots: dict[int | str, Answer]  # argument index, or "receiver"

def resolve_site(workspace, site) -> list[Binding]: ...
```

- [ ] **Step 1: Write the failing tests — the M-1 case first, because it is why the primitive is a path**

```python
def test_a_helper_called_twice_yields_two_paths_not_four_combinations():
    """Spec §0c M-1. `register("orders", OrderImpl)` and `register("billing", BillingImpl)`
    reach ONE site inside `register`. Resolving its two slots independently yields 2x2 = four,
    two of which no code path produces. Per path it is two bindings, and each binding's slots
    agree because they came from the same caller."""
    bindings = resolve_site(workspace, site_inside_register)
    assert [(b.slots[0].value, b.slots[1].value) for b in bindings] == [
        ("orders", "com/acme/OrderImpl#"),
        ("billing", "com/acme/BillingImpl#"),
    ]

def test_several_returns_in_a_callee_are_several_paths():
    """`method_return` keeps several returns as several facts; the walk keeps them as several
    bindings, for the same stated reason — picking one would be a fact about code that may
    never run."""
    assert sorted(b.slots[0].value for b in bindings) == ["orders", "orders-fast"]

def test_a_value_merged_on_a_branch_is_unresolved_not_two_answers():
    """The distinction §1c draws: several PATHS are several answers; one path whose value
    cannot be enumerated is one `unresolved`. D00's array rule generalised."""
    assert [a.reason for a in answers] == ["non_enumerable"]
```

Then one test per `unresolved` reason — `not_readable`, `non_enumerable`, `escapes`, `no_writer`, `external`, `cycle` — each asserting the reason by name, and one per edge kind resolving through it.

- [ ] **Step 2: Run them to verify they fail**

Expected: FAIL — module not found.

- [ ] **Step 3: Write the walk**

Backward from the site's slots, over the edge view, **per path**. The rules that carry the design, each stated in the module docstring with the spec section behind it:

- memoise on `(position, path)`, never on position alone (§1c);
- a position already on the current path is `unresolved("cycle")`;
- a producer outside the scanned module is `unresolved("external")`;
- enumerable multiplicity branches the path; non-enumerable ambiguity ends it with a reason;
- **no cap** (§3a) — Task 4 decides whether one is needed.

The module names no framework: `identified_by` arrives as data in Task 6, and until then a `produced_by` edge whose producer has no identity entry answers `unresolved("not_readable")`.

- [ ] **Step 4: Run the tests**

```bash
.venv/bin/python -m pytest tests/application/test_values.py -q
```

- [ ] **Step 5: Confirm nothing consumes it yet**

```bash
grep -rn "resolve_site\|from sextant.application.resolve.values" src/sextant/ | grep -v "resolve/values.py"
```
Expected: no output. The walk ships unwired — Task 4 is the gate.

- [ ] **Step 6: Run the gate and commit**

```bash
git commit -m "feat(resolve): the backward value walk, resolved per calling path"
```

---

## Task 4: The measurement gate — STOPS FOR A RULING

**This task does not end in a code change.** It ends in numbers and a decision that is the user's.

**Files:**
- Create: `scripts/measure_value_walk.py`
- Create: `docs/research/2026-xx-value-walk-measurement.md`

- [ ] **Step 1: Write the harness**

For every position a shipped catalog asks about, on every fixture plus the largest corpus available (`mall-admin` — 48 MB of facts, 648 documents), record: path count, hop depth, answer count, wall time.

- [ ] **Step 2: Report distribution, maximum and tail — never the mean**

A mean hides the pathological module, which is the only thing this measurement is for.

- [ ] **Step 3: STOP and report to the controller**

The data either says no cap is needed, or names the cap and its reason. **If it names one, `fan_out` and `depth` join the reason vocabulary then and not before.** Do not implement a cap on your own judgement — spec §3a makes this a ruling point.

- [ ] **Step 4: Commit the measurement**

```bash
git commit -m "docs(research): what the value walk costs, measured before anything consumes it"
```

---

## Task 5: `value_resolutions` and shadow mode

**Files:**
- Modify: `src/sextant/storage/duckdb/schema.sql`, plus insert/reset SQL
- Modify: `src/sextant/application/resolve/values.py`
- Test: `tests/application/test_values.py`

**Interfaces:**
- Produces: a `value_resolutions` table — `(position, path, outcome, reason)` — written **only** for positions a catalog asked about. Task 13 generates COVERAGE from it.

- [ ] **Step 1: Write the failing test**

```python
def test_shadow_mode_records_what_it_would_resolve_and_publishes_nothing():
    """Spec §7a. The whole risk of this work is that a conversion is a new assertion; shadow
    mode makes every candidate reviewable as data before a row changes."""
    rows = run_in_shadow(workspace)
    assert {r["outcome"] for r in rows} == {"would_resolve", "unresolved"}
    assert workspace.query("endpoints") == before   # not one row moved
```

- [ ] **Step 2–4:** implement, run, and confirm an analysis in shadow mode moves **zero** rows in `endpoints`, `endpoint_metadata` and `shapes`.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(resolve): shadow mode — record what the walk would resolve, publish nothing"
```

---

## Task 6: The hoist, `value-models/`, and the probe rule

**Files:**
- Create: `src/sextant/catalogs/value-models/` and its first files
- Modify: `src/sextant/ingress/catalogs/yaml_source.py`
- Modify: `docs/components/D02-catalog-schema.md`
- Test: `tests/ingress/test_yaml_source.py`, `tests/architecture/`

**Interfaces:**
- Produces: `identified_by` entries — `{owner?, method, arg}` — reachable by the walk. **`owner` is OPTIONAL** (spec §5a: Go and Python free functions; `owner_of` already documents that an ownerless symbol is an answer, never an exception).

- [ ] **Step 1: Write the failing tests**

```python
def test_an_existing_channel_via_is_read_as_an_identity_entry():
    """Spec §2a step 1. The two forms are the same three fields; only the declaration site
    differs. Hoisting costs no catalog edit and changes no behaviour."""
    model = load_catalogs().value_model
    assert {"owner": "jakarta/jms/Session#", "method": "createQueue", "arg": 0} in model

def test_an_identity_entry_without_an_owner_loads():
    """§5a: a free function is an answer, not an error. Requiring `owner` would bake OO into
    a model the fact grammar does not."""

def test_an_identity_entry_without_a_probe_row_is_refused():
    """§7b: `value-models/` becomes a dumping ground otherwise. The same rule the architecture
    suite already applies to `measured:` blocks."""
```

- [ ] **Step 2–4:** implement the hoist, write the first `value-models/` files for producers no existing declaration covers, document the model in D02 §2, and confirm **no shipped row moves** — the hoist is a read, not a behaviour change.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(catalogs): value-models — identity declared once per producer, hoisted from existing hop keys"
```

---

## Tasks 7–9: Migrate the three engines, one at a time

Each is the same shape. **Smallest pinned surface first**, so the first migration is the cheapest place to discover the walk is wrong.

| task | engine | catalogs |
|---|---|---|
| 7 | `interface_implementation` | 1 |
| 8 | `single_call` | 13 |
| 9 | `fluent` | the rest |

For each:

- [ ] **Step 1: Run shadow mode and read the table first**

```bash
.venv/bin/sextant module analyze <fixture> --workspace /tmp/tN --shadow
```
Every `would_resolve` row is a candidate new claim. **Read them all before changing anything.** A wrong address looks exactly like a right one in a diff (spec §7).

- [ ] **Step 2: Replace the private follow with `resolve_site`**

`single_call`'s `channel_of`-then-`linked_channels`, `interface_implementation`'s copy of it. **`fluent`'s chain walk stays** — it answers *which calls form one boundary*, a different question (spec §2b).

- [ ] **Step 3: Diff every column of `endpoints`, `endpoint_metadata` and `shapes`**

- `unresolved` → resolved is the win, and **each one is read**.
- **Any other movement stops the migration** and is reported as a finding.

- [ ] **Step 4: Move the e2e pins in this same task**, never a later one.

- [ ] **Step 5: Gate, guards, commit.**

---

## Task 10: Delete the hop declarations, then refuse the keys

**This is the step that makes the design hold** (spec §2a step 3, §5b). A design that merely recommends the new way decays: a new catalog author copies the nearest example.

- [ ] **Step 1:** delete the now-redundant `channel_via` / `url_via` / `call_wrappers` declarations from the 14 migrated catalogs.
- [ ] **Step 2:** make the loader **refuse** those keys with a `CatalogError` naming the file and pointing at `value-models/`, the way every closed vocabulary here is enforced.
- [ ] **Step 3:** a test that the refusal fires, and that the error names the replacement.
- [ ] **Step 4:** confirm **no row moves** — the hoist already made these declarations redundant, so deleting them is cosmetic. Any movement means a migration was incomplete.
- [ ] **Step 5: Commit.**

---

## Task 11: Capability 9.19 — binding writes outside an initialiser

**A separate track.** It is the only edge with no fact, and a wrong binding-write fact fabricates silently everywhere.

**Files:**
- Modify: `extractor-jvm/…`
- Create: `scripts/probes/cp33_binding_writes/`
- Modify: `docs/components/D00-fact-schema.md` (capability 9.19)

- [ ] **Step 1:** probe first — what the bytecode shows for a field assigned in a setter, in `@PostConstruct`, in a static initialiser, and in a method that also reads it.
- [ ] **Step 2:** emit the fact **only where the assignment is directly traceable**, the discipline `field_write` already keeps ("direct traces only"); a computed assignment emits nothing.
- [ ] **Step 3:** document it as a capability any backend may report (spec §4, §5a), with the walk degrading **visibly** where it is absent — the `requires:` pattern.
- [ ] **Step 4:** fixture, pins, gate, commit.

---

## Task 12: Wire the sixth edge

- [ ] Add the `written_by` arm to the view, resolve through it, and pin the cross-method case — a reference obtained in one method and used in another, which is `akka-pekko-actors`' shape.
- [ ] Measure and report what newly resolves; the same read-every-conversion discipline as Tasks 7–9.

---

## Task 13: Docs, register, COVERAGE, open issues

- [ ] `OI-124`, `OI-126`, `OI-110` close, each citing the test that proves it.
- [ ] COVERAGE's boundary statements for the affected rows are **generated from `value_resolutions`** rather than hand-written (spec §3d).
- [ ] D02 documents `value-models/`; D00 documents capability 9.19.
- [ ] The register records what closed and what did not — including, honestly, whether `akka-pekko-actors` moved off "possibly permanent" or merely became tier B.
- [ ] `scripts/coverage_matrix.py --check` passes.

---

## Task 14: Finish

- [ ] Full gate and `--guards`.
- [ ] Amend the spec with anything implementation forced, in the voice §0c uses.
- [ ] Use superpowers:finishing-a-development-branch. **Do not merge without the user.**

---

## Self-Review

**Spec coverage.** §1a → Tasks 2, 11, 12. §1b–§1c → Task 3. §1d → Tasks 3, 5. §2a → Tasks 6, 10. §2b → Tasks 7–9. §3a → Task 4. §3b → Tasks 2, 3. §3c → Tasks 7–9. §3d → Task 5. §4 → Task 11. §5a → Tasks 3, 6, 11. §5b → Task 10. §6 → Task 3's boundaries. §7a → Task 5. §7b → Task 6. §8 → every task's tests. §9's open question → **Task 1, ruled: first and alone.**

**Placeholders.** None. The one place a task defers a decision is Task 4, which defers it deliberately to the user and says so.

**Type consistency.** `Answer` and `Binding` are spelled once, in Task 3, and every later task names those fields. `resolve_site(workspace, site) -> list[Binding]` is the only entry point — Tasks 7–9 all call it.

**Ordering.** Task 1 before 2 (the view reads what it fixes). 2 before 3. **3 before 4, and 4 gates 5–10** — nothing consumes the walk until the measurement passes. 6 before 7–9 (the engines need the identity model). 7–9 before 10 (delete only what is proven redundant). 11 before 12. 13 last of the substantive work.

**The risk this plan carries, named where it is handled.** Tasks 7–9 each begin by reading shadow-mode output rather than by changing code, because the diff those tasks produce shows movement and not wrongness. That ordering is the plan's answer to spec §7, and it is why Task 5 comes before any migration.
