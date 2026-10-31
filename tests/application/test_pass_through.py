"""Which handler on a route chain answers (Vert.x spec 2026-10-30 §3b, plan Task 10).

A framework that runs a route's handlers in order, each passing the request on by calling a
declared method on the context it received (`passes_on`), answers with the first handler
that does not. The first half reads one module's handlers with `shapes.pass_through`; the
second derives Vert.x routes through `fluent` and checks which chain gives the row.
"""

from dataclasses import replace
from pathlib import Path

import pytest
from fixture_module import write_fixture_module_fact
from test_call_engines import _resolve_fluent, _resolve_fluent_walked
from test_values import (
    _MAKES_OBJECT,
    _MODULE,
    _ONE_TARGET,
    _PKG,
    _declared,
    _document,
    _site,
    _symbol,
    _type,
    _void,
    _writes,
)

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.shapes.chains import _method_symbols
from sextant.application.resolve.shapes.pass_through import (
    ANSWERS,
    PASSES_ON,
    UNREADABLE,
    HandlerReader,
    PassThroughRule,
    handler_outcomes,
)
from sextant.application.resolve.values import value_index
from sextant.domain.closed_sets import ConstructKind
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, SymbolFact
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# --- one module's handlers --------------------------------------------------------------
# `Routes` registers nothing here: each method below is a handler the framework calls with a
# `Context` as parameter 0, and `Context#next` is the declared call that passes on. Neither
# `Context` nor `Lib` is declared, so every call on them is a body this module does not read.
_ROUTES = _PKG + "Routes#"
_CONTEXT = _PKG + "Context#"
_LIB = _PKG + "Lib#"
_TAKES = "(Lcom/acme/orders/values/Context;)V"
_CAPTURED = "(Lcom/acme/orders/values/Context;Ljava/lang/Object;)V"
_NEXT = (_CONTEXT, "next", "()V")
_RESPONSE = (_CONTEXT, "response", "()Ljava/lang/Object;")
_FAIL = (_CONTEXT, "fail", "(I)V")
_PUT = (_CONTEXT, "put", "(Ljava/lang/String;Ljava/lang/Object;)V")
_END = ("java/lang/Object#", "end", "(Ljava/lang/String;)V")
_FORWARD = (_LIB, "forward", _TAKES)
_WRAPPER = _PKG + "Wrapper#"
_WRAPS = (_WRAPPER, "<init>", _TAKES)
_MAKER = ("java/lang/invoke/LambdaMetafactory#", "handle", _MAKES_OBJECT)
_PASSES_ON = frozenset({(_CONTEXT, "next")})
_PARAMETER_0 = CallArgument(kind="parameter", value=0)


def _handler(name: str, jvm: str = _TAKES) -> str:
    return _symbol(_ROUTES, name, jvm)


def _method(name: str, jvm: str = _TAKES) -> list:
    return [_declared(_ROUTES, name, jvm), _void(_ROUTES, name, jvm)]


def _lambda(name: str, captures: int, source: int | None, jvm: str = _CAPTURED) -> CallArgument:
    return CallArgument(
        kind="lambda",
        symbol=method_descriptor(_ROUTES, name, jvm),
        captures=captures,
        source=source,
    )


