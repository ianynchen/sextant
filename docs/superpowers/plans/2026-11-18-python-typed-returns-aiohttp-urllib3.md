# Typed-Return Module Variables + aiohttp/urllib3 Outbound Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close OI-444 (a module variable set from a call with a declared return type is typed, so its field reads resolve and its guards become `property`) and OI-454 (aiohttp and urllib3 outbound calls are read), plus OI-445 (the scanner tests this plan's Task 1 adds pin the shapes that must stay untyped).

**Architecture:** OI-444 extends `PythonHeaders.variable_class` (src/sextant/ingress/extract/python/project.py:307) with one new acceptance: the variable's single write is a call of a `def` in a scanned file whose written return names a class with a known shape. The lookup already exists in `_factory_class` (project.py:330) — the new rung accepts a plain class where that one demands `type[X]`. Nothing downstream changes: the consumer is `calls.py:2469` and the guards/fields flow follows. OI-454 adds two `single_call` catalogs that mirror `httpx.yml` exactly; every rule comes from a wire probe (DR-6). The existing catalog schema expresses everything (owner, client_base, method_arg, method_case, body_arg lists) — **if a probe-measured rule cannot be expressed with the existing vocabulary, stop and ask the user; new vocabulary needs approval.**

**Tech Stack:** Python (ast scanner, DuckDB), YAML catalogs, aiohttp 3.x / urllib3 2.x in the fixture venv only (Sextant never runs them; probes do, on purpose).

**Spec:** docs/superpowers/specs/2026-11-06-python-reader-design.md (§3c outbound; §7 probes). The two Plane items: SEXTANT-437 (OI-444), SEXTANT-447 (OI-454) — their text adds nothing beyond docs/open-issues.md rows 444/454; verified 2026-11-18.

## Global Constraints

- `JAVA_HOME=/opt/homebrew/opt/openjdk@21` for every build and test run.
- Never use `git stash` (shared stack).
- Every task ends with the full gate green (`uv run pytest`) and all 9 field pins green (`uv run python scripts/field_check.py`); JVM outputs stay byte-identical in every task.
- Truth first: no `resolved` row carries a guess. A call the framework itself rejects at runtime publishes no lying row; an unknown gets one general reason. Deployment-decides stands.
- DR-6: catalogs mirror the framework exactly; every catalog rule cites the probe that measured it. Probe docs cite symbols, never line numbers.
- Catalogs name defining-file symbols only (the file that defines the method, not the re-export).
- No framework names in general code; frameworks live in catalogs.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- New catalog vocabulary (a key D02 does not list) requires user approval before use.
- Pins: a pin diff is reviewed line by line; only truthful improvements are accepted into expectations.

## Review Focus

1. A module variable written once from a typed-return `def` and reassigned elsewhere in the same file (`settings = None` under a guard) — must stay untyped; a guess here publishes wrong field resolutions project-wide. Test in Task 1.
2. A `def` whose written return is `type[X]` (a class factory, ruling R17 territory) — `variable_class` must refuse it: the variable holds a class, not an instance. Test in Task 1.
3. An aiohttp relative URL on a session built without `base_url` — aiohttp raises; the row must be `unresolved`, never a guessed peer (the plan-3 httpx NULL-peer lie). Probe + test in Task 3.
4. A urllib3/aiohttp `request(method, url)` whose method is a variable, not a literal — the verb is unknown; the row must not claim one. Test in Tasks 3 and 4.
5. A call that writes two body keywords the library rejects together (aiohttp `data=` + `json=`) — mirror the framework: the probe measures what the library does, the catalog copies it, and no row invents a body. Probe in Task 2, tests in Tasks 3/4.

---

### Task 1: Typed-return module variables (OI-444, OI-445)

