# Flask REST-in Implementation Plan (Python plan 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flask inbound routes become endpoint rows — `@app.route`/verb shortcuts/`add_url_rule`, blueprints with prefixes (own, at registration, nested), path converters as written, and request reads (`request.args/headers/cookies/values`) as request requirements — moving COVERAGE's Python/Flask REST-in cell to ✅.

**Architecture:** Flask reuses the FastAPI machinery: decorators are the calls they are (design §3a), so `flask.yml` is a `fluent` inbound catalog shaped like `fastapi.yml` (roots with `http_method`/`url`/`handler` captures, `router_holds`, `mount`, `request_params`-style vocabulary). Two measured Flask rules the existing vocabulary cannot state need TWO new catalog words (**user approved 2026-11-19**): `path_join: single_slash` (Flask joins `url_prefix.rstrip("/") + "/" + rule.lstrip("/")`; `leading_slash` would publish `/api//items` where Flask serves `/api/items`) and a mount key `prefix_replaces_own: true` (`register_blueprint(bp, url_prefix=…)` REPLACES the blueprint's own `url_prefix`; FastAPI's include concatenates). Request reads reuse the `request_reads` vocabulary (Ktor/servlet) over the Python scanner's call facts — `flask.request` is an annotated module variable (`request: Request` in flask's `globals.py`), so plan-4's typed-variable machinery types the receiver.

**Tech Stack:** Python (ast scanner, DuckDB), YAML catalogs, Flask 3.x in the fixture venv only (Sextant never runs it; probes and oracles do, on purpose).

**Spec:** docs/superpowers/specs/2026-11-06-python-reader-design.md (§3a decorators; §7 probes); docs/coverage/python.md inbound table (Flask rows); COVERAGE.md REST-in Python/Flask row. Scope ruled 2026-11-19: REST-in Flask only; Flask-SocketIO is OI-477 (SEXTANT-470, whole Python WebSocket row in one later run). Controller files the driving Plane item (OI-478, "Flask REST-in") at execution start.

## Global Constraints

- `JAVA_HOME=/opt/homebrew/opt/openjdk@21` for every build and test run.
- Never use `git stash` (shared stack).
- Every task ends with the full gate green (`uv run pytest`) and all field pins green (`uv run python scripts/field_check.py`); JVM outputs stay byte-identical in every task. `examples/` is empty after PR #103: the first `field_check` run re-clones, which is slow once.
- Truth first: no `resolved` row carries a guess. A registration Flask itself refuses at import (unrooted rule path: werkzeug raises) publishes no lying row. Deployment-decides stands.
- DR-6: catalogs mirror the framework exactly; every catalog rule cites the probe that measured it. Probe docs cite symbols, never line numbers.
- Catalogs name defining-file symbols only — `route` and the verb shortcuts are defined on Flask's Scaffold base, not on `Flask`; the probe names the defining classes at the pinned version.
- No framework names in general code; frameworks live in catalogs.
- New catalog vocabulary (a key D02 does not list) requires user approval before use. The two words above ARE approved (user, 2026-11-19); any THIRD word a task finds it needs stops and asks.
- FACT_SCHEMA_VERSION bumps at most once on this branch (17 → 18), and only if scan-time facts change.
- Pins: a pin diff is reviewed line by line; only truthful improvements are accepted into expectations.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Review Focus

1. A blueprint with `url_prefix="/api/"` (trailing slash) and a route `"/items"` — the row must be `/api/items`, never `/api//items`. Test in Task 3.
2. `Blueprint(..., url_prefix="/v1")` registered with `register_blueprint(bp, url_prefix="/v2")` — rows under `/v2` only; concatenating to `/v2/v1` or keeping `/v1` is a lie. Test in Task 3.
3. One blueprint registered twice (distinct `name=`) under two prefixes — one row per registration, both prefixes served. Probe + test in Task 3.
4. `methods=["post"]` (lowercase) and a bare `@app.route("/x")` — the verb is upper-cased; absent means GET only, and the HEAD/OPTIONS rows Flask adds by itself are a stated catalog boundary, never invented rows. Probe in Task 1, test in Task 2.
5. `request.args["q"]` (subscript) is a required query parameter, `.get("q")` optional; the same method names on a receiver that is not the request must match nothing. Test in Task 4.

