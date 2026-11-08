"""FastAPI routes are `fluent` rows: verbs, paths, handlers and responses (plan
2026-11-08-python-fastapi-inbound Task 5; N8, N9; rulings R1, R4).

Each test writes a small FastAPI program, scans it with the real Python scanner against the
FastAPI 0.162.0 that `fixtures/orders-fastapi` locks (its own environment is the library read),
and runs the real pipeline with the shipped catalogs. It then reads `endpoints`. The rules are
FastAPI's own, quoted in `scripts/probes/fastapi_rules.md`.
"""

import json
import shutil
from pathlib import Path

import pytest
from fixture_module import FIXTURE_CAPABILITIES

from fixture_python import FIXTURES
from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.pipeline import resolve
from sextant.application.resolve.values import PATH_CAP
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_PREFIX = "sextant-python pypi shop 1 "
# The distributions `fixtures/orders-fastapi` locks, read as the program's libraries.
_LOCKED = {"fastapi": "0.162.0", "starlette": "1.10.0", "pydantic": "2.14.3"}


@pytest.fixture(scope="module")
def libraries(orders_fastapi_env: Path) -> tuple[LibraryRoot, ...]:
    (site,) = (FIXTURES / "orders-fastapi" / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _LOCKED.items())


def _resolved(
    tmp_path: Path,
    libraries: tuple[LibraryRoot, ...],
    files: dict[str, str],
    catalogs: Path | None = None,
) -> DuckDbWorkspace:
    source = tmp_path / "src"
    for name, text in files.items():
        path = source / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    facts = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates="shop",
            version="1",
            classes_dir=source,
            out_dir=facts,
            dependency_archives=libraries,
        )
    )
    module = Document(
        document_id="module",
        relative_path="pyproject.toml",
        module_id="shop",
        language="python",
        sextant_version="0",
        fact_schema_version="0",
        scanner_id="module",
        content_hash="sha256:none",
        origin_entry="shop",
        origin_tier="module_output",
        redaction_set_hash="sha256:none",
    )
    write_fact_file(
        facts / "module.jsonl",
        module,
        [
            ModuleFact(
                document_id="module",
                module_id="shop",
                module_kind="pyproject",
                languages=["python"],
                source_roots=["src"],
                output_dirs=["src"],
                lookup="c3",
                dependency_coordinates=list(_LOCKED),
                dependency_versions=dict(_LOCKED),
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(
        workspace,
        facts,
        YamlCatalogSource(catalogs or catalogs_dir()),
        PythonScanner().capabilities(),
    )
    return workspace


def _handler(name: str, module: str = "app/main") -> str:
    return f"{module}#{name}(sig_"


def _bare(symbol: object) -> str | None:
    """A handler's symbol without its package prefix and its signature digest."""
    if symbol is None:
        return None
    text = str(symbol).removeprefix(_PREFIX)
    return text[: text.index("(sig_") + len("(sig_")] if "(sig_" in text else text


def _response(row: dict) -> str | None:
    """The shape a row's response descriptor names, else its wire type; None where it has none."""
    shape = row["response_shape"]
    if shape is None:
        return None
    described = json.loads(shape)
    return str(described.get("shape_id") or described["wire_type"])


def _rows(workspace: DuckDbWorkspace) -> list[tuple[object, ...]]:
    rows = [
        (
            row["method"],
            row["path"],
            _bare(row["handler"]),
            row["resolution"],
            _response(row),
        )
        for row in workspace.query("endpoints")
        if row["catalog_id"] == "fastapi"
    ]
    return sorted(rows, key=lambda row: tuple("" if part is None else str(part) for part in row))


def _questions(workspace: DuckDbWorkspace, question: str) -> list[dict]:
    return [row for row in workspace.query("open_questions") if row["question"] == question]


_ROUTER = "from fastapi import APIRouter\nrouter = APIRouter()\n"


def test_a_decorated_function_is_a_get_row(tmp_path: Path, libraries):
    """`@router.get("/items")` is a call of `APIRouter.get` whose result is called with the
    function: one GET row, the function its handler, its return annotation its response."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {"main.py": _ROUTER + "@router.get('/items')\ndef items() -> list[str]:\n    return []\n"},
    )

    assert _rows(workspace) == [("GET", "/items", _handler("items"), "resolved", "array")]


def test_app_get_is_a_row_on_the_app(tmp_path: Path, libraries):
    """`FastAPI` defines the same verb methods as `APIRouter` (it hands each to its router)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": (
                "from fastapi import FastAPI\napp = FastAPI()\n"
                "@app.get(path='/health')\ndef health() -> dict[str, str]:\n    return {}\n"
            )
        },
    )

    assert _rows(workspace) == [("GET", "/health", _handler("health"), "resolved", "map")]


