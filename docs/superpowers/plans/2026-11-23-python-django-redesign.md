# Django Inbound Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Django routes, their prefixes, methods and handlers are read with the mechanisms Sextant already has, with zero wrong `resolved` rows against Django's own resolver on four real projects.

**Architecture:** Route lists, mounts, `include` and `as_view` are read by the existing value walk; the branch's own list walk and four added concepts are removed. General changes go where the mechanism lives (the value walk, the Python scanner, value-model matching), so every language reader gets them. Each rule is first proven in the engine on a throwaway copy (Task 1) before it enters the product.

**Tech Stack:** Python 3.14, DuckDB workspace, YAML catalogs, pytest; Django 5.2 fixture `fixtures/orders-django`.

**Spec:** `docs/superpowers/specs/2026-11-23-python-django-redesign.md` (§4, §4a, §4b, §4c are binding). It replaces parts of `2026-11-22-python-django-core-design.md`; the probe `scripts/probes/django_rules.md` stays the source of every Django rule.

## Global Constraints

- **Truth first.** A `resolved` row that Django does not serve fails the task that produced it. Unknown is `partial` or `unresolved` with one of the six existing reasons; never a new reason.
- **No new concept.** The only new vocabulary this plan may add, each with an approval entry in `tests/architecture/vocabulary.yml` (approved by the user 2026-11-23): catalog keys `router_named`, `variable`, `element`; catalog value `expression` of `url_is`. Any other new catalog key or value, question kind, scan fact, reason or truth rule: STOP and report to the controller, who asks the user. Never build it "provisionally".
- **Reuse.** Before writing a rule, find its row in `docs/value-reading-scenarios.md` or in the spec's §4 table and use that mechanism. If the shape is in neither, STOP and report.
- **Removed from the branch, and they stay removed:** keys `through`, `read`, `narrowed_by`; question kind `mounted_router`; scan fact `calls_super`; functions `_held_by`, `_reach`, `_lists`, `_reached_at`, `_handed_lists`, `unread_routers`.
- **Not supported, by ruling:** a registration in a loop or comprehension; the keywords of a `**kwargs` parameter; a lookup by key in a dict. The row keeps its reason and a question names the line. Do not build a reader for these.
- **General changes are general.** A change in `resolve/values.py`, in the Python scanner or in value-model matching has a test for a non-Django reader too, and the 12 pins (`uv run python scripts/field_check.py`) must show no row lost.
- **Timebox every long run:** `scratchpad/timebox.sh EXPECTED_SECONDS LABEL -- CMD` (kills at 3x). Gate: `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh > FILE 2>&1; echo $?` (about 480 s). Pins: about 650 s.
- **Two fix rounds on one task:** stop and report "the concept may be wrong".
- **Schema.** `FACT_SCHEMA_VERSION` changes only where a fact is added or removed; removing `calls_super` returns the header fact to its form on `main`.
- Commit per task; never push; the commit trailer is `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Review Focus

1. **A wrong `resolved` row from a held list**: a copy taken before later additions (zulip `zproject/urls.py:776`, additions at 908 and 1022) must not hold the later members → Task 3.
2. **A list that nothing readable reaches** (zulip's `EXTRA_INSTALLED_APPS` loop; weblate `addons/api.py:62`) must publish the hole at `partial`, never the root at `resolved` → Task 6.
3. **A DRF `APIView` under `path()`** (weblate, netbox) must be `partial` with the method not read, never one `resolved` any-method row → Task 8.
4. **`include((patterns, "app"))`**: the string in the tuple is never read as a module of routes → Task 5.
5. **A list changed in a way that is not an addition** (`remove`, `pop`, `sort`, an index store) or handed to unread code is never `resolved` → Task 3.

---

### Task 0: Bring the branch up to `main`

**Files:** none edited by hand.

- [ ] **Step 1:** In `.worktrees/python-django`, `git merge main` (PR #110 and, when merged, PR #111). The test merge of 2026-11-23 was clean. Resolve nothing by guessing: a conflict is reported.
- [ ] **Step 2:** Run the gate. Expected: exit 0.
- [ ] **Step 3:** Commit the merge.

### Task 1: Prove the composed design in the engine, on the throwaway copy

This task writes NO product code. It exists because the spec's numbers came from a driver script, not from the engine.

**Files (throwaway worktree `.worktrees/django-on-main`, branch `tmp/django-on-main`, never merged):**
- Modify freely: `src/sextant/application/resolve/values.py`, `shapes/mounts.py`, `engines/fluent.py`, `ingress/extract/python/calls.py`, `libraries.py`, `catalogs/django.yml`, `catalogs/value-models/django.yml`.
- Create: `scratchpad/django-compare.py` (from `scratchpad/t9-healthchecks/compare2.py` and `oracle_wrap.py`).

**Produces:** `scratchpad/task1-report.md` with, per project (healthchecks, bookwyrm, weblate, zulip): Django (method, path) pairs; Sextant rows by truth level; pairs correct; **every `resolved` row Django does not serve, listed**; every not-read group with its cause and count.

- [ ] **Step 1:** Implement, at spike quality, §4a (the join and the unreached-list rule), §4b (the four `annotations` entries read by the fluent engine), and the §4c rules M2, M3, M5, M6, M7, M9, M10, M11, on top of the existing throwaway changes.
- [ ] **Step 2:** Run `sextant module analyze` on the four real trees (expected 60 s each, timeboxed) and the compare against the oracle files in `scratchpad/t9-principles/oracle-*.json` (each has `route`, `allowed` methods, `handler`).
- [ ] **Step 3:** For every `resolved` row Django does not serve: find the rule that produced it. A rule that cannot be made true goes to the controller with the code line and the count; it does not enter the product.
- [ ] **Step 4:** Report. **Gate for the rest of the plan: zero wrong `resolved` rows on the four trees**, or a user ruling on each remaining one.

Timebox: 4 hours green path; stop and report at 8.

### Task 2: A list held in a name answers with its members

**Files:**
- Modify: `src/sextant/application/resolve/values.py` (`_Walk._binding_writes`, the `else` arm that answers `NOT_READABLE` for a container; its comment states the old rule)
- Test: `tests/application/test_values.py`, `tests/application/test_fastapi_routes.py`

**Interfaces:**
- Produces: a `field` entry whose write is an `array` answers one `_Reached` per member, each with an `_ELEMENT_OF` step, exactly as `_elements` gives for an array written in place; a write that is another name is followed; an unpacked member that names the list itself is skipped (the other writes are its members).

- [ ] **Step 1: Failing tests.**
  - `test_a_list_held_in_a_field_answers_with_its_members`: facts `X = ["a", "b"]`, a read of `X` → answers `a`, `b`, two paths.
  - `test_a_name_for_another_list_is_followed`: `Y = X` → the members of `X`.
  - `test_a_list_summed_onto_itself_holds_every_write`: `X = ["a"]`, `X = [*X, "b"]` → `a`, `b`; no `cycle`.
  - `test_a_held_list_with_one_unreadable_member_keeps_the_others`: one trailing `not_readable`.
  - Change `test_a_verb_list_held_in_a_module_name_is_never_read_as_its_first_value` to assert the rows `GET /c` at `resolved` (rename: `..._is_read`), and `test_a_verb_list_changed_in_another_file_is_not_read` to assert `GET` and `POST` (rename: `..._holds_both`).
- [ ] **Step 2:** Run them; expected FAIL (`not_readable`).
- [ ] **Step 3:** Implement in `_binding_writes`. Members of one list are resolved one read per member by the caller that enumerates them (spec §4c M11): `PATH_CAP` and its checks are not changed.
- [ ] **Step 4:** Tests pass; `uv run pytest tests/application -q`.
- [ ] **Step 5:** Pins. Expected: no row lost; a row that moves from `unresolved` to `resolved` is listed in the report with its source line.
- [ ] **Step 6:** Commit.

### Task 3: When a held list is not exactly known, and the order of reads

**Files:**
- Modify: `src/sextant/application/resolve/values.py` (the held-list read of Task 2; `Flow` for the order within one body)
- Test: `tests/application/test_values.py`

- [ ] **Step 1: Failing tests** (each asserts NO `resolved` answer for the member in question):
  - `test_a_call_on_a_held_list_that_is_not_an_addition_makes_it_inexact` — parametrised over `remove`, `pop`, `clear`, `insert`, `sort`, `reverse`, `__setitem__`, `__delitem__`: the answers are `inexact`.
  - `test_a_held_list_handed_to_unread_code_escapes`.
  - `test_a_read_inside_the_writing_body_sees_only_earlier_writes`: `A = ["a"]`, `B = [*A]`, `A = [*A, "b"]` in one body → `B` holds `a` only.
  - `test_a_read_from_another_body_sees_every_write`.
  - `test_a_later_write_in_a_loop_or_branch_is_inexact_for_an_earlier_read`.
  - `test_a_member_written_under_a_test_carries_that_test`: the write's guard arrives on the member's path (consumed in Task 6).
  - One of the first two with JVM-spelled facts (`putstatic` of an array, a `List.add` on it).
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement with the existing `escapes` window, `inexact` mark, and the body order (`ordinal`, `loop_group`, `dominator`) the walk already uses for setters. No new reason, no new mark.
- [ ] **Step 4:** Tests pass. **Step 5:** Pins. **Step 6:** Commit.

### Task 4: The scanner records a copy and the list adders as lists; `.format` as a template

**Files:**
- Modify: `src/sextant/ingress/extract/python/calls.py` (`_value`, `_sum`, `_augmented`, `_concat`; the call arm for a method on a name)
- Test: `tests/ingress/extract/python/test_calls.py`

- [ ] **Step 1: Failing tests** (assert the written fact):
  - `test_list_of_a_value_is_the_list_of_its_members`: `b = list(a)` writes `array [ *a ]`. `list` must resolve to the builtin: a local name `list` is not it.
  - `test_append_and_extend_on_a_module_list_are_writes`: `x.append(v)` → `x` written `[ *x, v ]`; `x.extend(vs)` → `[ *x, *vs ]`. Only on a name whose writes in this file are lists.
  - `test_a_sum_onto_a_list_name_is_a_list`: `x += other.attr` → `[ *x, *other.attr ]`; `urlpatterns = f(*a) + b` where `b` is a list name → `[ *f(...), *b ]`. `count += 1` and `text += "x"` are unchanged.
  - `test_format_on_a_literal_is_its_template`: `"/<org>{}".format(rule)` → `concat` `/<org>{}` with `rule` as its operand; `"{a}-{b}".format(a=x, b=y)` by name; a `{0!r}` or format spec the reader does not model → the value is unread, as today.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS, plus `uv run pytest tests/ingress/extract/python -q`.
- [ ] **Step 5:** Pins (redash is expected to gain paths from `.format`; list them). **Step 6:** Commit.

### Task 5: `include` and `as_view` through value models; `element`; matching on ancestors

**Files:**
- Modify: `src/sextant/application/resolve/values.py` (`_stated_value`: the owner match), `src/sextant/ingress/catalogs/yaml_source.py` (`returns_arguments`: the `{ arg, element }` form), `src/sextant/catalogs/value-models/django.yml`, `src/sextant/catalogs/django.yml` (remove `through`, `read`), `docs/components/D02-catalog-schema.md`, `tests/architecture/vocabulary.yml` (approval entry for `element`)
- Test: `tests/application/test_values.py`, `tests/application/test_django_includes.py`, `tests/application/test_django_class_views.py`

**Interfaces:**
- Produces: value-model entries `{ owner: django.urls.conf, method: include, returns: { arg: 0, element: 0 } }` and `{ owner: django.views.generic.base.View, method: as_view, returns_receiver: true }`.

- [ ] **Step 1: Failing tests.**
  - `test_a_stated_call_matches_a_subclass_receiver`: an entry on `Base#m`, a call on a `Sub` value → the entry applies.
  - `test_a_nearer_definition_in_read_code_wins_over_the_entry`: `Sub` defines `m` in the module → the entry does not apply; the body is followed.
  - `test_element_reads_the_first_of_a_written_tuple`: `include((patterns, "app"))` → the value is `patterns`; `include(patterns)` → `patterns`; the string `"app"` produces no read of a module.
  - `test_include_of_a_module_name_arrives_as_its_name` (existing behaviour kept): `include("a.urls")` → literal `a.urls`.
  - `test_as_view_names_the_class_it_is_called_on`.
  - A non-Django test of the ancestor match: `httpx.Client.__enter__` on a subclass (the existing `returns_receiver` entry).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. The owner is the one the engine's receiver binding gives (`bound_receivers`), and the lookup order is `Dispatch`'s; do not write a second hierarchy walk.
