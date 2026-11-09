"""`fixtures/orders-fastapi` against FastAPI itself.

The expected routes below are written by hand from the fixture's source, then checked against
what FastAPI prints for it (`fastapi_oracle.py`, run in the fixture's own environment). This
pins the fixture to FastAPI, not to Sextant: the tests below compare Sextant's answers to the
same oracle output (plan 2026-11-08-python-fastapi-inbound Task 10). FastAPI is right where the
two differ.
"""

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES
from reason_guard import outside_the_list, stored_reason_tables, stored_reasons_outside_the_list
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

ORACLE = Path(__file__).with_name("fastapi_oracle.py")
ROOT = FIXTURES / "orders-fastapi"

AUDIT = ("header", "x-audit-user", True)
REQUEST_ID = ("header", "x-request-id", True)

# (methods, path) -> (endpoint, response model, request parameters, body parameter names).
# A parameter is (kind, wire name, required). Every route reached through `orders.router`
# carries `audit` (its constructor's dependencies); the admin routes carry it from the include.
EXPECTED: dict[
    tuple[tuple[str, ...], str], tuple[str, str | None, set[tuple[str, str, bool]], list[str]]
] = {
    (("GET",), "/health"): ("health", "dict[str, str]", {REQUEST_ID}, []),
    (("GET",), "/api/v1/orders/{order_id}"): (
        "get",
        "OrderOut",
        {
            AUDIT,
            ("path", "order_id", True),
            ("query", "verbose", False),
            ("query", "search", False),
            ("header", "x-trace-id", False),
            ("header", "x-api-key", True),
            ("cookie", "session_id", True),
        },
        [],
    ),
    (("POST",), "/api/v1/orders"): ("create", "OrderOut", {AUDIT}, ["body"]),
    (("POST", "PUT"), "/api/v1/orders/{order_id}/cancel"): (
        "cancel",
        "dict[str, str]",
        {AUDIT, ("path", "order_id", True)},
        [],
    ),
    (("GET",), "/api/v1/orders/export"): ("export", "list[str]", {AUDIT}, []),
    (("GET",), "/api/v1/orders/v2/stats"): ("stats", "dict[str, int]", {AUDIT}, []),
    (("GET",), "/api/v1/orders/raw"): ("raw", None, {AUDIT}, []),
    (("GET",), "/api/v1/orders/a"): ("either", "dict[str, str]", {AUDIT}, []),
    (("GET",), "/api/v1/orders/b"): ("either", "dict[str, str]", {AUDIT}, []),
    (("GET",), "/api/v1/orders/paged"): (
        "paged",
        "dict[str, int]",
        {AUDIT, ("query", "limit", False), ("query", "offset", False)},
        [],
    ),
    (("GET",), "/api/v1/admin/users"): ("users", "list[str]", {AUDIT}, []),
    (("DELETE",), "/api/v1/admin/orders/{order_id}"): (
        "purge",
        None,
        {AUDIT, ("path", "order_id", True)},
        [],
    ),
}


def oracle_routes(python: Path) -> list[dict]:
    """FastAPI's route table for the fixture, from a subprocess under the fixture's interpreter."""
    done = subprocess.run(
        [str(python), str(ORACLE), str(ROOT)], check=True, capture_output=True, text=True
    )
    return json.loads(done.stdout)


def parameters_of(route: dict) -> set[tuple[str, str, bool]]:
    kinds = {"query": "query", "header": "header", "cookie": "cookie", "path_params": "path"}
    return {
        (kind, field["alias"], field["required"])
        for key, kind in kinds.items()
        for field in route[key]
    }


@pytest.fixture(scope="module")
def routes(orders_fastapi_env: Path) -> list[dict]:
    return oracle_routes(orders_fastapi_env)


def test_fastapi_serves_the_fixture_routes(routes: list[dict]) -> None:
    served = {(tuple(r["methods"]), r["path"]): r for r in routes}
    assert len(served) == len(routes), "two routes share a method set and path"
    assert set(served) == set(EXPECTED)
    for key, (endpoint, model, parameters, body) in EXPECTED.items():
        route = served[key]
        assert route["endpoint"] == endpoint, key
        assert route["response_model"] == model, key
        assert parameters_of(route) == parameters, key
        assert route["body"] == body, key


