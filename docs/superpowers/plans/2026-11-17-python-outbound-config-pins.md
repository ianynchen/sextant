# Python plan 3: outbound clients, configuration, field pins — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the approved Python reader design: outbound HTTP (`requests`, `httpx`),
configuration (`os.environ`, pydantic-settings, `.env`), settings-field conditions promoted from
`test` to `property`, and the three field pins — so every "Done when" item of the spec holds.

**Architecture:** No new pipeline. Outbound calls are `single_call` catalog entries read by the
existing engine; `httpx` base URLs go through the existing `client_base`; configuration reuses the
JVM's `config_model`, the field-sources ladder and `resolved_peers`; the pins extend
`scripts/field_check.py` with a Python build path. Four small vocabulary additions need approval
(§Needs approval) — everything else uses existing words.

**Tech Stack:** Python 3.12+ stdlib `ast`; DuckDB; YAML catalogs. `requests` (types from the
pinned typeshed), `httpx` (ships its own types), pydantic-settings — all read from the installed
environment, never imported by Sextant.

**Spec:** `docs/superpowers/specs/2026-11-06-python-reader-design.md` (APPROVED v2): §3c rows
left by plan 2 (`httpx.Client(base_url=)` → `client_base`; `.request("GET", url)` → verb from an
argument; `.model_dump()` bodies), §3d (configuration), §7 items 3–5 (pins, budget, truth).
Hand-offs from plan 2: `docs/superpowers/plans/2026-11-08-python-fastapi-inbound.md` §"What plan
3 needs from this plan". The 2026-11-09 OI-368 ruling binds Task 6: a guard reading a settings
field uses the existing `property` condition kind; plan 3 links settings fields to config keys.

## Global Constraints

- Truth: no `resolved` row carries a guessed value; unknown gets one general reason and a
  detail (`tell-the-truth`, one-reason-vocabulary). Per-path rows, never combined.
- Deployment decides: a value the deployment can change is "not evaluated" for existence;
  resolved values are facts about the repository.
- No framework names in general code; catalogs name only the defining symbol (ruling R18).
- JVM outputs stay byte-identical: 38+ fixture modules × 50 tables, `field_check.py` 6/6 pins,
  every task.
- Budget (spec §5, measured end of plan 2): polar cold 36.9 s / warm 1.5 s; mealie 12.6 s /
  1.2 s. Ceiling 300 s / 30 s fails the task; every pass added states its runs × rows first
  (GUIDELINES §8.7).
- JVM fixtures build with `JAVA_HOME=/opt/homebrew/opt/openjdk@21`. Never use `git stash`.
- Per-file reuse holds: a changed catalog or code digest invalidates reuse keys; an unchanged
  tree skips the resolve.
- Branch `cov/python-outbound`, worktree `.worktrees/python-outbound` (create with the
  worktrees skill at execution start; commit this plan there first).

## Needs approval

Format: the item, options, then **Recommend**. Tasks name the items they use.

**N1 — a value-model word for environment reads** (spec §3d says `os.environ[...]`/`os.getenv`
are "value-model data", but no such entry kind exists; the JVM has none to copy).
- A. New value-model block `environment:` with entries
  `{owner, method, key_arg, default_arg?}` (keyword forms allowed, as everywhere). The call's
  value becomes the expression `${KEY}` when the key is a literal, with the default recorded as
  a declared default; a non-literal key is `unresolved non_enumerable`. General: a later JVM
  entry for `java.lang.System#getenv` uses the same word (and would close the published-default
  bug noted at D00:1573).
- B. A Python-only rule in the resolver, no catalog word.
- **Recommend A** — it is data, not code; B would put a framework-shaped rule in general code.