- [ ] **Step 4:** PASS; the vocabulary test passes with the one approval entry; the pins list every value-model match that changed.
- [ ] **Step 5:** Commit.

### Task 6: The join for a registration made on nothing; the unreached list

**Files:**
- Modify: `src/sextant/application/resolve/shapes/mounts.py` (delete `_held_by`, `_reach`, `_lists`, `_reached_at`, `_handed_lists`, `unread_routers`, `_placed`, `_unplaced` and their uses; add the join of spec §4a), `src/sextant/application/resolve/engines/fluent.py` (callers), `src/sextant/application/resolve/open_questions.py` (remove `mounted_router`), `src/sextant/catalogs/django.yml`
- Test: `tests/application/test_django_includes.py`, `tests/application/test_django_routes.py`, `tests/application/test_mounts.py`

**Interfaces:**
- Consumes: Task 2/3 (members of a held list, with guards), Task 5 (`include` returns its router).
- Produces: for a route root made on nothing, `MountReader.of_route` answers from a map built once per reader: for each mount and each root, the members the value walk reaches (`producer_paths` with the registration calls as stops, one read per member), each with the walk's `Path`.

- [ ] **Step 1: Failing tests** (fixture-level, real scanner):
  - `test_a_route_in_an_included_list_serves_under_the_prefix`; nested; a list included twice → two rows.
  - `test_a_helper_that_returns_a_route_keeps_each_callers_path_and_prefix` (zulip `rest_path`).
  - `test_the_root_is_the_module_root_urlconf_names`; two written roots → both.
  - `test_a_list_no_mount_and_no_root_reaches_is_the_hole`: rows `<prefix>/x` at `partial`, one `mount_prefix` question; **no `resolved` row**.
  - `test_a_repository_with_no_root_urlconf_has_no_resolved_row`.
  - `test_a_library_call_that_takes_the_list_is_no_mount` (`i18n_patterns(*x)`): the hole.
  - `test_a_mount_of_a_library_module_adds_nothing` (`include("django_scim.urls")`): no row, no question.
  - `test_a_route_added_under_a_setting_carries_the_condition`.
  - `test_a_route_list_of_three_hundred_members_is_read` (bookwyrm has 296).
  - Vert.x, FastAPI and Flask mount tests unchanged and green.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5:** Cost: time `sextant module analyze` on bookwyrm and weblate before and after; a resolve more than 1.5x slower is reported.
