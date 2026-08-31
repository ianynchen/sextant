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
from sextant.application.resolve.shapes.arguments import split_url
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
    # D02D-prep spec §1a, Task 1: every row is stamped with the id of the
    # catalog that derived it.
    assert endpoint["catalog_id"] == "spring-resttemplate"
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


# --- I2: a verb nobody could read is a NULL column, never a dropped row ----


def test_an_unreadable_verb_derives_the_row_with_a_null_method(tmp_path: Path):
    """Reviewer-proved gap (final review, I2): `exchange` states its verb in
    an argument, and a caller that passes its own `HttpMethod` parameter
    through gives the scanner nothing to read — the compiler's honest
    `unresolved`. The row was silently dropped, so a method that demonstrably
    calls something over HTTP disappeared from the answer on the strength of
    the one column nobody could fill.

    Everything else here is readable — the url, the body's own instance, the
    class-literal response — so `resolution: unresolved` can only be the
    verb's doing, and `method` NULL is where that failure is recorded. The
    same discipline the url already had (D02 §2, and CP-2's NULL path):
    unresolved is an answer, never an omission."""
    caller = "com/acme/http/Client#callWithPassedVerb()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="exchange",
                descriptor=(
                    "(Ljava/lang/String;Lorg/springframework/http/HttpMethod;"
                    "Lorg/springframework/http/HttpEntity;"
                    "Ljava/lang/Class;[Ljava/lang/Object;)"
                    "Lorg/springframework/http/ResponseEntity;"
                ),
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=12,
            arguments=[
                CallArgument(kind="string", value="/billing/passed-verb"),
                # The verb, arriving as this method's own parameter.
                CallArgument(kind="unresolved"),
                CallArgument(kind="instance", source=6, symbol=ORDER_REQUEST),
                CallArgument(kind="class", symbol=ORDER_VIEW),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["method"] is None
    assert endpoint["path"] == "/billing/passed-verb"
    assert endpoint["resolution"] == "unresolved"
    assert endpoint["direction"] == "outbound"
    # The payloads were readable and are still recorded: a NULL verb is one
    # column's answer, not a reason to discard the rest of the row.
    assert json.loads(str(endpoint["request_shape"]))["shape_id"] == ORDER_REQUEST
    assert json.loads(str(endpoint["response_shape"]))["shape_id"] == ORDER_VIEW


# --- C1 + I5: what a bare call argument projects to ------------------------
#
# A `class` literal and a constructed `instance` reach payload rooting as a
# bare symbol, because the extractor's wire projection rides on a type
# reference (D00 §5a) and a call argument carries none. Before the fix every
# one of them was described as `wire_type: object` — a shape claim about
# `String`, about `Void`, and about an array — and a literal argument was
# described as no payload at all. Both halves must now answer exactly what a
# scanned field of the same type answers.

_URL_ARGUMENT = CallArgument(kind="string", value="/billing/payload-case")
_STRING_SCALAR = {"wire_type": "string", "wire_format": "", "nullable": True}
_ORDER_VIEW_OBJECT = {
    "wire_type": "object",
    "wire_format": "",
    "nullable": True,
    "shape_id": ORDER_VIEW,
}

# (case, catalog method, the arguments after the url, request, response).
_PAYLOAD_CASES = [
    (
        "a String class literal is the string it names, never an object shape",
        "getForObject",
        [CallArgument(kind="class", symbol="java/lang/String#")],
        None,
        _STRING_SCALAR,
    ),
    (
        "a boxed primitive keeps the width the wire cares about",
        "getForObject",
        [CallArgument(kind="class", symbol="java/lang/Integer#")],
        None,
        {"wire_type": "integer", "wire_format": "int32", "nullable": True},
    ),
    (
        "a Void response is no payload, not a type nobody can expand",
        "getForObject",
        [CallArgument(kind="class", symbol="java/lang/Void#")],
        None,
        None,
    ),
    (
        "an array literal is an array of what it holds",
        "getForObject",
        [CallArgument(kind="class", symbol="java/lang/String#[]")],
        None,
        {"wire_type": "array", "wire_format": "", "nullable": True, "item": _STRING_SCALAR},
    ),
    (
        "an array of a payload type still roots the shape it holds",
        "getForObject",
        [CallArgument(kind="class", symbol=ORDER_VIEW + "[]")],
        None,
        {
            "wire_type": "array",
            "wire_format": "",
            "nullable": True,
            "item": _ORDER_VIEW_OBJECT,
        },
    ),
    (
        "a known type still resolves through the catalog's own entry",
        "getForObject",
        [CallArgument(kind="class", symbol="java/time/Instant#")],
        None,
        {"wire_type": "string", "wire_format": "date-time", "nullable": True},
    ),
    (
        "a bare String body is a string on a resolved row, never NULL",
        "postForObject",
        [
            CallArgument(kind="string", value="{}"),
            CallArgument(kind="class", symbol=ORDER_VIEW),
        ],
        # `nullable: False`, unlike the class literal above: a literal is a
        # value the call site passes, and an absent one is D00 §5's own
        # `null` kind instead.
        {"wire_type": "string", "wire_format": "", "nullable": False},
        _ORDER_VIEW_OBJECT,
    ),
]


@pytest.mark.parametrize(
    ("case", "name", "arguments", "request_shape", "response_shape"),
    _PAYLOAD_CASES,
    ids=[case[0] for case in _PAYLOAD_CASES],
)
def test_a_bare_call_argument_projects_to_what_a_scanned_field_of_that_type_would(
    tmp_path: Path,
    case: str,
    name: str,
    arguments: list,
    request_shape: dict | None,
    response_shape: dict | None,
):
    """Reviewer-proved gap (final review, C1 and I5). Every row here is a
    payload a real call site states outright, and each was answered wrongly
    before: `String.class` and `Integer.class` claimed an object shape (and
    were then reported as types nobody could expand); `Void.class` claimed a
    payload for a call that returns none; `String[].class` claimed an object
    rather than an array, losing the element entirely; and a literal body
    resolved to no payload at all, which made NULL mean two things at once
    on a `resolved` row.

    The answers come from the two places that already own them: the
    catalog's own `known_types`, which is where the serialiser's scalar
    knowledge lives (D02 §2g) and which now declares the same wire types and
    formats the extractor's projection emits, and D00 §5's argument kinds,
    which name a literal's type on their own. `Instant` is in the table to
    prove the pre-existing `known_types` path is untouched by either."""
    caller = f"com/acme/http/Client#case{abs(hash(case))}()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name=name,
                descriptor="(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=12,
            arguments=[_URL_ARGUMENT, *arguments, CallArgument(kind="unresolved")],
        ),
    ]
    catalog = _catalog()
    workspace = _resolve(tmp_path, facts, catalog)
    expanded = derive_endpoint_shapes(workspace, [catalog], capabilities=CAPABILITIES)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["resolution"] == "resolved"
    assert _descriptor(endpoint["request_shape"]) == request_shape
    assert _descriptor(endpoint["response_shape"]) == response_shape
    # The other half of C1: a type that is a scalar on the wire is never
    # rooted as a shape, so the report stops naming it as a payload type
    # nobody could expand. (`OrderView` itself has no field facts here and is
    # reported, correctly, exactly as it always was.)
    assert [name for name in expanded.unexpanded_types if str(name).startswith("java/")] == []


def _descriptor(column: object) -> dict | None:
    return None if column is None else json.loads(str(column))


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


# --- Task 6: `single_call` learns arity, channel_arg, per-row direction and
# verbless rows (D02 §2's `single_call` style, amended). No shipped catalog
# declares any of these yet — invented catalogs, exactly as the fluent
# section below invents its own (`ports/catalogs.py`'s own note that the
# invented catalogs tests construct by hand are a documented case).

PRODUCER = "com/acme/messaging/Producer#"
CONSUMER = "com/acme/messaging/Consumer#"


def _single_call_catalog(
    matches: dict,
    catalog_id: str = "invented-single-call",
    direction: str = "outbound",
    protocol: str = "kafka",
) -> Catalog:
    return Catalog(
        id=catalog_id,
        style="single_call",
        protocol=protocol,
        direction=direction,
        requires=("call_site", "string_constants"),
        matches=matches,
        source=Path(f"tests/{catalog_id}.yml"),
    )


def _send_call(caller: str, ordinal: int, arguments: list, name: str = "send") -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=PRODUCER, name=name, descriptor="()V"),
        invoke_kind="virtual",
        ordinal=ordinal,
        receiver=3,
        result=None,
        arguments=arguments,
    )


