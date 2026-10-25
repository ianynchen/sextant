"""gRPC is delivered for Quarkus when every way a Quarkus module serves and calls a gRPC
service, declared the way an application declares them on the classes grpc-java and
Quarkus's Mutiny generator emit, is visible (spec 2026-10-24 §1 ruling 3, §3d-§3e; spec
2026-10-25 §3f).

Its own file beside `test_messaging_quarkus_delivered.py`, which reads the same fixture
module for its SmallRye channels. The generated classes are hand-written stand-ins
(`fixtures/orders-quarkus/.../hello/HelloGrpc.java` says what they stand in for), which keep
the identity calls and the nested classes protoc emits; the Mutiny ones
(`quotes/MutinyQuotesGrpc.java`) keep what Quarkus's generator emits (spec 2026-10-25 §2a).

The fixture serves `acme.hello.Hello` (grpc-java's form) and `acme.quotes.Quotes` (the Mutiny
form), calls both from REST methods, and calls `acme.pricing.Pricing`, which it does not
serve. A call to a service the module serves is a hop to its handler, not an outbound row
(spec 2026-10-25 ruling 1); a call to one it does not serve is an outbound row.

**Not a document check**, except the last test. Real bytecode, real pipeline, assertion on
derived endpoints and on the trace walk.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.query.trace import traces_of
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

QUARKUS = FIXTURES / "orders-quarkus"


@pytest.fixture(scope="module")
def quarkus_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list]:
    """Every gRPC row the Quarkus fixture derives, every open question it files, every
    trace, and the rendered document, from one `analyze` and one `render`."""
    workspace_dir = tmp_path_factory.mktemp("quarkus-grpc")
    compile_fixture(QUARKUS)
    runner = CliRunner()
    for command in ("analyze", "render"):
        result = runner.invoke(
            cli, ["module", command, str(QUARKUS), "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            "endpoints": [
                dict(row) for row in workspace.query("endpoints") if str(row["protocol"]) == "grpc"
            ],
            "open_questions": [dict(row) for row in workspace.query("open_questions")],
            "traces": traces_of(workspace),
            "document": [(workspace_dir / "render" / "architecture.md").read_text()],
        }
    finally:
        workspace.close()


def _trace(quarkus_tables, path: str):
    """The trace of the one root `GET <path>` reaches."""
    [trace] = [
        trace
        for trace in quarkus_tables["traces"]
        if any(
            (identity.protocol, identity.method, identity.path) == ("http", "GET", path)
            for identity in trace.root.identities
        )
    ]
    return trace


@pytest.mark.pins(
    "grpc.a-QUARKUS-client-field-is-an-outbound-service",
    "grpc.an-INTERFACE-client-resolves-through-the-generated-client",
    "grpc.an-injected-WRAPPER-stub-takes-the-identity-it-delegates-to",
)
def test_a_quarkus_grpc_client_field_is_an_outbound_service(quarkus_tables):
    """`PricingClient`'s `@GrpcClient` field, value omitted (the client is named by the
    field, CP-52 rows 2, 5): one outbound, service-level row at the stub's own
    `SERVICE_NAME`, read off `ServiceDescriptor.newBuilder` in its generated outer class —
    `grpc-net-devh.yml`'s read, through `grpc-quarkus-client.yml`. `PricingGrpc` carries
    protoc's own `FileDescriptorSupplier extends BaseDescriptorSupplier` nesting, as
    every full-protobuf generated class does, and that fences nothing (OI-191).

    `PriceQuoter`'s two Mutiny fields (spec 2026-10-25 §3a, §3b) resolve to the same
    service: `@GrpcClient Pricing` through the generated `PricingClient`, the module class
    implementing both it and `MutinyClient`, and `@GrpcClient MutinyPricingStub` through
    the one marked class its nest calls into, `PricingGrpc`. An unread one would be a row
    at the injected type, unresolved. The generated `PricingBean` extends
    `MutinyPricingGrpc`'s base and fences nothing: no module class serves Pricing."""
    grpc_out = {
        (str(r["path"]), r["method"], str(r["resolution"]))
        for r in quarkus_tables["endpoints"]
        if r["catalog_id"] == "grpc-quarkus-client"
    }
    assert grpc_out == {("acme.pricing.Pricing", None, "resolved")}, sorted(grpc_out, key=str)


