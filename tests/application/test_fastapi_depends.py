"""FastAPI dependencies (plan 2026-11-08-python-fastapi-inbound Task 8; N5, N6, N10, N11; Review
Focus 1).

FastAPI fills a parameter marked `Depends(recipe)` with what it gets by calling the recipe (a
generator's first yield), and flattens the recipe's own parameters into the route's
(`dependencies/utils.py` `get_dependant`, `get_flat_dependant`): a recipe's query, header and
cookie parameters are the route's. `dependencies=` on a route, a router, an include and the app
run before the handler too; a sub-application mounted with `mount` takes none of its parent's.

The value walk reads the recipe as one more path BESIDE the parameter's in-module callers (N5):
a caller passing an argument is its own path. Each recipe FastAPI runs is a `roots` row at the
route's address (N11).

Each test writes a small FastAPI program, scans it with the real Python scanner against the
FastAPI 0.162.0 that `fixtures/orders-fastapi` locks, and runs the real pipeline with the
shipped catalogs (`test_fastapi_routes._resolved`).
"""

import shutil
from pathlib import Path

import pytest
import test_fastapi_routes
from test_fastapi_request_params import _params
from test_fastapi_routes import _bare, _resolved

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.receiver_binding import bind_until_settled
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir

libraries = test_fastapi_routes.libraries

_HEAD = (
    "from typing import Annotated\n"
    "from fastapi import APIRouter, Depends, FastAPI, Header\n"
    "router = APIRouter()\n"
    "class Repo:\n"
    "    def find(self) -> int:\n"
    "        return 1\n"
    "class Other(Repo):\n"
    "    def find(self) -> int:\n"
    "        return 2\n"
)


def _owners(workspace, caller: str, name: str) -> list[tuple[object, object]]:
    """Each bound receiver of the calls named `name` in `caller` (a bare symbol prefix):
    (owner, reason), sorted."""
    sites = {
        (row["caller"], row["ordinal"])
        for row in workspace.query("call_sites")
        if row["name"] == name and str(_bare(row["caller"])).startswith(caller)
    }
    return sorted(
        {
            (row["owner"], row["reason"])
            for row in workspace.query("bound_receivers")
            if (row["caller"], row["ordinal"]) in sites
        },
        key=repr,
    )


def _callees(workspace, caller: str, name: str) -> list[str]:
    """The bodies the calls named `name` in `caller` reach (`call_edges`), bare and without
    their signature."""
    return sorted(
        {
            str(_bare(row["callee"])).split("(")[0]
            for row in workspace.query("call_edges")
            if row["callee"] is not None
            and str(_bare(row["caller"])).startswith(caller)
            and str(row["callee"]).split("(")[0].endswith(f"#{name}")
        }
    )


def _roots(workspace) -> list[tuple[object, ...]]:
    """Each root as (handler, kind, method, path), the handler bare."""
    return sorted(
        (
            (_bare(row["handler"]), row["root_kind"], row["method"], row["path"])
            for row in workspace.query("roots")
        ),
        key=repr,
    )


def test_depends_default_fills_the_parameter_with_the_recipe_return(tmp_path: Path, libraries):
    """`repo = Depends(get_repo)`, unannotated: the receiver is what `get_repo` returns."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "def get_repo():\n"
            "    return Other()\n"
            "@router.get('/x')\n"
            "def handler(repo=Depends(get_repo)) -> str:\n"
            "    repo.find()\n"
            "    return ''\n"
        },
    )

    assert _owners(workspace, "app/main#handler", "find") == [("app/main/Other#", None)]


def test_a_yield_dependency_fills_with_its_first_yield(tmp_path: Path, libraries):
    """A generator recipe hands the parameter its yield (N10), not the generator object."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "def get_repo():\n"
            "    repo = Other()\n"
            "    try:\n"
            "        yield repo\n"
            "    finally:\n"
            "        pass\n"
            "@router.get('/x')\n"
            "def handler(repo=Depends(get_repo)) -> str:\n"
            "    repo.find()\n"
            "    return ''\n"
        },
    )

    assert _owners(workspace, "app/main#handler", "find") == [("app/main/Other#", None)]