def _facts() -> list:
    direct, helper, in_lambda = _handler("direct"), _handler("helper"), _handler("inLambda")
    body = _handler("lambda$inLambda$0", _CAPTURED)
    drains, drained = _handler("drains"), _handler("lambda$drains$1")
    return [
        _type(_ROUTES),
        # `direct(ctx) { ctx.next(); }`
        *_method("direct"),
        _site(direct, 0, _NEXT, kind="interface", receiver_parameter=0),
        # `viaHelper(ctx) { helper(ctx); }` and `helper(ctx) { ctx.next(); }`
        *_method("viaHelper"),
        _site(_handler("viaHelper"), 0, (_ROUTES, "helper", _TAKES), arguments=[_PARAMETER_0]),
        *_method("helper"),
        _site(helper, 0, _NEXT, kind="interface", receiver_parameter=0),
        # `inLambda(ctx) { lib.later(u -> ctx.next()); }`: the lambda captured `ctx`.
        *_method("inLambda"),
        _site(in_lambda, 0, _MAKER, arguments=[_PARAMETER_0], result=5),
        _site(
            in_lambda,
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[_lambda("lambda$inLambda$0", 1, 5)],
        ),
        *_method("lambda$inLambda$0", _CAPTURED),
        _site(body, 0, _NEXT, kind="interface", receiver_parameter=0),
        # `outside(ctx) { Lib.forward(ctx); }`: whatever `forward` does is not read here.
        *_method("outside"),
        _site(_handler("outside"), 0, _FORWARD, arguments=[_PARAMETER_0]),
        # `onContext(ctx) { ctx.put("k", "v"); ctx.response().end("x"); ctx.fail(500); }`:
        # calls ON the context are the framework's own API, never a hand-off.
        *_method("onContext"),
        _site(
            _handler("onContext"),
            0,
            _PUT,
            kind="interface",
            receiver_parameter=0,
            arguments=[
                CallArgument(kind="string", value="k"),
                CallArgument(kind="string", value="v"),
            ],
        ),
        _site(
            _handler("onContext"), 1, _RESPONSE, kind="interface", receiver_parameter=0, result=3
        ),
        _site(
            _handler("onContext"),
            2,
            _END,
            kind="interface",
            receiver=3,
            arguments=[CallArgument(kind="string", value="x")],
        ),
        _site(
            _handler("onContext"),
            3,
            _FAIL,
            kind="interface",
            receiver_parameter=0,
            arguments=[CallArgument(kind="int", value=500)],
        ),
        # `drains(ctx) { parked.forEach(other -> other.next()); ctx.response().end("x"); }`:
        # the `next()` is on contexts the lambda is handed by `forEach`, not on `ctx`.
        *_method("drains"),
        _site(drains, 0, _MAKER, result=5),
        _site(
            drains,
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[_lambda("lambda$drains$1", 0, 5, _TAKES)],
        ),
        _site(drains, 2, _RESPONSE, kind="interface", receiver_parameter=0, result=7),
        _site(
            drains,
            3,
            _END,
            kind="interface",
            receiver=7,
            arguments=[CallArgument(kind="string", value="x")],
        ),
        *_method("lambda$drains$1"),
        _site(drained, 0, _NEXT, kind="interface", receiver_parameter=0),
        # Two handlers, `first(ctx) { second(ctx); }` and `second(ctx) { ctx.next(); }`.
        *_method("first"),
        _site(_handler("first"), 0, (_ROUTES, "second", _TAKES), arguments=[_PARAMETER_0]),
        *_method("second"),
        _site(_handler("second"), 0, _NEXT, kind="interface", receiver_parameter=0),
        # `replies(ctx) { replyTo(ctx); }` and `replyTo(ctx) { ctx.response().end("r"); }`.
        *_method("replies"),
        _site(_handler("replies"), 0, (_ROUTES, "replyTo", _TAKES), arguments=[_PARAMETER_0]),
        *_method("replyTo"),
        _site(_handler("replyTo"), 0, _RESPONSE, kind="interface", receiver_parameter=0, result=2),
        # `stores(ctx) { this.held = ctx; }`: read back by a `getfield` no fact names.
        *_writes(_ROUTES, "stores", _TAKES, "held"),
        # `wraps(ctx) { new Wrapper(ctx); }`: the object keeps it, as a capture field does.
        *_method("wraps"),
        _site(_handler("wraps"), 0, _WRAPS, kind="special", arguments=[_PARAMETER_0]),
        _declared(_WRAPPER, "<init>", _TAKES),
        _void(_WRAPPER, "<init>", _TAKES),
        _site(
            _handler("replyTo"),
            1,
            _END,
            kind="interface",
            receiver=2,
            arguments=[CallArgument(kind="string", value="r")],
        ),
    ]


