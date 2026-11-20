"""`fixtures/orders-flask` against Flask itself.

The expected rows below are written by hand from the fixture's source, then checked against what
Flask prints for it (`flask_oracle.py`, run in the fixture's own environment) and against what
Sextant derives. Flask is right where they differ.

Two exclusions, both Flask's own and not routes the program wrote: the automatic HEAD (werkzeug
adds it to a GET rule) and OPTIONS (Flask adds it to every rule) methods, and the `static`
endpoint every app registers. Sextant's declared-method rows are a subset of `url_map` rows
(`scripts/probes/flask_rules.md`), so the comparison drops those methods and that endpoint.
"""

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

ORACLE = Path(__file__).with_name("flask_oracle.py")
ROOT = FIXTURES / "orders-flask"
AUTOMATIC = {"HEAD", "OPTIONS"}

# (method, path) -> handler, written from the fixture's source: `app/main.py` registers the
# blueprints, `orders.py` has its own prefix, `admin.py` is overridden to `/admin/` and nests
# `reports.py`, `public.py` is registered twice, `legacy.py` under `url_prefix=""`.
EXPECTED: dict[tuple[str, str], str] = {
    ("GET", "/health"): "app.main.health",
    ("GET", "/files/<path:rest>"): "app.main.download",
    ("GET", "/ping"): "app.main.ping",
    ("POST", "/webhooks/orders"): "app.main.order_webhook",
    ("PUT", "/webhooks/orders"): "app.main.order_webhook",
    ("GET", "/orders/<int:order_id>"): "app.orders.get_order",
    ("POST", "/orders/"): "app.orders.create_order",
    ("POST", "/orders/<int:order_id>/cancel"): "app.orders.cancel_order",
    ("PUT", "/orders/<int:order_id>/cancel"): "app.orders.cancel_order",
    ("GET", "/orders/export"): "app.orders.export_orders",
    ("GET", "/admin/users"): "app.admin.list_users",
    ("DELETE", "/admin/orders/<int:order_id>"): "app.admin.purge_order",
    ("GET", "/admin/reports/daily"): "app.reports.daily",
    ("GET", "/v1/catalog"): "app.public.catalog",
    ("GET", "/v2/catalog"): "app.public.catalog",
    ("GET", "/status"): "app.legacy.status",
}

# (method, path, kind, wire name, requirement): `.get` states none (A3), a subscript is required.
READS = {
    ("GET", "/health", "header", "X-Request-Id", None),
    ("GET", "/files/<path:rest>", "query", "inline", None),
    ("POST", "/webhooks/orders", "header", "X-Webhook-Source", None),
    ("PUT", "/webhooks/orders", "header", "X-Webhook-Source", None),
    ("GET", "/orders/<int:order_id>", "query", "verbose", None),
    ("GET", "/orders/<int:order_id>", "header", "X-Api-Key", "required"),
    ("GET", "/orders/<int:order_id>", "cookie", "session_id", None),
    ("POST", "/orders/", "param", "source", None),
    ("POST", "/orders/<int:order_id>/cancel", "query", "reason", "required"),
    ("PUT", "/orders/<int:order_id>/cancel", "query", "reason", "required"),
    ("GET", "/orders/export", "header", "X-Trace-Id", None),
    ("GET", "/admin/reports/daily", "query", "day", None),
}


@pytest.fixture(scope="module")
def served(orders_flask_env: Path) -> dict[tuple[str, str], str]:
    done = subprocess.run(
        [str(orders_flask_env), str(ORACLE), str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    return {
        (method, r["path"]): f"{r['handler_module']}.{r['handler']}"
        for r in json.loads(done.stdout)
        if r["endpoint"] != "static"
        for method in r["methods"]
        if method not in AUTOMATIC
    }


@pytest.fixture(scope="module")
def workspace(orders_flask_env: Path, tmp_path_factory: pytest.TempPathFactory):
    # `orders_flask_env` is requested for ordering only: the venv must exist before analysis reads
    # the fixture's libraries from it.
    out = tmp_path_factory.mktemp("orders-flask")
    result = CliRunner().invoke(cli, ["module", "analyze", str(ROOT), "--workspace", str(out)])
    assert result.exit_code == 0, result.output
    opened = DuckDbWorkspace(out / "workspace.duckdb")
    yield opened
    opened.close()


def test_flask_serves_the_fixture_routes(served):
    assert served == EXPECTED


def test_sextant_matches_flask_on_the_fixture(workspace, served):
    rows = [r for r in workspace.query("endpoints") if r["catalog_id"] == "flask"]
    assert {r["resolution"] for r in rows} == {"resolved"}
    derived = {
        (r["method"], r["path"]): str(r["handler"])
        .split(" 0.1.0 ")[1]
        .split("(sig_")[0]
        .replace("#", ".")
        .replace("/", ".")
        for r in rows
    }
    assert len(derived) == len(rows)
    assert derived == served


def test_sextant_reads_the_requests_as_written(workspace):
    reads = {
        (r["method"], r["path"], r["kind"], r["name"], r["requirement"])
        for r in workspace.query("endpoint_metadata")
        if r["direction"] == "inbound"
    }
    assert reads == READS
