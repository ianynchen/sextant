"""A dispatch send is a trace hop to the handler its value's class reaches (spec 2026-11-05
§1, 2026-11-04 §3c, §3d items 3, 4 and 7): one `hops` row per reachable handler, keyed at the
send's own call site, `protocol` the catalog's, `path` the message class (a constant by its
identity). A class no behavior handles is a stop that names it; a class not read is a stop
that says so. Never a guessed hop.

Read over the two compiled fixtures (`fixtures/orders-actors-pekko`, `-akka`, the same
sources), each analysed once the way a user analyses it, so every assertion is on rows the
real pipeline derives from javac's bytecode (CP-57's shapes). The loader's refusals of a
malformed `dispatch_sends` entry are tested on a catalog file directly.
"""

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from flow_facts import straight_line
from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.query.trace import trace_of
from sextant.application.resolve.dispatch_hops import _keyed_methods, _Reading
from sextant.application.resolve.dispatch_registrations import dispatch_mechanism
from sextant.application.resolve.roots import Root
from sextant.cli.app import cli
from sextant.domain.closed_sets import ConstructKind, OriginTier, RootKind, TraceStop
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, SymbolFact, TypeHeaderFact
from sextant.domain.symbols import bare_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
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
        cases = workspace.query("dispatch_registrations")
        rows = [row for row in workspace.query("hops") if row["protocol"] == "actor"]
    finally:
        workspace.close()
    by_handler = {
        str(case["handler"]): _short(str(case["key_type"] or case["key_value"]))
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


@pytest.mark.pins("dispatch-hops.the-hops-are-WRITTEN")
def test_a_tell_reaches_the_first_matching_handler(hops):
    """`stock.tell(new Stock.Release(sku, false))`: `Stock`'s cases for `Release` are a
    predicated one (`p -> p.urgent()`) and then an unpredicated one. The predicate may decline,
    so it never shadows (spec §3d item 2): both are reached, and the search stops at the
    unpredicated one."""
    assert _from(hops, "Counter#release") == {
        ("Stock$Release", "Stock#onUrgentRelease"),
        ("Stock$Release", "Stock#onRelease"),
    }


@pytest.mark.pins("dispatch-hops.the-value-is-at-its-DECLARED-argument")
def test_an_actor_ask_sends_what_its_request_returns(hops):
    """`context.ask(Stock.Reply.class, stock, timeout, r -> new Stock.Reserve(…), mapper)`:
    the message is argument 3's request, a `Reserve`, which `Stock`'s first case takes; argument
    0 is the reply's class literal, never the message."""
    assert [hop for hop in hops if hop[2] == "Stock$Reserve"] == [
        ("Frontend#onStart", 4, "Stock$Reserve", "Stock#onReserve", "compiler")
    ]


@pytest.mark.pins("dispatch-hops.a-LAMBDA-value-is-read-through-its-RETURNS")
def test_an_ask_lambda_is_read_through_its_return(hops):
    """`entityRefFor(KEY, id).ask(replyTo -> new OrderEntity.Get(id, replyTo), timeout)`:
    the message is the `new` the lambda returns, never the lambda's erased return type."""
    assert _from(hops, "OrderRoutes#summary") == {("OrderEntity$Get", "handler(OrderEntity$Get)")}


@pytest.mark.pins(
    "dispatch-hops.a-DELIVERING-handler-CONTINUES",
    "dispatch-hops.a-MERGED-return-is-a-hop-per-CANDIDATE",
    "dispatch-registrations.a-registration-no-chain-holds-is-its-OWN-group",
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
    "dispatch-hops.a-CONSTRUCTOR-reference-returns-its-OWNER",
    "dispatch-registrations.a-CONSTRUCTOR-reference-is-a-handler",
)
def test_a_constructor_reference_adapter_continues_from_its_super_call(hops):
    """`messageAdapter(Stock.Reply.class, Counted::new)`, the samples' usual adapter: the
    handler is `Counted`'s constructor, which returns no value of its own; the class it makes
    is its owner, a hop from its super-constructor call, the first thing it runs. A `Reply`
    reaches this adapter and the ask's reply mapper alike: which actor a reference holds is
    not read (spec §4)."""
    assert ("Stock$Reply", "Counter$Counted#<init>") in _from(hops, "Stock#onReserve")
    assert _from(hops, "Counter$Counted#<init>") == {("Counter$Counted", "Counter#onCounted")}


@pytest.mark.pins("dispatch-hops.a-CONSTRUCTOR-reference-returns-its-OWNER")
def test_an_ask_by_constructor_reference_sends_its_class(hops):
    """`AskPattern.ask(counter, Report::new, …)`: the request function is the constructor."""
    assert _from(hops, "Counter#report") == {("Counter$Report", "Counter#onReport")}


def test_a_pipe_to_self_reaches_the_handler_of_what_its_mapper_returns(hops):
    assert ("Frontend$Loaded", "handler(Frontend$Loaded)") in _from(hops, "Frontend#onStart")


@pytest.mark.pins("dispatch-hops.a-CONSTANT-is-sent-with-its-IDENTITY")
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


@pytest.mark.pins("dispatch-hops.a-value-NOBODY-handles-is-a-STOP-naming-its-class")
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


def test_an_unread_message_class_is_a_stop(hops):
    """`Relay.forward(Object msg, ActorRef<Object> to) { to.tell(msg); }`: the message is a
    parameter, so its class is not read here. One row, no path and no handler, which is what
    says so; never a hop to every handler. Its evidence stays in D00 §4's closed set: the send
    site is a compiler fact, whatever its argument is."""
    [relay] = [hop for hop in hops if hop[0] == "Relay#forward"]
    assert relay[2:4] == (None, None)
    assert relay[4] == "compiler"


@pytest.mark.pins("dispatch-hops.an-UNREAD-class-is-a-STOP-that-says-so")
def test_an_unread_message_class_reaches_not_even_a_predicate_only_case(tmp_path: Path):
    """A predicate-only case (`onCommand(Predicate, h)`) matches every message whose class is
    known; a message whose class was not read still reaches it nothing: one stop, no path, no
    handler, never a guessed hop. Asked of the hop rule directly, over one such case."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace._connection.execute(
            "INSERT INTO dispatch_registrations VALUES "
            "('m Entity#create(sig_1).#0', 0, NULL, NULL, NULL, true, 'm Entity#onAny(sig_2).', "
            "false, 'first', 'pekko')"
        )
        reading = _Reading(workspace, [])
        unread = reading.hops(
            "m Relay#forward(sig_3).", 0, (None, None, None, "parameter", False), "actor", "pekko"
        )
        read = reading.hops(
            "m Relay#forward(sig_3).", 0, ("Get#", None, None, None, False), "actor", "pekko"
        )
    finally:
        workspace.close()
    assert [(row["path"], row["handler"], row["evidence"]) for row in unread] == [
        (None, None, "compiler")
    ]
    assert [row["handler"] for row in read] == ["m Entity#onAny(sig_2)."]


# `Reserve` implements `Command`, declared as the conformance table declares a JDK type's.
_RESERVE_IS_A_COMMAND = [{"subtype": "Reserve", "supertype": "Command", "by": "test"}]


@pytest.mark.pins("dispatch-hops.under-FIRST-a-DECLARED-type-reads-only-where-no-SUBTYPE-case")
def test_under_first_a_declared_type_is_read_only_where_no_case_names_a_subtype(tmp_path: Path):
    """A value read by its DECLARED type (`tell(cmd)`, `cmd` a `Command` parameter) is a
    `Command` or any subtype. Under `first` its handler is certain only in a group where no
    case names a strict subtype: in `Stock`'s `[Reserve, Command]` the value may be a `Reserve`
    the first case takes, so that group is not read (one stop, no path, no handler), never a
    guessed hop to `onCommand`. In `Audit`'s `[Command]` alone, it is a hop. The same class
    read EXACTLY (`new Command()`) reaches both groups' `Command` cases."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace._connection.execute(
            "INSERT INTO dispatch_registrations VALUES "
            "('m Stock#create(sig_1).#0', 0, 'Reserve#', NULL, NULL, false, "
            "'m Stock#onReserve(sig_2).', false, 'first', 'pekko'), "
            "('m Stock#create(sig_1).#0', 1, 'Command#', NULL, NULL, false, "
            "'m Stock#onCommand(sig_3).', false, 'first', 'pekko'), "
            "('m Audit#create(sig_4).#0', 0, 'Command#', NULL, NULL, false, "
            "'m Audit#onCommand(sig_5).', false, 'first', 'pekko')"
        )
        reading = _Reading(workspace, _RESERVE_IS_A_COMMAND)
        declared = reading.hops(
            "m Relay#forward(sig_6).", 0, ("Command#", None, None, None, True), "actor", "pekko"
        )
        exact = reading.hops(
            "m Relay#forward(sig_6).", 0, ("Command#", None, None, None, False), "actor", "pekko"
        )
    finally:
        workspace.close()
    assert sorted(
        [(row["path"], row["handler"]) for row in declared], key=lambda pair: str(pair)
    ) == [("Command#", "m Audit#onCommand(sig_5)."), (None, None)]
    assert sorted(row["handler"] for row in exact) == [
        "m Audit#onCommand(sig_5).",
        "m Stock#onCommand(sig_3).",
    ]


