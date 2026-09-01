"""Tests for the `protocol_hint` pass (2H design §6) — the reclassification
that turns rows other engines minted into rows of another protocol.

Everything here is built by hand — invented MIME strings, invented marker
types, an invented source protocol and an invented target — for the reason
every other engine test in this directory states: a behaviour per test,
isolated and fast, with the shipped catalogs' own live answers pinned once in
`test_pipeline.py` against real bytecode. The invented vocabulary is also the
point: a test reaching for Spring's own spellings would not prove the pass
reads catalog data rather than knowing them.

**One shape is copied verbatim from reality, and only one**: the two return
types checkpoint answer 6 froze off live bytecode — a FLAT reference whose own
symbol is the marker, and a TWO-LEVEL generic chain whose marker is the MIDDLE
link under an ordinary outer wrapper. Their type NAMES here are invented;
their nesting is not, because the nesting is exactly what the rule turns on.
"""

import dataclasses
import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.format import resolve_format
from sextant.application.resolve.open_questions import record_open_questions
from sextant.application.resolve.protocol_hint import apply_protocol_hints
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import AnnotationFact, AnnotationUse, Document
from sextant.domain.symbols import type_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# Invented vocabulary. None of it is a real MIME type or class — every one is
# a value the catalogs below declare and the pass looks up.
STREAM_MIME = "application/x-parcel-stream"
PLAIN_MIME = "application/x-parcel"
EMITTER = "com.acme.stream.ParcelEmitter"
ENVELOPE = "com.acme.stream.ParcelEvent"
WRAPPER = "com.acme.async.Eventually"
PAYLOAD = "com.acme.contracts.Parcel"
MARKER = "com.acme.binder"

# The two protocols this pass moves between, both members of D00's closed set
# (the target is written into a closed column, so an invented name could not
# be used for it). `http` is the SOURCE only because a catalog's own
# `protocol` field is what scopes the pass — no rule below names it.
SOURCE = "http"
TARGET = "sse"
OTHER = "graphql"


def _flat(symbol: str) -> dict:
    """A return type that names one type and takes no arguments — checkpoint
    answer 6's `SseEmitter` shape, where the marker IS the outer symbol."""
    return {"symbol": type_descriptor(symbol), "wire_type": "object", "arguments": []}


def _nested(*symbols: str) -> dict:
    """A generic chain, outermost first — checkpoint answer 6's
    `Flux<ServerSentEvent<OrderView>>` shape, where the marker is a MIDDLE
    link and the outer symbol says nothing at all."""
    reference = _flat(symbols[-1])
    for symbol in reversed(symbols[:-1]):
        reference = _flat(symbol) | {"arguments": [reference]}
    return reference


def _signature(returns: dict) -> str:
    return json.dumps({"parameters": [], "returns": returns}, sort_keys=True)


def _seed(workspace: DuckDbWorkspace, *rows: dict) -> None:
    """Rows the endpoint engines already minted — what this pass reclassifies.
    Written through the same `call_endpoints` derive every style uses, so the
    rows are indistinguishable from real ones."""
    workspace.derive(
        "call_endpoints",
        rows=[
            {
                "protocol": SOURCE,
                "direction": "inbound",
                "method": "GET",
                "path": None,
                "handler": None,
                "caller": None,
                "peer": None,
                "handler_signature": None,
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "invented-hints",
                "request_shape": None,
                "response_shape": None,
                "consumes": None,
                "produces": None,
                **row,
            }
            for row in rows
        ],
    )


def _catalog(
    protocol: str = SOURCE,
    hint: dict | None = None,
    catalog_id: str = "invented-hints",
    media_formats: dict[str, str] | None = None,
    json_default_markers: list[str] | None = None,
) -> Catalog:
    """A catalog carrying a `protocol_hint` block, scoped by its own
    `protocol` — which is the whole of how the pass knows which rows it may
    move."""
    return Catalog(
        id=catalog_id,
        style="annotation_driven",
        protocol=protocol,
        direction="inbound",
        requires=(),
        matches={},
        source=Path(f"tests/{catalog_id}.yml"),
        protocol_hint={"protocol": TARGET, "hint_media": [STREAM_MIME]} if hint is None else hint,
        media_formats=media_formats or {},
        json_default_markers=json_default_markers or [],
    )


