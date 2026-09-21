"""The three SHIPPED Spring Integration broker catalogs (spec 2026-09-21 §4–§6) on
synthetic facts: each one's near-miss — an input satisfying every conjunct of the rule but
one, deriving NOTHING (GUIDELINES §10) — beside the positive that differs from it in that
one conjunct. The real-bytecode arm is `tests/e2e/test_async_delivered.py` over
`fixtures/spring-integration-probe`; these pin the DECLINE, which no fixture can show.

The facts mirror the emitted grammar the way `test_fluent_registrations.py`'s do; the
descriptors are the ones CP-27 and CP-28 recorded, because the catalogs match by them.
"""

from pathlib import Path

import pytest
from test_call_engines import _MODULE, CATALOGS_DIR, FLUENT_CAPABILITIES, _call, _document
from test_fluent_registrations import BODY, _body_symbol, _lambda

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CALLER = _MODULE + "com/acme/flows/Wiring#flow()."
FLOW = "org/springframework/integration/dsl/IntegrationFlow#"
BUILDER = "org/springframework/integration/dsl/IntegrationFlowBuilder#"
AMQP = "org/springframework/integration/amqp/dsl/Amqp#"
KAFKA = "org/springframework/integration/kafka/dsl/Kafka#"
PUBSUB_ADAPTER = "com/google/cloud/spring/pubsub/integration/inbound/PubSubInboundChannelAdapter#"
PUBSUB_SOURCE = "com/google/cloud/spring/pubsub/integration/inbound/PubSubMessageSource#"

# CP-27 row 8 / row 6 / rows 3, 3b; CP-28 rows 1 and 4.
_AMQP_ADAPTER = "(Lorg/springframework/amqp/rabbit/connection/ConnectionFactory;[Ljava/lang/String;)Lorg/springframework/integration/amqp/dsl/AmqpInboundChannelAdapterSMLCSpec;"
_AMQP_GATEWAY = "(Lorg/springframework/amqp/rabbit/connection/ConnectionFactory;[Ljava/lang/String;)Lorg/springframework/integration/amqp/dsl/AmqpInboundGatewaySMLCSpec;"
_KAFKA_ADAPTER = "(Lorg/springframework/kafka/core/ConsumerFactory;[Ljava/lang/String;)Lorg/springframework/integration/kafka/dsl/KafkaMessageDrivenChannelAdapterSpec$KafkaMessageDrivenChannelAdapterListenerContainerSpec;"
_FROM_SPEC = "(Lorg/springframework/integration/dsl/MessageProducerSpec;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder;"
_HANDLE = "(Ljava/lang/Class;Lorg/springframework/integration/core/GenericHandler;)Lorg/springframework/integration/dsl/BaseIntegrationFlowDefinition;"
_GET = "()Lorg/springframework/integration/dsl/StandardIntegrationFlow;"
_PUBSUB_INIT = "(Lcom/google/cloud/spring/pubsub/core/subscriber/PubSubSubscriberOperations;Ljava/lang/String;)V"
# CP-27 rows 1 and 3.
_FROM_STRING = "(Ljava/lang/String;)Lorg/springframework/integration/dsl/IntegrationFlowBuilder;"
_HANDLE_REACTIVE = "(Lorg/springframework/messaging/ReactiveMessageHandler;)Lorg/springframework/integration/dsl/IntegrationFlow;"


def _shipped(catalog_id: str) -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == catalog_id)


def _site(
    owner: str,
    name: str,
    descriptor: str,
    ordinal: int,
    *,
    receiver: int | None,
    result: int | None,
    arguments: list[CallArgument] | None = None,
    invoke_kind: str = "virtual",
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=CALLER,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind=invoke_kind,
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=arguments or [],
    )


def _flow_after(source_result: int) -> list[CallSiteFact]:
    """`IntegrationFlow.from(<the spec>).handle(String.class, lambda).get()` — the flow a
    source spec's chain continues into, compiled against `IntegrationFlowBuilder` as
    CP-27 row 16 measured."""
    return [
        _site(
            FLOW,
            "from",
            _FROM_SPEC,
            1,
            receiver=None,
            result=11,
            arguments=[CallArgument(kind="unresolved", source=source_result)],
            invoke_kind="static",
        ),
        _site(
            BUILDER,
            "handle",
            _HANDLE,
            2,
            receiver=11,
            result=12,
            arguments=[CallArgument(kind="class", symbol="java/lang/String#"), _lambda()],
        ),
        _site(BUILDER, "get", _GET, 3, receiver=12, result=13),
        _body_symbol(),
    ]


