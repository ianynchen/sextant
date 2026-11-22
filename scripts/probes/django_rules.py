"""Pin the Django URL-routing, view and request-read rules the Python inbound catalog copies (plan 6, Task 1).

Run it inside the orders-django fixture's own environment, never Sextant's:

    fixtures/orders-django/.venv/bin/python -I scripts/probes/django_rules.py

Every rule is asserted, then printed. URL lists are built in-process (settings configured without
a database), walked through `django.urls.get_resolver`, and requests go through Django's own test
client. The probe runs Django on purpose; Sextant itself never does (spec 7). Rules and quotes are
in `django_rules.md`.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import sys
import types
from functools import partial

import django
from django.conf import settings

settings.configure(
    SECRET_KEY="probe",
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF="probe_urls",
    INSTALLED_APPS=[],
    USE_TZ=True,
)
django.setup()

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.test import Client, RequestFactory
from django.urls import conf as urls_conf
from django.urls import include, path, re_path, register_converter, resolve
from django.urls.resolvers import RegexPattern, URLResolver, get_resolver
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.decorators import classonlymethod
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
    require_safe,
)


def rule(text: str) -> None:
    print(f"RULE: {text}")


def definer(cls: type, name: str) -> str:
    """The class in the MRO whose own __dict__ defines `name`, as module.Class."""
    for k in cls.__mro__:
        if name in k.__dict__:
            return f"{k.__module__}.{k.__name__}"
    raise AssertionError(name)


def ok(request, *a, **k):
    return HttpResponse("ok")


_ids = iter(range(10_000))


def mount(patterns: list) -> tuple[Client, types.ModuleType]:
    """Serve `patterns` as a fresh urlconf module; return its test client."""
    mod = types.ModuleType(f"probe_urls_{next(_ids)}")
    mod.urlpatterns = patterns  # type: ignore[attr-defined]
    sys.modules[mod.__name__] = mod
    settings.ROOT_URLCONF = mod.__name__
    return Client(), mod


def routes(patterns: list, prefix: str = "") -> list[str]:
    """Every leaf route as the concatenation of the patterns' own strings, nothing between."""
    out = []
    for p in patterns:
        here = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            out += routes(p.url_patterns, here)
        else:
            out.append(here)
    return out


def codes(client: Client, url: str, methods=("get", "post", "put", "delete")) -> dict[str, int]:
    return {m: getattr(client, m)(url).status_code for m in methods}


print("versions:", {d: importlib.metadata.version(d) for d in ("django",)})

# 1. Defining symbols.
assert path.func is urls_conf._path and re_path.func is urls_conf._path
assert isinstance(path, partial) and isinstance(re_path, partial)
assert path.keywords["Pattern"].__name__ == "RoutePattern"
assert re_path.keywords["Pattern"].__name__ == "RegexPattern"
assert path.func.__module__ == "django.urls.conf" and include.__module__ == "django.urls.conf"
assert urls_conf.path is path and sys.modules["django.urls"].path is path
rule(
    "path and re_path are functools.partial objects over django.urls.conf._path (Pattern=RoutePattern / RegexPattern), "
    "bound in django.urls.conf and re-exported by django.urls; include is the plain function django.urls.conf.include"
)
assert list(inspect.signature(urls_conf._path).parameters)[:4] == [
    "route",
    "view",
    "kwargs",
    "name",
]
assert list(inspect.signature(include).parameters) == ["arg", "namespace"]
rule(
    "path/re_path take (route, view, kwargs=None, name=None): route index 0, view index 1; include(arg, namespace=None)"
)
assert definer(View, "as_view") == "django.views.generic.base.View"
assert type(View.__dict__["as_view"]) is classonlymethod
assert classonlymethod.__mro__[1] is classmethod
rule(
    "View.as_view is defined on django.views.generic.base.View as django.utils.decorators.classonlymethod, "
    "whose base class is builtins.classmethod"
)
assert View.__module__ == "django.views.generic.base" and django.views.generic.View is View
rule(
    "django.views.generic.View and django.views.View are the same class as django.views.generic.base.View"
)
for name, dec in (
    ("require_http_methods", require_http_methods),
    ("require_GET", require_GET),
    ("require_POST", require_POST),
    ("require_safe", require_safe),
    ("csrf_exempt", csrf_exempt),
    ("cache_page", cache_page),
):
    print(f"OWNER: {name} -> {dec.__module__}")
