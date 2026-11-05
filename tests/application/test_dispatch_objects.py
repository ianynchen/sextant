"""Object-keyed in-process dispatch (spec 2026-11-05 §1, §3, §4 item 7): a value put on a
queue reaches the code that takes from THAT queue object, whatever the value's class. A
receive site is a `dispatch_registrations` row whose `key_object` is the call that made the
object its receiver reaches (`values.producer_paths`, `which_object`); a send is a hop to every
receive site whose receiver reaches the same producer (`match: one`: one consumer takes each
value, which one decided at run time). A receiver from outside the module is a stop that says
so; never a hop to every receive site.

Read over `fixtures/orders-queues` (JDK 21, Guava's `Queues` factory), analysed once the way a
user analyses it, so every assertion is on rows the real pipeline derives from javac's
bytecode (CP-59 findings 12-15). Nothing here is written for queues beyond the catalog's data.
"""

import dataclasses
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.ports.catalogs import CatalogError
from sextant.application.query.trace import trace_of
from sextant.application.resolve.dispatch_registrations import record_dispatch_registrations
from sextant.application.resolve.roots import Root
from sextant.cli.app import cli
from sextant.domain.closed_sets import RootKind, TraceStop
from sextant.domain.symbols import bare_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_ROOT = FIXTURES / "orders-queues"
_MECHANISM = "jdk-blocking-queue"


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
    """`Class#method` (a type: `Class`), module, package and signature left out."""
    if symbol is None:
        return None
    return bare_descriptor(str(symbol)).rsplit("/", 1)[-1].split("(")[0].removesuffix("#")


@pytest.fixture(scope="module")
def tables(analyzed: Path) -> dict[str, list[dict]]:
    workspace = DuckDbWorkspace(analyzed)
    try:
        return {
            "hops": workspace.query("hops"),
            "registrations": workspace.query("dispatch_registrations"),
        }
    finally:
        workspace.close()


def _hops_from(tables: dict, caller: str) -> set[tuple]:
    """`(protocol, handler)` of every hop the method `caller` makes, shortened."""
    return {
        (str(row["protocol"]), _short(row["handler"]))
        for row in tables["hops"]
        if _short(row["caller"]) == caller
    }


def _paths_from(tables: dict, caller: str) -> set[object]:
    return {row["path"] for row in tables["hops"] if _short(row["caller"]) == caller}


def _keys_of(tables: dict, handler: str) -> set[object]:
    """The `key_object` of every receive registration whose handler is `handler`."""
    return {
        row["key_object"]
        for row in tables["registrations"]
        if row["mechanism"] == _MECHANISM and _short(row["handler"]) == handler
    }


@pytest.mark.pins("dispatch-objects.a-RECEIVE-site-registers-keyed-by-its-OBJECT")
@pytest.mark.pins("dispatch-objects.a-SEND-hops-to-the-receives-on-its-OBJECT")
@pytest.mark.pins("dispatch-objects.an-OBJECT-key-is-not-asked-for-a-CLASS")
def test_a_field_held_queue_links_across_methods(tables):
    """`Pipeline.jobs = new LinkedBlockingQueue<>()` is handed to `new Worker(jobs)`, which
    keeps it in its own field. `submit` puts on it (`put`) and `trySubmit` offers (`offer(v,
    t, u)`); `Worker.run` takes (`take`) and `tryNext` polls (`poll(t, u)`). Both sends reach
    both receives — two fields, two classes, one queue — and nothing else."""
    worker = {("in_process", "Worker#run"), ("in_process", "Worker#tryNext")}
    assert _hops_from(tables, "Pipeline#submit") == worker
    assert _hops_from(tables, "Pipeline#trySubmit") == worker
    [made] = _paths_from(tables, "Pipeline#submit")
    assert _keys_of(tables, "Worker#run") == {made}
    assert _short(str(made).rsplit("#", 1)[0]) == "Pipeline#<init>"


@pytest.mark.pins("dispatch-objects.a-SEND-hops-to-the-receives-on-its-OBJECT")
def test_two_queues_of_one_type_stay_apart(tables):
    """`Pipeline.audit` is a second `BlockingQueue<Job>` in the same class: `record` (`add`)
    and `tryRecord` (`offer(v)`) reach only its own `nextAudit` (`take`) and `pollAudit`
    (`poll()`), never `Worker`; and `submit` never reaches `audit`'s takes."""
    audit = {("in_process", "Pipeline#nextAudit"), ("in_process", "Pipeline#pollAudit")}
    assert _hops_from(tables, "Pipeline#record") == audit
    assert _hops_from(tables, "Pipeline#tryRecord") == audit
    assert _paths_from(tables, "Pipeline#record") != _paths_from(tables, "Pipeline#submit")