# --- Sextant against the same oracle (plan 2 Task 10) -----------------------------------------
#
# The fixture is analysed once, by the real `module analyze` with the fixture's own environment
# as its libraries, and each answer is compared to FastAPI's (the routes, their parameters and
# recipes) or to pydantic's (the wire names of the two models a route reads and writes).

_PREFIX = "sextant-python pypi orders-fastapi 0.1.0 "
STRING = {"nullable": False, "wire_format": None, "wire_type": "string"}
INTEGER = {"nullable": False, "wire_format": None, "wire_type": "integer"}

# FastAPI's response model, as the oracle prints it, in Sextant's wire grammar: a model class is
# its shape, `dict[str, X]` a map of X, `list[X]` an array of X.
RESPONSES: dict[str | None, dict[str, object] | None] = {
    None: None,
    "OrderOut": {"shape_id": "app/schemas/OrderOut#", "wire_type": "object"},
    "dict[str, str]": {"wire_type": "map", "item": STRING},
    "dict[str, int]": {"wire_type": "map", "item": INTEGER},
    "list[str]": {"wire_type": "array", "item": STRING},
}


def _bare(symbol: object) -> str:
    """A symbol without its package prefix and its signature digest."""
    text = str(symbol).removeprefix(_PREFIX)
    return text.split("(sig_")[0]


def _dotted(symbol: object) -> str:
    """A handler symbol as Python names the callable: `app/deps/Paging#<init>` is
    `app.deps.Paging.__init__`."""
    return _bare(symbol).replace("#<init>", "#__init__").replace("/", ".").replace("#", ".")


def _response(shape: object) -> dict[str, object] | None:
    """The parts of a response descriptor the oracle states: the shape a model names, or the
    wire type and item of a container."""
    if shape is None:
        return None
    described = json.loads(str(shape))
    if described.get("shape_id"):
        return {"shape_id": described["shape_id"], "wire_type": described["wire_type"]}
    return {"wire_type": described["wire_type"], "item": described["item"]}


@pytest.fixture(scope="module")
def workspace(orders_fastapi_env: Path, tmp_path_factory: pytest.TempPathFactory):
    out = tmp_path_factory.mktemp("orders-fastapi")
    result = CliRunner().invoke(cli, ["module", "analyze", str(ROOT), "--workspace", str(out)])
    assert result.exit_code == 0, result.output
    opened = DuckDbWorkspace(out / "workspace.duckdb")
    yield opened
    opened.close()