assert require_GET.__module__ == require_http_methods.__module__ == "django.views.decorators.http"
assert csrf_exempt.__module__ == "django.views.decorators.csrf"
assert cache_page.__module__ == "django.views.decorators.cache"
rule(
    "require_http_methods/require_GET/require_POST/require_safe live in django.views.decorators.http; "
    "csrf_exempt in django.views.decorators.csrf; cache_page in django.views.decorators.cache"
)
print(
    "OWNER: HttpRequest.GET/COOKIES/headers/META:",
    {n: n in HttpRequest.__dict__ for n in ("GET", "COOKIES", "headers", "META")},
)
init_src = inspect.getsource(HttpRequest.__init__)
assert "self.GET = QueryDict(mutable=True)" in init_src
assert "self.COOKIES = {}" in init_src and "self.META = {}" in init_src
assert HttpRequest.__init__.__qualname__ == "HttpRequest.__init__"
assert HttpRequest.__module__ == "django.http.request"
assert not {"GET", "COOKIES", "META"} & set(HttpRequest.__dict__)
assert type(HttpRequest.__dict__["headers"]).__module__ == "django.utils.functional"
assert type(HttpRequest.__dict__["headers"]).__name__ == "cached_property"
assert register_converter.__module__ == "django.urls.converters"
assert django.urls.register_converter is register_converter
assert URLResolver._join_route.__qualname__ == "URLResolver._join_route"
assert URLResolver.__module__ == "django.urls.resolvers"
assert MultiValueDictKeyError.__module__ == "django.utils.datastructures"
assert inspect.isfunction(include)
rule(
    "HttpRequest.GET, .COOKIES, .META are instance attributes assigned in django.http.request.HttpRequest.__init__ "
    "(GET a QueryDict); HttpRequest.headers is a cached_property of the same class"
)

# 2. The join: pieces concatenate with nothing between them.
child = [
    path("", ok),
    path("x", ok),
    path("/lead", ok),
    path("<id>", ok),
    path("<int:id>", ok),
    path("<path:rest>", ok),
    path("<uuid:x>", ok),
]
assert routes(child) == ["", "x", "/lead", "<id>", "<int:id>", "<path:rest>", "<uuid:x>"]
rule(
    "a route string is stored verbatim by RoutePattern/RegexPattern (str(pattern.pattern) is the route as written)"
)
parent = [path("api", include(child)), path("api/", include(child)), path("", include(child))]
got = routes(parent)
assert got[:3] == ["api", "apix", "api/lead"], got
assert got[7:10] == ["api/", "api/x", "api//lead"], got
assert got[14:16] == ["", "x"], got
rule(
    "prefix and child route concatenate with nothing between: 'api'+'x' is 'apix', 'api/'+'x' is 'api/x', "
    "'api/'+'/lead' is 'api//lead'; an empty route adds nothing"
)
c, mod = mount([path("api/", include([path("", ok), path("x", ok), path("/lead", ok)]))])
assert c.get("/api/x").status_code == 200 and c.get("/api/").status_code == 200
assert c.get("/api//lead").status_code == 200 and c.get("/api/lead").status_code == 404
assert c.get("/apix").status_code == 404
rule(
    "served path equals the concatenation: '/api//lead' is 200 and '/api/lead' is 404; the request path always has the leading '/', the route string never does"
)
# The leading slash of a root route string is a system check warning, and the route still never matches '/x'.
c, mod = mount([path("/lead", ok), path("lead2", ok)])
assert c.get("/lead").status_code == 404 and c.get("//lead").status_code == 404
r = get_resolver(mod.__name__)
chk = [w.id for w in r.url_patterns[0].pattern.check()]
assert "urls.W002" in chk, chk
rule(
    f"a route that starts with '/' draws system check urls.W002 ({chk}); the request path '/lead' does not match the route '/lead' (404)"
)
assert c.get("/lead").status_code == 404 and c.get("/lead2").status_code == 200


