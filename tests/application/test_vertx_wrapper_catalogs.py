"""The RxJava 3 and Mutiny wrappers of Vert.x Web and WebClient (spec 2026-10-30 §3e, Task 15).

`vertx-web.yml`, `vertx-webclient.yml` and `client-models/vertx-web.yml` name each wrapper's
types as another `owner`, the way `javalin.yml` names one library under three names. The facts
below are shaped as CP-56 row group (g) records the wrappers (`scripts/probes/cp56_vertx_web.md`,
rows 134-302): the same method names on `io.vertx.rxjava3.ext.web.*` and
`io.vertx.mutiny.ext.web.*`, the chain staying in the wrapper's own types, RxJava 3's handlers
taking `io.vertx.core.Handler` and Mutiny's `java.util.function.Consumer`, each wrapper's
`RoutingContext.next()` on its own type.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_call_engines import (
    _MODULE,
    CATALOGS_DIR,
    _resolve_fluent,
    _resolve_fluent_walked,
)

from sextant.application.ports.catalogs import Catalog
from sextant.domain.closed_sets import ConstructKind
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    MethodReturnFact,
    SymbolFact,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

REPO = Path(__file__).parents[2]
PROBE = REPO / "scripts" / "probes" / "cp56_vertx_web.md"
HTTP_METHOD = "Lio/vertx/core/http/HttpMethod;"


@dataclass(frozen=True)
class Wrapper:
    """One generated wrapper, as CP-56 row group (g) records it."""

    name: str
    web: str  # the package of Router, Route, RoutingContext (as a symbol prefix)
    handlers: str  # the framework's own handler package
    vertx: str  # the wrapper's Vertx type, the factories' first parameter
    handler: str  # what Route.handler takes
    singles: str  # what HttpRequest.send answers
    sends: tuple[str, ...]  # the terminals that send a request, no argument

    @property
    def router(self) -> str:
        return f"{self.web}Router#"

    @property
    def route(self) -> str:
        return f"{self.web}Route#"

    @property
    def context(self) -> str:
        return f"{self.web}RoutingContext#"

    @property
    def client(self) -> str:
        return f"{self.web}client/WebClient#"

    @property
    def request(self) -> str:
        return f"{self.web}client/HttpRequest#"

    @property
    def template(self) -> str:
        return self.web.replace("/ext/web/", "/uritemplate/") + "UriTemplate#"

    def jvm(self, symbol: str) -> str:
        """`io/vertx/rxjava3/ext/web/Route#` as the descriptor type `Lio/…/Route;`."""
        return "L" + symbol.removesuffix("#") + ";"


RX3 = Wrapper(
    name="rxjava3",
    web="io/vertx/rxjava3/ext/web/",
    handlers="io/vertx/rxjava3/ext/web/handler/",
    vertx="Lio/vertx/rxjava3/core/Vertx;",
    handler="Lio/vertx/core/Handler;",
    singles="Lio/reactivex/rxjava3/core/Single;",
    sends=("send", "rxSend"),
)
MUTINY = Wrapper(
    name="mutiny",
    web="io/vertx/mutiny/ext/web/",
    handlers="io/vertx/mutiny/ext/web/handler/",
    vertx="Lio/vertx/mutiny/core/Vertx;",
    handler="Ljava/util/function/Consumer;",
    singles="Lio/smallrye/mutiny/Uni;",
    sends=("send", "sendAndAwait", "sendAndForget"),
)
WRAPPERS = pytest.mark.parametrize("wrapper", [RX3, MUTINY], ids=lambda w: w.name)


def _catalog(catalog_id: str) -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == catalog_id)


def _string(value: str) -> CallArgument:
    return CallArgument(kind="string", value=value)


def _int(value: int) -> CallArgument:
    return CallArgument(kind="int", value=value)


def _verb(name: str) -> CallArgument:
    return CallArgument(kind="enum", symbol=f"io/vertx/core/http/HttpMethod#{name}.")


# Inbound: a Router chain in the wrapper's own types ----------------------------------------

ROUTES = "com/acme/vertx/OrderRoutes#"
REGISTER = _MODULE + ROUTES + "register()V."


class _Routes:
    """Route chains in one registering method, and the handler bodies they name."""

    def __init__(self, wrapper: Wrapper) -> None:
        self.w = wrapper
        self.facts: list = []
        self._value = 100
        self._handlers: set[str] = set()
        self._ordinal: dict[str, int] = {}

    def call(
        self,
        owner: str,
        name: str,
        descriptor: str,
        receiver: int | None,
        arguments: list[CallArgument],
        caller: str = REGISTER,
        kind: str = "interface",
    ) -> int:
        self._value += 1
        ordinal = self._ordinal.get(caller, 0)
        self._ordinal[caller] = ordinal + 1
        self.facts.append(
            CallSiteFact(
                document_id="doc_1",
                caller=caller,
                target=CallTarget(owner=owner, name=name, descriptor=descriptor),
                invoke_kind=kind,
                ordinal=ordinal,
                receiver=receiver,
                result=self._value,
                arguments=arguments,
            )
        )
        return self._value

    def handler_symbol(self, name: str) -> str:
        return f"{ROUTES}{name}({self.w.jvm(self.w.context)})V."

    def ref(self, name: str) -> CallArgument:
        """`this::name`, a method reference naming the handler method itself (row 304)."""
        self._handlers.add(name)
        return CallArgument(kind="lambda", source=90, symbol=self.handler_symbol(name), captures=0)

    def route_type(self) -> str:
        return self.w.jvm(self.w.route)

    def root(self, name: str, arguments: list[CallArgument], *, descriptor: str | None = None):
        route = self.route_type()
        if descriptor is None:
            descriptor = "(Ljava/lang/String;)" + route if arguments else "()" + route
        return self.call(self.w.router, name, descriptor, None, arguments)

    def step(self, value: int, name: str, descriptor: str, arguments: list[CallArgument]) -> int:
        return self.call(self.w.route, name, descriptor, value, arguments)

    def handler(self, value: int, name: str) -> int:
        return self.step(
            value,
            "handler",
            f"({self.w.handler}){self.route_type()}",
            [self.ref(name)],
        )

    def passes_on(self, name: str) -> None:
        """`name(ctx) { ctx.next(); }` on the wrapper's own context (row 293 / 294)."""
        self.facts.append(
            CallSiteFact(
                document_id="doc_1",
                caller=_MODULE + self.handler_symbol(name),
                target=CallTarget(owner=self.w.context, name="next", descriptor="()V"),
                invoke_kind="virtual",
                ordinal=0,
                receiver_parameter=0,
            )
        )

    def all_facts(self) -> list:
        symbols = [
            fact
            for name in sorted(self._handlers)
            for fact in (
                SymbolFact(
                    document_id="doc_1",
                    symbol=_MODULE + self.handler_symbol(name),
                    construct_kind=ConstructKind.METHOD,
                ),
                MethodReturnFact(
                    document_id="doc_1", method=_MODULE + self.handler_symbol(name), ordinal=0
                ),
            )
        ]
        return [*self.facts, *symbols]