@pytest.fixture(scope="module")
def models(orders_fastapi_env: Path) -> dict[str, dict]:
    done = subprocess.run(
        [
            str(orders_fastapi_env),
            str(ORACLE),
            str(ROOT),
            "--models",
            "app.schemas:OrderIn,OrderOut",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(done.stdout)


def _served(routes: list[dict]) -> dict[tuple[str, str], dict]:
    """The oracle's routes, one per (method, path): a route serving two methods is two rows in
    Sextant, as it is two answers on the wire."""
    return {(method, r["path"]): r for r in routes for method in r["methods"]}


def test_sextant_matches_fastapi_on_the_fixture(workspace, routes, models):
    served = _served(routes)
    endpoints = [r for r in workspace.query("endpoints") if r["catalog_id"] == "fastapi"]

    # Routes: method, path, handler and response model, each one resolved.
    assert {
        (r["method"], r["path"]): (
            _dotted(r["handler"]).rsplit(".", 1)[1],
            _response(r["response_shape"]),
        )
        for r in endpoints
    } == {key: (r["endpoint"], RESPONSES[r["response_model"]]) for key, r in served.items()}
    assert len(endpoints) == len(served)
    assert {r["resolution"] for r in endpoints} == {"resolved"}

    # Parameters: a path variable is the path's own `{name}`, every other one an
    # `endpoint_metadata` row of its kind, wire name and requirement.
    metadata = {
        (r["method"], r["path"], r["kind"], r["name"], r["requirement"] == "required")
        for r in workspace.query("endpoint_metadata")
        if r["direction"] == "inbound"
    }
    expected = set()
    for (method, path), route in served.items():
        for kind, name, required in parameters_of(route):
            if kind == "path":
                assert f"{{{name}}}" in path and required, (method, path, name)
            else:
                expected.add((method, path, kind, name, required))
    assert metadata == expected

    # Request body: the route that reads one takes the model its one body parameter names.
    bodies = {(r["method"], r["path"]): r["request_shape"] for r in endpoints}
    for key, route in served.items():
        if route["body"]:
            assert json.loads(bodies[key])["shape_id"] == "app/schemas/OrderIn#", key
        else:
            assert bodies[key] is None, key

    # Shapes: OrderIn as a request reads it, OrderOut as a response writes it, by wire name.
    fields: dict[str, dict[str, bool]] = {}
    for row in workspace.query("shape_fields"):
        fields.setdefault(row["shape_id"], {})[row["wire_name"]] = row["required"]
    for model, direction in (("OrderIn", "input"), ("OrderOut", "output")):
        wire = fields[f"app/schemas/{model}#"]
        assert sorted(wire) == models[model][direction]["properties"], model
        assert (
            sorted(n for n, required in wire.items() if required)
            == (models[model][direction]["required"])
        ), model

    # Recipes: each callable FastAPI runs for a route is a root at the route's address, beside
    # the handler's own root.
    roots: dict[tuple[str, str], set[str]] = {}
    for r in workspace.query("roots"):
        assert r["root_kind"] == "inbound_endpoint", r
        roots.setdefault((r["method"], r["path"]), set()).add(_dotted(r["handler"]))
    assert roots == {
        key: {f"{r['endpoint_module']}.{r['endpoint']}", *r["recipes"]} for key, r in served.items()
    }

    # `orders.create(...)` in `create` binds to the module's `OrderService()` and reaches it.
    sites = {
        r["ordinal"]
        for r in workspace.query("call_sites")
        if _bare(r["caller"]) == "app/orders#create" and r["name"] == "create"
    }
    bound = [
        (r["owner"], r["resolution"])
        for r in workspace.query("bound_receivers")
        if _bare(r["caller"]) == "app/orders#create" and r["ordinal"] in sites
    ]
    assert bound == [("app/services/OrderService#", "resolved")]
    assert "app/services/OrderService#create" in {
        _bare(r["callee"])
        for r in workspace.query("call_edges")
        if _bare(r["caller"]) == "app/orders#create" and r["callee"] is not None
    }


def test_every_reason_on_the_fixture_is_one_word_of_the_general_list(workspace):
    """The one-reason guard (`tests/application/test_one_reason_list.py`) over this fixture's
    tables, with the guard's own functions; `bound_receivers` carries a reason too."""
    assert stored_reasons_outside_the_list(stored_reason_tables(workspace)) == []
    assert (
        outside_the_list(
            workspace.query("bound_receivers"),
            "bound_receivers",
            "reason",
            found=lambda row: row["owner"] is not None,
            detail="detail",
        )
        == []
    )


# Every row Sextant writes for the fixture, table by table. An extra row fails as a missing one
# does: plan 3 extends this list when it adds the fixture's outbound files. Descriptors are the
# exact JSON the `endpoints` columns store.
MAP_OF_STRING = (
    '{"item":{"nullable":false,"wire_format":null,"wire_type":"string"},'
    '"nullable":false,"wire_format":null,"wire_type":"map"}'
)
MAP_OF_INTEGER = (
    '{"item":{"nullable":false,"wire_format":null,"wire_type":"integer"},'
    '"nullable":false,"wire_format":null,"wire_type":"map"}'
)
ARRAY_OF_STRING = (
    '{"item":{"nullable":false,"wire_format":null,"wire_type":"string"},'
    '"nullable":false,"wire_format":null,"wire_type":"array"}'
)
ORDER_IN = (
    '{"nullable":false,"shape_id":"app/schemas/OrderIn#","wire_format":null,"wire_type":"object"}'
)
ORDER_OUT = (
    '{"nullable":false,"shape_id":"app/schemas/OrderOut#","wire_format":null,"wire_type":"object"}'
)
# `response_model=OrderOut` is read as a class argument, the JVM's class-literal descriptor:
# nullable, with an empty format. FastAPI refuses None there; logged as OI_NULLABLE_KEYWORD.
ORDER_OUT_BY_KEYWORD = (
    '{"nullable":true,"shape_id":"app/schemas/OrderOut#","wire_format":"","wire_type":"object"}'
)

PINNED: dict[str, list[tuple[object, ...]]] = {
    "endpoints": [
        ("DELETE", "/api/v1/admin/orders/{order_id}", "app/admin#purge", "resolved", None, None),
        ("GET", "/api/v1/admin/users", "app/admin#users", "resolved", None, ARRAY_OF_STRING),
        ("GET", "/api/v1/orders/a", "app/orders#either", "resolved", None, MAP_OF_STRING),
        ("GET", "/api/v1/orders/b", "app/orders#either", "resolved", None, MAP_OF_STRING),
        ("GET", "/api/v1/orders/export", "app/orders#export", "resolved", None, ARRAY_OF_STRING),
        ("GET", "/api/v1/orders/paged", "app/orders#paged", "resolved", None, MAP_OF_INTEGER),
        ("GET", "/api/v1/orders/raw", "app/orders#raw", "resolved", None, None),
        ("GET", "/api/v1/orders/v2/stats", "app/orders#stats", "resolved", None, MAP_OF_INTEGER),
        (
            "GET",
            "/api/v1/orders/{order_id}",
            "app/orders#get",
            "resolved",
            None,
            ORDER_OUT_BY_KEYWORD,
        ),
        ("GET", "/health", "app/main#health", "resolved", None, MAP_OF_STRING),
        ("POST", "/api/v1/orders", "app/orders#create", "resolved", ORDER_IN, ORDER_OUT),
        (
            "POST",
            "/api/v1/orders/{order_id}/cancel",
            "app/orders#cancel",
            "resolved",
            None,
            MAP_OF_STRING,
        ),
        (
            "PUT",
            "/api/v1/orders/{order_id}/cancel",
            "app/orders#cancel",
            "resolved",
            None,
            MAP_OF_STRING,
        ),
    ],
    "endpoint_metadata": [
        (
            "DELETE",
            "/api/v1/admin/orders/{order_id}",
            "header",
            "x-audit-user",
            "required",
            "resolved",
            "declared",
        ),
        (
            "GET",
            "/api/v1/admin/users",
            "header",
            "x-audit-user",
            "required",
            "resolved",
            "declared",
        ),
        ("GET", "/api/v1/orders/a", "header", "x-audit-user", "required", "resolved", "declared"),
        ("GET", "/api/v1/orders/b", "header", "x-audit-user", "required", "resolved", "declared"),
        (
            "GET",
            "/api/v1/orders/export",
            "header",
            "x-audit-user",
            "required",
            "resolved",
            "declared",
        ),
        (
            "GET",
            "/api/v1/orders/paged",
            "header",
            "x-audit-user",
            "required",
            "resolved",
            "declared",
        ),
        ("GET", "/api/v1/orders/paged", "query", "limit", "optional", "resolved", "declared"),
        ("GET", "/api/v1/orders/paged", "query", "offset", "optional", "resolved", "declared"),
        ("GET", "/api/v1/orders/raw", "header", "x-audit-user", "required", "resolved", "declared"),
        (
            "GET",
            "/api/v1/orders/v2/stats",
            "header",
            "x-audit-user",
            "required",
            "resolved",
            "declared",
        ),
        (
            "GET",
            "/api/v1/orders/{order_id}",
            "cookie",
            "session_id",
            "required",
            "resolved",
            "declared",
        ),
        (
            "GET",
            "/api/v1/orders/{order_id}",
            "header",
            "x-api-key",
            "required",
            "resolved",
            "declared",
        ),
        (
            "GET",
            "/api/v1/orders/{order_id}",
            "header",
            "x-audit-user",
            "required",
            "resolved",
            "declared",
        ),
        (
            "GET",
            "/api/v1/orders/{order_id}",
            "header",
            "x-trace-id",
            "optional",
            "resolved",
            "declared",
        ),
        ("GET", "/api/v1/orders/{order_id}", "query", "search", "optional", "resolved", "declared"),
        (
            "GET",
            "/api/v1/orders/{order_id}",
            "query",
            "verbose",
            "optional",
            "resolved",
            "declared",
        ),
        ("GET", "/health", "header", "x-request-id", "required", "resolved", "declared"),
        ("POST", "/api/v1/orders", "header", "x-audit-user", "required", "resolved", "declared"),
        (
            "POST",
            "/api/v1/orders/{order_id}/cancel",
            "header",
            "x-audit-user",
            "required",
            "resolved",
            "declared",
        ),
        (
            "PUT",
            "/api/v1/orders/{order_id}/cancel",
            "header",
            "x-audit-user",
            "required",
            "resolved",
            "declared",
        ),
    ],
    "roots": [
        ("DELETE", "/api/v1/admin/orders/{order_id}", "app/admin#purge", "inbound_endpoint"),
        ("DELETE", "/api/v1/admin/orders/{order_id}", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/admin/users", "app/admin#users", "inbound_endpoint"),
        ("GET", "/api/v1/admin/users", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/orders/a", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/orders/a", "app/orders#either", "inbound_endpoint"),
        ("GET", "/api/v1/orders/b", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/orders/b", "app/orders#either", "inbound_endpoint"),
        ("GET", "/api/v1/orders/export", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/orders/export", "app/orders#export", "inbound_endpoint"),
        ("GET", "/api/v1/orders/paged", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/orders/paged", "app/deps/Paging#<init>", "inbound_endpoint"),
        ("GET", "/api/v1/orders/paged", "app/orders#paged", "inbound_endpoint"),
        ("GET", "/api/v1/orders/raw", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/orders/raw", "app/orders#raw", "inbound_endpoint"),
        ("GET", "/api/v1/orders/v2/stats", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/orders/v2/stats", "app/orders#stats", "inbound_endpoint"),
        ("GET", "/api/v1/orders/{order_id}", "app/deps#audit", "inbound_endpoint"),
        ("GET", "/api/v1/orders/{order_id}", "app/deps#get_db", "inbound_endpoint"),
        ("GET", "/api/v1/orders/{order_id}", "app/deps/Authenticator#__call__", "inbound_endpoint"),
        ("GET", "/api/v1/orders/{order_id}", "app/orders#get", "inbound_endpoint"),
        ("GET", "/health", "app/deps#request_id", "inbound_endpoint"),
        ("GET", "/health", "app/main#health", "inbound_endpoint"),
        ("POST", "/api/v1/orders", "app/deps#audit", "inbound_endpoint"),
        ("POST", "/api/v1/orders", "app/orders#create", "inbound_endpoint"),
        ("POST", "/api/v1/orders", "app/services#get_service", "inbound_endpoint"),
        ("POST", "/api/v1/orders/{order_id}/cancel", "app/deps#audit", "inbound_endpoint"),
        ("POST", "/api/v1/orders/{order_id}/cancel", "app/orders#cancel", "inbound_endpoint"),
        ("PUT", "/api/v1/orders/{order_id}/cancel", "app/deps#audit", "inbound_endpoint"),
        ("PUT", "/api/v1/orders/{order_id}/cancel", "app/orders#cancel", "inbound_endpoint"),
    ],
    "shapes": [
        ("app/schemas/OrderIn#", False),
        ("app/schemas/OrderOut#", False),
    ],
    "shape_fields": [
        ("app/schemas/OrderIn#", "customerId", "integer", None, True, False, "partial"),
        ("app/schemas/OrderIn#", "grandTotal", "string", None, True, False, "partial"),
        ("app/schemas/OrderIn#", "note", "string", None, False, True, "resolved"),
        ("app/schemas/OrderOut#", "createdAt", "string", "date-time", True, False, "partial"),
        ("app/schemas/OrderOut#", "orderId", "string", "uuid", True, False, "partial"),
        ("app/schemas/OrderOut#", "state", "string", None, True, False, "partial"),
    ],
}


def _pinned_rows(workspace) -> dict[str, list[tuple[object, ...]]]:
    """Each table's rows as `PINNED` states them, sorted."""
    columns = {
        "endpoints": lambda r: (
            r["method"],
            r["path"],
            _bare(r["handler"]),
            r["resolution"],
            r["request_shape"],
            r["response_shape"],
        ),
        "endpoint_metadata": lambda r: (
            r["method"],
            r["path"],
            r["kind"],
            r["name"],
            r["requirement"],
            r["resolution"],
            r["evidence"],
        ),
        "roots": lambda r: (r["method"], r["path"], _bare(r["handler"]), r["root_kind"]),
        "shapes": lambda r: (r["shape_id"], r["open"]),
        "shape_fields": lambda r: (
            r["shape_id"],
            r["wire_name"],
            r["wire_type"],
            r["wire_format"],
            r["required"],
            r["nullable"],
            r["resolution"],
        ),
    }
    return {
        table: sorted((row_of(r) for r in workspace.query(table)), key=repr)
        for table, row_of in columns.items()
    }


def test_every_fixture_row_is_pinned(workspace):
    assert _pinned_rows(workspace) == {
        table: sorted(rows, key=repr) for table, rows in PINNED.items()
    }
