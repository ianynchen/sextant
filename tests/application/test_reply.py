"""Tests for the `reply` block (D02 §2's `annotation_driven` amendment, Task
8): a listener's declared reply (`@SendTo` and its like) derives a second,
OUTBOUND endpoint row per listed destination, carrying the handler's own
return type as its payload.

Facts are hand-built, mirroring the exact grammar `annotation_driven`'s own
tests use (`tests/application/test_endpoints.py`) — an invented, deliberately
non-Spring annotation set, so the engine's own genericity (no framework name
appears in it) is exercised rather than assumed."""

import json
from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.storage.duckdb.workspace import DuckDbWorkspace

KAFKA_LISTENER = "com/acme/messaging/annotation/KafkaListener#"
SEND_TO = "com/acme/messaging/annotation/SendTo#"
RECEIPT_VIEW = "com/acme/orders/contracts/ReceiptView#"

_MATCHES = {
    "mapping": {
        "path_from": ["topics"],
        "prefix_from": [],
        "method_from": "method",
        # Verbless (D02 §2, amended): a listener declares no HTTP-style verb.
        "all_methods": [],
        "prefix_annotation": "com.acme.messaging.annotation.Topic",
        "annotations": [{"fqn": "com.acme.messaging.annotation.KafkaListener"}],
    },
    # D02 §2's `reply` block, frozen (Task 1): {annotation, destination_from,
    # payload: return}. `payload` is documentation only here — this engine
    # always roots the reply payload at the handler's own return type.
    "reply": {
        "annotation": "com.acme.messaging.annotation.SendTo",
        "destination_from": "value",
        "payload": "return",
    },
}


def _catalog() -> Catalog:
    return Catalog(
        id="invented-reply-listener",
        style="annotation_driven",
        protocol="kafka",
        direction="inbound",
        requires=("annotation_args",),
        source=Path("tests/invented-reply.yml"),
        matches=_MATCHES,
    )


def _document(document_id: str = "doc_1") -> Document:
    return Document(
        document_id=document_id,
        relative_path="com/acme/notify/OrderListener.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _receipt_returns() -> TypeRef:
    return TypeRef(
        symbol=RECEIPT_VIEW,
        wire_type="object",
        wire_format="",
        nullable=True,
        nullable_resolution="resolved",
    )


def _void_returns() -> TypeRef:
    # The real emitted shape of a `void` return (checkpoint-verified,
    # `tests/application/test_shapes.py`'s own `_resolved_void_handler`):
    # `wire_type` empty, never absent.
    return TypeRef(
        symbol="void#",
        wire_type="",
        wire_format="",
        nullable=False,
        nullable_resolution="resolved",
    )


def _resolve(tmp_path: Path, facts: list) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "OrderListener.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_catalog()], capabilities={"annotation_args"})
    assert skipped == []
    return workspace


def _replies_for(workspace: DuckDbWorkspace, handler: str) -> list[dict]:
    return [
        e
        for e in workspace.query("endpoints")
        if e["direction"] == "outbound" and e["caller"] == handler
    ]


# --- (a) a single-destination @SendTo derives one resolved outbound row ---


def test_a_single_destination_send_to_derives_one_resolved_outbound_reply_row(
    tmp_path: Path,
):
    listener = "com/acme/notify/OrderListener#"
    handler = "com/acme/notify/OrderListener#onReturn()."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_receipt_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=KAFKA_LISTENER, args={"topics": ["order-returns"]}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=SEND_TO, args={"value": ["order-return-receipts"]}),
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    replies = _replies_for(workspace, handler)
    workspace.close()

    assert len(replies) == 1
    [reply] = replies
    assert reply["path"] == "order-return-receipts"
    assert reply["resolution"] == "resolved"
    assert reply["method"] is None
    assert reply["handler"] is None
    assert reply["peer"] is None
    assert reply["handler_signature"] is None
    assert reply["evidence"] == "compiler"
    assert reply["response_shape"] is None
    assert json.loads(reply["request_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": RECEIPT_VIEW,
    }


# --- (b) a two-destination @SendTo derives two rows ------------------------


def test_b_a_two_destination_send_to_derives_two_resolved_rows(tmp_path: Path):
    listener = "com/acme/notify/OrderListener#"
    handler = "com/acme/notify/OrderListener#onMultiReturn()."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_receipt_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=KAFKA_LISTENER, args={"topics": ["order-multi"]}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=SEND_TO, args={"value": ["dest-a", "dest-b"]}),
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    replies = _replies_for(workspace, handler)
    workspace.close()

    assert len(replies) == 2
    assert {r["path"] for r in replies} == {"dest-a", "dest-b"}
    assert all(r["resolution"] == "resolved" for r in replies)
    assert all(json.loads(r["request_shape"])["shape_id"] == RECEIPT_VIEW for r in replies)