def test_two_arities_of_the_same_name_route_the_body_capture_to_their_own_position(
    tmp_path: Path,
):
    """D02 §2's `arity`: a row without it matches every overload (the
    shipped 2C catalogs' own case, unchanged), but `send(topic, payload)`
    and `send(topic, key, payload)` need telling apart, one row per arity —
    and each row's own `body_arg` must route to its own declared position.
    Before Task 6, `methods` was a dict keyed by name (`:40`), so the second
    `send` row would have silently overwritten the first: this proves both
    arities survive and each keeps its own `body_arg`."""
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [
            {"name": "send", "arity": 2, "http_method": "SEND", "channel_arg": 0, "body_arg": 1},
            {"name": "send", "arity": 3, "http_method": "SEND", "channel_arg": 0, "body_arg": 2},
        ],
    }
    caller_two = "com/acme/messaging/Producer#sendTwoArg()."
    caller_three = "com/acme/messaging/Producer#sendThreeArg()."
    facts = [
        _send_call(
            caller_two,
            0,
            [
                CallArgument(kind="string", value="orders.created"),
                CallArgument(kind="class", symbol=ORDER_VIEW),
            ],
        ),
        _send_call(
            caller_three,
            0,
            [
                CallArgument(kind="string", value="orders.updated"),
                CallArgument(kind="string", value="order-42"),
                CallArgument(kind="class", symbol=ORDER_REQUEST),
            ],
        ),
    ]
    catalog = _single_call_catalog(matches, "invented-arity")
    workspace = _resolve(tmp_path, facts, catalog)
    [two_arg] = [e for e in workspace.query("endpoints") if e["caller"] == caller_two]
    [three_arg] = [e for e in workspace.query("endpoints") if e["caller"] == caller_three]
    workspace.close()

    assert json.loads(two_arg["request_shape"])["shape_id"] == ORDER_VIEW
    assert json.loads(three_arg["request_shape"])["shape_id"] == ORDER_REQUEST


def test_channel_arg_fills_path_exactly_as_url_arg_would(tmp_path: Path):
    """D02 §2: `channel_arg` is an alias of `url_arg` for protocols whose
    identity is a destination rather than a URL — a topic name behaves
    exactly like a path template, string literal in, `path` out unchanged."""
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [{"name": "send", "http_method": "SEND", "channel_arg": 0}],
    }
    caller = "com/acme/messaging/Producer#publish()."
    facts = [_send_call(caller, 0, [CallArgument(kind="string", value="orders.created")])]
    catalog = _single_call_catalog(matches, "invented-channel-arg")
    workspace = _resolve(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "orders.created"
    assert endpoint["resolution"] == "resolved"


def test_a_channel_arg_holding_a_queue_url_keeps_the_whole_url_as_the_destination(
    tmp_path: Path,
):
    """Final review, IMPORTANT: `channel_arg` is an *alias* of `url_arg` in
    the catalog grammar, but the two are not the same READER. A queue URL is
    the canonical SQS destination — `SqsTemplate.send` takes exactly this —
    and it is a destination expression, not a URL to be parsed: routing it
    through `url_of` split it into a fabricated `peer`
    (`sqs.us-east-1.amazonaws.com`) plus a truncated `path`
    (`/123456789012/my-queue`), so the destination nobody could send to was
    the one recorded, and a peer no messaging fact ever asserted appeared
    from nowhere. Both halves of the discipline are pinned here: destination
    expressions verbatim, never evaluated, and messaging peers stay NULL."""
    queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/my-queue"
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [{"name": "send", "channel_arg": 0}],
    }
    caller = "com/acme/messaging/Producer#publishToQueue()."
    facts = [_send_call(caller, 0, [CallArgument(kind="string", value=queue_url)])]
    catalog = _single_call_catalog(matches, "invented-queue-url")
    workspace = _resolve(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == queue_url
    assert endpoint["peer"] is None
    assert endpoint["resolution"] == "resolved"


def test_a_row_declaring_both_url_arg_and_channel_arg_is_refused_at_run_start(
    tmp_path: Path,
):
    """`url_arg` and `channel_arg` name the same capture (D02 §2); a row
    declaring both is a broken catalog, not two pieces of evidence.
    `ports/catalogs.py`'s own discipline: an unchecked value does not stay
    in the file. The facts here are empty — no call site could ever reach
    this row by name — proving the check runs once at `run` start rather
    than lazily on first match."""
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [{"name": "send", "http_method": "SEND", "url_arg": 0, "channel_arg": 0}],
    }
    catalog = _single_call_catalog(matches, "invented-both-args")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()

    assert "invented-both-args.yml" in str(raised.value)


def test_an_invalid_row_level_direction_is_refused_at_run_start(tmp_path: Path):
    """A row's own `direction` override is still D00's closed Direction set
    (`inbound`/`outbound`/`both`) — a typo here is exactly the mistake
    `yaml_source.py`'s own catalog-level `_closed` check exists to catch,
    only this one is a row inside `matches`, invisible to that loader-level
    check, so `single_call` must refuse it itself, at `run` start, naming
    the file."""
    matches = {
        "owner": "com.acme.messaging.Consumer",
        "methods": [
            {
                "name": "onMessage",
                "direction": "sideways",
                "http_method": "RECEIVE",
                "channel_arg": 0,
            }
        ],
    }
    catalog = _single_call_catalog(matches, "invented-bad-direction")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()

    assert "invented-bad-direction.yml" in str(raised.value)
    assert "sideways" in str(raised.value)


def test_a_row_level_inbound_direction_overrides_the_catalogs_own_direction(
    tmp_path: Path,
):
    """D02 §2: `direction` on a row overrides the catalog's declared
    direction — Pub/Sub's `subscribe` is inbound even inside an otherwise
    outbound file. The deriving method (the call site's own `caller`) lands
    in `handler`, not `caller`, on that row: it is the consumer, not the
    caller (D01 §3's rule, applied per row's own direction)."""
    matches = {
        "owner": "com.acme.messaging.Consumer",
        "methods": [
            {
                "name": "onMessage",
                "direction": "inbound",
                "http_method": "RECEIVE",
                "channel_arg": 0,
            }
        ],
    }
    caller = "com/acme/messaging/Consumer#onMessage(Ljava/lang/String;)."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(owner=CONSUMER, name="onMessage", descriptor="()V"),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=None,
            arguments=[CallArgument(kind="string", value="orders.created")],
        )
    ]
    catalog = _single_call_catalog(matches, "invented-inbound-row", direction="outbound")
    workspace = _resolve(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["path"] == "orders.created"]
    workspace.close()

    assert endpoint["direction"] == "inbound"
    assert endpoint["handler"] == caller
    assert endpoint["caller"] is None


def test_a_verbless_row_with_a_resolved_channel_derives_a_null_method_without_penalising_resolution(
    tmp_path: Path,
):
    """D02 §2: a row declaring neither `http_method` nor `method_arg` is
    verbless by declaration — a topic has no verb. `method` is NULL, but
    `resolution` is not penalised for the missing verb (`this method calls
    something over a channel` is still true and useful on its own); two
    identical verbless resolved identities collapse to one row, deduped on
    `(protocol, direction, path)` since there is no method to distinguish
    them by."""
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [{"name": "publish", "channel_arg": 0}],
    }
    caller = "com/acme/messaging/Producer#publishTwice()."
    facts = [
        _send_call(
            caller, 0, [CallArgument(kind="string", value="orders.deleted")], name="publish"
        ),
        _send_call(
            caller, 1, [CallArgument(kind="string", value="orders.deleted")], name="publish"
        ),
    ]
    catalog = _single_call_catalog(matches, "invented-verbless")
    workspace = _resolve(tmp_path, facts, catalog)
    rows = [e for e in workspace.query("endpoints") if e["path"] == "orders.deleted"]
    workspace.close()

    assert len(rows) == 1
    assert rows[0]["method"] is None
    assert rows[0]["resolution"] == "resolved"


def test_a_verbless_row_whose_channel_is_a_parameter_derives_unresolved_and_never_dedups(
    tmp_path: Path,
):
    """The other half of the verbless rule: a channel the scanner could not
    read still derives the row — `path` NULL, `resolution: unresolved` —
    and, because SQL's `NULL = NULL` is unknown rather than true (D02 §2's
    unresolved-is-an-answer), two such calls never collapse into one; each
    is its own real 'this method calls something' fact."""
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [{"name": "publish", "channel_arg": 0}],
    }
    caller = "com/acme/messaging/Producer#publishDynamic()."
    facts = [
        _send_call(caller, 0, [CallArgument(kind="unresolved")], name="publish"),
        _send_call(caller, 1, [CallArgument(kind="unresolved")], name="publish"),
    ]
    catalog = _single_call_catalog(matches, "invented-verbless-unresolved")
    workspace = _resolve(tmp_path, facts, catalog)
    rows = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert len(rows) == 2
    assert all(row["path"] is None and row["resolution"] == "unresolved" for row in rows)


# --- Task 7: `record_arg` / `record_wrappers` (D02 §2's `single_call`,
# amended) — `send(ProducerRecord)`'s one argument names neither the topic
# nor the payload directly: both live on the record's own linked
# constructor, found by the same `<init>` one-hop `call_wrappers` already
# uses (`contracts._linked_constructor`), read at the catalog's declared
# `channel_ctor_arg`/`payload_ctor_arg` positions. Real fixture shapes
# (`com/acme/orders/messaging/EventProducers`, checkpoint-verified at BASE):
# `new ProducerRecord<>("order-audit", event)` (2-arg) and `new
# ProducerRecord<>("order-raw", key, event)` (3-arg).