def test_api_route_methods_are_one_row_each_upper_cased(tmp_path: Path, libraries):
    """`methods` is read as written, each upper-cased (`{method.upper() for method in
    methods}`): a list gives one row per verb, a repeated verb once."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "@router.api_route('/c', methods=['post', 'PUT', 'Post'])\n"
            + "def cancel() -> str:\n    return ''\n"
        },
    )

    assert _rows(workspace) == [
        ("POST", "/c", _handler("cancel"), "resolved", "string"),
        ("PUT", "/c", _handler("cancel"), "resolved", "string"),
    ]


def test_api_route_without_methods_is_get(tmp_path: Path, libraries):
    """`if methods is None: methods = ["GET"]` (ruling R1): not written and `None` are GET."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "@router.api_route('/a')\ndef a() -> str:\n    return ''\n"
            + "@router.api_route('/b', methods=None)\ndef b() -> str:\n    return ''\n"
        },
    )

    assert _rows(workspace) == [
        ("GET", "/a", _handler("a"), "resolved", "string"),
        ("GET", "/b", _handler("b"), "resolved", "string"),
    ]


def test_empty_methods_is_a_refused_registration(tmp_path: Path, libraries):
    """`methods=[]` is never GET: `generate_unique_id` asserts `route.methods`, so FastAPI
    raises at import (ruling R1). No row; a `refused_registration` question instead."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "@router.api_route('/x', methods=[])\ndef x() -> str:\n    return ''\n"
        },
    )

    assert _rows(workspace) == []
    (question,) = _questions(workspace, "refused_registration")
    assert question["path"] == "/x"
    (candidate,) = json.loads(question["candidates"])
    assert (candidate["reason"], _bare(candidate["handler"])) == ("no_methods", _handler("x"))


def test_add_api_route_names_its_endpoint(tmp_path: Path, libraries):
    """`add_api_route(path, endpoint)` registers in one call: the function is its second
    parameter, positional or named."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "def export() -> list[str]:\n    return []\n"
            + "def purge() -> str:\n    return ''\n"
            + "router.add_api_route('/export', export)\n"
            + "router.add_api_route('/purge', endpoint=purge, methods=['delete'])\n"
        },
    )

    assert _rows(workspace) == [
        ("DELETE", "/purge", _handler("purge"), "resolved", "string"),
        ("GET", "/export", _handler("export"), "resolved", "array"),
    ]


def test_two_route_decorators_are_two_rows_one_handler(tmp_path: Path, libraries):
    """A route decorator's `decorator(func)` returns `func`, so the outer one registers the
    same function the inner one did."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "@router.get('/a')\n@router.get('/b')\ndef either() -> str:\n    return ''\n"
        },
    )

    assert _rows(workspace) == [
        ("GET", "/a", _handler("either"), "resolved", "string"),
        ("GET", "/b", _handler("either"), "resolved", "string"),
    ]


def test_fstring_path_from_a_module_constant_resolves(tmp_path: Path, libraries):
    """`f"{VERSION}/stats"` is a concatenation over a module constant, read through it."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "VERSION = '/v2'\n"
            + "@router.get(f'{VERSION}/stats')\ndef stats() -> str:\n    return ''\n"
        },
    )

    assert _rows(workspace) == [("GET", "/v2/stats", _handler("stats"), "resolved", "string")]


_MODELS = (
    "from pydantic import BaseModel\n"
    "class Out(BaseModel):\n    id: int\n"
    "class Other(BaseModel):\n    name: str\n"
)