_HANDLERS = (
    "stores",
    "wraps",
    "direct",
    "viaHelper",
    "inLambda",
    "outside",
    "onContext",
    "drains",
    "first",
    "second",
    "replies",
)


# An anonymous `Handler<Letter>` class: javac's bridge `handle(Object)` hands the context to
# `handle(Letter)`. `Letter` because its descriptor sorts AFTER the bridge's, so name order
# alone would name the bridge.
_ANONYMOUS = _PKG + "Routes$1#"
_BRIDGE = "(Ljava/lang/Object;)V"
_TAKES_LETTER = "(Lcom/acme/orders/values/Letter;)V"


def _anonymous_facts() -> list:
    return [
        _type(_ANONYMOUS),
        _declared(_ANONYMOUS, "handle", _BRIDGE),
        _void(_ANONYMOUS, "handle", _BRIDGE),
        _site(
            _symbol(_ANONYMOUS, "handle", _BRIDGE),
            0,
            (_ANONYMOUS, "handle", _TAKES_LETTER),
            kind="virtual",
            arguments=[_PARAMETER_0],
        ),
        _declared(_ANONYMOUS, "handle", _TAKES_LETTER),
        _void(_ANONYMOUS, "handle", _TAKES_LETTER),
    ]


@pytest.fixture(scope="module")
def walked(tmp_path_factory: pytest.TempPathFactory):
    tmp_path = tmp_path_factory.mktemp("pass_through")
    facts = tmp_path / "facts"
    write_fact_file(facts / "routes.jsonl", _document(), [*_facts(), *_anonymous_facts()])
    write_fixture_module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_return_flows(workspace)
    record_call_edges(workspace)
    yield workspace
    workspace.close()


@pytest.fixture(scope="module")
def outcomes(walked) -> tuple[dict, dict]:
    return handler_outcomes(
        value_index(walked), _PASSES_ON, {_handler(name): 0 for name in _HANDLERS}
    )


def _reader(walked) -> HandlerReader:
    rule = PassThroughRule(_PASSES_ON, ("io.vertx.ext.web.handler",), frozenset({"handle"}))
    return HandlerReader(value_index(walked), rule, _method_symbols(walked), {}, dict)


@pytest.mark.pins("pass_through.a-bridge-hands-the-context-to-the-method-the-row-names")
def test_a_handler_object_of_the_module_runs_its_handler_method_not_the_bridge(walked):
    """`new X(…)` runs `X.handle` (user ruling 2026-10-30); of javac's two, the row names the
    one the bridge hands the context to."""
    handler = _reader(walked).of({"kind": "instance", "symbol": _ANONYMOUS}, None)
    assert handler.outcome is None
    assert handler.symbols[0] == _symbol(_ANONYMOUS, "handle", _TAKES_LETTER)
    assert set(handler.symbols) == {
        _symbol(_ANONYMOUS, "handle", _TAKES_LETTER),
        _symbol(_ANONYMOUS, "handle", _BRIDGE),
    }


@pytest.mark.pins("pass_through.a-framework-handler-object-passes-on")
def test_a_handler_object_of_a_framework_package_passes_on(walked):
    """A subpackage is inside its package: `…handler.impl.BodyHandlerImpl` is the framework's."""
    built = {"kind": "instance", "symbol": "io/vertx/ext/web/handler/impl/BodyHandlerImpl#"}
    assert _reader(walked).of(built, None).outcome == PASSES_ON


def test_a_handler_object_built_elsewhere_and_not_the_frameworks_is_unreadable(walked):
    handler = _reader(walked).of({"kind": "instance", "symbol": "com/other/Thing#"}, None)
    assert (handler.outcome, handler.unread) == (UNREADABLE, "com/other/Thing#")


@pytest.mark.pins("pass_through.a-next-reached-on-the-received-context-passes-on")
def test_a_next_on_the_received_context_passes_on(outcomes):
    """In the handler's own body, in a module helper it hands the context to, and in a
    lambda that captured it."""
    found, _ = outcomes
    assert {name: found[_handler(name)] for name in ("direct", "viaHelper", "inLambda")} == {
        "direct": PASSES_ON,
        "viaHelper": PASSES_ON,
        "inLambda": PASSES_ON,
    }