PRODUCER_RECORD = "org/apache/kafka/clients/producer/ProducerRecord#"
ORDER_EVENT = "com/acme/orders/contracts/OrderEvent#"


def _record_wrappers_catalog(catalog_id: str = "invented-record-wrappers") -> Catalog:
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [{"name": "send", "record_arg": 0}],
        "record_wrappers": [
            {
                "type": "org.apache.kafka.clients.producer.ProducerRecord",
                "channel_ctor_arg": 0,
                "payload_ctor_arg": "last",
            }
        ],
    }
    return _single_call_catalog(matches, catalog_id)


def _record_ctor(caller: str, ordinal: int, receiver: int, arguments: list) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=PRODUCER_RECORD, name="<init>", descriptor="()V"),
        invoke_kind="special",
        ordinal=ordinal,
        receiver=receiver,
        result=None,
        arguments=arguments,
    )


def test_a_two_arg_producer_record_derives_the_topic_and_the_payload(tmp_path: Path):
    """D02 §2's `record_arg`: `new ProducerRecord<>("order-audit", event)`
    linked into `send(record)` resolves the topic and the payload off the
    record's own constructor, never off `send`'s own (single) argument —
    `channel_ctor_arg: 0` is the topic, `payload_ctor_arg: "last"` is the
    2-arg constructor's own last slot, the event."""
    caller = "com/acme/orders/messaging/EventProducers#publishAudit()."
    facts = [
        _record_ctor(
            caller,
            0,
            10,
            [
                CallArgument(kind="string", value="order-audit"),
                CallArgument(kind="instance", symbol=ORDER_EVENT),
            ],
        ),
        _send_call(caller, 1, [CallArgument(kind="instance", source=10, symbol=PRODUCER_RECORD)]),
    ]
    workspace = _resolve(tmp_path, facts, _record_wrappers_catalog())
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["protocol"], endpoint["direction"]) == ("kafka", "outbound")
    assert endpoint["method"] is None
    assert endpoint["path"] == "order-audit"
    assert endpoint["resolution"] == "resolved"
    assert json.loads(endpoint["request_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": ORDER_EVENT,
    }


def test_a_three_arg_producer_record_still_lands_the_payload_on_last(tmp_path: Path):
    """The 3-arg overload (`topic, key, value`) proves `payload_ctor_arg:
    "last"` is a rule about the constructor's own shape, not a fixed index —
    it holds across every `ProducerRecord` overload (design doc), landing on
    the value even though the value has moved from position 1 to position 2."""
    caller = "com/acme/orders/messaging/EventProducers#publishRaw()."
    facts = [
        _record_ctor(
            caller,
            0,
            11,
            [
                CallArgument(kind="string", value="order-raw"),
                CallArgument(kind="string", value="order-42"),
                CallArgument(kind="instance", symbol=ORDER_EVENT),
            ],
        ),
        _send_call(caller, 1, [CallArgument(kind="instance", source=11, symbol=PRODUCER_RECORD)]),
    ]
    workspace = _resolve(tmp_path, facts, _record_wrappers_catalog())
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "order-raw"
    assert endpoint["resolution"] == "resolved"
    assert json.loads(endpoint["request_shape"])["shape_id"] == ORDER_EVENT


def test_an_unlinked_record_argument_derives_unresolved_with_a_null_path(tmp_path: Path):
    """A `record_arg` the scanner could not resolve at all — a `ProducerRecord`
    built elsewhere and passed in as a parameter, `kind: unresolved` — still
    derives the row (D02 §2's unresolved-is-an-answer): there is no
    constructor to link, so neither the topic nor the payload can be read,
    and per I1 that drops the row's own `resolution`, `path` NULL."""
    caller = "com/acme/orders/messaging/EventProducers#publishDynamic()."
    facts = [_send_call(caller, 0, [CallArgument(kind="unresolved")])]
    workspace = _resolve(tmp_path, facts, _record_wrappers_catalog())
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] is None
    assert endpoint["resolution"] == "unresolved"
    assert endpoint["request_shape"] is None


def test_a_one_arg_producer_record_never_reports_the_topic_as_the_payload(tmp_path: Path):
    """Review round 1, MAJOR: a linked constructor whose only argument IS the
    channel slot (`channel_ctor_arg: 0` on a 1-arg ctor) must not also let
    `payload_ctor_arg: "last"` resolve to that same slot — doing so would
    report the topic string back as the payload (`{"wire_type": "string",
    ...}`), a confidently wrong body for a message with none. The payload
    capture fails instead, honestly (I1): `request_shape` is None and the
    row's own `resolution` drops to `unresolved`, exactly as a `body_arg`
    row's failed capture would — but `path` is untouched, because the
    channel argument itself read fine; a resolved url already survives a
    failed body capture the same way."""
    caller = "com/acme/orders/messaging/EventProducers#publishTombstone()."
    facts = [
        _record_ctor(caller, 0, 12, [CallArgument(kind="string", value="order-audit")]),
        _send_call(caller, 1, [CallArgument(kind="instance", source=12, symbol=PRODUCER_RECORD)]),
    ]
    workspace = _resolve(tmp_path, facts, _record_wrappers_catalog())
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "order-audit"
    assert endpoint["request_shape"] is None
    assert endpoint["resolution"] == "unresolved"


def test_a_record_whose_payload_slot_is_unresolved_still_carries_the_channel(tmp_path: Path):
    """Review round 1, MINOR (coverage gap the implementer's own report
    flagged): the channel resolves cleanly off the linked constructor, but
    the ctor's own payload-position argument is the compiler's `unresolved`
    (a value passed through as a parameter). Per I1 the declared payload
    capture still fails and drops the row's `resolution`, but `path` again
    survives untouched — this is the "capture found something unreadable"
    half of the guard, distinct from the MAJOR fix's "capture found the
    wrong thing" half above."""
    caller = "com/acme/orders/messaging/EventProducers#publishUnknownPayload()."
    facts = [
        _record_ctor(
            caller,
            0,
            13,
            [
                CallArgument(kind="string", value="order-audit"),
                CallArgument(kind="unresolved"),
            ],
        ),
        _send_call(caller, 1, [CallArgument(kind="instance", source=13, symbol=PRODUCER_RECORD)]),
    ]
    workspace = _resolve(tmp_path, facts, _record_wrappers_catalog())
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "order-audit"
    assert endpoint["request_shape"] is None
    assert endpoint["resolution"] == "unresolved"


def test_a_row_declaring_record_arg_with_body_arg_is_refused_at_run_start(tmp_path: Path):
    """`record_arg` IS the channel+payload source (D02 §2) — a row also
    declaring `body_arg` (or `url_arg`/`channel_arg`/`response_arg`) is
    contradictory evidence, not a richer row, and is refused before any call
    site is matched, the same `_validate_methods` discipline as the
    `url_arg`+`channel_arg` conflict."""
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [{"name": "send", "record_arg": 0, "body_arg": 1}],
    }
    catalog = _single_call_catalog(matches, "invented-record-body-conflict")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()

    assert "invented-record-body-conflict.yml" in str(raised.value)


@pytest.mark.parametrize(
    "wrapper",
    [
        {"channel_ctor_arg": 0, "payload_ctor_arg": "last"},  # missing type
        {"type": "org.apache.kafka.clients.producer.ProducerRecord", "payload_ctor_arg": "last"},
        {
            "type": "org.apache.kafka.clients.producer.ProducerRecord",
            "channel_ctor_arg": "0",  # not an int
            "payload_ctor_arg": "last",
        },
        {
            "type": "org.apache.kafka.clients.producer.ProducerRecord",
            "channel_ctor_arg": 0,
            "payload_ctor_arg": "middle",  # neither an int nor "last"
        },
    ],
)
def test_a_malformed_record_wrappers_entry_is_refused_at_run_start(tmp_path: Path, wrapper: dict):
    """The `record_wrappers` block shape (`{type, channel_ctor_arg: int,
    payload_ctor_arg: int|"last"}`) is checked once, at `run` start, exactly
    as a broken `methods` row is — a missing field, a non-int
    `channel_ctor_arg`, or a `payload_ctor_arg` that is neither an int nor
    the literal `"last"` is a broken catalog, never a silent no-op at
    resolve time."""
    matches = {
        "owner": "com.acme.messaging.Producer",
        "methods": [{"name": "send", "record_arg": 0}],
        "record_wrappers": [wrapper],
    }
    catalog = _single_call_catalog(matches, "invented-bad-record-wrapper")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()

    assert "invented-bad-record-wrapper.yml" in str(raised.value)


