"""A grpc-java service is read on what protoc REALLY emits: the handlers a generated
`<Service>ImplBase` exposes are default methods of its nested `<Service>Grpc$AsyncService`
interface, and the base class itself declares only its constructor and `bindService`.

`fixtures/grpc-probe` is that generated code, compiled by protoc and protoc-gen-grpc-java
1.62.2 from `order_service.proto`. `OrderServiceImpl extends OrderServiceImplBase` overrides
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
    `schema_operations` merges the `.proto`'s row into the same identity, so there is one
    row, not two."""
    rows = [
        (str(r["path"]), str(r["handler"]).rsplit(" ", 1)[-1], str(r["resolution"]))
        for r in probe_tables["endpoints"]
        if r["protocol"] == "grpc"
    ]
    assert rows == [
        (
            "sextant.grpcprobe.OrderService/GetOrder",
            "com/example/grpcprobe/OrderServiceImpl#getOrder(sig_ba59a558).",
            "resolved",
        )
    ], rows
    assert not [q for q in probe_tables["open_questions"] if q["question"] == "service_identity"], (
        probe_tables["open_questions"]
    )