# --- (c) a value-returning handler without @SendTo derives one unresolved,
# path-NULL row --------------------------------------------------------------


def test_c_a_value_returning_handler_without_send_to_derives_one_unresolved_row(
    tmp_path: Path,
):
    listener = "com/acme/notify/OrderListener#"
    handler = "com/acme/notify/OrderListener#escalate()."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_receipt_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=KAFKA_LISTENER, args={"topics": ["order-escalations"]}),
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    replies = _replies_for(workspace, handler)
    workspace.close()

    assert len(replies) == 1
    [reply] = replies
    assert reply["path"] is None
    assert reply["resolution"] == "unresolved"
    assert json.loads(reply["request_shape"])["shape_id"] == RECEIPT_VIEW


# --- (d) a void handler derives no reply row --------------------------------


def test_d_a_void_handler_derives_no_reply_row(tmp_path: Path):
    listener = "com/acme/notify/OrderListener#"
    handler = "com/acme/notify/OrderListener#onEvent()."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_void_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=KAFKA_LISTENER, args={"topics": ["order-events"]}),
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    replies = _replies_for(workspace, handler)
    workspace.close()

    assert replies == []


# --- (e) a handler never matched by this catalog's own inbound mapping
# derives nothing, even when annotated with the reply annotation ------------


def test_e_a_handler_never_matched_by_this_catalogs_inbound_mapping_derives_no_reply_row(
    tmp_path: Path,
):
    listener = "com/acme/notify/OrderListener#"
    matched_handler = "com/acme/notify/OrderListener#onAudit()."
    unmatched_handler = "com/acme/notify/OrderListener#neverListened()."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        # A genuinely listened handler, so `endpoints` is not trivially empty
        # — proving the exclusion below is real, not incidental.
        SymbolFact(
            document_id="doc_1",
            symbol=matched_handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_void_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=matched_handler,
            retention="runtime",
            use=AnnotationUse(annotation=KAFKA_LISTENER, args={"topics": ["order-audit"]}),
        ),
        # Carries the reply annotation and a value-returning signature, but
        # no listener annotation at all — this catalog's own inbound mapping
        # never produces an endpoint row for it.
        SymbolFact(
            document_id="doc_1",
            symbol=unmatched_handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_receipt_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=unmatched_handler,
            retention="runtime",
            use=AnnotationUse(annotation=SEND_TO, args={"value": ["dest-never"]}),
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("endpoints")
    unmatched_rows = [e for e in rows if unmatched_handler in (e["handler"], e["caller"])]
    workspace.close()

    assert any(e["handler"] == matched_handler for e in rows)
    assert unmatched_rows == []


# --- (f)/(g) a BARE reply annotation — declared, but naming no destination
# — derives the same path-NULL unresolved row (f) does, never nothing -------


def _bare_send_to_facts(handler: str, listener: str, args: dict) -> list:
    """(f) and (g) differ only in how the bare annotation reached the facts —
    the attribute key absent, or present holding an empty array — so the rest
    of the fixture is shared rather than written twice."""
    return [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_receipt_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=KAFKA_LISTENER, args={"topics": ["order-bare"]}),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=SEND_TO, args=args),
        ),
    ]


def test_f_a_send_to_whose_destination_key_is_absent_derives_one_unresolved_row(
    tmp_path: Path,
):
    """Final review, CRITICAL: a bare `@SendTo` reaches bytecode as its
    annotation's own default — the destination attribute simply not recorded
    — and the engine used to derive NOTHING for it, while the very same
    handler with NO reply annotation at all derived a path-NULL `unresolved`
    row (test (c)). That inverted the evidence: a handler that *declares* it
    replies is strictly stronger evidence of a reply than one that declares
    nothing, and stronger evidence must never produce less output. The bare
    form now lands on (c)'s own answer — the reply destination exists, this
    catalog just cannot name it."""
    listener = "com/acme/notify/OrderListener#"
    handler = "com/acme/notify/OrderListener#onBareAbsent()."
    workspace = _resolve(tmp_path, _bare_send_to_facts(handler, listener, {}))
    replies = _replies_for(workspace, handler)
    workspace.close()

    assert len(replies) == 1
    [reply] = replies
    assert reply["path"] is None
    assert reply["resolution"] == "unresolved"
    assert json.loads(reply["request_shape"])["shape_id"] == RECEIPT_VIEW