@pytest.mark.pins("pass_through.a-context-handed-outside-the-module-is-unreadable")
def test_a_context_handed_to_a_body_outside_the_module_is_unreadable(outcomes):
    """`Lib.forward(ctx)`: whether it passes on is decided where this analysis does not
    read, and the method is named so a reader can say why."""
    found, unread = outcomes
    assert found[_handler("outside")] == UNREADABLE
    assert unread[_handler("outside")] == (method_descriptor(_LIB, "forward", _TAKES),)


@pytest.mark.pins("pass_through.only-an-argument-is-a-hand-off")
def test_calls_on_the_context_do_not_make_it_unreadable(outcomes):
    """`ctx.put(…)`, `ctx.response().end(…)` and `ctx.fail(500)` are calls ON the context,
    the framework's own API: the handler answers."""
    found, unread = outcomes
    assert found[_handler("onContext")] == ANSWERS
    assert _handler("onContext") not in unread


def test_a_next_on_another_requests_context_does_not_pass_on(outcomes):
    """`parked.forEach(other -> other.next())` calls `next()` on contexts the lambda is
    handed, never on the one the handler received: the handler answers."""
    found, _ = outcomes
    assert found[_handler("drains")] == ANSWERS


@pytest.mark.pins("pass_through.a-context-handed-to-another-handler-follows-it")
def test_a_context_handed_to_another_handler_passes_on_with_it(outcomes):
    """`first(ctx)` calls `second(ctx)`, a handler of its own whose body calls `next()`: the
    walk back from that `next()` stops at `second`'s parameter, and `first` passes on
    through the hand-off."""
    found, _ = outcomes
    assert (found[_handler("first")], found[_handler("second")]) == (PASSES_ON, PASSES_ON)


@pytest.mark.pins("pass_through.a-context-written-to-a-field-is-unreadable")
def test_a_context_written_to_a_field_is_not_readable_here(outcomes):
    """`this.held = ctx`: a `next()` on the field later is on a `getfield` no fact names, so
    the walk cannot tell — never an answering row (ruling 2026-10-31)."""
    found, unread = outcomes
    assert found[_handler("stores")] == UNREADABLE
    assert unread[_handler("stores")] == (_ROUTES + "held.",)


@pytest.mark.pins("pass_through.a-context-handed-to-a-constructor-is-unreadable")
def test_a_context_handed_to_a_constructor_is_not_readable_here(outcomes):
    """`new Wrapper(ctx)`: the object keeps the context, however empty the constructor's
    body reads here."""
    found, unread = outcomes
    assert found[_handler("wraps")] == UNREADABLE
    assert unread[_handler("wraps")] == (method_descriptor(_WRAPPER, "<init>", _TAKES),)


def test_a_handler_that_replies_through_a_module_helper_answers(outcomes):
    found, unread = outcomes
    assert found[_handler("replies")] == ANSWERS
    assert _handler("replies") not in unread


# --- which chain gives the row ----------------------------------------------------------
# Vert.x routes through `vertx-web.yml`, each handler a method reference whose body either
# answers (no sites) or passes on (`ctx.next()`).
ROUTER = "io/vertx/ext/web/Router#"
ROUTE = "io/vertx/ext/web/Route#"
CONTEXT = "io/vertx/ext/web/RoutingContext#"
OWNER = "com/acme/vertx/Routes#"
_PATH = "(Ljava/lang/String;)Lio/vertx/ext/web/Route;"
_HANDLER = "(Lio/vertx/core/Handler;)Lio/vertx/ext/web/Route;"
_ORDER = "(I)Lio/vertx/ext/web/Route;"
_LAST = "()Lio/vertx/ext/web/Route;"
_RECEIVES = "(Lio/vertx/ext/web/RoutingContext;)V"


def _vertx_web():
    from test_call_engines import CATALOGS_DIR

    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "vertx-web")