@pytest.mark.pins("dispatch-hops.under-FIRST-an-EARLIER-UNRELATED-case-leaves-the-group-NOT-READ")
def test_under_first_an_earlier_unrelated_interface_case_leaves_the_group_unread(tmp_path: Path):
    """`[Loggable, Command]` and a value declared `Command`: a `Command` implementing
    `Loggable` is taken by the first case at run time, so the group is not read, never a hop
    to `onCommand`. An earlier case of a class both are known classes unrelated to cannot
    take it (`[Ping, Command]`, `Ping` and `Command` module classes): that group is a hop."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace._connection.execute(
            "INSERT INTO dispatch_registrations VALUES "
            "('m Log#create(sig_1).#0', 0, 'Loggable#', NULL, NULL, false, "
            "'m Log#onLoggable(sig_2).', false, 'first', 'pekko'), "
            "('m Log#create(sig_1).#0', 1, 'Command#', NULL, NULL, false, "
            "'m Log#onCommand(sig_3).', false, 'first', 'pekko')"
        )
        reading = _Reading(workspace, [])
        unrelated = reading.hops(
            "m Relay#forward(sig_6).", 0, ("Command#", None, None, None, True), "actor", "pekko"
        )
        reading._known_classes = frozenset({"Command#", "Loggable#"})
        both_classes = reading.hops(
            "m Relay#forward(sig_6).", 0, ("Command#", None, None, None, True), "actor", "pekko"
        )
    finally:
        workspace.close()
    assert [(row["path"], row["handler"]) for row in unrelated] == [(None, None)]
    assert [(row["path"], row["handler"]) for row in both_classes] == [
        ("Command#", "m Log#onCommand(sig_3).")
    ]


@pytest.mark.pins("dispatch-hops.a-DECLARED-type-with-SUBTYPE-registrations-is-NOT-READ")
def test_under_all_a_declared_type_with_subtype_listeners_adds_the_unread_row(tmp_path: Path):
    """Under `all`, a value declared `Command` certainly reaches the listener of `Command`; a
    listener of `Reserve`, below it, may run too, so the not-read row stands beside the hop.
    With only the subtype's listener there is no "nobody handles it" stop naming `Command`."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace._connection.execute(
            "INSERT INTO dispatch_registrations VALUES "
            "('m A#on(sig_1).', 0, 'Reserve#', NULL, NULL, false, 'm A#on(sig_1).', "
            "false, 'all', 'events'), "
            "('m B#on(sig_2).', 0, 'Command#', NULL, NULL, false, 'm B#on(sig_2).', "
            "false, 'all', 'events')"
        )
        reading = _Reading(workspace, _RESERVE_IS_A_COMMAND)
        both = reading.hops(
            "m P#send(sig_3).", 0, ("Command#", None, None, None, True), "in_process", "events"
        )
        workspace._connection.execute(
            "DELETE FROM dispatch_registrations WHERE \"group\" = 'm B#on(sig_2).'"
        )
        only_below = _Reading(workspace, _RESERVE_IS_A_COMMAND).hops(
            "m P#send(sig_3).", 0, ("Command#", None, None, None, True), "in_process", "events"
        )
    finally:
        workspace.close()
    assert sorted([(row["path"], row["handler"]) for row in both], key=lambda pair: str(pair)) == [
        ("Command#", "m B#on(sig_2)."),
        (None, None),
    ]
    assert [(row["path"], row["handler"]) for row in only_below] == [(None, None)]


