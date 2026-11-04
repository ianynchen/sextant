"""Sub-router mounts (Vert.x spec 2026-10-30 §3c, plan Task 11).

A route registered on a router takes the prefix of every mount that received that same
router: the object one producer made, reached along one call path (`shapes/mounts.py`). The
facts below are Vert.x routes through `vertx-web.yml`, shaped as CP-56 row group (h)
records javac's output: `Router.router(vertx)` a static call, every route and mount call
`invokeinterface` on `Router` or `Route`, a router handed between methods as an argument.
"""

import json
from pathlib import Path

import pytest
from test_call_engines import _MODULE, CATALOGS_DIR, _resolve_fluent_walked

from flow_facts import straight_line
from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.shapes.inbound_routes import (
    EXACT_MOUNT_PATH,
    PATTERN_MOUNT_PATH,
    WILDCARD_MOUNT_POINT,
)
from sextant.application.resolve.shapes.mounts import mount_rules_of, router_producers
from sextant.application.resolve.values import value_index
from sextant.domain.closed_sets import ConstructKind
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    MethodReturnFact,
    SymbolFact,
)
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

ROUTER = "io/vertx/ext/web/Router#"
ROUTE = "io/vertx/ext/web/Route#"
VERTX = "Lio/vertx/core/Vertx;"
_MAKES = f"({VERTX})Lio/vertx/ext/web/Router;"
_PATH = "(Ljava/lang/String;)Lio/vertx/ext/web/Route;"
_REGEX = "(Ljava/lang/String;)Lio/vertx/ext/web/Route;"
_HANDLER = "(Lio/vertx/core/Handler;)Lio/vertx/ext/web/Route;"
_SUB_ROUTER = "(Lio/vertx/ext/web/Router;)Lio/vertx/ext/web/Route;"
_MOUNT_SUB_ROUTER = "(Ljava/lang/String;Lio/vertx/ext/web/Router;)Lio/vertx/ext/web/Route;"
_RECEIVES = "(Lio/vertx/ext/web/RoutingContext;)V"
_TAKES_ROUTER = "(Lio/vertx/ext/web/Router;)V"


def _vertx_web():
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "vertx-web")


def _string(value: str) -> CallArgument:
    return CallArgument(kind="string", value=value)


def _parameter(index: int) -> CallArgument:
    return CallArgument(kind="parameter", value=index)


def _value(source: int) -> CallArgument:
    return CallArgument(kind="unresolved", source=source)


class _Module:
    """Method bodies numbered as the extractor numbers them — ordinals in order per method,
    each call's result a fresh value id — and the methods they declare."""

    def __init__(self) -> None:
        self.facts: list = []
        self._ordinals: dict[str, int] = {}
        self._value = 100

    def method(self, owner: str, name: str, jvm: str, returns: int | None = None) -> str:
        """Declares `owner#name` with a body, handing back value `returns` where one is
        given; answers the method's symbol."""
        symbol = _MODULE + method_descriptor(owner, name, jvm)
        value = None if returns is None else _value(returns)
        self.facts.extend(
            [
                SymbolFact(
                    document_id="doc_1",
                    symbol=symbol,
                    construct_kind=ConstructKind.METHOD,
                    enclosing=_MODULE + owner,
                ),
                MethodReturnFact(document_id="doc_1", method=symbol, ordinal=0, value=value),
            ]
        )
        return symbol

    def call(
        self,
        caller: str,
        owner: str,
        name: str,
        descriptor: str,
        arguments: list[CallArgument],
        receiver: int | None = None,
        receiver_parameter: int | None = None,
        kind: str = "interface",
    ) -> int:
        self._value += 1
        ordinal = self._ordinals.get(caller, 0)
        self._ordinals[caller] = ordinal + 1
        self.facts.append(
            CallSiteFact(
                document_id="doc_1",
                caller=caller,
                target=CallTarget(owner=owner, name=name, descriptor=descriptor),
                invoke_kind=kind,
                ordinal=ordinal,
                receiver=receiver,
                receiver_parameter=receiver_parameter,
                result=self._value,
                arguments=arguments,
            )
        )
        return self._value

    def router(self, caller: str) -> int:
        """`Router.router(vertx)`, the vertx being the caller's parameter 0."""
        return self.call(caller, ROUTER, "router", _MAKES, [_parameter(0)], kind="static")

    def route(
        self,
        caller: str,
        path: str,
        handler: str,
        receiver: int | None = None,
        receiver_parameter: int | None = None,
    ) -> None:
        """`router.get(path).handler(owner::handler)` on the router in `receiver` (a value) or
        `receiver_parameter`, the handler a method of the caller's class that answers."""
        owner = caller.removeprefix(_MODULE).rsplit("#", 1)[0] + "#"
        made = self.call(
            caller, ROUTER, "get", _PATH, [_string(path)], receiver, receiver_parameter
        )
        symbol = method_descriptor(owner, handler, _RECEIVES)
        self.method(owner, handler, _RECEIVES)
        argument = CallArgument(kind="lambda", source=90, symbol=symbol, captures=0)
        self.call(caller, ROUTE, "handler", _HANDLER, [argument], receiver=made)

    def sub_router(
        self,
        caller: str,
        path: str,
        router: CallArgument,
        receiver: int | None = None,
        receiver_parameter: int | None = None,
        root: str = "route",
    ) -> None:
        """`parent.route(path).subRouter(router)`, or `routeWithRegex` for `root`."""
        made = self.call(
            caller, ROUTER, root, _REGEX, [_string(path)], receiver, receiver_parameter
        )
        self.call(caller, ROUTE, "subRouter", _SUB_ROUTER, [router], receiver=made)


