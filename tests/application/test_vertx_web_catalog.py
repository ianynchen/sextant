"""Vert.x Web routes (`vertx-web.yml`, the `fluent` style; spec 2026-10-30 §3a).

The facts below are what the extractor emits for `fixtures/orders-vertx-web`, shaped as
CP-56 row group (h) records javac's output (`scripts/probes/cp56_vertx_web.md`, rows
304-316): every call `invokeinterface` on `Router` or `Route`, the root's result the
step's receiver, a method reference a `lambda` argument naming the method it refers to,
and a statement-style route's later calls made on the stored `Route` with their results
dropped (row 309).
"""

import logging
from dataclasses import replace
from pathlib import Path

import pytest
from fixture_module import FIXTURE_CAPABILITIES, write_fixture_module_fact_with
from test_call_engines import _MODULE, CATALOGS_DIR, _document, _resolve_fluent

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.pipeline import resolve
from sextant.domain.closed_sets import ANY_METHOD, PATH_KIND_PATTERN, ConstructKind
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, SymbolFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

ROUTER = "io/vertx/ext/web/Router#"
ROUTE = "io/vertx/ext/web/Route#"
HTTP_METHOD = "io/vertx/core/http/HttpMethod#"
ROUTES = "com/acme/vertx/OrderRoutes#"
CALLER = _MODULE + ROUTES + "register(Lio/vertx/ext/web/Router;)V."

_PATH = "(Ljava/lang/String;)Lio/vertx/ext/web/Route;"
_NONE = "()Lio/vertx/ext/web/Route;"
_VERB_PATH = "(Lio/vertx/core/http/HttpMethod;Ljava/lang/String;)Lio/vertx/ext/web/Route;"
_METHOD = "(Lio/vertx/core/http/HttpMethod;)Lio/vertx/ext/web/Route;"
_HANDLER = "(Lio/vertx/core/Handler;)Lio/vertx/ext/web/Route;"


def _vertx_web() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "vertx-web")


def _handler(name: str) -> str:
    """The bare symbol a `this::name` argument names, and (with the module prefix) the
    method's own symbol fact."""
    return f"{ROUTES}{name}(Lio/vertx/ext/web/RoutingContext;)V."


def _ref(name: str) -> CallArgument:
    return CallArgument(kind="lambda", source=90, symbol=_handler(name))


def _string(value: str) -> CallArgument:
    return CallArgument(kind="string", value=value)


def _verb(name: str) -> CallArgument:
    return CallArgument(kind="enum", symbol=f"{HTTP_METHOD}{name}.")


class _Body:
    """One method body's call sites, numbered as the extractor numbers them: ordinals in
    order, each call's result a fresh value id."""

    def __init__(self) -> None:
        self.sites: list[CallSiteFact] = []
        self._next_value = 100

    def call(
        self,
        owner: str,
        name: str,
        descriptor: str,
        receiver: int | None,
        arguments: list[CallArgument],
    ) -> int:
        self._next_value += 1
        self.sites.append(
            CallSiteFact(
                document_id="doc_1",
                caller=CALLER,
                target=CallTarget(owner=owner, name=name, descriptor=descriptor),
                invoke_kind="interface",
                ordinal=len(self.sites),
                receiver=receiver,
                result=self._next_value,
                arguments=arguments,
            )
        )
        return self._next_value

    def chain(self, root: tuple[str, str, list[CallArgument]], *steps: tuple) -> int:
        """`router.<root>(…).<step>(…)…` on one operand stack (row 304)."""
        value = self.call(ROUTER, root[0], root[1], None, root[2])
        for name, descriptor, arguments in steps:
            value = self.call(ROUTE, name, descriptor, value, arguments)
        return value


def _symbols(*names: str) -> list[SymbolFact]:
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + _handler(name),
            construct_kind=ConstructKind.METHOD,
        )
        for name in names
    ]


def _derived(tmp_path: Path, body: _Body, *handlers: str) -> tuple[list[dict], list[dict]]:
    workspace = _resolve_fluent(tmp_path, [*body.sites, *_symbols(*handlers)], _vertx_web())
    rows = [dict(row) for row in workspace.query("endpoints")]
    questions = [dict(row) for row in workspace.query("open_questions")]
    workspace.close()
    return rows, questions