@pytest.mark.pins("dispatch-hops.an-UNRELATED-interface-registration-leaves-ALL-NOT-READ")
def test_under_all_an_unrelated_interface_listener_adds_the_unread_row(tmp_path: Path):
    """Under `all`, a value declared `Command` and the one listener of `Loggable`, unrelated:
    a `Command` that is also `Loggable` reaches it, so the send is the not-read row, never a
    stop naming `Command` as handled by nobody. Both known classes, the stop is true."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace._connection.execute(
            "INSERT INTO dispatch_registrations VALUES "
            "('m A#on(sig_1).', 0, 'Loggable#', NULL, NULL, false, 'm A#on(sig_1).', "
            "false, 'all', 'events')"
        )
        reading = _Reading(workspace, [])
        unrelated = reading.hops(
            "m P#send(sig_3).", 0, ("Command#", None, None, None, True), "in_process", "events"
        )
        reading._known_classes = frozenset({"Command#", "Loggable#"})
        classes = reading.hops(
            "m P#send(sig_3).", 0, ("Command#", None, None, None, True), "in_process", "events"
        )
    finally:
        workspace.close()
    assert [(row["path"], row["handler"]) for row in unrelated] == [(None, None)]
    assert [(row["path"], row["handler"]) for row in classes] == [("Command#", None)]


@pytest.mark.pins("dispatch-hops.only-a-MODULE-type-or-a-SUPERCLASS-is-a-KNOWN-class")
def test_a_library_interface_with_super_interfaces_is_no_known_class(tmp_path: Path):
    """A dependency's interface whose header names super-interfaces is in the module's
    ancestry, but it is no class: only module types that are no interface, and types some
    class extends, are known classes."""
    module = "sextant-jvm maven com.acme/shop 1.0.0 "
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/shop/Order.java",
        module_id="com.acme:shop",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    facts = [
        SymbolFact(
            document_id="doc_1",
            symbol=module + "com/acme/shop/Order#",
            construct_kind="class",
            superclass="com/acme/shop/Base#",
            interfaces=["lib/Auditable#"],
        ),
        TypeHeaderFact(
            document_id="doc_1",
            symbol="sextant-jvm maven org.lib/lib 1.0.0 lib/Auditable#",
            construct_kind=ConstructKind.INTERFACE,
            interfaces=["lib/Marker#"],
            origin="org.lib:lib",
            version="1.0.0",
        ),
    ]
    write_fact_file(tmp_path / "facts" / "Order.jsonl", document, straight_line(facts))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace.load_facts(tmp_path / "facts")
        known = _Reading(workspace, [])._classes()
    finally:
        workspace.close()
    assert "com/acme/shop/Order#" in known
    assert "com/acme/shop/Base#" in known
    assert "lib/Auditable#" not in known


# The shipped root-type conformance (`type-models/conformance.yml`): every class is an
# `Object`, so `Get` is assignable to the listener's key.
_ROOT = [{"subtype": "*", "supertype": "java.lang.Object", "by": "JLS 4.10.2"}]


def _two_mechanisms(workspace: DuckDbWorkspace) -> tuple[str, str]:
    """One module running an actor toolkit and Spring application events: a behavior's case
    for `Get` and a listener of `Object`, each written under its own catalog's mechanism, as
    the registration pass writes them. Returns the two mechanisms, read off the shipped
    catalogs rather than spelled here."""
    catalogs = {catalog.id: catalog for catalog in YamlCatalogSource(catalogs_dir()).load()}
    actor = dispatch_mechanism(catalogs["pekko-actor-handlers"])
    events = dispatch_mechanism(catalogs["spring-events"])
    workspace._connection.execute(
        "INSERT INTO dispatch_registrations VALUES "
        "('m Entity#create(sig_1).#0', 0, 'Get#', NULL, NULL, false, 'm Entity#onGet(sig_2).', "
        f"false, 'first', '{actor}'), "
        "('m Any#on(sig_4).', 0, 'java/lang/Object#', NULL, NULL, false, 'm Any#on(sig_4).', "
        f"false, 'all', '{events}')"
    )
    return actor, events


@pytest.mark.pins("dispatch-hops.a-send-reaches-only-its-OWN-mechanism")
def test_a_tell_never_reaches_a_listener_of_object(tmp_path: Path):
    """A module running both: an actor `tell(new Get())` is handled by the behavior's case,
    and never by the application-event listener of `Object`, which a `Get` is assignable to
    but which no actor send can reach."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        actor, _ = _two_mechanisms(workspace)
        reading = _Reading(workspace, _ROOT)
        rows = reading.hops(
            "m Relay#forward(sig_3).", 0, ("Get#", None, None, None, False), "actor", actor
        )
    finally:
        workspace.close()
    assert [row["handler"] for row in rows] == ["m Entity#onGet(sig_2)."]