def _served(tmp_path: Path, routes: _Routes) -> tuple[set[tuple], list[dict]]:
    workspace = _resolve_fluent_walked(tmp_path, routes.all_facts(), _catalog("vertx-web"))
    rows = {
        (
            r["method"],
            r["path"],
            str(r["handler"]).rsplit("#", 1)[-1].split("(")[0],
            r["resolution"],
        )
        for r in workspace.query("endpoints")
    }
    questions = [dict(row) for row in workspace.query("open_questions")]
    workspace.close()
    return rows, questions


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-routers-are-owners",
    "vertx-wrappers.mutiny-routers-are-owners",
    "vertx-wrappers.mutiny-handler-takes-a-consumer",
)
@WRAPPERS
def test_a_wrapper_route_is_one_row(tmp_path: Path, wrapper: Wrapper):
    """`router.get("/orders").handler(this::list)` on the wrapper's `Router` and `Route`."""
    routes = _Routes(wrapper)
    root = routes.root("get", [_string("/orders")])
    routes.handler(root, "list")

    rows, questions = _served(tmp_path, routes)

    assert rows == {("GET", "/orders", "list", "resolved")}
    assert questions == []


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-routes-are-owners",
    "vertx-wrappers.mutiny-routes-are-owners",
    "vertx-wrappers.mutiny-failure-handler-takes-a-consumer",
)
@WRAPPERS
def test_a_wrapper_route_built_by_statements_keeps_every_step(tmp_path: Path, wrapper: Wrapper):
    """`Route r = router.route(p); r.method(GET); r.failureHandler(…); r.setName(…);
    r.method(DELETE); r.handler(…)`: each call on the stored route, its result dropped (row
    309). The same two rows as the one-statement form, and no row for the failure handler."""
    routes = _Routes(wrapper)
    route = routes.route_type()
    stored = routes.root("route", [_string("/orders/:id")])
    routes.step(stored, "method", f"({HTTP_METHOD}){route}", [_verb("GET")])
    routes.step(stored, "failureHandler", f"({wrapper.handler}){route}", [routes.ref("failed")])
    routes.step(stored, "setName", f"(Ljava/lang/String;){route}", [_string("order")])
    routes.step(stored, "method", f"({HTTP_METHOD}){route}", [_verb("DELETE")])
    routes.handler(stored, "find")

    rows, _ = _served(tmp_path, routes)

    assert rows == {
        ("GET", "/orders/:id", "find", "resolved"),
        ("DELETE", "/orders/:id", "find", "resolved"),
    }