@pytest.mark.pins("dispatch-objects.an-UNREAD-object-is-a-STOP-that-says-so")
@pytest.mark.pins("dispatch-objects.an-UNREAD-receive-is-KEPT-keyless")
def test_a_queue_from_outside_the_module_is_a_stop(tables, analyzed: Path):
    """Nothing in the module constructs a `Relay`, so the queue its constructor is given
    comes from outside. `forward`'s `put` is one stop with no path and no handler — never a
    hop to every take in the module — and `receive`'s `take` is kept with no key, matching
    nothing. The trace says why in its step."""
    assert _hops_from(tables, "Relay#forward") == {("in_process", None)}
    assert _paths_from(tables, "Relay#forward") == {None}
    assert _keys_of(tables, "Relay#receive") == {None}
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
        ("in_process (key not read)", TraceStop.BOUNDARY)
    ]


@pytest.mark.pins("dispatch-objects.the-object-walk-lets-calls-ON-the-object-PAST")
def test_a_queue_used_between_its_put_and_its_take_is_one_object(tables):
    """`Batch.runAll`: a local `new ArrayBlockingQueue<>(n)`, `put` in a loop, then `isEmpty()`
    and `take()`. The calls made on the queue in between do not make it another queue (the
    object reader's `which_object`), so the put reaches the take in the same method."""
    assert _hops_from(tables, "Batch#runAll") == {("in_process", "Batch#runAll")}


def test_a_queue_held_by_its_class_type_is_read(tables):
    """`dolphinscheduler-alert`'s shape: a field typed `LinkedBlockingQueue`, so javac writes
    `LinkedBlockingQueue.put`/`take` (CP-59 finding 14), each declared owner by owner."""
    assert _hops_from(tables, "Alerts#push") == {("in_process", "Alerts#next")}


@pytest.mark.pins("dispatch-objects.a-LIBRARY-call-that-makes-the-object-is-its-producer")
def test_a_queue_made_by_a_library_factory_links(tables):
    """`examples/apollo`'s shape: `toClean = Queues.newLinkedBlockingQueue(100)`, a library
    static call whose body is not here. That call is the object's producer, so `schedule`'s
    `offer` reaches `nextToClean`'s `poll(t, u)`."""
    assert _hops_from(tables, "Cleaner#schedule") == {("in_process", "Cleaner#nextToClean")}


@pytest.mark.declines("jdk-blocking-queue")
@pytest.mark.pins("calls.a-declared-call-is-matched-on-its-OWNER")
def test_a_plain_queue_is_no_dispatch(tables):
    """Near miss: `Queue<Job> q = new ArrayDeque<>(); q.offer(job); q.poll()` — javac writes
    `Queue.offer`/`poll`, an owner the catalog does not declare (a plain queue is a local data
    structure). No hop, no registration."""
    assert _hops_from(tables, "Scratch#roundTrip") == set()
    assert not any(_short(row["handler"]) == "Scratch#roundTrip" for row in tables["registrations"])


def test_a_receive_registration_names_its_site_and_rule(tables):
    """Each receive site is its own group (`<caller>#<ordinal>`) at position 0, its handler
    the method making the take (`handler: enclosing`), under the catalog's `match: one`, with
    no class key."""
    [row] = [
        row
        for row in tables["registrations"]
        if row["mechanism"] == _MECHANISM and _short(row["handler"]) == "Alerts#next"
    ]
    assert _short(str(row["group"]).rsplit("#", 1)[0]) == "Alerts#next"
    assert (row["position"], row["match"], row["key_type"], row["key_value"]) == (
        0,
        "one",
        None,
        None,
    )
    assert row["key_object"] is not None


@pytest.mark.pins("dispatch-objects.a-LAMBDA-ARG-handler-is-refused-not-guessed")
def test_a_receive_handing_its_value_to_a_function_is_refused(analyzed: Path, tmp_path: Path):
    """`handler: lambda_arg` (a receive giving its value to the function it is passed) is
    refused when read rather than read as its enclosing method, which is not the code that
    handles the value."""
    queues = next(
        catalog for catalog in YamlCatalogSource(catalogs_dir()).load() if catalog.id == _MECHANISM
    )
    lambda_arg = dataclasses.replace(
        queues,
        dispatch_receives=tuple(
            receive | {"handler": "lambda_arg"} for receive in queues.dispatch_receives
        ),
    )
    copy = tmp_path / "workspace.duckdb"
    shutil.copy(analyzed, copy)
    workspace = DuckDbWorkspace(copy)
    try:
        with pytest.raises(CatalogError, match="`handler: lambda_arg`"):
            record_dispatch_registrations(workspace, [lambda_arg])
    finally:
        workspace.close()
