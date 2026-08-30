"""Tests for the `single_call` engine (D02 §2's `single_call` style) and the
shared call-payload helpers it and Task 11's `fluent` engine both use.

Facts are hand-built to mirror the *real* emitted grammar exactly — verified
against a live scan of `fixtures/orders-service`'s `BillingRestTemplate`
during this task's checkpoint — rather than compiling and scanning real
bytecode, so each behaviour is isolated and fast."""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.shapes import derive_endpoint_shapes
from sextant.application.resolve.shapes.contracts import split_url
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS_DIR = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"
CAPABILITIES = {"call_site", "string_constants"}
# The module-coordinates prefix a real symbol fact's own `symbol` carries
# (D00 §5a) — only `single_call`'s `supertypes` lookup and the shape pass's
# own `fields`/`enum_types` queries ever read it; every call-argument symbol
# stays bare, exactly as the real fixture emits it.
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

RESTTEMPLATE = "org/springframework/web/client/RestTemplate#"
ORDER_VIEW = "com/acme/orders/contracts/OrderView#"
ORDER_REQUEST = "com/acme/orders/contracts/OrderRequest#"


def _catalog() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "spring-resttemplate")


def _document(
    document_id: str = "doc_1", relative_path: str = "com/acme/http/Client.java"
) -> Document:
    return Document(
        document_id=document_id,
        relative_path=relative_path,
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _resolve(tmp_path: Path, facts: list, catalog: Catalog | None = None):
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [catalog or _catalog()], capabilities=CAPABILITIES)
    assert skipped == []
    return workspace


# --- 1. getForObject, a string url and a class-literal response -----------


def test_a_string_url_and_a_class_literal_response_derive_a_resolved_endpoint(
    tmp_path: Path,
):
    caller = "com/acme/http/Client#getBalance()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="getForObject",
                descriptor="(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=12,
            arguments=[
                CallArgument(kind="string", value="/billing/balances/{id}"),
                CallArgument(kind="class", symbol=ORDER_VIEW),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("GET", "/billing/balances/{id}")
    assert endpoint["direction"] == "outbound"
    assert endpoint["resolution"] == "resolved"
    assert endpoint["handler"] is None
    assert endpoint["peer"] is None
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_VIEW,
    }
    assert endpoint["request_shape"] is None


# --- 2. exchange: an enum verb, the HttpEntity hop, and the PTR response --


def _batch_facts(caller: str) -> list:
    return [
        # new OrderRequest()
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(owner=ORDER_REQUEST, name="<init>", descriptor="()V"),
            invoke_kind="special",
            ordinal=0,
            receiver=8,
            result=None,
            arguments=[],
        ),
        # new HttpEntity<>(orderRequest)
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner="org/springframework/http/HttpEntity#",
                name="<init>",
                descriptor="(Ljava/lang/Object;)V",
            ),
            invoke_kind="special",
            ordinal=1,
            receiver=6,
            result=None,
            arguments=[CallArgument(kind="instance", source=8, symbol=ORDER_REQUEST)],
        ),
        # new ParameterizedTypeReference<List<OrderView>>() {}
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner="com/acme/http/Client$1#",
                name="<init>",
                descriptor="(Lcom/acme/http/Client;)V",
            ),
            invoke_kind="special",
            ordinal=2,
            receiver=12,
            result=None,
            arguments=[CallArgument(kind="unresolved")],
        ),
        # restTemplate.exchange(url, HttpMethod.POST, entity, ptr)
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="exchange",
                descriptor=(
                    "(Ljava/lang/String;Lorg/springframework/http/HttpMethod;"
                    "Lorg/springframework/http/HttpEntity;"
                    "Lorg/springframework/core/ParameterizedTypeReference;"
                    "[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;"
                ),
            ),
            invoke_kind="virtual",
            ordinal=3,
            receiver=3,
            result=18,
            arguments=[
                CallArgument(kind="string", value="/billing/batch"),
                CallArgument(kind="enum", symbol="org/springframework/http/HttpMethod#POST."),
                CallArgument(
                    kind="instance", source=6, symbol="org/springframework/http/HttpEntity#"
                ),
                CallArgument(kind="instance", source=12, symbol="com/acme/http/Client$1#"),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]


def _ptr_symbol_fact(document_id: str = "doc_1") -> SymbolFact:
    """The anonymous PTR subclass's own symbol fact: its declared generic
    supertype names the payload (D00 §5a; D02 §2h)."""
    return SymbolFact(
        document_id=document_id,
        symbol="com/acme/http/Client$1#",
        construct_kind="class",
        supertype=TypeRef(
            symbol="org/springframework/core/ParameterizedTypeReference#",
            nullable=True,
            nullable_resolution="resolved",
            wire_type="object",
            wire_format="",
            arguments=[
                TypeRef(
                    symbol="java/util/List#",
                    nullable=True,
                    nullable_resolution="resolved",
                    wire_type="array",
                    wire_format="",
                    arguments=[
                        TypeRef(
                            symbol=ORDER_VIEW,
                            nullable=True,
                            nullable_resolution="resolved",
                            wire_type="object",
                            wire_format="",
                        )
                    ],
                )
            ],
        ),
    )