@WRAPPERS
def test_a_wrapper_route_with_a_verb_constant_and_a_regex_root(tmp_path: Path, wrapper: Wrapper):
    """The roots and steps with the same names and parameters as the core's (rows 135-155):
    `route(HttpMethod, String)` reads its verb off the constant, `getWithRegex` is a pattern
    row."""
    routes = _Routes(wrapper)
    both = f"({HTTP_METHOD}Ljava/lang/String;){routes.route_type()}"
    routes.handler(
        routes.root("route", [_verb("PUT"), _string("/orders/:id")], descriptor=both), "put"
    )
    routes.handler(routes.root("getWithRegex", [_string("\\/files\\/.+")]), "file")

    rows, _ = _served(tmp_path, routes)

    assert rows == {
        ("PUT", "/orders/:id", "put", "resolved"),
        ("GET", "\\/files\\/.+", "file", "resolved"),
    }


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-next-passes-the-request-on",
    "vertx-wrappers.mutiny-next-passes-the-request-on",
)
@WRAPPERS
def test_a_wrapper_handler_calling_its_own_next_passes_on(tmp_path: Path, wrapper: Wrapper):
    """`next()` on the wrapper's `RoutingContext` carries the request on (rows 293-294), so
    the row names the handler after it."""
    routes = _Routes(wrapper)
    root = routes.root("get", [_string("/x")])
    routes.handler(routes.handler(root, "auth"), "reply")
    routes.passes_on("auth")
    only_middleware = routes.root("get", [_string("/mw")])
    routes.handler(only_middleware, "auth")

    rows, _ = _served(tmp_path, routes)

    assert rows == {("GET", "/x", "reply", "resolved")}


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-framework-handlers-pass-on",
    "vertx-wrappers.mutiny-framework-handlers-pass-on",
)
@WRAPPERS
def test_the_wrappers_own_handler_package_passes_on_by_contract(tmp_path: Path, wrapper: Wrapper):
    """`router.route().handler(BodyHandler.create())` with the wrapper's `BodyHandler`: the
    framework's handler carries the request on, so a route served only by it is no row."""
    routes = _Routes(wrapper)
    body_handler = f"{wrapper.handlers}BodyHandler#"
    made = routes.call(
        body_handler, "create", f"(){wrapper.jvm(body_handler)}", None, [], kind="static"
    )
    root = routes.root("route", [])
    routes.step(
        root,
        "handler",
        f"({wrapper.handler}){routes.route_type()}",
        [CallArgument(kind="unresolved", source=made)],
    )

    rows, questions = _served(tmp_path, routes)

    assert rows == set()
    assert questions == []


# Vert.x Web's own `Router` and `Route`, beside the wrappers, for the handlers every flavour
# ships in another artifact (vertx-web-validation's `ValidationHandler`, OI-261).
CORE = Wrapper(
    name="core",
    web="io/vertx/ext/web/",
    handlers="io/vertx/ext/web/handler/",
    vertx="Lio/vertx/core/Vertx;",
    handler="Lio/vertx/core/Handler;",
    singles="Lio/vertx/core/Future;",
    sends=("send",),
)


