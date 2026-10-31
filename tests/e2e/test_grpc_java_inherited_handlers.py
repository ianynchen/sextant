"""A grpc-java service is read on what protoc REALLY emits: the handlers a generated
`<Service>ImplBase` exposes are default methods of its nested `<Service>Grpc$AsyncService`
interface, and the base class itself declares only its constructor and `bindService`.

`fixtures/grpc-probe` is that generated code, compiled by protoc and protoc-gen-grpc-java
from `order_service.proto` (1.62.2 when this test was written, 1.81.0 since 2026-10-30; the
shape is the same at both, `scripts/probes/cp3_cp8_grpc_facts.md`). `OrderServiceImpl extends OrderServiceImplBase` overrides
`getOrder`, which the base INHERITS from `AsyncService`. Measured before this test: the module
derived only the `.proto`'s row, with handler NULL, and no `supertype_derived` row, because the
engine looked for `getOrder` on the base class alone.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

GRPC_PROBE = FIXTURES / "grpc-probe"


@pytest.fixture(scope="module")
def probe_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    workspace_dir = tmp_path_factory.mktemp("grpc-probe")
    compile_fixture(GRPC_PROBE)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(GRPC_PROBE), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            "endpoints": [dict(row) for row in workspace.query("endpoints")],
            "open_questions": [dict(row) for row in workspace.query("open_questions")],
        }
    finally:
        workspace.close()


@pytest.mark.pins("supertype_derived.a-supertypes-members-are-what-it-INHERITS")
def test_an_rpc_inherited_from_the_generated_interface_names_its_handler(probe_tables):
    """The one RPC, at its wire identity, with the implementer's override as its handler.
    `schema_operations` merges the `.proto`'s row into the same identity rather than adding
    a handlerless row beside it. The bound `AsyncService` class is the test below."""
    rows = [
        (str(r["path"]), str(r["handler"]).rsplit(" ", 1)[-1], str(r["resolution"]))
        for r in probe_tables["endpoints"]
        if r["protocol"] == "grpc"
    ]
    assert [row for row in rows if "AsyncImpl" not in row[1]] == [
        (
            "sextant.grpcprobe.OrderService/GetOrder",
            "com/example/grpcprobe/OrderServiceImpl#getOrder(sig_ba59a558).",
            "resolved",
        )
    ], rows
    assert not [q for q in probe_tables["open_questions"] if q["question"] == "service_identity"], (
        probe_tables["open_questions"]
    )


@pytest.mark.pins("supertype_derived.an-AsyncService-implementation-is-served-once-BOUND")
def test_a_class_implementing_the_generated_interface_is_a_handler_once_bound(probe_tables):
    """`OrderServiceAsyncImpl implements OrderServiceGrpc.AsyncService` and
    `serve` hands a new one to `OrderServiceGrpc.bindService` (ruled 2026-10-30, option B).
    Measured before the rule: no row named it. Now the same RPC names both classes, each a
    handler of its own server."""
    handlers = sorted(
        str(r["handler"]).rsplit(" ", 1)[-1]
        for r in probe_tables["endpoints"]
        if r["protocol"] == "grpc" and r["path"] == "sextant.grpcprobe.OrderService/GetOrder"
    )
    assert [h.split("#")[0] for h in handlers] == [
        "com/example/grpcprobe/OrderServiceAsyncImpl",
        "com/example/grpcprobe/OrderServiceImpl",
    ], handlers