def test_exchange_resolves_the_enum_verb_the_http_entity_hop_and_the_ptr_response(
    tmp_path: Path,
):
    caller = "com/acme/http/Client#batchSettlements()."
    facts = [*_batch_facts(caller), _ptr_symbol_fact()]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("POST", "/billing/batch")
    assert endpoint["resolution"] == "resolved"
    # The HttpEntity one-hop: the linked constructor's own payload_ctor_arg
    # (0) is the OrderRequest instance built inline.
    assert json.loads(endpoint["request_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_REQUEST,
    }
    # The PTR follow: the anonymous subclass's own declared supertype names
    # List<OrderView>, fed to expansion._described exactly as a field
    # reference — the array-ness survives, and the item roots OrderView.
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "array",
        "wire_format": "",
        "nullable": True,
        "item": {
            "wire_type": "object",
            "wire_format": "",
            "nullable": True,
            "shape_id": ORDER_VIEW,
        },
    }


# --- Task 10 hardening: PTR/supertype resolution -------------------------
#
# Task 9 delivered the `supertypes` named query and the carrier walk inside
# `argument_descriptor`'s `type_carrier` path (`contracts.py`). These three
# tests gate that delivery from a reviewer's seat rather than the
# implementer's: a bare (non-collection) carrier payload, the honest-`None`
# answer for an `instance` this catalog's carrier/wrapper rules cannot open,
# and the workspace-wide reach of the `supertypes` join across documents.


def test_a_bare_ptr_carrier_resolves_an_object_descriptor_and_the_shape_expands(
    tmp_path: Path,
):
    """D02 §2h's PTR follow for the non-collection case: `new
    ParameterizedTypeReference<OrderView>() {}` — no `List` around the
    payload — must still root at `OrderView` itself as an object descriptor.
    `test_exchange_resolves_...` above already proves the carrier walk for a
    `List<OrderView>` supertype; this proves `_reference_of`'s `carried[0]`
    feeds `_described` a bare (non-array) reference just as directly, since
    nothing about the one-hop follow is collection-specific. `OrderView`
    carries a real field fact here, unlike the class-literal tests above, so
    the shape assertions also prove this call-only root genuinely expands —
    `shapes`/`shape_fields` rows behind the `shape_id`, not a dangling
    reference (Task 9 review, Finding C1, mutation-caught again here: a
    broken `carried[0]` index, or a carrier walk that forgot to feed
    `_described`, would either raise, describe the wrong symbol, or leave
    `OrderView` absent from `shapes` entirely — any of which fails this
    test)."""
    caller = "com/acme/http/Client#getSingleObject()."
    anonymous = "com/acme/http/Client$2#"
    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + ORDER_VIEW, construct_kind="class"),
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + ORDER_VIEW + "id.",
            construct_kind="field",
            enclosing=_MODULE + ORDER_VIEW,
            signature=Signature(
                returns=TypeRef(
                    symbol="java/lang/String#",
                    wire_type="string",
                    wire_format="",
                    nullable=True,
                    nullable_resolution="resolved",
                )
            ),
        ),
        # new ParameterizedTypeReference<OrderView>() {}
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=anonymous, name="<init>", descriptor="(Lcom/acme/http/Client;)V"
            ),
            invoke_kind="special",
            ordinal=0,
            receiver=12,
            result=None,
            arguments=[CallArgument(kind="unresolved")],
        ),
        # restTemplate.postForEntity(url, orderRequest.class, ptr)
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="postForEntity",
                descriptor=(
                    "(Ljava/lang/String;Ljava/lang/Object;"
                    "Ljava/lang/Class;[Ljava/lang/Object;)"
                    "Lorg/springframework/http/ResponseEntity;"
                ),
            ),
            invoke_kind="virtual",
            ordinal=1,
            receiver=3,
            result=18,
            arguments=[
                CallArgument(kind="string", value="/billing/single-object"),
                CallArgument(kind="class", symbol=ORDER_REQUEST),
                CallArgument(kind="instance", source=12, symbol=anonymous),
                CallArgument(kind="unresolved"),
            ],
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=anonymous,
            construct_kind="class",
            supertype=TypeRef(
                symbol="org/springframework/core/ParameterizedTypeReference#",
                nullable=True,
                nullable_resolution="resolved",
                wire_type="object",
                wire_format="",
                arguments=[
                    TypeRef(
                        symbol=ORDER_VIEW,
                        nullable=True,
                        nullable_resolution="resolved",
                        wire_type="object",
                        wire_format="",
                    )
                ],
            ),
        ),
    ]
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    catalog = _catalog()
    skipped = derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    assert skipped == []
    expanded = derive_endpoint_shapes(workspace, [catalog], capabilities=CAPABILITIES)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    shape_ids = {s["shape_id"] for s in workspace.query("shapes")}
    order_view_fields = {
        f["wire_name"] for f in workspace.query("shape_fields") if f["shape_id"] == ORDER_VIEW
    }
    workspace.close()

    assert endpoint["resolution"] == "resolved"
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_VIEW,
    }
    assert ORDER_VIEW in shape_ids
    assert order_view_fields == {"id"}
    assert ORDER_VIEW not in expanded.unexpanded_types