@pytest.mark.pins("dispatch-hops.a-send-reaches-only-its-OWN-mechanism")
def test_a_published_event_never_reaches_an_actor_case(tmp_path: Path):
    """The other way: `publishEvent(new Get())` reaches the listener of `Object` and never the
    actor case for `Get`, which only a send to that actor runs."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        _, events = _two_mechanisms(workspace)
        reading = _Reading(workspace, _ROOT)
        rows = reading.hops(
            "m Publisher#place(sig_5).", 0, ("Get#", None, None, None, False), "in_process", events
        )
    finally:
        workspace.close()
    assert [row["handler"] for row in rows] == ["m Any#on(sig_4)."]


@pytest.mark.pins("dispatch-hops.a-KEY-is-served-only-by-its-OWN-mechanism")
def test_an_inbound_key_is_served_only_by_its_own_mechanism(tmp_path: Path):
    """An actor key carrying `Get` names the behavior's case as its handler, never the
    application-event listener of `Object`."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        actor, events = _two_mechanisms(workspace)
        reading = _Reading(workspace, _ROOT)
        served = reading.key_handlers("Get#", actor)
        listened = reading.key_handlers("Get#", events)
    finally:
        workspace.close()
    assert served == ["m Entity#onGet(sig_2)."]
    assert listened == ["m Any#on(sig_4)."]


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
        ("actor (key not read)", TraceStop.BOUNDARY)
    ]


