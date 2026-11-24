# Django core, inbound REST (Python plan 6) — design

**Status:** draft for review, 2026-11-22. Nothing is built. Ruled 2026-11-22: scope (core only), pins (§7), new catalog words only where no existing word can be reused (the plan's first task checks each one). Open: §5c.
**Parent:** `2026-11-06-python-reader-design.md` (it lists Django as "not in this design").
**Scope ruling asked:** Django core only. Django REST Framework is plan 7, on top of this.

## 1. Intent

Sextant publishes one inbound REST row for each (path, method) a Django program serves through
`urlpatterns`: the path, the method, the handler, and the request values the handler reads.
The rows are checked against Django's own resolver, as Flask's are checked against `url_map`.

Why now: Django is the third Python framework in the ruled order (2026-10-26). FastAPI and Flask
are built.

## 2. What was measured (2026-11-22)

Url registrations by shape, test code and migrations left out
(`scratchpad/django_shapes.py`, a syntax-tree count):

| Project | function view | `Class.as_view()` | `include(...)` | `re_path` share | Not core |
|---|---|---|---|---|---|
| healthchecks | 149 | 0 | 42 (34 by module name) | 0% | none; no DRF |
| weblate | 199 | 120 | 12 | 0% | 24 DRF files; 21 views wrapped by a call |
| bookwyrm | 116 | 173 | 1 | 98% | 6 feed objects |
| zulip | 210 | 21 | 16 | 2% | 149 rows through its own `rest_path()` |
| pretix | 75 | 433 | 41 | 99% | 56 DRF files; plugins; 3 root url modules chosen per request |
| netbox | 1 | 82 | 305 | 0% | 273 rows from a runtime registry (`get_model_urls`), DRF routers |
| saleor | 9 | 0 | 0 | 100% | GraphQL program; 9 rows in all |

Other counts: `@require_*` decorators — healthchecks 24, bookwyrm 95, weblate 75. Class views
that define `get/post/put/patch/delete` — bookwyrm 210 methods, pretix 281, weblate 47.

What Sextant reads today from a five-file Django program (measured, `scratchpad/djspike`):

- `path`, `re_path` and `include` calls already bind to `django.urls.conf`. The route string and
  the view argument are read. `include("shop.api_urls")` is read as a string.
- `views.Item.as_view()` does **not** bind (owner unknown). Cause: `as_view` is decorated with
  `classonlymethod`, a subclass of `classmethod`, and the scanner knows only the builtin.
- No row is published: no catalog exists.

## 3. Rules to mirror

Each rule below is Django's own. Task 1 of the plan measures every one with a probe
(`scripts/probes/django_rules.md`) before any code depends on it (DR-6).

1. **Path.** A served path is `/` + the routes from the root list down, joined with nothing
   between them. Example: `path("api/", include(x))` and `path("items/<int:id>/", v)` serve
   `/api/items/<int:id>/`. Converters stay as written, as Flask's do.
2. **Function view.** Django gives the view every method. A `require_http_methods([...])`,
   `require_GET`, `require_POST` or `require_safe` decorator narrows it; another method answers
   405 from the framework.
3. **Class view.** `View.as_view()` serves each name in `http_method_names` that the class
   defines, own or inherited. `options` (defined on `View`) and the automatic `head` are the
   framework's own answers and are not published, as Flask's automatic rows are not.
4. **`include`.** It takes a module name as a string, a module, a list, or a
   `(list, app_name)` tuple.
5. **`re_path`.** The route is a regular expression.

## 4. Approaches

**A. A catalog in the `fluent` style, with new words where Django has no receiver (picked).**
`path(...)` is a registration; `path(prefix, include(x))` is a mount. This is the same model as
Flask blueprints and Ktor nesting, so prefixes, handlers, request reads, reuse and rendering
come from code that exists. Cost: the new words of §5.

**B. A Django-only reader that walks `urlpatterns` itself.** Faster to a first row. Refused: it
puts framework knowledge in Python code (the spec's §3c forbids it), and it repeats the prefix
and handler logic.

**C. Run Django and read its resolver.** Exact, but Sextant never runs the program it reads
(spec §4). Used only as the test oracle.

## 5. Design

### 5a. Catalog `django.yml`

Roots: `path` and `re_path` on `django.urls.conf`. Captures: `url` = argument 0, `handler` =
argument 1. `path_join: concatenate` (the word exists).

### 5b. New general capabilities (each is a rule, not a Django case)

| # | Capability | Why Django needs it | Example |
|---|---|---|---|
| 1 | **A list is a router.** A registration belongs to the list value it is an element of. The value walk follows the list through names, `+`, `+=`, `append`, `extend`. | `path` has no receiver; the group is `urlpatterns` or a named list. | `api = [path("a", v)]`, `path("x/", include(api))` |
| 2 | **A mount through an inner call.** The router is an argument of a call that is itself the argument. | `path(prefix, include(x))` | catalog: `router_arg: { arg: 1, through: include }` |
| 3 | **A router named by a module name.** A string names a module; the router is that module's variable of a catalog-given name. | `include("hc.api.urls")` — 34 of 42 in healthchecks | catalog: `router_named: { variable: urlpatterns }` |
| 4 | **Any-method row, narrowed by a decorator.** | rule 2 | `@require_POST` gives one POST row; no decorator gives one row with no method (spring-webflux-router publishes a null method for a route that names none) |
| 5 | **Verbs from the methods a class defines.** One row per defined name; the handler is that method. The servlet catalog does this for `doGet`. | rule 3 | `class Item(View): def get...; def delete...` gives GET and DELETE rows |
| 6 | **A decorator class that extends `classmethod` or `staticmethod` is that decorator.** | `as_view` does not bind today | `classonlymethod` |
| 7 | **The framework types a handler's parameter.** Parameter 0 of a registered handler is `django.http.request.HttpRequest`. | `def view(request)` is never annotated, so no request read can bind | `request.GET["q"]` gives a required query row |

Request reads (`request.GET`, `request.headers`, `request.COOKIES`) then use the existing
`request_reads` word. Body reads (`request.POST`, `request.body`) are a stated boundary, as in
Flask.

### 5c. `re_path` (proposal, measured 2026-11-22; awaits ruling)

851 `re_path` routes were classified (bookwyrm 288, pretix 548, saleor 9, zulip 6;
`scratchpad/regex_shapes.py`):

| What the expression has | Routes | Share |
|---|---|---|
| Literal text, `^`, `$`, named groups only (a missing `$` included: Django matches a prefix) | 558 | 66% |
| The above, plus a trailing `/?` | 249 | 29% |
| Another optional piece: `(\.json)?`, `(?P<id>\d+)?`, `deactivate?` | about 35 | 4% |
| A list of literals in an unnamed group: `(shelf\|books)` | about 6 | 1% |

Three structural reads, not a regex parser (ruling 2026-10-21):

1. **Named groups.** `^` and `$` are dropped; each `(?P<name>...)` becomes `<name>`. `resolved`.
2. **An optional piece gives two rows.** `X?`, where `X` is one literal character or one group,
   is a closed set of two paths (ruling "enumerable is exact"). `^inbox/?$` gives `/inbox` and
   `/inbox/`, both `resolved`. More than two optional pieces in one route: `partial`, as written.
3. **Everything else** (an unnamed group that is not optional, `|`, a class or a quantifier in
   the text) publishes the expression as written at `partial`.

Reads 1 and 2 together give exact rows for about 99% of the measured routes. The cost of read 2:
bookwyrm publishes two rows for most routes.

### 5d. Roots and existence (my call)

A list that no `include` names is served at `/`. `ROOT_URLCONF` is not required to find it:
pretix has three root modules, chosen per request. A `urlpatterns += [...]` under
`if settings.DEBUG:` is "not evaluated" with the repository value as evidence (ruling
2026-10-23).

Known wrong case, logged and not designed for: a dead urls module that nothing includes and no
setting names publishes rows that are not served.

## 6. Goals, non-goals, anti-goals

**Goals.** Rows for function views and class views behind `path`, `re_path` and every `include`
form of rule 4. Request reads. An `orders-django` fixture checked three ways against Django's
resolver. Field pins.

**Non-goals (each gets an issue with its measured count).**
- Django REST Framework: routers, viewsets, `@api_view` (plan 7).
- A project's own registration function whose verbs come from keyword names (zulip `rest_path`,
  149 rows). The path is read by following the code; the verbs are not.
- A runtime registry (netbox `get_model_urls`, 273 rows).
- `i18n_patterns`, syndication feed objects, Django Channels, the admin site's own urls.

**Anti-goals.** A `resolved` row Django does not serve. A row for a method Django answers 405.
Framework knowledge in Python code.

## 7. Pins (my proposal)

| Pin | Why | Stated gap |
|---|---|---|
| healthchecks | Plain Django: 149 function views, includes by module name, no DRF, no `re_path` | none expected |
| weblate | `path` with function and class views together | DRF rows absent until plan 7 |
| bookwyrm | `re_path` and class-view verbs | rows at `partial` where the expression has `/?` |
| zulip (kept from the spec) | 210 function views | `rest_path` rows have no verb |

netbox and saleor leave the Django core pins: 71% of netbox's rows come from a registry, and
saleor has 9 rows. netbox returns for plan 7.

## 8. Performance

No new pass. Capability 1 is a value-walk question per registration, the same count Flask asks.
Capability 3 is one lookup per `include`. Target: each pin inside the existing 60 s cold / 10 s
warm limits; the plan measures cold and warm on every pin.

## 9. Done when

- The fixture's rows equal Django's resolver output, row for row.
- The four pins are recorded and green; all 12 existing pins are unchanged.
- COVERAGE: Python / Django REST-in moves from "not yet" to built, with the non-goals listed.

## 10. Left to the plan

The probe list; the exact catalog spellings of capabilities 2, 3 and 5; the fact-schema version
bump; the order of tasks.

## 11. Questions for you

1. **Scope:** is Django core without DRF the correct plan 6?
2. **New words:** do you approve the three catalog words (capabilities 2, 3, 5)? The other four
   capabilities add no word.
3. **`re_path`:** is `partial` correct for an expression the one rule cannot read, or do you
   want the trailing `/?` rule in plan 6?
4. **Pins:** do you accept the four pins and the removal of netbox and saleor from Django core?
