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

import pytest
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
    # Outermost first (review Minor 10): the caller's test, then the helper's early return.
    ordered = sorted(workspace.query("endpoint_existence"), key=lambda row: row["position"])
    assert [json.loads(str(row["expression"]))["test"] for row in ordered] == [
        "settings.DEBUG and settings.ENV == 'dev'",
        "not os.path.exists('/static')",
    ]


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


def test_a_helper_including_two_routers_takes_each_calls_own_test(tmp_path: Path, libraries):
    """Review Major 1: one helper includes each router it is handed, called once under no test
    and once under one. Each row takes the test of the call that produced it, not of the helper
    as a whole: `/debug/two` is "not evaluated", `/orders/one` is served."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "r1 = APIRouter()\n@r1.get('/one')\ndef one() -> str:\n    return ''\n"
            + "r2 = APIRouter()\n@r2.get('/two')\ndef two() -> str:\n    return ''\n"
            + "def add(a: FastAPI, r: APIRouter, prefix: str) -> None:\n"
            + "    a.include_router(r, prefix=prefix)\n"
            + "add(app, r1, '/orders')\n"
            + "if settings.DEBUG:\n"
            + "    add(app, r2, '/debug')\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [
        ("GET", "/debug/two"),
        ("GET", "/orders/one"),
    ]
    assert _existence(workspace) == {("GET", "/debug/two"): [_open(0, "settings.DEBUG")]}


def test_a_route_helper_called_twice_takes_each_calls_own_test(tmp_path: Path, libraries):
    """The same with a helper that registers the route itself."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "def page() -> str:\n    return ''\n"
            + "def add(a: FastAPI, path: str) -> None:\n"
            + "    a.get(path)(page)\n"
            + "add(app, '/orders')\n"
            + "if settings.DEBUG:\n"
            + "    add(app, '/debug')\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/debug"), ("GET", "/orders")]
    assert _existence(workspace) == {("GET", "/debug"): [_open(0, "settings.DEBUG")]}


_FACTORY = (
    "def page() -> str:\n    return ''\n"
    "def create_app() -> FastAPI:\n"
    "    made = FastAPI()\n"
    "    made.get('/f')(page)\n"
    "    return made\n"
)


def test_a_factory_run_from_the_main_block_is_served(tmp_path: Path, libraries):
    """Ruled 2026-11-09 (review Major 2): `if __name__ == "__main__":` is an entry point, not a
    condition on what exists; its calls run the module as a program. A factory called only
    from it serves its routes wherever the module runs."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import uvicorn\nfrom fastapi import FastAPI\n"
            + _FACTORY
            + "if __name__ == '__main__':\n"
            + "    uvicorn.run(create_app())\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/f")]
    assert _existence(workspace) == {}


def test_a_plain_app_made_in_the_main_block_is_served(tmp_path: Path, libraries):
    """`app = create_app()` written in the module's `__main__` block (the test spelled either
    way round), then run: served."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import uvicorn\nfrom fastapi import FastAPI\n"
            + _FACTORY
            + "if '__main__' == __name__:\n"
            + "    app = create_app()\n"
            + "    uvicorn.run(app)\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/f")]
    assert _existence(workspace) == {}


def test_the_evidence_prefix_is_the_one_the_bean_presence_view_states(tmp_path: Path):
    """Review Minor 11: the text a not-evaluated condition's evidence starts with is one
    constant, and `bean_presence`'s reason in `schema.sql` spells the same words."""
    import sextant
    from sextant.application.resolve.registration_conditions import NOT_EVALUATED

    root = Path(sextant.__file__).parent
    schema = (root / "storage" / "duckdb" / "schema.sql").read_text(encoding="utf-8")
    assert f"'{NOT_EVALUATED}'" in schema


