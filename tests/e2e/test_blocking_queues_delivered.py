"""Java blocking queues are object-keyed in-process dispatch (spec 2026-11-05 §4 item 7): a
trace from the method that puts a value on a queue walks on into the method that takes it off
that same queue, as it walks into a handler a gRPC self-call reaches. Never an endpoint row.

**Not a document check.** Real bytecode (`fixtures/orders-queues`, JDK 21), real pipeline, the
trace a user asks for. The rows themselves are pinned in
`tests/application/test_dispatch_objects.py`.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.query.trace import trace_of
from sextant.application.resolve.roots import Root
from sextant.cli.app import cli
from sextant.domain.closed_sets import RootKind
from sextant.domain.symbols import bare_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_ROOT = FIXTURES / "orders-queues"


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace_dir = tmp_path_factory.mktemp("orders-queues")
    compile_fixture(_ROOT)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(_ROOT), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    return workspace_dir / "workspace.duckdb"


def _short(symbol: object) -> str | None:
    if symbol is None:
        return None
    return bare_descriptor(str(symbol)).rsplit("/", 1)[-1].split("(")[0].removesuffix("#")


def _trace(analyzed: Path, method: str) -> list[tuple]:
    workspace = DuckDbWorkspace(analyzed)
    try:
        [root] = [
            str(row["symbol"])
            for row in workspace.query("method_declarations")
            if f"{method}(" in str(row["symbol"])
        ]
        endpoints = workspace.query("endpoints")
        trace = trace_of(workspace, Root(handler=root, kind=RootKind.INBOUND_ENDPOINT))
    finally:
        workspace.close()
    assert not [row for row in endpoints if row["protocol"] == "in_process"]
    return [(_short(step.callee), step.via) for step in trace.steps if step.via is not None]


def test_a_trace_walks_from_the_put_into_every_take_on_that_queue(analyzed: Path):
    """`Pipeline.submit` puts on `jobs`, which `Worker` takes from in `run` and polls in
    `tryNext`: the trace steps into both (one consumer takes each job, which one is decided
    at run time), each step naming the queue by the call that made it, and never into
    `Pipeline`'s own `audit` takes. No `in_process` endpoint row is minted."""
    steps = _trace(analyzed, "Pipeline#submit")
    assert [callee for callee, _ in steps] == ["Worker#run", "Worker#tryNext"]
    assert {via.split(" ", 1)[0] for _, via in steps} == {"in_process"}
    assert {_short(via.split(" ", 1)[1].rsplit("#", 1)[0]) for _, via in steps} == {
        "Pipeline#<init>"
    }