# --- Task 7 (2E-prep): `channel_via` — the linked-call follow (D02 §2h,
# amended). An instance argument's own channel is not the literal captured
# at its position but read off the call that PRODUCED it —
# `session.createProducer(session.createQueue("raw-audit"))` reads the topic
# off `createQueue`'s own argument, never `createProducer`'s. Real fixture
# shapes (`com/acme/orders/messaging/raw/RawJmsBridge`,
# `RawKafkaConsumers`, checkpoint-verified at BASE): `session.createQueue
# ("raw-audit")` (`(String)Queue`, `invokeinterface`) and
# `KafkaConsumer#subscribe(List.of("raw-t1", "raw-t2"))`
# (`List.of(Object,Object)`, `invokestatic`). The checkpoint's own probe
# against the real scanner (not assumed): the linked call's return value
# reaches its consumer as the compiler's `unresolved` kind, never
# `instance` — only a `NEW` names a concrete type, and `createQueue`/
# `List.of` are a method result, not a constructor — but it still carries
# `source`, which is all `linked_channels` ever reads.

SESSION = "jakarta/jms/Session#"
JAVA_LIST = "java/util/List#"
KAFKA_CONSUMER = "org/apache/kafka/clients/consumer/KafkaConsumer#"


def _channel_via_catalog(matches: dict, catalog_id: str, protocol: str) -> Catalog:
    return _single_call_catalog(matches, catalog_id, protocol=protocol)


def _create_queue_form(arg: int | str = 0) -> dict:
    return {"owner": "jakarta.jms.Session", "method": "createQueue", "arg": arg}


def _list_of_form(arg: int | str = "all_strings") -> dict:
    return {"owner": "java.util.List", "method": "of", "arg": arg}


def _create_queue_call(caller: str, ordinal: int, result: int, topic: str) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(
            owner=SESSION, name="createQueue", descriptor="(Ljava/lang/String;)Ljakarta/jms/Queue;"
        ),
        invoke_kind="interface",
        ordinal=ordinal,
        receiver=5,
        result=result,
        arguments=[CallArgument(kind="string", value=topic)],
    )


def _create_producer_call(caller: str, ordinal: int, source: int | None) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(
            owner=SESSION,
            name="createProducer",
            descriptor="(Ljakarta/jms/Destination;)Ljakarta/jms/MessageProducer;",
        ),
        invoke_kind="interface",
        ordinal=ordinal,
        receiver=3,
        result=8,
        arguments=[CallArgument(kind="unresolved", source=source)],
    )


def _list_of_call(caller: str, ordinal: int, result: int, values: list) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(
            owner=JAVA_LIST,
            name="of",
            descriptor="(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/List;",
        ),
        invoke_kind="static",
        ordinal=ordinal,
        receiver=None,
        result=result,
        arguments=values,
    )


def _subscribe_call(caller: str, ordinal: int, source: int | None) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(
            owner=KAFKA_CONSUMER, name="subscribe", descriptor="(Ljava/util/Collection;)V"
        ),
        invoke_kind="virtual",
        ordinal=ordinal,
        receiver=3,
        result=None,
        arguments=[CallArgument(kind="unresolved", source=source)],
    )


_CREATE_PRODUCER_MATCHES = {
    "owner": "jakarta.jms.Session",
    "methods": [
        {"name": "createProducer", "channel_arg": 0, "channel_via": _create_queue_form()},
    ],
}

_SUBSCRIBE_LIST_MATCHES = {
    "owner": "org.apache.kafka.clients.consumer.KafkaConsumer",
    "methods": [
        {"name": "subscribe", "channel_arg": 0, "channel_via": _list_of_form()},
    ],
}


def test_a_linked_createqueue_call_derives_the_topic_off_its_own_argument(tmp_path: Path):
    """`createProducer(instance -> createQueue("raw-audit"))`: `arg: 0` reads
    `createQueue`'s own single argument, never `createProducer`'s (which the
    scanner never resolved beyond `unresolved` + `source` in the first
    place) — one row, `path` the topic, `resolution: resolved`, `peer`
    always None (a destination is opaque, D02 §3)."""
    caller = "com/acme/orders/messaging/raw/RawJmsBridge#createAuditProducer()."
    facts = [
        _create_queue_call(caller, 0, 7, "raw-audit"),
        _create_producer_call(caller, 1, 7),
    ]
    catalog = _channel_via_catalog(
        _CREATE_PRODUCER_MATCHES, "invented-channel-via-createqueue", "jms"
    )
    workspace = _resolve(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["protocol"], endpoint["direction"]) == ("jms", "outbound")
    assert endpoint["peer"] is None
    assert endpoint["path"] == "raw-audit"
    assert endpoint["resolution"] == "resolved"


def test_a_channel_via_declaring_row_still_resolves_a_literal_argument_first(tmp_path: Path):
    """Fix round 1 ruling: `single_call`'s own `channel_via` branch is now
    the SAME literal-first, linked-call-fallback LADDER `fluent`/
    `interface_implementation` already read a destination through, not an
    either/or that always follows the link once `channel_via` is declared.
    `createProducer`'s own arg0 here is a plain string literal — no
    `createQueue` call anywhere in this caller for it to link to — so the
    ladder's first rung (`channel_of`, the SAME reader the non-`channel_via`
    branch uses) answers directly, `channel_via`'s own linked-call form
    never even tried. Fixture-neutral for every catalog shipped so far
    (`jakarta-jms.yml`/`kafka-consumer.yml`'s real `channel_arg` positions
    are never themselves literals — verified live, every frozen pipeline
    row unchanged), but the ladder's own first rung has to exist and be
    provably reachable on its own."""
    caller = "com/acme/orders/messaging/raw/RawJmsBridge#createLiteralProducer()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=SESSION,
                name="createProducer",
                descriptor="(Ljakarta/jms/Destination;)Ljakarta/jms/MessageProducer;",
            ),
            invoke_kind="interface",
            ordinal=0,
            receiver=3,
            result=8,
            arguments=[CallArgument(kind="string", value="raw-literal")],
        ),
    ]
    catalog = _channel_via_catalog(
        _CREATE_PRODUCER_MATCHES, "invented-channel-via-literal-first", "jms"
    )
    workspace = _resolve(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "raw-literal"
    assert endpoint["peer"] is None
    assert endpoint["resolution"] == "resolved"


def test_all_strings_derives_one_row_per_element_of_a_linked_list_of_call(tmp_path: Path):
    """`subscribe(instance -> List.of("raw-t1", "raw-t2"))` with
    `arg: "all_strings"`: `List.of` with <=2 elements binds the FIXED-ARITY
    overload (checkpoint ruling), so both elements are their own positional
    string literals — `linked_channels` reads each as its own tuple, and the
    engine derives ONE ROW PER TUPLE (the same multi-topic precedent
    `annotation_driven._derive_replies` keeps for a listener's declared
    reply destinations)."""
    caller = "com/acme/orders/messaging/raw/RawKafkaConsumers#subscribeToTopics()."
    facts = [
        _list_of_call(
            caller,
            0,
            6,
            [
                CallArgument(kind="string", value="raw-t1"),
                CallArgument(kind="string", value="raw-t2"),
            ],
        ),
        _subscribe_call(caller, 1, 6),
    ]
    catalog = _channel_via_catalog(_SUBSCRIBE_LIST_MATCHES, "invented-channel-via-list-of", "kafka")
    workspace = _resolve(tmp_path, facts, catalog)
    endpoints = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert sorted(e["path"] for e in endpoints) == ["raw-t1", "raw-t2"]
    assert all(e["resolution"] == "resolved" for e in endpoints)
    assert all(e["peer"] is None for e in endpoints)


def test_a_partially_resolved_list_derives_its_resolved_elements_plus_one_unresolved_row(
    tmp_path: Path,
):
    """One element of the linked `List.of` call reads as a literal, the
    other as the compiler's own `unresolved` (a variable, not a constant):
    the resolved element still derives its own row, and the one that failed
    derives a SINGLE trailing `(None, None, unresolved)` row rather than
    being silently dropped — D02 §2's unresolved-is-an-answer, applied per
    element."""
    caller = "com/acme/orders/messaging/raw/RawKafkaConsumers#subscribeToPartial()."
    facts = [
        _list_of_call(
            caller,
            0,
            6,
            [CallArgument(kind="string", value="raw-t1"), CallArgument(kind="unresolved")],
        ),
        _subscribe_call(caller, 1, 6),
    ]
    catalog = _channel_via_catalog(
        _SUBSCRIBE_LIST_MATCHES, "invented-channel-via-list-partial", "kafka"
    )
    workspace = _resolve(tmp_path, facts, catalog)
    endpoints = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    rows = sorted((e["path"] or "", e["resolution"]) for e in endpoints)
    assert rows == [("", "unresolved"), ("raw-t1", "resolved")]


def test_an_unlinked_argument_derives_one_null_path_unresolved_row(tmp_path: Path):
    """The `createProducer` argument never resolved to a call at all — the
    scanner's `unresolved` kind with no `source` (a `Queue` built elsewhere
    and passed in as a parameter). There is nothing to follow, so
    `linked_channels` gives the same honest answer an unreadable url would:
    one row, `path` NULL, `resolution: unresolved` — never a dropped row."""
    caller = "com/acme/orders/messaging/raw/RawJmsBridge#createDynamicProducer()."
    facts = [_create_producer_call(caller, 0, None)]
    catalog = _channel_via_catalog(_CREATE_PRODUCER_MATCHES, "invented-channel-via-unlinked", "jms")
    workspace = _resolve(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] is None
    assert endpoint["peer"] is None
    assert endpoint["resolution"] == "unresolved"


def test_a_linked_call_matching_no_declared_form_derives_one_null_path_unresolved_row(
    tmp_path: Path,
):
    """The argument IS linked to a real call site — `Session#
    createTemporaryQueue()` — but the catalog's only declared `channel_via`
    form names `createQueue`, a different method. "Matches at most one
    form" (D02 §2h) means none of them ever reach this site, so the row
    derives exactly as an unlinked argument would: `path` NULL,
    `resolution: unresolved` — never a guess at the wrong method's own
    identity."""
    caller = "com/acme/orders/messaging/raw/RawJmsBridge#createTempProducer()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=SESSION,
                name="createTemporaryQueue",
                descriptor="()Ljakarta/jms/TemporaryQueue;",
            ),
            invoke_kind="interface",
            ordinal=0,
            receiver=5,
            result=7,
            arguments=[],
        ),
        _create_producer_call(caller, 1, 7),
    ]
    catalog = _channel_via_catalog(
        _CREATE_PRODUCER_MATCHES, "invented-channel-via-no-form-match", "jms"
    )
    workspace = _resolve(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] is None
    assert endpoint["resolution"] == "unresolved"