def test_alias_dependency_in_another_file_binds_the_receiver(tmp_path: Path, libraries):
    """Review Focus 1: `db_session: DbSession`, `DbSession = Annotated[Session,
    Depends(get_db)]` in `deps.py`. No query row; the recipe `get_db` runs at the route (a
    root); `db_session.query(...)` binds to `Session`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "deps.py": (
                "from typing import Annotated\n"
                "from fastapi import Depends\n"
                "class Session:\n"
                "    def query(self, what: str) -> int:\n"
                "        return 0\n"
                "def get_db():\n"
                "    session = Session()\n"
                "    try:\n"
                "        yield session\n"
                "    finally:\n"
                "        pass\n"
                "DbSession = Annotated[Session, Depends(get_db)]\n"
            ),
            "main.py": (
                "from fastapi import APIRouter\n"
                "from app.deps import DbSession\n"
                "router = APIRouter()\n"
                "@router.get('/x')\n"
                "def handler(db_session: DbSession) -> str:\n"
                "    db_session.query('orders')\n"
                "    return ''\n"
            ),
        },
    )

    assert _params(workspace) == []
    assert _callees(workspace, "app/main#handler", "query") == ["app/deps/Session#query"]
    assert ("app/deps#get_db", "inbound_endpoint", "GET", "/x") in [
        (str(handler).split("(")[0], kind, method, path)
        for handler, kind, method, path in _roots(workspace)
    ]


def test_empty_depends_constructs_the_parameter_type(tmp_path: Path, libraries):
    """`Depends()` with nothing: the parameter's type is the recipe (`empty_recipe:
    parameter_type`), constructed, so its `__init__` runs at the route."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class Paging:\n"
            "    def __init__(self, limit: int = 20) -> None:\n"
            "        self.limit = limit\n"
            "    def page(self) -> int:\n"
            "        return self.limit\n"
            "@router.get('/x')\n"
            "def handler(p: Paging = Depends()) -> str:\n"
            "    p.page()\n"
            "    return ''\n"
        },
    )

    assert _callees(workspace, "app/main#handler", "page") == ["app/main/Paging#page"]
    assert [
        (str(handler).split("(")[0], kind, path)
        for handler, kind, _, path in _roots(workspace)
        if "Paging" in str(handler)
    ] == [("app/main/Paging#<init>", "inbound_endpoint", "/x")]


def test_an_instance_recipe_runs_its_call_method(tmp_path: Path, libraries):
    """Polar's `Authenticator`: `Depends(Authenticator("scope"))` runs the instance's class's
    `__call__`, whose return fills the parameter and whose header is the route's."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class User:\n"
            "    def name(self) -> str:\n"
            "        return ''\n"
            "class Authenticator:\n"
            "    def __init__(self, scope: str) -> None:\n"
            "        self.scope = scope\n"
            "    def __call__(self, x_api_key: Annotated[str, Header()]) -> User:\n"
            "        return User()\n"
            "Principal = Annotated[User, Depends(Authenticator('orders:read'))]\n"
            "@router.get('/x')\n"
            "def handler(who: Principal) -> str:\n"
            "    who.name()\n"
            "    return ''\n"
        },
    )

    assert _callees(workspace, "app/main#handler", "name") == ["app/main/User#name"]
    assert _params(workspace) == [("GET", "/x", "header", "x-api-key", "required", "resolved")]
    assert [str(handler).split("(")[0] for handler, _, _, _ in _roots(workspace)] == [
        "app/main#handler",
        "app/main/Authenticator#__call__",
    ]


def test_a_direct_caller_argument_is_its_own_path(tmp_path: Path, libraries):
    """N5 option A: the recipe is one more path beside the in-module callers. A caller that
    passes `Repo()` is its own path; FastAPI's fill is another."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "def get_repo():\n"
            "    return Other()\n"
            "def helper(repo=Depends(get_repo)) -> int:\n"
            "    return repo.find()\n"
            "def caller() -> int:\n"
            "    return helper(Repo())\n"
        },
    )

    assert _owners(workspace, "app/main#helper", "find") == [
        ("app/main/Other#", None),
        ("app/main/Repo#", None),
    ]


def test_a_recipe_header_joins_the_route_params(tmp_path: Path, libraries):
    """A recipe's own `Header()` parameter is the route's, recursively: `audit` depends on
    `who`, whose header is read too."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "def who(x_user: Annotated[str, Header()]) -> str:\n"
            "    return x_user\n"
            "def audit(x_audit: Annotated[str, Header()], by: str = Depends(who)) -> str:\n"
            "    return x_audit\n"
            "@router.get('/x')\n"
            "def handler(a: str = Depends(audit)) -> str:\n"
            "    return a\n"
        },
    )

    assert _params(workspace) == [
        ("GET", "/x", "header", "x-audit", "required", "resolved"),
        ("GET", "/x", "header", "x-user", "required", "resolved"),
    ]


def test_a_class_recipe_init_params_are_queries(tmp_path: Path, libraries):
    """`Paging = Depends()` on a class: its `__init__` parameters, without `self`, are the
    route's query parameters, optional where they default."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class Paging:\n"
            "    def __init__(self, limit: int = 20, offset: int = 0) -> None:\n"
            "        self.limit = limit\n"
            "        self.offset = offset\n"
            "@router.get('/x')\n"
            "def handler(p: Paging = Depends()) -> str:\n"
            "    return ''\n"
        },
    )

    assert _params(workspace) == [
        ("GET", "/x", "query", "limit", "optional", "resolved"),
        ("GET", "/x", "query", "offset", "optional", "resolved"),
    ]


def test_route_router_include_and_app_dependencies_join(tmp_path: Path, libraries):
    """N6: `dependencies=` on the route, on the router's construction, on the include and on the
    app all run before the handler. A sub-application `mount`ed under the app takes none of
    the app's: Starlette serves it as an application of its own."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": (
                "from typing import Annotated\n"
                "from fastapi import APIRouter, Depends, FastAPI, Header\n"
                "def a(x_a: Annotated[str, Header()]) -> None:\n"
                "    return None\n"
                "def b(x_b: Annotated[str, Header()]) -> None:\n"
                "    return None\n"
                "def c(x_c: Annotated[str, Header()]) -> None:\n"
                "    return None\n"
                "def d(x_d: Annotated[str, Header()]) -> None:\n"
                "    return None\n"
                "app = FastAPI(dependencies=[Depends(a)])\n"
                "router = APIRouter(dependencies=[Depends(b)])\n"
                "@router.get('/x', dependencies=[Depends(c)])\n"
                "def handler() -> str:\n"
                "    return ''\n"
                "app.include_router(router, dependencies=[Depends(d)])\n"
                "sub = FastAPI()\n"
                "@sub.get('/y')\n"
                "def served() -> str:\n"
                "    return ''\n"
                "app.mount('/sub', sub)\n"
            )
        },
    )

    assert _params(workspace) == [
        ("GET", "/x", "header", "x-a", "required", "resolved"),
        ("GET", "/x", "header", "x-b", "required", "resolved"),
        ("GET", "/x", "header", "x-c", "required", "resolved"),
        ("GET", "/x", "header", "x-d", "required", "resolved"),
    ]


def test_a_router_included_twice_gets_each_include_dependencies_on_its_row(
    tmp_path: Path, libraries
):
    """Two includes of one router are two serving places: each row takes its own include's
    dependencies, never the other's."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": (
                "from typing import Annotated\n"
                "from fastapi import APIRouter, Depends, FastAPI, Header\n"
                "def a(x_a: Annotated[str, Header()]) -> None:\n"
                "    return None\n"
                "def b(x_b: Annotated[str, Header()]) -> None:\n"
                "    return None\n"
                "app = FastAPI()\n"
                "router = APIRouter()\n"
                "@router.get('/x')\n"
                "def handler() -> str:\n"
                "    return ''\n"
                "app.include_router(router, prefix='/one', dependencies=[Depends(a)])\n"
                "app.include_router(router, prefix='/two', dependencies=[Depends(b)])\n"
            )
        },
    )

    assert _params(workspace) == [
        ("GET", "/one/x", "header", "x-a", "required", "resolved"),
        ("GET", "/two/x", "header", "x-b", "required", "resolved"),
    ]


def test_each_recipe_is_a_root_at_the_route_address(tmp_path: Path, libraries):
    """N11: one `roots` row per recipe FastAPI runs for a route, nested recipes included, at
    the route's address, `inbound_endpoint`; the handler keeps its own."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "def inner() -> str:\n"
            "    return ''\n"
            "def outer(i: str = Depends(inner)) -> str:\n"
            "    return i\n"
            "@router.get('/x', dependencies=[Depends(inner)])\n"
            "def handler(o: str = Depends(outer)) -> str:\n"
            "    return o\n"
        },
    )

    assert [
        (str(handler).split("(")[0], kind, method, path)
        for handler, kind, method, path in _roots(workspace)
    ] == [
        ("app/main#handler", "inbound_endpoint", "GET", "/x"),
        ("app/main#inner", "inbound_endpoint", "GET", "/x"),
        ("app/main#outer", "inbound_endpoint", "GET", "/x"),
    ]


def test_a_recipe_in_code_not_scanned_is_external(tmp_path: Path, libraries):
    """A recipe from a library (`HTTPBearer()`, whose `__call__` is not read here) fills its
    parameter from code not scanned: `external`, and it is no root."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": (
                "from fastapi import APIRouter, Depends\n"
                "from fastapi.security import HTTPBearer\n"
                "router = APIRouter()\n"
                "@router.get('/x')\n"
                "def handler(credentials=Depends(HTTPBearer())) -> str:\n"
                "    credentials.lower()\n"
                "    return ''\n"
            )
        },
    )

    assert _owners(workspace, "app/main#handler", "lower") == [(None, "external")]
    assert [str(handler).split("(")[0] for handler, _, _, _ in _roots(workspace)] == [
        "app/main#handler"
    ]


def test_a_recipe_imported_from_another_file_is_the_function_it_names(tmp_path: Path, libraries):
    """`from app.deps import get_repo`, then `Depends(get_repo)`: the file reads the name as a
    field nothing writes, and the `def` that binds it is the recipe (polar's `get_db_session`)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "deps.py": (
                "class Repo:\n"
                "    def find(self) -> int:\n"
                "        return 1\n"
                "def get_repo():\n"
                "    return Repo()\n"
            ),
            "main.py": (
                "from fastapi import APIRouter, Depends\n"
                "from app.deps import get_repo\n"
                "router = APIRouter()\n"
                "@router.get('/x')\n"
                "def handler(repo=Depends(get_repo)) -> str:\n"
                "    repo.find()\n"
                "    return ''\n"
            ),
        },
    )

    assert _owners(workspace, "app/main#handler", "find") == [("app/deps/Repo#", None)]
    assert ("app/deps#get_repo", "inbound_endpoint", "GET", "/x") in [
        (str(handler).split("(")[0], kind, method, path)
        for handler, kind, method, path in _roots(workspace)
    ]


@pytest.mark.parametrize(
    ("written", "replaced", "named"),
    [
        (
            "method: Security, recipe_arg: { arg: 0, keyword: dependency }",
            "method: Security, recipe_arg: { arg: x }",
            "recipe_calls",
        ),
        ("empty_recipe: parameter_type", "empty_recipe: parameter", "empty_recipe"),
        ("injection: names_recipe", "injection: names_recipes", "injection"),
    ],
)
def test_a_malformed_recipe_model_is_refused(tmp_path: Path, written, replaced, named):
    """A misspelt `names_recipe` key would leave every marked parameter filled by nothing."""
    catalogs = tmp_path / "catalogs"
    shutil.copytree(catalogs_dir(), catalogs)
    model = catalogs / "bean-models" / "fastapi.yml"
    text = model.read_text(encoding="utf-8")
    assert written in text
    model.write_text(text.replace(written, replaced), encoding="utf-8")

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(catalogs).bean_models()

    assert named in str(raised.value)


def _bound_whole(workspace) -> None:
    """Binding run again with every round walking every site over a rebuilt index (the
    reference the incremental rounds are proved against)."""
    bind_until_settled(workspace, YamlCatalogSource(catalogs_dir()).load(), incremental=False)


def test_a_handler_also_called_directly_keeps_the_callers_path_round_by_round(
    tmp_path: Path, libraries
):
    """Review C1: `h` is a route (the decorator rebinds its name, so the call `h(Other())` gets
    its edge only in a later round) and is also called directly. The direct caller's value is
    its own path beside FastAPI's fill, and the rounds give what binding every site whole
    gives."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "def get_repo():\n"
            "    return Repo()\n"
            "@router.get('/x')\n"
            "def h(repo=Depends(get_repo)) -> str:\n"
            "    repo.find()\n"
            "    return ''\n"
            "def caller() -> None:\n"
            "    h(Other())\n"
        },
    )

    incremental = _owners(workspace, "app/main#h", "find")
    _bound_whole(workspace)

    assert ("app/main/Other#", None) in incremental
    assert ("app/main/Repo#", None) in incremental
    assert incremental == _owners(workspace, "app/main#h", "find")


def test_one_handlers_parameters_come_from_one_calling_context(tmp_path: Path, libraries):
    """Review M1: under FastAPI `h` gets `Repo()` and `A()`, so `A.pick(Repo())` is a `Repo`;
    called as `h(Other(), B())`, `B.pick` makes an `Other2`. The direct caller's `Other` with
    FastAPI's `A` is no run of the code, so it is never an owner."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class Other2(Repo):\n"
            "    def find(self) -> int:\n"
            "        return 3\n"
            "class A:\n"
            "    def pick(self, r):\n"
            "        return r\n"
            "class B:\n"
            "    def pick(self, r):\n"
            "        return Other2()\n"
            "def get_repo():\n"
            "    return Repo()\n"
            "def get_o():\n"
            "    return A()\n"
            "def h(repo=Depends(get_repo), o=Depends(get_o)) -> str:\n"
            "    o.pick(repo).find()\n"
            "    return ''\n"
            "router.get('/x')(h)\n"
            "def caller() -> None:\n"
            "    h(Other(), B())\n"
        },
    )

    owners = {owner for owner, _ in _owners(workspace, "app/main#h", "find")}
    _bound_whole(workspace)
    whole = {owner for owner, _ in _owners(workspace, "app/main#h", "find")}

    assert "app/main/Other#" not in owners | whole
    assert {"app/main/Repo#", "app/main/Other2#"} <= owners
    assert owners == whole
