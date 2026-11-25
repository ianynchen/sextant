# Django inbound REST, redesign (plan 6, second design)

**Status:** BUILT on the branch `cov/python-django` (plan tasks 0–10, 2026-11-23 to
2026-11-24); not pushed, no pull request yet. First proved on a throwaway copy
(`tmp/django-on-main`, never merged; the change is kept as
`.worktrees/django-task1-proper.patch`). The product branch is measured in §9 (Task 10,
2026-11-24). The rulings of §2 items 12–14 came from the proof; items 9 and 11 and §4c M6 and
M7 were corrected by rulings made during the tasks (marked "ruled during the build").
**Replaces:** how route lists, mounts, roots, class views and method decorators are read in
`2026-11-22-python-django-core-design.md`. The probe's 70 measured rules
(`scripts/probes/django_rules.md`) and the approved `re_path` reads stay.
**Branch:** `cov/python-django` (not pushed), behind `main` by PR #110; a test merge was clean.

## 1. Why a second design

The first build gave 91 correct rows of 3,112 on the real trees. Two causes:

1. **Mechanisms built a second time.** The branch walks route lists with its own code (the
   branch's `shapes/mounts.py` is 440 lines longer than main's), reads `include` and `as_view` with a new key, reads a
   library `dispatch` with a new scan fact, and states method decorators with a new key. In
   each case an existing mechanism already has that role (§4).
2. **Concepts added without the user**: five catalog keys, one catalog value, one question
   kind, one scan fact, found by the vocabulary test of PR #111 (§5).

## 2. Rulings that bind this design (user, 2026-11-23)

1. Read the shapes the framework's documentation teaches; one honest answer for the rest.
   Sextant parses code; it is not a compiler or a run-time.
2. Before any new word, fact or rule: name the Java construct with the same role and reuse
   its mechanism. A different encoding is not a different concept.
3. A library a project uses is code we have. Unknown is only for code that is absent.
4. A list held in a name is read when its exact values are known; an alteration we can see
   (`+=`, `a + b`, `append`, `extend`) does not make it unknown.
5. The members of one written list do not count against the path limit (`PATH_CAP`).
6. `"...{}".format(x)` is a template. `list(x)` is a copy.
7. A mount of a router the module does not build adds nothing (the existing Vert.x and
   FastAPI rule). No question kind for it.
8. `@require_POST` and its three siblings are stated with the Spring words
   `annotations: [{fqn, method}]`.
9. A library class's `dispatch` is read with the existing servlet rule. **Ruled during the
   build (user, 2026-11-23, option B):** the scanner reads the method bodies of each library
   class a module class extends (the library classes in a module class's lookup order) and
   writes the existing method and call facts for them. The scanner knows no catalog word: it
   does not pick methods by a catalog. Rows that come from those bodies are not the module's
   rows; the existing borrowed-rows rule drops them (keyed by the caller, then the handler).
   No new fact. Fact schema 22.
10. `url_is: expression` is approved for `re_path`.
11. Not supported: a registration in a loop or comprehension; the keywords of a `**kwargs`
    parameter; a lookup by key in a dict. The row keeps its reason and a question names the
    line.
12. **The root has a catalog word** (approved 2026-11-23): `root_setting: ROOT_URLCONF`, beside
    `router_named`, which gives the variable.
13. **A read of the method has a catalog word and a fact** (approved 2026-11-23): a
    `request_reads` entry with the new kind `method`
    (`{ owner: django.http.request.HttpRequest, method: method, arity: 0, kind: method }`);
    and the scanner writes an attribute read on a parameter whose class is not known as the
    call fact it already writes for a known class, with no owner.
14. **Captured values sit after the written parameters in a Python body** (approved
    2026-11-23). D00's `captures` says "leading" for the JVM; a Python function is called by
    its written signature, so those positions stay.

## 3. What was measured

Real engine plus the throwaway changes of §4, real trees, no workarounds, compared with
Django's resolver (route paths):

| Project | Django serves | Read and correct | Wrong |
|---|---|---|---|
| zulip | 815 | 432 | 0 |
| bookwyrm | 405 | 288 | 0 |
| weblate | 827 | 278 | 0 |
| healthchecks | 254 | 179 | 0 |
| **Total** | **2,301** | **1,177** | **0** |

Routes read that Django's answer lacks are under a deployment setting (healthchecks
`path(f"{prefix}admin/", ...)` with `prefix` from `settings.SITE_ROOT`) or have a hole in
the path. The existing rules publish those with a condition or at `partial`, never
`resolved`.

