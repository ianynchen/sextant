"""gRPC is delivered for Quarkus when a Quarkus module's `@GrpcService` service and
`@GrpcClient` client, declared the way an application declares them on grpc-java's
generated classes, are visible (spec 2026-10-24 §1 ruling 3, §3d-§3e).

Its own file beside `test_messaging_quarkus_delivered.py`, which reads the same fixture
module for its SmallRye channels. The generated classes are hand-written stand-ins
(`fixtures/orders-quarkus/.../hello/HelloGrpc.java` says what they stand in for), which keep
the identity calls and the nested classes protoc emits.

Quarkus's Mutiny forms, a service `implements <Service>` and a client field typed
`<Service>`, are NOT read (`quarkus-grpc-mutiny`, OI-192), and nothing here pins them.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

QUARKUS = FIXTURES / "orders-quarkus"


@pytest.fixture(scope="module")
def quarkus_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    """Every gRPC row the Quarkus fixture derives, and every open question it files,
    analysed once."""
    workspace_dir = tmp_path_factory.mktemp("quarkus-grpc")
    compile_fixture(QUARKUS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(QUARKUS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            "endpoints": [
                dict(row) for row in workspace.query("endpoints") if str(row["protocol"]) == "grpc"
            ],
            "open_questions": [dict(row) for row in workspace.query("open_questions")],
        }
    finally:
        workspace.close()


@pytest.mark.pins(
    "grpc.a-QUARKUS-client-field-is-an-outbound-service",
    "injected_client.a-GENERATED-class-own-nesting-does-not-fence",
)
def test_a_quarkus_grpc_client_field_is_an_outbound_service(quarkus_tables):
    """`PricingClient`'s `@GrpcClient` field, value omitted (the client is named by the
    field, CP-52 rows 2, 5): one outbound, service-level row at the stub's own
    `SERVICE_NAME`, read off `ServiceDescriptor.newBuilder` in its generated outer class —
    `grpc-net-devh.yml`'s read, through `grpc-quarkus-client.yml`. `PricingGrpc` carries
    protoc's own `FileDescriptorSupplier extends BaseDescriptorSupplier` nesting, as
    every full-protobuf generated class does, and that fences nothing (OI-191)."""
    grpc_out = {
        (str(r["path"]), r["method"], str(r["resolution"]))
        for r in quarkus_tables["endpoints"]
        if r["catalog_id"] == "grpc-quarkus-client"
    }
    assert grpc_out == {("acme.pricing.Pricing", None, "resolved")}, sorted(grpc_out, key=str)


def test_a_quarkus_grpc_service_derives_and_is_corroborated(quarkus_tables):
    """`HelloService` carries `@GrpcService` and extends the generated `HelloImplBase`, so
    `grpc-java.yml`'s supertype read derives its RPC and the corroboration
    (`grpc-spring.yml`, CP-52 rows 1, 7) finds it named as a handler: no
    `service_identity` question."""
    grpc_in = {
        (str(r["path"]), str(r["resolution"]))
        for r in quarkus_tables["endpoints"]
        if r["protocol"] == "grpc" and r["direction"] == "inbound"
    }
    assert grpc_in == {("acme.hello.Hello/SayHello", "resolved")}, sorted(grpc_in)
    assert not [
        q for q in quarkus_tables["open_questions"] if q["question"] == "service_identity"
    ], quarkus_tables["open_questions"]
