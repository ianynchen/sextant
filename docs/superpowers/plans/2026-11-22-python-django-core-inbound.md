# Django core REST-in Implementation Plan (Python plan 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Django `urlpatterns` become endpoint rows — `path`/`re_path` with function views and class views, every `include` form, verbs narrowed by `require_*` decorators, and request reads — moving COVERAGE's Python/Django REST-in cell from "not yet" to built.

**Architecture:** Django reuses the Flask/FastAPI machinery: `django.yml` is a `fluent` inbound catalog whose roots are the module functions `path` and `re_path` (they already bind to `django.urls.conf`, measured). Django has no receiver object, so seven general capabilities carry it (design §5b): a list is a router; a mount through an inner call; a router named by a module name; an any-method row narrowed by a decorator; verbs from the methods a class defines; a decorator class that extends `classmethod`; a framework-typed handler parameter. `re_path` uses three structural reads (design §5c), never a regex parser.

**Tech Stack:** Python (ast scanner, DuckDB), YAML catalogs, Django in the fixture venv only (Sextant never runs it; probes and oracles do, on purpose).

**Spec:** docs/superpowers/specs/2026-11-22-python-django-core-design.md (approved 2026-11-22: scope, pins, §5c reads 1–3, new words only where no existing word fits). Parent: docs/superpowers/specs/2026-11-06-python-reader-design.md. The controller files the driving Plane item (OI-500, "Django core REST-in") at execution start.

## Global Constraints

