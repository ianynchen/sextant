"""FastAPI prefixes: `include_router(prefix=)`, the router's own `APIRouter(prefix=)` and
Starlette sub-application mounts (plan 2026-11-08-python-fastapi-inbound Task 6; N6, N7;
rulings R4, R23).

FastAPI joins a prefix and a path by plain string concatenation and serves the result as it
is (`self.prefix + path`, `parent_router.prefix + prefix`): nothing is cleaned, so
`"/orders" + ""` is `/orders`. A Starlette `Mount` strips its trailing slashes
(`path.rstrip("/")`). The rules are quoted in `scripts/probes/fastapi_rules.md` §1-§2.

Each test writes a small FastAPI program, scans it with the real Python scanner against the
FastAPI 0.162.0 that `fixtures/orders-fastapi` locks, and runs the real pipeline with the
shipped catalogs (`test_fastapi_routes._resolved`).
"""

import json
import shutil
from pathlib import Path

import pytest
import test_fastapi_routes
from test_fastapi_routes import _handler, _questions, _resolved, _rows

from sextant.application.ports.catalogs import CatalogError
from sextant.resources import catalogs_dir

# The FastAPI environment the route tests read, shared rather than restated.
libraries = test_fastapi_routes.libraries

_APP = "from fastapi import APIRouter, FastAPI\napp = FastAPI()\n"


def _paths(workspace) -> list[tuple[object, object]]:
    return sorted((row[0], row[1]) for row in _rows(workspace))


def _refusals(workspace) -> list[tuple[object, object, str]]:
    """Each refused registration as (method, path, reason), one per candidate."""
    return sorted(
        (question["method"], question["path"], candidate["reason"])
        for question in _questions(workspace, "refused_registration")
        for candidate in json.loads(question["candidates"])
    )


def test_router_prefix_goes_before_every_route_on_it(tmp_path: Path, libraries):
    """`add_api_route`: `self.prefix + path`. The empty path is the prefix itself, never `/`
    (ruling R23: no cleaning)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "router = APIRouter(prefix='/orders')\n"
            + "@router.get('/{order_id}')\ndef get(order_id: int) -> str:\n    return ''\n"
            + "@router.post('')\ndef create() -> str:\n    return ''\n"
            + "app.include_router(router)\n"
        },
    )

    assert _rows(workspace) == [
        ("GET", "/orders/{order_id}", _handler("get"), "resolved", "string"),
        ("POST", "/orders", _handler("create"), "resolved", "string"),
    ]


def test_include_prefix_goes_before_the_router_prefix(tmp_path: Path, libraries):
    """`for_include`: the include's prefix in front of the route's path, which already carries
    the router's own prefix."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "router = APIRouter(prefix='/orders')\n"
            + "@router.get('/x')\ndef x() -> str:\n    return ''\n"
            + "app.include_router(router, prefix='/v1')\n"
        },
    )

    assert _paths(workspace) == [("GET", "/v1/orders/x")]


def test_a_parent_router_prefix_goes_before_an_include_on_it(tmp_path: Path, libraries):
    """The probe's composition (`fastapi_rules.md` §1): the outermost include, the parent's own
    prefix, the inner include, the inner router's own prefix, then the route's path."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "inner = APIRouter(prefix='/inner')\n"
            + "@inner.get('/leaf')\ndef leaf() -> str:\n    return ''\n"
            + "@inner.get('')\ndef bare() -> str:\n    return ''\n"
            + "middle = APIRouter(prefix='/middle')\n"
            + "middle.include_router(inner, prefix='/a')\n"
            + "app.include_router(middle, prefix='/b')\n"
        },
    )

    assert _paths(workspace) == [("GET", "/b/middle/a/inner"), ("GET", "/b/middle/a/inner/leaf")]


def test_a_sub_application_mount_prefixes_its_routes(tmp_path: Path, libraries):
    """`app.mount("/api/", app=api)` serves `api` under the mount path less its trailing
    slashes (Starlette's `Mount.__init__`: `path.rstrip("/")`), the routes `api` includes and
    its own alike. The outer app's own route is not under it."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "api = FastAPI()\n"
            + "v1 = APIRouter()\n"
            + "@v1.get('/x')\ndef x() -> str:\n    return ''\n"
            + "@api.get('/ping')\ndef ping() -> str:\n    return ''\n"
            + "@app.get('/health')\ndef health() -> str:\n    return ''\n"
            + "api.include_router(v1, prefix='/v1')\n"
            + "app.mount('/api//', app=api)\n"
        },
    )

    assert _paths(workspace) == [("GET", "/api/ping"), ("GET", "/api/v1/x"), ("GET", "/health")]