def test_response_model_comes_before_the_return_annotation(tmp_path: Path, libraries):
    """A written `response_model` is used as written; the annotation is not looked at."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "models.py": _MODELS,
            "main.py": _ROUTER
            + "from app.models import Out, Other\n"
            + "@router.get('/o', response_model=Out)\ndef o() -> Other:\n    return Other(name='')\n",
        },
    )

    assert _rows(workspace) == [("GET", "/o", _handler("o"), "resolved", "app/models/Out#")]


def test_response_model_none_is_no_response(tmp_path: Path, libraries):
    """`response_model=None` is no response model, over any annotation, and is read: the row
    stays `resolved`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "models.py": _MODELS,
            "main.py": _ROUTER
            + "from app.models import Out\n"
            + "@router.get('/raw', response_model=None)\ndef raw() -> Out:\n    return Out(id=1)\n",
        },
    )

    assert _rows(workspace) == [("GET", "/raw", _handler("raw"), "resolved", None)]


def test_a_response_subclass_return_is_no_response(tmp_path: Path, libraries):
    """`lenient_issubclass(return_annotation, Response)`: `Response` and its subclasses give no
    response model."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "from fastapi import Response\nfrom fastapi.responses import JSONResponse\n"
            + "@router.get('/r')\ndef r() -> Response:\n    return Response()\n"
            + "@router.get('/j')\ndef j() -> JSONResponse:\n    return JSONResponse({})\n"
        },
    )

    assert _rows(workspace) == [
        ("GET", "/j", _handler("j"), "resolved", None),
        ("GET", "/r", _handler("r"), "resolved", None),
    ]


def test_a_none_return_is_no_response(tmp_path: Path, libraries):
    """`-> None` gives `response_model = None` in 0.141 and later (probe §6)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {"main.py": _ROUTER + "@router.delete('/d')\ndef d() -> None:\n    return None\n"},
    )

    assert _rows(workspace) == [("DELETE", "/d", _handler("d"), "resolved", None)]


def test_a_union_with_a_response_is_a_refused_registration(tmp_path: Path, libraries):
    """`-> Item | Response` fails the registration (`FastAPIError: Invalid args for response
    field!`, probe §6): no row, a `refused_registration` question."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "models.py": _MODELS,
            "main.py": _ROUTER
            + "from fastapi import Response\nfrom app.models import Out\n"
            + "@router.get('/u')\ndef u() -> Out | Response:\n    return Response()\n",
        },
    )

    assert _rows(workspace) == []
    (question,) = _questions(workspace, "refused_registration")
    (candidate,) = json.loads(question["candidates"])
    assert (question["method"], question["path"], candidate["reason"]) == (
        "GET",
        "/u",
        "invalid_response_type",
    )


def test_the_return_annotation_is_the_response_when_no_model_is_written(tmp_path: Path, libraries):
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "models.py": _MODELS,
            "main.py": _ROUTER
            + "from app.models import Out\n"
            + "@router.post('/o')\ndef o() -> Out:\n    return Out(id=1)\n",
        },
    )

    assert _rows(workspace) == [("POST", "/o", _handler("o"), "resolved", "app/models/Out#")]


def test_no_model_no_annotation_reads_the_returned_type(tmp_path: Path, libraries):
    """With neither written, the response is the one type the handler returns (N9); two types,
    or none read, leave it unread and the row `partial`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "models.py": _MODELS,
            "main.py": _ROUTER
            + "from app.models import Out, Other\n"
            + "@router.get('/one')\ndef one():\n    return Out(id=1)\n"
            + "@router.get('/two')\ndef two(flag: bool):\n"
            + "    if flag:\n        return Out(id=1)\n    return Other(name='')\n",
        },
    )

    assert _rows(workspace) == [
        ("GET", "/one", _handler("one"), "resolved", "app/models/Out#"),
        ("GET", "/two", _handler("two"), "partial", None),
    ]


