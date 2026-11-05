"""An actor message send is a trace hop to the handler its message's class reaches (spec
2026-11-04 §3c, §3d items 3, 4 and 7): one `rpc_hops` row per reachable handler, keyed at the
send's own call site, `protocol` the catalog's, `path` the message class (a constant by its
identity). A class no behavior handles is a stop that names it; a class not read is a stop
that says so. Never a guessed hop.

Read over the two compiled fixtures (`fixtures/orders-actors-pekko`, `-akka`, the same
sources), each analysed once the way a user analyses it, so every assertion is on rows the
real pipeline derives from javac's bytecode (CP-57's shapes). The loader's refusals of a
malformed `message_sends` entry are tested on a catalog file directly.
"""

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.query.trace import trace_of
from sextant.application.resolve.message_hops import _keyed_methods, _paired
from sextant.application.resolve.roots import Root
from sextant.cli.app import cli
from sextant.domain.closed_sets import RootKind, TraceStop
from sextant.domain.symbols import bare_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_FAMILIES = ("orders-actors-pekko", "orders-actors-akka")


@pytest.fixture(scope="module", params=_FAMILIES)
def analyzed(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = FIXTURES / request.param
    workspace_dir = tmp_path_factory.mktemp(request.param)
    compile_fixture(root)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(root), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    return workspace_dir / "workspace.duckdb"


def _short(symbol: str) -> str:
    """`Class#method` (a type: `Class`), module, package and signature left out; a lambda's hash and index
    dropped, because javac names a synthetic body with a hash that differs between the two
    families' builds."""
    name = bare_descriptor(symbol).rsplit("/", 1)[-1].split("(")[0].removesuffix("#")
    return re.sub(r"(#lambda\$[^$]+)\$.*", r"\1", name)


@pytest.fixture(scope="module")
def hops(analyzed: Path) -> set[tuple]:
    """Every `actor` hop one fixture gives: `(caller, ordinal, path, handler, evidence)`,
    each symbol shortened. A lambda that is a case's handler is named by the case:
    `handler(<class>)`, so two lambdas in one method stay apart."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        cases = workspace.query("message_handlers")
        rows = [row for row in workspace.query("rpc_hops") if row["protocol"] == "actor"]
    finally:
        workspace.close()
    by_handler = {
        str(case["handler"]): _short(str(case["message_type"] or case["message_value"]))
        for case in cases
        if case["handler"] is not None and "#lambda$" in str(case["handler"])
    }

    def named(symbol: object) -> str | None:
        if symbol is None:
            return None
        if str(symbol) in by_handler:
            return f"handler({by_handler[str(symbol)]})"
        return _short(str(symbol))

    return {
        (
            named(row["caller"]),
            row["ordinal"],
            None if row["path"] is None else _short(str(row["path"])),
            named(row["handler"]),
            row["evidence"],
        )
        for row in rows
    }


def _from(hops: set[tuple], caller: str) -> set[tuple]:
    return {(path, handler) for at, _, path, handler, _ in hops if at == caller}


@pytest.mark.pins("message-hops.the-hops-are-WRITTEN")
def test_a_tell_reaches_the_first_matching_handler(hops):
    """`stock.tell(new Stock.Release(sku, false))`: `Stock`'s cases for `Release` are a
    predicated one (`p -> p.urgent()`) and then an unpredicated one. The predicate may decline,
    so it never shadows (spec §3d item 2): both are reached, and the search stops at the
    unpredicated one."""
    assert _from(hops, "Counter#release") == {
        ("Stock$Release", "Stock#onUrgentRelease"),
        ("Stock$Release", "Stock#onRelease"),
    }


@pytest.mark.pins("message-hops.the-message-is-at-its-DECLARED-argument")
def test_an_actor_ask_sends_what_its_request_returns(hops):
    """`context.ask(Stock.Reply.class, stock, timeout, r -> new Stock.Reserve(…), mapper)`:
    the message is argument 3's request, a `Reserve`, which `Stock`'s first case takes; argument
    0 is the reply's class literal, never the message."""
    assert [hop for hop in hops if hop[2] == "Stock$Reserve"] == [
        ("Frontend#onStart", 4, "Stock$Reserve", "Stock#onReserve", "compiler")
    ]


@pytest.mark.pins("message-hops.a-LAMBDA-message-is-read-through-its-RETURNS")
def test_an_ask_lambda_is_read_through_its_return(hops):
    """`entityRefFor(KEY, id).ask(replyTo -> new OrderEntity.Get(id, replyTo), timeout)`:
    the message is the `new` the lambda returns, never the lambda's erased return type."""
    assert _from(hops, "OrderRoutes#summary") == {("OrderEntity$Get", "handler(OrderEntity$Get)")}


@pytest.mark.pins(
    "message-hops.a-DELIVERING-handler-CONTINUES",
    "message-hops.a-MERGED-return-is-a-hop-per-CANDIDATE",
    "message-handlers.a-registration-no-chain-holds-is-its-OWN-behavior",
)
def test_a_two_return_mapper_gives_a_hop_per_class(hops):
    """`context.ask`'s reply mapper `(res, ex) -> res != null ? new Reserved(res) : new
    Failed(ex)` is a behavior of its own, reached by the reply class `Stock.Reply`; it
    delivers, so each class it returns is a hop from that return's own `new`."""
    assert ("Stock$Reply", "handler(Stock$Reply)") in _from(hops, "Stock#onReserve")
    assert _from(hops, "handler(Stock$Reply)") == {
        ("Frontend$Reserved", "handler(Frontend$Reserved)"),
        ("Frontend$Failed", "handler(Frontend$Failed)"),
    }


def test_an_adapter_continues_to_the_handler_of_what_it_returns(hops):
    """`messageAdapter(Receptionist.Listing.class, l -> new Workers(l))`: the adapter's
    lambda returns a `Workers`, delivered to `Frontend` itself."""
    assert _from(hops, "handler(Receptionist$Listing)") == {
        ("Frontend$Workers", "Frontend#onWorkers")
    }


@pytest.mark.pins(
    "message-hops.a-CONSTRUCTOR-reference-returns-its-OWNER",
    "message-handlers.a-CONSTRUCTOR-reference-is-a-handler",
)
def test_a_constructor_reference_adapter_continues_from_its_super_call(hops):
    """`messageAdapter(Stock.Reply.class, Counted::new)`, the samples' usual adapter: the
    handler is `Counted`'s constructor, which returns no value of its own; the class it makes
    is its owner, a hop from its super-constructor call, the first thing it runs. A `Reply`
    reaches this adapter and the ask's reply mapper alike: which actor a reference holds is
    not read (spec §4)."""
    assert ("Stock$Reply", "Counter$Counted#<init>") in _from(hops, "Stock#onReserve")
    assert _from(hops, "Counter$Counted#<init>") == {("Counter$Counted", "Counter#onCounted")}


@pytest.mark.pins("message-hops.a-CONSTRUCTOR-reference-returns-its-OWNER")
def test_an_ask_by_constructor_reference_sends_its_class(hops):
    """`AskPattern.ask(counter, Report::new, …)`: the request function is the constructor."""
    assert _from(hops, "Counter#report") == {("Counter$Report", "Counter#onReport")}


def test_a_pipe_to_self_reaches_the_handler_of_what_its_mapper_returns(hops):
    assert ("Frontend$Loaded", "handler(Frontend$Loaded)") in _from(hops, "Frontend#onStart")


@pytest.mark.pins("message-hops.a-CONSTANT-is-sent-with-its-IDENTITY")
def test_a_timer_is_a_send_to_the_actor_itself(hops):
    """`timers.startTimerWithFixedDelay(Tick.INSTANCE, …)`: the key-less form, message at
    argument 0, a constant read by identity, so it reaches `onMessageEquals(Tick.INSTANCE,
    …)` and the path is the constant itself."""
    assert _from(hops, "Stock#lambda$create") >= {("Stock$Tick#INSTANCE.", "Stock#onTick")}


def test_a_receive_timeout_is_a_send_to_the_actor_itself(hops):
    """`getContext().setReceiveTimeout(Duration.ofSeconds(3), Timeout.INSTANCE)` (the
    `pekko-sample-cluster-java` `StatsAggregator` shape): after that long without a message the
    actor tells itself argument 1, so the constant reaches its `onMessageEquals` case. Argument
    0, the duration, is never the message."""
    assert _from(hops, "Session#<init>") == {("Session$Timeout#INSTANCE.", "Session#onTimeout")}


@pytest.mark.pins("message-hops.a-message-NOBODY-handles-is-a-STOP-naming-its-class")
def test_a_reply_nobody_handles_is_a_stop(hops):
    """`replyTo.tell(new Summary(…))`: no behavior here takes a `Summary` (the asker reads it
    off its future), so the send is a stop naming the class, with no handler."""
    assert _from(hops, "OrderEntity#onGet") == {("OrderEntity$Summary", None)}


def test_a_pubsub_message_reaches_its_subscriber_and_the_envelope_is_a_stop(hops):
    """`new Publish("prices", new Price(…))` carries a `Price`, which `ClassicBroker`'s own
    `match(Price.class, …)` takes; the `Publish` itself is told to the mediator, a system
    actor whose behavior is not here, so that send stops naming `Publish`."""
    assert _from(hops, "ClassicBroker#announce") == {
        ("ClassicBroker$Price", "ClassicBroker#onPrice"),
        ("DistributedPubSubMediator$Publish", None),
        ("DistributedPubSubMediator$Send", None),
    }


@pytest.mark.pins("message-hops.an-UNREAD-class-is-a-STOP-that-says-so")
def test_an_unread_message_class_is_a_stop(hops):
    """`Relay.forward(Object msg, ActorRef<Object> to) { to.tell(msg); }`: the message is a
    parameter, so its class is not read here. One row, no path and no handler, and its
    evidence says why; never a hop to every handler."""
    [relay] = [hop for hop in hops if hop[0] == "Relay#forward"]
    assert relay[2:4] == (None, None)
    assert relay[4] == "message class not read: parameter"


def test_a_trace_crosses_the_ask(analyzed: Path):
    """From `OrderRoutes#summary` the walk used to end at `EntityRef#ask`, a library body.
    The hop takes it to `OrderEntity`'s handler for `Get` and on through `onGet`, whose reply
    nobody here handles: a boundary that still names the class."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        [summary] = [
            str(row["method"])
            for row in workspace.query("method_returns")
            if "OrderRoutes#summary(" in str(row["method"])
        ]
        trace = trace_of(workspace, Root(handler=summary, kind=RootKind.INBOUND_ENDPOINT))
    finally:
        workspace.close()
    hopped = [step for step in trace.steps if step.via is not None]
    assert [
        (_short(str(step.callee)) if step.callee else None, step.via, step.stop) for step in hopped
    ] == [
        ("OrderEntity#lambda$create", "actor com/acme/actors/OrderEntity$Get#", None),
        (None, "actor com/acme/actors/OrderEntity$Summary#", TraceStop.BOUNDARY),
    ]
    assert "OrderEntity#onGet" in [_short(str(step.callee)) for step in trace.steps if step.callee]


@pytest.mark.pins("trace.an-UNREAD-hop-says-why-in-its-via")
def test_a_trace_names_an_unread_class(analyzed: Path):
    """The stop a parameter's message makes says so in the step itself, not `actor None`."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        [forward] = [
            str(row["method"])
            for row in workspace.query("method_returns")
            if "Relay#forward(" in str(row["method"])
        ]
        trace = trace_of(workspace, Root(handler=forward, kind=RootKind.INBOUND_ENDPOINT))
    finally:
        workspace.close()
    assert [(step.via, step.stop) for step in trace.steps] == [
        ("actor (message class not read: parameter)", TraceStop.BOUNDARY)
    ]