@pytest.mark.pins("vertx-web.validation-handlers-pass-on")
@pytest.mark.parametrize("wrapper", [CORE, RX3], ids=lambda w: w.name)
def test_a_validation_handler_passes_on_to_the_handler_after_it(tmp_path: Path, wrapper: Wrapper):
    """vertx-examples' `validation`: `post(p).handler(ValidationHandlerBuilder.create(…)
    .build()).handler(rc -> …)`. vertx-web-validation's `ValidationHandlerImpl.handle` calls
    `next()` once the request validates and `fail` otherwise (`javap`, 4.5.10 and 5.2.1), so
    the row names the handler after it. Its package was outside `framework_handlers`, so the
    row was `partial` with handler NULL. RxJava 3's `ValidationHandler` wraps the same."""
    routes = _Routes(wrapper)
    validation = wrapper.web + "validation/"
    builder = f"{validation}builder/ValidationHandlerBuilder#"
    made = routes.call(
        builder, "build", f"(){wrapper.jvm(validation + 'ValidationHandler#')}", 50, []
    )
    root = routes.root("post", [_string("/hello")])
    validated = routes.step(
        root,
        "handler",
        f"({wrapper.handler}){routes.route_type()}",
        [CallArgument(kind="unresolved", source=made)],
    )
    routes.handler(validated, "reply")

    rows, questions = _served(tmp_path, routes)

    assert rows == {("POST", "/hello", "reply", "resolved")}
    assert questions == []


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-sub-router-mounts-by-its-route-path",
    "vertx-wrappers.mutiny-sub-router-mounts-by-its-route-path",
    "vertx-wrappers.rxjava3-routers-are-router-types",
    "vertx-wrappers.mutiny-routers-are-router-types",
)
@WRAPPERS
def test_a_wrapper_sub_router_serves_under_its_mount(tmp_path: Path, wrapper: Wrapper):
    """`parent.route("/api/*").subRouter(sub)` with the wrapper's `Router` for both: the
    routes registered on `sub` serve under `/api` (row 171 / 250)."""
    routes = _Routes(wrapper)
    router, route = wrapper.jvm(wrapper.router), routes.route_type()
    sub = routes.call(
        wrapper.router, "router", f"({wrapper.vertx}){router}", None,
        [CallArgument(kind="parameter", value=0)], kind="static",
    )  # fmt: skip
    served = routes.call(
        wrapper.router, "get", f"(Ljava/lang/String;){route}", sub, [_string("/orders")]
    )
    routes.handler(served, "list")
    mount = routes.call(
        wrapper.router, "route", f"(Ljava/lang/String;){route}", None, [_string("/api/*")]
    )
    routes.step(
        mount, "subRouter", f"({router}){route}", [CallArgument(kind="unresolved", source=sub)]
    )

    rows, _ = _served(tmp_path, routes)

    assert rows == {("GET", "/api/orders", "list", "resolved")}


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-mount-sub-router-mounts-at-its-prefix",
    "vertx-wrappers.mutiny-mount-sub-router-mounts-at-its-prefix",
)
@WRAPPERS
def test_a_wrapper_mount_sub_router_is_there_at_vertx_4_5(tmp_path: Path, wrapper: Wrapper):
    """`parent.mountSubRouter("/api", sub)` (rows 137, 216: RxJava 3 4.5.10 and Mutiny 3.23.1
    only), as the core's."""
    routes = _Routes(wrapper)
    router, route = wrapper.jvm(wrapper.router), routes.route_type()
    sub = routes.call(
        wrapper.router, "router", f"({wrapper.vertx}){router}", None,
        [CallArgument(kind="parameter", value=0)], kind="static",
    )  # fmt: skip
    served = routes.call(
        wrapper.router, "get", f"(Ljava/lang/String;){route}", sub, [_string("/o")]
    )
    routes.handler(served, "list")
    parent = routes.call(
        wrapper.router, "router", f"({wrapper.vertx}){router}", None,
        [CallArgument(kind="parameter", value=0)], kind="static",
    )  # fmt: skip
    routes.call(
        wrapper.router,
        "mountSubRouter",
        f"(Ljava/lang/String;{router}){route}",
        parent,
        [_string("/api"), CallArgument(kind="unresolved", source=sub)],
    )

    rows, _ = _served(tmp_path, routes)

    assert rows == {("GET", "/api/o", "list", "resolved")}


def test_mutinys_blocking_handler_takes_a_consumer_at_both_measured_versions(tmp_path: Path):
    """`blockingHandler(Consumer)` and, at Mutiny 4.0.2, `blockingHandler(Consumer, boolean)`
    (row 247) register the route; at 3.23.1 the two-argument form takes a `Handler`. The
    handler is argument 0 in every one."""
    routes = _Routes(MUTINY)
    route = routes.route_type()
    for path, descriptor, extra in (
        ("/a", f"(Ljava/util/function/Consumer;){route}", []),
        (
            "/b",
            f"(Ljava/util/function/Consumer;Z){route}",
            [CallArgument(kind="boolean", value=True)],
        ),
        ("/c", f"(Lio/vertx/core/Handler;Z){route}", [CallArgument(kind="boolean", value=True)]),
    ):
        root = routes.root("get", [_string(path)])
        routes.step(root, "blockingHandler", descriptor, [routes.ref("slow"), *extra])

    rows, _ = _served(tmp_path, routes)

    assert rows == {
        ("GET", "/a", "slow", "resolved"),
        ("GET", "/b", "slow", "resolved"),
        ("GET", "/c", "slow", "resolved"),
    }


def test_a_mutiny_handler_object_is_not_read_for_its_accept_method(tmp_path: Path):
    """A Mutiny handler that is an OBJECT (`handler(new Auth())`, a class implementing
    `Consumer`) is a stated boundary: the catalog's `handler_methods` is `handle` for every
    owner, and Vert.x runs `accept` on a Consumer. So the object's body is not read and the row
    is `partial` with a pass-through question, never a guess at which of its methods runs."""
    routes = _Routes(MUTINY)
    auth = "com/acme/vertx/Auth#"
    context = MUTINY.jvm(MUTINY.context)
    accept = f"{auth}accept({context})V."
    routes.facts.extend(
        [
            SymbolFact(
                document_id="doc_1", symbol=_MODULE + auth, construct_kind=ConstructKind.CLASS
            ),
            SymbolFact(
                document_id="doc_1", symbol=_MODULE + accept, construct_kind=ConstructKind.METHOD
            ),
            MethodReturnFact(document_id="doc_1", method=_MODULE + accept, ordinal=0),
        ]
    )
    root = routes.root("get", [_string("/guarded")])
    routes.step(
        root,
        "handler",
        f"({MUTINY.handler}){routes.route_type()}",
        [CallArgument(kind="instance", symbol=auth)],
    )

    rows, questions = _served(tmp_path, routes)

    assert rows == {("GET", "/guarded", "None", "partial")}
    assert [q["question"] for q in questions] == ["handler_pass_through"]
    assert "com/acme/vertx/Auth#" in questions[0]["candidates"]