Still missed, by cause: Django admin about 330 (not built in this plan); DRF 254 (plan 7); zulip loops and
comprehensions about 280 (ruling 11); library URL modules about 40 (ruling 7); regex routes
the test script compared as text and small unopened groups about 220.

Not measured yet: methods and handlers on the four projects (this run compared paths);
`append` / `extend`; the library `dispatch` read on netbox's 43 classes.

## 4. Design: each need, the existing mechanism, the change

| # | Need | Java / existing construct with the same role | Existing mechanism | Change | Verified |
|---|---|---|---|---|---|
| 1 | A route list held in a name | a field holding an array | array rule of the value walk (`_elements`) | `values.py` `_binding_writes`: a list written to a name answers with its members; `*x` of itself is the other writes | zulip: 295 routes behind 13 mounts, each with its caller's path |
| 2 | A name for another list (`urlpatterns = real_patterns`) | field read | `_entry` field arm | the same place follows a written name | weblate root read |
| 3 | More than 256 routes in one list | — | `PATH_CAP` | members of one written list are not counted | bookwyrm 296, weblate 261 members; 0.7 s |
| 4 | `list(x)` | `[*x]` | scanner array with an unpacked member | `calls.py`: a copy is recorded as `[*x]` | zulip plain copies read |
| 5 | `x += module.attr`, `a + b` where the scanner cannot type an operand | list sum | scanner `_sum`, `_augmented` | a sum onto a name written as a list is a list | zulip `urls`, `i18n_urls` |
| 6 | `x.append(v)`, `x.extend(vs)` | same as 5 | same members | read as `+=` is (how: the plan, with the existing mechanism it names) | not yet |
| 7 | `path(p, include(x))` | Vert.x `mountSubRouter(p, router)` | `mount` with `router_arg`, `prefix_arg`; value-model `returns: arg0` | one value-model entry for `include`; the branch's key `through` is removed | zulip `api/v1/`, `json/`: 125 routes each |
| 8 | `include("app.urls")`, `ROOT_URLCONF` | none in any language (survey E) | — | `router_named: { variable: urlpatterns }`, approved 2026-11-22, stays | module name arrives as a value |
| 9 | `X.as_view()` | a call that returns its receiver | value-model `returns_receiver: true` | one entry; a stated call is matched on the owner the engine already binds, and its ancestors | bookwyrm 173 of 173 name their class |
| 10 | Class view methods | servlet `doGet` | `dispatch`, `bypassed_by` (`jakarta-servlet.yml`) | as on the branch | fixture |
| 11 | A library `dispatch` override | servlet base class calling `super.service` | the same rule, read from a `special` call fact | scanner writes the existing method and call facts for every method body of each library class a project class extends (ruled during the build, option B: no catalog word in the scanner); rows from those bodies are dropped by the borrowed-rows rule; `calls_super` removed | fixture: correct with bodies read, wrong `resolved` row without. Cost measured in Task 8: whole run +12% on bookwyrm, +5% on weblate (resolve +23%, +13%) |
| 12 | `@require_POST` | `@PostMapping`, `@RequestMapping(method=…)` | `annotations: [{fqn, method}]`, `method_from`; the engine's `decorators_passed` (click) | the words in `django.yml`; the fluent engine applies them to the decorators between a registration and its function; `narrowed_by` removed | mechanism on the fixture; 199 views to measure |
| 13 | A view with no method stated | Vert.x route with no method | `verbless_serves: any` | as on the branch | fixture |
| 14 | Library and project decorators on a view | — | `result_calls` / `result_returns`; walk into module decorators; `handler_pass_through` | as on the branch (22 entries, each citing the probe) | zulip: 290 questions on its own decorators, cause not known (§6) |
| 15 | A mount of a library's router | Vert.x `subRouter(Bridge.router())` | adds nothing | `mounted_router` and its gate removed | — |
| 16 | A route under a setting | conditional registration | "not evaluated" | also read from the guard of a list write (§4c M5) | healthchecks, zulip, weblate |
| 17 | `re_path` | Vert.x regex route | `url_is` | value `expression` + the three approved reads | first design |
| 18 | `"...{}".format(x)` | f-string | concat rule | scanner `_concat` | redash 57 rows wait on it |

Deleted from the branch: `_held_by`, `_reach`, `_lists`, `_reached_at`, `_handed_lists`,
`unread_routers` and their callers; the keys `through`, `read`, `narrowed_by`; the question
kind `mounted_router`; the fact `calls_super`.

## 4a. How a route finds its mount and its root (review C1, ruled 2026-11-23)

A Django route has no receiver, so the existing join (the route's receiver and the mount's
router argument meet at one router object) cannot place it. No Java construct has this role:
in Java a route always has a receiver. The join for a registration made on nothing is the
approved capability 1 of the first design, "a list is a router":

