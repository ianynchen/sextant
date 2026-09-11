"""One wire identity a module both serves and calls is a QUESTION, not a merge
(F5 §6.1, W27).

## What the merge asserted

`merge_endpoints.sql` collapsed an inbound row and an outbound row sharing
`(protocol, method, path)` into one `direction: both` row, keeping the handler and
carrying the caller and its peer onto it. That asserts the thing this module calls IS the
thing this module serves — a claim about the far end of a call, which a module's own
bytecode cannot show. And it keyed on the wire identity alone, so `peer` never entered
the comparison (RC-5).

**Measured on the orders-service fixture, where two of the six merged rows were wrong.**
The `both` row for `{http://orders.example.com/ws}placeOrderRequest` carried `peer:
${soap.billing.uri}`: the module's own served operation and a call to the BILLING service,
published as one endpoint, because they share a payload QName. `POST /v1/orders` merged
the module's own handler with a call to `orders-loop`. The other four — three Kafka topics
and a Pub/Sub subscription, all with no peer on either side — are the genuine
self-publish/self-consume case that made the merge look right.

The rows now stand apart (141 endpoints became 147) and the question is filed instead.

## Everything here is invented

Invented protocols, paths and symbols, for the reason every engine test in this directory
gives: a behaviour per test, isolated and fast, with the shipped answer pinned once in
`test_pipeline.py` against real bytecode. The protocol values are the exception — they
are written into a closed column — so they come from D00's set and nothing below turns on
which member they are.
"""

import json
from pathlib import Path

from sextant.application.resolve.self_exchange import record_self_exchange
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# Module-prefixed exactly as a fact writes them (D00 §5a) — which is what the
# `endpoints` columns hold, and what a candidate must strip to match how the rest of the
# document spells a symbol.
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
SERVED = "com/acme/orders/OrderController#create(sig_00000000)."
CALLED = "com/acme/orders/clients/LoopClient#createOrder(sig_11111111)."
OTHER_CALLER = "com/acme/orders/clients/OtherClient#create(sig_22222222)."