---

### Task 1: Fixture skeleton + Flask rules probe (DR-6)

**Files:**
- Create: `fixtures/orders-flask/pyproject.toml` + `uv.lock` (Flask 3.x pinned; `uv sync` venv like `fixtures/orders-fastapi`) and `fixtures/orders-flask/app/__init__.py` with a minimal `create_app()` (grows in Task 5)
- Create: `scripts/probes/flask_rules.py`, `scripts/probes/flask_rules.md`

**Interfaces:**
- Produces: the measured rules Tasks 2–4 copy into the catalog, each quoted in the .md with the defining symbol. Run form: `fixtures/orders-flask/.venv/bin/python -I scripts/probes/flask_rules.py`.

- [ ] **Step 1: Write the probe** (mirror `scripts/probes/fastapi_rules.py` style: register, read `app.url_map`, every rule asserted then printed, library identity reported by the running process). Measure at least:
  - defining classes/files of `route`, `get/post/put/patch/delete`, `add_url_rule` (Scaffold vs app vs blueprint at the pinned version); `add_url_rule`'s handler position (`view_func`).
  - `methods=`: absent → GET; casing on the wire (`url_map`); declared HEAD/OPTIONS; the automatic HEAD-on-GET and OPTIONS rows and `provide_automatic_options=False`.
  - path refusals: a rule without leading `/` (what werkzeug raises, at import); converters `<id>`, `<int:id>`, `<path:rest>` kept as written in `url_map`.
  - blueprint joins: own `url_prefix`; `register_blueprint(url_prefix=…)` REPLACES the own prefix; trailing-slash prefix joins with exactly one `/`; empty rule under a prefix serves the prefix itself; nested `bp.register_blueprint(child)` composes parent then child; one blueprint registered twice (needs distinct `name=` — measure what Flask refuses); `strict_slashes`/`merge_slashes` behavior (measured for the .md as a stated boundary, not modeled).
  - request reads: `flask.request`'s annotation in `globals.py`; the defining owners of `args`, `headers`, `cookies`, `values` properties; `args["q"]` raising `BadRequestKeyError` (= required) vs `.get` (optional); `values` merging query and form (= the `param` kind's exact meaning).
- [ ] **Step 2: Run it; every assertion passes.** Write the .md with quoted rules and defining symbols.
- [ ] **Step 3: Gate + pins green. Commit.**

### Task 2: `flask.yml` — routes

**Files:**
- Create: `src/sextant/catalogs/flask.yml` (`style: fluent`, `direction: inbound`, `detect.coordinates: [flask]`, `measured` citing `flask_rules.md`)
- Test: `tests/application/test_flask_routes.py` (mirror `tests/application/test_fastapi_routes.py` fixtures/style)

**Interfaces:**
- Consumes: the fluent inbound engine as `fastapi.yml` does (roots, `steps: __call__` for the decorator, `terminal`, `path_join` validated by `validated_path_join`).
- Produces: endpoint rows for `@app.route("/x", methods=[...])`, `@app.get/post/put/patch/delete`, `app.add_url_rule("/x", view_func=f)`, on `Flask` and `Blueprint` receivers (owners = the defining classes the probe names).

- [ ] **Step 1: Write the failing tests**: bare `@app.route("/items")` → `GET /items` only; `methods=["post", "delete"]` → POST and DELETE rows; `@app.get("/x")` shortcut; `add_url_rule` with `view_func=`; `<int:id>` published as written; a blueprint-owned route rows at the blueprint's own prefix even with no registration seen (pre-flight ruling: the FastAPI precedent — no new vocabulary; a never-registered blueprint is dead code, Minor by house rule).
- [ ] **Step 2: Verify they fail.**
- [ ] **Step 3: Write the catalog** — roots like `fastapi.yml`'s (`http_method: { keyword: methods, absent: GET, case: upper }` on `route`/`add_url_rule`; fixed verbs on shortcuts), `response_fallback: { from: handler_return }` with semantics identical to `fastapi.yml`'s (pre-flight ruling: it is the general fallback; absent annotation → the type the handler returns). Catalog comments state the automatic HEAD/OPTIONS boundary with the probe quote.
- [ ] **Step 4: Tests pass; gate + pins green; JVM byte-identical. Commit.**

