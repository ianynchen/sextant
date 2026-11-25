"""`fixtures/orders-django` against Django itself.

The expected rows below are written by hand from the fixture's source, then checked against what
Django serves for it (`django_oracle.py`, run in the fixture's own environment) and against what
Sextant derives. Django is right where they differ. The oracle walks the real resolver
(`get_resolver().url_patterns`, routes joined by `URLResolver._join_route`) and measures each
pattern's methods by BEHAVIOUR: it calls the callback through `RequestFactory` once for each of
GET, HEAD, POST, PUT, PATCH, DELETE and OPTIONS, with a signed-in stub user and plausible values
for the route's parameters, and a method is allowed when the answer is not 405. No shape needed
a fallback to inspection; inspection only NAMES a class row's handler (the method each verb
reaches through the class's MRO).

THE COMPARISON CONVENTION.

- Paths. A `path` route is published as `/` + Django's joined route text, converters as
  written. A `re_path` read exactly is a set of Sextant rows, each of which must be served by the
  oracle's joined regex (`re.fullmatch` of the row with every `<name>` replaced by `5`), while
  its near-miss (the same text plus `x`) must not be. A route expression not read exactly is
  one `pattern` row and compares as text.
- Methods. Sextant's rows for a (path, handler) are Django's allowed set MINUS the framework's
  automatic answers the catalog states it never publishes: `OPTIONS` on a class view (from
  `View.options`) and the automatic `HEAD` of a class view with `get` and no `head` (from
  `View.setup`). A function view answers both itself, so nothing is subtracted there. An
  any-method row (method NULL) matches an allowed set of every method measured; a class view
  that answers every method is the `dispatch` override, and its row's handler is `dispatch`.
- Stated boundaries. Rows Sextant publishes at `partial`, and the questions it files, are
  compared separately (`test_the_stated_boundaries_are_published_as_today`), each named there.
- Not evaluated. The `settings.DEBUG` branch is decided by the deployment: the oracle runs with
  DEBUG on and off, the one route that differs is `/debug/echo/`, and Sextant publishes that row
  with an `endpoint_existence` condition `settings.DEBUG` that holds `unresolved`.

Request reads (plan 6, Task 7) are not built: Sextant publishes no request metadata for Django,
and the fixture's `request.GET.get(...)` reads are not rows here.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

ORACLE = Path(__file__).with_name("django_oracle.py")
ROOT = FIXTURES / "orders-django"
EVERY = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
VIEW_OPTIONS = "django.views.generic.base.View.options"

# (method, path) -> handler, written from the fixture's source; method None is the any-method row.
# `shop/urls.py` is the root: `orders/` includes `shop.orders.urls` by name (with a namespace),
# which includes `shop.orders.item_urls` (three levels); `api/` includes the module object
# `api_urls`, whose `urlpatterns = v1 + v2` mixes `path` and `re_path`; `account/` a local list;
# one help list under `help/` (as a `(list, app_name)` tuple) and `support/`; `^legacy/` is a
# `re_path` prefix; `+=` and `.extend` add `ping/` and `exports/orders/`.
EXPECTED: dict[tuple[str | None, str], str] = {
    (None, "/health/"): "shop.views.health",
    (None, "/catalog/"): "shop.views.catalog",  # cache_page(60)(view)
    ("GET", "/products/<slug:slug>/"): "shop.views.product",
    ("GET", "/receipts/<uuid:token>/"): "shop.views.receipt",  # require_safe
    ("HEAD", "/receipts/<uuid:token>/"): "shop.views.receipt",
    ("GET", "/files/<path:rest>"): "shop.views.download",
    ("GET", "/orders/<int:order_id>/"): "shop.orders.views.OrderDetail.get",
    ("DELETE", "/orders/<int:order_id>/"): "shop.orders.views.OrderDetail.delete",
    ("GET", "/orders/<int:order_id>/items/"): "shop.base.JsonView.get",  # inherited
    ("POST", "/orders/<int:order_id>/items/"): "shop.base.JsonView.post",
    ("GET", "/orders/mine/"): "shop.orders.views.MyOrders.get",  # LoginRequiredMixin
    ("GET", "/orders/history/"): "shop.orders.views.OrderHistory.get",  # login_required(as_view)
    (None, "/orders/status/"): "shop.orders.views.StatusProbe.dispatch",
    ("GET", "/orders/shipping/"): "django.views.generic.base.TemplateView.get",
    ("GET", "/api/v1/cart/"): "shop.views.cart",  # require_http_methods(["GET", "POST"])
    ("POST", "/api/v1/cart/"): "shop.views.cart",
    (None, "/api/v1/status/"): "shop.views.health",  # a `path` prefix over a `re_path` child
    ("GET", "/api/v2/cart/"): "shop.views.cart",
    ("POST", "/api/v2/cart/"): "shop.views.cart",
    (None, "/account/profile/"): "shop.views.profile",  # login_required
    (None, "/account/wishlist/"): "shop.views.wishlist",  # login_required(login_url=...)
    ("POST", "/account/password/"): "shop.views.change_password",  # login_required + require_POST
    (None, "/help/faq/"): "shop.views.faq",
    (None, "/support/faq/"): "shop.views.faq",
    ("POST", "/webhooks/stripe/"): "shop.views.stripe_webhook",  # csrf_exempt(view)
    ("GET", "/about/"): "django.views.generic.base.TemplateView.get",  # as_view(template_name=)
    (None, "/legacy/orders/<order_id>/"): "shop.views.legacy_order",
    (None, "/legacy/track"): "shop.views.ping",  # `^track/?$`: two rows
    (None, "/legacy/track/"): "shop.views.ping",
    ("GET", "/legacy/invoices/<number>"): "shop.views.invoice",  # `(\.pdf)?`: rows doubled
    ("GET", "/legacy/invoices/<number>.pdf"): "shop.views.invoice",
    (None, "/ping/"): "shop.views.ping",
    (None, "/exports/orders/"): "shop.views.export_orders",  # @audited: a wrapper that calls it
    (None, "/promo/current/"): "shop.views.promotions",  # include(tracked(...)): a copy, read
    (None, "/debug/echo/"): "shop.views.debug_echo",  # under `if settings.DEBUG:`
}

# STATED BOUNDARIES: Django's route, Sextant's row (method, path, handler) at `partial`.
# - `http_method_names = ["get"]` on a class: the list is a value not read, so the class's rows
#   are `partial`, and Django serves GET alone;
# - `include(partner_feeds.urls)`, a property no read follows: the mount's router argument
#   reads as no value, so the call is published as a route with no handler at `partial`
#   (design 2026-11-23 §9b, a known limit), and the route the property builds is in no list
#   the root reaches: under the `<prefix>` hole, with a `mount_prefix` question at the row.
BOUNDARIES = {
    "orders/<int:order_id>/items/archived/": {
        ("GET", "/orders/<int:order_id>/items/archived/", "shop.orders.views.ArchivedItems.get"),
        ("POST", "/orders/<int:order_id>/items/archived/", "shop.orders.views.ArchivedItems.post"),
    },
    "partners/feed/": {
        (None, "/<prefix>feed/", "shop.integrations.PartnerFeeds.feed"),
        (None, "/partners/", None),
    },
}
# The `/partners/` row names no handler, so which methods it answers is not read: its
# `not_read` question names the registration (ruled 2026-11-25, R4).
QUESTIONS = {
    ("mount_prefix", "/<prefix>feed/"),
    ("not_read", "/partners/"),
}
# A route expression not read exactly (`(a|b)`): one `pattern` row, compared as text.
PATTERN_ROUTE = "^legacy/(shelf|books)/$"


def _oracle(interpreter: Path, *, debug: bool) -> list[dict]:
    environment = {**os.environ, "SHOP_DEBUG": "1" if debug else "0"}
    done = subprocess.run(
        [str(interpreter), "-I", str(ORACLE), str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _derived(pattern: dict) -> dict[str | None, str]:
    """The rows Django's answer predicts for one pattern, by the convention: method -> handler."""
    allowed = set(pattern["allowed"])
    methods = pattern.get("class_methods")
    if methods is None:
        return (
            {None: pattern["handler"]}
            if allowed == EVERY
            else dict.fromkeys(allowed, pattern["handler"])
        )
    if allowed == EVERY:
        return {None: methods["dispatch"]}
    if methods.get("options") == VIEW_OPTIONS:
        allowed.discard("OPTIONS")
    if "head" not in methods:
        allowed.discard("HEAD")
    return {method: methods[method.lower()] for method in allowed}


