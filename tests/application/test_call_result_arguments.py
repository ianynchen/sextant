"""A JVM `single_call` row's address read through a call's result (plan 3 Task 3, rulings R17,
R19).

`single_call` walks an address argument that is a call's RESULT (`{kind: unresolved, source: N}`)
as it walks a `concat` or a `field`: the catalog names the position, and the producing call is
the walk's established machinery. The reach is deliberate and covers both a url row and a channel
row: `producer.send(Topics.orders(), …)` is the same trace-the-value question as a Python
`requests.get(os.getenv("U"))`. A result the walk cannot state stays `unresolved`."""

from pathlib import Path

import pytest
from fixture_module import declared_parameters
from test_call_engines import (
    CAPABILITIES,
    PRODUCER,
    _document,
    _send_call,
    _single_call_catalog,
)

from flow_facts import straight_line
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.return_flow import record_return_flows
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    MethodReturnFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import method_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_TOPICS = "com/acme/messaging/Topics#"
_CALLER = _MODULE + method_descriptor(PRODUCER, "publish", "()V")
_HELPER = _MODULE + method_descriptor(_TOPICS, "orders", "()Ljava/lang/String;")


def _facts(returned: CallArgument | None, send: str) -> list:
    """`producer.<send>(Topics.orders())`, where `Topics.orders()` returns `returned` (None: a
    method this module does not hold)."""
    facts: list = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + PRODUCER, construct_kind="class"),
        CallSiteFact(
            document_id="doc_1",
            caller=_CALLER,
            target=CallTarget(owner=_TOPICS, name="orders", descriptor="()Ljava/lang/String;"),
            invoke_kind="static",
            ordinal=0,
            receiver=None,
            result=7,
            arguments=[],
        ),
        _send_call(_CALLER, 1, [CallArgument(kind="unresolved", source=7)], name=send),
    ]
    if returned is not None:
        facts += [
            SymbolFact(
                document_id="doc_1",
                symbol=_HELPER,
                construct_kind="method",
                enclosing=_MODULE + _TOPICS,
                signature=Signature(
                    parameters=declared_parameters("()Ljava/lang/String;"),
                    returns=TypeRef(symbol="java/lang/String#"),
                ),
            ),
            MethodReturnFact(document_id="doc_1", method=_HELPER, ordinal=0, value=returned),
        ]
    return facts


def _rows(tmp_path: Path, facts: list, matches: dict, protocol: str) -> list[tuple]:
    catalog = _single_call_catalog(matches, "invented-call-result", protocol=protocol)
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), straight_line(facts))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    record_return_flows(workspace)
    record_call_edges(workspace)
    assert derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES) == []
    rows = [(e["path"], e["resolution"]) for e in workspace.query("endpoints")]
    workspace.close()
    return rows


_CHANNEL = {
    "owner": "com.acme.messaging.Producer",
    "methods": [{"name": "send", "channel_arg": 0, "http_method": "SEND"}],
}
_URL = {
    "owner": "com.acme.messaging.Producer",
    "methods": [{"name": "fetch", "url_arg": 0, "http_method": "GET"}],
}
_STATED = CallArgument(kind="string", value="orders.created")
_UNSTATED = CallArgument(kind="unresolved")


@pytest.mark.parametrize(
    ("matches", "protocol", "send", "returned", "expected"),
    [
        (_CHANNEL, "kafka", "send", _STATED, [("orders.created", "resolved")]),
        (_CHANNEL, "kafka", "send", _UNSTATED, [(None, "unresolved")]),
        (_CHANNEL, "kafka", "send", None, [(None, "unresolved")]),
        (_URL, "http", "fetch", _STATED, [("orders.created", "resolved")]),
        (_URL, "http", "fetch", _UNSTATED, [(None, "unresolved")]),
        (_URL, "http", "fetch", None, [(None, "unresolved")]),
    ],
)
def test_a_call_result_address_is_walked_on_a_url_row_and_a_channel_row(
    tmp_path, matches, protocol, send, returned, expected
):
    assert _rows(tmp_path, _facts(returned, send), matches, protocol) == expected
