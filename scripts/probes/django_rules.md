# Django URL-routing, view and request-read rules (plan 6, Task 1)

Measured by `django_rules.py`, run as
`fixtures/orders-django/.venv/bin/python -I scripts/probes/django_rules.py`.
Every rule below is an `assert` in the script. URL lists are built in-process with settings
configured by `django.conf.settings.configure(...)` (no database, no network); URLs are walked
through `django.urls.resolve` and requests go through `django.test.Client`.

**Version scope.** Django 5.2.8, pinned in the fixture's `pyproject.toml` and `uv.lock`. The running
process prints the version on its first line. Every verdict holds for this version and no other.

## Differs from the design

Against `docs/superpowers/specs/2026-11-22-python-django-core-design.md` §3 and §5c:

1. **§5c, "a missing `$` included: Django matches a prefix" is only half true.**
   `RegexPattern.match` uses `self.regex.fullmatch(path)` when the pattern is an endpoint
   (`_is_endpoint`, no include below it) and its text ends with `$`; otherwise `self.regex.search(path)`.
   So `^noend` serves `/noend`, `/noendx` and `/noend/deeper` (prefix), and a pattern with
   neither `^` nor a final `$` (`loose/`) matches anywhere (`/zz/loose/` is 200). But `mid/x$`
   with no `^` serves only `/mid/x`: the `$` makes it a full match. A missing `^` matters only
   when there is no final `$`.
2. **§5c read 1, "`^` and `$` are dropped" must also drop the child `^` after a prefix**, and
   **named versus unnamed groups matter.** When a pattern has any named group, unnamed groups are
   ignored (`^mixed/(\d+)/(?P<n>[a-z]+)/$` calls the view with `n=` only). Only a pattern with no
   named group passes unnamed groups as positional arguments. The unnamed group still has to match
   the URL text, but it adds no argument to the view.
3. **§3 rule 1, "joined with nothing between them" holds, and a child route that starts with `/`
   is a real case.** `path("api/", include([path("/lead", v)]))` serves `/api//lead`, not
   `/api/lead`. A route that starts with `/` at the root never matches (`/lead` is 404) and draws
   system check `urls.W002`. The catalog must not strip or add a slash.
4. **§3 rule 2, "narrows it", needs the exact sets.** `require_GET` serves GET only: a HEAD
   request is 405. `require_safe` serves GET and HEAD. `require_http_methods([...])` serves exactly
   its list, no automatic HEAD or OPTIONS. A function view has no automatic OPTIONS: an
   OPTIONS request reaches a plain function view (200) and is 405 on `require_GET`.
5. **§3 rule 3, "`View.as_view()` serves each name in `http_method_names`", leaves out three
   overrides.** (a) `as_view(http_method_names=[...])` replaces the list for that route (it is an
   initkwarg; `as_view` accepts any attribute the class already has, and raises `TypeError` for a
   verb name or an unknown name). The route's list wins over the class's. (b) A class that
   overrides `dispatch` answers every method, so its verb set cannot be read from its methods.
   (c) `http_method_names` may list a name that is not a standard verb (`custom`); the request
   method `CUSTOM` reaches `custom`.
6. **§3 rule 3, "the automatic `head`" is `View.setup`, not `View.dispatch`.** `setup` sets
   `self.head = self.get` when the class has `get` and no `head`. A class with no `get` has no
   HEAD (405). A class with its own `head` keeps it. `options` is `View.options`; a subclass
   `options` replaces it. A class view with no verb methods still answers OPTIONS 200.
