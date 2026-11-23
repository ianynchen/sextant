# Django inbound REST, redesign (plan 6, second design)

**Status:** UNDER REVIEW, NOT READY. An adversarial review (2026-11-23) found 2 critical and
11 major issues; they go to the user one at a time and this document changes with each
ruling. No product code before approval.
**What was and was not run.** Rows 1–5, 7 and 9 of §4 were run as throwaway changes on a copy
(`tmp/django-on-main`, never merged). Rows 6, 11 (the targeted read), 12 and 18 were NOT run.
§3's numbers come from a driver script that walks down from a root module given by hand; it
is not the engine and not the algorithm of §4.
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
9. A library class's `dispatch` is read with the existing servlet rule; the scanner writes
   the existing call facts for the library methods a catalog names. No new fact.
10. `url_is: expression` is approved for `re_path`.
11. Not supported: a registration in a loop or comprehension; the keywords of a `**kwargs`
    parameter; a lookup by key in a dict. The row keeps its reason and a question names the
    line.

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

Still missed, by cause: Django admin about 330 (non-goal); DRF 254 (plan 7); zulip loops and
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
| 11 | A library `dispatch` override | servlet base class calling `super.service` | the same rule, read from a `special` call fact | scanner writes the existing call facts for catalog-named methods of library classes a project class extends; `calls_super` removed | fixture: correct with bodies read, wrong `resolved` row without; a full scan is 10x slower, so the read is targeted |
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
| M6 a copy taken part-way is over-read | truth | A read of a held list inside the body that writes it sees only the writes before it, by the order of the body. A read from another body sees every write. Where the order is not proven (a write in a loop or under a branch after the read), the member is `partial`. Zulip: `urls = list(i18n_urls)` at line 776, more added at 908 and 1022. |
| M7 when a held list is NOT exactly known | ruling 4, and the existing reasons | Known: the written members, `+`, `+=`, `append`, `extend`, a copy. Not known, and answered with the existing reason, never `resolved`: any other call on the list (`remove`, `pop`, `clear`, `insert`, `sort`, an index or slice store, `del`), or the list handed to code that is not read (`escapes`). The rule is in the shared value walk, so each case has a test that a wrong `resolved` row is not published, for Python and for Java. |
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

**To design before Task 9 is built:** where the captured values sit among the body's
parameters. A JVM lambda body is never called directly; a Python inner function is, and its
arguments are bound by its written signature, so the written parameters must keep their
positions. The format follows D00's `captures`.

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
- Non-goals: DRF (plan 7), admin, method tests in a view body (next design), request reads
  (the design after).

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