def test_a_helper_called_with_two_prefixes_takes_each_calls_own_test(tmp_path: Path, libraries):
    """Re-review R1-1: the helper's only differing argument is the prefix. The call that gave
    the prefix its words is the row's call: `/b/one` is "not evaluated", `/a/one` served."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "r1 = APIRouter()\n@r1.get('/one')\ndef one() -> str:\n    return ''\n"
            + "def add(prefix: str) -> None:\n"
            + "    app.include_router(r1, prefix=prefix)\n"
            + "add('/a')\n"
            + "if settings.DEBUG:\n"
            + "    add('/b')\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/a/one"), ("GET", "/b/one")]
    assert _existence(workspace) == {("GET", "/b/one"): [_open(0, "settings.DEBUG")]}


def test_a_router_factory_called_with_two_prefixes_takes_each_calls_own_test(
    tmp_path: Path, libraries
):
    """Re-review R1-1: a factory builds a router, registers a route and includes it at the
    prefix it is handed."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "def page() -> str:\n    return ''\n"
            + "def make(prefix: str) -> None:\n"
            + "    r = APIRouter()\n"
            + "    r.get('/x')(page)\n"
            + "    app.include_router(r, prefix=prefix)\n"
            + "make('/a')\n"
            + "if settings.DEBUG:\n"
            + "    make('/b')\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/a/x"), ("GET", "/b/x")]
    assert _existence(workspace) == {("GET", "/b/x"): [_open(0, "settings.DEBUG")]}


def test_a_helper_with_no_arguments_called_both_ways_is_served(tmp_path: Path, libraries):
    """Re-review ruling: the row a no-argument helper registers is the same row from both
    calls, one of them under no test, so it exists wherever the module runs."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "def page() -> str:\n    return ''\n"
            + "def add() -> None:\n"
            + "    app.get('/same')(page)\n"
            + "add()\n"
            + "if settings.DEBUG:\n"
            + "    add()\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/same")]
    assert _existence(workspace) == {}


def test_a_verb_added_to_a_held_list_under_a_test_carries_the_test(tmp_path: Path, libraries):
    """A value a reader takes through a write under a test is served only where the test holds
    (`field_write.guards`): the verb the write adds is a row with that condition, never a
    `resolved` row with none, and the verb written under no test has none."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import os\n"
            + _APP
            + "MORE = ['post']\nVERBS = ['get']\n"
            + "if os.environ.get('W'):\n    VERBS += MORE\n"
            + "@app.api_route('/c', methods=VERBS)\ndef c() -> str:\n    return ''\n"
        },
    )

    assert [(row[0], row[1], row[3]) for row in _rows(workspace)] == [
        ("GET", "/c", "resolved"),
        ("POST", "/c", "resolved"),
    ]
    assert _existence(workspace) == {
        ("POST", "/c"): [_open(0, "os.environ.get('W')")],
    }


_BY_FLAG = (
    "def create_app(database):\n"
    "    made = FastAPI()\n"
    "    @made.get('/health')\n    def health() -> str:\n        return ''\n"
    "    if database:\n"
    "        @made.get('/db')\n        def db() -> str:\n            return ''\n"
    "    return made\n"
)


def test_a_test_on_a_value_each_caller_fixes_is_decided_per_caller(tmp_path: Path, libraries):
    """Ruling R2 of 2026-11-25 (polar's `create_app(database: bool)`): a test that is one name
    is decided where the value walk gives that name exactly one written value on the path.
    One caller passes `True`: the route under the test is served, with no condition from it.
    The caller that passes `False` registers nothing there."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {"main.py": _APP + _BY_FLAG + "a = create_app(True)\nb = create_app(False)\n"},
    )

    assert [(row[0], row[1], row[3]) for row in _rows(workspace)] == [
        ("GET", "/db", "resolved"),
        ("GET", "/health", "resolved"),
    ]
    assert _existence(workspace) == {}


def test_a_registration_under_a_test_decided_false_on_every_path_gives_no_row(
    tmp_path: Path, libraries
):
    """Under a test decided false on every path the registration gives nothing, as under
    `if False:`; `not x`, `x is None` and `x is not None` are decided the same way, and a
    module name with one written value is decided as a parameter is."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _BY_FLAG
            + "a = create_app(False)\n"
            + "OFF = False\nON = 'x'\n"
            + "if OFF:\n    @app.get('/off')\n    def off() -> str:\n        return ''\n"
            + "if not OFF:\n    @app.get('/not-off')\n    def n() -> str:\n        return ''\n"
            + "if OFF is None:\n    @app.get('/none')\n    def o() -> str:\n        return ''\n"
            + "if ON is not None:\n    @app.get('/on')\n    def p() -> str:\n        return ''\n"
            + "if ON is None:\n    @app.get('/gone')\n    def q() -> str:\n        return ''\n"
        },
    )

    assert [(row[0], row[1], row[3]) for row in _rows(workspace)] == [
        ("GET", "/health", "resolved"),
        ("GET", "/not-off", "resolved"),
        ("GET", "/on", "resolved"),
    ]
    assert _existence(workspace) == {}