# 3. Converters as the resolver reports them.
class Hex2:
    regex = "[0-9a-f]{2}"

    def to_python(self, v):
        return int(v, 16)

    def to_url(self, v):
        return f"{v:02x}"


register_converter(Hex2, "hex2")
c, mod = mount(
    [
        path("c/<id>", ok, name="plain"),
        path("i/<int:id>", ok),
        path("p/<path:rest>", ok),
        path("u/<uuid:x>", ok),
        path("h/<hex2:h>", ok),
        path("s/<slug:s>/<str:t>", ok),
    ]
)
seen = {}
for url in (
    "/c/a",
    "/i/7",
    "/p/a/b",
    "/u/12345678-1234-5678-1234-567812345678",
    "/h/ff",
    "/s/a-b/x",
):
    m = resolve(url)
    seen[url] = (str(m.route), {k: type(v).__name__ for k, v in m.kwargs.items()})
assert seen["/c/a"] == ("c/<id>", {"id": "str"})
assert seen["/i/7"] == ("i/<int:id>", {"id": "int"})
assert seen["/p/a/b"] == ("p/<path:rest>", {"rest": "str"})
assert seen["/u/12345678-1234-5678-1234-567812345678"][1] == {"x": "UUID"}
assert seen["/h/ff"] == ("h/<hex2:h>", {"h": "int"})
assert seen["/s/a-b/x"][1] == {"s": "str", "t": "str"}
assert c.get("/i/abc").status_code == 404 and c.get("/c/a/b").status_code == 404
assert c.get("/p/a/b").status_code == 200 and c.get("/h/zz").status_code == 404
rule(
    "ResolverMatch.route keeps converters as written: 'c/<id>', 'i/<int:id>', 'p/<path:rest>', 'u/<uuid:x>', 'h/<hex2:h>'; <id> with no converter is str"
)
rule(
    "view kwargs are converted by the converter's to_python: int -> int, uuid -> UUID, custom hex2 -> whatever to_python returns; <path:rest> is str and spans '/'; <id> does not span '/'"
)
try:
    path("bad/<nosuch:x>", ok)
except ImproperlyConfigured:
    pass
else:
    raise AssertionError("unknown converter accepted")
rule(
    "register_converter(Cls, 'hex2') is a call of django.urls.register_converter; a converter name that was never registered raises ImproperlyConfigured when the path() call runs"
)

# 4. include() forms.
inner = [path("leaf", ok)]
fake = types.ModuleType("probe_inc_mod")
fake.urlpatterns = inner  # type: ignore[attr-defined]
sys.modules["probe_inc_mod"] = fake
app_ns = types.ModuleType("probe_inc_app")
app_ns.urlpatterns = inner  # type: ignore[attr-defined]
app_ns.app_name = "shopapp"  # type: ignore[attr-defined]
sys.modules["probe_inc_app"] = app_ns
c, mod = mount(
    [
        path("s/", include("probe_inc_mod")),
        path("m/", include(fake)),
        path("l/", include(inner)),
        path("t/", include((inner, "tapp"))),
        path("n/", include((inner, "napp"), namespace="inst")),
        path("a/", include("probe_inc_app")),
        path("twice1/", include(inner)),
        path("twice2/", include(inner)),
    ]
)
for u in (
    "/s/leaf",
    "/m/leaf",
    "/l/leaf",
    "/t/leaf",
    "/n/leaf",
    "/a/leaf",
    "/twice1/leaf",
    "/twice2/leaf",
):
    assert c.get(u).status_code == 200, u