@pytest.mark.pins("message-hops.ONE-reset-before-both-writers")
def test_a_second_analysis_replaces_the_hops(tmp_path: Path):
    """`rpc_hops` has two writers that only insert; the pipeline resets it once before both,
    so analysing again leaves one set of rows, not two."""
    root = FIXTURES / _FAMILIES[0]
    compile_fixture(root)
    for _ in range(2):
        result = CliRunner().invoke(
            cli, ["module", "analyze", str(root), "--workspace", str(tmp_path)]
        )
        assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        rows = [tuple(row.values()) for row in workspace.query("rpc_hops")]
    finally:
        workspace.close()
    assert rows and len(rows) == len(set(rows))


def _catalog_file(tmp_path: Path, sends: str) -> Path:
    (tmp_path / "sends.yml").write_text(
        "id: sends\ndisplayName: sends\nstyle: message_handlers\nprotocol: actor\n"
        "requires: [call_site, chain_reconstruction]\n"
        f"matches:\n  roots: []\n  steps: []\n  terminal: [build]\n  message_sends:\n{sends}"
    )
    return tmp_path


@pytest.mark.parametrize(
    ("entry", "refused"),
    [
        (
            "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V' }\n",
            "message_arg",
        ),
        (
            "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V', message_arg: 1 }\n",
            "message_arg: 1",
        ),
        (
            "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V', message_arg: 0, to: 1 }\n",
            "unknown keys",
        ),
        (
            "    - { owner: a.Ref, method: tell, descriptor: 'tell', message_arg: 0 }\n",
            "descriptor",
        ),
    ],
)
def test_a_malformed_send_is_refused_at_load(tmp_path: Path, entry: str, refused: str):
    with pytest.raises(CatalogError, match=refused):
        YamlCatalogSource(_catalog_file(tmp_path, entry)).load()