def _protocols(workspace: DuckDbWorkspace) -> dict[object, object]:
    return {row["path"]: row["protocol"] for row in workspace.query("endpoints")}


# --- the two evidence kinds -----------------------------------------------


def test_produces_event_stream_reclassifies(tmp_path: Path):
    """Evidence 1, the cheap and strong one: the row's own declared media
    names the envelope, so the channel said what it is in the source and no
    return type is needed."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/stream", "produces": json.dumps([STREAM_MIME])},
        {"path": "/plain", "produces": json.dumps([PLAIN_MIME])},
    )
    apply_protocol_hints(workspace, [_catalog()])
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/stream": TARGET, "/plain": SOURCE}


def test_return_type_reclassifies(tmp_path: Path):
    """Evidence 2, and the case it exists for: a handler that declares NO
    media at all is still a stream, and its return type is then the only
    statement there is.

    Both real shapes at once (checkpoint answer 6). `/emitter` returns the
    marker FLAT — the marker is the outer symbol and there are no arguments —
    while `/stream` returns it nested two levels down under an ordinary
    wrapper. A rule that read only the outer symbol would answer the first and
    miss the second entirely; `/wrapped` is the control that proves the walk
    is not simply matching anything it can reach, since its chain carries the
    wrapper and the payload and no marker."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/emitter", "handler_signature": _signature(_flat(EMITTER))},
        {"path": "/stream", "handler_signature": _signature(_nested(WRAPPER, ENVELOPE, PAYLOAD))},
        {"path": "/wrapped", "handler_signature": _signature(_nested(WRAPPER, PAYLOAD))},
    )
    apply_protocol_hints(
        workspace,
        [_catalog(hint={"protocol": TARGET, "hint_returns": [EMITTER, ENVELOPE]})],
    )
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/emitter": TARGET, "/stream": TARGET, "/wrapped": SOURCE}


def test_media_answers_a_row_whose_return_type_says_nothing(tmp_path: Path):
    """The two evidence kinds are independent, and media is read first: a row
    declaring the envelope reclassifies even though its return type carries no
    marker anywhere in its chain."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {
            "path": "/stream",
            "produces": json.dumps([STREAM_MIME]),
            "handler_signature": _signature(_nested(WRAPPER, PAYLOAD)),
        },
    )
    apply_protocol_hints(
        workspace,
        [
            _catalog(
                hint={"protocol": TARGET, "hint_media": [STREAM_MIME], "hint_returns": [EMITTER]}
            )
        ],
    )
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/stream": TARGET}


def test_an_inbound_rows_consumes_is_never_protocol_evidence(tmp_path: Path):
    """Review fix round 1. `consumes` is the REQUEST-body media, so on an
    INBOUND row it says what the route ACCEPTS — a handler being HANDED an
    event stream by its caller, not one streaming anything back. Reclassifying
    on it would rename the channel after its input.

    This is the one place the pass deliberately diverges from the format
    ladder's rung 2, which folds both columns into one answer: `format`
    describes one wire and both columns describe it, while a protocol hint is
    a claim about what the channel IS.

    `/accepts` declares the envelope in `consumes` and nothing in `produces`,
    and must not move. `/emits` is the control — the same MIME string in the
    column that does count."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/accepts", "consumes": json.dumps([STREAM_MIME])},
        {"path": "/emits", "produces": json.dumps([STREAM_MIME])},
    )
    apply_protocol_hints(workspace, [_catalog()])
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/accepts": SOURCE, "/emits": TARGET}


def test_a_client_side_rows_consumes_is_protocol_evidence(tmp_path: Path):
    """The other half of the same rule. On an OUTBOUND row — and on the merged
    `both` row that carries a caller's own declaration — `consumes` is what the
    client RECEIVES off the wire, which is exactly the envelope. Both sides
    count there, so the narrowing above is about direction and not about the
    column."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/calls", "direction": "outbound", "consumes": json.dumps([STREAM_MIME])},
        {"path": "/merged", "direction": "both", "consumes": json.dumps([STREAM_MIME])},
    )
    apply_protocol_hints(workspace, [_catalog()])
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/calls": TARGET, "/merged": TARGET}


# --- the three promises ---------------------------------------------------


def test_scoped_to_the_declaring_catalogs_own_protocol(tmp_path: Path):
    """Promise 3. A row of another protocol is untouchable, not merely
    untouched: the SOURCE is the declaring catalog's own `protocol` field, so
    a catalog can only ever move rows of the protocol it owns — even where the
    other row carries exactly the evidence the block names."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/mine", "produces": json.dumps([STREAM_MIME])},
        {"path": "/theirs", "protocol": OTHER, "produces": json.dumps([STREAM_MIME])},
    )
    apply_protocol_hints(workspace, [_catalog()])
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/mine": TARGET, "/theirs": OTHER}