@pytest.mark.pins("dispatch-hops.ONE-reset-before-both-writers")
def test_a_second_analysis_replaces_the_hops(tmp_path: Path):
    """`hops` has two writers that only insert; the pipeline resets it once before both,
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
        rows = [tuple(row.values()) for row in workspace.query("hops")]
    finally:
        workspace.close()
    assert rows and len(rows) == len(set(rows))


def _registering(tmp_path: Path) -> None:
    """A catalog registering handlers for mechanism `m`, beside a send or key catalog naming
    it: the loader refuses a mechanism no registering catalog names."""
    (tmp_path / "handlers.yml").write_text(
        "id: handlers\nstyle: fluent\ndispatch: {key: type, match: first, mechanism: m}\n"
        "matches:\n  dispatch_registrations:\n"
        "    - { owner: a.B, method: handle, descriptor: '(Ljava/lang/Class;Ljava/lang/Object;)V', "
        "class_arg: 0, handler_arg: 1 }\n",
        encoding="utf-8",
    )


def _catalog_file(tmp_path: Path, sends: str) -> Path:
    (tmp_path / "sends.yml").write_text(
        "id: sends\ndisplayName: sends\nstyle: fluent\nprotocol: actor\n"
        "dispatch: {key: type, match: first, mechanism: m}\n"
        "requires: [call_site, chain_reconstruction]\n"
        f"matches:\n  roots: []\n  steps: []\n  terminal: [build]\n  dispatch_sends:\n{sends}"
    )
    return tmp_path


@pytest.mark.parametrize(
    ("entry", "refused"),
    [
        (
            "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V' }\n",
            "value_arg",
        ),
        (
            "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V', value_arg: 1 }\n",
            "value_arg: 1",
        ),
        (
            "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V', value_arg: 0, to: 1 }\n",
            "unknown keys",
        ),
        (
            "    - { owner: a.Ref, method: tell, descriptor: 'tell', value_arg: 0 }\n",
            "descriptor",
        ),
    ],
)
def test_a_malformed_send_is_refused_at_load(tmp_path: Path, entry: str, refused: str):
    with pytest.raises(CatalogError, match=refused):
        YamlCatalogSource(_catalog_file(tmp_path, entry)).load()


@pytest.mark.pins("dispatch-hops.a-dispatch-catalog-with-NO-PROTOCOL-is-refused-at-LOAD")
def test_a_dispatch_catalog_with_no_protocol_is_refused_at_load(tmp_path: Path):
    """Every hop a catalog's sends give is written under its `protocol`: one declaring sends and
    no protocol is refused when it is loaded, naming the file, never later by the pass that
    writes the hops."""
    (tmp_path / "sends.yml").write_text(
        "id: sends\ndisplayName: sends\nstyle: fluent\n"
        "dispatch: {key: type, match: first, mechanism: m}\n"
        "requires: [call_site, chain_reconstruction]\n"
        "matches:\n  roots: []\n  steps: []\n  terminal: [build]\n  dispatch_sends:\n"
        "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V', value_arg: 0 }\n"
    )
    with pytest.raises(CatalogError, match="sends.yml.*protocol"):
        YamlCatalogSource(tmp_path).load()


def test_a_send_is_loaded_with_its_value_position(tmp_path: Path):
    _registering(tmp_path)
    [catalog] = [
        catalog
        for catalog in YamlCatalogSource(
            _catalog_file(
                tmp_path,
                "    - { owner: a.Ref, method: tell, descriptor: '(Ljava/lang/Object;)V', "
                "value_arg: 0 }\n",
            )
        ).load()
        if catalog.id == "sends"
    ]
    assert catalog.dispatch_sends == (
        {
            "owner": "a/Ref#",
            "method": "tell",
            "descriptor": "(Ljava/lang/Object;)V",
            "value_arg": 0,
        },
    )


def _keyed_catalog(tmp_path: Path, methods: str) -> Catalog:
    (tmp_path / "keys.yml").write_text(
        "id: keys\ndisplayName: keys\nstyle: single_call\nprotocol: actor\ndirection: inbound\n"
        "dispatch: {mechanism: m}\nrequires: [call_site, string_constants]\n"
        f"matches:\n  owner: a.Registry\n  methods:\n{methods}"
    )
    _registering(tmp_path)
    return next(catalog for catalog in YamlCatalogSource(tmp_path).load() if catalog.id == "keys")


_REGISTER = (
    "    - { name: register, arity: 1, descriptor: '(La/Key;)V', channel_arg: 0,\n"
    "        channel_via: [{ owner: a.Key, method: create, arg: 1VIA }] }\n"
)
_VIA = ", class_arg: 0"


@pytest.mark.parametrize(
    ("methods", "refused"),
    [
        (
            _REGISTER.replace("VIA", _VIA)
            + "    - { name: serve, arity: 1, descriptor: '(La/Key;)V', url_arg: 0 }\n",
            "reading no `channel_arg`",
        ),
        (
            _REGISTER.replace("VIA", _VIA.replace("class_arg: 0", "class_arg: first")),
            "`class_arg: 'first'`",
        ),
        (
            _REGISTER.replace("VIA", _VIA.replace("class_arg: 0", "class_arg: 1")),
            "both the value and its class",
        ),
    ],
)
def test_a_malformed_key_class_is_refused(tmp_path: Path, methods: str, refused: str):
    """A `channel_via` entry's `class_arg` (spec 2026-11-05 §2) is an argument index other
    than the value's, checked where the entry is hoisted; and once a catalog's keys name their
    class, every inbound row reads its key at `channel_arg`, since the key pass replaces them
    all."""
    with pytest.raises(CatalogError, match=refused):
        _keyed_methods(_keyed_catalog(tmp_path, methods))


@pytest.mark.pins("key-handlers.every-INBOUND-row-of-a-keyed-catalog-is-read")
def test_an_inbound_row_reads_the_class_its_producer_names_elsewhere(tmp_path: Path):
    """`class_arg` is the producer's: an outbound row may carry it (it changes nothing there),
    and an inbound row naming only the key's first step still has its class read through the
    hoisted entry — every inbound row of the catalog is keyed, no outbound one is."""
    methods = _REGISTER.replace("VIA", "").replace("arg: 1 }", "arg: 0 }").replace(
        "a.Key", "a.Entity"
    ) + _REGISTER.replace("VIA", _VIA).replace(
        "arity: 1,", "arity: 1, direction: outbound,"
    ).replace("register", "find")
    assert [method["name"] for method in _keyed_methods(_keyed_catalog(tmp_path, methods))] == [
        "register"
    ]