def test_a_row_declaring_channel_via_without_channel_arg_or_url_arg_is_refused_at_run_start(
    tmp_path: Path,
):
    """`channel_via` says HOW to read an instance already named by
    `channel_arg`/`url_arg` — it is not itself a position. A row declaring
    it alone is missing the position it describes, refused before any call
    site is matched, the same `_validate_methods` discipline as the
    `url_arg`+`channel_arg` conflict."""
    matches = {
        "owner": "jakarta.jms.Session",
        "methods": [{"name": "createProducer", "channel_via": _create_queue_form()}],
    }
    catalog = _channel_via_catalog(matches, "invented-channel-via-no-position", "jms")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()

    assert "invented-channel-via-no-position.yml" in str(raised.value)


@pytest.mark.parametrize(
    "entry",
    [
        {"method": "createQueue", "arg": 0},  # missing owner
        {"owner": "jakarta.jms.Session", "arg": 0},  # missing method
        {"owner": "jakarta.jms.Session", "method": "createQueue", "arg": "first"},  # bad arg
        "jakarta.jms.Session",  # not even a dict
    ],
)
def test_a_malformed_channel_via_entry_is_refused_at_run_start(tmp_path: Path, entry):
    """Each declared `channel_via` entry must be `{owner, method, arg:
    int|"all_strings"}` — the same shape discipline `record_wrappers`
    entries keep, checked once at `run` start rather than a crash the first
    time a call site reaches it."""
    matches = {
        "owner": "jakarta.jms.Session",
        "methods": [{"name": "createProducer", "channel_arg": 0, "channel_via": entry}],
    }
    catalog = _channel_via_catalog(matches, "invented-bad-channel-via", "jms")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()

    assert "invented-bad-channel-via.yml" in str(raised.value)


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


def test_a_later_empty_capture_overwrites_the_good_one_and_drops_the_resolution(
    tmp_path: Path,
):
    """Reviewer-proved gap (final review, I4): last-wins is what a repeated
    step is *for* (the test above), but a later step that carries nothing at
    the position it declares used to overwrite a good capture with `None` and
    leave the row reading `resolved` — the exact NULL-means-two-things
    failure D01 §3 forbids. Reading the row, the body was absent; reading
    the chain, the body was there and then lost.

    Probed here with the shape that produces it in real code: a zero-argument
    `bodyValue()` overload reached after `bodyValue(request)`. The capture
    was declared by a step this chain genuinely reached, so it is a declared
    capture that failed to read — single_call's `_capture_resolved` has said
    exactly that about a declared positional slot since ruling I1, and this
    is the same answer for a declared step capture."""
    caller = "com/acme/http/Client#reserveTwice()."
    facts = [
        _call(caller, WEBCLIENT, "post", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/v2/inventory/reserve")],
        ),
        _call(
            caller,
            URI_SPEC,
            "bodyValue",
            2,
            receiver=10,
            result=11,
            arguments=[CallArgument(kind="instance", source=8, symbol=ORDER_REQUEST)],
        ),
        # The same step name again, this time with nothing at arg0.
        _call(caller, URI_SPEC, "bodyValue", 3, receiver=11, result=12, arguments=[]),
        _call(caller, URI_SPEC, "retrieve", 4, receiver=12, result=13),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert (endpoint["method"], endpoint["path"]) == ("POST", "/v2/inventory/reserve")
    assert endpoint["request_shape"] is None
    assert endpoint["resolution"] == "unresolved"


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


@pytest.mark.parametrize(
    ("case", "captures"),
    [
        ("a misspelled position", {"url": "argX"}),
        ("a bare number, not a position", {"url": 0}),
        ("a field name where a position belongs", {"body": "request"}),
    ],
    ids=["argX", "a bare number", "a field name"],
)
def test_a_capture_that_does_not_name_a_call_site_position_is_refused(
    tmp_path: Path, case: str, captures: dict
):
    """Reviewer-proved gap (final review, I6). `url`, `body` and `response`
    address an argument by position, and anything that is not `argN`
    captured nothing at all — silently. The row still derived, with the url
    unresolved and the payload NULL, which reads exactly like a call site
    that genuinely carries neither: a catalog typo disguised as an
    observation, which is the one thing `ports/catalogs.py`'s discipline
    exists to prevent.

    Refused loudly instead, naming the file, the entry and the value. A
    capture that is well-formed but out of *range* is a different question —
    the range belongs to the matched call site, not to the catalog — and
    ruling I1 already answers it at derive time by dropping the row's
    resolution."""
    matches = {
        "roots": [
            {
                "owner": "com.acme.http.WebClient",
                "method": "get",
                "captures": {"http_method": "GET"},
            }
        ],
        "steps": [{"method": "uri", "captures": captures}],
        "terminal": ["retrieve"],
    }
    catalog = _fluent_catalog(matches, "invented-bad-capture")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    workspace.close()

    assert "invented-bad-capture.yml" in str(raised.value)
    assert "uri" in str(raised.value)
    assert str(next(iter(captures.values()))) in str(raised.value)


def test_every_shipped_catalog_still_loads_and_derives(tmp_path: Path):
    """The other half of the check above: the refusal must be a rule the
    shipped files already keep, not a rule that breaks them. Every catalog
    Sextant ships is run against a workspace with no facts at all, so what is
    being proved is loading and validation — including `_validate_steps` and
    the capture check — rather than any derivation. Every capability any
    catalog declares is granted, because a catalog gated out never reaches
    its engine and so would never be validated at all."""
    catalogs = YamlCatalogSource(CATALOGS_DIR).load()
    granted = {capability for catalog in catalogs for capability in catalog.requires}
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    skipped = derive_endpoints(workspace, catalogs, capabilities=granted)
    endpoints = workspace.query("endpoints")
    workspace.close()

    assert [catalog.id for catalog in catalogs] != []
    assert skipped == []
    assert endpoints == []


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


SELF_RETURNING = "com/acme/http/SelfBuilder#"


def test_a_self_returning_step_roots_its_own_type_and_the_walk_still_ends(
    tmp_path: Path,
):
    """The self-reference the walk and the payload rooting each have to
    survive, pinned (final review, residual 6) because nothing else covers
    it and both halves fail silently if it breaks.

    The chain: a builder step called on the very type it returns, so each
    row's own `result` feeds the next row's `receiver` between two sites of
    one type — the shape a `by_receiver` walk would loop on if a row could
    ever match itself. It ends exactly where the facts end, deriving one row.

    The payload: the captured argument is an `instance` whose declared
    supertype is generic and names the argument's own type
    (`SelfBuilder extends AbstractBuilder<SelfBuilder>`) — the D02 §2h PTR
    follow is offered a carrier and declines, because this catalog declares
    no `type_carriers` matching it. Falling through to the type's own bare
    reference is the right answer, and it is the reason the fall-through must
    not read the supertype's argument: that argument is the type itself, and
    following it would describe a payload the code never states."""
    caller = "com/acme/http/Client#selfBuilt()."
    facts = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + SELF_RETURNING,
            construct_kind="class",
            supertype=TypeRef(
                symbol="com/acme/http/AbstractBuilder#",
                wire_type="object",
                wire_format="",
                nullable=True,
                nullable_resolution="resolved",
                arguments=[
                    TypeRef(
                        symbol=SELF_RETURNING,
                        wire_type="object",
                        wire_format="",
                        nullable=True,
                        nullable_resolution="resolved",
                    )
                ],
            ),
        ),
        _call(caller, WEBCLIENT, "post", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/v2/self")],
        ),
        _call(
            caller,
            URI_SPEC,
            "bodyValue",
            2,
            receiver=10,
            result=11,
            arguments=[CallArgument(kind="instance", source=8, symbol=SELF_RETURNING)],
        ),
        _call(caller, URI_SPEC, "retrieve", 3, receiver=11, result=13),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_WEBCLIENT_MATCHES))
    endpoints = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert len(endpoints) == 1
    assert (endpoints[0]["method"], endpoints[0]["path"]) == ("POST", "/v2/self")
    assert endpoints[0]["resolution"] == "resolved"
    assert json.loads(str(endpoints[0]["request_shape"])) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": SELF_RETURNING,
    }