rule(
    "include accepts a dotted string, a module object, a list, and a (list, app_name) tuple; each mounts its patterns under the prefix"
)
assert resolve("/t/leaf").namespaces == ["tapp"] and resolve("/t/leaf").app_names == ["tapp"]
assert resolve("/n/leaf").namespaces == ["inst"] and resolve("/n/leaf").app_names == ["napp"]
assert resolve("/a/leaf").namespaces == ["shopapp"]
assert resolve("/l/leaf").namespaces == []
rule(
    "a (list, app_name) tuple sets namespace = app_name; namespace='inst' overrides the namespace and keeps app_name; a module's own app_name is read; no app_name means no namespace"
)
rule(
    "one list included twice mounts at both prefixes: '/twice1/leaf' and '/twice2/leaf' both 200 (the same list object is shared)"
)
bad = types.ModuleType("probe_inc_bad")
bad.patterns = inner  # type: ignore[attr-defined]
sys.modules["probe_inc_bad"] = bad
try:
    _ = path("x/", include("probe_inc_bad")).url_patterns
except ImproperlyConfigured:
    pass
else:
    raise AssertionError("module without urlpatterns accepted")
rule(
    "the variable Django reads from an included module is `urlpatterns`; a module naming the list anything else raises ImproperlyConfigured when the patterns are first needed"
)
c_a, mod_a = mount([path("only-a", ok)])
assert c_a.get("/only-a").status_code == 200
c_b, mod_b = mount([path("only-b", ok)])
assert c_b.get("/only-b").status_code == 200 and c_b.get("/only-a").status_code == 404
settings.ROOT_URLCONF = mod_a.__name__
assert c_b.get("/only-a").status_code == 200 and c_b.get("/only-b").status_code == 404
rule(
    "changing settings.ROOT_URLCONF to another module's dotted path changes which `urlpatterns` list the resolver serves ('/only-a' and '/only-b' swap between 200 and 404); every mount() above is this same assertion"
)


# 5. Function views.
@require_http_methods(["GET", "PUT"])
def v_rhm(request):
    return HttpResponse("ok")


@require_GET
def v_get(request):
    return HttpResponse("ok")


@require_POST
def v_post(request):
    return HttpResponse("ok")


@require_safe
def v_safe(request):
    return HttpResponse("ok")


@csrf_exempt
@require_POST
def v_csrf_over_post(request):
    return HttpResponse("ok")