def _served(rows: list[dict]) -> set[tuple]:
    return {
        (
            r["method"],
            r["path"],
            str(r["handler"]).rsplit("#", 1)[-1].split("(")[0],
            r["resolution"],
        )
        for r in rows
    }


def _h(name: str) -> tuple[str, str, list[CallArgument]]:
    return ("handler", _HANDLER, [_ref(name)])


def test_a_verb_root_with_a_handler_is_one_row(tmp_path: Path):
    """`router.get("/orders").handler(this::list)` (row 304)."""
    body = _Body()
    body.chain(("get", _PATH, [_string("/orders")]), _h("list"))
    rows, questions = _derived(tmp_path, body, "list")

    assert _served(rows) == {("GET", "/orders", "list", "resolved")}
    assert (rows[0]["method_kind"], rows[0]["path_kind"]) == (None, None)
    assert questions == []


def test_a_route_built_with_a_verb_constant_takes_its_verb(tmp_path: Path):
    """`router.route(HttpMethod.PUT, "/orders/:id")` (row 310): a `getstatic` the catalog's
    `verb_values` names."""
    body = _Body()
    body.chain(("route", _VERB_PATH, [_verb("PUT"), _string("/orders/:id")]), _h("update"))
    rows, _ = _derived(tmp_path, body, "update")

    assert _served(rows) == {("PUT", "/orders/:id", "update", "resolved")}


@pytest.mark.pins("fluent.several-accumulated-verbs-are-one-row-each")
def test_each_verb_a_route_accumulates_is_a_row_of_its_own(tmp_path: Path):
    """`route("/orders/:id").method(GET).method(DELETE).handler(…)` serves both verbs:
    two rows, one per verb (spec §3f)."""
    body = _Body()
    body.chain(
        ("route", _PATH, [_string("/orders/:id")]),
        ("method", _METHOD, [_verb("GET")]),
        ("method", _METHOD, [_verb("DELETE")]),
        _h("find"),
    )
    rows, _ = _derived(tmp_path, body, "find")

    assert _served(rows) == {
        ("GET", "/orders/:id", "find", "resolved"),
        ("DELETE", "/orders/:id", "find", "resolved"),
    }


def test_a_verb_root_keeps_its_own_verb_beside_an_added_one(tmp_path: Path):
    """`get("/x").method(POST)`: Vert.x adds to the route's method set."""
    body = _Body()
    body.chain(("get", _PATH, [_string("/x")]), ("method", _METHOD, [_verb("POST")]), _h("list"))
    rows, _ = _derived(tmp_path, body, "list")

    assert {r["method"] for r in rows} == {"GET", "POST"}


def test_a_statement_style_route_with_self_returning_calls_between_is_one_chain(tmp_path: Path):
    """`Route r = router.route(p); r.method(GET); r.failureHandler(…); r.setName(…);
    r.method(DELETE); r.handler(…)` — each call on the stored route, its result dropped
    (row 309). The same two rows as the one-statement form, and no others: the failure
    handler registers no route and is never the row's handler."""
    body = _Body()
    route = body.call(ROUTER, "route", _PATH, None, [_string("/statement/:id")])
    body.call(ROUTE, "method", _METHOD, route, [_verb("GET")])
    body.call(ROUTE, "failureHandler", _HANDLER, route, [_ref("failed")])
    body.call(ROUTE, "setName", _PATH, route, [_string("statement")])
    body.call(ROUTE, "method", _METHOD, route, [_verb("DELETE")])
    body.call(ROUTE, "handler", _HANDLER, route, [_ref("statement")])
    rows, _ = _derived(tmp_path, body, "statement", "failed")

    assert _served(rows) == {
        ("GET", "/statement/:id", "statement", "resolved"),
        ("DELETE", "/statement/:id", "statement", "resolved"),
    }


@pytest.mark.pins("fluent.a-verbless-chain-serves-any-method-where-the-catalog-says-so")
def test_a_route_with_no_verb_is_one_row_serving_any_method(tmp_path: Path):
    """`route("/any").handler(…)` serves every verb: ONE row, method NULL, carrying the
    any-method marker (rows 114, 133: an empty method set, an open set of verbs)."""
    body = _Body()
    body.chain(("route", _PATH, [_string("/any")]), _h("any"))
    [row], _ = _derived(tmp_path, body, "any")

    assert (row["method"], row["path"], row["method_kind"], row["resolution"]) == (
        None,
        "/any",
        ANY_METHOD,
        "resolved",
    )