# Outbound: a WebClient in the wrapper's own types ------------------------------------------

CALLER = _MODULE + "com/acme/vertx/InventoryClient#call()V."


class _Calls:
    """WebClient calls in one method, the chain staying in the wrapper's types (row 317)."""

    def __init__(self, wrapper: Wrapper) -> None:
        self.w = wrapper
        self.sites: list[CallSiteFact] = []
        self._value = 100

    def call(
        self,
        owner: str,
        name: str,
        descriptor: str,
        receiver: int | None,
        arguments: list[CallArgument],
        kind: str = "virtual",
    ) -> int:
        self._value += 1
        self.sites.append(
            CallSiteFact(
                document_id="doc_1",
                caller=CALLER,
                target=CallTarget(owner=owner, name=name, descriptor=descriptor),
                invoke_kind=kind,
                ordinal=len(self.sites),
                receiver=receiver,
                result=self._value,
                arguments=arguments,
            )
        )
        return self._value

    def request_type(self) -> str:
        return self.w.jvm(self.w.request)

    def get(self, descriptor_parameters: str, arguments: list[CallArgument], client=90) -> int:
        return self.call(
            self.w.client,
            "get",
            f"({descriptor_parameters}){self.request_type()}",
            client,
            arguments,
        )

    def step(self, value: int, name: str, parameters: str, arguments: list[CallArgument]) -> int:
        return self.call(
            self.w.request, name, f"({parameters}){self.request_type()}", value, arguments
        )

    def send(self, value: int, name: str = "send", returns: str | None = None) -> int:
        return self.call(self.w.request, name, f"(){returns or self.w.singles}", value, [])


def _rows(tmp_path: Path, calls: _Calls) -> list[tuple]:
    workspace = _resolve_fluent(tmp_path, calls.sites, _catalog("vertx-webclient"))
    rows = sorted(
        (
            (r["method"], r["peer"], r["path"], r["resolution"])
            for r in workspace.query("endpoints")
        ),
        key=str,
    )
    workspace.close()
    return rows


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-clients-are-owners",
    "vertx-wrappers.mutiny-clients-are-owners",
    "vertx-wrappers.rxjava3-rx-send-sends-the-request",
    "vertx-wrappers.mutiny-and-await-sends-the-request",
)
@WRAPPERS
def test_a_wrapper_request_is_a_row_for_every_terminal_that_sends(tmp_path: Path, wrapper: Wrapper):
    """`client.get(8080, "inventory", "/stock").send()` and the wrapper's other sends (rows
    206, 285, 298, 302): RxJava 3's `rxSend`, Mutiny's `sendAndAwait` and `sendAndForget`."""
    calls = _Calls(wrapper)
    for terminal in wrapper.sends:
        request = calls.get(
            "ILjava/lang/String;Ljava/lang/String;",
            [_int(8080), _string("inventory"), _string(f"/{terminal}")],
        )
        calls.send(request, terminal)

    assert _rows(tmp_path, calls) == sorted(
        [("GET", "inventory:8080", f"/{terminal}", "resolved") for terminal in wrapper.sends],
        key=str,
    )


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-requests-are-owners",
    "vertx-wrappers.mutiny-requests-are-owners",
)
@WRAPPERS
def test_a_statement_style_wrapper_request_keeps_what_each_statement_set(
    tmp_path: Path, wrapper: Wrapper
):
    """Row 322 with the wrapper's types: `r = client.postAbs(q); r.putHeader(…);
    r.addQueryParam(…); r.timeout(…); r.as(codec).send()`, each call made on the stored request
    and its result dropped. One row carrying the header and the query parameter: a step the
    wrapper's owner does not name is not `returns_receiver`, and would fork its own branch."""
    calls = _Calls(wrapper)
    request = calls.call(
        wrapper.client,
        "postAbs",
        f"(Ljava/lang/String;){calls.request_type()}",
        90,
        [_string("http://prometheus:9090/q")],
    )
    strings = "Ljava/lang/String;Ljava/lang/String;"
    calls.step(request, "putHeader", strings, [_string("X-Tenant"), _string("acme")])
    calls.step(request, "addQueryParam", strings, [_string("a"), _string("b")])
    calls.step(request, "timeout", "J", [CallArgument(kind="long", value=5)])
    typed = calls.step(
        request,
        "as",
        f"({wrapper.jvm(wrapper.web + 'codec/BodyCodec#')})",
        [CallArgument(kind="unresolved")],
    )
    calls.send(typed)
    workspace = _resolve_fluent(tmp_path, calls.sites, _catalog("vertx-webclient"))
    rows = sorted(
        (
            (r["method"], r["peer"], r["path"], r["resolution"])
            for r in workspace.query("endpoints")
        ),
        key=str,
    )
    entries = sorted(
        (r["kind"], r["name"], r["value"]) for r in workspace.query("endpoint_metadata")
    )
    workspace.close()

    assert rows == [("POST", "prometheus:9090", "/q", "resolved")]
    assert entries == [("header", "X-Tenant", "acme"), ("query", "a", "b")]


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-body-sends-name-their-body",
    "vertx-wrappers.mutiny-body-sends-name-their-body",
)
@WRAPPERS
def test_a_wrapper_body_carrying_send_names_the_body_it_sends(tmp_path: Path, wrapper: Wrapper):
    """RxJava 3's `rxSendJson` and Mutiny's `sendJsonAndAwait` and `sendJsonAndForget` send a
    request as `sendJson` does (rows 298, 302): each a row, whose request shape is the type of
    the object handed to it."""
    terminals = {"rxjava3": ("rxSendJson",), "mutiny": ("sendJsonAndAwait", "sendJsonAndForget")}
    calls = _Calls(wrapper)
    for name in terminals[wrapper.name]:
        request = calls.call(
            wrapper.client,
            "postAbs",
            f"(Ljava/lang/String;){calls.request_type()}",
            90,
            [_string(f"http://billing/{name}")],
        )
        calls.call(
            wrapper.request,
            name,
            f"(Ljava/lang/Object;){wrapper.singles}",
            request,
            [CallArgument(kind="class", symbol="com/acme/Order#")],
        )
    workspace = _resolve_fluent(tmp_path, calls.sites, _catalog("vertx-webclient"))
    rows = sorted(
        (r["path"], r["resolution"], '"shape_id":"com/acme/Order#"' in str(r["request_shape"]))
        for r in workspace.query("endpoints")
    )
    workspace.close()

    assert rows == sorted((f"/{name}", "resolved", True) for name in terminals[wrapper.name])


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-uri-template-is-read-off-its-factory",
    "vertx-wrappers.mutiny-uri-template-is-read-off-its-factory",
)
@WRAPPERS
def test_a_wrapper_uri_template_form_reads_its_template(tmp_path: Path, wrapper: Wrapper):
    """`client.get(UriTemplate.of("/stock/{id}"))`: the wrapper's own `UriTemplate` (row 177)
    and its `of(String)` factory, which `javap` shows on the RxJava 3 and Mutiny jars."""
    calls = _Calls(wrapper)
    template_type = wrapper.jvm(wrapper.template)
    made = calls.call(
        wrapper.template, "of", f"(Ljava/lang/String;){template_type}", None,
        [_string("/stock/{id}")], kind="static",
    )  # fmt: skip
    request = calls.get(template_type, [CallArgument(kind="unresolved", source=made)])
    calls.send(request)

    assert _rows(tmp_path, calls) == [("GET", None, "/stock/{id}", "resolved")]