1. The engine starts at each mount (`path(p, include(x))`, `i18n_patterns(...)`) and at each
   root. A root is the `urlpatterns` of a module that a written `ROOT_URLCONF` names; two
   writes, or two Django projects in one repository, are two roots.
2. It asks the value walk for the members of that list (rows 1–6). A helper is followed, and
   each caller keeps its own prefix.
3. Each route reached is served under that mount's prefix, joined outermost first; a route
   reached from a root is served from the empty prefix.

**A list that no readable mount and no root reaches has no `resolved` row.** Its routes are
published with the existing hole, `<prefix>/x`, at `partial`, with the existing
`mount_prefix` question. Django serves only what the root reaches, so a list we cannot
connect can be under a prefix we did not read; the existing rule for other frameworks ("a
router never mounted is served at its own prefix, `resolved`") would be a wrong `resolved`
row here. A repository with no `ROOT_URLCONF` (a reusable app) therefore has every row at
`partial` with the hole.

The user's condition on this ruling: it must not deviate from the truth. The plan measures
it in the ENGINE on the four real trees against Django's resolver; a `resolved` row Django
does not serve fails the task.

## 4b. Method decorators (review C2, ruled 2026-11-23: option 1)

Row 12 named the wrong function: `decorators_passed` looks only in the method that holds the
registration. In Django the registration is in `urls.py` and the decorators are on the `def`
in `views.py`. The mechanism is the BRANCH's walk from the registration's handler argument to
the function and the decorators on it (Task 4 of the first plan). It is kept. Measured on the
real healthchecks tree with the branch's engine: `notification_status` (`@csrf_exempt`,
`@require_POST`) has `POST` rows; 52 rows have their method from a decorator.

The catalog states the four decorators with the Spring words, with one extension:

```yaml
annotations:
  - { fqn: django.views.decorators.http.require_GET,  method: [GET] }
  - { fqn: django.views.decorators.http.require_POST, method: [POST] }
  - { fqn: django.views.decorators.http.require_safe, method: [GET, HEAD] }
  - { fqn: django.views.decorators.http.require_http_methods,
      method_from: { arg: 0, keyword: request_method_list } }
```

- **The extension (approved):** `method_from` may take the argument form the fluent catalogs
  already use, `{ arg, keyword }`; in `spring-mvc.yml` it is an attribute name. The values
  are the strings written, compared as Django compares them (probe).
- **Two decorators on one view:** the row has the intersection of their methods, as Django
  does (probe). An empty intersection is no method.
- **No decorator:** one row serving any method (`verbless_serves: any`, row 13).
- The fluent engine reads this block; today only the annotation engine reads the words. That
  is engine work, not a new word.
- Not verified yet: an unknown decorator above `@require_POST`; every one of the 52 rows
  against Django. Both are in the plan's first task.

## 4c. The other review findings, each settled by a standing principle (2026-11-23)