def test_direction_never_changes(tmp_path: Path):
    """Promise 1. A merged `both` row is one identity the module both exposes
    and calls — the merge has already run by the time this pass sees it — so
    it moves WHOLESALE. Changing direction afterwards would silently undo that
    merge, which is why direction is not in the statement's SET clause at
    all."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/both", "direction": "both", "produces": json.dumps([STREAM_MIME])},
        {"path": "/out", "direction": "outbound", "produces": json.dumps([STREAM_MIME])},
    )
    apply_protocol_hints(workspace, [_catalog()])
    rows = {
        row["path"]: (row["protocol"], row["direction"]) for row in workspace.query("endpoints")
    }
    workspace.close()

    assert rows == {"/both": (TARGET, "both"), "/out": (TARGET, "outbound")}


def test_no_row_created(tmp_path: Path):
    """Promise 2. Every row written is one an engine already minted: the table
    holds the same number of rows before and after, and each reclassified row
    keeps every column but `protocol`."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/stream", "produces": json.dumps([STREAM_MIME]), "response_shape": "{}"},
        {"path": "/plain"},
    )
    before = workspace.query("endpoints")
    apply_protocol_hints(workspace, [_catalog()])
    after = workspace.query("endpoints")
    workspace.close()

    assert len(before) == len(after) == 2
    assert _but_protocol(before) == _but_protocol(after)


def _but_protocol(rows: list[dict]) -> list[dict]:
    """Every row's every column except the one this pass writes, keyed by path
    rather than by position: reclassifying a row also moves it in the
    `endpoints` query's own protocol-first ordering."""
    return sorted(
        ({column: value for column, value in row.items() if column != "protocol"} for row in rows),
        key=lambda row: str(row["path"]),
    )


def test_a_reclassified_rows_open_questions_move_with_it(tmp_path: Path):
    """Review fix round 1. `open_questions.protocol` is a SNAPSHOT of a wire
    identity, not a join into `endpoints` (schema.sql says why: the endpoint
    table is rebuilt every resolve). The parse-binding pass takes that snapshot
    BEFORE this one runs, so a reclassified row's `payload_binding` question
    would keep publishing the old protocol while the endpoint published the
    new one — one bundle, two tables, two answers about one channel.

    The ledger follows. The untouched row's own question stays put, which is
    what makes this a match rather than a blanket rewrite."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/stream", "produces": json.dumps([STREAM_MIME])},
        {"path": "/plain"},
    )
    record_open_questions(
        workspace,
        [
            {
                "protocol": SOURCE,
                "method": "GET",
                "path": path,
                "question": "payload_binding",
                "candidates": "[]",
                "evidence": "invented",
            }
            for path in ("/stream", "/plain")
        ],
    )
    apply_protocol_hints(workspace, [_catalog()])
    ledger = {row["path"]: row["protocol"] for row in workspace.query("open_questions")}
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/stream": TARGET, "/plain": SOURCE}
    assert ledger == answers


def test_two_rows_sharing_a_wire_identity_move_independently(tmp_path: Path):
    """`(protocol, direction, method, path)` is not unique in this table, so
    the write matches on `handler`/`caller` too — the same six columns
    `stamp_format.sql` uses. Two rows differing only in their handler must not
    both move because one of them declared the envelope."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/shared", "handler": "a#f().", "produces": json.dumps([STREAM_MIME])},
        {"path": "/shared", "handler": "b#g()."},
    )
    apply_protocol_hints(workspace, [_catalog()])
    rows = {row["handler"]: row["protocol"] for row in workspace.query("endpoints")}
    workspace.close()

    assert rows == {"a#f().": TARGET, "b#g().": SOURCE}


# --- the format ladder, downstream of the move ----------------------------