def test_a_factory_built_router_class_keeps_its_prefix(tmp_path: Path, libraries):
    """A router class made by a factory in another file (`fixtures/orders-fastapi`'s
    `routing.py`, polar's shape) is constructed as `APIRouter` is, so its `prefix=` is held.
    The construction is a `virtual <init>` of the library class; OI-341 does not reach it."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "routing.py": (
                "from fastapi import APIRouter as FastAPIRouter\n"
                "from fastapi.routing import APIRoute\n"
                "def router_class(route: type[APIRoute]) -> type[FastAPIRouter]:\n"
                "    class Router(FastAPIRouter):\n"
                "        def __init__(self, *args, **kwargs) -> None:\n"
                "            kwargs.setdefault('route_class', route)\n"
                "            super().__init__(*args, **kwargs)\n"
                "    return Router\n"
                "APIRouter = router_class(APIRoute)\n"
            ),
            "orders.py": (
                "from app.routing import APIRouter\n"
                "router = APIRouter(prefix='/orders')\n"
                "@router.get('/{order_id}')\ndef get(order_id: int) -> str:\n    return ''\n"
            ),
            "main.py": (
                "from fastapi import FastAPI\nfrom app import orders\n"
                "app = FastAPI()\napp.include_router(orders.router, prefix='/v1')\n"
            ),
        },
    )

    assert _rows(workspace) == [
        ("GET", "/v1/orders/{order_id}", _handler("get", "app/orders"), "resolved", "string")
    ]


def test_a_prefix_ending_in_slash_is_refused_and_the_route_has_no_row(tmp_path: Path, libraries):
    """`assert not prefix.endswith("/")`, in `APIRouter.__init__` and in `include_router`: the
    app does not start. Each route reached only that way has no row; the refusal is filed."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "held = APIRouter(prefix='/r/')\n"
            + "@held.get('/x')\ndef x() -> str:\n    return ''\n"
            + "included = APIRouter()\n"
            + "@included.get('/y')\ndef y() -> str:\n    return ''\n"
            + "app.include_router(included, prefix='/a/')\n"
            + "@app.get('/ok')\ndef ok() -> str:\n    return ''\n"
        },
    )

    assert _paths(workspace) == [("GET", "/ok")]
    assert _refusals(workspace) == [
        (None, "/a/", "trailing_slash"),
        (None, "/r/", "trailing_slash"),
    ]


def test_an_unrooted_prefix_is_refused(tmp_path: Path, libraries):
    """A prefix must start with `/` (ruling R4), a route path need not: `APIRouter(prefix="r")`
    is refused, while a route `x` under `/r` serves `/rx`, as FastAPI does."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "bad = APIRouter(prefix='r')\n"
            + "@bad.get('/x')\ndef x() -> str:\n    return ''\n"
            + "good = APIRouter(prefix='/r')\n"
            + "@good.get('x')\ndef y() -> str:\n    return ''\n"
            + "app.include_router(good)\n"
        },
    )

    assert _paths(workspace) == [("GET", "/rx")]
    assert _refusals(workspace) == [(None, "r", "unrooted_path")]


def test_empty_prefix_and_empty_path_is_refused(tmp_path: Path, libraries):
    """`Prefix and path cannot be both empty`: an include with no prefix of a router whose route
    path, its own prefix included, is empty. The route has no row; the router's other routes
    keep theirs. A router prefix or an include prefix makes the empty path fine."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "bare = APIRouter()\n"
            + "@bare.get('')\ndef empty() -> str:\n    return ''\n"
            + "@bare.get('/y')\ndef y() -> str:\n    return ''\n"
            + "app.include_router(bare)\n"
            + "held = APIRouter(prefix='/r')\n"
            + "@held.get('')\ndef r() -> str:\n    return ''\n"
            + "app.include_router(held)\n"
            + "plain = APIRouter()\n"
            + "@plain.get('')\ndef a() -> str:\n    return ''\n"
            + "app.include_router(plain, prefix='/a')\n"
        },
    )

    assert _paths(workspace) == [("GET", "/a"), ("GET", "/r"), ("GET", "/y")]
    assert _refusals(workspace) == [("GET", "", "empty_path")]


def test_a_router_included_twice_is_two_rows(tmp_path: Path, libraries):
    """One router included plain and with a prefix serves under both (the probe's `/p` and
    `/twice/p`)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "router = APIRouter()\n"
            + "@router.get('/p')\ndef p() -> str:\n    return ''\n"
            + "app.include_router(router)\n"
            + "app.include_router(router, prefix='/twice')\n"
        },
    )

    assert _paths(workspace) == [("GET", "/p"), ("GET", "/twice/p")]


def test_a_router_never_included_serves_at_its_own_prefix(tmp_path: Path, libraries):
    """A router no include receives is served as read, and as read it carries its own prefix:
    the prefix is the router's from its construction, not the include's."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": (
                "from fastapi import APIRouter\nrouter = APIRouter(prefix='/orders')\n"
                "@router.get('/x')\ndef x() -> str:\n    return ''\n"
            )
        },
    )

    assert _paths(workspace) == [("GET", "/orders/x")]