| Finding | Principle that decides it | Resolution |
|---|---|---|
| M1 `i18n_patterns(*x)` had no row | §4a | A library call that takes the list is no readable mount: the routes get the hole `<prefix>/x` at `partial` with `mount_prefix`. The language prefix comes from a setting and the request, so the hole is exact. |
| M2 `include((patterns, app_name))` | read the documented shape (ruling 1) | **Approved new part `element` of the argument reference:** `returns: { arg: 0, element: 0 }`; where the argument is a written tuple the value is its first element, else the argument. Django's `include` decides by `isinstance`, which is not followed because Sextant does not run code. Counted: 9 of 374 calls. |
| M3 a stated call matched on ancestors | the language's own lookup is the truth | A value-model entry on a class applies to a call on a subclass, by the lookup order the engine's dispatch already has; a definition of that method in code we have, nearer in the order, wins over the entry. General for every value model; the pins and one test per changed match guard it. The spike's "any call named `as_view`" is not the rule. |
| M4 a DRF `APIView` under `path()` | a wrong `resolved` is a lie; do not hide a route | `APIView.dispatch` does not call its parent and picks the method with `getattr`, which is not read. The row is published with its path, method not read, at `partial`, with a question. Never one `resolved` any-method row naming the library method. Plan 7 makes it exact. |
| M5 a condition on the hand-over of a list | deployment decides (2026-10-23) | A member reached through a write under a test carries that test as its existence condition, "not evaluated": `if settings.DEVELOPMENT: urls += dev_urls.urls`. Row 16 is changed: this is work, read from the guard of the write. |
| M6 a copy taken part-way is over-read | truth | A read of a held list inside the body that writes it sees only the writes before it, by the order of the body. A read from another body sees every write. Zulip: `urls = list(i18n_urls)` at line 776, more added at 908 and 1022. **Ruled during the build (Task 3):** the order is the SCANNER's (`BodyReader._in_order`): a module-level list is written with the elements it holds at that line, so a copy holds only the earlier members. A name written under a test or in a loop has no one value from there on: a later `*name` stays a read of the name, which the walk answers with every write of it. Test: `tests/ingress/extract/python/test_calls.py::test_a_copy_of_a_module_list_holds_the_elements_at_its_line`. |
| M7 when a held list is NOT exactly known | ruling 4, and the existing reasons | Known: the written members, `+`, `+=`, `append`, `extend`, a copy. Not known, and answered `escapes`, never `resolved`: any other call ON the list (`remove`, `pop`, `clear`, `insert`, `sort`, `reverse`). **Ruled during the build (Task 3):** (1) a list passed as an argument stays read: the reading call is itself such a hand-over, and the walk tracks no hand-over of a field, as in Java (`tests/application/test_values.py::test_a_held_list_handed_to_a_call_is_still_read`; a list handed to module code that changes it is a logged limit); (2) an element store or delete is the call the language makes, `x[i] = v` is `__setitem__`, `del x[i]` is `__delitem__`, so it is a call on the list (`tests/ingress/extract/python/test_calls.py::test_an_element_store_and_delete_are_the_calls_the_language_makes`); (3) a call on the list through a second name (`VERBS = BASE; VERBS.remove(v)`) makes the list not known by that name; by the first name it is a logged limit (`test_values.py::test_a_list_changed_through_a_second_name_is_not_known_by_that_name`). The Java half (an element store on a static array) is not built: a logged limit. |
| M8 §3 does not measure §4 | measure before design; say what was not verified | Stated in the status line. The plan's first task builds §4 in the engine and repeats the measurement there. The oracle has the allowed methods of each route (it calls each view), so methods are compared too. |
| M9 `append` / `extend` had no mechanism | ruling 4 | The scanner records `x.append(v)` on a name as the write `[*x, v]` and `x.extend(vs)` as `[*x, *vs]`, as it records `x += [...]` today. |
| M10 22 named library decorators | a library is code we have; one structural rule | The common decorator returns an inner function that calls the wrapped one (`@wraps(f) def inner(...): ... f(...)`). Today the walk reads only a decorator that returns its function, which is why it stops on zulip's own decorators 290 times. The rule: a returned function that calls the decorator's parameter stands for that parameter — the meaning of the existing `result_calls`, read from the code. It applies to project decorators and, through the targeted read of row 11, to library decorators. A value-model entry stays only where the body cannot be read. Earlier measurement: handlers readable 747 → 1,937; 1,212 of 1,222 agree with Django. |
| M11 the `PATH_CAP` exemption was undefined | ruling 5 | The reader resolves each member of a list as its own read, with its own limit. Nothing inside the limit changes; alternatives (branches, callers, several writes of one value) are counted as before. |

## 4d. What "any method" means (ruled 2026-11-23: option B, then option 2)

An "any method" row means **the endpoint answers every method**, not "the router sends every
method to the handler". A function view's any-method row is `resolved` only when its body
gives no reason to doubt it.

**What is a reason to doubt** (ruled, option 2):

- the view reads `request.method`, in its own body or in **project code that it gives the
  request to**, followed as far as the project's code goes. Zulip's `rest_dispatch` gives the
  request to `get_target_view_function_or_response`, which selects by `request.method`;
- the view gives its request to another view (`EmbedList.as_view()(request, ...)`).

Such a row is `partial`, method not read. This plan does not read HOW the body limits the
methods; that is the next design.

**What is not a reason to doubt:** the request given to a library function
(`render(request, "x.html")`, `messages.success(request, ...)`). A library function that
answers 405 for some methods when a function view calls it is possible and improbable;
libraries limit methods with decorators and class views, which are read. Recorded as an
issue with the count, not designed for.

**Correction.** An earlier version of this section said the Vert.x pass-through rule gives a
delegating view the rows of the view it calls. That was a misreading: in Vert.x a handler
passes on by calling `next()`, and a handler that calls a helper with the request still
answers (`test_a_handler_that_replies_through_a_module_helper_answers`). The handler of a
delegating view stays that view.

- **A view object** (`path("rss", RssFeed())`): calling an object runs its class's
  `__call__`; that method is the handler, found by the class lookup.

Counted in the four projects (1,285 function views): 124 read `request.method` in their own
body; 957 give the request to project code; more than 300 give it to a library function; 264
give it to no other code and read no method; 7 give it to another view.