def _register(method: str) -> str:
    return _MODULE + OWNER + f"{method}(Lio/vertx/ext/web/Router;)V."


class _Routes:
    """Route chains in one or more registering methods, and the handler bodies they name."""

    def __init__(self) -> None:
        self.facts: list = []
        self._ordinals: dict[str, int] = {}
        self._value = 100
        self._handlers: set[str] = set()

    def _call(
        self, caller: str, owner: str, name: str, descriptor: str, receiver, arguments
    ) -> int:
        self._value += 1
        ordinal = self._ordinals.get(caller, 0)
        self._ordinals[caller] = ordinal + 1
        self.facts.append(
            CallSiteFact(
                document_id="doc_1",
                caller=caller,
                target=CallTarget(owner=owner, name=name, descriptor=descriptor),
                invoke_kind="interface",
                ordinal=ordinal,
                receiver=receiver,
                result=self._value,
                arguments=arguments,
            )
        )
        return self._value

    def route(self, method: str, path: str, *steps: tuple[str, object]) -> None:
        """`router.post(path)` then each step: `("handler", name)`, `("order", n)`, `("last", None)`."""
        caller = _register(method)
        value = self._call(
            caller, ROUTER, "post", _PATH, None, [CallArgument(kind="string", value=path)]
        )
        for step, operand in steps:
            if step == "handler":
                self._handlers.add(str(operand))
                symbol = OWNER + f"{operand}{_RECEIVES}."
                argument = CallArgument(kind="lambda", source=90, symbol=symbol, captures=0)
                value = self._call(caller, ROUTE, "handler", _HANDLER, value, [argument])
            elif step == "order":
                value = self._call(
                    caller, ROUTE, "order", _ORDER, value, [CallArgument(kind="int", value=operand)]
                )
            else:
                value = self._call(caller, ROUTE, "last", _LAST, value, [])

    def passes_on(self, name: str) -> None:
        """`name(ctx) { ctx.next(); }`."""
        self.facts.append(
            CallSiteFact(
                document_id="doc_1",
                caller=_MODULE + OWNER + f"{name}{_RECEIVES}.",
                target=CallTarget(owner=CONTEXT, name="next", descriptor="()V"),
                invoke_kind="interface",
                ordinal=0,
                receiver_parameter=0,
            )
        )

    def all_facts(self) -> list:
        symbols = [
            SymbolFact(
                document_id="doc_1",
                symbol=_MODULE + OWNER + f"{name}{_RECEIVES}.",
                construct_kind=ConstructKind.METHOD,
            )
            for name in sorted(self._handlers)
        ]
        return [*self.facts, *symbols]


def _rows(tmp_path: Path, routes: _Routes) -> set[tuple]:
    workspace = _resolve_fluent_walked(tmp_path, routes.all_facts(), _vertx_web())
    rows = {
        (r["path"], str(r["handler"]).rsplit("#", 1)[-1].split("(")[0], r["resolution"])
        for r in workspace.query("endpoints")
    }
    workspace.close()
    return rows


@pytest.mark.pins("fluent.a-chain-whose-every-handler-passes-on-is-no-row")
def test_a_chain_whose_handlers_all_pass_on_is_no_row(tmp_path: Path):
    routes = _Routes()
    routes.route("wire", "/mw", ("handler", "auth"))
    routes.route("wire", "/x", ("handler", "auth"), ("handler", "reply"))
    routes.passes_on("auth")
    assert _rows(tmp_path, routes) == {("/x", "reply", "resolved")}


@pytest.mark.pins("fluent.a-route-chain-in-one-method-runs-in-root-order")
def test_two_answering_chains_in_one_method_are_the_first_registered(tmp_path: Path):
    routes = _Routes()
    routes.route("wire", "/x", ("handler", "first"))
    routes.route("wire", "/x", ("handler", "second"))
    assert _rows(tmp_path, routes) == {("/x", "first", "resolved")}


