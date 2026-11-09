"""A FastAPI route, include or mount registered under a test the analysis cannot decide exists
where the deployment makes the test go its way: its existence is "not evaluated" (OI-368; the
user's ruling of 2026-10-23, "deployment decides what it can set"; plan
2026-11-08-python-fastapi-inbound Task 10b, design approved 2026-11-09).

The tests a registration runs under are its own call's (`call_site.guards`), its function's
callers' where every caller is under one (a fixpoint over the call graph), and those of every
include or mount its router is served through. Each is a `test` condition in
`endpoint_existence`, one row per (endpoint row, condition, environment), keyed by the row: no
test is evaluated, and the row's address and resolution do not change. A test the language
decides (a constant, `TYPE_CHECKING`) keeps its decided answer and writes nothing.

Each test writes a small FastAPI program and runs the real scanner and pipeline with the shipped
catalogs (`test_fastapi_routes._resolved`)."""

import json
from pathlib import Path

import test_fastapi_routes
from test_fastapi_routes import _resolved, _rows

libraries = test_fastapi_routes.libraries

_APP = "from fastapi import APIRouter, FastAPI\napp = FastAPI()\n"
_SETTINGS = (
    "class Settings:\n    ENV: str = 'dev'\n    DEBUG: bool = False\nsettings = Settings()\n"
)
_NOT_EVALUATED = "a condition this analysis does not evaluate: "


def _existence(workspace) -> dict[tuple[object, object], list[tuple[object, ...]]]:
    """Each row's conditions, as (route, test, holds in code, verdict, resolution, evidence),
    by (method, path), from the rows bound to a live endpoint row."""
    live = {row["row_id"]: (row["method"], row["path"]) for row in workspace.query("endpoints")}
    found: dict[tuple[object, object], list[tuple[object, ...]]] = {}
    for row in workspace.query("endpoint_existence"):
        assert row["row_id"] in live, row
        assert (row["method"], row["path"]) == live[row["row_id"]], row
        assert row["kind"] == "test"
        assert row["environment"] == "default"
        expression = json.loads(str(row["expression"]))
        found.setdefault(live[row["row_id"]], []).append(
            (
                row["route"],
                expression["test"],
                expression["holds"],
                row["holds"],
                row["resolution"],
                row["evidence"],
            )
        )
    return {key: sorted(value) for key, value in found.items()}


def _open(route: int, test: str, holds: bool = True) -> tuple[object, ...]:
    return (route, test, holds, "unresolved", "unresolved", f"{_NOT_EVALUATED}`{test}`")


def test_a_mount_under_a_settings_condition_is_not_evaluated(tmp_path: Path, libraries):
    """polar's shape: a sub-application mounted only where a settings value says so. Every
    route under the mount is "not evaluated", the test stated as the code writes it; the
    outer app's own route is not under it, and the rows themselves are unchanged."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "back = FastAPI()\n"
            + "@back.get('/users')\ndef users() -> str:\n    return ''\n"
            + "@app.get('/health')\ndef health() -> str:\n    return ''\n"
            + "if settings.ENV != 'production':\n"
            + "    app.mount('/backoffice', app=back)\n"
        },
    )

    assert [(row[0], row[1], row[3]) for row in _rows(workspace)] == [
        ("GET", "/backoffice/users", "resolved"),
        ("GET", "/health", "resolved"),
    ]
    assert _existence(workspace) == {
        ("GET", "/backoffice/users"): [_open(0, "settings.ENV != 'production'")],
    }


def test_a_route_under_a_decided_test_keeps_its_answer(tmp_path: Path, libraries):
    """A constant test and `TYPE_CHECKING` are decided by the language: the route under the arm
    that runs exists, and no condition is written."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import typing\n"
            + _APP
            + "if True:\n"
            + "    @app.get('/always')\n    def always() -> str:\n        return ''\n"
            + "if not typing.TYPE_CHECKING:\n"
            + "    @app.get('/running')\n    def running() -> str:\n        return ''\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [
        ("GET", "/always"),
        ("GET", "/running"),
    ]
    assert _existence(workspace) == {}