## 4e. A wrapper that calls what it wraps (Task 1 finding, 2026-11-23)

The common Python decorator returns an inner function that calls the wrapped one:

```python
def add_google_analytics(view_func):
    @wraps(view_func)
    def _wrapped_view_func(request, /, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        ...
    return _wrapped_view_func
```

**The Java construct with the same role is a lambda that captured a value** ("Lambda body
reads a captured value → the captured value", `values.py` "the seventh edge",
`tests/application/test_values.py:2247`). The inner function reads `view_func`, a value of
the outer function.

**The gap is in the Python scanner: it records no capture.** A nested function is written
with `captures=0` (`ingress/extract/python/calls.py:2157`, `structure.py:524`), and a name of
the enclosing function read inside it is `unresolved` (`calls.py:2298`). On the JVM the facts
carry the capture (D00 `captures`: the capture site's last N arguments bind the body's N
leading parameters).

**The handler is the wrapped function**, as it is for a library wrapper a value model states
with `result_calls` ("calling the result runs the argument"): for a project wrapper the same
meaning is read from the code, once the capture is in the facts — the inner function calls a
captured function with the request it received. Django's own answer names the wrapped
function too.

Measured with a throwaway version on zulip: the `handler_pass_through` questions fall from
437 to 5.

A second defect found on the way: `functools.wraps(f)(inner)` is stated `result_returns:
arg0`, but `_stated_value` applies that form only where the applying `__call__` has no owner;
here the scanner types it `functools/_Wrapper#`, so the statement never fires.

**Decided (2026-11-23, §2 item 14, built in §9a):** the captured values are the body's
parameters after its written ones.

## 5. Every concept the branch added, and its state

| Concept | State |
|---|---|
| key `router_named` (+ `variable`) | stays; approved 2026-11-22; no existing word has the role |
| value `url_is: expression` | stays; approved 2026-11-23 |
| key `through` (+ `read`) | removed; existing value-model forms (rows 7, 9) |
| key `narrowed_by` | removed; Spring words (row 12) |
| question kind `mounted_router` | removed; existing rule (row 15) |
| scan fact `calls_super` | removed; existing call facts (row 11) |
| Task 7 (request reads) removed without approval | not in this design; its own design next |
| key `root_setting` | new; approved 2026-11-23 (§2 item 12) |
| `request_reads` kind `method` | new value; approved 2026-11-23 (§2 item 13) |
| part `element` of `returns` | new; approved 2026-11-23 (§4c M2) |
| key `supertype` in a `fluent` catalog | existing word of `jakarta-servlet.yml`, read by the fluent engine too: the class whose subclasses answer by `dispatch` |
| key `annotations` in a `fluent` catalog | existing words of `spring-mvc.yml` (§4b) |
| fact: an `array` entry carries `symbol` (`builtins/tuple#`, `builtins/list#`) | existing field, filled for a written collection; `element` needs it |
| fact: a capture site `types/FunctionType#<init>` (`dynamic`) and `captures: N` | existing D00 words, written by the Python scanner for the first time |
| fact: an attribute read on a parameter of unknown class, as an ownerless call | approved 2026-11-23 (§2 item 13) |

## 6. Open, to investigate in the plan's first task (no design yet)

- Zulip's 290 `handler_pass_through` questions on its own decorators
  (`add_google_analytics` 50, `typed_endpoint` 35, `require_post` 11, five more): why the
  existing walk into a project decorator stops. Either a defect or a shape for the scenario
  list; it comes to the user with the cause and a count.
- The about 220 routes of §3's last group.

## 6a. Minor points, settled (review of 2026-11-23)

- Two routes with one path both publish, as in every other framework; Django's first-match
  order is not modelled.
- `static(...)` and `staticfiles_urlpatterns()` as members of a list are one trailing unread
  member (the array rule); the plan checks this in the engine.
- A library's URL module adds nothing (ruling 7) while a library `dispatch` body is read
  (ruling 9). The difference: the routes of a library module are the library's own endpoints,
  not routes this program wrote; the `dispatch` body decides the rows of a class this program
  wrote.
- `as_view(http_method_names=...)` and an overridden `as_view`: none in the six projects;
  recorded as an issue, not designed for.
- `@method_decorator(X, name="dispatch")` on a class writes no `def dispatch`, so it is no
  bypass; one fixture case pins this.

## 7. Goals, non-goals

- Goal: zero wrong `resolved` rows against Django's resolver on the four projects, for paths,
  methods and handlers.
- Goal: no second mechanism (§4 column 4 is the whole list).
- Not in this plan, each still a goal of Django REST inbound: DRF (plan 7), admin routes
  (ruled 2026-11-24, below), method tests in a view body (next design), request reads
  (the design after).