- [ ] **Step 6:** Commit.

### Task 7: Method decorators with the Spring words

**Files:**
- Modify: `src/sextant/catalogs/django.yml` (the `annotations` block of spec §4b; remove `narrowed_by`), `src/sextant/ingress/catalogs/yaml_source.py` (`method_from` as `{ arg, keyword }` in a fluent catalog), `src/sextant/application/resolve/engines/fluent.py` (read the block for the decorators on the handler's `def`; keep the branch's walk from the registration to the function), `docs/components/D02-catalog-schema.md`
- Test: `tests/application/test_django_verbs.py`

- [ ] **Step 1: Failing tests:** one fixed method; `require_safe` → GET and HEAD rows; `require_http_methods(["GET", "POST"])` by position and by keyword; a list the walk cannot read → one row, method not read, `unresolved`; two decorators → the intersection; an empty intersection → no method; an unknown decorator above `@require_POST` → the POST narrowing still holds and the handler has its `handler_pass_through` question; no decorator → one any-method row; the decorator applied as a call, `path("x", require_POST(view))`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS; the vocabulary test shows no new word.
- [ ] **Step 5:** Commit.

### Task 8: A library `dispatch` is read by the existing rule

**Files:**
- Modify: `src/sextant/ingress/extract/python/libraries.py` (write the existing call-site facts for the body of a library method that a loaded catalog names under `bypassed_by`, for the library classes a module class extends; remove `_calls_super`), `src/sextant/domain/facts.py` (remove `calls_super`), `src/sextant/domain/version.py`, `src/sextant/application/resolve/engines/fluent.py` (the delegating test reads the `special` call for library and module bodies alike), `docs/components/D00-fact-schema.md`
- Test: `tests/ingress/extract/python/test_libraries.py`, `tests/application/test_django_class_views.py`, `tests/e2e/test_orders_django.py`