@pytest.mark.pins("fluent.route-chains-in-different-methods-are-narrowed")
def test_two_answering_chains_in_two_methods_are_each_narrowed(tmp_path: Path):
    routes = _Routes()
    routes.route("one", "/x", ("handler", "first"))
    routes.route("two", "/x", ("handler", "second"))
    assert _rows(tmp_path, routes) == {("/x", "first", "narrowed"), ("/x", "second", "narrowed")}


@pytest.mark.pins("fluent.a-literal-route-order-decides")
def test_literal_orders_decide_between_methods(tmp_path: Path):
    """`order(2)` in the first method and `order(1)` in the second: Vert.x tries the lower
    order first, wherever it was registered."""
    routes = _Routes()
    routes.route("one", "/x", ("order", 2), ("handler", "first"))
    routes.route("two", "/x", ("order", 1), ("handler", "second"))
    assert _rows(tmp_path, routes) == {("/x", "second", "resolved")}


@pytest.mark.pins("fluent.a-last-route-runs-after-the-rest")
def test_a_last_route_runs_after_the_others(tmp_path: Path):
    routes = _Routes()
    routes.route("one", "/x", ("last", None), ("handler", "first"))
    routes.route("two", "/x", ("handler", "second"))
    assert _rows(tmp_path, routes) == {("/x", "second", "resolved")}


def test_one_handler_registered_from_two_methods_is_one_resolved_row(tmp_path: Path):
    """Task 6's key: candidates sharing one handler are one consumer, `resolved` — `narrowed`
    is only between different handlers."""
    routes = _Routes()
    routes.route("one", "/x", ("handler", "same"))
    routes.route("two", "/x", ("handler", "same"))
    assert _rows(tmp_path, routes) == {("/x", "same", "resolved")}


def test_a_chain_after_an_answering_one_in_its_method_is_dropped_but_another_method_stays_narrowed(
    tmp_path: Path,
):
    routes = _Routes()
    routes.route("one", "/x", ("handler", "first"))
    routes.route("one", "/x", ("handler", "shadowed"))
    routes.route("two", "/x", ("handler", "other"))
    assert _rows(tmp_path, routes) == {("/x", "first", "narrowed"), ("/x", "other", "narrowed")}


# --- the words, refused when malformed --------------------------------------------------


def _with(**matches: object):
    catalog = _vertx_web()
    return replace(catalog, matches={**catalog.matches, **matches})


def _without_passes_on(**matches: object):
    catalog = _vertx_web()
    kept = {k: v for k, v in catalog.matches.items() if k != "passes_on"}
    return replace(catalog, matches={**kept, **matches})


@pytest.mark.pins("pass_through.a-malformed-word-is-refused")
@pytest.mark.parametrize(
    ("catalog", "fragment"),
    [
        (lambda: _with(passes_on=[]), "vertx-web.*passes_on"),
        (lambda: _with(passes_on=[{"owner": "a.Context"}]), "vertx-web.*passes_on"),
        (lambda: _with(framework_handlers="io.vertx"), "vertx-web.*framework_handlers"),
        (lambda: _with(handler_methods=[1]), "vertx-web.*handler_methods"),
        (lambda: _without_passes_on(), "vertx-web.*beside `passes_on`"),
    ],
    ids=["empty", "no-method", "packages-not-a-list", "methods-not-names", "alone"],
)
def test_a_malformed_pass_through_word_is_refused_naming_the_file(
    tmp_path: Path, catalog, fragment: str
):
    with pytest.raises(CatalogError, match=fragment):
        _resolve_fluent(tmp_path, [], catalog())


@pytest.mark.pins("fluent.an-order-capture-reads-an-argument-or-last")
def test_an_order_capture_that_is_neither_an_argument_nor_last_is_refused(tmp_path: Path):
    catalog = _vertx_web()
    steps = [
        {**step, "captures": {"order": "first"}} if step["method"] == "order" else step
        for step in catalog.matches["steps"]
    ]
    with pytest.raises(CatalogError, match="vertx-web.*order"):
        _resolve_fluent(tmp_path, [], replace(catalog, matches={**catalog.matches, "steps": steps}))