def test_an_instance_of_a_type_with_no_supertype_fact_honestly_resolves_no_payload(
    tmp_path: Path,
):
    """`argument_descriptor` must stay honest, never guess, when an
    `instance` argument's own type carries no `supertype` fact at all — the
    ordinary case for a JDK/framework type this catalog never scanned, such
    as a `ResponseEntity` built inline and passed on rather than returned.
    `workspace_types.supertypes.get(symbol)` misses; the type is not a
    declared `call_wrappers` entry either; `_reference_of` falls to
    `_bare_reference`, which `root_type` then finds *is* one of the
    catalog's own declared `wrappers` (`ResponseEntity`) with nothing
    visible at its payload position — the same "declared envelope, nothing
    inside it" answer `_payload_descriptor` already gives an erased
    `ResponseEntity` return type (D02 §2a). `None`, not a crash and not a
    shape describing `ResponseEntity` itself.

    This capture succeeds as a *capture* (`kind` is `instance`, never
    `unresolved`) — I1 governs a capture the scanner could not read, not one
    that was read and honestly names no payload — so it alone would not
    drop the row. To also exercise I1's row-level drop on the very same
    row, `body_arg` is a genuinely unresolved capture here (a passed-through
    parameter, mirroring `test_an_unresolved_body_capture_drops_...` above);
    the two assertions below are independent proofs on the same row: the
    `response_shape` column reads `None` because of the wrapper-envelope
    rule, while `resolution` reads `unresolved` because of `body_arg`'s
    separate failure — proving `argument_descriptor`'s honest-`None` answer
    for this instance neither masks nor depends on a different capture's
    own failure on the same call site."""
    caller = "com/acme/http/Client#submitWrapped()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="postForObject",
                descriptor=(
                    "(Ljava/lang/String;Ljava/lang/Object;"
                    "Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;"
                ),
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=9,
            arguments=[
                CallArgument(kind="string", value="/billing/wrapped-response"),
                CallArgument(kind="unresolved"),
                CallArgument(
                    kind="instance",
                    source=9,
                    symbol="org/springframework/http/ResponseEntity#",
                ),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("POST", "/billing/wrapped-response")
    assert endpoint["resolution"] == "unresolved"
    assert endpoint["response_shape"] is None


def test_a_carrier_subtype_declared_in_a_different_document_still_resolves(
    tmp_path: Path,
):
    """The `supertypes` named query (`storage/duckdb/workspace.py`) reads
    `raw_facts` across the whole workspace, never scoped to one document —
    proved by moving the anonymous PTR subclass's own symbol fact (which
    `_batch_facts`' `exchange` call references by symbol alone) into a
    SEPARATE document from the call site itself. A query accidentally
    scoped to the call site's own `document_id` — a plausible mistake a
    per-document join invites, and one `test_exchange_resolves_...` above
    cannot catch, since its symbol fact and call site already share
    `doc_1` — would silently miss this join and describe the same
    `List<OrderView>` payload as unresolved instead; this test is the one
    that would fail if that regressed."""
    caller = "com/acme/http/Client#batchSettlementsAcrossDocuments()."
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document("doc_1"), _batch_facts(caller))
    write_fact_file(
        tmp_path / "facts" / "Types.jsonl",
        _document("doc_2", relative_path="com/acme/http/Types.java"),
        [_ptr_symbol_fact(document_id="doc_2")],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_catalog()], capabilities=CAPABILITIES)
    assert skipped == []
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["resolution"] == "resolved"
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "array",
        "wire_format": "",
        "nullable": True,
        "item": {
            "wire_type": "object",
            "wire_format": "",
            "nullable": True,
            "shape_id": ORDER_VIEW,
        },
    }


# --- 3. a variable url: the row still derives, unresolved -----------------


def test_a_variable_url_still_derives_the_row_unresolved(tmp_path: Path):
    caller = "com/acme/http/Client#removeSomething()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="delete",
                descriptor="(Ljava/lang/String;[Ljava/lang/Object;)V",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=None,
            arguments=[CallArgument(kind="unresolved")],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    # "This method calls something over HTTP" is true and useful on its own
    # (D02 §2): the row derives even though the template could not be read.
    assert endpoint["method"] == "DELETE"
    assert endpoint["path"] is None
    assert endpoint["resolution"] == "unresolved"


# --- 4. two identical calls in one method dedup to one row ----------------


def test_two_identical_calls_in_one_method_dedup_to_one_row(tmp_path: Path):
    caller = "com/acme/http/Client#getBalanceTwice()."

    def _call(ordinal: int, receiver: int, result: int) -> CallSiteFact:
        return CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="getForObject",
                descriptor="(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=ordinal,
            receiver=receiver,
            result=result,
            arguments=[
                CallArgument(kind="string", value="/billing/duplicate"),
                CallArgument(kind="class", symbol=ORDER_VIEW),
                CallArgument(kind="unresolved"),
            ],
        )

    facts = [_call(0, 3, 12), _call(1, 3, 15)]
    workspace = _resolve(tmp_path, facts)
    rows = [e for e in workspace.query("endpoints") if e["path"] == "/billing/duplicate"]
    workspace.close()

    assert len(rows) == 1