# --- Task 12 fix round 1 (coordinator review): okhttp's own verb steps -----


def test_okhttp_put_patch_delete_head_steps_derive_their_own_verb_not_the_roots_default(
    tmp_path: Path,
):
    """MAJOR: the root always seeds `http_method: GET` (OkHttp's own real
    default for a bare `Request.Builder`); before this fix `okhttp.yml`'s own
    `steps` matched only `url`/`get`/`post`, so a `.put(body)`/`.delete()`/
    `.head()` chain's own verb-setting call was an unmatched step (D02 §4:
    "unmatched steps pass through uncaptured") and the root's GET default
    stood uncorrected — a confidently WRONG verb derived, not an honest gap.
    Uses the real, shipped `okhttp` catalog rather than an invented
    stand-in, since the bug was in that file's own step list, not in the
    engine. `patch` is exercised alongside `put` (both capture a body
    argument the same way); `delete` and `head` both capture no body,
    proving the catalog's per-verb `captures` are correct in both shapes."""
    catalogs = YamlCatalogSource(CATALOGS_DIR).load()
    okhttp = next(c for c in catalogs if c.id == "okhttp")
    # The real owners `okhttp.yml` matches on — distinct from `BUILDER`/
    # `OKHTTP_CLIENT`/`REQUEST` above, which belong to the *invented*
    # `_OKHTTP_MATCHES` catalog's own made-up `com.acme.http` package.
    real_builder = "okhttp3/Request$Builder#"
    real_client = "okhttp3/OkHttpClient#"
    real_request = "okhttp3/Request#"

    def _builder_chain(caller: str, verb_call: str, has_body: bool) -> list:
        return [
            _call(
                caller, real_builder, "<init>", 0, receiver=2, result=None, invoke_kind="special"
            ),
            _call(
                caller,
                real_builder,
                "url",
                1,
                receiver=2,
                result=8,
                arguments=[CallArgument(kind="string", value="/orders/{id}")],
            ),
            _call(
                caller,
                real_builder,
                verb_call,
                2,
                receiver=8,
                result=11,
                arguments=[CallArgument(kind="unresolved")] if has_body else [],
            ),
            _call(caller, real_builder, "build", 3, receiver=11, result=14),
        ]

    def _newcall(caller: str) -> CallSiteFact:
        return _call(
            caller,
            real_client,
            "newCall",
            4,
            receiver=99,
            result=20,
            arguments=[CallArgument(kind="instance", source=14, symbol=real_request)],
        )

    callers = {
        "put": "com/acme/http/Client#replace().",
        "patch": "com/acme/http/Client#amend().",
        "delete": "com/acme/http/Client#remove().",
        "head": "com/acme/http/Client#probe().",
    }
    facts = [
        fact
        for verb, caller in callers.items()
        for fact in (
            *_builder_chain(caller, verb, has_body=verb in ("put", "patch")),
            _newcall(caller),
        )
    ]
    workspace = _resolve_fluent(tmp_path, facts, okhttp)
    by_caller = {e["caller"]: e for e in workspace.query("endpoints")}
    workspace.close()

    assert by_caller[callers["put"]]["method"] == "PUT"
    assert by_caller[callers["patch"]]["method"] == "PATCH"
    assert by_caller[callers["delete"]]["method"] == "DELETE"
    assert by_caller[callers["head"]]["method"] == "HEAD"


# --- Task 8 (2E-prep): `when` — the value-guarded step (D02 §2b) -----------
#
# Checkpoint-confirmed (task-6-report.md javap evidence, reviewer-reproduced):
# `KafkaHeaders.TOPIC` inlines to `LDC "kafka_topic"` at the call site, so a
# `when` guard's string-literal comparison against a real `setHeader(String,
# Object)` chain is sound. The invented catalog below stays HTTP-shaped (an
# extra `setHeader` step folded into the WebClient chain) rather than
# reaching for the real Kafka shape — `fluent`'s own `_derive` still requires
# a root-seeded `http_method` today, and shipping the real
# `spring-kafka-message.yml` catalog is a later task's job, not this one's.

_GUARDED_STEP_MATCHES = {
    "roots": [
        {"owner": "com.acme.http.WebClient", "method": "get", "captures": {"http_method": "GET"}},
    ],
    "steps": [
        {"method": "uri", "captures": {"url": "arg0"}},
        {
            "method": "setHeader",
            "when": {"arg": 0, "equals": "kafka_topic"},
            "captures": {"url": "arg1"},
        },
    ],
    "terminal": ["retrieve"],
}


def test_a_guarded_step_whose_key_matches_captures_under_the_guard(tmp_path: Path):
    """D02 §2b's plain case: the guard argument reads the declared `equals`
    literal exactly, so the step's own captures apply — a `setHeader`
    reached with `("kafka_topic", "t")` captures `url: "t"` exactly as an
    unguarded step would."""
    caller = "com/acme/http/Client#sendGuarded()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "setHeader",
            1,
            receiver=4,
            result=10,
            arguments=[
                CallArgument(kind="string", value="kafka_topic"),
                CallArgument(kind="string", value="t"),
            ],
        ),
        _call(caller, URI_SPEC, "retrieve", 2, receiver=10, result=13),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_GUARDED_STEP_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "t"
    assert endpoint["resolution"] == "resolved"


def test_a_guarded_step_whose_key_is_a_different_literal_passes_through_uncaptured(
    tmp_path: Path,
):
    """The step still matches the chain either way (D02 §2b: "the step
    matches the chain either way, pass-through when the guard doesn't
    hold") — a `setHeader` keyed `"other"` captures nothing at all, and the
    url an earlier step set stands untouched, exactly like today's
    unmatched-step pass-through."""
    caller = "com/acme/http/Client#sendMismatched()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/orders/1")],
        ),
        _call(
            caller,
            URI_SPEC,
            "setHeader",
            2,
            receiver=10,
            result=11,
            arguments=[
                CallArgument(kind="string", value="other"),
                CallArgument(kind="string", value="x"),
            ],
        ),
        _call(caller, URI_SPEC, "retrieve", 3, receiver=11, result=13),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_GUARDED_STEP_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "/orders/1"
    assert endpoint["resolution"] == "resolved"


def test_a_guarded_step_whose_key_is_unresolved_poisons_the_capture_it_declares(
    tmp_path: Path,
):
    """An unreadable guard key must never let a chain preserve an earlier
    confident answer (D02 §2b): the guard argument's own kind is the
    compiler's `unresolved` (never a string this catalog could compare), so
    every capture this step declares — here just `url` — poisons to
    unresolved, overwriting the resolved url an earlier `uri` step set, and
    dropping the row's own resolution (checkpoint ruling I1, unified in Task
    4's `_capture_resolved`)."""
    caller = "com/acme/http/Client#sendUnresolvedKey()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/orders/1")],
        ),
        _call(
            caller,
            URI_SPEC,
            "setHeader",
            2,
            receiver=10,
            result=11,
            arguments=[CallArgument(kind="unresolved"), CallArgument(kind="string", value="x")],
        ),
        _call(caller, URI_SPEC, "retrieve", 3, receiver=11, result=13),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_GUARDED_STEP_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] is None
    assert endpoint["resolution"] == "unresolved"


def test_a_later_guarded_write_supersedes_an_earlier_poison(tmp_path: Path):
    """Last-wins (D02 §4) applies across a poison too: an unresolved guard
    key poisons `url`, but a LATER `setHeader` reached with a matching,
    resolved guard key overwrites the poison exactly like any other
    repeated step's capture — the poison is not sticky once a confident
    answer follows it, and the row derives fully resolved off the later
    write."""
    caller = "com/acme/http/Client#sendUnpoisoned()."
    facts = [
        _call(caller, WEBCLIENT, "get", 0, receiver=3, result=4),
        _call(
            caller,
            URI_SPEC,
            "uri",
            1,
            receiver=4,
            result=10,
            arguments=[CallArgument(kind="string", value="/orders/1")],
        ),
        _call(
            caller,
            URI_SPEC,
            "setHeader",
            2,
            receiver=10,
            result=11,
            arguments=[CallArgument(kind="unresolved"), CallArgument(kind="string", value="x")],
        ),
        _call(
            caller,
            URI_SPEC,
            "setHeader",
            3,
            receiver=11,
            result=12,
            arguments=[
                CallArgument(kind="string", value="kafka_topic"),
                CallArgument(kind="string", value="t"),
            ],
        ),
        _call(caller, URI_SPEC, "retrieve", 4, receiver=12, result=13),
    ]
    workspace = _resolve_fluent(tmp_path, facts, _fluent_catalog(_GUARDED_STEP_MATCHES))
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "t"
    assert endpoint["resolution"] == "resolved"