def test_a_version_test_in_the_modules_own_code_is_not_evaluated(tmp_path: Path, libraries):
    """`sys.version_info` is decided only where a LIBRARY is read for a known Python
    (`imports.live_arm`); the module's own code runs on whichever Python the deployment starts,
    so both arms are read and each route is "not evaluated" under the test."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import sys\n"
            + _APP
            + "if sys.version_info >= (3, 8):\n"
            + "    @app.get('/new')\n    def new() -> str:\n        return ''\n"
            + "else:\n"
            + "    @app.get('/old')\n    def old() -> str:\n        return ''\n"
        },
    )

    assert _existence(workspace) == {
        ("GET", "/new"): [_open(0, "sys.version_info >= (3, 8)")],
        ("GET", "/old"): [_open(0, "sys.version_info >= (3, 8)", holds=False)],
    }


def test_routes_under_a_not_evaluated_include_inherit_it(tmp_path: Path, libraries):
    """The include is under the test; the routes are written unconditionally on the router in
    another file. Each served through the include inherits the include's test, and a router
    included twice (once under a test, once not) is conditional on the one serving place
    only. A nested include under a second test carries both."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "orders.py": "from fastapi import APIRouter\nrouter = APIRouter()\n"
            + "@router.get('/x')\ndef x() -> str:\n    return ''\n",
            "debug.py": "from fastapi import APIRouter\nrouter = APIRouter()\n"
            + "@router.get('/y')\ndef y() -> str:\n    return ''\n",
            "main.py": _APP
            + _SETTINGS
            + "from app import debug, orders\n"
            + "inner = APIRouter()\n"
            + "app.include_router(orders.router, prefix='/v1')\n"
            + "if settings.DEBUG:\n"
            + "    app.include_router(orders.router, prefix='/debug')\n"
            + "    if settings.ENV == 'dev':\n"
            + "        inner.include_router(debug.router, prefix='/inner')\n"
            + "    app.include_router(inner, prefix='/d')\n",
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [
        ("GET", "/d/inner/y"),
        ("GET", "/debug/x"),
        ("GET", "/v1/x"),
    ]
    assert _existence(workspace) == {
        ("GET", "/debug/x"): [_open(0, "settings.DEBUG")],
        ("GET", "/d/inner/y"): [_open(0, "settings.DEBUG"), _open(0, "settings.ENV == 'dev'")],
    }


def test_a_registration_in_a_helper_run_only_under_a_test_inherits_it(tmp_path: Path, libraries):
    """mealie's shape: the helper that registers the routes is called only under a test, and
    returns early under a test of its own. A function every call of which is under a test runs
    only there; its own early return guards what follows it."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import os\n"
            + _APP
            + _SETTINGS
            + "def page() -> str:\n    return ''\n"
            + "def mount_pages(target: FastAPI) -> None:\n"
            + "    if not os.path.exists('/static'):\n"
            + "        return\n"
            + "    target.get('/page')(page)\n"
            + "def routers() -> None:\n"
            + "    if settings.DEBUG and settings.ENV == 'dev':\n"
            + "        mount_pages(app)\n"
            + "routers()\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/page")]
    assert _existence(workspace) == {
        ("GET", "/page"): [
            _open(0, "not os.path.exists('/static')", holds=False),
            _open(0, "settings.DEBUG and settings.ENV == 'dev'"),
        ],
    }


def test_an_unconditional_route_is_unchanged(tmp_path: Path, libraries):
    """A route under no test, and one registered by a helper that some call runs under no test,
    exist wherever the module runs: no condition is written for either."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "def page() -> str:\n    return ''\n"
            + "def register(target: FastAPI) -> None:\n"
            + "    target.get('/page')(page)\n"
            + "@app.get('/health')\ndef health() -> str:\n    return ''\n"
            + "register(app)\n"
            + "if settings.DEBUG:\n"
            + "    register(app)\n"
        },
    )

    assert [(row[0], row[1], row[3]) for row in _rows(workspace)] == [
        ("GET", "/health", "resolved"),
        ("GET", "/page", "resolved"),
    ]
    assert _existence(workspace) == {}