@pytest.mark.pins("fluent.a-pathless-chain-serves-the-catalogs-every-path")
def test_a_route_with_no_path_serves_every_path(tmp_path: Path):
    """`router.route().handler(…)`, the hello world's only route (rows 113, 117): path
    `/*`, method NULL, any method."""
    body = _Body()
    body.chain(("route", _NONE, []), _h("any"))
    [row], _ = _derived(tmp_path, body, "any")

    assert (row["method"], row["path"], row["method_kind"], row["resolution"]) == (
        None,
        "/*",
        ANY_METHOD,
        "resolved",
    )


def test_a_pathless_root_given_a_path_later_takes_that_path(tmp_path: Path):
    """`router.get().path("/later")`: the step supplies what the root lacks."""
    body = _Body()
    body.chain(("get", _NONE, []), ("path", _PATH, [_string("/later")]), _h("list"))
    rows, _ = _derived(tmp_path, body, "list")

    assert _served(rows) == {("GET", "/later", "list", "resolved")}


@pytest.mark.pins("fluent.a-pattern-capture-marks-the-row-and-skips-canonicalising")
def test_a_regex_route_is_a_verbatim_pattern_row(tmp_path: Path):
    """`getWithRegex("\\/files\\/.+")` (row 313): the regex verbatim, `resolved`, marked as
    a pattern, with no `/` put in front of its leading backslash."""
    body = _Body()
    body.chain(("getWithRegex", _PATH, [_string("\\/files\\/.+")]), _h("file"))
    [row], questions = _derived(tmp_path, body, "file")

    assert (row["method"], row["path"], row["path_kind"], row["resolution"]) == (
        "GET",
        "\\/files\\/.+",
        PATH_KIND_PATTERN,
        "resolved",
    )
    assert questions == []


@pytest.mark.pins("fluent.a-pattern-path-is-never-refused")
def test_a_regex_route_is_never_refused_for_lacking_a_leading_slash(tmp_path: Path):
    """Vert.x skips `checkPath` for a regex route (row 118), so a pattern starting with
    anything is registered as written: a row, and no refusal."""
    body = _Body()
    body.chain(("getWithRegex", _PATH, [_string("files/.+")]), _h("file"))
    rows, questions = _derived(tmp_path, body, "file")

    assert [(r["path"], r["path_kind"]) for r in rows] == [("files/.+", PATH_KIND_PATTERN)]
    assert questions == []


@pytest.mark.pins("fluent.a-pattern-path-keeps-its-query-characters")
def test_a_pattern_keeps_a_question_mark_as_part_of_the_expression(tmp_path: Path):
    """`?` in a regex is a quantifier, not the start of a query string: `/(a|b)?q=.+` is one
    expression, never the path `/(a|b)` with a query parameter `q`."""
    body = _Body()
    body.chain(("getWithRegex", _PATH, [_string("/(a|b)?q=.+")]), _h("file"))
    workspace = _resolve_fluent(tmp_path, [*body.sites, *_symbols("file")], _vertx_web())
    rows = [dict(row) for row in workspace.query("endpoints")]
    entries = [dict(row) for row in workspace.query("endpoint_metadata")]
    workspace.close()

    assert [r["path"] for r in rows] == ["/(a|b)?q=.+"]
    assert entries == []


def test_a_path_after_a_regex_is_an_address_again(tmp_path: Path):
    """`routeWithRegex(r).path("/p")`: the last call says what the path is."""
    body = _Body()
    body.chain(
        ("routeWithRegex", _PATH, [_string("x.+")]), ("path", _PATH, [_string("/p")]), _h("file")
    )
    rows, _ = _derived(tmp_path, body, "file")

    assert [(r["path"], r["path_kind"]) for r in rows] == [("/p", None)]


@pytest.mark.pins("fluent.a-chain-marked-not-serving-derives-nothing")
def test_a_disabled_route_is_no_row(tmp_path: Path):
    """`router.get("/gone").handler(this::g).disable()`: Vert.x serves nothing for it."""
    body = _Body()
    body.chain(("get", _PATH, [_string("/gone")]), _h("gone"), ("disable", _NONE, []))
    rows, questions = _derived(tmp_path, body, "gone")

    assert rows == []
    assert questions == []