def test_a_test_on_a_value_not_fixed_stays_not_evaluated(tmp_path: Path, libraries):
    """Not decided, exactly as before (ruling R2): a name the environment gives, a name with
    two written values, a loop variable (redash's `for blueprint in [...]: if blueprint:`),
    and every wider form (`==`, `in`, `and`) though each name in it has one value."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import os\n"
            + _APP
            + "ENV = os.environ.get('E')\n"
            + "TWO = None\nTWO = 'x'\n"
            + "ONE = 'x'\n"
            + "if ENV:\n    @app.get('/env')\n    def e() -> str:\n        return ''\n"
            + "if TWO:\n    @app.get('/two')\n    def t() -> str:\n        return ''\n"
            + "if ONE == 'y':\n    @app.get('/eq')\n    def q() -> str:\n        return ''\n"
            + "if ONE in ['y']:\n    @app.get('/in')\n    def i() -> str:\n        return ''\n"
            + "if ONE and ENV:\n    @app.get('/and')\n    def a() -> str:\n        return ''\n"
            + "for each in [None, app]:\n"
            + "    if each:\n"
            + "        @app.get('/loop')\n        def l() -> str:\n            return ''\n"
        },
    )

    assert _existence(workspace) == {
        ("GET", "/and"): [_open(0, "ONE and ENV")],
        ("GET", "/env"): [_open(0, "ENV")],
        ("GET", "/eq"): [_open(0, "ONE == 'y'")],
        ("GET", "/in"): [_open(0, "ONE in ['y']")],
        ("GET", "/loop"): [_open(0, "each")],
        ("GET", "/two"): [_open(0, "TWO")],
    }


_BY_CONFIG = (
    "from app import config\n"
    + _APP
    + "if config.DOCS:\n    @app.get('/x')\n    def x() -> str:\n        return ''\n"
    + "if not config.DOCS:\n    @app.get('/nx')\n    def nx() -> str:\n        return ''\n"
)


def test_a_star_import_that_binds_the_tested_name_decides_nothing(tmp_path: Path, libraries):
    """A test is decided only on the value the name holds when the test runs. `DOCS = False`,
    then `from .local_config import *` with `DOCS = True` there, leaves `DOCS` true: the star
    replaces the module's own write. Which of the two is written last is not read (OI-565),
    so the name has no one value here and nothing is decided: both routes exist "not
    evaluated". Never the row under `if config.DOCS:` removed."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "local_config.py": "DOCS = True\n",
            "config.py": "DOCS = False\nfrom .local_config import *\n",
            "main.py": _BY_CONFIG,
        },
    )

    assert _existence(workspace) == {
        ("GET", "/nx"): [_open(0, "not config.DOCS")],
        ("GET", "/x"): [_open(0, "config.DOCS")],
    }


@pytest.mark.xfail(strict=True, reason="OI-565: a star import after the write is not the value")
def test_a_name_a_later_star_import_rebinds_is_read_as_the_star_gives_it(tmp_path: Path, libraries):
    """The walk fault behind the rule above, in a plain read: `VERB = 'get'`, then `from
    .local_config import *` with `VERB = 'post'` there. Python serves POST."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "local_config.py": "VERB = 'post'\n",
            "config.py": "VERB = 'get'\nfrom .local_config import *\n",
            "main.py": "from app import config\n"
            + _APP
            + "@app.api_route('/v', methods=[config.VERB])\ndef v() -> str:\n    return ''\n",
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("POST", "/v")]


def test_a_star_import_of_a_module_not_read_decides_nothing(tmp_path: Path, libraries):
    """`try: from .local_config import *` with no `local_config` in the repository: the star
    import may replace the name, and what it binds is not read. Nothing is decided: both
    routes exist "not evaluated", each under its test."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "config.py": "DOCS = False\n"
            "try:\n    from .local_config import *\nexcept ImportError:\n    pass\n",
            "main.py": _BY_CONFIG,
        },
    )

    assert _existence(workspace) == {
        ("GET", "/nx"): [_open(0, "not config.DOCS")],
        ("GET", "/x"): [_open(0, "config.DOCS")],
    }