@WRAPPERS
def test_a_wrapper_socket_address_request_names_no_peer(tmp_path: Path, wrapper: Wrapper):
    """`request(HttpMethod, SocketAddress, String)`: sent to that address, which is not read.
    RxJava 3 4.5.10 takes its own `SocketAddress`, 5.x the core's (row 189), each a row."""
    calls = _Calls(wrapper)
    for path, socket in (
        ("/core-socket", "Lio/vertx/core/net/SocketAddress;"),
        ("/wrapper-socket", wrapper.vertx.replace("core/Vertx", "core/net/SocketAddress")),
    ):
        request = calls.call(
            wrapper.client,
            "request",
            f"({HTTP_METHOD}{socket}Ljava/lang/String;){calls.request_type()}",
            90,
            [_verb("GET"), CallArgument(kind="unresolved"), _string(path)],
        )
        calls.send(request)

    assert _rows(tmp_path, calls) == [
        ("GET", None, "/core-socket", "resolved"),
        ("GET", None, "/wrapper-socket", "resolved"),
    ]


OPTIONS = "io/vertx/ext/web/client/WebClientOptions#"


@pytest.mark.pins(
    "vertx-wrappers.rxjava3-client-factory-is-a-rung",
    "vertx-wrappers.mutiny-client-factory-is-a-rung",
)
@WRAPPERS
def test_a_wrapper_clients_options_fill_a_request_naming_no_address(
    tmp_path: Path, wrapper: Wrapper
):
    """`WebClient.create(vertx, new WebClientOptions().setDefaultHost("search")
    .setDefaultPort(9200))` with the wrapper's factory (row 175 / 254): the options are the
    core's own type, so the same setters read them, and `client.get("/q")` joins the
    defaults."""
    calls = _Calls(wrapper)
    calls.sites.append(
        CallSiteFact(
            document_id="doc_1", caller=CALLER,
            target=CallTarget(owner=OPTIONS, name="<init>", descriptor="()V"),
            invoke_kind="special", ordinal=0, receiver=500, result=None, arguments=[],
        )
    )  # fmt: skip
    options = calls.call(
        OPTIONS, "setDefaultHost",
        "(Ljava/lang/String;)Lio/vertx/ext/web/client/WebClientOptions;", 500, [_string("search")],
    )  # fmt: skip
    options = calls.call(
        OPTIONS, "setDefaultPort", "(I)Lio/vertx/ext/web/client/WebClientOptions;", options,
        [_int(9200)],
    )  # fmt: skip
    client = calls.call(
        wrapper.client,
        "create",
        f"({wrapper.vertx}Lio/vertx/ext/web/client/WebClientOptions;){wrapper.jvm(wrapper.client)}",
        None,
        [CallArgument(kind="parameter", value=0), CallArgument(kind="unresolved", source=options)],
        kind="static",
    )
    request = calls.get("Ljava/lang/String;", [_string("/q")], client=client)
    calls.send(request)

    assert _rows(tmp_path, calls) == [("GET", "search:9200", "/q", "resolved")]