def test_a_route_enabled_after_it_was_disabled_serves_again(tmp_path: Path):
    body = _Body()
    body.chain(
        ("get", _PATH, [_string("/back")]),
        ("disable", _NONE, []),
        _h("gone"),
        ("enable", _NONE, []),
    )
    rows, _ = _derived(tmp_path, body, "gone")

    assert _served(rows) == {("GET", "/back", "gone", "resolved")}


def test_a_removed_route_is_not_restored_by_enable(tmp_path: Path):
    """`remove()` takes the route out of the router; `enable()` after it adds nothing back."""
    body = _Body()
    body.chain(
        ("get", _PATH, [_string("/removed")]),
        _h("gone"),
        ("remove", _NONE, []),
        ("enable", _NONE, []),
    )
    rows, _ = _derived(tmp_path, body, "gone")

    assert rows == []


def test_a_path_vertx_refuses_is_no_row_and_is_recorded(tmp_path: Path):
    """`router.get("bad")` throws `Path must start with /` (row 118): no row, not repaired
    to `/bad`, filed as a refused registration."""
    body = _Body()
    body.chain(("get", _PATH, [_string("bad")]), _h("bad"))
    rows, [question] = _derived(tmp_path, body, "bad")

    assert rows == []
    assert (question["method"], question["path"], question["question"]) == (
        "GET",
        "bad",
        "refused_registration",
    )


def test_a_virtual_host_is_a_host_requirement_on_the_row(tmp_path: Path):
    """`router.get("/v").virtualHost("api.example.com").handler(…)`."""
    body = _Body()
    body.chain(
        ("get", _PATH, [_string("/v")]),
        ("virtualHost", _PATH, [_string("api.example.com")]),
        _h("virtualHost"),
    )
    workspace = _resolve_fluent(tmp_path, [*body.sites, *_symbols("virtualHost")], _vertx_web())
    entries = [
        (r["method"], r["path"], r["kind"], r["name"], r["value"])
        for r in workspace.query("endpoint_metadata")
    ]
    workspace.close()

    assert entries == [("GET", "/v", "host", "api.example.com", "api.example.com")]


def test_media_types_accumulate_into_the_media_columns(tmp_path: Path):
    body = _Body()
    body.chain(
        ("post", _PATH, [_string("/orders")]),
        ("consumes", _PATH, [_string("application/json")]),
        ("consumes", _PATH, [_string("text/xml")]),
        ("produces", _PATH, [_string("application/json")]),
        _h("create"),
    )
    [row], _ = _derived(tmp_path, body, "create")

    assert (row["consumes"], row["produces"]) == (
        '["application/json","text/xml"]',
        '["application/json"]',
    )


@pytest.mark.declines("vertx-web")
@pytest.mark.pins("fluent.no-terminal-no-row")
def test_a_route_given_no_handler_derives_nothing(tmp_path: Path):
    """§10 near-miss for the TERMINAL conjunct: the root, its descriptor, a literal rooted
    path and a self-returning step all hold, and no handler is ever given — so Vert.x
    registers nothing a request can reach (`route("/api/*")` waiting for a `subRouter`)."""
    body = _Body()
    body.chain(("route", _PATH, [_string("/api/*")]), ("setName", _PATH, [_string("api")]))
    rows, questions = _derived(tmp_path, body)

    assert (rows, questions) == ([], [])


@pytest.mark.declines("vertx-web")
@pytest.mark.pins("fluent.root-owner-is-the-declared-type")
def test_a_route_on_an_applications_own_router_type_derives_nothing(tmp_path: Path):
    """§10 near-miss for the ROOT OWNER conjunct: the method name, its descriptor, a literal
    path and a real `.handler(this::list)` on `Route` all hold; only the type the chain roots
    on is the application's own, which this catalog never read."""
    body = _Body()
    value = body.call("com/acme/vertx/OwnRouter#", "get", _PATH, None, [_string("/orders")])
    body.call(ROUTE, "handler", _HANDLER, value, [_ref("list")])
    rows, questions = _derived(tmp_path, body, "list")

    assert (rows, questions) == ([], [])


# --- Review Focus: a module with vertx-web on the classpath and no router ------------