def test_a_star_import_that_does_not_bind_the_tested_name_leaves_it_decided(
    tmp_path: Path, libraries
):
    """A star import of a module that is read and binds no `DOCS` replaces nothing: the test
    is decided on the one written value."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "local_config.py": "OTHER = True\n",
            "config.py": "DOCS = False\nfrom .local_config import *\n",
            "main.py": _BY_CONFIG,
        },
    )

    assert [(row[0], row[1], row[3]) for row in _rows(workspace)] == [("GET", "/nx", "resolved")]
    assert _existence(workspace) == {}


def test_a_value_read_through_a_return_under_a_test_carries_the_test(tmp_path: Path, libraries):
    """A value a reader takes through a `return` under a test that is not decided is served
    only where the test holds (`method_return.guards`), as one read through a write under a
    test is: never a `resolved` row with no condition."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": "import os\n"
            + _APP
            + "def verbs(w):\n    if w:\n        return ['get', 'post']\n    return ['get']\n"
            + "@app.api_route('/e', methods=verbs(os.getenv('W')))\ndef e() -> str:\n"
            + "    return ''\n"
        },
    )

    assert [(row[0], row[1], row[3]) for row in _rows(workspace)] == [
        ("GET", "/e", "resolved"),
        ("POST", "/e", "resolved"),
    ]
    existence = _existence(workspace)
    assert existence[("POST", "/e")] == [_open(0, "w")]
    # `GET` is in both arms: it is served either way, and carries both arms' tests where it
    # should carry none (OI-564, the same for a write in both arms).
    assert existence[("GET", "/e")] == [_open(0, "w", holds=False), _open(1, "w")]


_MAY_BE_REPLACED = (
    "DOCS = False\ntry:\n    from .local_config import *\nexcept ImportError:\n    pass\n"
)
_X = "def x() -> str:\n    return ''\n"
_THROUGH = {
    "a parameter": (
        (
            "def create_app(docs):\n"
            "    made = FastAPI()\n"
            "    if docs:\n"
            "        made.add_api_route('/x', x)\n"
            "    return made\n"
            "made = create_app(config.DOCS)\n"
        ),
        "docs",
    ),
    "a local name": (
        (
            "def reg():\n"
            "    docs = config.DOCS\n"
            "    if docs:\n"
            "        app.add_api_route('/x', x)\n"
            "reg()\n"
        ),
        "docs",
    ),
    "a second module name": (
        "SHOW = config.DOCS\nif SHOW:\n    app.add_api_route('/x', x)\n",
        "SHOW",
    ),
    "a return": (
        (
            "def docs():\n    return config.DOCS\n"
            "def reg():\n"
            "    shown = docs()\n"
            "    if shown:\n"
            "        app.add_api_route('/x', x)\n"
            "reg()\n"
        ),
        "shown",
    ),
    "a parameter of a parameter": (
        (
            "def inner(shown):\n"
            "    if shown:\n"
            "        app.add_api_route('/x', x)\n"
            "def outer(docs):\n    inner(docs)\n"
            "outer(config.DOCS)\n"
        ),
        "shown",
    ),
}


