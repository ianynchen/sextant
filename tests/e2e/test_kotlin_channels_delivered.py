"""Kotlin channels and flows are object-keyed in-process dispatch (spec 2026-11-05 §4 item 7):
a trace from the method that sends on a channel walks on into the method that receives from that
same channel, a `for` loop included, and a trace from an emit on a shared flow walks into every
collector's lambda body. Never an endpoint row.

**Not a document check.** Real bytecode (`fixtures/orders-kotlin-channels`, kotlinc 2.4.20,
JDK 21), real pipeline, the trace a user asks for. The rows themselves are pinned in
`tests/application/test_dispatch_kotlin_channels.py`.
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

_ROOT = FIXTURES / "orders-kotlin-channels"


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace_dir = tmp_path_factory.mktemp("orders-kotlin-channels")
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


def test_a_trace_walks_from_a_send_into_the_for_loop_on_that_channel(analyzed: Path):
    """`Pipeline.record` sends on `audit`, which only `auditNext` receives from; `Pipeline.submit`
    sends on `orders`, and its trace steps into the `for` loop of `drain`, each step naming the
    channel by the call that made it."""
    assert [callee for callee, _ in _trace(analyzed, "Pipeline#record")] == ["Pipeline#auditNext"]
    steps = _trace(analyzed, "Pipeline#submit")
    assert "Pipeline#drain" in [callee for callee, _ in steps]
    assert {via.split(" ", 1)[0] for _, via in steps} == {"in_process"}
    assert {_short(via.split(" ", 1)[1].rsplit("#", 1)[0]) for _, via in steps} == {
        "Pipeline#<init>"
    }


def test_a_trace_walks_from_an_emit_into_every_collector(analyzed: Path):
    """`Bus.publish` emits on `events`: the trace steps into each collector's lambda body."""
    assert sorted(callee for callee, _ in _trace(analyzed, "Bus#publish")) == [
        "Bus$log$2#emit",
        "Bus$mail$2#emit",
        "Mailer$run$2#emit",
    ]