def test_a_module_decorator_under_the_route_is_walked_into(tmp_path: Path, libraries):
    """A decorator factory in the module's own code is followed into it (design
    2026-11-06-reading-decorators §6, polar's `version`): its `decorator(endpoint)` returns the
    function, so the route's handler is the function itself."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "def version(*, since=None):\n"
            + "    def decorator(endpoint):\n        return endpoint\n    return decorator\n"
            + "@router.get('/v')\n@version(since=1)\ndef v() -> str:\n    return ''\n"
        },
    )

    assert _rows(workspace) == [("GET", "/v", _handler("v"), "resolved", "string")]


def test_a_returned_response_subclass_is_no_response(tmp_path: Path, libraries):
    """With no annotation, a handler returning a `Response` subclass (`RedirectResponse`,
    `FileResponse`) gives no response model, as the annotation of one would; one beside a
    model names no one type, so the row is `partial`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "models.py": _MODELS,
            "main.py": _ROUTER
            + "from fastapi.responses import FileResponse, RedirectResponse\n"
            + "from app.models import Out\n"
            + "@router.get('/r')\ndef r():\n    return RedirectResponse('/x')\n"
            + "@router.get('/f')\ndef f():\n    return FileResponse('x')\n"
            + "@router.get('/m')\ndef m(flag: bool):\n"
            + "    if flag:\n        return RedirectResponse('/x')\n    return Out(id=1)\n",
        },
    )

    assert _rows(workspace) == [
        ("GET", "/f", _handler("f"), "resolved", None),
        ("GET", "/m", _handler("m"), "partial", None),
        ("GET", "/r", _handler("r"), "resolved", None),
    ]


def test_a_bound_method_is_read_through_its_class(tmp_path: Path, libraries):
    """`self.endpoint` names the method on the instance's class (a bound method): FastAPI calls
    that method. `s.h` on a local object is a value the facts state no source for, so the
    handler is not read: `partial`, with a `not_readable` question."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "class Api:\n"
            + "    def __init__(self, path):\n"
            + "        router.add_api_route(path, self.endpoint)\n"
            + "    def endpoint(self) -> int:\n        return 1\n"
            + "Api('/e')\n"
            + "class S:\n    def h(self) -> str:\n        return ''\n"
            + "def wire():\n    s = S()\n    router.add_api_route('/cm', s.h)\n"
        },
    )

    assert _rows(workspace) == [
        ("GET", "/cm", None, "partial", None),
        ("GET", "/e", "app/main/Api#endpoint(sig_", "resolved", "integer"),
    ]
    (question,) = _questions(workspace, "handler_pass_through")
    ((unread,),) = [json.loads(question["candidates"])[0]["unread"]]
    assert unread["reason"] == "not_readable"


def test_a_verb_list_held_elsewhere_is_read_through_the_walk(tmp_path: Path, libraries):
    """`methods=VERBS` (a module constant) and an element that is a parameter are traced to
    their values: one row per verb read."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "VERBS = ['get', 'post']\n"
            + "@router.api_route('/c', methods=VERBS)\ndef c() -> str:\n    return ''\n"
            + "def make(method):\n"
            + "    @router.api_route('/p', methods=[method])\n"
            + "    def p() -> str:\n        return ''\n"
            + "make('PUT')\nmake('delete')\n"
        },
    )

    rows = [row[:2] for row in _rows(workspace)]
    assert rows == [("DELETE", "/p"), ("GET", "/c"), ("POST", "/c"), ("PUT", "/p")]


def test_a_refused_route_with_an_unread_path_is_still_filed(tmp_path: Path, libraries):
    """FastAPI refuses `methods=[]` whatever the path: a path not read is no reason to drop the
    question."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "def wire(path):\n"
            + "    router.add_api_route(path(), wire, methods=[])\n"
        },
    )

    assert _rows(workspace) == []
    (question,) = _questions(workspace, "refused_registration")
    assert question["path"] is None


def test_a_library_wrapper_under_the_route_is_partial_external(tmp_path: Path, libraries):
    """A library decorator no value model states ends the handler walk: which function runs is
    not read here, so the row keeps its address at `partial` with no handler, and the
    `handler_pass_through` question names the call as `external`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "from functools import singledispatch\n"
            + "@router.get('/w')\n@singledispatch\ndef w() -> str:\n    return ''\n"
        },
    )

    assert _rows(workspace) == [("GET", "/w", None, "partial", None)]
    (question,) = _questions(workspace, "handler_pass_through")
    (candidate,) = json.loads(question["candidates"])
    ((unread,),) = [candidate["unread"]]
    assert unread["reason"] == "external"
    assert "singledispatch" in unread["detail"]