def _serves(pattern: dict, path: str) -> bool:
    if pattern["kind"] == "route":
        return path == "/" + pattern["route"]
    concrete = re.sub(r"<[^>]+>", "5", path.removeprefix("/"))
    regex = re.compile(pattern["regex"])
    return bool(regex.fullmatch(concrete)) and not regex.fullmatch(concrete + "x")


@pytest.fixture(scope="module")
def served(orders_django_env: Path) -> list[dict]:
    return _oracle(orders_django_env, debug=True)


@pytest.fixture(scope="module")
def workspace(orders_django_env: Path, tmp_path_factory: pytest.TempPathFactory):
    # `orders_django_env` is requested for ordering only: the venv must exist before analysis
    # reads the fixture's libraries from it.
    out = tmp_path_factory.mktemp("orders-django")
    result = CliRunner().invoke(cli, ["module", "analyze", str(ROOT), "--workspace", str(out)])
    assert result.exit_code == 0, result.output
    opened = DuckDbWorkspace(out / "workspace.duckdb")
    yield opened
    opened.close()


def _handler(symbol: object) -> str | None:
    """`sextant-python pypi <dist> <version> a/b/C#m(sig_...)` as `a.b.C.m`."""
    if symbol is None:
        return None
    return str(symbol).split(" ")[4].split("(sig_")[0].replace("#", ".").replace("/", ".")