def test_static_files_mount_adds_no_rows(tmp_path: Path, libraries):
    """`app.mount("/static", StaticFiles(...))` mounts no router: no row, no question."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "from starlette.staticfiles import StaticFiles\n"
            + "app.mount('/static', StaticFiles(directory='static'), name='static')\n"
            + "@app.get('/h')\ndef h() -> str:\n    return ''\n"
        },
    )

    assert _paths(workspace) == [("GET", "/h")]
    assert _refusals(workspace) == []


@pytest.mark.parametrize(
    ("written", "replaced", "named"),
    [
        ("refuses: [unrooted, trailing_slash] }", "refuses: [unrooted, trailing] }", "refuses"),
        (
            "dependencies_arg: { keyword: dependencies }, refuses: [unrooted, trailing_slash] }",
            "dependencies_arg: { word: dependencies }, refuses: [unrooted, trailing_slash] }",
            "dependencies_arg",
        ),
        ('strip_trailing: "/"', 'strip_trailing: "//"', "strip_trailing"),
        ("\n  path_join: concatenate\n", "\n  path_join: concatenated\n", "path_join"),
    ],
)
def test_a_misspelt_prefix_key_is_refused(
    tmp_path: Path, libraries, written: str, replaced: str, named: str
):
    """A `router_holds` refusal word, a `dependencies_arg`, a `strip_trailing` and a `path_join`
    the engine does not know are refused at load, never read as nothing."""
    catalogs = tmp_path / "catalogs"
    shutil.copytree(catalogs_dir(), catalogs)
    text = (catalogs / "fastapi.yml").read_text(encoding="utf-8")
    assert written in text
    (catalogs / "fastapi.yml").write_text(text.replace(written, replaced, 1), encoding="utf-8")

    with pytest.raises(CatalogError) as raised:
        _resolved(tmp_path, libraries, {"main.py": _APP}, catalogs)

    assert named in str(raised.value)


def test_a_factory_router_pairs_each_callers_verb_with_its_own_prefix(tmp_path: Path, libraries):
    """polar's `get_oauth_login_router`: a factory builds a router per call, its prefix and a
    route's verb both read from the call's arguments. Each caller's verb goes with that caller's
    prefix alone, never another's (M-1): `apple` is POST only, `github` GET only."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "def login(name: str, method: str = 'GET') -> APIRouter:\n"
            + "    router = APIRouter(prefix=f'/{name}')\n"
            + "    @router.api_route('/callback', methods=[method])\n"
            + "    def callback() -> str:\n        return ''\n"
            + "    return router\n"
            + "app.include_router(login('apple', method='POST'))\n"
            + "app.include_router(login('github'))\n"
        },
    )

    assert _paths(workspace) == [("GET", "/github/callback"), ("POST", "/apple/callback")]


def test_a_router_subclass_passing_its_prefix_to_super_holds_it(tmp_path: Path, libraries):
    """mealie's `AdminAPIRouter(APIRouter)`, whose `__init__` hands `prefix` to
    `super().__init__`: the prefix is read where the base constructor is called, on the path
    entering that `__init__` from each construction, so `AdminAPIRouter(prefix="/admin")` holds
    `/admin`, and a router it includes is served below it."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "routers.py": (
                "from fastapi import APIRouter\n"
                "class AdminAPIRouter(APIRouter):\n"
                "    def __init__(self, tags=None, prefix: str = '', **kwargs):\n"
                "        super().__init__(tags=tags, prefix=prefix, **kwargs)\n"
            ),
            "about.py": (
                "from fastapi import APIRouter\nrouter = APIRouter(prefix='/about')\n"
                "@router.get('/version')\ndef v() -> str:\n    return ''\n"
            ),
            "admin.py": (
                "from app.routers import AdminAPIRouter\nfrom app import about\n"
                "router = AdminAPIRouter(prefix='/admin')\n"
                "@router.get('/ping')\ndef p() -> str:\n    return ''\n"
                "router.include_router(about.router, tags=['x'])\n"
            ),
            "main.py": (
                "from fastapi import APIRouter, FastAPI\nfrom app import admin\n"
                "api = APIRouter(prefix='/api')\napi.include_router(admin.router)\n"
                "app = FastAPI()\napp.include_router(api)\n"
            ),
        },
    )

    assert _paths(workspace) == [("GET", "/api/admin/about/version"), ("GET", "/api/admin/ping")]


def test_a_router_subclass_inheriting_the_constructor_holds_its_prefix(tmp_path: Path, libraries):
    """`class S(APIRouter): pass` runs `APIRouter.__init__`: `S(prefix="/s")` holds `/s`, and
    an include made on it goes below it."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "class S(APIRouter):\n    pass\n"
            + "inner = APIRouter(prefix='/r')\n@inner.get('/x')\ndef x() -> str:\n    return ''\n"
            + "s = S(prefix='/s')\n@s.get('/y')\ndef y() -> str:\n    return ''\n"
            + "s.include_router(inner, prefix='/inc')\n"
            + "app.include_router(s)\n"
        },
    )

    assert _paths(workspace) == [("GET", "/s/inc/r/x"), ("GET", "/s/y")]