# --- I1: a declared capture that fails to resolve drops the row's own
# resolution (checkpoint ruling I1) — the url stays independently correct,
# and a different, successfully-resolved column on the very same row keeps
# its real value. ------------------------------------------------------


def test_an_unresolved_body_capture_drops_the_rows_resolution_but_keeps_the_url(
    tmp_path: Path,
):
    """Mirrors the real fixture's `postForObject` exactly: `settlement` is a
    passed-through method parameter, not a literal or a `NEW`, so the
    scanner records it as `unresolved` (D00 §5) even though the url is a
    plain string. Before I1, this NULLed `request_shape` while leaving
    `resolution` at `resolved` — indistinguishable from a call that
    genuinely declares no body, violating D01's one-meaning-per-NULL rule.
    After I1: the row's own `resolution` drops to `unresolved`; `path`
    still carries the known template (the url's own answer is untouched by
    a *different* capture's failure); and `response_shape` — a separately
    resolved capture on the same row — still carries its real descriptor,
    proving the two columns stay independently meaningful even once the row
    itself reads `unresolved`."""
    caller = "com/acme/http/Client#submitSettlement()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="postForObject",
                descriptor=(
                    "(Ljava/lang/String;Ljava/lang/Object;"
                    "Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;"
                ),
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=9,
            arguments=[
                CallArgument(kind="string", value="/billing/settlements"),
                CallArgument(kind="unresolved"),
                CallArgument(kind="class", symbol=ORDER_VIEW),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("POST", "/billing/settlements")
    assert endpoint["resolution"] == "unresolved"
    assert endpoint["request_shape"] is None
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_VIEW,
    }


# --- C1: a payload type reached only through a call site's own arguments
# still gets expanded — never a shape_id with nothing behind it. -----------