def _workspace(
    tmp_path: Path, *rows: tuple[str, str, str | None, str | None, str | None]
) -> DuckDbWorkspace:
    """A workspace holding exactly the endpoint rows a test names, as
    `(protocol, direction, method, path, symbol)` — the symbol landing in `handler` for
    an inbound row and in `caller` for an outbound one, which is where the engines put
    it."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    for protocol, direction, method, path, symbol in rows:
        peer = None
        if direction == "outbound" and symbol is not None and "@" in symbol:
            symbol, _, peer = symbol.partition("@")
        stored = None if symbol is None else _MODULE + symbol
        workspace._connection.execute(
            "INSERT INTO endpoints (protocol, direction, method, path, handler, caller, peer) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                protocol,
                direction,
                method,
                path,
                stored if direction == "inbound" else None,
                stored if direction == "outbound" else None,
                peer,
            ],
        )
    return workspace


def _questions(workspace: DuckDbWorkspace) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in workspace.query("open_questions")
        if str(row["question"]) == "self_exchange"
    ]


def test_one_identity_in_both_directions_is_asked_about_not_merged(tmp_path: Path):
    """The positive half (§10): one identity claimed in both directions is a QUESTION,
    not a merge.

    The direction assertion below restates `_workspace`'s own two `INSERT`s — nothing
    between them and the read can fold a row, because `record_self_exchange` only reads
    `endpoints` and writes `open_questions`. It is kept as a statement of the invariant
    the pass must not break, NOT as a check that the merge is gone: the docstring used to
    claim it "would pass with the merge still running" the other way round, and that is
    the inverse of the truth (W27 review). The merge was a statement inside
    `derive_endpoints`, which this test never calls.

    Where "the two rows stand" is genuinely pinned is against real derivation:
    `test_endpoints.py::test_a_path_the_module_both_exposes_and_calls_stays_two_endpoints`
    and `test_pipeline.py`'s fixture counts.
    """
    workspace = _workspace(
        tmp_path,
        ("http", "inbound", "POST", "/v1/orders", SERVED),
        ("http", "outbound", "POST", "/v1/orders", f"{CALLED}@orders-loop"),
    )

    record_self_exchange(workspace)
    questions = _questions(workspace)
    directions = sorted(str(row["direction"]) for row in workspace.query("endpoints"))
    workspace.close()

    assert directions == ["inbound", "outbound"], (
        "the two rows stand; `both` is reserved for the linking tier"
    )
    assert len(questions) == 1
    assert (questions[0]["protocol"], questions[0]["method"], questions[0]["path"]) == (
        "http",
        "POST",
        "/v1/orders",
    )
    candidates = json.loads(str(questions[0]["candidates"]))
    assert [c["side"] for c in candidates] == ["served", "called"]
    assert candidates[0]["symbol"] == SERVED, (
        "the descriptor alone — every other symbol on the page is spelled this way, and "
        "a reader has to be able to match a question to the row it is about by eye"
    )
    assert candidates[1]["peer"] == "orders-loop", (
        "the address is what makes the question answerable — it is the column the merge "
        "never compared"
    )


def test_an_identity_in_one_direction_only_is_no_question(tmp_path: Path):
    """The near-miss (§10). An ordinary served route and an ordinary outbound call are
    not a question about anything, and a rule that asked about every endpoint would
    bury the six that mean something under every row in the table."""
    workspace = _workspace(
        tmp_path,
        ("http", "inbound", "GET", "/served-only", SERVED),
        ("http", "outbound", "GET", "/called-only", CALLED),
    )

    record_self_exchange(workspace)
    questions = _questions(workspace)
    workspace.close()

    assert questions == []


def test_the_identity_is_the_whole_identity(tmp_path: Path):
    """A pair differing in protocol, in method, or in path is two unrelated endpoints.

    Each of these three reaches the same grouping and is refused by one component of it,
    so a rule that dropped any component would pair exactly one of them — and this names
    which. `method` is the one worth stating: it is nullable, and a rule comparing it
    loosely would pair a verbless topic with a verbed route on a shared name.
    """
    workspace = _workspace(
        tmp_path,
        ("http", "inbound", "GET", "/a", SERVED),
        ("kafka", "outbound", "GET", "/a", CALLED),
        ("http", "inbound", "GET", "/b", SERVED),
        ("http", "outbound", "POST", "/b", CALLED),
        ("http", "inbound", "GET", "/c", SERVED),
        ("http", "outbound", "GET", "/c-other", CALLED),
    )

    record_self_exchange(workspace)
    questions = _questions(workspace)
    workspace.close()

    assert questions == []


def test_a_verbless_identity_pairs_on_its_address(tmp_path: Path):
    """The messaging case, which is the one the merge got right and which must keep
    being asked: a topic has no verb, so both rows carry `method` NULL and the pair is
    the address alone. This is self-publish/self-consume — a service publishing to a
    topic and reading it back — and it is real, which is exactly why the answer is a
    question rather than a rule."""
    workspace = _workspace(
        tmp_path,
        ("kafka", "inbound", None, "order-events", SERVED),
        ("kafka", "outbound", None, "order-events", CALLED),
    )

    record_self_exchange(workspace)
    questions = _questions(workspace)
    workspace.close()

    assert len(questions) == 1
    assert questions[0]["method"] is None
    assert questions[0]["path"] == "order-events"


def test_two_unresolved_rows_are_not_a_pair(tmp_path: Path):
    """An unresolved row names no address, so it shares `path IS NULL` with every other
    unresolved row on its protocol. Pairing those would ask the reader about a
    coincidence of two ABSENCES — a question with nothing in it to answer — and on a
    module with several unresolved calls it would ask once per protocol forever."""
    workspace = _workspace(
        tmp_path,
        ("kafka", "inbound", None, None, SERVED),
        ("kafka", "outbound", None, None, CALLED),
    )

    record_self_exchange(workspace)
    questions = _questions(workspace)
    workspace.close()

    assert questions == []


def test_a_row_naming_no_method_is_still_a_candidate(tmp_path: Path):
    """A schema-first row names no method at all: its operation is declared by a `.wsdl`
    or a `.proto`, and `schema_operations` mints it with neither handler nor caller.

    The question is still worth asking about such a row — the module really does serve
    that operation, and something really does call it — so the candidate carries a NULL
    symbol rather than being dropped, and the renderer says so instead of composing a
    sentence that trails off after "served here by".
    """
    workspace = _workspace(
        tmp_path,
        ("soap", "inbound", None, "{urn:acme}quote", None),
        ("soap", "outbound", None, "{urn:acme}quote", f"{CALLED}@billing"),
    )

    record_self_exchange(workspace)
    questions = _questions(workspace)
    workspace.close()

    assert len(questions) == 1
    candidates = json.loads(str(questions[0]["candidates"]))
    assert candidates[0] == {"side": "served", "symbol": None, "peer": None}


def test_every_caller_of_a_served_path_is_a_candidate(tmp_path: Path):
    """Two callers reaching one served path are ONE question with three candidates, not
    two questions — the question is about the identity, and the reader settles it once.

    Each caller keeps its own address, which is the whole point: the answer may well be
    "this one is us and that one is not", and a candidate list that collapsed them could
    not express it.
    """
    workspace = _workspace(
        tmp_path,
        ("http", "inbound", "POST", "/v1/orders", SERVED),
        ("http", "outbound", "POST", "/v1/orders", f"{CALLED}@orders-loop"),
        ("http", "outbound", "POST", "/v1/orders", f"{OTHER_CALLER}@elsewhere"),
    )

    record_self_exchange(workspace)
    questions = _questions(workspace)
    workspace.close()

    assert len(questions) == 1
    candidates = json.loads(str(questions[0]["candidates"]))
    assert [c["side"] for c in candidates] == ["served", "called", "called"]
    assert {c["peer"] for c in candidates if c["side"] == "called"} == {
        "orders-loop",
        "elsewhere",
    }