7. **Request reads, not in the design: `request.GET["k"]` with `k` absent is 500, not 400.**
   `MultiValueDictKeyError` is a `KeyError` subclass that Django does not map to a client error
   (Flask's `BadRequestKeyError` answers 400). The `.get` form never raises. A row for the
   subscript read should not claim "400 when absent".
8. **`as_view()` returns a closure named `view`.** `view.__name__` is `'view'`;
   `view.view_class` holds the class. The class comes from the `as_view` receiver in the source,
   never from a name on the returned function.

## Defining symbols

Quoted symbols are the file's own names; no line numbers.

| Surface | Defined on | Module |
|---|---|---|
| `path` | `functools.partial(_path, Pattern=RoutePattern)`, bound in `django.urls.conf` | `django.urls.conf` (re-exported by `django.urls`) |
| `re_path` | `functools.partial(_path, Pattern=RegexPattern)` | `django.urls.conf` |
| `_path` | `def _path(route, view, kwargs=None, name=None, Pattern=None)` | `django.urls.conf` |
| `include` | plain function `include(arg, namespace=None)` | `django.urls.conf` |
| `register_converter` | function | `django.urls.converters`, re-exported by `django.urls` |
| `View`, `View.as_view`, `View.setup`, `View.dispatch`, `View.options`, `View.http_method_not_allowed` | `View` | `django.views.generic.base` |
| `View.as_view` kind | `classonlymethod`, whose base class is `classmethod` | `django.utils.decorators` |
| `require_http_methods`, `require_GET`, `require_POST`, `require_safe` | decorators | `django.views.decorators.http` |
| `csrf_exempt` | decorator | `django.views.decorators.csrf` |
| `cache_page` | decorator | `django.views.decorators.cache` |
| `RegexPattern.match`, `RoutePattern.match` | `RegexPattern`, `RoutePattern` | `django.urls.resolvers` |
| `URLResolver._join_route` | `URLResolver` | `django.urls.resolvers` |
| `HttpRequest.GET`, `.COOKIES`, `.META` | instance attributes assigned in `HttpRequest.__init__` | `django.http.request` |
| `HttpRequest.headers` | `cached_property` on `HttpRequest` | `django.http.request` |
| `MultiValueDictKeyError` | subclass of `KeyError` | `django.utils.datastructures` |

What the scanner must name: calls of `path`, `re_path`, `include` carry owner
`django/urls/conf#`, which is the module that defines them (the `partial` objects are module
variables, not functions). `as_view` is a `classonlymethod`, so the scanner must treat
`classonlymethod` as a `classmethod` kind to bind `Class.as_view()`.

## Paths

- `RoutePattern` and `RegexPattern` store the route text verbatim; `str(pattern.pattern)` is the
  route as written.
- Prefix and child route concatenate with nothing between: `'api'` + `'x'` is `apix`, `'api/'` +
  `'x'` is `api/x`, `'api/'` + `'/lead'` is `api//lead`. An empty route adds nothing. The served
  path is that string with a leading `/`.
- `path` and `re_path` take `(route, view, kwargs=None, name=None)`: route index 0, view index 1.
  `include(arg, namespace=None)`.
- `ResolverMatch.route` keeps converters as written: `c/<id>`, `i/<int:id>`, `p/<path:rest>`,
  `u/<uuid:x>`, `h/<hex2:h>` (a custom converter registered by `register_converter`).
- View keyword arguments are converted by the converter's `to_python`: `int` gives `int`, `uuid`
  gives `UUID`, `hex2` gives what its `to_python` returns; `<id>` has no converter and is `str`.
  `<path:rest>` spans `/`; `<id>` does not.
- A converter name never registered raises `ImproperlyConfigured` when the `path(...)` call runs.

## `include`

- `include` accepts a dotted string, a module object, a list, and a `(list, app_name)` tuple. Each
  mounts its patterns under the prefix.
- The variable Django reads from an included module is `urlpatterns`. A module that names its
  list anything else raises `ImproperlyConfigured` when the patterns are first needed.
- A `(list, app_name)` tuple sets the namespace to `app_name`. `namespace='inst'` overrides the
  namespace and keeps `app_name`. A module's own `app_name` is read. With no `app_name` there is
  no namespace.
- One list included at two prefixes mounts at both (`/twice1/leaf` and `/twice2/leaf` are 200).
- `ROOT_URLCONF` is the setting `get_resolver()` reads, a dotted module path; the root list is
  that module's `urlpatterns`.
- `BaseHandler.resolve_request` reads `request.urlconf`. Setting it on a request (the probe
  does so by hand) swaps the root for that request only: `/b` is 200 under `request.urlconf = 'probe_alt'` and 404 under
  `ROOT_URLCONF`. This is the boundary §5d states, measured: `ROOT_URLCONF` is the root only when
  `request.urlconf` is unset; a middleware that sets it is the case, not measured as such.

## Function views

| Registration | GET | POST | PUT | DELETE | Other |
|---|---|---|---|---|---|
| plain function | 200 | 200 | 200 | 200 | OPTIONS 200 |
| `require_http_methods(["GET", "PUT"])` | 200 | 405 | 200 | 405 | |
| `require_GET` | 200 | 405 | 405 | 405 | HEAD 405, OPTIONS 405 |
| `require_POST` | 405 | 200 | 405 | 405 | |
| `require_safe` | 200 | 405 | 405 | 405 | HEAD 200 |
| `csrf_exempt(require_POST(f))`, or `@csrf_exempt` over `@require_POST` | 405 | 200 | 405 | 405 | |
| `cache_page(60)(require_GET(f))` | 200 | 405 | 405 | 405 | |

- `require_http_methods(request_method_list)`: the allowed set is parameter 0, a list of method
  names. The 405 response's `Allow` header lists the set: `GET` for `require_GET`, `GET, HEAD` for
  `require_safe`, `GET, PUT` for `require_http_methods(["GET", "PUT"])`.
- `csrf_exempt` and `cache_page` keep the inner function's allowed set, as a decorator or as a call.
- A `require_*` decorated view keeps its name and module (`functools.wraps`), so the decorated
  function is still the handler.

## Class views

- `View.http_method_names` is `['get','post','put','patch','delete','head','options','trace']`.
- `as_view()` dispatches only methods the class defines: `Items(get, post)` answers GET and POST
  200, PUT and DELETE 405.
- Verb methods are inherited through the MRO: `Child(Base)` answers `Base.get`, `Base.delete` and
  its own `post`.
- A class-level `http_method_names` overrides the list: `('get',)` over a class with `post`
  leaves POST 405. Names left out of the list are not dispatched even when defined.
- `View.options` answers OPTIONS 200 on every class view; `Allow` lists the defined verbs plus
  `HEAD` and `OPTIONS` (`GET, POST, HEAD, OPTIONS` for `Items`). A subclass `options` replaces it.
- HEAD: `View.setup` sets `self.head = self.get` when there is a `get` and no `head`. HEAD is 200
  on `Items` and has no body; an own `head` is kept (203 in the probe); no `get` means HEAD is 405.
- A `View` subclass with no verb methods answers 405 to every method except OPTIONS (200).
- A class overriding `dispatch` answers every method itself (POST 200 with no `post` method).
- `as_view(**initkwargs)` sets instance attributes. `as_view(http_method_names=['post'])` on a class
  that defines `get` and `post` answers POST 200 and GET 405; `['get','post','delete']` on `Items`
  still answers only GET and POST. A verb name as a keyword (`get=...`) or an attribute the class
  lacks raises `TypeError` at `as_view()`. `view.view_initkwargs` holds them.
- `as_view()` returns the closure `view` with `.view_class` set to the class.
- `View.as_view` is a `classonlymethod` of `django.utils.decorators`, whose base class is
  `classmethod`. `django.views.generic.View` is the same class as
  `django.views.generic.base.View`.

## `re_path`

| Expression | Serves |
|---|---|
| `^exact/$` | `/exact/` only |
| `^noend` | `/noend`, `/noendx`, `/noend/deeper` (prefix) |
| `mid/x$` | `/mid/x` only (final `$`: `fullmatch`); `/zzmid/x` and `/a/b/mid/x` are 404 |
| `loose/` | `/loose/`, `/zz/loose/`, `/loose/deeper` (no `^`, no `$`: `search`) |
| `^opt/?$` | `/opt` and `/opt/`; `/opt//` is 404 |
| `^named/(?P<id>\d+)/$` | view called with `id='5'` (str keyword) |
| `^unnamed/(\d+)/$` | view called with `'5'` positional |
| `^mixed/(\d+)/(?P<n>[a-z]+)/$` | view called with `n='ab'` only; the unnamed group is ignored |

- `RegexPattern.match` returns `fullmatch` for an endpoint ending in `$`, and `search` otherwise.
  The remainder after the match goes to the child patterns.
- A `re_path` prefix and a `re_path` child are each matched against the remainder, so a child `^`
  still anchors at the child's start. `ResolverMatch.route` joins them with
  `URLResolver._join_route`, which drops the child's leading `^`: `^pre/` and `^in$` give
  `^pre/in$`.
- A route starting with `/` (see "Differs from the design" item 3) is `urls.W002`.

## Request reads

- `request.GET["k"]` with `k` absent raises `MultiValueDictKeyError` (a `KeyError`); the client
  gets **500**. `request.GET.get("k", default)` never raises.
- `request.COOKIES["ck"]`, `request.headers["X-Thing"]` and `request.META["HTTP_X_THING"]` read
  the same cookie and header; `headers` keys are case-insensitive, `META` keys are `HTTP_` plus
  the upper-cased name with `-` as `_`.
- Parameter 0 of a function view, and parameter 1 (after `self`) of a class verb method, is the
  `HttpRequest`; it is the same object as `self.request`.

## Not measured

- `re_path` optional pieces other than `/?` (`(\.json)?`, `(?P<id>\d+)?`, `deactivate?`) and
  alternation groups: the design's §5c reads 2 and 3 are Sextant's own structural reads of the
  expression text, not a Django behaviour. Django's regex engine is Python `re`; the probe measures
  only the shapes named in the table.
- Async views (`async def` verb methods, `view_is_async`): not in the brief.
- `decorator_from_middleware`-style decorators and `method_decorator` on class methods: not in the
  brief.

## Observations

| Check | 5.2.8 |
|---|---|
| Assertions in `scripts/probes/django_rules.py` | all pass; the run prints `OK` |
| `RULE:` lines printed | 58 |

The `5.2.8` column is the version the process under test printed on its first line
(`importlib.metadata.version("django")`, run by `scripts/probes/django_rules.py` inside
`fixtures/orders-django/.venv`), not the version the fixture's `pyproject.toml` asked for.
Every rule in this file is one of those printed `RULE:` lines; each row of the defining-symbol
table is an assertion the probe makes before it prints them.