def test_a_call_only_payload_type_still_reaches_shape_expansion(tmp_path: Path):
    """Reviewer-proved gap (Task 9 review, Finding C1): a response type
    reached only through a call site's own arguments (D02 §2h) — never
    through any handler's declared signature — must still get expanded.

    Before the fix, `derive_endpoint_shapes`'s per-resolve `shapes_reset`
    (which runs *after* `derive_endpoints`, and therefore after
    `single_call.run`, unconditionally) wiped whatever `single_call`'s own
    `referenced` accumulator reached — that accumulator was built and
    threaded through `CallFacts`, and then never read by anything that ran
    after the reset. The endpoint row still named a `shape_id`; the
    `shapes`/`shape_fields` rows behind it simply did not exist. This test
    proves both halves: a field-bearing call-only type gets real
    `shapes`/`shape_fields` rows, and a call-only type with no field facts
    at all still gets an open `shapes` row and is named in
    `unexpanded_types` — reported as a gap, never silently dropped."""
    call_only = "com/acme/http/CallOnly#"
    unexpandable = "com/acme/http/Unexpandable#"
    only_caller = "com/acme/http/Client#getOnly()."
    gone_caller = "com/acme/http/Client#getUnexpandable()."
    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + call_only, construct_kind="class"),
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + call_only + "note.",
            construct_kind="field",
            enclosing=_MODULE + call_only,
            signature=Signature(
                returns=TypeRef(
                    symbol="java/lang/String#",
                    wire_type="string",
                    wire_format="",
                    nullable=True,
                    nullable_resolution="resolved",
                )
            ),
        ),
        CallSiteFact(
            document_id="doc_1",
            caller=only_caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="getForObject",
                descriptor="(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=12,
            arguments=[
                CallArgument(kind="string", value="/only/thing"),
                CallArgument(kind="class", symbol=call_only),
                CallArgument(kind="unresolved"),
            ],
        ),
        # A second call-only response type with no symbol fact at all — no
        # field list, no class fact — the real "third-party type nobody
        # described" case D02 §2g and D2 already name for a signature-rooted
        # payload, now proven for a call-site-rooted one too.
        CallSiteFact(
            document_id="doc_1",
            caller=gone_caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="getForObject",
                descriptor="(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=13,
            arguments=[
                CallArgument(kind="string", value="/unexpandable/thing"),
                CallArgument(kind="class", symbol=unexpandable),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    catalog = _catalog()
    skipped = derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    assert skipped == []
    expanded = derive_endpoint_shapes(workspace, [catalog], capabilities=CAPABILITIES)
    shape_ids = {s["shape_id"] for s in workspace.query("shapes")}
    call_only_fields = {
        f["wire_name"] for f in workspace.query("shape_fields") if f["shape_id"] == call_only
    }
    workspace.close()

    assert call_only in shape_ids
    assert call_only_fields == {"note"}
    assert unexpandable in shape_ids
    assert unexpandable in expanded.unexpanded_types


# --- The shared url split (CP-2), unit-tested directly ---------------------


def test_split_url_reads_an_absolute_url_as_peer_and_path():
    assert split_url("http://billing.internal/v1/invoices") == (
        "billing.internal",
        "/v1/invoices",
    )


def test_split_url_leaves_a_relative_url_path_only_with_no_peer():
    assert split_url("/billing/settlements/{id}") == (None, "/billing/settlements/{id}")


def test_split_url_reads_an_absolute_url_with_no_path_as_an_empty_path():
    assert split_url("https://billing.internal") == ("billing.internal", "")


# --- The `fluent` engine (Task 11): chains reassembled from value links ----
#
# No catalog ships with this task (Task 12 writes the real spring-webclient/
# spring-restclient/okhttp files) — these are the "invented catalogs tests
# construct by hand" `Catalog` itself already documents (`ports/catalogs.py`).
# Facts mirror the real emitted grammar the checkpoint verified live: a
# WebClient chain links result -> receiver directly; an OkHttp constructor
# root chains by its own receiver (CP-3, its result is void); OkHttp's
# `build()` -> `newCall()` split joins through an argument `source`, never
# through receiver/result (`terminal_via_argument`).

FLUENT_CAPABILITIES = {"call_site", "string_constants", "chain_reconstruction"}

WEBCLIENT = "com/acme/http/WebClient#"
URI_SPEC = "com/acme/http/WebClient$UriSpec#"
RESPONSE_SPEC = "com/acme/http/WebClient$ResponseSpec#"

_WEBCLIENT_MATCHES = {
    "roots": [
        {"owner": "com.acme.http.WebClient", "method": "get", "captures": {"http_method": "GET"}},
        {
            "owner": "com.acme.http.WebClient",
            "method": "post",
            "captures": {"http_method": "POST"},
        },
    ],
    "steps": [
        {"method": "uri", "captures": {"url": "arg0"}},
        {"method": "bodyValue", "captures": {"body": "arg0"}},
        {"method": "bodyToMono", "captures": {"response": "arg0"}},
        {"method": "bodyToFlux", "captures": {"response": "arg0", "response_is": "array"}},
    ],
    "terminal": ["retrieve", "exchange"],
}

BUILDER = "com/acme/http/Request$Builder#"
OKHTTP_CLIENT = "com/acme/http/OkHttpClient#"
REQUEST = "com/acme/http/Request#"

_OKHTTP_MATCHES = {
    "roots": [
        {
            "owner": "com.acme.http.Request$Builder",
            "method": "<init>",
            "captures": {"http_method": "GET"},
        }
    ],
    "steps": [
        {"method": "url", "captures": {"url": "arg0"}},
        {"method": "post", "captures": {"http_method": "POST", "body": "arg0"}},
    ],
    "terminal": [{"method": "build", "terminal_via_argument": True}],
}


def _fluent_catalog(matches: dict, catalog_id: str = "invented-fluent") -> Catalog:
    return Catalog(
        id=catalog_id,
        style="fluent",
        protocol="http",
        direction="outbound",
        requires=("call_site", "string_constants", "chain_reconstruction"),
        matches=matches,
        source=Path(f"tests/{catalog_id}.yml"),
    )


def _resolve_fluent(tmp_path: Path, facts: list, catalog: Catalog):
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    assert skipped == []
    return workspace


def _call(
    caller: str,
    owner: str,
    name: str,
    ordinal: int,
    receiver: int | None,
    result: int | None,
    arguments: list | None = None,
    invoke_kind: str = "virtual",
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor="()V"),
        invoke_kind=invoke_kind,
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=arguments or [],
    )


def test_a_webclient_shaped_chain_derives_get_with_url_and_bodytomono_response(
    tmp_path: Path,
):
    """The plain case: root seeds the verb, `uri` captures the url, the
    chain runs past `retrieve` (executability, not the walk's end) to
    `bodyToMono`, which captures the response — exactly D02 §4's example."""
    caller = "com/acme/http/Client#getOrder()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/orders/{id}")],
        ),
        _call(caller, URI_SPEC, "retrieve", 2, receiver=10, result=13),
        _call(
            caller,
            RESPONSE_SPEC,
            "bodyToMono",
            3,
            receiver=13,
            result=16,
            arguments=[CallArgument(kind="class", symbol=ORDER_VIEW)],
        ),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("GET", "/orders/{id}")
    assert endpoint["direction"] == "outbound"
    assert endpoint["resolution"] == "resolved"
    assert endpoint["handler"] is None
    assert endpoint["peer"] is None
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_VIEW,
    }
    assert endpoint["request_shape"] is None


def test_a_repeated_step_captures_last_wins(tmp_path: Path):
    """Two `uri` calls chained one after the other — the second overwrites
    the first's own `url` capture, in visitation order, with no special
    bookkeeping beyond folding captures as the walk reaches each row."""
    caller = "com/acme/http/Client#getOrderTwice()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/first")],
        ),
        _call(
            caller,
            URI_SPEC,
            "uri",
            2,
            receiver=10,
            result=11,
            arguments=[CallArgument(kind="string", value="/second")],
        ),
        _call(caller, URI_SPEC, "retrieve", 3, receiver=11, result=13),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "/second"