- [ ] **Step 1: Failing tests:**
  - `test_a_catalog_named_library_method_has_its_call_sites`: for `LoginRequiredMixin.dispatch` the facts hold the call `super().dispatch(...)` as `special`; a library method no catalog names has none.
  - `test_a_view_under_an_auth_mixin_keeps_its_method_rows`: `MyOrders(LoginRequiredMixin, View)` → `GET /orders/mine/`, handler `MyOrders.get`, `resolved`.
  - `test_a_library_dispatch_that_does_not_call_its_parent_is_partial`: a DRF-shaped base in a fixture library → one row, path read, method not read, `partial`, a question; never `resolved` with the library method as handler.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5:** Cost: the fixture's scan time and fact count against the "full scan" figures of the spec (14.7 s, 46,757 call facts): the targeted read must stay within 1.2x of the unscanned run (1.5 s, 241).
- [ ] **Step 6:** Commit.

### Task 9: A wrapper that calls what it wraps

**Files:**
- Modify: `src/sextant/application/resolve/values.py` (the walk into a decorator: a returned function that calls the decorator's parameter stands for that parameter, for the reader that asks what a call of the value runs), `src/sextant/ingress/extract/python/libraries.py` (the targeted read of Task 8, for a library function that decorates a module function), `src/sextant/catalogs/value-models/django.yml` (remove each entry the rule now reads)
- Test: `tests/application/test_fastapi_routes.py`, `tests/application/test_django_routes.py`

- [ ] **Step 1: Failing tests:**
  - `test_a_module_wrapper_that_calls_its_function_names_that_function`: `def deco(f): @wraps(f) def inner(*a, **k): return f(*a, **k); return inner`.
  - The factory form `deco(args)(f)`; a wrapper that calls `f` on one branch only (still the handler); a wrapper that never calls `f` → `handler_pass_through`, handler not named; two stacked wrappers.
  - A lambda wrapper: `lambda function: user_passes_test(...)(function)` (zulip `zulip_login_required`) → the handler is the function, never the lambda (the wrong row of the first measurement).
  - A library wrapper read through the targeted read; a library wrapper whose body cannot be read keeps its value-model entry.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5:** For each of the 22 entries of `value-models/django.yml`: remove it where the fixture test of that decorator still passes without it; keep and list the ones that need it, with the reason.
- [ ] **Step 6:** Pins: FastAPI and Flask handlers that change are listed. **Step 7:** Commit.

### Task 10: Measure, pin, document

**Files:**
- Create: `scripts/field-expectations/py-bookwyrm.json`, `py-weblate.json`, `py-zulip.json` (+ sidecar locks, as `py-healthchecks`)
- Modify: `scripts/field-expectations/py-healthchecks.json`, `docs/value-reading-scenarios.md` (the catalog-level survey and the rulings of 2026-11-23), `docs/COVERAGE.md`, `docs/coverage/python.md`, `docs/components/D02-catalog-schema.md`, `CHANGELOG.md`, `docs/open-issues.md` (OI-501 id-map row; the issues below), `tests/architecture/vocabulary.yml`

- [ ] **Step 1:** Run the product engine on the four real trees and the compare of Task 1. **Zero wrong `resolved` rows**; the yield per project; every not-read group with cause and count.
- [ ] **Step 2:** Pin the four projects; run all 16 pins.
- [ ] **Step 3:** Log in Plane and in `docs/open-issues.md`, each with its count: a registration in a loop (about 15 places in 14 projects); `**kwargs` keywords (zulip 259 routes); a lookup by key (zulip 731 pairs); `as_view(http_method_names=...)`; Django's first-match order for duplicate paths; admin routes.
- [ ] **Step 4:** Full gate; expected exit 0.
- [ ] **Step 5:** Commit. Report to the user; the push and the PR wait for the user's word.

---

## Principles check

Reference: `docs/value-reading-scenarios.md`.

| Task | Shape | Row of the reference / existing mechanism |
|---|---|---|
| 2, 3 | A list held in a name | "A list held in a module name" (ruled 2026-11-23); the array rule; `escapes`, `inexact` |
| 4 | A copy, an adder, a template | scanner array with an unpacked member; "Concat, one part unknown" |
| 5 | A call that returns its argument or its receiver | value-model forms `returns`, `returns_receiver` |
| 6 | Mounts | "Mounts and prefixes"; "A prefix that cannot be read"; "A mount of a router the module does not build" |
| 7 | Method from a marker on the handler | `spring-mvc.yml` `annotations[].method`, `method_from` |
| 8 | Class dispatch | `jakarta-servlet.yml` `dispatch`, `bypassed_by`; the `special` call rule |
| 9 | A wrapper | "A library wrapper a value model states" (`result_calls`), read from code |

| Rule | How the plan follows it |
|---|---|
| §8.8-1 follow the value through code we have | Tasks 2–6 and 8–9 read through the value walk and through library bodies |
| §8.8-2 one structural rule | Task 9 replaces 22 entries with one rule; no reader for loops |
| §8.8-3 name the general concept | each task names the existing mechanism it extends |
| §8.8-4 a closed set is exact | one row per member of a known list |
| §8.9 a new concept is the user's decision | Global Constraints list the four approved words; anything else stops |
| §8.1 measured on real projects | Task 1 before any product code; Task 10 after |

New concepts in this plan: the part `element` of the argument reference (approved 2026-11-23). No other.