@pytest.mark.declines("fastapi")
@pytest.mark.pins("fluent.root-owner-is-the-declared-type")
def test_a_get_on_anything_but_an_app_or_a_router_derives_nothing(tmp_path: Path, libraries):
    """`get` is a common name: a dict's `get`, and a route-shaped decorator of the module's
    own router class, are calls on no FastAPI type, so they register no route."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": (
                "class Router:\n    def get(self, path):\n        return lambda f: f\n"
                "router = Router()\n"
                "@router.get('/items')\ndef items() -> list[str]:\n    return []\n"
                "CACHE = {}\nCACHE.get('/items')\n"
            )
        },
    )

    assert _rows(workspace) == []


def test_a_function_value_called_past_the_path_cap_is_no_route(tmp_path: Path, libraries):
    """Calling a function value is a `__call__`, the route decorator's terminal too. A call of a
    parameter handed more values than the walk enumerates (polar's `save_fixture(customer)`)
    is on no type the facts name, so it is not known to be a route at all: no row."""
    callers = "".join(f"def c{n}():\n    save_it(print)\n" for n in range(PATH_CAP + 2))
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _ROUTER
            + "@router.get('/x')\ndef x() -> str:\n    return ''\n"
            + "def save_it(save):\n    save(1)\n"
            + callers
        },
    )

    assert _rows(workspace) == [("GET", "/x", _handler("x"), "resolved", "string")]


@pytest.mark.parametrize(
    ("written", "replaced", "named"),
    [
        (
            "{ keyword: methods, absent: GET, case: upper }",
            "{ keyword: methods, absent: GET, case: title }",
            "http_method",
        ),
        (
            "{ keyword: methods, absent: GET, case: upper }",
            "{ keyword: methods, absent: GET, default: GET }",
            "http_method",
        ),
        (
            "response_fallback: { from: handler_return,",
            "response_fallback: { from: handler_body,",
            "response_fallback",
        ),
    ],
)
def test_a_misspelt_verb_list_or_response_fallback_is_refused(
    tmp_path: Path, libraries, written: str, replaced: str, named: str
):
    """A misspelt key would load and read every route as GET, or every response as unread."""
    catalogs = tmp_path / "catalogs"
    shutil.copytree(catalogs_dir(), catalogs)
    text = (catalogs / "fastapi.yml").read_text(encoding="utf-8")
    assert written in text
    (catalogs / "fastapi.yml").write_text(text.replace(written, replaced), encoding="utf-8")

    with pytest.raises(CatalogError) as raised:
        _resolved(tmp_path, libraries, {"main.py": _ROUTER}, catalogs)

    assert named in str(raised.value)


def test_every_jvm_catalog_derives_the_same_rows(tmp_path: Path, fixture_facts: Path):
    """The FastAPI catalog and its value model change nothing a JVM module derives: the JVM
    fixture resolves to the same rows with and without them."""
    without = tmp_path / "catalogs"
    shutil.copytree(catalogs_dir(), without)
    (without / "fastapi.yml").unlink()
    (without / "value-models" / "fastapi.yml").unlink()

    def tables(catalogs: Path, name: str) -> dict[str, list]:
        workspace = DuckDbWorkspace(tmp_path / f"{name}.duckdb")
        resolve(workspace, fixture_facts, YamlCatalogSource(catalogs), FIXTURE_CAPABILITIES)
        return {
            table: sorted(json.dumps(row, sort_keys=True, default=str) for row in rows)
            for table in ("endpoints", "endpoint_metadata", "roots", "open_questions")
            if (rows := workspace.query(table)) is not None
        }

    assert tables(catalogs_dir(), "with") == tables(without, "without")