v_cache_over_get = cache_page(60)(require_GET(ok))
v_csrf_call = csrf_exempt(require_POST(ok))
c, mod = mount(
    [
        path("plain", ok),
        path("rhm", v_rhm),
        path("get", v_get),
        path("post", v_post),
        path("safe", v_safe),
        path("csrf", v_csrf_over_post),
        path("cache", v_cache_over_get),
        path("csrfcall", v_csrf_call),
    ]
)
c.handler.enforce_csrf_checks = False
assert codes(c, "/plain") == {"get": 200, "post": 200, "put": 200, "delete": 200}
rule("a plain function view receives every method: GET, POST, PUT, DELETE all 200")
assert codes(c, "/rhm") == {"get": 200, "post": 405, "put": 200, "delete": 405}
rule("require_http_methods(['GET','PUT']) allows exactly GET and PUT; POST and DELETE are 405")
assert codes(c, "/get") == {"get": 200, "post": 405, "put": 405, "delete": 405}
assert c.head("/get").status_code == 405
rule(
    "require_GET allows only GET (405 for POST, PUT, DELETE) and also 405 for HEAD: it does not add HEAD (require_safe does)"
)
assert codes(c, "/post") == {"get": 405, "post": 200, "put": 405, "delete": 405}
rule("require_POST allows only POST")
assert codes(c, "/safe") == {"get": 200, "post": 405, "put": 405, "delete": 405}
assert c.head("/safe").status_code == 200
rule("require_safe allows GET and HEAD only")
assert codes(c, "/csrf") == {"get": 405, "post": 200, "put": 405, "delete": 405}
assert codes(c, "/csrfcall") == {"get": 405, "post": 200, "put": 405, "delete": 405}
rule(
    "csrf_exempt(view) keeps the inner allowed set whether applied as a decorator over require_POST or called on it: only POST is 200"
)
assert codes(c, "/cache") == {"get": 200, "post": 405, "put": 405, "delete": 405}
rule("cache_page(60)(view) keeps the inner allowed set: only GET is 200 (POST, PUT, DELETE 405)")
assert c.options("/plain").status_code == 200 and c.options("/get").status_code == 405
rule(
    "a function view has no automatic OPTIONS: an OPTIONS request reaches a plain view (200) and is 405 on a require_GET view"
)
# The allowed set is read from the decorator argument; the 405 carries it.
assert c.head("/rhm").status_code == 405 and c.options("/rhm").status_code == 405
rule(
    "require_http_methods(['GET','PUT']) adds no automatic HEAD or OPTIONS: HEAD and OPTIONS requests are both 405"
)
resp = c.post("/rhm")
assert set(resp.headers["Allow"].split(", ")) == {"GET", "PUT"}
assert c.post("/get").headers["Allow"] == "GET" and set(
    c.post("/safe").headers["Allow"].split(", ")
) == {"GET", "HEAD"}
rule(
    "the 405 response's Allow header lists the decorator's set: require_GET 'GET', require_safe 'GET, HEAD', require_http_methods(['GET','PUT']) 'GET, PUT'"
)
assert list(inspect.signature(require_http_methods).parameters) == ["request_method_list"]
rule(
    "require_http_methods(request_method_list): the allowed set is parameter 0, a list of method names"
)
assert v_get.__wrapped__ is not None and v_get.__name__ == "v_get" and v_get.__module__ == __name__
rule(
    "a require_* decorated view keeps its name and module (functools.wraps), so the decorated function is still the handler"
)


# 6. Class views.
class Items(View):
    def get(self, request):
        return HttpResponse("g")

    def post(self, request):
        return HttpResponse("p")


class Base(View):
    def get(self, request):
        return HttpResponse("g")

    def delete(self, request):
        return HttpResponse("d")


class Child(Base):
    def post(self, request):
        return HttpResponse("p")


class Narrow(Items):
    http_method_names = ("get",)


class Widened(View):
    http_method_names = ("get", "put", "custom")

    def get(self, request):
        return HttpResponse("g")

    def post(self, request):
        return HttpResponse("p")

    def put(self, request):
        return HttpResponse("p")

    def custom(self, request):
        return HttpResponse("custom")


class OwnOptions(View):
    def get(self, request):
        return HttpResponse("g")

    def options(self, request):
        return HttpResponse("mine", status=204)


class OwnHead(View):
    def get(self, request):
        return HttpResponse("g")

    def head(self, request):
        return HttpResponse("h", status=203)


class NoVerbs(View):
    pass


class Dispatcher(View):
    def dispatch(self, request, *a, **k):
        return HttpResponse("custom dispatch")

    def get(self, request):
        return HttpResponse("g")