**N2 — field-sources keys for pydantic-settings** (the existing `field_sources` ladder is
annotation-based; a settings class has no annotations — its prefix sits in
`model_config = SettingsConfigDict(env_prefix=...)` and its name in the field or its alias).
- A. Extend the `field_sources` block with a class-based form:
  `settings_base` (the base class that makes a class a settings class),
  `config_call` (the call read for configuration — already the shape-model's word),
  `prefix_key` (`env_prefix`), `name_from: [validation_alias, alias, name]`,
  `case_insensitive` (default true, pydantic-settings' own default). Rung 3 then yields
  `${PREFIX+NAME}` exactly as the Spring rung yields `${prefix.name}`.
- B. A separate new catalog block for settings classes.
- **Recommend A** — same ladder, same output; the keys mirror pydantic-settings' documented
  resolution (DR-6), checked by a probe in Task 0.

**N3 — a config source named by the code** (spec §3d: `.env` is "a `config_model` source, only
the file the code names"; today `sources` are glob patterns, no reader claims a suffix-less
file, and the built-in ignore layer refuses `.env` outright).
- A. `config_model.sources` accepts `{from_argument: env_file}`: the file named by that keyword
  on the settings class's config call, read by a new dotenv reader registered by file NAME.
  The config reader opens the named file deliberately — the ignore layer still hides `.env`
  from the scan walk, so no unnamed `.env` is ever read. A file named through a variable is
  `external` (spec). Values from the named file land in `resolved_config` like any config
  entry (the JVM already reads application.yml with whatever it holds).
- B. Do not read `.env`; every env-file value stays `external`.
- **Recommend A** — it is the approved spec sentence; B descopes an approved line.

**N4 — a shape-model word for serializer calls** (`payload.model_dump()` passed as `json=`:
nothing says the call's result carries the receiver's shape).
- A. `shape-models/pydantic.yml` key `serializers: [model_dump, model_dump_json]`: an argument
  that is such a call is described by its receiver's shape.
- B. Leave it: such bodies are `unresolved`, reason recorded.
- **Recommend A** — one key, mirrors pydantic; polar and mealie both write this shape.

**N5 — the dispatch pin's environment** (spec §7.3 pins dispatch; its checkout has NO lock file
of any kind, so `uv sync --frozen` cannot work and any fresh resolve is unreproducible).
- A. Commit a sidecar lock: generate `uv.lock` once, store it as
  `scripts/field-expectations/py-dispatch.uv.lock`; the pin step copies it into the checkout
  (untracked, so the dirty check stays green) and runs `uv sync --frozen --no-install-project`.
- B. Pin dispatch without an environment (typeshed only) and accept the lower yield.
- C. Drop dispatch from the pins (a spec §7.3 change).
- **Recommend A** — reproducible, touches no upstream file, keeps the spec's pin.

**Already ruled, used as given:** settings-read guards → `property` kind with the field's
config key, per-row storage (user, 2026-11-09); recipe hop for a client handed in by `Depends`;
`parameter_markers` for defaulted `timeout`/`base_url` arguments.

## Review Focus

1. `os.getenv("K") or "default"` and `os.environ.get("K", d)` — the default must never publish
   as the resolved value (the JVM's Ktor bug, D00:1573). Test in Task 3.
2. A verb held in a variable (`client.request(method, url)`) — `method` NULL, row `unresolved`,
   never a guessed verb. Test in Task 2.
3. An `httpx` call on a client with no `base_url` and a relative path — peer `unresolved`, the
   path kept; never an invented host. Test in Task 2.
4. A settings field whose env name differs by case or alias — the key must follow
   pydantic-settings' own resolution (prefix + alias, case-insensitive). Test in Task 5.
5. An `.env` entry for a field the class does not declare, and an `env_file` chosen through a
   variable — no invented field; the variable case is `external`. Test in Task 4.

---

### Task 0: Probes, baselines, costs

**Files:**
- Create: `scripts/probes/requests_httpx_rules.py` + `.md`, `scripts/probes/pydantic_settings_rules.py` + `.md`
- Test: probe scripts self-assert (run with `python -I`, as the existing probes)

**Interfaces:**
- Produces: the quoted framework rules every later task's catalog data copies; the measured
  pass costs; the corrected plan text if a probe disagrees (report to controller before Task 1,
  as plan 2's R5 ruled).

- [ ] **Step 1:** Probe `requests` and `httpx` in the fixture's environment: defining symbols
  (`requests.api.*`, `requests.sessions.Session.*` from typeshed; `httpx._api.*`,
  `httpx._client.Client/AsyncClient.*` from httpx's own types); the verb set; `url_arg`
  positions; keyword bodies `json=`, `data=`, `content=`; `request(method, url)` argument
  order; how `httpx` joins `base_url` with a request path (its documented merge, quoted);
  that `requests.Session` has no base URL.
- [ ] **Step 2:** Probe pydantic-settings: env name = `env_prefix` + (validation_alias | alias |
  field name), case-insensitivity default, precedence env > dotenv > field default,
  `env_file=` reading, what a missing file does. Record exact quotes.
- [ ] **Step 3:** Count in polar/mealie/dispatch: outbound call sites per library and form
  (module-level `requests.get`, session/client method, `request(method,...)`), `os.environ`
  read forms, settings classes and their field counts, guards whose reads name a settings
  field. State the §8.7 cost line: each new pass's runs × rows on polar.
- [ ] **Step 4:** Record the plan-start baseline (polar, mealie, Sextant cold/warm) in the
  ledger. Commit probes.

### Task 1: A construction's object is keyed by its value, not its receiver (OI-341)

**Files:**
- Modify: `src/sextant/application/resolve/shapes/client_base.py:982` (`_Options._stored`),
  `src/sextant/application/resolve/shapes/arguments.py` (`_linked_constructor`),
  `src/sextant/application/resolve/shapes/chains.py` (`_chain_key` constructor root)
- Test: `tests/application/test_client_base.py` (extend), `tests/application/test_values.py`

**Interfaces:**
- Produces: the three readers key a constructor's object by `receiver` when present, else by
  the construction's value id (the virtual `<init>` form Python writes). Task 2's
  `httpx.Client(base_url=...)` options depend on this.

- [ ] **Step 1:** Write a failing test: a class constructed through a virtual `<init>` (no
  receiver) with a keyword option is found by `_Options`; the JVM receiver form still works.
- [ ] **Step 2:** Run; expect FAIL (no object found).
- [ ] **Step 3:** Implement the shared keying rule once (follow-the-object: value id + method),
  used by all three readers.
- [ ] **Step 4:** Gate: full suite + JVM tables identical + pins 6/6. Commit. Close OI-341.

### Task 2: Outbound catalogs — `requests` and `httpx`

**Files:**
- Create: `src/sextant/catalogs/requests.yml`, `src/sextant/catalogs/httpx.yml`,
  `fixtures/orders-fastapi/app/clients.py`
- Modify: `src/sextant/catalogs/shape-models/pydantic.yml` (N4 `serializers`),
  `tests/e2e/test_orders_fastapi.py` (`PINNED` outbound rows)
- Test: `tests/application/test_python_outbound.py`, e2e pinned rows

**Interfaces:**
- Consumes: Task 1's keying; plan 2's `parameter_markers` (defaulted `timeout`/`base_url`),
  recipe hop (`AsyncClient` provided by `Depends`), `argument_descriptor` for bodies.
- Produces: outbound endpoint rows for both libraries; the fixture's outbound pinned list.

- [ ] **Step 1:** Write `app/clients.py`: module-level `requests.get` with an f-string URL; a
  `Session` used across methods; `httpx.Client(base_url=...)` as a singleton;
  `httpx.AsyncClient` from a `Depends` recipe; `client.request(verb_var, url)` (unresolved
  verb); a relative-path call on a client without `base_url`; a `json=payload.model_dump()`
  body. Extend `PINNED`; run the e2e test; expect FAIL (missing rows).
- [ ] **Step 2:** Write `requests.yml` and `httpx.yml`: `style: single_call`,
  `direction: outbound`, `protocol: http`, `shape_model: pydantic`,
  `detect.coordinates: [requests] / [httpx]`; rows per verb with
  `http_method`, `url_arg: 0` (`1` on `Session`/`Client` methods counted per the probe),
  `body_arg: {keyword: json}` (+`data`, `content` per probe); `request` rows with
  `method_arg`; `httpx.yml` `client_base` from the probe's quoted join rule. Catalog owners
  are the defining symbols from Task 0.
- [ ] **Step 3:** Add N4 `serializers` to `pydantic.yml`; unit tests for the Review Focus
  items 2 and 3 and the serializer body.
- [ ] **Step 4:** Run e2e; expect PASS. Measure polar/mealie/dispatch outbound row counts;
  hand-check a sample of 5 per corpus and record it in the ledger (spec §7.3).
- [ ] **Step 5:** Gate; commit.

### Task 3: Environment reads as values (N1)

**Files:**
- Create: `src/sextant/catalogs/value-models/python-environment.yml` (or extend
  `python-wrappers.yml` if the loader prefers one file — implementer's choice)
- Modify: the value-model loader (`ingress/catalogs/yaml_source.py`) and the walk's read of the
  new entries (`application/resolve/values.py`)
- Test: `tests/application/test_environment_reads.py`

**Interfaces:**
- Consumes: N1 approval.
- Produces: a call matching an entry resolves to the expression `${KEY}` with any declared
  default kept as a default, never as the value. Tasks 4–6 and `resolved_peers` consume the
  expression.

- [ ] **Step 1:** Failing tests: `os.getenv("HOST")` in an f-string URL yields
  `http://${HOST}/x`; `os.environ["HOST"]` and `os.environ.get("HOST", "d")` the same with
  the default recorded; `os.getenv(var)` is `unresolved non_enumerable`;
  `os.getenv("K") or "d"` never publishes `"d"` (Review Focus 1).
- [ ] **Step 2:** Entries for `os.getenv`, `os.environ.__getitem__`, `os.environ.get` (typeshed
  defining symbols). Implement the loader + walk arm. Run; expect PASS.
- [ ] **Step 3:** Gate (JVM identical — the new word loads from data no JVM catalog declares);
  commit.

### Task 4: The named `.env` file as a config source (N3)

**Files:**
- Create: `src/sextant/ingress/read/dotenv.py`
- Modify: `src/sextant/ingress/read/registry.py`, `application/resolve/config.py`
  (`config_model_of` must select per module — today it takes the first declared model in the
  workspace, which breaks a polyglot repo), the Python catalog that declares the model
- Test: `tests/ingress/test_dotenv.py`, `tests/application/test_python_config.py`

**Interfaces:**
- Consumes: N3 approval; Task 5 names which call's `env_file` argument is read.
- Produces: `resolved_config` rows for the named file under environment `default`; a file
  named through a variable → no rows, the settings fields stay `external` with the detail
  naming the expression.

- [ ] **Step 1:** Failing tests: a named `.env` yields `resolved_config` rows; an unnamed
  `.env` in the tree is never opened (the ignore layer's test extended, not weakened); a
  variable `env_file` is `external`; Review Focus 5.
- [ ] **Step 2:** Implement the dotenv reader (KEY=VALUE, `#` comments, quotes — the rules
  python-dotenv documents, quoted by Task 0's probe) and the `{from_argument: env_file}`
  source; scope `config_model_of` per module.
- [ ] **Step 3:** Gate; commit.

### Task 5: pydantic-settings fields on the ladder (N2)

**Files:**
- Modify: `src/sextant/catalogs/httpx.yml` + `requests.yml` (`field_sources` block),
  `src/sextant/application/resolve/`(the rung-3 engine, M04 §field-sources),
  `fixtures/orders-fastapi/app/settings.py` (create: `BaseSettings`, `env_prefix`, one alias,
  an `env_file=".env"`, a field feeding a client's `base_url`)
- Test: `tests/application/test_settings_fields.py`, e2e `PINNED`

**Interfaces:**
- Consumes: N2 approval; plan 2's PEP 526 class-body defaults; Task 4's sources.
- Produces: a read of `settings.X` resolves to `${PREFIX+NAME}`; `resolved_peers` answers per
  environment with the `.env` value or the field default as the repository's answer,
  `external` where nothing in the repository sets the key. Task 6 maps the same field to its
  key for conditions.

- [ ] **Step 1:** Failing tests: a `base_url` fed by a settings field gives an outbound row
  whose peer is the key expression, and `resolved_peers` fills it from `.env` / the default;
  Review Focus 4 (alias + case).
- [ ] **Step 2:** Implement the class-based rung (N2 keys); wire the fixture's
  `app/settings.py` and point one client's `base_url` at it; extend `PINNED`.
- [ ] **Step 3:** Gate; commit.

### Task 6: Settings guards become `property` conditions

**Files:**
- Modify: `src/sextant/application/resolve/registration_conditions.py` (classify a guard whose
  reads resolve to settings fields), `fixtures/orders-fastapi/app/flags.py` → delete,
  `app/support.py` + `app/main.py` (the switch becomes `settings.SUPPORT_ROUTES`, per the
  fixture README), e2e `PINNED` (`endpoint_existence` rows)
- Test: `tests/application/test_registration_conditions.py` (extend)

**Interfaces:**
- Consumes: Task 5's field→key mapping; the 2026-11-09 ruling (kind `property`, per-row
  storage, "not evaluated", repository value as evidence — same evidence lines as
  `bean_conditions` `_judged` with `set_by: deployment`).
- Produces: `endpoint_existence` rows with `kind: property` and the key in the expression;
  guards no settings field explains stay `test`.

- [ ] **Step 1:** Failing test: the fixture's support route carries `kind: property`,
  expression naming `${PREFIX+SUPPORT_ROUTES}`, holds "unresolved", evidence quoting the
  repository value; a non-settings guard stays `test`.
- [ ] **Step 2:** Implement; measure polar's `/backoffice` rows and mealie's SPA rows move
  from `test` to `property`; record the counts.
- [ ] **Step 3:** Gate; commit.

### Task 7: Python field pins

**Files:**
- Modify: `scripts/field_check.py` (a `uv` build path beside Maven: `uv sync --frozen
  --no-install-project` into the checkout, `jdk`/`maven` keys unused)
- Create: `scripts/field-expectations/py-polar-server.json`, `py-mealie.json`,
  `py-dispatch.json` (+ `py-dispatch.uv.lock`, N5)
- Test: `python scripts/field_check.py py-polar-server py-mealie py-dispatch`

**Interfaces:**
- Consumes: every earlier task's output; the spec's pinned commits (§2: polar 0e5a3f1,
  dispatch dd2837e, mealie c3dc906).
- Produces: three pin files asserting endpoints metadata and the Inbound/Outbound route
  tables, as the JVM pins do; the route counts cross-checked once against
  `tests/e2e/fastapi_oracle.py` run on each corpus's own environment (the oracle never ships
  in the pin run).

- [ ] **Step 1:** Add the Python build path; write the polar pin from the current output
  (668/671 oracle pairs recorded beside it); run; expect PASS.
- [ ] **Step 2:** mealie pin (289/289). dispatch per N5; record its oracle count.
- [ ] **Step 3:** Record final timings against the budget in
  `docs/research/2026-11-06-python-performance.md`. A ceiling miss stops for a ruling.
- [ ] **Step 4:** Gate (all 9 pins); commit.

### Task 8: Docs, logged items, close-out

**Files:**
- Modify: `docs/components/D02-catalog-schema.md` (N1–N4 words), `D00-fact-schema.md` (none
  expected — state "no fact change" or the delta), `M03`/`M04`, `docs/COVERAGE.md` (Python
  §2a REST-out cell → ✅ requests+httpx; §5.2 row; the stale "27.6 s" line at :761),
  `docs/coverage/python.md` (outbound + configuration sections), `fixtures/orders-fastapi/
  README.md` (drop the "left for plan 3" paragraph), `CHANGELOG.md`, `docs/open-issues.md`
- Test: the full gate; the doc-truth architecture tests

- [ ] **Step 1:** Write the docs; every logged Minor from the task reviews gets an OI row
  (next id OI-418) and a Plane item.
- [ ] **Step 2:** Full gate + 9 pins + fixture e2e. Commit; open the PR (auto_fix +
  address_comments on).

## Self-review (done at writing)

- Spec coverage: §3c remaining rows → Tasks 2 (clients, verb-arg, bodies) and 1 (client_base
  through a class object); §3d → Tasks 3–5; the 10b ruling → Task 6; §7.3–7.5 → Task 7;
  §7.6 docs → Task 8. `aiohttp`/`urllib3` are not in the spec's §3c table and stay logged
  (COVERAGE §5.2 cell text updated to say which half is built).
- Types: `parameter_markers`, `argument_descriptor`, `resolved_config`, `endpoint_existence`
  names match plan 2's build.
- Proportion: 8 tasks against a 7-page spec section; no code bodies beyond catalog shapes.