def test_two_interleaved_chains_in_one_caller_derive_two_correct_endpoints(
    tmp_path: Path,
):
    """Value ids, not adjacency, keep two builders apart even when their own
    call sites are interleaved ordinal by ordinal within one caller — the
    exact case adjacency heuristics would fabricate a link across."""
    caller = "com/acme/http/Client#getBoth()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(caller, WEBCLIENT, "post", 1, receiver=5, result=6),
        _call(
            caller,
            URI_SPEC,
            "uri",
            2,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/a")],
        ),
        _call(
            caller,
            URI_SPEC,
            "uri",
            3,
            receiver=6,
            result=11,
            arguments=[CallArgument(kind="string", value="/b")],
        ),
        _call(caller, URI_SPEC, "retrieve", 4, receiver=10, result=13),
        _call(caller, URI_SPEC, "retrieve", 5, receiver=11, result=14),
        _call(
            caller,
            RESPONSE_SPEC,
            "bodyToMono",
            6,
            receiver=13,
            result=16,
            arguments=[CallArgument(kind="class", symbol=ORDER_VIEW)],
        ),
        _call(
            caller,
            RESPONSE_SPEC,
            "bodyToMono",
            7,
            receiver=14,
            result=17,
            arguments=[CallArgument(kind="class", symbol=ORDER_REQUEST)],
        ),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    endpoints = {e["path"]: e for e in workspace.query("endpoints") if e["caller"] == caller}
    workspace.close()

    assert set(endpoints) == {"/a", "/b"}
    assert endpoints["/a"]["method"] == "GET"
    assert json.loads(endpoints["/a"]["response_shape"])["shape_id"] == ORDER_VIEW
    assert endpoints["/b"]["method"] == "POST"
    assert json.loads(endpoints["/b"]["response_shape"])["shape_id"] == ORDER_REQUEST


def test_a_rootless_fragment_derives_nothing(tmp_path: Path):
    """`uri`/`retrieve`/`bodyToMono` calls with no `get`/`post` root anywhere
    in the caller: nothing ever starts a walk, so nothing derives — a
    builder fragment reached by nothing this catalog calls a root is not a
    chain at all."""
    caller = "com/acme/http/Client#orphanSteps()."
    facts = [
        _call(
            caller,
            URI_SPEC,
            "uri",
            0,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/x")],
        ),
        _call(caller, URI_SPEC, "retrieve", 1, receiver=10, result=13),
        _call(
            caller,
            RESPONSE_SPEC,
            "bodyToMono",
            2,
            receiver=13,
            result=16,
            arguments=[CallArgument(kind="class", symbol=ORDER_VIEW)],
        ),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    endpoints = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoints == []


def test_a_root_without_a_terminal_derives_nothing(tmp_path: Path):
    """A `Request.Builder` built and never executed made no call (D02 §4):
    the root and its `uri` step are real rows, but the chain never reaches
    `retrieve`/`exchange`, so nothing derives."""
    caller = "com/acme/http/Client#abandonedBuilder()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/y")],
        ),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    endpoints = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoints == []


def test_bodytoflux_wraps_the_response_in_an_array_descriptor(tmp_path: Path):
    caller = "com/acme/http/Client#listOrders()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/orders")],
        ),
        _call(caller, URI_SPEC, "retrieve", 2, receiver=10, result=13),
        _call(
            caller,
            RESPONSE_SPEC,
            "bodyToFlux",
            3,
            receiver=13,
            result=16,
            arguments=[CallArgument(kind="class", symbol=ORDER_VIEW)],
        ),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "array",
        "wire_format": "",
        "nullable": True,
        "item": {
            "wire_type": "object",
            "wire_format": "",
            "nullable": True,
            "shape_id": ORDER_VIEW,
        },
    }


def test_a_uri_lambda_argument_derives_the_row_unresolved(tmp_path: Path):
    """`uri(uriBuilder -> …)` records a real `lambda`-kind argument (D00 §5),
    never a `string` — the url capture fails honestly, and per I1 that drops
    the row's own `resolution`, even though `bodyToMono`'s own response
    capture, a completely different step, still resolves fine on the same
    row."""
    caller = "com/acme/http/Client#getWithBuilder()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="lambda", symbol="com/acme/http/Client$$Lambda$1#")],
        ),
        _call(caller, URI_SPEC, "retrieve", 2, receiver=10, result=13),
        _call(
            caller,
            RESPONSE_SPEC,
            "bodyToMono",
            3,
            receiver=13,
            result=16,
            arguments=[CallArgument(kind="class", symbol=ORDER_VIEW)],
        ),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["resolution"] == "unresolved"
    assert endpoint["path"] is None
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_VIEW,
    }