**Files:**
- Modify: `src/sextant/ingress/extract/python/project.py` (`variable_class`, ~:307)
- Modify: `src/sextant/domain/version.py` (FACT_SCHEMA_VERSION 16 → 17, with a history line in BOTH commented blocks, ~:148 and ~:245 style)
- Modify: `fixtures/orders-fastapi/app/settings.py`
- Test: `tests/ingress/extract/python/test_attribute_reads.py` (extend; follow the file's tmp_path fixture style)
- Test: `tests/e2e/test_orders_fastapi.py` (pinned; must pass UNCHANGED)
- Expectations: `scripts/field-expectations/py-mealie.json` (regenerate; review diff)

**Interfaces:**
- Consumes: `self.returns(method_descriptor(type_symbol(Target(module)), member, PY_SIGNATURE))` — the same lookup `_factory_class` uses.
- Produces: `variable_class(module, name) -> str | None` — signature unchanged; it now also returns the class symbol when the one write is a call of a scanned `def` whose written return names a class with a known shape (self or libraries, same shape check as today). A written return of `type[X]`, no annotation, a def outside `self._files`, or more than one write still gives None.

- [ ] **Step 1: Write the failing tests** in `test_attribute_reads.py`:

```python
def test_a_variable_from_a_typed_return_call_holds_the_class(tmp_path):
    # config.py: class Settings(BaseModel): debug: bool = False
    #            @lru_cache
    #            def get_settings() -> Settings: return Settings()
    #            settings = get_settings()
    # assert: an attribute read settings.debug in another function is a field fact of Settings
    # (same assertion style as test_a_variable_another_file_constructs_once_holds_that_class)

def test_an_unannotated_factory_leaves_the_variable_untyped(tmp_path):
    # def get_settings(): return Settings()  → no field fact

def test_a_class_returning_factory_is_not_an_instance(tmp_path):
    # def get_cls() -> type[Settings]  → no field fact

def test_a_reassigned_variable_stays_untyped(tmp_path):
    # settings = get_settings() then settings = None  → no field fact (closes OI-445's gap)
```

- [ ] **Step 2: Run them to verify they fail** — `uv run pytest tests/ingress/extract/python/test_attribute_reads.py -v`; the four new ones FAIL.

- [ ] **Step 3: Implement the new rung in `variable_class`.** When the single factory target is not a class: resolve the def like `_factory_class` does, take its written return, and accept it when `names_a_type(returned.symbol)` and the shape check passes; refuse `TYPE_OF`. Keep the existing construction path first.

- [ ] **Step 4: Run the four tests — PASS; run the file — all green.**

- [ ] **Step 5: Bump FACT_SCHEMA_VERSION to 17** (scan-time facts change: these variables' attribute reads become field facts). One history line per commented block.

- [ ] **Step 6: Switch the fixture to the real-world shape.** In `fixtures/orders-fastapi/app/settings.py`, replace `settings = Settings()` with:

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

(import `lru_cache` from functools; keep the docstring, note the plan-3→this-plan change in one line). This is the mealie/FastAPI shape; the pinned e2e rows must stay IDENTICAL — identical rows through this refactor are the end-to-end proof of the typing.

- [ ] **Step 7: Run `uv run pytest tests/e2e/test_orders_fastapi.py -v`** — every pinned row unchanged, all PASS. A changed row means the rung is wrong; fix the rung, never the pin.

- [ ] **Step 8: Regenerate the mealie pin and review the diff.** Expected movement: mealie's 4 settings guards `test` → `property`, and field reads over `get_app_settings()`-bound variables resolve. Check py-polar-server.json and py-dispatch.json for drift too; accept only truthful improvements, line by line. `uv run python scripts/field_check.py` — all 9 green.

- [ ] **Step 9: Full gate green, JVM byte-identical. Commit** (`feat(python): a module variable from a typed-return call holds that class (OI-444, OI-445)`).

### Task 1b: Star re-export member resolution (controller addition, ruling R4)

**Added mid-plan 2026-11-18.** Task 1's rung is correct but mealie did not move: `from mealie.core.settings import AppSettings` resolves through the package's `__init__.py`, which binds `AppSettings` only via `from .settings import *` — and the scanner skips star imports (imports.py, both `alias.name == "*": continue` arms). This is a general name-resolution gap: every member imported from a package that re-exports it with a star is unresolved, for calls and shapes alike. OI-444's stated example (mealie) needs it, so it is in scope.

**Files:**
- Modify: `src/sextant/ingress/extract/python/imports.py` (record a module's star-import bases in its header; on a member lookup that finds no explicit binding, consult the star bases' headers, Python's own rules: explicit bindings win over star names; `__all__` restricts a star when the source module defines it, else public names only (no leading `_`); later star import wins over earlier; chains followed with a visited-set guard)
- Modify: `src/sextant/domain/version.py` — NOT bumped again: Task 1's 17 is unreleased on this same branch; one bump per branch (controller ruling).
- Test: `tests/ingress/extract/python/` (the file where import-resolution tests live; follow its style)
- Expectations: regenerate the Python pins that truthfully move (mealie's 4 settings guards `test` → `property` is the expected headline); review every changed line.

**Interfaces:**
- Consumes: the headers/ModuleIndex lookup `member_of` already uses.
- Produces: `member_of` resolves names through star re-exports; no signature changes.

- [ ] **Step 1: Write failing tests**: a name star-re-exported through a package `__init__` resolves to its defining module's class (the mealie shape, as a tmp_path project); `__all__` excludes a name not listed; a leading-underscore name does not travel a star; an explicit binding in the `__init__` beats a star name; a two-step star chain resolves; a star cycle does not hang.
- [ ] **Step 2: Verify they fail.**
- [ ] **Step 3: Implement** (smallest change inside the existing lookup path).
- [ ] **Step 4: Tests pass; full gate green; JVM byte-identical.**
- [ ] **Step 5: Regenerate moved Python pins, review line by line, run `uv run python scripts/field_check.py` — 9 green. Commit.**

### Task 2: Wire probes for aiohttp and urllib3 (DR-6)

**Files:**
- Create: `scripts/probes/aiohttp_urllib3_rules.py`, `scripts/probes/aiohttp_urllib3_rules.md`
- Modify: `fixtures/orders-fastapi/pyproject.toml` + `uv.lock` (add `aiohttp`, `urllib3` — the fixture gains real call sites in Tasks 3/4, and the probe runs in its venv like `requests_httpx_rules.py`)

**Interfaces:**
- Produces: the measured rules Tasks 3 and 4 copy into catalogs, each quoted in the .md with the defining symbol (never a line number). Run form: `fixtures/orders-fastapi/.venv/bin/python -I scripts/probes/aiohttp_urllib3_rules.py`.

- [ ] **Step 1: Write the probe** (mirror `requests_httpx_rules.py`: local HTTP server, every rule asserted then printed, library identity reported by the running process). Measure at least:
  - aiohttp: the defining symbols of `ClientSession` and the module-level `aiohttp.request`; the verb-method set; `request(method, url)` verb casing; the `base_url` join rule (which relative forms join, which raise) and what a relative URL without `base_url` does; body keyword precedence and what `data=` + `json=` together does; whether `async with` changes anything on the wire (it must not).
  - urllib3: the defining symbols of `PoolManager.request` (inheritance: name the defining file's class); `request(method, url)` verb casing on the wire; `body=` / `json=` / `fields=` precedence and which combinations the library rejects; the module-level `urllib3.request`.
- [ ] **Step 2: Run it; every assertion passes.** Write the .md with quoted rules and symbols.
- [ ] **Step 3: Gate + pins green (fixture lock changed: e2e must still pass). Commit.**

### Task 3: aiohttp outbound catalog

**Files:**
- Create: `src/sextant/catalogs/aiohttp.yml`
- Modify: `fixtures/orders-fastapi/app/clients.py` (one `async with aiohttp.ClientSession(base_url=...)` client with a relative `post(..., json=...)`, plus one session without `base_url` making a relative call — the unresolved case)
- Test: `tests/application/test_python_outbound.py` (extend, same style), `tests/e2e/test_orders_fastapi.py` (new pinned rows)

**Interfaces:**
- Consumes: Task 2's measured rules; the existing `single_call` vocabulary exactly as `httpx.yml` uses it (owner, shape_model: pydantic, client_base with `client_arg: receiver` + `<init>` `base_url` ladder + join, methods with url_arg/method_arg/method_case/body_arg).
- Produces: outbound rows for aiohttp calls; no new vocabulary.

- [ ] **Step 1: Write failing unit tests** (relative-on-based-client resolves against the base; relative-without-base is `unresolved` with the general reason; `request(verb_var, url)` claims no verb; body field names come from the pydantic serializer rule).
- [ ] **Step 2: Verify they fail.**
- [ ] **Step 3: Write `aiohttp.yml`** — every rule cites `aiohttp_urllib3_rules.md`; owner lists defining symbols the probe reported.
- [ ] **Step 4: Unit tests pass.**
- [ ] **Step 5: Add the fixture call sites; extend the e2e pins with the new rows; run e2e — green.**
- [ ] **Step 6: Full gate + 9 pins green, JVM byte-identical. Commit.**

### Task 4: urllib3 outbound catalog

**Files:**
- Create: `src/sextant/catalogs/urllib3.yml`
- Modify: `fixtures/orders-fastapi/app/clients.py` (one `urllib3.request("POST", url, json=...)` or PoolManager site, absolute URL)
- Test: `tests/application/test_python_outbound.py` (extend), `tests/e2e/test_orders_fastapi.py` (new pinned rows)

**Interfaces:**
- Consumes: Task 2's rules; same vocabulary as Task 3. The verb is `method_arg: { arg: 0, keyword: method }` with `method_case` only if the probe measured upcasing.
- Produces: outbound rows for urllib3 calls. `HTTPConnectionPool(host, port)` relative requests are OUT of scope: the base is host+port constructor arguments, not a URL keyword the `client_base` ladder expresses, and no corpus uses it — log it as the next OI instead of building it.

- [ ] **Step 1: Write failing unit tests** (absolute `request("GET", url)` resolves with verb GET; variable method claims no verb; body per probe precedence).
- [ ] **Step 2: Verify they fail.**
- [ ] **Step 3: Write `urllib3.yml`** — rules cite the probe .md; owners are defining symbols.
- [ ] **Step 4: Unit tests pass.**
- [ ] **Step 5: Fixture site + e2e pins; green.**
- [ ] **Step 6: Full gate + 9 pins green, JVM byte-identical. Commit.**

### Task 5: Docs and close-out

**Files:**
- Modify: `docs/coverage/python.md` (the two "Not built (OI-454)" rows at ~:407–408 flip to built, with the catalog names; the OI-444 note on mealie's guards updates with the measured guard movement)
- Modify: `docs/COVERAGE.md` (the Python REST-out cell and its narrative at ~:785 — apply the cell's own written criterion to the new truth; state the before/after in the commit message)
- Modify: `CHANGELOG.md`, `docs/open-issues.md` (OI-444, OI-445, OI-454 move to the closed map; any new issues found this plan start at OI-459)
- Plane: closing SEXTANT-437/438/447 happens at finish, by the controller, after merge is requested — not in this task.

- [ ] **Step 1: Amend the docs with the measured numbers** (mealie guard movement, new outbound row counts from `scripts/probes/python_outbound_counts.py` if it covers the fixture corpora — otherwise state fixture evidence only; the corpus has zero aiohttp/urllib3 call sites, say so plainly in python.md).
- [ ] **Step 2: Full gate + pins green. Commit** (`docs: Python typed-return variables and aiohttp/urllib3 outbound (OI-444, OI-445, OI-454)`).