def _rows(workspace: DuckDbWorkspace) -> list[dict]:
    return [r for r in workspace.query("endpoints") if r["catalog_id"] == "django"]


def test_django_serves_the_expected_rows(served):
    """Every expected row is served by exactly one Django pattern, with the convention's methods
    and handler; and every pattern outside the boundaries predicts only expected rows."""
    checked = [p for p in served if p["route"] not in BOUNDARIES and p["route"] != PATTERN_ROUTE]
    for (method, path), handler in EXPECTED.items():
        (pattern,) = [p for p in checked if _serves(p, path)]
        assert _derived(pattern).get(method) == handler, (method, path)
    for pattern in checked:
        predicted = _derived(pattern)
        rows = [(m, p) for (m, p) in EXPECTED if m in predicted and _serves(pattern, p)]
        assert {m for m, _ in rows} == set(predicted), pattern["route"]


def test_only_the_debug_route_depends_on_debug(orders_django_env, served):
    off = {p["route"] for p in _oracle(orders_django_env, debug=False)}
    assert {p["route"] for p in served} - off == {"debug/echo/"}


def test_sextant_matches_django_on_the_fixture(workspace):
    resolved = [r for r in _rows(workspace) if r["resolution"] == "resolved"]
    derived = {(r["method"], r["path"]): _handler(r["handler"]) for r in resolved}
    assert len(derived) == len(resolved)
    assert derived == EXPECTED


def test_the_debug_row_is_not_evaluated(workspace):
    live = {r["row_id"]: r["path"] for r in _rows(workspace)}
    conditions = {
        (live[r["row_id"]], json.loads(str(r["expression"]))["test"], r["holds"])
        for r in workspace.query("endpoint_existence")
    }
    assert conditions == {("/debug/echo/", "settings.DEBUG", "unresolved")}


def test_the_stated_boundaries_are_published_as_today(workspace, served):
    """Each boundary named at `BOUNDARIES`: what Django serves there, and what Sextant says."""
    django = {p["route"]: p for p in served}
    assert django["orders/<int:order_id>/items/archived/"]["allowed"] == ["GET"]
    assert set(django["partners/feed/"]["allowed"]) == EVERY
    assert set(django["promo/current/"]["allowed"]) == EVERY

    partial = {
        (r["method"], r["path"], _handler(r["handler"]))
        for r in _rows(workspace)
        if r["resolution"] == "partial" and r["path_kind"] is None
    }
    assert partial == set().union(*BOUNDARIES.values())
    questions = {(q["question"], q["path"]) for q in workspace.query("open_questions")}
    assert questions == QUESTIONS


def test_a_route_expression_not_read_exactly_is_one_pattern_row(workspace):
    patterns = [
        (r["method"], r["method_kind"], r["resolution"], _handler(r["handler"]))
        for r in _rows(workspace)
        if r["path_kind"] == "pattern"
    ]
    assert patterns == [(None, "any", "partial", "shop.views.shelf")]


@pytest.mark.xfail(
    strict=True,
    reason="Sextant drops the `^` of an exact `re_path` prefix in front of a pattern child: it "
    "publishes `legacy/(shelf|books)/$`, Django's route is `^legacy/(shelf|books)/$`",
)
def test_a_pattern_row_behind_a_re_path_prefix_is_djangos_route_text(workspace):
    (row,) = [r for r in _rows(workspace) if r["path_kind"] == "pattern"]
    assert row["path"] == PATTERN_ROUTE


def test_no_request_reads_are_published(workspace):
    assert [r for r in workspace.query("endpoint_metadata")] == []