@pytest.mark.pins("grpc.a-SELF-call-is-not-an-outbound-row")
def test_a_call_to_a_service_this_module_serves_is_no_outbound_row(quarkus_tables):
    """Spec 2026-10-25 ruling 1: `QuotesResource` calls `acme.quotes.Quotes` through a
    blocking stub and through the Mutiny interface, and `HelloResource` calls
    `acme.hello.Hello` through a blocking stub. The module serves both, so none of the three
    is an outbound row: each is a hop (below)."""
    served = [
        r
        for r in quarkus_tables["endpoints"]
        if r["direction"] == "outbound"
        and str(r["path"]).split("/")[0] in ("acme.quotes.Quotes", "acme.hello.Hello")
    ]
    assert served == [], served


@pytest.mark.pins(
    "supertype_derived.a-supertypes-members-are-what-it-INHERITS",
    "grpc.a-QUARKUS-service-implementing-its-interface-is-the-handler",
)
def test_a_quarkus_grpc_service_derives_and_is_corroborated(quarkus_tables):
    """`HelloService` carries `@GrpcService` and extends the generated `HelloImplBase`, whose
    `sayHello` it inherits from `HelloGrpc$AsyncService` as protoc emits it, so
    `grpc-java.yml`'s supertype read derives its RPC and the corroboration
    (`grpc-spring.yml`, CP-52 rows 1, 7) finds it named as a handler.

    `QuotesService` carries `@GrpcService` and implements the Mutiny interface `Quotes`, the
    `delegate` type of the generated `QuotesBean` (spec 2026-10-25 §3b, CP-53): it is the
    handler of the RPC `QuotesBean`'s base delegates to `QuotesGrpc`. No `service_identity`
    question on either."""
    grpc_in = {
        (str(r["path"]), str(r["handler"]).split("/")[-1].split("(")[0], str(r["resolution"]))
        for r in quarkus_tables["endpoints"]
        if r["protocol"] == "grpc" and r["direction"] == "inbound"
    }
    assert grpc_in == {
        ("acme.hello.Hello/SayHello", "HelloService#sayHello", "resolved"),
        ("acme.quotes.Quotes/GetQuote", "QuotesService#getQuote", "resolved"),
    }, sorted(grpc_in)
    assert not [
        q for q in quarkus_tables["open_questions"] if q["question"] == "service_identity"
    ], quarkus_tables["open_questions"]


@pytest.mark.pins(
    "grpc.a-STUB-call-to-a-served-rpc-is-a-hop",
    "trace.the-walk-CROSSES-a-hop-into-the-handler",
)
@pytest.mark.parametrize(
    ("path", "via", "handler"),
    [
        ("/quotes/blocking/{symbol}", "grpc acme.quotes.Quotes/GetQuote", "QuotesService#getQuote"),
        ("/quotes/mutiny/{symbol}", "grpc acme.quotes.Quotes/GetQuote", "QuotesService#getQuote"),
        ("/hello/{name}", "grpc acme.hello.Hello/SayHello", "HelloService#sayHello"),
    ],
)
def test_a_self_call_is_a_hop_to_its_handler(quarkus_tables, path, via, handler):
    """Spec 2026-10-25 ruling 2, §3d: the trace of each REST method that calls a served
    service crosses the stub's call into `ClientCalls` and lands on the handler, the step
    carrying the wire path — the blocking stub directly, the Mutiny interface through
    `QuotesClient`, `MutinyQuotesStub` and the method reference into `QuotesStub`."""
    hops = [step for step in _trace(quarkus_tables, path).steps if step.via is not None]
    assert hops, f"no hop in the trace of GET {path}"
    assert {(step.via, str(step.callee).split("/")[-1].split("(")[0]) for step in hops} == {
        (via, handler)
    }, hops
    assert all(step.stop is None for step in hops), hops


def test_the_document_draws_the_hop(quarkus_tables):
    """The rendered trace of `GET /quotes/blocking/{symbol}` draws the arrow into the
    handler's lifeline, labelled with what the code called and the wire path it left by
    (spec 2026-10-25 §3d)."""
    [document] = quarkus_tables["document"]
    section = document.split("reached by `GET /quotes/blocking/{symbol}`", 1)[1]
    section = section.split("\n- `", 1)[0]
    diagram = section.split("```mermaid", 1)[1].split("```", 1)[0]
    [handler] = [
        line.split()[1] for line in diagram.splitlines() if line.endswith(" as QuotesService")
    ]
    assert (
        f"->>{handler}: blockingUnaryCall (declared ClientCalls)"
        " via grpc acme.quotes.Quotes/GetQuote" in diagram
    ), diagram