c, mod = mount(
    [
        path("items", Items.as_view()),
        path("child", Child.as_view()),
        path("narrow", Narrow.as_view()),
        path("wide", Widened.as_view()),
        path("ownopt", OwnOptions.as_view()),
        path("ownhead", OwnHead.as_view()),
        path("noverbs", NoVerbs.as_view()),
        path("disp", Dispatcher.as_view()),
        path("init", Narrow.as_view(http_method_names=["post"])),
        path("initpost", Items.as_view(http_method_names=["get", "post", "delete"])),
    ]
)
assert codes(c, "/items") == {"get": 200, "post": 200, "put": 405, "delete": 405}
rule(
    "as_view() dispatches only methods the class defines: Items(get, post) answers GET and POST 200, PUT and DELETE 405"
)
assert View.http_method_names == [
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
]
rule(
    "View.http_method_names is ['get','post','put','patch','delete','head','options','trace'] (django.views.generic.base.View)"
)
assert codes(c, "/child") == {"get": 200, "post": 200, "put": 405, "delete": 200}
rule(
    "verb methods are inherited through the MRO: Child(Base) answers Base's get and delete and its own post"
)
assert codes(c, "/narrow") == {"get": 200, "post": 405, "put": 405, "delete": 405}
rule(
    "a class-level http_method_names overrides the dispatch list: Narrow(['get']) over a class with post leaves POST 405"
)
assert codes(c, "/wide") == {"get": 200, "post": 405, "put": 200, "delete": 405}
assert c.generic("CUSTOM", "/wide").status_code == 200
rule(
    "a class-level http_method_names can add a non-HTTP-standard name: a 'custom' method is called for the request method CUSTOM; names left out of the list are not dispatched even when defined"
)
assert definer(View, "options") == "django.views.generic.base.View"
assert c.options("/items").status_code == 200
assert set(c.options("/items").headers["Allow"].split(", ")) == {"GET", "POST", "HEAD", "OPTIONS"}
rule(
    "View defines options: an OPTIONS request is 200 on every class view and Allow lists the defined verbs plus HEAD and OPTIONS ('GET, POST, HEAD, OPTIONS' for Items)"
)
assert c.head("/items").status_code == 200 and c.head("/noverbs").status_code == 405
assert c.head("/ownhead").status_code == 203 and c.head("/items").content == b""
_req = RequestFactory().head("/x")
_inst = Items()
assert not hasattr(_inst, "head")
_inst.setup(_req)
assert _inst.head == _inst.get
assert "head" not in inspect.getsource(View.dispatch)
assert "self.head = self.get" in inspect.getsource(View.setup)


class NoSuperSetup(Items):
    def setup(self, request, *a, **k):
        self.request, self.args, self.kwargs = request, a, k


_ns = NoSuperSetup()
_ns.setup(_req)
assert not hasattr(_ns, "head")
assert NoSuperSetup.as_view()(_req).status_code == 405
rule(
    "View.setup assigns self.head = self.get when the class has get and no head: HEAD is 200 on Items; a class with its own head keeps it (203); a class with no get has no HEAD (405); an instance has no head before setup() and head == get after; View.dispatch never mentions head; a subclass whose setup does not call super has no head (HEAD 405)"
)
assert c.options("/ownopt").status_code == 204
rule("an options method on the subclass replaces View.options")
assert (
    codes(c, "/noverbs") == {"get": 405, "post": 405, "put": 405, "delete": 405}
    and c.options("/noverbs").status_code == 200
)
rule(
    "a View subclass with no verb methods answers 405 to every method except OPTIONS (200 from View.options)"
)
assert codes(c, "/disp")["get"] == 200 and c.post("/disp").content == b"custom dispatch"
rule(
    "a class that overrides dispatch answers every method itself (POST 200 with no post method): the verb set is then unknowable from the class body"
)
# initkwargs
assert codes(c, "/init") == {"get": 405, "post": 200, "put": 405, "delete": 405}
assert codes(c, "/initpost") == {"get": 200, "post": 200, "put": 405, "delete": 405}
try:
    Items.as_view(get=1)
except TypeError:
    pass
else:
    raise AssertionError("as_view(get=...) accepted")
try:
    Items.as_view(nonsense=1)
except TypeError:
    pass
else:
    raise AssertionError("as_view(nonsense=...) accepted")