def test_okhttp_build_joins_newcall_through_the_argument_source(tmp_path: Path):
    """OkHttp's split: the builder chain's own last row is `build` — nothing
    in this caller has a `receiver` matching `build`'s own `result`, so the
    walk would otherwise end right there, unresolved. `terminal_via_argument`
    is the second, argument-`source` join the checkpoint verified live
    (`build`'s `result` == `newCall`'s own argument `source`) — found among
    ALL of this caller's call sites, never through receiver/result chaining,
    because `newCall`'s own receiver is the client, not the builder. Also
    proves the negative: the same builder chain with no `newCall` row at all
    derives nothing, so `build` alone — reached but never joined — is not
    itself enough."""
    catalog = _fluent_catalog(_OKHTTP_MATCHES, catalog_id="invented-okhttp")
    executed = "com/acme/http/Client#legacyExport()."
    abandoned = "com/acme/http/Client#unusedBuilder()."

    def _builder_chain(caller: str) -> list:
        return [
            _call(caller, BUILDER, "<init>", 0, receiver=2, result=None, invoke_kind="special"),
            _call(
                caller,
                BUILDER,
                "url",
                1,
                receiver=2,
                result=8,
                arguments=[
                    CallArgument(kind="string", value="https://legacy.acme.internal/legacy/exports")
                ],
            ),
            _call(caller, BUILDER, "build", 2, receiver=8, result=14),
        ]

    facts = [
        *_builder_chain(executed),
        _call(
            executed,
            OKHTTP_CLIENT,
            "newCall",
            3,
            receiver=99,
            result=20,
            arguments=[CallArgument(kind="instance", source=14, symbol=REQUEST)],
        ),
        *_builder_chain(abandoned),
    ]
    workspace = _resolve_fluent(tmp_path, facts, catalog)
    endpoints = [e for e in workspace.query("endpoints") if e["caller"] == executed]
    abandoned_endpoints = [e for e in workspace.query("endpoints") if e["caller"] == abandoned]
    workspace.close()

    [endpoint] = endpoints
    assert (endpoint["method"], endpoint["peer"], endpoint["path"]) == (
        "GET",
        "legacy.acme.internal",
        "/legacy/exports",
    )
    assert endpoint["resolution"] == "resolved"
    assert abandoned_endpoints == []


# --- Fix round 1: owner-gated steps, the terminal_via_argument mapping, and
# the void-mid-chain guard's own covering test. -----------------------------

REQUEST_BODY_SPEC = "com/acme/http/RestClient$RequestBodySpec#"
RESTCLIENT_RESPONSE_SPEC = "com/acme/http/RestClient$ResponseSpec#"
RESTCLIENT = "com/acme/http/RestClient#"

# RestClient's own `body` reused for two different roles on two different
# types — a request-setter on `RequestBodySpec`, a response-extractor on
# `ResponseSpec` — distinguishable only by `owner`, never by method name
# alone (D02 §4, amended).
_RESTCLIENT_MATCHES = {
    "roots": [
        {"owner": "com.acme.http.RestClient", "method": "post", "captures": {"http_method": "POST"}}
    ],
    "steps": [
        {"method": "uri", "captures": {"url": "arg0"}},
        {
            "method": "body",
            "owner": "com.acme.http.RestClient$RequestBodySpec",
            "captures": {"body": "arg0"},
        },
        {
            "method": "body",
            "owner": "com.acme.http.RestClient$ResponseSpec",
            "captures": {"response": "arg0"},
        },
    ],
    "terminal": ["retrieve"],
}