# The catalogs name only what CP-56 or javap measured ---------------------------------------

_WRAPPER_PACKAGES = ("io.vertx.rxjava3.", "io.vertx.mutiny.")

# Methods the wrappers declare that CP-56 row group (g) does not list, measured with `javap` on
# vertx-rx-java3 4.5.10, 5.0.0 and 5.2.1 and smallrye-mutiny-vertx-web / -web-client 3.23.1 and
# 4.0.2 (Task 15): every one answers `aload_0; areturn` (Mutiny 3.23.1's `Consumer` forms
# through its private `__` twin, which does). Task 11 measured the core `Router`'s the same way.
_JAVAP_ONLY = {
    "Router": {
        "putMetadata", "clear", "errorHandler", "uncaughtErrorHandler", "modifiedHandler",
        "allowForward",
    },
    "Route": {"useNormalisedPath", "setRegexGroupsNames"},
    "HttpRequest": {
        "authentication", "connectTimeout", "idleTimeout", "multipartMixed", "proxy",
        "putHeaders", "routingKey", "traceOperation", "virtualHost",
        "rxSendJson", "rxSendJsonObject", "rxSendBuffer",
        "sendJsonAndAwait", "sendJsonAndForget", "sendJsonObjectAndAwait",
        "sendJsonObjectAndForget", "sendBufferAndAwait", "sendBufferAndForget",
    },
    "UriTemplate": {"of"},
}  # fmt: skip


def _cp56() -> dict[tuple[str, str], list[str]]:
    """`(owner, method)` to every descriptor CP-56 lists for it in any column."""
    found: dict[tuple[str, str], list[str]] = {}
    for line in PROBE.read_text().splitlines():
        row = re.match(r"\| (\d+) \| descriptors of `(\w+)\.(\w+)` .*? \| `([\w.]+)` \|(.*)", line)
        if row is None:
            continue
        owner, method = row.group(4), row.group(3)
        found.setdefault((owner, method), []).extend(re.findall(r"`(\([^`]*)`", row.group(5)))
    return found


def _parameters(descriptor: str) -> str:
    return descriptor[: descriptor.index(")") + 1]


def _entries() -> list[tuple[str, dict, str]]:
    """Every root, step and rung of the three catalogs that names a wrapper owner, with the
    catalog it is in."""
    out = []
    for catalog_id in ("vertx-web", "vertx-webclient"):
        matches = _catalog(catalog_id).matches
        for section in ("roots", "steps"):
            out.extend((section, entry, catalog_id) for entry in matches[section])
        out.extend(("mount", entry, catalog_id) for entry in matches.get("mount", []))
    ladder = _catalog("vertx-webclient").matches["client_base"]["ladder"]
    out.extend(("ladder", rung, "client-models/vertx-web") for rung in ladder)
    return out


def _owners(entry: dict) -> list[str]:
    owner = entry["owner"]
    return owner if isinstance(owner, list) else [owner]


def test_every_wrapper_owner_and_descriptor_is_cited_in_cp56_or_measured_with_javap():
    """The wrapper half of a catalog entry is a claim about a jar: each wrapper `owner` an
    entry names declares the entry's method, and where the entry fixes a descriptor, one with
    the same parameter types. Rows 134-302 are the citation; a method they do not list is in
    `_JAVAP_ONLY`, with the measurement stated there."""
    listed = _cp56()
    unmeasured = []
    for _, entry, catalog_id in _entries():
        for owner in _owners(entry):
            if not owner.startswith(_WRAPPER_PACKAGES):
                continue
            descriptors = listed.get((owner, entry["method"]), [])
            if "descriptor" in entry:
                fixed = _parameters(entry["descriptor"])
                cited = any(_parameters(d) == fixed for d in descriptors)
            else:
                cited = bool(descriptors)
            simple = owner.rsplit(".", 1)[-1]
            if not cited and entry["method"] not in _JAVAP_ONLY.get(simple, ()):
                unmeasured.append((catalog_id, owner, entry["method"], entry.get("descriptor")))
    assert unmeasured == []