@pytest.mark.parametrize("through", sorted(_THROUGH))
def test_a_value_a_star_import_can_replace_decides_nothing_at_any_depth(
    tmp_path: Path, libraries, through: str
):
    """Ruling R10 of 2026-11-25: `DOCS = False`, then `try: from .local_config import *` with
    no `local_config` in the repository. The deployment's file may give `DOCS` another value,
    so a test whose value comes from that write is not decided, however far the value
    travelled to the test: the row exists, "not evaluated". Never the row removed."""
    body, test = _THROUGH[through]
    workspace = _resolved(
        tmp_path,
        libraries,
        {"config.py": _MAY_BE_REPLACED, "main.py": "from app import config\n" + _APP + _X + body},
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/x")]
    assert _existence(workspace) == {("GET", "/x"): [_open(0, test)]}


@pytest.mark.parametrize("through", sorted(_THROUGH))
def test_a_value_no_star_import_can_replace_is_decided_at_any_depth(
    tmp_path: Path, libraries, through: str
):
    """The controls of R10: with no star import the same test is decided on the one written
    value. `True`: the row, no condition. `False`: no row. A star import of a module that is
    read and does not bind the name replaces nothing."""
    if through == "a return":
        pytest.skip("a value a local name takes from a call is no test value (never decided)")
    body, _ = _THROUGH[through]
    main = "from app import config\n" + _APP + _X + body

    served = _resolved(tmp_path / "on", libraries, {"config.py": "DOCS = True\n", "main.py": main})
    assert [(row[0], row[1], row[3]) for row in _rows(served)] == [("GET", "/x", "resolved")]
    assert _existence(served) == {}

    off = _resolved(tmp_path / "off", libraries, {"config.py": "DOCS = False\n", "main.py": main})
    assert _rows(off) == []

    unbound = _resolved(
        tmp_path / "unbound",
        libraries,
        {
            "local_config.py": "OTHER = True\n",
            "config.py": "DOCS = False\nfrom .local_config import *\n",
            "main.py": main,
        },
    )
    assert _rows(unbound) == []


def test_a_name_star_imports_alone_give_is_decided_on_the_last_that_gives_it(
    tmp_path: Path, libraries
):
    """A name a module takes by star imports alone has the value of the last star that gives
    it (Python's rule): decided. Where that source's own value can be replaced, or a star of
    the module is not read, the name has no one value this reading can state: not decided."""
    served = [("GET", "/x", "resolved")]
    one = _resolved(
        tmp_path / "one",
        libraries,
        {"base.py": "DOCS = True\n", "config.py": "from .base import *\n", "main.py": _BY_CONFIG},
    )
    assert [(row[0], row[1], row[3]) for row in _rows(one)] == served
    assert _existence(one) == {}

    two = _resolved(
        tmp_path / "two",
        libraries,
        {
            "base.py": "DOCS = False\n",
            "more.py": "DOCS = True\n",
            "config.py": "from .base import *\nfrom .more import *\n",
            "main.py": _BY_CONFIG,
        },
    )
    assert [(row[0], row[1], row[3]) for row in _rows(two)] == served
    assert _existence(two) == {}

    both = {
        ("GET", "/nx"): [_open(0, "not config.DOCS")],
        ("GET", "/x"): [_open(0, "config.DOCS")],
    }
    absent = "try:\n    from .local import *\nexcept ImportError:\n    pass\n"
    replaced = _resolved(
        tmp_path / "replaced",
        libraries,
        {
            "base.py": "DOCS = True\n" + absent,
            "config.py": "from .base import *\n",
            "main.py": _BY_CONFIG,
        },
    )
    assert _existence(replaced) == both

    unread = _resolved(
        tmp_path / "unread",
        libraries,
        {
            "base.py": "DOCS = True\n",
            "config.py": "from .base import *\n" + absent,
            "main.py": _BY_CONFIG,
        },
    )
    assert _existence(unread) == both

    library = _resolved(
        tmp_path / "library",
        libraries,
        {
            "base.py": "DOCS = True\n",
            "config.py": "from .base import *\nfrom fastapi import *\n",
            "main.py": _BY_CONFIG,
        },
    )
    assert _existence(library) == both


def test_a_plain_read_of_a_value_a_star_import_can_replace_is_not_changed(
    tmp_path: Path, libraries
):
    """Only the step that decides a test reads the mark (R10): a verb read from a name a star
    import can replace is the written value, as before (the fault of that read is OI-565)."""
    absent = "try:\n    from .local import *\nexcept ImportError:\n    pass\n"
    main = (
        "from app import config\n"
        + _APP
        + "@app.api_route('/v', methods=[config.VERB])\ndef v() -> str:\n    return ''\n"
    )
    own = _resolved(
        tmp_path / "own", libraries, {"config.py": "VERB = 'put'\n" + absent, "main.py": main}
    )
    assert [(row[0], row[1], row[3]) for row in _rows(own)] == [("PUT", "/v", "resolved")]
    assert _existence(own) == {}

    taken = _resolved(
        tmp_path / "taken",
        libraries,
        {
            "base.py": "VERB = 'put'\n",
            "config.py": "from .base import *\n" + absent,
            "main.py": main,
        },
    )
    assert [(row[0], row[1], row[3]) for row in _rows(taken)] == [("PUT", "/v", "resolved")]
    assert _existence(taken) == {}