assert Items.as_view(http_method_names=["get"]).view_initkwargs == {"http_method_names": ["get"]}
rule(
    "as_view(**initkwargs) sets instance attributes, so as_view(http_method_names=[...]) replaces the dispatch list for that route "
    "(['post'] on a class whose own list is ['get'] and which defines get and post answers POST 200 and GET 405, so the route's list wins over the class's; ['get','post','delete'] on Items still answers only GET and POST 200); "
    "a verb name as a keyword (get=...) or an attribute the class lacks raises TypeError at as_view()"
)
assert Items.as_view().view_class is Items and Items.as_view().__name__ == "view"
rule(
    "as_view() returns the closure `view` with .view_class set to the class; its __name__ is 'view', so the class must be read from view_class / the as_view receiver, never the name"
)

# 7. re_path.
c, mod = mount(
    [
        re_path(r"^exact/$", ok),
        re_path(r"^noend", ok),
        re_path(r"mid/x$", ok),
        re_path(r"loose/", ok),
        re_path(r"^opt/?$", ok),
        re_path(r"^named/(?P<id>\d+)/$", lambda r, **k: JsonResponse({"k": k}), name="named"),
        re_path(r"^unnamed/(\d+)/$", lambda r, *a, **k: JsonResponse({"a": a, "k": k})),
        re_path(r"^mixed/(\d+)/(?P<n>[a-z]+)/$", lambda r, *a, **k: JsonResponse({"a": a, "k": k})),
        re_path(r"^pre/", include([re_path(r"^in$", ok), re_path(r"in2$", ok)])),
    ]
)
g = lambda u: c.get(u).status_code
assert (g("/exact/"), g("/exact"), g("/exact/x")) == (200, 404, 404)
rule("re_path(r'^exact/$') matches '/exact/' only")
assert (g("/noend"), g("/noendx"), g("/noend/deeper")) == (200, 200, 200)
rule(
    "re_path with no trailing $ matches any path that starts with the pattern ('^noend' serves /noend, /noendx, /noend/deeper): the route is a prefix, not an exact path"
)
assert (g("/mid/x"), g("/zzmid/x"), g("/a/b/mid/x")) == (200, 404, 404)
assert (g("/loose/"), g("/zz/loose/"), g("/loose/deeper")) == (200, 200, 200)
rule(
    "a re_path with neither ^ nor a final $ ('loose/') is matched with regex.search: it matches anywhere in the path ('/loose/', '/zz/loose/', '/loose/deeper' all 200)"
)
rule(
    "a re_path whose final pattern ends in $ and is an endpoint is matched with regex.fullmatch: 'mid/x$' without ^ still answers '/mid/x' only ('/zzmid/x' and '/a/b/mid/x' are 404); so a missing ^ matters only when there is no final $"
)
assert (g("/opt"), g("/opt/"), g("/opt//")) == (200, 200, 404)
rule("re_path(r'^opt/?$') matches both '/opt' and '/opt/'")
assert c.get("/named/5/").json() == {"k": {"id": "5"}}
rule(
    "a named group is passed as a keyword argument, as a str: '/named/5/' calls view(request, id='5')"
)
assert c.get("/unnamed/5/").json() == {"a": ["5"], "k": {}}
rule("unnamed groups are passed as positional arguments when there is no named group")
assert c.get("/mixed/5/ab/").json() == {"a": [], "k": {"n": "ab"}}
rule(
    "when a pattern has any named group, unnamed groups are ignored: '/mixed/5/ab/' calls view(request, n='ab') with no positional '5'"
)
assert (g("/pre/in"), g("/pre/in2"), g("/prein2")) == (200, 200, 404)
assert str(resolve("/pre/in").route) == "^pre/in$"
assert (
    URLResolver._join_route("^pre/", "^in$") == "^pre/in$"
    and URLResolver._join_route("a/", "^in$") == "a/in$"
)
rule(
    "a re_path prefix and child are matched in turn against the remainder, so a child '^' still anchors at the child's start; ResolverMatch.route joins them with URLResolver._join_route, which drops the child's leading '^' ('^pre/' + '^in$' is '^pre/in$')"
)
assert definer(RegexPattern, "match") == "django.urls.resolvers.RegexPattern"
src = inspect.getsource(RegexPattern.match)
assert "self.regex.fullmatch(path)" in src and "self.regex.search(path)" in src
rule(
    "RegexPattern.match uses fullmatch when the pattern is an endpoint (no include below it) and ends with '$', otherwise search; the remainder after the match goes to the child patterns"
)