def test_a_send_is_loaded_with_its_message_position(tmp_path: Path):
    [catalog] = YamlCatalogSource(
        _catalog_file(
            tmp_path,
            "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V', message_arg: 0 }\n",
        )
    ).load()
    assert catalog.message_sends == (
        {
            "owner": "a/Ref#",
            "method": "tell",
            "descriptor": "(Ljava/lang/Object;)V",
            "message_arg": 0,
        },
    )


@pytest.mark.pins("key-handlers.a-key-takes-the-class-read-on-its-OWN-path")
def test_a_key_takes_only_the_class_read_on_its_own_path():
    """Two keys one helper builds (`ServiceKey.create(c, name)` with both from its callers):
    the address walk and the class walk each give one path per caller, and a key takes the
    class read on its own path, where one path extends the other (the crossings both made are
    the nearest, the end of `Binding.path`). Never the other caller's class. A site whose
    address no path read is one row with no address, carrying every class read there."""
    named = [(("x",), "a"), (("y",), "b")]
    read = [(("x",), "A#"), (("outer", "y"), "B#")]
    assert _paired(named, read) == {"a": {"A#"}, "b": {"B#"}}
    assert _paired(named, []) == {"a": {None}, "b": {None}}
    assert _paired([], read) == {None: {"A#", "B#"}}