def test_an_app_subclass_includes_its_routers(tmp_path: Path, libraries):
    """`class App(FastAPI)` inherits `include_router`: the include on it is a mount."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": (
                "from fastapi import APIRouter, FastAPI\n"
                "class App(FastAPI):\n    pass\n"
                "app = App()\n"
                "r = APIRouter(prefix='/r')\n@r.get('/x')\ndef x() -> str:\n    return ''\n"
                "@app.get('/own')\ndef own() -> str:\n    return ''\n"
                "app.include_router(r, prefix='/v1')\n"
            )
        },
    )

    assert _paths(workspace) == [("GET", "/own"), ("GET", "/v1/r/x")]


def test_a_router_subclass_whose_prefix_cannot_be_read_is_the_hole(tmp_path: Path, libraries):
    """A subclass whose `__init__` hands the base constructor only an unpacked mapping: the
    prefix may be in it, so it is the named hole at `partial`, never the empty prefix."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "class R(APIRouter):\n"
            + "    def __init__(self, **kwargs) -> None:\n"
            + "        super().__init__(**kwargs)\n"
            + "r = R(prefix='/r')\n@r.get('/x')\ndef x() -> str:\n    return ''\n"
            + "app.include_router(r)\n"
        },
    )

    assert [(row[1], row[3]) for row in _rows(workspace)] == [("<prefix>/x", "partial")]


def test_each_callers_verb_goes_with_its_own_include_prefix(tmp_path: Path, libraries):
    """A factory's router included per call with its own prefix: each call's verb is read on
    that call's include (M-1)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "def make(method: str) -> APIRouter:\n"
            + "    router = APIRouter()\n"
            + "    @router.api_route('/cb', methods=[method])\n"
            + "    def cb() -> str:\n        return ''\n"
            + "    return router\n"
            + "app.include_router(make('POST'), prefix='/a')\n"
            + "app.include_router(make('GET'), prefix='/b')\n"
        },
    )

    assert _paths(workspace) == [("GET", "/b/cb"), ("POST", "/a/cb")]


@pytest.mark.parametrize(
    ("router", "include_a", "include_b"),
    [
        ("APIRouter(prefix=f'/{name}')", "make('a', '/x')", "make('b', '/y')"),
        ("APIRouter()", "make('a', '/x'), prefix='/a'", "make('b', '/y'), prefix='/b'"),
    ],
)
def test_each_callers_route_path_goes_with_its_own_prefix(
    tmp_path: Path, libraries, router: str, include_a: str, include_b: str
):
    """A route path a factory takes from its caller is read on that caller's call, whether the
    prefix is the router's own or the include's: `/a/x` and `/b/y`, never `/a/y`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "def make(name: str, leaf: str) -> APIRouter:\n"
            + f"    router = {router}\n"
            + "    @router.get(leaf)\n"
            + "    def cb() -> str:\n        return ''\n"
            + "    return router\n"
            + f"app.include_router({include_a})\n"
            + f"app.include_router({include_b})\n"
        },
    )

    assert _paths(workspace) == [("GET", "/a/x"), ("GET", "/b/y")]


def test_a_crud_factory_serves_each_callers_handler_at_its_own_prefix(tmp_path: Path, libraries):
    """`make(prefix, handler)` with `add_api_route("/x", handler)`: `/a/x` is `ha` and `/b/x`
    is `hb`, each `resolved`, never both handlers on both paths."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "def ha() -> str:\n    return ''\n"
            + "def hb() -> int:\n    return 1\n"
            + "def make(name: str, handler) -> APIRouter:\n"
            + "    router = APIRouter(prefix=f'/{name}')\n"
            + "    router.add_api_route('/x', handler)\n"
            + "    return router\n"
            + "app.include_router(make('a', ha))\n"
            + "app.include_router(make('b', hb))\n"
        },
    )

    assert _rows(workspace) == [
        ("GET", "/a/x", _handler("ha"), "resolved", "string"),
        ("GET", "/b/x", _handler("hb"), "resolved", "integer"),
    ]