def test_an_owner_scoped_step_disambiguates_a_reused_method_name(tmp_path: Path):
    """Two `body` steps, same method name, correctly captured into two
    different fields — `body` (the request) and `response` — purely because
    each declares a different `owner` and the walk matches each row's own
    owner against it, not the method name alone."""
    caller = "com/acme/http/Client#createOrder()."
    facts = [
        _call(caller, RESTCLIENT, "post", 0, receiver=3, result=4),
        _call(
            caller,
            REQUEST_BODY_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/orders")],
        ),
        _call(
            caller,
            REQUEST_BODY_SPEC,
            "body",
            2,
            receiver=10,
            result=13,
            arguments=[CallArgument(kind="instance", symbol=ORDER_REQUEST)],
        ),
        _call(caller, REQUEST_BODY_SPEC, "retrieve", 3, receiver=13, result=16),
        _call(
            caller,
            RESTCLIENT_RESPONSE_SPEC,
            "body",
            4,
            receiver=16,
            result=19,
            arguments=[CallArgument(kind="class", symbol=ORDER_VIEW)],
        ),
    ]
    workspace = _resolve_fluent(
        tmp_path, facts, _fluent_catalog(_RESTCLIENT_MATCHES, "invented-restclient")
    )
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("POST", "/orders")
    assert json.loads(endpoint["request_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_REQUEST,
    }
    assert json.loads(endpoint["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_VIEW,
    }


def test_two_same_named_steps_with_no_distinguishing_owner_is_refused(tmp_path: Path):
    """Silent last-wins on two `body` steps that never declare — or share —
    an `owner` would hide the exact catalog bug §4's owner filter exists to
    surface. Refused loudly, naming the file, per `ports/catalogs.py`'s own
    discipline: an unchecked value never stays in the file."""
    matches = {
        "roots": [
            {
                "owner": "com.acme.http.RestClient",
                "method": "post",
                "captures": {"http_method": "POST"},
            }
        ],
        "steps": [
            {"method": "body", "captures": {"body": "arg0"}},
            {"method": "body", "captures": {"response": "arg0"}},
        ],
        "terminal": ["retrieve"],
    }
    catalog = _fluent_catalog(matches, "invented-ambiguous")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    workspace.close()

    assert "invented-ambiguous.yml" in str(raised.value)
    assert "body" in str(raised.value)


LOGGER = "com/acme/http/Logger#"

_OKHTTP_FILTERED_MATCHES = {
    "roots": [
        {
            "owner": "com.acme.http.Request$Builder",
            "method": "<init>",
            "captures": {"http_method": "GET"},
        }
    ],
    "steps": [{"method": "url", "captures": {"url": "arg0"}}],
    "terminal": [
        {
            "method": "build",
            "terminal_via_argument": {"owner": "com.acme.http.OkHttpClient", "method": "newCall"},
        }
    ],
}


def test_terminal_via_argument_mapping_excludes_a_non_executing_use(tmp_path: Path):
    """The reviewer's fabrication channel: a bare `terminal_via_argument:
    true` completes the chain for ANY row consuming the built value, so a
    `log.debug("…", request)` alongside a genuine, never-called
    `client.newCall(request)` would derive an endpoint for a request that
    was built and logged but never sent. An `{owner, method}` mapping closes
    it — narrowing the join to the one declared executing call — proved here
    both ways: `logged_only` (debug, no `newCall`) derives nothing;
    `logged_then_sent` (debug AND the real `newCall`) derives correctly, so
    the mapping discriminates rather than simply disabling the join."""
    catalog = _fluent_catalog(_OKHTTP_FILTERED_MATCHES, "invented-okhttp-filtered")
    logged_only = "com/acme/http/Client#loggedButNeverSent()."
    logged_then_sent = "com/acme/http/Client#loggedThenSent()."

    def _builder_chain(caller: str) -> list:
        return [
            _call(caller, BUILDER, "<init>", 0, receiver=2, result=None, invoke_kind="special"),
            _call(
                caller,
                BUILDER,
                "url",
                1,
                receiver=2,
                result=8,
                arguments=[
                    CallArgument(kind="string", value="https://legacy.acme.internal/legacy/exports")
                ],
            ),
            _call(caller, BUILDER, "build", 2, receiver=8, result=14),
        ]

    def _debug_log(caller: str) -> CallSiteFact:
        return _call(
            caller,
            LOGGER,
            "debug",
            3,
            receiver=None,
            result=None,
            arguments=[CallArgument(kind="instance", source=14, symbol=REQUEST)],
        )

    facts = [
        *_builder_chain(logged_only),
        _debug_log(logged_only),
        *_builder_chain(logged_then_sent),
        _debug_log(logged_then_sent),
        _call(
            logged_then_sent,
            OKHTTP_CLIENT,
            "newCall",
            4,
            receiver=99,
            result=20,
            arguments=[CallArgument(kind="instance", source=14, symbol=REQUEST)],
        ),
    ]
    workspace = _resolve_fluent(tmp_path, facts, catalog)
    logged_only_endpoints = [e for e in workspace.query("endpoints") if e["caller"] == logged_only]
    sent_endpoints = [e for e in workspace.query("endpoints") if e["caller"] == logged_then_sent]
    workspace.close()

    assert logged_only_endpoints == []
    [endpoint] = sent_endpoints
    assert (endpoint["method"], endpoint["peer"], endpoint["path"]) == (
        "GET",
        "legacy.acme.internal",
        "/legacy/exports",
    )


def test_a_void_step_past_the_terminal_never_chains_into_an_unrelated_static_call(
    tmp_path: Path,
):
    """A void, non-constructor row's own chain key is `None` (D00 §5: no
    `result` for a `void` method) — the identical bucket a static call's own
    `receiver` sits in. Without the guard, `subscribe()`'s own dead end would
    fan out into every unrelated static call sharing that bucket in this
    caller (here, an unrelated logging call), each a spurious extra
    continuation of the SAME chain. Exactly one endpoint must derive."""
    caller = "com/acme/http/Client#getOrderAndLog()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/orders/{id}")],
        ),
        _call(caller, URI_SPEC, "retrieve", 2, receiver=10, result=13),
        _call(
            caller,
            RESPONSE_SPEC,
            "bodyToMono",
            3,
            receiver=13,
            result=16,
            arguments=[CallArgument(kind="class", symbol=ORDER_VIEW)],
        ),
        # A void step chained off the post-terminal `bodyToMono` — its own
        # chain key is None.
        _call(caller, "reactor/core/publisher/Mono#", "subscribe", 4, receiver=16, result=None),
        # Two unrelated, void static calls elsewhere in this same caller —
        # `receiver` is None for both (D00 §5: null for statics), the same
        # bucket `subscribe`'s own chain key falls into. Two of them, not
        # one: without the guard, each would also look itself up by that
        # same `None` key and find the other, so the fabricated detour does
        # not merely revisit `subscribe` (whose own `receiver` is 16, not
        # None, so it is not even a member of that bucket) — it cycles
        # between the two statics forever, which is what actually makes this
        # case a *regression* test rather than one dedup alone would mask.
        _call(
            caller,
            LOGGER,
            "info",
            5,
            receiver=None,
            result=None,
            arguments=[CallArgument(kind="string", value="done")],
        ),
        _call(
            caller,
            LOGGER,
            "flush",
            6,
            receiver=None,
            result=None,
        ),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    endpoints = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert len(endpoints) == 1
    assert (endpoints[0]["method"], endpoints[0]["path"]) == ("GET", "/orders/{id}")