def _factory(owner: str, name: str, descriptor: str, factory_type: str) -> CallSiteFact:
    """`<owner>.<name>(factory, "orders.q")` — a static factory, result 10, one queue."""
    return _site(
        owner,
        name,
        descriptor,
        0,
        receiver=None,
        result=10,
        arguments=[
            CallArgument(kind="instance", source=2, symbol=factory_type),
            CallArgument(kind="array", elements=[CallArgument(kind="string", value="orders.q")]),
        ],
        invoke_kind="static",
    )


def _derived(tmp_path: Path, facts: list, catalog_id: str) -> tuple[list[dict], list[dict]]:
    """The endpoint rows and the `channel_bindings` edges the shipped catalog derives."""
    write_fact_file(tmp_path / "facts" / "Wiring.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_shipped(catalog_id)], capabilities=FLUENT_CAPABILITIES)
    assert skipped == []
    rows = [dict(row) for row in workspace.query("endpoints")]
    bindings = [dict(row) for row in workspace.query("channel_bindings")]
    workspace.close()
    return rows, bindings


def _rows(tmp_path: Path, facts: list, catalog_id: str) -> list[dict]:
    return _derived(tmp_path, facts, catalog_id)[0]


# --- AMQP -----------------------------------------------------------------------------


def test_an_amqp_source_spec_handed_to_from_derives_the_flows_handler(tmp_path: Path):
    """The positive: `Amqp.inboundAdapter(cf, "orders.q")` → `from` → `handle(lambda)` —
    one inbound row, the queue, the lambda's body, `caller` the flow method."""
    facts = [
        _factory(
            AMQP,
            "inboundAdapter",
            _AMQP_ADAPTER,
            "org/springframework/amqp/rabbit/connection/ConnectionFactory#",
        ),
        *_flow_after(10),
    ]
    rows = _rows(tmp_path, facts, "spring-integration-amqp")

    assert [(r["direction"], r["path"], r["handler"], r["resolution"]) for r in rows] == [
        ("inbound", "orders.q", _MODULE + BODY, "resolved")
    ]


@pytest.mark.declines("spring-integration-amqp")
@pytest.mark.pins("fluent.root-is-a-declared-request-starter")
def test_an_amqp_inbound_gateway_is_not_an_adapter_and_derives_nothing(tmp_path: Path):
    """The near-miss: `Amqp.inboundGateway(cf, "orders.q")` — the same owner, the same
    parameter types (CP-27 row 8 lists it among the factories this catalog does not
    read), handed to the same flow. A request-reply gateway is a registration of another
    kind, stated outside the catalog's slice; rooting on any factory of the owner would
    publish it as an adapter's row. It differs from the positive in the method name
    alone."""
    facts = [
        _factory(
            AMQP,
            "inboundGateway",
            _AMQP_GATEWAY,
            "org/springframework/amqp/rabbit/connection/ConnectionFactory#",
        ),
        *_flow_after(10),
    ]

    assert _rows(tmp_path, facts, "spring-integration-amqp") == []


# --- Kafka ----------------------------------------------------------------------------


def test_a_kafka_source_spec_handed_to_from_derives_the_flows_handler(tmp_path: Path):
    facts = [
        _factory(
            KAFKA,
            "messageDrivenChannelAdapter",
            _KAFKA_ADAPTER,
            "org/springframework/kafka/core/ConsumerFactory#",
        ),
        *_flow_after(10),
    ]
    rows = _rows(tmp_path, facts, "spring-integration-kafka")

    assert [(r["direction"], r["path"], r["handler"], r["resolution"]) for r in rows] == [
        ("inbound", "orders.q", _MODULE + BODY, "resolved")
    ]


@pytest.mark.declines("spring-integration-kafka")
@pytest.mark.pins("fluent.root-owner-is-the-declared-type")
def test_a_helpers_factory_of_the_same_name_and_shape_derives_nothing(tmp_path: Path):
    """The near-miss: a module's own `KafkaSources.messageDrivenChannelAdapter(cf,
    "orders.q")` — the framework factory's name and parameter types on a type the catalog
    knows nothing about, handed to the same flow. What such a helper builds is its own
    business (a spec, a wrapper, a stub); rooting on the name would publish its argument
    as a Kafka topic at `resolved`/`compiler`. It differs from the positive in the owner
    alone."""
    facts = [
        _factory(
            "com/acme/flows/KafkaSources#",
            "messageDrivenChannelAdapter",
            _KAFKA_ADAPTER,
            "org/springframework/kafka/core/ConsumerFactory#",
        ),
        *_flow_after(10),
    ]

    assert _rows(tmp_path, facts, "spring-integration-kafka") == []


# --- Pub/Sub --------------------------------------------------------------------------


def _constructed(owner: str, calls: list[tuple[str, list[CallArgument]]] = ()) -> list:
    """`new <owner>(template, "orders-sub")` and void setters on it (receiver 5)."""
    facts = [
        _site(
            owner,
            "<init>",
            _PUBSUB_INIT,
            0,
            receiver=5,
            result=None,
            arguments=[
                CallArgument(
                    kind="instance",
                    source=2,
                    symbol="com/google/cloud/spring/pubsub/core/PubSubTemplate#",
                ),
                CallArgument(kind="string", value="orders-sub"),
            ],
            invoke_kind="special",
        )
    ]
    for ordinal, (name, arguments) in enumerate(calls, start=1):
        facts.append(
            _call(CALLER, owner, name, ordinal, receiver=5, result=None, arguments=arguments)
        )
    return facts


def test_a_pubsub_adapter_derives_its_subscription(tmp_path: Path):
    """The positive: `new PubSubInboundChannelAdapter(template, "orders-sub")` with no
    channel named — the adapter's own row, `handler` NULL, resolved."""
    rows = _rows(tmp_path, _constructed(PUBSUB_ADAPTER), "spring-integration-pubsub")

    assert [(r["direction"], r["path"], r["handler"], r["resolution"]) for r in rows] == [
        ("inbound", "orders-sub", None, "resolved")
    ]


@pytest.mark.declines("spring-integration-pubsub")
@pytest.mark.pins("fluent.root-owner-is-the-declared-type")
def test_a_pubsub_message_source_is_not_the_adapter_and_derives_nothing(tmp_path: Path):
    """The near-miss: `new PubSubMessageSource(template, "orders-sub")` — the adapter's
    exact constructor shape (CP-28 row 4) on another type: a polled `MessageSource`,
    consumed through `from(MessageSource, Consumer)`, which spec §5 states as a boundary.
    Rooting on the constructor's shape alone would publish it as the adapter's row. It
    differs from the positive in the owner alone."""
    assert _rows(tmp_path, _constructed(PUBSUB_SOURCE), "spring-integration-pubsub") == []


# --- the flow that ends without `get()` (every broker catalog) --------------------------


@pytest.mark.parametrize(
    "catalog_id",
    ["spring-integration-kafka", "spring-integration-amqp", "spring-integration-pubsub"],
)
def test_a_channel_sourced_flow_ending_in_handle_reactive_is_the_channels_reader(
    tmp_path: Path, catalog_id: str
):
    """Final fix wave, item 7(b). `IntegrationFlow.from("orders.ch").handleReactive(h)` —
    `handleReactive` returns the finished flow (spring-integration-core 6.2.4, CP-27 row
    3), so no `get()` follows and, with `get` the only terminal, the chain never derived:
    no `read_by`, the handler lost. Each broker catalog declares `handleReactive` a
    terminal beside `get`, and the flow writes `read_by(orders.ch, h)` and no row, exactly
    as `from("orders.ch").handle(h).get()` does."""
    facts = [
        _site(
            FLOW,
            "from",
            _FROM_STRING,
            0,
            receiver=None,
            result=11,
            arguments=[CallArgument(kind="string", value="orders.ch")],
            invoke_kind="static",
        ),
        _site(
            BUILDER,
            "handleReactive",
            _HANDLE_REACTIVE,
            1,
            receiver=11,
            result=12,
            arguments=[_lambda()],
        ),
        _body_symbol(),
    ]
    rows, bindings = _derived(tmp_path, facts, catalog_id)

    assert rows == []
    assert [(b["role"], b["channel"], b["symbol"]) for b in bindings] == [
        ("read_by", "orders.ch", _MODULE + BODY)
    ]