def test_format_fixed_rung_fires(tmp_path: Path):
    """Rung 1 (2G design §5) read through the pipeline's own ordering: this
    pass runs BEFORE the ladder precisely so a moved row is answered under its
    true protocol.

    The catalog declares a fixed format for the protocol the row is moving TO
    and none for the one it came from, so the answer is only reachable if the
    reclassification happened first — which is the ordering, tested rather
    than asserted in a comment."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(workspace, {"path": "/stream", "produces": json.dumps([STREAM_MIME])})
    catalog = dataclasses.replace(_catalog(), format_fixed={TARGET: "xml"})
    apply_protocol_hints(workspace, [catalog])
    resolve_format(workspace, [catalog])
    rows = _formats(workspace)
    workspace.close()

    assert rows == {"/stream": ("xml", "resolved")}


def test_sse_format_honest(tmp_path: Path):
    """The envelope is not the payload. The MIME string that named the
    PROTOCOL maps to no format at all, so rung 2 has nothing to say about the
    moved row and it falls to the framework default at `narrowed` — an
    assumption that reads like one.

    The plain row beside it is the control: its own MIME string IS in the
    table, so it is answered at `resolved`, which is what makes the streaming
    row's silence a rule rather than an empty catalog."""
    workspace = _marked_workspace(tmp_path)
    _seed(
        workspace,
        {
            "path": "/stream",
            "produces": json.dumps([STREAM_MIME]),
            "response_shape": json.dumps({"shape_id": type_descriptor(PAYLOAD)}),
        },
        {"path": "/plain", "produces": json.dumps([PLAIN_MIME])},
    )
    catalog = _catalog(media_formats={PLAIN_MIME: "xml"}, json_default_markers=[MARKER])
    apply_protocol_hints(workspace, [catalog])
    resolve_format(workspace, [catalog])
    rows = _formats(workspace)
    workspace.close()

    assert rows == {"/stream": ("json", "narrowed"), "/plain": ("xml", "resolved")}


def _formats(workspace: DuckDbWorkspace) -> dict[object, tuple[object, object]]:
    return {
        row["path"]: (row["format"], row["format_resolution"])
        for row in workspace.query("endpoints")
    }