# 8. Request reads.
def reads(request):
    return JsonResponse({"v": request.GET["k"]})


def reads_get(request):
    return JsonResponse({"v": request.GET.get("k", "dflt")})


def reads_all(request):
    return JsonResponse(
        {
            "cookie": request.COOKIES.get("ck"),
            "hdr": request.headers.get("X-Thing"),
            "meta": request.META.get("HTTP_X_THING"),
            "ct": request.headers.get("Content-Type"),
        }
    )


class ReadView(View):
    def get(self, request):
        return JsonResponse({"self": self.__class__.__name__, "req": request is self.request})


c, mod = mount(
    [path("r", reads), path("rg", reads_get), path("ra", reads_all), path("rv", ReadView.as_view())]
)
c.raise_request_exception = False
assert c.get("/r", {"k": "v"}).json() == {"v": "v"}
assert c.get("/r").status_code == 500
rule(
    "request.GET['k'] with 'k' absent raises MultiValueDictKeyError (a KeyError subclass) that Django does not map to a client error: the response is 500, not 400 (the opposite of Flask's 400)"
)
assert issubclass(MultiValueDictKeyError, KeyError)
try:
    RequestFactory().get("/r").GET["k"]
except MultiValueDictKeyError:
    pass
else:
    raise AssertionError
assert RequestFactory().get("/r").GET.get("k") is None
assert c.get("/rg").json() == {"v": "dflt"} and c.get("/rg", {"k": "x"}).json() == {"v": "x"}
rule(
    "request.GET.get('k', default) never raises: absent -> the default (None without one), status 200"
)
c.cookies["ck"] = "cv"
j = c.get("/ra", headers={"X-Thing": "tv"}).json()
assert RequestFactory().get("/", headers={"X-Thing": "tv"}).headers.get("x-thing") == "tv"
assert j["cookie"] == "cv" and j["hdr"] == "tv" and j["meta"] == "tv"
rule(
    "request.COOKIES['ck'], request.headers['X-Thing'] and request.META['HTTP_X_THING'] read the same cookie / header; headers keys are case-insensitive and META keys are HTTP_ + upper-cased with '-' as '_'"
)
assert c.get("/rv").json() == {"self": "ReadView", "req": True}
assert list(inspect.signature(ReadView.get).parameters) == ["self", "request"]
assert next(iter(inspect.signature(ok).parameters)) == "request"
rule(
    "parameter 0 of a function view and parameter 1 (after self) of a class verb method is the HttpRequest; the same object is self.request"
)
from django.core.handlers.base import BaseHandler

assert "request.urlconf" in inspect.getsource(BaseHandler.resolve_request)
rule(
    "BaseHandler.resolve_request reads request.urlconf at request time, so a request whose `urlconf` attribute is set is resolved against that list instead: ROOT_URLCONF is the root only when request.urlconf is unset (the boundary §5d states)"
)
c2, mod2 = mount([path("a", ok)])
alt = types.ModuleType("probe_alt")
alt.urlpatterns = [path("b", ok)]  # type: ignore[attr-defined]
sys.modules["probe_alt"] = alt
req = RequestFactory().get("/b")
req.urlconf = "probe_alt"
assert resolve("/b", urlconf="probe_alt").func is ok
h = BaseHandler()
h.load_middleware()
assert h.get_response(req).status_code == 200
assert h.get_response(RequestFactory().get("/b")).status_code == 404
rule(
    "a request with request.urlconf set (the probe sets it by hand, as middleware would) swaps the root for that request only: '/b' is 200 under request.urlconf='probe_alt' and 404 under ROOT_URLCONF"
)

print("OK")