@pytest.mark.parametrize(
    "when",
    [
        {"equals": "kafka_topic"},  # missing arg
        {"arg": 0},  # missing equals
        {"arg": "0", "equals": "kafka_topic"},  # arg not an int
        {"arg": 0, "equals": 7},  # equals not a str
        {"arg": 0, "equals": "kafka_topic", "extra": True},  # extra key
        "kafka_topic",  # not even a dict
    ],
)
def test_a_malformed_when_guard_is_refused_at_run_start(tmp_path: Path, when: object):
    """A `when` guard must be `{arg: int, equals: str}` exactly — anything
    else is refused before any call site is matched, the same
    `_validate_captures`/`_validate_methods` discipline every other
    catalog-shape check in this file keeps: an unchecked value does not
    stay in the file."""
    matches = {
        "roots": [
            {
                "owner": "com.acme.http.WebClient",
                "method": "get",
                "captures": {"http_method": "GET"},
            },
        ],
        "steps": [{"method": "setHeader", "when": when, "captures": {"url": "arg1"}}],
        "terminal": ["retrieve"],
    }
    catalog = _fluent_catalog(matches, "invented-bad-when")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    workspace.close()

    assert "invented-bad-when.yml" in str(raised.value)
    assert "setHeader" in str(raised.value)


def test_a_when_guard_on_a_root_is_refused_at_run_start(tmp_path: Path):
    """`when` (D02 §2b) is a STEP's own guard — a root starts the chain,
    with no prior capture a guard could ever condition. Fix round 1
    (reviewer MAJOR): the root's own list construction used to carry only
    `owner`/`method`/`captures` forward, so a `when` on a root entry was
    silently stripped before validation ever saw it — exactly the "an
    unchecked value does not stay in the file" failure mode every other
    catalog-shape check in this file refuses instead. Refused here even
    though the guard itself is otherwise well-formed: placement, not
    shape, is what is wrong."""
    matches = {
        "roots": [
            {
                "owner": "com.acme.http.WebClient",
                "method": "get",
                "when": {"arg": 0, "equals": "kafka_topic"},
                "captures": {"http_method": "GET"},
            }
        ],
        "steps": [{"method": "uri", "captures": {"url": "arg0"}}],
        "terminal": ["retrieve"],
    }
    catalog = _fluent_catalog(matches, "invented-when-on-root")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    workspace.close()

    assert "invented-when-on-root.yml" in str(raised.value)
    assert "when" in str(raised.value)
    assert "get" in str(raised.value)


# --- Task 11 precondition (2E-prep, controller plan-amendment ruling):
# verbless fluent chains — a root declaring NO `http_method` capture derives
# `method` NULL, resolution not penalised for the missing verb, mirroring
# single_call's own D02 §2 `verbless` row (a topic has no verb). The invented
# catalog below shapes its root as a static factory ("builder", never
# `<init>`) and its terminal through `terminal_via_argument`, deliberately
# mirroring `aws-sqs-sdk.yml`'s real
# `SendMessageRequest.builder()...queueUrl(...)...build()` chain — proving
# the static-root chain-key (`_chain_key`: a non-`<init>` root's own
# `result`, not its `receiver`) already carries a verbless walk end to end.

ENVELOPE = "com/acme/messaging/Envelope#"
ENVELOPE_PRODUCER = "com/acme/messaging/Producer#"

_VERBLESS_MATCHES = {
    "roots": [
        # No `http_method` in this root's own captures at all — verbless by
        # declaration, not by a read that came back empty.
        {"owner": "com.acme.messaging.Envelope", "method": "builder", "captures": {}},
    ],
    "steps": [
        {"method": "destination", "captures": {"url": "arg0"}},
    ],
    "terminal": [
        {
            "method": "build",
            "terminal_via_argument": {
                "owner": "com.acme.messaging.Producer",
                "method": "send",
            },
        }
    ],
}


def _verbless_chain(caller: str, ordinal: int, destination) -> list:
    """One full builder→destination→build→send chain, `ordinal` offsetting
    every call site so two chains in the same caller never collide on their
    own `receiver`/`result` value ids."""
    base = ordinal * 10
    return [
        _call(
            caller,
            ENVELOPE,
            "builder",
            base,
            receiver=None,
            result=base + 1,
            invoke_kind="static",
        ),
        _call(
            caller,
            ENVELOPE,
            "destination",
            base + 1,
            receiver=base + 1,
            result=base + 2,
            arguments=[destination],
        ),
        _call(caller, ENVELOPE, "build", base + 2, receiver=base + 2, result=base + 3),
        _call(
            caller,
            ENVELOPE_PRODUCER,
            "send",
            base + 3,
            receiver=999,
            result=None,
            arguments=[CallArgument(kind="instance", source=base + 3, symbol=ENVELOPE)],
        ),
    ]