def _keyed_catalog(tmp_path: Path, methods: str) -> Catalog:
    (tmp_path / "keys.yml").write_text(
        "id: keys\ndisplayName: keys\nstyle: single_call\nprotocol: actor\ndirection: inbound\n"
        "requires: [call_site, string_constants]\n"
        f"matches:\n  owner: a.Registry\n  methods:\n{methods}"
    )
    [catalog] = YamlCatalogSource(tmp_path).load()
    return catalog


_REGISTER = (
    "    - { name: register, arity: 1, descriptor: '(La/Key;)V', channel_arg: 0,\n"
    "        channel_via: [{ owner: a.Key, method: create, arg: 1 }]VIA }\n"
)
_VIA = ",\n        message_class_via: [{ owner: a.Key, method: create, arg: 0 }]"


@pytest.mark.parametrize(
    ("methods", "refused"),
    [
        (
            _REGISTER.replace("VIA", _VIA)
            + _REGISTER.replace("VIA", "").replace("register", "serve"),
            "declaring no `message_class_via` beside one that does",
        ),
        (
            _REGISTER.replace("VIA", _VIA).replace("arity: 1,", "arity: 1, direction: outbound,"),
            "not inbound",
        ),
        (
            _REGISTER.replace("VIA", _VIA.replace("arg: 0", "arg: first")),
            "non-empty list",
        ),
    ],
)
def test_a_malformed_message_class_via_is_refused(tmp_path: Path, methods: str, refused: str):
    with pytest.raises(CatalogError, match=refused):
        _keyed_methods(_keyed_catalog(tmp_path, methods))


def test_an_outbound_row_needs_no_message_class_via(tmp_path: Path):
    methods = _REGISTER.replace("VIA", _VIA) + _REGISTER.replace("VIA", "").replace(
        "arity: 1,", "arity: 1, direction: outbound,"
    ).replace("register", "find")
    assert [method["name"] for method in _keyed_methods(_keyed_catalog(tmp_path, methods))] == [
        "register"
    ]