def _rows(tmp_path: Path, module: _Module) -> tuple[set[tuple], list[dict]]:
    workspace = _resolve_fluent_walked(tmp_path, straight_line(module.facts), _vertx_web())
    rows = {
        (r["path"], str(r["handler"]).rsplit("#", 1)[-1].split("(")[0], r["resolution"])
        for r in workspace.query("endpoints")
    }
    questions = [dict(row) for row in workspace.query("open_questions")]
    workspace.close()
    return rows, questions


BASE = "com/acme/vertx/BaseVerticle#"
IMPL = "com/acme/vertx/OrdersVerticle#"
APP = "com/acme/vertx/App#"


@pytest.mark.pins("mounts.a-route-takes-the-prefix-of-the-mount-that-received-its-router")
def test_a_router_passed_through_three_methods_takes_its_prefix(tmp_path: Path):
    """Review Focus. The router is built in a base class (`BaseVerticle#router`), handed to
    `addRoutes(router)`, which the subclass overrides and registers a route on, and mounted
    by a third method (`BaseVerticle#start`): the route serves under the mount's prefix."""
    module = _Module()
    module.facts.extend(
        [
            SymbolFact(
                document_id="doc_1", symbol=_MODULE + BASE, construct_kind=ConstructKind.CLASS
            ),
            SymbolFact(
                document_id="doc_1",
                symbol=_MODULE + IMPL,
                construct_kind=ConstructKind.CLASS,
                superclass=_MODULE + BASE,
            ),
            # `abstract void addRoutes(Router router)`: declared, no body.
            SymbolFact(
                document_id="doc_1",
                symbol=_MODULE + method_descriptor(BASE, "addRoutes", _TAKES_ROUTER),
                construct_kind=ConstructKind.METHOD,
                enclosing=_MODULE + BASE,
            ),
        ]
    )
    # `Router router(Vertx vertx) { return Router.router(vertx); }`
    builds = _MODULE + method_descriptor(BASE, "router", _MAKES)
    made = module.router(builds)
    module.method(BASE, "router", _MAKES, returns=made)
    # `void start(Vertx vertx, Router root) { Router r = router(vertx); addRoutes(r);
    #  root.route("/api/*").subRouter(r); }`
    starts = module.method(BASE, "start", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    built = module.call(starts, BASE, "router", _MAKES, [_parameter(0)], kind="virtual")
    module.call(starts, BASE, "addRoutes", _TAKES_ROUTER, [_value(built)], kind="virtual")
    module.sub_router(starts, "/api/*", _value(built), receiver_parameter=1)
    # `void addRoutes(Router router) { router.get("/orders").handler(this::list); }`
    adds = module.method(IMPL, "addRoutes", _TAKES_ROUTER)
    module.route(adds, "/orders", "list", receiver_parameter=0)

    rows, questions = _rows(tmp_path, module)

    assert rows == {("/api/orders", "list", "resolved")}
    assert questions == []


@pytest.mark.pins("mounts.a-mount-reads-its-prefix-on-the-routes-own-path")
def test_a_helper_that_builds_and_mounts_per_call_gives_each_router_its_own_prefix(
    tmp_path: Path,
):
    """`createSubRouter(root, vertx, name)` builds a router, mounts it at `"/" + name + "*"`
    and returns it, called for `users` and for `groups`: each route serves under its own
    caller's prefix only (OI-222's mixing would add `/groups/:id` and `/users/:id/members`)."""
    module = _Module()
    jvm = f"(Lio/vertx/ext/web/Router;{VERTX}Ljava/lang/String;)Lio/vertx/ext/web/Router;"
    helper = _MODULE + method_descriptor(APP, "createSubRouter", jvm)
    sub = module.call(helper, ROUTER, "router", _MAKES, [_parameter(1)], kind="static")
    joined = module.call(
        helper,
        "java/lang/invoke/StringConcatFactory#",
        "makeConcatWithConstants",
        "(Ljava/lang/String;)Ljava/lang/String;",
        [_parameter(2)],
        kind="dynamic",
    )
    route = module.call(
        helper,
        ROUTER,
        "route",
        _PATH,
        [CallArgument(kind="concat", source=joined, value="/{}*")],
        receiver_parameter=0,
    )
    module.call(helper, ROUTE, "subRouter", _SUB_ROUTER, [_value(sub)], receiver=route)
    module.method(APP, "createSubRouter", jvm, returns=sub)
    register = module.method(APP, "register", f"(Lio/vertx/ext/web/Router;{VERTX})V")
    users = module.call(
        register, APP, "createSubRouter", jvm, [_parameter(0), _parameter(1), _string("users")]
    )
    module.route(register, "/:userUuid", "user", receiver=users)
    groups = module.call(
        register, APP, "createSubRouter", jvm, [_parameter(0), _parameter(1), _string("groups")]
    )
    module.route(register, "/:groupUuid/members", "members", receiver=groups)

    rows, _ = _rows(tmp_path, module)

    assert rows == {
        ("/users/:userUuid", "user", "resolved"),
        ("/groups/:groupUuid/members", "members", "resolved"),
    }


@pytest.mark.pins("fluent.a-mount-chain-derives-no-row-of-its-own")
def test_a_mount_of_a_router_the_module_does_not_build_adds_nothing(tmp_path: Path):
    """`root.route("/bridge/*").subRouter(Bridge.router())` mounts a router a library builds
    (a SockJS bridge's shape): no route here is on it, so it adds no prefix to anything and
    no row of its own. A router built here and never mounted serves at its root."""
    module = _Module()
    wire = module.method(APP, "wire", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    own = module.router(wire)
    module.route(wire, "/orders", "list", receiver=own)
    bridged = module.call(
        wire, "com/other/Bridge#", "router", "()Lio/vertx/ext/web/Router;", [], kind="static"
    )
    module.sub_router(wire, "/bridge/*", _value(bridged), receiver_parameter=1)

    rows, questions = _rows(tmp_path, module)

    assert rows == {("/orders", "list", "resolved")}
    assert questions == []


@pytest.mark.pins("mounts.a-prefix-argument-is-the-mount-point")
def test_4_5_mount_sub_router_reads_its_string_prefix(tmp_path: Path):
    """Vert.x 4.5's `root.mountSubRouter("/api", sub)`: the string is the prefix, a trailing
    `/` being the separator the join supplies."""
    module = _Module()
    wire = module.method(APP, "wire", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    sub = module.router(wire)
    module.route(wire, "/orders", "list", receiver=sub)
    module.call(
        wire,
        ROUTER,
        "mountSubRouter",
        _MOUNT_SUB_ROUTER,
        [_string("/api/"), _value(sub)],
        receiver_parameter=1,
    )

    rows, questions = _rows(tmp_path, module)

    assert rows == {("/api/orders", "list", "resolved")}
    assert questions == []


@pytest.mark.pins(
    "mounts.nested-mounts-compose", "values.an-object-reader-lets-calls-on-the-object-past"
)
def test_nested_mounts_compose_their_prefixes(tmp_path: Path):
    """`root.route("/api/*").subRouter(api)` and `api.route("/v1/*").subRouter(v1)`: a route
    on `v1` serves under both, outermost first."""
    module = _Module()
    wire = module.method(APP, "wire", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    api = module.router(wire)
    v1 = module.router(wire)
    module.route(wire, "/orders", "list", receiver=v1)
    module.sub_router(wire, "/v1/*", _value(v1), receiver=api)
    module.sub_router(wire, "/api/*", _value(api), receiver_parameter=1)

    rows, _ = _rows(tmp_path, module)

    assert rows == {("/api/v1/orders", "list", "resolved")}


@pytest.mark.pins(
    "mounts.a-refused-mount-serves-nothing",
    "mounts.a-refused-mount-is-recorded",
)
def test_a_route_reached_only_through_mounts_vertx_refuses_is_no_row(tmp_path: Path):
    """`subRouter` on an exact path, on a regex path, and 4.5's `mountSubRouter` given a
    trailing `*` each throw in Vert.x (CP-56 rows 119-120): each is recorded under its own
    reason, and the router they named is served through none of them — nor at its root,
    since Vert.x threw at the mount (coordinator ruling 4)."""
    module = _Module()
    wire = module.method(APP, "wire", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    sub = module.router(wire)
    module.route(wire, "/orders", "list", receiver=sub)
    module.sub_router(wire, "/exact", _value(sub), receiver_parameter=1)
    module.sub_router(wire, "/r/.*", _value(sub), receiver_parameter=1, root="routeWithRegex")
    module.call(
        wire,
        ROUTER,
        "mountSubRouter",
        _MOUNT_SUB_ROUTER,
        [_string("/star*"), _value(sub)],
        receiver_parameter=1,
    )

    rows, questions = _rows(tmp_path, module)

    assert rows == set()
    refused = {
        (q["path"], candidate)
        for q in questions
        if q["question"] == "refused_registration"
        for candidate in [__import__("json").loads(q["candidates"])[0]["reason"]]
    }
    assert refused == {
        ("/exact", EXACT_MOUNT_PATH),
        ("/r/.*", PATTERN_MOUNT_PATH),
        ("/star*", WILDCARD_MOUNT_POINT),
    }


@pytest.mark.pins("mounts.a-refused-mount-adds-no-prefix")
def test_a_route_also_mounted_where_vertx_accepts_keeps_that_row(tmp_path: Path):
    """The same router mounted on an exact path (refused) and at `/api/*`: the route serves
    under `/api` only — the refused mount adds nothing and takes nothing away."""
    module = _Module()
    wire = module.method(APP, "wire", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    sub = module.router(wire)
    module.route(wire, "/orders", "list", receiver=sub)
    module.sub_router(wire, "/exact", _value(sub), receiver_parameter=1)
    module.sub_router(wire, "/api/*", _value(sub), receiver_parameter=1)

    rows, questions = _rows(tmp_path, module)

    assert rows == {("/api/orders", "list", "resolved")}
    assert [q["path"] for q in questions] == ["/exact"]


@pytest.mark.pins("mounts.an-execution-that-reaches-no-mount-serves-at-the-root")
def test_a_helpers_router_mounted_by_one_caller_and_not_another_serves_both_ways(
    tmp_path: Path,
):
    """`build(vertx)` makes a router and gives it a route; `mounted` mounts what it returns
    at `/api/*` and `served` does not. Enumerable is exact: the route serves under `/api`
    for the first caller and at its root for the second (coordinator ruling 3)."""
    module = _Module()
    builds = _MODULE + method_descriptor(APP, "build", _MAKES)
    made = module.router(builds)
    module.route(builds, "/orders", "list", receiver=made)
    module.method(APP, "build", _MAKES, returns=made)
    mounted = module.method(APP, "mounted", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    built = module.call(mounted, APP, "build", _MAKES, [_parameter(0)], kind="virtual")
    module.sub_router(mounted, "/api/*", _value(built), receiver_parameter=1)
    served = module.method(APP, "served", f"({VERTX})V")
    alone = module.call(served, APP, "build", _MAKES, [_parameter(0)], kind="virtual")
    module.call(
        served,
        "io/vertx/core/http/HttpServer#",
        "requestHandler",
        "(Lio/vertx/core/Handler;)Lio/vertx/core/http/HttpServer;",
        [_value(alone)],
    )

    rows, _ = _rows(tmp_path, module)

    assert rows == {("/api/orders", "list", "resolved"), ("/orders", "list", "resolved")}


def _mount_under(second: str) -> _Module:
    """`mountUnder(Route route, Router sub) { route.subRouter(sub); }`, called for
    `root.route("/a/*")` with a router serving `/x`, and for `root.route(second)` with one
    serving `/y`: the mount call is one site, walked back to each caller's route."""
    module = _Module()
    jvm = "(Lio/vertx/ext/web/Route;Lio/vertx/ext/web/Router;)V"
    helper = module.method(APP, "mountUnder", jvm)
    module.call(helper, ROUTE, "subRouter", _SUB_ROUTER, [_parameter(1)], receiver_parameter=0)
    start = module.method(APP, "start", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    a = module.router(start)
    module.route(start, "/x", "ax", receiver=a)
    ra = module.call(start, ROUTER, "route", _PATH, [_string("/a/*")], receiver_parameter=1)
    module.call(start, APP, "mountUnder", jvm, [_value(ra), _value(a)], kind="virtual")
    b = module.router(start)
    module.route(start, "/y", "by", receiver=b)
    rb = module.call(start, ROUTER, "route", _PATH, [_string(second)], receiver_parameter=1)
    module.call(start, APP, "mountUnder", jvm, [_value(rb), _value(b)], kind="virtual")
    return module


@pytest.mark.pins("mounts.every-chain-end-of-a-mount-call-is-a-way-to-it")
def test_a_mount_call_in_a_helper_reads_each_callers_route(tmp_path: Path):
    """Review fix 1. Each caller's route is that caller's mount path: `/a/x` and `/b/y`,
    never `/y` at the root because only the first chain end was kept."""
    rows, questions = _rows(tmp_path, _mount_under("/b/*"))

    assert {row[0] for row in rows} == {"/a/x", "/b/y"}
    assert questions == []


@pytest.mark.pins("mounts.a-refusal-is-read-for-every-way-to-the-mount")
def test_a_helpers_mount_on_an_exact_path_is_refused_on_that_callers_way(tmp_path: Path):
    """Review fix 1. The second caller mounts on the exact path `/b`, which Vert.x refuses:
    the refusal is filed, and the second router serves nothing; the first is unaffected."""
    rows, questions = _rows(tmp_path, _mount_under("/b"))

    assert {row[0] for row in rows} == {"/a/x"}
    assert [(q["path"], q["question"]) for q in questions] == [("/b", "refused_registration")]


@pytest.mark.pins(
    "mounts.a-self-returning-router-call-is-the-same-router",
    "values.an-object-reader-goes-through-a-self-returning-call",
)
def test_a_self_returning_router_call_is_the_same_router(tmp_path: Path):
    """Review fix 2. `root.route("/api/*").subRouter(sub.errorHandler(500, h))`:
    `errorHandler` returns the router it was called on, so the mount receives `sub`."""
    module = _Module()
    wire = module.method(APP, "wire", f"({VERTX}Lio/vertx/ext/web/Router;)V")
    sub = module.router(wire)
    module.route(wire, "/x", "list", receiver=sub)
    same = module.call(
        wire,
        ROUTER,
        "errorHandler",
        "(ILio/vertx/core/Handler;)Lio/vertx/ext/web/Router;",
        [CallArgument(kind="int", value=500), _parameter(0)],
        receiver=sub,
    )
    module.sub_router(wire, "/api/*", _value(same), receiver_parameter=1)

    rows, _ = _rows(tmp_path, module)

    assert rows == {("/api/x", "list", "resolved")}


@pytest.mark.pins("mounts.a-router-handed-in-is-the-parameter-it-arrived-at")
def test_a_router_handed_in_and_mounted_here_takes_the_prefix(tmp_path: Path):
    """Review fix 3. `wire(vertx, root, sub)` gives `sub` a route and mounts it at `/api/*`:
    two ends at one parameter on agreeing paths are one object, served under the mount only."""
    module = _Module()
    wire = module.method(
        APP, "wire", f"({VERTX}Lio/vertx/ext/web/Router;Lio/vertx/ext/web/Router;)V"
    )
    module.route(wire, "/x", "list", receiver_parameter=2)
    module.sub_router(wire, "/api/*", _parameter(2), receiver_parameter=1)

    rows, _ = _rows(tmp_path, module)

    assert rows == {("/api/x", "list", "resolved")}


def _mounted_on_a_template(template: str, root: str = "route") -> _Module:
    """`wire(vertx, root, p)` mounts a router serving `/orders` at a path built from `p`, a
    parameter nothing here binds, by `template`."""
    module = _Module()
    wire = module.method(APP, "wire", f"({VERTX}Lio/vertx/ext/web/Router;Ljava/lang/String;)V")
    sub = module.router(wire)
    module.route(wire, "/orders", "list", receiver=sub)
    joined = module.call(
        wire,
        "java/lang/invoke/StringConcatFactory#",
        "makeConcatWithConstants",
        "(Ljava/lang/String;)Ljava/lang/String;",
        [_parameter(2)],
        kind="dynamic",
    )
    route = module.call(
        wire,
        ROUTER,
        root,
        _PATH,
        [CallArgument(kind="concat", source=joined, value=template)],
        receiver_parameter=1,
    )
    module.call(wire, ROUTE, "subRouter", _SUB_ROUTER, [_value(sub)], receiver=route)
    return module


@pytest.mark.pins("mounts.a-path-read-in-part-is-refused-where-the-part-read-decides")
def test_a_mount_path_whose_last_piece_is_read_without_the_wildcard_is_refused(tmp_path: Path):
    """Review fix 4. `root.route(p + "/v1").subRouter(sub)`: whatever `p` is, the path ends
    in `/v1`, so it is exact and Vert.x refuses it. Recorded as a literal would be; the
    router serves nothing."""
    rows, questions = _rows(tmp_path, _mounted_on_a_template("{}/v1"))

    assert rows == set()
    assert [(q["path"], json.loads(q["candidates"])[0]["reason"]) for q in questions] == [
        ("{}/v1", EXACT_MOUNT_PATH)
    ]


@pytest.mark.pins("mounts.a-refused-mount-is-recorded")
def test_a_regex_mount_path_read_in_part_is_refused_and_recorded(tmp_path: Path):
    """Review fix 4. `root.routeWithRegex(p + ".*").subRouter(sub)`: a regex mount path is
    refused whatever it reads, and the refusal is filed, not only the router left unserved."""
    rows, questions = _rows(tmp_path, _mounted_on_a_template("{}.*", root="routeWithRegex"))

    assert rows == set()
    assert [(q["path"], json.loads(q["candidates"])[0]["reason"]) for q in questions] == [
        ("{}.*", PATTERN_MOUNT_PATH)
    ]


def test_a_mount_point_whose_last_piece_is_unread_is_not_refused(tmp_path: Path):
    """The undecided half of fix 4: `root.route("/" + p).subRouter(sub)` ends in what `p`
    is, which may be `*`, so it is not refused: the route serves under the named hole."""
    rows, questions = _rows(tmp_path, _mounted_on_a_template("/{}"))

    assert rows == {("<prefix>/orders", "list", "partial")}
    assert [q["question"] for q in questions] == ["mount_prefix"]


@pytest.mark.pins("mounts.a-module-method-returning-a-router-is-walked-into")
def test_router_producers_are_derived_by_type(tmp_path: Path):
    """The producer reader's stops are derived from the facts by type (spec §3c): a library
    call returning the router type, and a constructor of a class implementing it. A module
    method returning a router is walked into, never a stop."""
    module = _Module()
    wire = module.method(APP, "wire", f"({VERTX})Lio/vertx/ext/web/Router;")
    made = module.router(wire)
    module.call(
        wire,
        "io/vertx/ext/web/impl/RouterImpl#",
        "<init>",
        f"({VERTX})V",
        [_parameter(0)],
        receiver=made,
        kind="special",
    )
    module.call(wire, APP, "wire", f"({VERTX})Lio/vertx/ext/web/Router;", [], kind="virtual")
    module.call(wire, "com/other/Lib#", "name", "()Ljava/lang/String;", [], kind="static")
    workspace = _resolve_fluent_walked(tmp_path, straight_line(module.facts), _vertx_web())
    index = value_index(workspace)
    ancestors = {"io/vertx/ext/web/impl/RouterImpl#": [(ROUTER, "implements", False)]}
    found = router_producers(index, frozenset({ROUTER}), ancestors)
    workspace.close()

    assert found == frozenset({(ROUTER, "router"), ("io/vertx/ext/web/impl/RouterImpl#", "<init>")})


@pytest.mark.parametrize(
    ("matches", "message"),
    [
        ({"mount": [{"method": "m", "router_arg": 0, "prefix_arg": 1}]}, "router_type"),
        ({"router_type": ["a.Router"]}, "mount"),
        ({"router_type": [], "mount": []}, "router_type"),
        (
            {"router_type": ["a.Router"], "mount": [{"owner": "a.Router", "method": "m"}]},
            "router_arg",
        ),
        (
            {
                "router_type": ["a.Router"],
                "mount": [
                    {
                        "owner": "a.Router",
                        "method": "m",
                        "router_arg": 0,
                        "prefix_arg": 1,
                        "prefix_from": "receiver_path",
                    }
                ],
            },
            "exactly one",
        ),
        (
            {
                "router_type": ["a.Router"],
                "mount": [
                    {
                        "owner": "a.Router",
                        "method": "n",
                        "router_arg": 0,
                        "prefix_from": "receiver_path",
                    }
                ],
            },
            "terminal",
        ),
        (
            {
                "router_type": ["a.Router"],
                "mount": [
                    {
                        "owner": "a.Router",
                        "method": "m",
                        "router_arg": 0,
                        "prefix_arg": 1,
                        "wildcard": 7,
                    }
                ],
            },
            "wildcard",
        ),
        (
            {
                "router_type": ["a.Router"],
                "mount": [
                    {
                        "owner": "a.Router",
                        "method": "m",
                        "router_arg": 0,
                        "prefix_arg": 1,
                        "wildcard": "",
                    }
                ],
            },
            "wildcard",
        ),
        (
            {
                "router_type": ["a.Router"],
                "path_join": "leading-slash",
                "mount": [{"owner": "a.Router", "method": "m", "router_arg": 0, "prefix_arg": 1}],
            },
            "path_join",
        ),
        (
            {
                "router_type": ["a.Router"],
                "mount": [
                    {
                        "owner": "a.Router",
                        "method": "m",
                        "descriptor": 3,
                        "router_arg": 0,
                        "prefix_arg": 1,
                    }
                ],
            },
            "descriptor",
        ),
        (
            {
                "router_type": ["a.Router"],
                "mount": [
                    {
                        "owner": "a.Router",
                        "method": "m",
                        "router_arg": 0,
                        "prefix_arg": 1,
                        "refuses": ["sometimes"],
                    }
                ],
            },
            "refuses",
        ),
    ],
)
@pytest.mark.pins("inbound_routes.a-path-join-other-than-leading-slash-is-refused")
def test_a_malformed_mount_word_is_refused_naming_the_file(matches: dict, message: str):
    with pytest.raises(CatalogError, match=f"mounts.yml.*{message}"):
        mount_rules_of({"terminal": ["m"], **matches}, "mounts.yml")