def _marked_workspace(tmp_path: Path) -> DuckDbWorkspace:
    """A workspace holding one annotation from the invented marker package
    family — rung 5's whole presence test (`test_format_ladder.py` builds the
    same thing the same way)."""
    write_fact_file(
        tmp_path / "facts" / "Parcel.jsonl",
        Document(
            document_id="doc_1",
            relative_path="com/acme/contracts/Parcel.java",
            module_id="com.acme:orders-service",
            language="java",
            sextant_version="0.1.0",
            fact_schema_version="1.0.0",
            scanner_id="asm",
            scanner_version="9.9",
            content_hash="sha256:a",
            origin_entry="target/classes",
            origin_tier=OriginTier.MODULE_OUTPUT,
            redaction_set_hash="sha256:b",
        ),
        [
            AnnotationFact(
                document_id="doc_1",
                target=type_descriptor(PAYLOAD) + "id.",
                use=AnnotationUse(annotation=type_descriptor(f"{MARKER}.Named")),
                retention="runtime",
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


# --- determinism and refusals ---------------------------------------------


def test_deterministic(tmp_path: Path):
    """NFR-1. The pass reads `endpoints` in the named query's own total order
    and writes one value per matched row, so running it twice over two
    identical workspaces produces identical tables — and running it twice over
    ONE workspace changes nothing the second time, because a moved row no
    longer matches the source protocol it was matched on."""
    rows = (
        {"path": "/stream", "produces": json.dumps([STREAM_MIME])},
        {"path": "/emitter", "handler_signature": _signature(_flat(EMITTER))},
        {"path": "/plain"},
    )
    hint = {"protocol": TARGET, "hint_media": [STREAM_MIME], "hint_returns": [EMITTER]}
    answers = []
    for name in ("first", "second"):
        workspace = DuckDbWorkspace(tmp_path / f"{name}.duckdb")
        _seed(workspace, *rows)
        apply_protocol_hints(workspace, [_catalog(hint=hint)])
        apply_protocol_hints(workspace, [_catalog(hint=hint)])
        answers.append(workspace.query("endpoints"))
        workspace.close()

    assert answers[0] == answers[1]
    assert _protocols_of(answers[0]) == {"/stream": TARGET, "/emitter": TARGET, "/plain": SOURCE}


def _protocols_of(rows: list[dict]) -> dict[object, object]:
    return {row["path"]: row["protocol"] for row in rows}


def test_two_catalogs_of_a_family_union_their_evidence(tmp_path: Path):
    """The shipped shape: two catalogs of one family each own the marker types
    their own artifact declares, and a module pulling in either must get that
    one's markers. The lists UNION — the target protocol, being a single
    value, is the half a contradiction is refused on."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(
        workspace,
        {"path": "/emitter", "handler_signature": _signature(_flat(EMITTER))},
        {"path": "/stream", "handler_signature": _signature(_nested(WRAPPER, ENVELOPE, PAYLOAD))},
    )
    apply_protocol_hints(
        workspace,
        [
            _catalog(hint={"protocol": TARGET, "hint_returns": [EMITTER]}, catalog_id="one"),
            _catalog(hint={"protocol": TARGET, "hint_returns": [ENVELOPE]}, catalog_id="two"),
        ],
    )
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/emitter": TARGET, "/stream": TARGET}


def test_a_declared_hint_that_matches_no_row_leaves_the_table_alone(tmp_path: Path):
    """The ordinary case for most real modules: the vocabulary is loaded (both
    shipped Spring HTTP catalogs declare it) and NOTHING in the module streams,
    so the pass reaches the write with an empty row list. It must be a no-op,
    not a failure — a module with no SSE at all is the common one."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(workspace, {"path": "/plain"}, {"path": "/other", "produces": json.dumps([PLAIN_MIME])})
    apply_protocol_hints(workspace, [_catalog()])
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/plain": SOURCE, "/other": SOURCE}


def test_two_catalogs_disagreeing_on_the_target_are_refused(tmp_path: Path):
    """One source protocol, one target. Picking either side silently would
    make the answer depend on filename order — the rule `format.py`'s own
    merged tables keep."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(workspace, {"path": "/stream"})
    with pytest.raises(CatalogError, match="contradicts"):
        apply_protocol_hints(
            workspace,
            [
                _catalog(hint={"protocol": TARGET, "hint_media": [STREAM_MIME]}, catalog_id="one"),
                _catalog(hint={"protocol": OTHER, "hint_media": [STREAM_MIME]}, catalog_id="two"),
            ],
        )
    workspace.close()


@pytest.mark.parametrize(
    "hint",
    [
        pytest.param({"protocol": TARGET, "hint_medias": [STREAM_MIME]}, id="unknown key"),
        pytest.param({"hint_media": [STREAM_MIME]}, id="no target"),
        pytest.param({"protocol": "stream", "hint_media": [STREAM_MIME]}, id="target off the set"),
        pytest.param({"protocol": SOURCE, "hint_media": [STREAM_MIME]}, id="target is the source"),
        pytest.param({"protocol": TARGET}, id="no evidence at all"),
        pytest.param({"protocol": TARGET, "hint_media": STREAM_MIME}, id="evidence not a list"),
        pytest.param({"protocol": TARGET, "hint_returns": [3]}, id="evidence not strings"),
        pytest.param([TARGET], id="block not a mapping"),
    ],
)
def test_a_malformed_block_is_refused_before_a_single_row_is_read(tmp_path: Path, hint: object):
    """A block this pass cannot act on is refused, never skipped. A skipped
    block makes a catalog that MEANT to reclassify indistinguishable from one
    that declared none — the one outcome the loader's own discipline exists to
    prevent — and the target reaches a closed published column, where a typo
    is indistinguishable from an observation (NFR-5)."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(workspace, {"path": "/stream", "produces": json.dumps([STREAM_MIME])})
    with pytest.raises(CatalogError):
        apply_protocol_hints(workspace, [_catalog(hint=hint)])  # type: ignore[arg-type]
    assert _protocols(workspace) == {"/stream": SOURCE}
    workspace.close()


def test_a_catalog_declaring_no_block_reclassifies_nothing(tmp_path: Path):
    """Every catalog shipped before this task declares no block, and the pass
    is a no-op for them — including for a row that happens to carry a MIME
    string some other catalog would have named."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    _seed(workspace, {"path": "/stream", "produces": json.dumps([STREAM_MIME])})
    apply_protocol_hints(workspace, [_catalog(hint={})])
    answers = _protocols(workspace)
    workspace.close()

    assert answers == {"/stream": SOURCE}