def test_g_a_send_to_holding_an_explicit_empty_destination_array_derives_one_unresolved_row(
    tmp_path: Path,
):
    """The other half of (f)'s bare form: `@SendTo({})` written out in
    source, which records the attribute holding an empty array rather than
    omitting it. Same evidence, same answer — the two must not diverge on a
    distinction that is a bytecode emission detail, not a fact about the
    handler."""
    listener = "com/acme/notify/OrderListener#"
    handler = "com/acme/notify/OrderListener#onBareEmpty()."
    workspace = _resolve(tmp_path, _bare_send_to_facts(handler, listener, {"value": []}))
    replies = _replies_for(workspace, handler)
    workspace.close()

    assert len(replies) == 1
    [reply] = replies
    assert reply["path"] is None
    assert reply["resolution"] == "unresolved"
    assert json.loads(reply["request_shape"])["shape_id"] == RECEIPT_VIEW


# --- Fix round 1, BLOCKER: `endpoints` carries no catalog-identity column,
# so two same-protocol `annotation_driven` catalogs must not let one
# catalog's reply pass reach the other's handlers. ---------------------------

OTHER_LISTENER = "com/acme/messaging/annotation/SqsListener#"


def _other_catalog() -> Catalog:
    """A second, invented `annotation_driven` catalog — same protocol
    (`kafka`) as `_catalog()`, a different mapping annotation, no `reply`
    block of its own, and a `source` that sorts before `_catalog()`'s own
    (`derive_endpoints`'s own ordering runs inbound-before-outbound then by
    filename, and both catalogs here are inbound, so this is what puts this
    one's inbound row down first)."""
    return Catalog(
        id="invented-other-listener",
        style="annotation_driven",
        protocol="kafka",
        direction="inbound",
        requires=("annotation_args",),
        source=Path("tests/aaa-other-listener.yml"),
        matches={
            "mapping": {
                "path_from": ["value"],
                "prefix_from": [],
                "method_from": "method",
                "all_methods": [],
                "prefix_annotation": "com.acme.messaging.annotation.OtherTopic",
                "annotations": [{"fqn": "com.acme.messaging.annotation.SqsListener"}],
            },
        },
    )


def test_a_second_same_protocol_catalog_without_reply_never_gets_phantom_reply_rows(
    tmp_path: Path,
):
    """Reviewer-reproduced gap (Task 8 review round 1, BLOCKER): filtering
    `_derive_replies`'s handler set on `protocol`/`direction` alone cannot
    tell catalog A's own inbound rows apart from catalog B's — both are
    `kafka`/`inbound` rows in the very same shared `endpoints` table — so A's
    reply pass would pick up B's value-returning, `@SendTo`-less handler and
    derive a phantom `unresolved` reply row for it, even though B declares no
    `reply` block at all and A's own mapping never matched that method.

    `_other_catalog()` sorts before `_catalog()` (`derive_endpoints`'s own
    filename tie-break), so its inbound row is the one already sitting in
    `endpoints` by the time A's `run` — and therefore A's `_derive_replies`
    — executes: the scenario the reviewer reproduced exactly, not a
    reordering this fix happens to dodge."""
    listener = "com/acme/notify/OrderListener#"
    a_handler = "com/acme/notify/OrderListener#onReturn()."
    b_handler = "com/acme/notify/OrderListener#onSqsMessage()."
    catalog_a = _catalog()
    catalog_b = _other_catalog()
    assert str(catalog_b.source) < str(catalog_a.source)

    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        # B's own handler: value-returning, matched only by B's own mapping
        # annotation — never A's, and B declares no `reply` block at all.
        SymbolFact(
            document_id="doc_1",
            symbol=b_handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_receipt_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=b_handler,
            retention="runtime",
            use=AnnotationUse(annotation=OTHER_LISTENER, args={"value": ["b-topic"]}),
        ),
        # A's own handler, no @SendTo — the (c)-style unresolved case, kept
        # here so A's own derivation is proven correct alongside the
        # isolation proof, not merely "A derives nothing at all".
        SymbolFact(
            document_id="doc_1",
            symbol=a_handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
            signature=Signature(returns=_receipt_returns()),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=a_handler,
            retention="runtime",
            use=AnnotationUse(annotation=KAFKA_LISTENER, args={"topics": ["order-returns"]}),
        ),
    ]
    write_fact_file(tmp_path / "facts" / "OrderListener.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [catalog_a, catalog_b], capabilities={"annotation_args"})
    rows = workspace.query("endpoints")
    b_rows = [e for e in rows if b_handler in (e["handler"], e["caller"])]
    a_replies = _replies_for(workspace, a_handler)
    workspace.close()

    assert skipped == []
    # B's handler carries no reply row at all — only its own inbound row.
    assert len(b_rows) == 1
    assert b_rows[0]["direction"] == "inbound"
    # A's own handler still gets its own (unresolved, no @SendTo) reply row
    # — the fix narrows scope without breaking A's own derivation.
    assert len(a_replies) == 1
    assert a_replies[0]["resolution"] == "unresolved"
