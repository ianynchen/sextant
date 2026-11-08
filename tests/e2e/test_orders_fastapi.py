"""`fixtures/orders-fastapi` against FastAPI itself.

The expected routes below are written by hand from the fixture's source, then checked against
what FastAPI prints for it (`fastapi_oracle.py`, run in the fixture's own environment). This
pins the fixture to FastAPI, not to Sextant: later tests compare Sextant's answers to the same
oracle output. FastAPI is right where the two differ.
"""

import json
import subprocess
from pathlib import Path

import pytest

from fixture_build import FIXTURES

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