**Admin routes are routes (user, 2026-11-24).** "Admin" is not a kind of endpoint: a route
the service answers is a route, written by the project or built by a library. Earlier text
called admin a non-goal; that was a build order, never a decision of the user. The routes
come from a registration in the code (`admin.site.register(Order)`), and the Java construct
with the same role is built: `spring-data-rest.yml`, style `derived_resource`, routes a
framework rule derives from a declaration, each rule measured on a live application. Size:
420 served admin patterns with no row (healthchecks 75, bookwyrm 93, weblate 252), from 46
registration lines in the four projects.

## 8. Done when

- The four real trees: zero wrong `resolved` rows; the yield per project with every
  not-read group named and counted.
- The 12 pins lose no row from rows 1–5 (they change the value walk and the scanner for all
  Python readers); the two FastAPI tests of the old held-list rule are changed to ruling 4.
- `scripts/check.sh` green; the vocabulary test passes with approval entries for
  `router_named`, `variable` and `url_is: expression`, and no other new word.

## Principles check

Reference: `docs/value-reading-scenarios.md` (PR #111), and the catalog-level survey of
2026-11-23 (to be merged into that reference).

| Shape | Row of the reference | Mechanism |
|---|---|---|
| A list written in place | "Every element a written constant" | as is |
| A list held in a name | "A list held in a module name" (ruled) | rows 1–3 |
| A helper returning a route or a list | "Helper returns the value"; "a helper builds, mounts and returns a router" | as is (zulip `rest_path`) |
| A mount, nested mounts, a mount in a helper | "Mounts and prefixes" | as is |
| A mount of a library's router | "A mount of a router the module does not build" | adds nothing |
| A setting a deployment decides | "A registration under a test a deployment decides" | as is |
| A decorator (library, project, unknown) | the three decorator rows | as is |
| A call that returns its argument / its receiver | value-model forms | rows 7, 9 |
| Method from a marker on the handler | catalog survey A(i): `annotations[].method` | row 12 |
| Class dispatch, override that calls the parent | catalog survey F: `dispatch`, `bypassed_by` | rows 10, 11 |
| A loop, `**kwargs`, a lookup by key | "Cases with no rule" (ruled: not supported) | reason + question |

| Rule | How the design follows it |
|---|---|
| §8.8-1 follow the value through code we have | lists, mounts, `include`, `as_view` and the library `dispatch` are read by the value walk and the existing rules; a library is code we have |
| §8.8-2 one structural rule | no model of a list method beyond "adds its argument"; no loop evaluation |
| §8.8-3 name the general concept | §4 column 2 names the Java construct for every row |
| §8.8-4 a closed set is exact | one row per member of a known list |
| §8.9 a new concept is the user's decision | §5: two words stay, both approved; four concepts removed |
| §8.1 measured first | §3 |
| Tell the truth | §7 goal 1; row 11 shows the wrong row that reading the body removes |

New concepts proposed by this design: none.

## 9. Task 1 result: the design in the engine, with the real mechanisms (2026-11-23)

Real engine, real trees, no step after the engine. Compared with Django's resolver: method,
path and handler.

The table above is the throwaway copy's (Task 1). **The product branch, measured in Task 10
(2026-11-24, HEAD 18c58a47)**, with the same compare (method, path and handler against
Django's resolver):

| Project | Inbound rows | `resolved` and equal to Django | `resolved` and wrong | Cold run (median of 3: scan / resolve / whole) |
|---|---|---|---|---|
| healthchecks | 356 | 82 | 0 | 3.1 / 2.2 / 6.3 s |
| bookwyrm | 827 | 791 | 0 | 4.5 / 3.8 / 9.5 s |
| weblate | 493 | 236 | 2 (true, see below) | 19.2 / 19.9 / 40.1 s |
| zulip | 581 | 38 | 0 | 16.7 / 19.9 / 38.3 s |

The two weblate rows the compare calls wrong are `POST` of the webauthn registration views
(`weblate/accounts/urls.py:45-54`). The library `BaseWebAuthnView.dispatch`
(`django_otp_webauthn/views.py:72`) calls `initial` and then `super().dispatch`, which gives
the method table: `POST` only. Where `initial` raises an `OTPWebAuthnApiError` (no login), it
answers every method with a JSON error. The oracle's request has no login, so it saw that
error for every method. The rows are the endpoint's methods; the error depends on the user,
which is a run-time fact. Checked against the library source on 2026-11-24.

The first build gave 91 correct rows. A first spike with shortcuts gave 1,175 correct and 4
wrong; the user rejected it ("spike for proper solution, not shortcuts").

### 9a. How each part is built

- **Captures (§4e).** The scanner records the names of enclosing functions a nested function
  or a `lambda` reads: a `dynamic` site `types/FunctionType#<init>` takes their values where
  the function is made, the `lambda` entry carries `captures: N` and `source`, and the body
  holds them as parameters after its written ones. A name written again after the `def` is
  `unresolved`. The existing fold ("the seventh edge") binds them; for a body called by its
  written signature the captured positions start after the declared parameters.
- **A wrapper stands for what it wraps.** `ValueIndex.hands_on`, from call facts: the body
  calls a captured parameter, the first argument is the first parameter the body is GIVEN
  (written or unpacked, `f(request, *a)`, `f(*args)`), and the call's result goes into a
  value the body returns: as it is (`return f(request)`) or inside what it returns
  (`return JsonResponse(f(request))`). A call whose result is only tested
  (`if test_func(request):`) or not used (`logger(request)`) is no hand-over; a body with
  no hand-over is itself what runs. The walk then reads the captured value on the same path
  (`_Walk._runs_captured`) and notes the body it ran through. Where the body hands on and
  no function is read there, the answer is `not_readable`, never the wrapper. (Whole-branch
  review, 2026-11-24: the first form asked for the result returned as it is, and named a
  JSON wrapper as the handler of every view below it.)
- **The methods a decorator states are read on the handler's own path** (whole-branch
  review, 2026-11-24). The walk notes each stated library call it passes on the way to the
  handler (`Path`'s passed calls), and the `annotations` entries among them give the
  methods. So `def api_post(f): return csrf_exempt(require_POST(f))` and
  `get_or_post = require_http_methods([...])` used as a decorator narrow the row, as a
  decorator written on the `def` does. One reader serves the handler and its methods.
  Where the paths of one handler value give different method sets, every row is `partial`.
- **A handler read on one path and not on another names no function** (`_walked_handler`):
  the row is `partial` with the `handler_pass_through` question. `result_calls` keeps an
  unread path beside the functions it reads.
- **A decorator made in one method and applied in another** (`d = user_passes_test(t)` in a
  helper, `d(view)` in its caller): the receiver's `made_by` call is looked up in the value
  models (`_applied_elsewhere`). Zulip: 39 handler questions fall to 5.
- **A library class's bodies (§2 item 9, option B).** The scanner reads every method body of
  each library class in a module class's lookup order (`libraries._class_bodies`), as module
  methods (fact schema 22). The servlet rule then reads `super().dispatch(...)` in a library
  `dispatch` as the `special` call it is. Rows from those bodies are dropped by the
  borrowed-rows rule. `calls_super` is gone.
- **`include`, `as_view`.** `returns: { arg: 0, element: 0 }` and `returns_receiver: true`. A
  stated call is matched on the receiver's class and its ancestors by `Dispatch`'s order; a
  nearer body in read code wins (`_stated_on_ancestor`, Python modules only for now).
- **The join (§4a).** `MountReader._list_tree`: from each written `root_setting` value and
  through each mount, the members are asked of the value walk (`producer_paths`, the
  registration calls its stops); prefixes are read and joined by the existing `_prefixes` and
  `_behind`. A call that is both a route root and a mount is a mount where its router argument
  reads as a router: it reaches a registration, or a string that names a module
  (`mounts_a_router`). The branch's key `through` and the question `mounted_router` are gone.
- **Held lists (rows 1–6, M6, M7, M11).** The value walk reads the members of each list
  write; members do not count against `PATH_CAP` (256). The scanner writes a module-level
  list with the elements it holds at that line (`_in_order`), so a copy does not see later
  additions; `append` and `extend` are the writes `[*x, v]`, `[*x, *vs]`. Not exactly known,
  answered `escapes`: a call ON the list that is not such a write (`x.remove(v)`; `x[0] = v`
  and `del x[0]`, which the scanner writes as the calls `__setitem__` and `__delitem__`).
  Ruled during the build (Task 3): a list handed whole to a call stays read (the reading
  call is such a hand-over; Java tracks no hand-over of a field either), and a call on the
  list through a second name makes it not known by that name only (§4c M7).
- **Any method (§4d).** `fluent._any_method_doubted`: the handler and each wrapper the path
  ran through; a `kind: method` read on the request, in the body or in module code the
  request is handed to; the request handed to a value that is called; a handler whose body
  was not read (a library's).
- **Method decorators, class views.** `annotations` (§4b) and `supertype` in `django.yml`;
  the handler value is read by the value walk, and a class below `supertype` answers by
  `dispatch`.

### 9b. Known limits, each with its count

Counted on the product branch on 2026-11-24 (Task 10), from the compare and from each
workspace's `open_questions`. Each limit is an open issue (`docs/open-issues.md`).

- **What is not read, by cause, per project** (Django (method, route) pairs: healthchecks 304,
  bookwyrm 536, weblate 913, zulip 1,366):
  - **Django admin** (not built yet): Django patterns with no row: healthchecks 75, bookwyrm 93,
    weblate 252, zulip 0 (OI-507).
  - **DRF** (plan 7): weblate 253 router patterns with no row; 10 `APIView` routes under
    `path()` are rows naming no handler, `partial` (OI-544).
  - **A library's URL module adds nothing** (ruling 7): bookwyrm 19 (`oauth2_provider.urls`),
    zulip 10 (`django_scim.urls` 6, `social_django.urls` 4).
  - **A registration in a loop or a comprehension** (ruling 11): zulip 22 rows with no path
    (3 `RedirectView` loops, 7 methods each; 1 webhook comprehension) stand for 149 Django
    patterns (96 webhooks at `zproject/urls.py:865`, 53 redirects). No question names the
    line, which ruling 11 asks for (OI-502).
  - **`**kwargs` keywords and a lookup by key** (ruling 11): zulip `rest_path`, 295 routes and
    829 Django pairs; Sextant publishes one any-method row per route, `partial` (259 rows
    compared, 717 pairs covered by them) (OI-503, OI-504).
  - **Any method doubted** (§4d): rows `partial` because the view or a wrapper reads
    `request.method` or hands the request on: healthchecks 91 (36 behind `cors(...)`),
    bookwyrm 2, weblate 52, zulip 287 (259 of them `rest_dispatch`). No question is filed
    for them (OI-540).
  - **Behind the `<prefix>` hole**: healthchecks 177 (every route a second time: the prefix
    comes from `settings.SITE_ROOT`), weblate 4 (`weblate/addons/api.py`, a list no root
    reaches), zulip 182 (`i18n_patterns(*x)`; lists added under a test; the
    `EXTRA_INSTALLED_APPS` loop at `zproject/urls.py:904`). 202 of zulip's 477 patterns with no
    exact row have a row behind the hole (prefix `""` or `en-us/`).
  - **Handler not named, `handler_pass_through` question**: healthchecks 6, bookwyrm 7,
    weblate 58, zulip 1. **Handler not named, no question**: bookwyrm 8 (view objects,
    OI-539), weblate 15 (10 of them DRF), zulip 1.
  - **`narrowed`**: zulip 22 rows name the view and `zulip_login_required`'s lambda (34 rows
    in all, holes included; OI-532).
  - **Not found by Task 10**: zulip's 66 language-prefixed (`en-us/`) copies have no row
    (OI-550); zulip's 6 `re_path` routes to `SCIMView.as_view(implemented=False)`
    (`zproject/urls.py:936-951`) have no row (OI-549).
- **One helper entered twice on one path** (the walk's existing bound, M-1): the same
  decorator factory twice on one view gives handler not read. healthchecks: 5 routes (OI-537).
- **A list added under a test** (`if settings.DEVELOPMENT: urls += dev_urls.urls`): built
  2026-11-25 (ruling R1, fact schema 23, OI-508): the write carries its tests
  (`field_write.guards`) and the members are rows at their address with the condition (M5).
  A MOUNT written under a test gives its routes the condition (controller fix b1c75286).
- **A root setting written under a test** (zulip `zproject.tornado_urls` under
  `if RUNNING_INSIDE_TORNADO`): built 2026-11-25 (ruling R1, OI-509): its routes carry the
  test. Two roots each written under no test are two roots with no condition.
- **A library `dispatch` body** is now read (§2 item 9, Task 8).
- **A mount whose router argument is not read** is published as a route with no handler, at
  `partial`: nothing says it is a mount (OI-548).
- **The ancestor match is for Python modules only** (OI-524).

### 9c. Tests on the throwaway copy

7,555 pass, 64 fail: 44 Django tests of the first design; 10 FastAPI and receiver-binding
tests of the old held-list rule and of a wrapper now read through; 3 Java lambda numbers of
that copy's fixture build; 7 pins of facts, documents and the vocabulary.

The 13 field pins (`scripts/field_check.py`) are all `ok` with the change: no row lost in the
five Java and eight Python projects. The run took 1,115 s where 650 s is usual; Task 10
measures the cost again on the product branch.
 **Product branch, 2026-11-24:** 16 field pins (the 13, plus bookwyrm, weblate and zulip, pinned with `build: none` because the script cannot rebuild their environments) are all `ok`; a cold run of all 16 took 985 s.