- `JAVA_HOME=/opt/homebrew/opt/openjdk@21` for every build and test run.
- Never use `git stash` (shared stack).
- Every long run is timeboxed: expected duration stated, hard kill at 3x (gate 450 s, pins 650 s expected). A killed run is diagnosed, never waited on.
- Every task ends with the full gate green (`bash scripts/check.sh`, real exit code, never piped through `tail`) and all field pins green (`uv run python scripts/field_check.py`). JVM outputs and the 12 existing pins stay byte-identical in every task.
- Truth first: no `resolved` row carries a guess. A row Django does not serve, or a method Django answers 405, is a lie. Deployment-decides stands (`if settings.DEBUG:` is "not evaluated").
- DR-6: the catalog mirrors Django exactly; every catalog rule cites the probe that measured it. Probe docs cite symbols, never line numbers.
- Catalogs name defining-file symbols only.
- No framework names in general code; Django lives in `django.yml`. Each capability is the general rule, never the Django case.
- New catalog vocabulary: **reuse first** (user ruling 2026-11-22). Task 2 decides, per capability, whether an existing word states the rule: candidates are `mount.router_arg` (click uses `chain_result`), the servlet catalog's `dispatch:` (method name → verb), `path_join: concatenate`, and the null method spring-webflux-router publishes. A new word is used only where Task 2 records why no existing word fits; at most three new words (design capabilities 2, 3, 5). A fourth stops and asks.
- `FACT_SCHEMA_VERSION` bumps at most once on this branch (18 → 19), and only if scan-time facts change.
- Pins: a pin diff is reviewed line by line; only truthful improvements are accepted.
- Do not widen a truth rule beyond what its task states (lesson of PR #109).
- Commits end with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Review Focus

1. `path("api/", include(x))` over `path("items/", v)` serves `/api/items/`; `path("api", include(x))` serves `/apiitems/`. The join adds nothing. A slash added or removed is a lie. Test in Task 3.
2. One list included under two prefixes gives one row per prefix; a list included by module name from another file gives the same rows as the same list included by object. Test in Task 3.
3. A function view with `@require_POST` gives one POST row and no other; with `@require_http_methods(["GET", "POST"])` two rows; with no decorator one row with no method. A `csrf_exempt(view)` or `cache_page(60)(view)` wrapper in the `path` call must not hide the function's own `require_*` decorator. Test in Task 4.
4. A class view serves the verbs its class **and its bases** define; `options` and the automatic `head` are never rows; a class that sets `http_method_names = ["get"]` and defines `post` serves GET only. Test in Task 5.
5. `^inbox/?$` gives `/inbox` and `/inbox/`; `^r/(?P<id>\d+)(\.json)?/?$` gives four rows; three optional pieces, an unnamed non-optional group or `|` gives one `partial` row with the expression as written — never a `resolved` guess. Test in Task 6.

---

### Task 1: Fixture skeleton + Django rules probe (DR-6)

**Files:**
- Create: `fixtures/orders-django/pyproject.toml` + `uv.lock` (Django pinned; `uv sync` venv like `fixtures/orders-flask`), `fixtures/orders-django/shop/{__init__,settings,urls,views}.py` minimal (grows in Task 8)
- Create: `scripts/probes/django_rules.py`, `scripts/probes/django_rules.md`

**Interfaces:**
- Produces: the measured rules Tasks 2–7 copy into the catalog, each quoted in the .md with its defining symbol. Run form: `fixtures/orders-django/.venv/bin/python -I scripts/probes/django_rules.py`.

- [ ] **Step 1: Write the probe** (mirror `scripts/probes/flask_rules.py`: build url lists, walk `django.urls.get_resolver(...)`, drive `django.test.Client` for status codes, assert then print every rule, report library identity). Measure at least:
  - defining module/symbols of `path`, `re_path`, `include` (they are `functools.partial` objects over `_path` — record what the scanner must name), `View.as_view`, `classonlymethod`'s base class.
  - the join: prefix and child route concatenated with nothing between; the leading `/`; an empty route; converters `<id>`, `<int:id>`, `<path:rest>`, `<uuid:x>` as the resolver reports them; a custom converter registered with `register_converter`.
  - `include` with: a dotted string, a module object, a list, a `(list, app_name)` tuple, `namespace=`; the variable name Django reads (`urlpatterns`); one list included twice.
  - function views: every method reaches the view (GET, POST, PUT, DELETE → 200); `require_http_methods`, `require_GET`, `require_POST`, `require_safe` → the exact allowed sets and 405 for the rest; the decorators' defining module; whether `csrf_exempt(view)` and `cache_page(n)(view)` keep the inner function's allowed set.
  - class views: which names `as_view()` dispatches (`http_method_names`); inherited verb methods; an overridden `http_method_names`; `options` defined on `View`; the automatic `head`; `as_view(http_method_names=[...])` initkwargs (measure; state as boundary if not modelled).
  - `re_path`: no `$` matches a prefix; no `^` (measure what Django does — `re.search` from the current position); `/?`; named and unnamed groups (unnamed groups are ignored when a named group exists — measure).
  - request reads: `HttpRequest.GET`/`COOKIES`/`headers`/`META` defining symbols; `request.GET["k"]` raising `MultiValueDictKeyError` and the status it gives (measure: 400 or 500) vs `.get`; parameter 0 of every view is the request, for function views and for class verb methods (`self` first).
  - `ROOT_URLCONF` and `request.urlconf` (stated boundary for §5d).
- [ ] **Step 2: Run it; every assertion passes.** Write the .md with quoted rules and defining symbols.
- [ ] **Step 3: Gate + pins green. Commit.**

### Task 2: Vocabulary decision + `django.yml` routes for function views behind `path`

**Files:**
- Create: `src/sextant/catalogs/django.yml` (`style: fluent`, `direction: inbound`, `detect.coordinates: [django]`, `measured` citing `django_rules.md`)
- The vocabulary decision is recorded in the ledger and in the catalog's comments; no separate document.
- Test: `tests/application/test_django_routes.py` (mirror `tests/application/test_flask_routes.py`)

**Interfaces:**
- Consumes: the fluent inbound engine as `flask.yml` does (roots on a module owner, as `httpx.yml` names `httpx._api`).
- Produces: (a) the ledger entry "Vocabulary": for each of capabilities 2, 3, 5 — the existing word reused, or the new word with the reason no existing word fits. Tasks 3 and 5 use exactly these spellings. (b) endpoint rows for `path("x/", view_function)` in a module-level list, method absent (the any-method row), path `/` + route, converters as written.

- [ ] **Step 1: Read `docs/components/D02-catalog-schema.md` and the candidate words named in Global Constraints; write the Vocabulary ledger entry.** If more than three new words are needed, stop and ask.
- [ ] **Step 2: Write the failing tests**: `path("", v)` → `/`; `path("items/<int:id>/", v)` → `/items/<int:id>/`, no method; a view imported from another module is the handler; `path(route="x", view=v)` keywords; a `path` call that is not inside any list reaching a `urlpatterns` (a stray call) — pin what the Flask precedent does and state it.
- [ ] **Step 3: Verify they fail. Write the catalog roots** (`path`, captures `url` arg 0 / keyword `route`, `handler` arg 1 / keyword `view`; `path_join: concatenate`; the measured root-slash rule). If the any-method row needs engine work, the general rule is "a root that captures no `http_method` and whose catalog declares none publishes a null method".
- [ ] **Step 4: Tests pass; gate + pins green; JVM byte-identical. Commit.**

### Task 3: Lists as routers and `include` (capabilities 1, 2, 3)

**Files:**
- Modify: `src/sextant/catalogs/django.yml` (`mount` for `path`/`re_path` whose view argument is an `include` call; the router-by-module-name declaration, spelled as Task 2 decided)
- Modify: `src/sextant/application/resolve/shapes/mounts.py` and the fluent engine under `src/sextant/application/resolve/engines/` (general rules: a registration's router is the list value it is an element of; a mount's router argument may be read through an inner call; a string router argument names a module whose catalog-given variable is the router); the Python scanner under `src/sextant/ingress/extract/python/` only if list-element facts are missing (then 18 → 19)
- Modify: `docs/components/D02-catalog-schema.md` (each new key, one entry)
- Test: `tests/application/test_django_includes.py`

**Interfaces:**
- Consumes: Task 2's roots; the value walk's answers for list values (`+`, `+=`, `append`, `extend` — count the questions asked per registration and state it in the report, GUIDELINES §8.7).
- Produces: prefixed rows for every `include` form the probe measured.

- [ ] **Step 1: Write the failing tests**: Review Focus 1 and 2; `include("pkg.urls")`; `include(module)`; `include(local_list)`; `include((local_list, "app"))`; `include(x, namespace="n")`; three levels of nesting; `urlpatterns = a + b`; `urlpatterns += [...]`; `urlpatterns.extend(...)`; `if settings.DEBUG: urlpatterns += [...]` → rows "not evaluated"; a list nothing includes → served at `/` (design §5d); `include(router.urls)` on an object the catalog does not know → no row and one open question (DRF boundary, never silent).
- [ ] **Step 2: Verify they fail. Implement** the smallest general change per capability.
- [ ] **Step 3: Tests pass; gate + pins green; JVM byte-identical. Commit.**

### Task 4: Verbs of function views (capability 4)

**Files:**
- Modify: `src/sextant/catalogs/django.yml` (the four `require_*` decorators with their measured method sets)
- Modify: the handler-decorator reading in the fluent engine, only as far as "a decorator call on the handler, or a wrapper call around it in the registration, that the catalog names narrows the row's methods" (general)
- Test: `tests/application/test_django_verbs.py`

**Interfaces:**
- Consumes: "every decorator is the call it is" (design 2026-11-06-reading-decorators §3a) and the handler follow-back Flask uses.
- Produces: one row per allowed method; the null-method row only where no narrowing decorator is found on a path that was fully read.

- [ ] **Step 1: Write the failing tests**: Review Focus 3; `require_safe` → the measured set; a `require_*` under another decorator the catalog does not know (`@login_required` above or below); the handler wrapped in the `path` call by `csrf_exempt(v)`; a project-own decorator whose body cannot be followed to the function → the row keeps the handler unresolved rather than claiming every method.
- [ ] **Step 2: Verify they fail. Implement.**
- [ ] **Step 3: Tests pass; gate + pins green. Commit.**

### Task 5: Class views (capabilities 5, 6)

**Files:**
- Modify: `src/sextant/ingress/extract/python/` (general: a decorator whose class extends `classmethod` or `staticmethod` binds as that builtin does — `as_view` then binds to `View.as_view`; 18 → 19 if facts change)
- Modify: `src/sextant/catalogs/django.yml` (the handler read through `as_view`; the verb-method names from the probe, spelled as Task 2 decided — the servlet `dispatch:` word if it fits)
- Modify: the fluent engine (general: a handler given as "class through a catalog-named call" yields one row per catalog-named method the class defines, own or inherited; the handler is that method)
- Test: `tests/application/test_django_class_views.py`

**Interfaces:**
- Consumes: C3 lookup the resolver already has; library classes read from the installed env (`TemplateView.get` is a base's method).
- Produces: per-verb rows with the verb method as handler. OI-479..490 hold a Flask `MethodView`/`as_view` gap: check whether this capability closes it; if it does with a catalog entry only, add it and say so; otherwise leave it and note it in Task 10.

- [ ] **Step 1: Write the failing tests**: Review Focus 4; `View` subclass with `get` + `delete`; verbs inherited from a project base; from a library base (`TemplateView` → GET); `as_view(template_name="x")` with arguments; a class the module imports from another file; a class whose bases cannot all be read → rows for the verbs found, marked `partial` (a base may add more).
- [ ] **Step 2: Verify they fail. Implement.**
- [ ] **Step 3: Tests pass; gate + pins green; JVM byte-identical. Commit.**

### Task 6: `re_path` (design §5c, reads 1–3)

**Files:**
- Create: `src/sextant/application/resolve/shapes/route_expression.py` — `paths_of(expression: str) -> tuple[tuple[str, ...], bool]`: the published paths and whether they are exact
- Modify: `src/sextant/catalogs/django.yml` (`re_path` root; a catalog key that says the url capture is a route expression — reuse an existing key if one states it)
- Test: `tests/application/test_route_expression.py`, additions to `tests/application/test_django_routes.py`

**Interfaces:**
- Produces: `paths_of("^inbox/?$") == (("inbox", "inbox/"), True)`; `paths_of("^old/(?P<item_id>\\d+)/$") == (("old/<item_id>/",), True)`; `paths_of("^(shelf|books)/$") == (("^(shelf|books)/$",), False)`. Exact → `resolved` rows, one per path; not exact → one `partial` row with the expression as written.

- [ ] **Step 1: Write the failing tests** from the table below, plus Review Focus 5:

| Expression | Paths | Exact |
|---|---|---|
| `^graphql/$` | `graphql/` | yes |
| `^api/v1/` (no `$`, used as an include prefix) | `api/v1/` | yes |
| `^download/(?P<id>[^/]+)/$` | `download/<id>/` | yes |
| `^opensearch\.xml$` | `opensearch.xml` | yes |
| `^directory/?` | `directory`, `directory/` | yes |
| `^r/(?P<id>\d+)(\.json)?/?$` | `r/<id>`, `r/<id>/`, `r/<id>.json`, `r/<id>.json/` | yes |
| `^u/(?P<a>\d+)/(?P<b>\d+)?$` | `u/<a>/`, `u/<a>/<b>` | yes |
| `^deactivate?$` | `deactivat`, `deactivate` | yes |
| `^a?/b?/c?$` (three optional pieces) | as written | no |
| `^(shelf\|books)/x/$` | as written | no |
| `^x/[a-z]+/$` (class in the text) | as written | no |
| `^s/(?P<status>(local\|federated))/$` (alternation inside a named group) | `s/<status>/` | yes |

- [ ] **Step 2: Verify they fail. Implement `paths_of`** as one left-to-right scan with a balanced-parenthesis reader; escapes `\.`, `\-`, `\/` in the text are their literal character; any other backslash in the text is "not exact". The no-`^` behaviour follows the probe.
- [ ] **Step 3: An f-string route whose pieces are constants** (`rf"^user/{USER_PATH}/?$"`, bookwyrm) is read through the value walk before `paths_of`; a piece that is not read gives `partial`. Test it.
- [ ] **Step 4: Tests pass; gate + pins green. Commit.**

### Task 7: Request reads (capability 7)

**Files:**
- Modify: `src/sextant/catalogs/django.yml` (`request_reads` via `GET`, `headers`, `COOKIES`: `.get` no requirement, subscript as the probe measured; the declaration that a handler's first non-`self` parameter is `django.http.request.HttpRequest`)
- Modify: `src/sextant/application/resolve/request_requirements.py` (general: a catalog may type a registered handler's parameter by position; an annotation the code writes wins)
- Test: `tests/application/test_django_requests.py`

**Interfaces:**
- Consumes: the `request_reads` word as `flask.yml` declares it.
- Produces: `endpoint_metadata` requirement entries on Django rows, kinds query/header/cookie.

- [ ] **Step 1: Write the failing tests**: `request.GET.get("q")` in a function view; `request.GET["q"]`; `request.headers["X-Token"]`; `request.COOKIES.get("s")`; the same in a class verb method (`self, request`); a parameter named `req`; a parameter the code annotates with another type → nothing; the same calls on a non-request receiver → nothing; a read in a helper → pin the handler-body-only boundary.
- [ ] **Step 2: Verify they fail. Implement.** Body reads (`request.POST`, `request.body`, `request.FILES`) and `request.META["HTTP_X"]` are stated boundaries: catalog comment + issue in Task 10.
- [ ] **Step 3: Tests pass; gate + pins green. Commit.**

### Task 8: Fixture surface + e2e oracle pin

**Files:**
- Modify: `fixtures/orders-django/shop/` — routes covering every Task 2–7 shape
- Create: `tests/e2e/django_oracle.py` (mirror `tests/e2e/flask_oracle.py`: subprocess under the fixture venv; walk the resolver; for each pattern report the full route and the allowed methods — for a function view from its `require_*` wrapper, for a class view from its dispatched names)
- Create: `tests/e2e/test_orders_django.py` (mirror `test_orders_flask.py`: hand-written expected rows, checked against the oracle AND against Sextant's rows; register the fixture in `tests/fixture_python.py`)

**Interfaces:**
- Produces: the pinned row list. The comparison convention (which automatic rows are excluded, how a two-path `re_path` compares with one resolver pattern) is stated in the test docstring.

- [ ] **Step 1: Write the fixture routes and the hand-written expected rows (failing e2e test).**
- [ ] **Step 2: Oracle agrees with the hand-written rows** (fix the hand-written list only where the oracle proves it wrong).
- [ ] **Step 3: Sextant rows match; gate + pins green. Commit.**

### Task 9: Corpus pins — healthchecks, weblate, bookwyrm, zulip

**Files:**
- Create: `scripts/field-expectations/py-healthchecks.json` (healthchecks @ ac59dec), `py-weblate.json` (weblate @ 255fc43), `py-bookwyrm.json` (bookwyrm @ 8e3cb8a), `py-zulip.json` (zulip @ e7f5aed, already in `examples/`); sidecar locks as `py-dispatch.uv.lock` where the upstream is not a uv project.

**Interfaces:**
- Consumes: the whole catalog; `field_check.py`'s recording flow.
- Produces: measured numbers for Task 10. Expected sizes from the design's count (a check, not a target): healthchecks ≈149 function views; weblate ≈199 + 120 class views; bookwyrm ≈116 + 173; zulip ≈210 + 21.

- [ ] **Step 1: One pin at a time, smallest first (healthchecks).** Clone, lock, record; review every expectation line; cold and warm time against the 60 s / 10 s limits. Report one line per finished pin.
- [ ] **Step 2: Per pin, attempt the oracle** (`django_oracle.py` under the corpus env with its settings module). Where the app cannot start without services, the pin's notes state the fallback: a hand-verified sample, with its size.
- [ ] **Step 3: Gaps.** A measured gap in the cell this plan ships (rows Django core serves that Sextant misses or gets wrong) is fixed in this plan as a new task with its own acceptance numbers (never-descope rule). A non-goal of the design (DRF, zulip `rest_path` verbs, registries, `i18n_patterns`, feeds) is stated in the pin's notes with its count.
- [ ] **Step 4: `field_check.py` green, all 16 pins, real exit code. Commit.**

### Task 10: Docs and close-out

**Files:**
- Modify: `docs/coverage/python.md` (Django inbound rows → built, with measured corpus numbers and the non-goals), `docs/COVERAGE.md` (REST-in Python/Django), `CHANGELOG.md`, `docs/open-issues.md` (+ id map rows)
- Plane: close OI-500; file one item per boundary with its measured count: DRF (plan 7); a registration function whose verbs come from keyword names (zulip, 149); runtime registries (netbox, 273); `i18n_patterns`; syndication feeds; `as_view(http_method_names=...)` if not modelled; body reads and `META`; a dead urls module published at `/`; `request.urlconf`. Next id: OI-501 onward.

- [ ] **Step 1: Write the docs with the measured numbers from Tasks 8–9** (never predicted ones).
- [ ] **Step 2: File/close the Plane items; add the id-map rows.**
- [ ] **Step 3: Full gate + all pins green; JVM byte-identical. Commit.**