### Task 3: Blueprints and prefixes (uses the two approved words)

**Files:**
- Modify: `src/sextant/catalogs/flask.yml` (`router_type`, `router_holds` for `Blueprint.<init>` `url_prefix=`, `mount` for `register_blueprint` on app and blueprint owners, `path_join: single_slash`, `prefix_replaces_own: true` on the mount entries)
- Modify: `src/sextant/application/resolve/shapes/inbound_routes.py` (`single_slash` in `validated_path_join` + `join_prefix`) and `src/sextant/application/resolve/shapes/mounts.py` (apply `prefix_replaces_own`)
- Modify: `docs/components/D02-catalog-schema.md` (the two new keys, one entry each)
- Test: `tests/application/test_flask_prefixes.py` (mirror `test_fastapi_prefixes.py`)

**Interfaces:**
- Consumes: Task 2's roots; the mount machinery `fastapi.yml` exercises.
- Produces: `join_prefix(prefix, path, "single_slash")` → `prefix.rstrip("/") + "/" + path.lstrip("/")` when path is non-empty, the prefix verbatim when path is `""`; mounts whose `prefix_arg` is written ignore the mounted router's own held prefix.

- [ ] **Step 1: Write the failing tests**: own `url_prefix` applies; registration `url_prefix` replaces it (Review Focus 2); trailing-slash prefix joins with one slash (Review Focus 1); nested blueprint = parent prefix then child; twice-registered blueprint rows under both prefixes (Review Focus 3); the Task 2 pin (a blueprint route with no registration rows at the blueprint's own prefix) stays green.
- [ ] **Step 2: Verify they fail.**
- [ ] **Step 3: Implement** — the smallest change inside `join_prefix`/`validated_path_join` and the mount prefix resolution; words and semantics exactly as the probe measured.
- [ ] **Step 4: Tests pass; gate + pins green; JVM byte-identical (the new words are additive; no JVM catalog declares them). Commit.**

### Task 4: Request reads

**Files:**
- Modify: `src/sextant/catalogs/flask.yml` (`request_reads`: via `args` → `get`/`__getitem__` kind query; `headers` → header; `cookies` → cookie; `values` → `param`; subscript = required, `.get` = optional, mirroring the probe)
- Modify (only if needed): `src/sextant/application/resolve/request_requirements.py` — if `request_reads` is not yet consumed for a `fluent` Python catalog's handlers, wire it over the Python call facts the scanner already writes (general rule, no framework names); `src/sextant/domain/version.py` 17 → 18 ONLY if scan-time facts must change.
- Test: `tests/application/test_flask_requests.py`

**Interfaces:**
- Consumes: plan-4 typed module variables (`flask.request` is annotated in flask's own `globals.py`, read from the installed fixture env) and the `request_reads` key as `ktor-routing.yml` declares it.
- Produces: `endpoint_metadata` requirement entries on Flask rows, kinds query/header/cookie/param.

- [ ] **Step 1: Write the failing tests**: `request.args.get("q")` → optional query `q`; `request.args["q"]` → required (Review Focus 5); `request.headers.get("X-Token")` → header; `request.cookies.get(...)` → cookie; `request.values.get(...)` → `param`; the same calls on a non-request receiver → nothing; a read in a helper the handler calls (same file) — assert whatever the JVM `request_reads` rule does today (handler body only, Ktor comment) and pin that boundary.
- [ ] **Step 2: Verify they fail.**
- [ ] **Step 3: Implement.** Body reads (`request.json`, `get_json()`, `request.form`) are a stated boundary (the coverage essay's overlay case): catalog comment + OI in Task 7, no rows.
- [ ] **Step 4: Tests pass; gate + pins green. Commit.**

### Task 5: Fixture surface + e2e oracle pin

**Files:**
- Modify: `fixtures/orders-flask/app/` — routes covering every Task 2–4 shape (bare route with methods, shortcut, `add_url_rule`, own-prefix blueprint, registration-override prefix, trailing-slash prefix, nested blueprint, twice-registered blueprint, `<int:id>`/`<path:rest>`, args/headers/cookies/values reads)
- Create: `tests/e2e/flask_oracle.py` (mirror `tests/e2e/fastapi_oracle.py`: subprocess under the fixture venv, dump `app.url_map` rules + methods as JSON)
- Create: `tests/e2e/test_orders_flask.py` (mirror `test_orders_fastapi.py`: expected rows written by hand from the fixture source, checked against the oracle AND against Sextant's derived rows; register the fixture in `tests/fixture_python.py`/`fixture_stub.py` the way `orders-fastapi` is)

**Interfaces:**
- Consumes: Tasks 2–4's catalog; the oracle comparison convention: Sextant's declared-method rows ⊆ the url_map rows, with Flask's automatic HEAD/OPTIONS excluded from the comparison and that exclusion stated in the test docstring.
- Produces: the pinned row list later tasks and plans must not break.

- [ ] **Step 1: Write the fixture routes and the hand-written expected rows (failing e2e test).**
- [ ] **Step 2: Oracle run agrees with the hand-written rows** (fix the hand-written list only where the oracle proves it wrong — the framework is the truth).
- [ ] **Step 3: Sextant rows match; gate + pins green. Commit.**

### Task 6: Corpus pins — redash and CTFd

**Files:**
- Create: `scripts/field-expectations/py-redash.json` (redash @ 09740ea), `scripts/field-expectations/py-ctfd.json` (CTFd @ a6a81dd) — sidecar locks like `py-dispatch.uv.lock` (N5) where the upstream is not a uv project; interpreter pin per `field_check.py`'s `build`/`python` docs.
- Test: `uv run python scripts/field_check.py` includes both, green.

**Interfaces:**
- Consumes: the whole catalog; `field_check.py`'s recording flow.
- Produces: measured numbers for Task 7's coverage statements.

- [ ] **Step 1: Clone, lock, record each pin; review every expectation line** — rows must be real core-Flask routes (blueprints, converters). Both corpora route their JSON APIs through Flask-RESTful (redash) / Flask-RESTX (CTFd): those endpoints are NOT expected rows; the pin records what core Flask serves, and the gap is Task 7's OIs, stated in each pin's `oracle`/notes field with counts (url_map total vs core-Flask-visible).
- [ ] **Step 2: Attempt the oracle per corpus** (`flask_oracle.py` against the corpus app under its env). If the app cannot build its `url_map` without services (likely for redash; CTFd may boot with SQLite), record the truthful fallback in the pin's notes: hand-verified sample instead of a full oracle, saying so.
- [ ] **Step 3: `field_check.py` green (all pins). Commit.**

### Task 7: Docs and close-out

**Files:**
- Modify: `docs/coverage/python.md` (Flask inbound rows → Built, with measured corpus numbers and the extension-gap statement), `docs/COVERAGE.md` (REST-in Python/Flask → ✅ with the shipped summary, counts cell), `CHANGELOG.md`, `docs/open-issues.md` (+ id map rows)
- Plane: close OI-478; file the boundary OIs (one each, measured statements): MethodView/`as_view` handlers; Flask-RESTful resources (redash's API surface); Flask-RESTX namespaces (CTFd's API surface); `subdomain=` on routes/blueprints; `strict_slashes`/`merge_slashes`; request body reads (`request.json`/`get_json`/`form` — the overlay case). Next OI id: OI-479 onward.

- [ ] **Step 1: Write the docs with the measured numbers from Tasks 5–6** (never predicted ones).
- [ ] **Step 2: File/close the Plane items; add the id-map rows.**
- [ ] **Step 3: Full gate + all pins green; JVM byte-identical. Commit.**