def test_no_owner_in_a_wrapper_catalog_entry_is_a_stray_or_a_typo():
    known = {
        "Router", "Route", "RoutingContext", "WebClient", "HttpRequest", "UriTemplate",
    }  # fmt: skip
    for _, entry, _ in _entries():
        for owner in _owners(entry):
            assert not owner.endswith(";")
            if owner.startswith(_WRAPPER_PACKAGES):
                assert owner.rsplit(".", 1)[-1] in known


@WRAPPERS
def test_a_wrapper_request_typed_by_as_and_then_configured_by_statements_keeps_them(
    tmp_path: Path, wrapper: Wrapper
):
    """`t = r.as(codec); t.putHeader(…); t.send()`: the typed request is stored and configured
    on its own, its result dropped. `as` answers the same request, so the header is the sent
    request's."""
    calls = _Calls(wrapper)
    request = calls.call(
        wrapper.client,
        "postAbs",
        f"(Ljava/lang/String;){calls.request_type()}",
        90,
        [_string("http://prometheus:9090/q")],
    )
    codec = wrapper.jvm(wrapper.web + "codec/BodyCodec#")
    typed = calls.step(request, "as", f"({codec})", [CallArgument(kind="unresolved")])
    calls.step(
        typed, "putHeader", "Ljava/lang/String;Ljava/lang/String;", [_string("X"), _string("1")]
    )
    calls.send(typed)
    workspace = _resolve_fluent(tmp_path, calls.sites, _catalog("vertx-webclient"))
    entries = sorted((r["kind"], r["name"]) for r in workspace.query("endpoint_metadata"))
    workspace.close()

    assert entries == [("header", "X")]


def _shape(entries, owner: str, arity) -> set[tuple]:
    return {
        (e["method"], arity(e))
        for e in entries
        if owner in _owners(e) and not str(e["method"]).startswith(("rxSend", "guard"))
    }


def _parameters_count(entry: dict) -> str | None:
    """The entry's parameter types with the wrapper's own types written as the core's
    (`Lio/vertx/mutiny/uritemplate/UriTemplate;` is `Lio/vertx/uritemplate/UriTemplate;`, a
    `Consumer` a `Handler`), so a twin is the same overload as its core entry."""
    descriptor = entry.get("descriptor")
    if descriptor is None:
        return None
    parameters = _parameters(descriptor)
    parameters = re.sub(r"Lio/vertx/(?:rxjava3|mutiny)/", "Lio/vertx/", parameters)
    return parameters.replace("Ljava/util/function/Consumer;", "Lio/vertx/core/Handler;")


def test_every_wrapper_has_a_twin_of_every_core_root_step_and_rung():
    """The wrapper entries that are written out by hand (the `UriTemplate` and `SocketAddress`
    roots, `Route.subRouter`, the Mutiny `Consumer` steps, the client rungs) must cover what the
    core declares, by method and by parameter types (the wrapper's own types read as the core's): a missing twin fails here, where the
    citation test above only catches a descriptor that drifted. `as` is the one step the wrapper
    does not need (an unmatched step passes through), and the send steps are named differently."""
    client = _catalog("vertx-webclient").matches
    web = _catalog("vertx-web").matches
    sets = (
        (
            client["roots"],
            "io.vertx.ext.web.client.WebClient",
            "io.vertx.%s.ext.web.client.WebClient",
        ),
        (web["roots"], "io.vertx.ext.web.Router", "io.vertx.%s.ext.web.Router"),
        (
            client["steps"],
            "io.vertx.ext.web.client.HttpRequest",
            "io.vertx.%s.ext.web.client.HttpRequest",
        ),
        (web["steps"], "io.vertx.ext.web.Route", "io.vertx.%s.ext.web.Route"),
        (web["steps"], "io.vertx.ext.web.Router", "io.vertx.%s.ext.web.Router"),
        (web["mount"], "io.vertx.ext.web.Route", "io.vertx.%s.ext.web.Route"),
        (web["mount"], "io.vertx.ext.web.Router", "io.vertx.%s.ext.web.Router"),
        (
            client["client_base"]["ladder"],
            "io.vertx.ext.web.client.WebClient",
            "io.vertx.%s.ext.web.client.WebClient",
        ),
    )
    for entries, core, twin in sets:
        expected = {m for m in _shape(entries, core, _parameters_count) if m[0] != "as"}
        for package in ("rxjava3", "mutiny"):
            found = _shape(entries, twin % package, _parameters_count)
            # Core entries a wrapper only gets by name (no descriptor) are the same set.
            missing = {
                m for m in expected - found if m[0] not in {x[0] for x in found if x[1] is None}
            }
            assert missing == set(), (core, package, sorted(missing, key=str))