def _resolved_module(
    tmp_path: Path, coordinates: tuple[str, ...], caplog: pytest.LogCaptureFixture
) -> tuple[list[dict], list[dict], list[str], list[str]]:
    """The whole resolve pipeline over a module whose only code calls nothing Vert.x Web
    reads — a Quarkus HTTP module's shape: vertx-web on the classpath, no `Router` call."""
    facts = tmp_path / "facts"
    body = [
        CallSiteFact(
            document_id="doc_1",
            caller=_MODULE + "com/acme/Service#run()V.",
            target=CallTarget(
                owner="java/lang/String#", name="trim", descriptor="()Ljava/lang/String;"
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=4,
            arguments=[],
        )
    ]
    write_fact_file(facts / "Service.jsonl", _document(), body)
    write_fixture_module_fact_with(facts, coordinates)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="sextant.application.resolve.pipeline"):
        report = resolve(workspace, facts, YamlCatalogSource(CATALOGS_DIR), FIXTURE_CAPABILITIES)
    rows = [dict(row) for row in workspace.query("endpoints")]
    questions = [dict(row) for row in workspace.query("open_questions")]
    workspace.close()
    stages = [record.getMessage().split()[0] for record in caplog.records]
    return rows, questions, stages, [s.catalog_id for s in report.skipped_catalogs]


def test_a_module_with_vertx_but_no_router_calls_derives_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """No row, no question, and the same timed stages as the module without vertx-web:
    the catalog runs (it is not skipped) and adds nothing."""
    rows, questions, stages, skipped = _resolved_module(
        tmp_path / "with", ("io.vertx:vertx-web",), caplog
    )
    _, _, without, _ = _resolved_module(tmp_path / "without", (), caplog)

    assert "vertx-web" not in skipped
    assert [r for r in rows if r["catalog_id"] == "vertx-web"] == []
    assert rows == []
    assert questions == []
    assert stages == without


# --- the engine words this catalog uses, refused when malformed -----------------------


def _with(**matches: object) -> Catalog:
    catalog = _vertx_web()
    return replace(catalog, matches={**catalog.matches, **matches})


@pytest.mark.pins("fluent.a-malformed-route-word-is-refused")
@pytest.mark.parametrize(
    ("matches", "fragment"),
    [
        ({"verbless_serves": "all"}, "vertx-web.*verbless_serves"),
        ({"pathless_serves": 7}, "vertx-web.*pathless_serves"),
    ],
    ids=["verbless-not-any", "pathless-not-a-path"],
)
def test_a_malformed_route_word_is_refused_naming_the_file(
    tmp_path: Path, matches: dict, fragment: str
):
    with pytest.raises(CatalogError, match=fragment):
        _resolve_fluent(tmp_path, [], _with(**matches))


@pytest.mark.pins("fluent.a-malformed-route-word-is-refused")
@pytest.mark.parametrize(
    ("capture", "fragment"),
    [
        ({"url_is": "regex"}, "vertx-web.*url_is"),
        ({"serves": "no"}, "vertx-web.*serves"),
    ],
    ids=["url-is-unknown", "serves-not-a-boolean"],
)
def test_a_malformed_route_capture_is_refused_naming_the_file(
    tmp_path: Path, capture: dict, fragment: str
):
    catalog = _vertx_web()
    steps = [
        {**step, "captures": {**step.get("captures", {}), **capture}}
        if step["method"] == "setName"
        else step
        for step in catalog.matches["steps"]
    ]
    with pytest.raises(CatalogError, match=fragment):
        _resolve_fluent(tmp_path, [], _with(steps=steps))


def test_the_catalog_names_no_unmeasured_row():
    """Every `Route` step is one CP-56 row 110 lists, so `returns_receiver` is measured."""
    measured = {
        "blockingHandler", "consumes", "disable", "enable", "failureHandler", "handler",
        "last", "method", "order", "path", "pathRegex", "produces", "putMetadata", "remove",
        "setName", "setRegexGroupsNames", "subRouter", "useNormalizedPath", "virtualHost",
        "respond", "useNormalisedPath",
    }  # fmt: skip
    steps = _vertx_web().matches["steps"]

    assert {step["method"] for step in steps} == measured
    assert all(step["returns_receiver"] is True for step in steps)
    # CP-56 rows 304-323 print some owners with a stray `;`; none is copied here.
    assert all(not str(step["owner"]).endswith(";") for step in steps)