def test_a_verbless_chain_derives_a_null_method_resolved_row(tmp_path: Path):
    """The plain case: the root seeds no verb at all, so `method` reads NULL
    — never a dropped row, and never penalised in `resolution`, exactly as
    single_call's own verbless row (D02 §2, amended)."""
    caller = "com/acme/messaging/Client#publishOnce()."
    facts = _verbless_chain(caller, 0, CallArgument(kind="string", value="orders.created"))
    catalog = _fluent_catalog(_VERBLESS_MATCHES, "invented-verbless-fluent")
    workspace = _resolve_fluent(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["method"] is None
    assert endpoint["path"] == "orders.created"
    assert endpoint["resolution"] == "resolved"


def test_two_identical_resolved_verbless_chains_dedup_to_one_row(tmp_path: Path):
    """Two separate chains — different callers, same wire identity — collapse
    to one row: a verbless resolved identity dedups on `(protocol,
    direction, path)` alone, there being no method to tell them apart by
    (mirroring single_call's own verbless dedup rule)."""
    first_caller = "com/acme/messaging/Client#publishFirst()."
    second_caller = "com/acme/messaging/Client#publishSecond()."
    facts = [
        *_verbless_chain(first_caller, 0, CallArgument(kind="string", value="orders.deleted")),
        *_verbless_chain(second_caller, 1, CallArgument(kind="string", value="orders.deleted")),
    ]
    catalog = _fluent_catalog(_VERBLESS_MATCHES, "invented-verbless-fluent-dedup")
    workspace = _resolve_fluent(tmp_path, facts, catalog)
    rows = [e for e in workspace.query("endpoints") if e["path"] == "orders.deleted"]
    workspace.close()

    assert len(rows) == 1
    assert rows[0]["method"] is None
    assert rows[0]["resolution"] == "resolved"


def test_a_verbless_unresolved_row_never_dedups_with_its_twin(tmp_path: Path):
    """The other half: a destination the scanner could not read still
    derives the row (`path` NULL, `resolution: unresolved`), and two such
    calls never collapse into one — SQL's `NULL = NULL` is unknown, not
    true, so `path is not None` never gates the dedup key at all here, and
    each stays its own real 'this method calls something' fact."""
    first_caller = "com/acme/messaging/Client#publishDynamicFirst()."
    second_caller = "com/acme/messaging/Client#publishDynamicSecond()."
    facts = [
        *_verbless_chain(first_caller, 0, CallArgument(kind="unresolved")),
        *_verbless_chain(second_caller, 1, CallArgument(kind="unresolved")),
    ]
    catalog = _fluent_catalog(_VERBLESS_MATCHES, "invented-verbless-fluent-unresolved")
    workspace = _resolve_fluent(tmp_path, facts, catalog)
    rows = [e for e in workspace.query("endpoints") if e["caller"] in (first_caller, second_caller)]
    workspace.close()

    assert len(rows) == 2
    assert all(row["path"] is None and row["resolution"] == "unresolved" for row in rows)
    assert all(row["method"] is None for row in rows)


# --- Task 12 precondition (2E-prep, checkpoint ruling): fluent gains a
# `channel` capture field, resolved through the SAME literal-first,
# `channel_via`-fallback ladder `single_call`/`interface_implementation`
# already use (`shapes.arguments.channel_of`/`linked_channels`) — never
# `url`'s own CP-2 peer/path split, D02 §2d's "a destination is never split
# into a peer". `google-pubsub-publisher.yml`'s real chain is the shape
# this mirrors: `Publisher.newBuilder(...)` is a static-factory root (no
# `<init>`, chain-keyed on its own `result`, Task 11's precondition already
# proved this) whose own arg0 is either a literal topic string (an overload
# that genuinely exists) or a `TopicName.of(project, topic)` linked call —
# read via `channel_via`'s own `{owner, method, arg}` ladder, exactly
# `kafka-consumer.yml`'s `subscribe` row already reads off `List.of`.

PUBLISHER = "com/acme/pubsub/Publisher#"
TOPIC_NAME = "com/acme/pubsub/TopicName#"

_PUBSUB_MATCHES = {
    "roots": [
        {
            "owner": "com.acme.pubsub.Publisher",
            "method": "newBuilder",
            "captures": {"channel": "arg0"},
            "channel_via": [{"owner": "com.acme.pubsub.TopicName", "method": "of", "arg": 1}],
        }
    ],
    "steps": [],
    # `build()` returns the concrete `Publisher` type — no erasure, no
    # `CHECKCAST` — and `publish` is called directly on that same stack
    # value (`build().publish(message)`, real `javap` verified at this
    # task's checkpoint): `build`'s own result IS `publish`'s own receiver,
    # a plain receiver-linked continuation, never the OkHttp/SQS
    # `terminal_via_argument` "built value passed as a DIFFERENT call's
    # argument" shape. `publish` alone is the terminal; `build` needs no
    # entry, D02 §4's "unmatched steps pass through uncaptured".
    "terminal": ["publish"],
}


def _newbuilder_call(
    caller: str, ordinal: int, result: int, channel_arg: CallArgument
) -> CallSiteFact:
    return _call(
        caller,
        PUBLISHER,
        "newBuilder",
        ordinal,
        receiver=None,
        result=result,
        arguments=[channel_arg],
        invoke_kind="static",
    )


def _build_and_publish_calls(caller: str, ordinal: int, builder_result: int) -> list:
    build_result = builder_result + 1
    return [
        _call(caller, PUBLISHER, "build", ordinal, receiver=builder_result, result=build_result),
        _call(
            caller,
            PUBLISHER,
            "publish",
            ordinal + 1,
            receiver=build_result,
            result=None,
            arguments=[CallArgument(kind="unresolved")],
        ),
    ]


def test_a_fluent_root_channel_resolves_the_literal_argument_first(tmp_path: Path):
    """The ladder tries the literal read FIRST — `Publisher.newBuilder`
    genuinely has a same-arity `String` overload alongside the `TopicName`
    one — so a plain string argument resolves without ever consulting
    `channel_via`, exactly `interface_implementation`'s own ladder order."""
    caller = "com/acme/pubsub/Client#publishDirect()."
    facts = [
        _newbuilder_call(
            caller, 0, 1, CallArgument(kind="string", value="projects/p/topics/orders")
        ),
        *_build_and_publish_calls(caller, 1, 1),
    ]
    catalog = _fluent_catalog(_PUBSUB_MATCHES, "invented-pubsub-literal")
    workspace = _resolve_fluent(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["method"] is None
    assert endpoint["path"] == "projects/p/topics/orders"
    assert endpoint["peer"] is None
    assert endpoint["resolution"] == "resolved"


def test_a_fluent_root_channel_falls_back_to_the_linked_topicname_call(tmp_path: Path):
    """The literal read fails (`newBuilder`'s own arg0 is the compiler's
    `unresolved`, carrying only `source`) — the ladder falls back to the
    declared `channel_via` form, following `source` to `TopicName.of`'s own
    call site and reading its `arg: 1` (the topic id, project at arg 0),
    exactly the checkpoint's real-fixture shape."""
    caller = "com/acme/pubsub/Client#publishViaTopicName()."
    facts = [
        _call(
            caller,
            TOPIC_NAME,
            "of",
            0,
            receiver=None,
            result=5,
            arguments=[
                CallArgument(kind="string", value="p"),
                CallArgument(kind="string", value="orders"),
            ],
            invoke_kind="static",
        ),
        _newbuilder_call(caller, 1, 1, CallArgument(kind="unresolved", source=5)),
        *_build_and_publish_calls(caller, 2, 1),
    ]
    catalog = _fluent_catalog(_PUBSUB_MATCHES, "invented-pubsub-channel-via")
    workspace = _resolve_fluent(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] == "orders"
    assert endpoint["peer"] is None
    assert endpoint["resolution"] == "resolved"


def test_a_fluent_root_channel_neither_literal_nor_linked_derives_unresolved(tmp_path: Path):
    """Neither the literal nor the linked-call follow reaches an answer (a
    field-held `TopicName` passed straight in, `source: None`) — the row
    still derives, `path` NULL, `resolution: unresolved`, D02 §2's
    unresolved-is-an-answer, never a dropped row."""
    caller = "com/acme/pubsub/Client#publishDynamic()."
    facts = [
        _newbuilder_call(caller, 0, 1, CallArgument(kind="unresolved")),
        *_build_and_publish_calls(caller, 1, 1),
    ]
    catalog = _fluent_catalog(_PUBSUB_MATCHES, "invented-pubsub-unresolved")
    workspace = _resolve_fluent(tmp_path, facts, catalog)
    [endpoint] = [e for e in workspace.query("endpoints") if e["caller"] == caller]
    workspace.close()

    assert endpoint["path"] is None
    assert endpoint["peer"] is None
    assert endpoint["resolution"] == "unresolved"


def test_a_fluent_root_declaring_channel_via_without_a_channel_capture_is_refused_at_run_start(
    tmp_path: Path,
):
    """`channel_via` says HOW to read an instance already named by
    `channel` — it is not itself a position, mirroring `single_call`'s own
    `channel_via`-without-`channel_arg` refusal (D02 §2h)."""
    matches = {
        "roots": [
            {
                "owner": "com.acme.pubsub.Publisher",
                "method": "newBuilder",
                "captures": {},
                "channel_via": [{"owner": "com.acme.pubsub.TopicName", "method": "of", "arg": 1}],
            }
        ],
        "steps": [],
        "terminal": [{"method": "build", "terminal_via_argument": True}],
    }
    catalog = _fluent_catalog(matches, "invented-pubsub-channel-via-no-position")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    workspace.close()

    assert "invented-pubsub-channel-via-no-position.yml" in str(raised.value)


def test_a_malformed_channel_via_entry_on_a_fluent_root_is_refused_at_run_start(tmp_path: Path):
    """Each declared `channel_via` entry must be `{owner, method, arg:
    int|"all_strings"}` — the same shape discipline
    `single_call`/`interface_implementation` already keep, checked once at
    `run` start rather than a crash the first time a call site reaches it."""
    matches = {
        "roots": [
            {
                "owner": "com.acme.pubsub.Publisher",
                "method": "newBuilder",
                "captures": {"channel": "arg0"},
                "channel_via": [{"method": "of", "arg": 1}],  # missing owner
            }
        ],
        "steps": [],
        "terminal": [{"method": "build", "terminal_via_argument": True}],
    }
    catalog = _fluent_catalog(matches, "invented-pubsub-bad-channel-via")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    workspace.close()

    assert "invented-pubsub-bad-channel-via.yml" in str(raised.value)


def test_a_url_and_a_channel_capture_on_the_same_entry_is_refused_at_run_start(
    tmp_path: Path,
):
    """The plain case (fix round 1, closing MINOR-6's untested per-entry
    refusal): one root declaring both `url` and `channel` is refused —
    `_derive` only ever reads one of the two."""
    matches = {
        "roots": [
            {
                "owner": "com.acme.pubsub.Publisher",
                "method": "newBuilder",
                "captures": {"url": "arg0", "channel": "arg0"},
            }
        ],
        "steps": [],
        "terminal": ["build"],
    }
    catalog = _fluent_catalog(matches, "invented-url-and-channel-same-entry")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    workspace.close()

    assert "invented-url-and-channel-same-entry.yml" in str(raised.value)


def test_a_url_on_one_step_and_a_channel_on_a_different_step_is_refused_at_run_start(
    tmp_path: Path,
):
    """The mutation-proven case (fix round 1, MAJOR): `url` declared on ONE
    step and `channel` declared on a DIFFERENT step, in the same chain,
    used to load with no error at all — a per-entry-only check never saw
    the two together, and `_derive` silently discarded whichever one folded
    in first (a real okhttp-shaped probe: resolved became unresolved with
    no diagnostic). Refused now: the check runs over the UNION of every
    root's and every step's own captures, not one entry at a time."""
    matches = {
        "roots": [
            {"owner": "com.acme.http.WebClient", "method": "get", "captures": {}},
        ],
        "steps": [
            {"method": "uri", "captures": {"url": "arg0"}},
            {"method": "topic", "captures": {"channel": "arg0"}},
        ],
        "terminal": ["retrieve"],
    }
    catalog = _fluent_catalog(matches, "invented-url-and-channel-different-steps")
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [catalog], capabilities=FLUENT_CAPABILITIES)
    workspace.close()

    assert "invented-url-and-channel-different-steps.yml" in str(raised.value)
