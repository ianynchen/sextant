import json
from pathlib import Path

import duckdb

from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    ConfigEntryFact,
    Document,
    FieldWriteFact,
    MethodReturnFact,
    ModuleFact,
    SymbolFact,
)
from sextant.domain.redaction import REDACTED, RedactionRules, Redactor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace


def _fixture_facts(root: Path) -> None:
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/A.java",
        module_id="com.acme:orders",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    symbol = SymbolFact(
        document_id="doc_1", symbol="s maven p 1 com/acme/A#", construct_kind=ConstructKind.CLASS
    )
    write_fact_file(root / "com" / "acme" / "A.jsonl", document, [symbol])


def _loaded_workspace(tmp_path: Path) -> DuckDbWorkspace:
    _fixture_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def _endpoint_facts(root: Path) -> None:
    """A minimal RestController with one GetMapping — enough for
    derive_endpoints to produce a single inbound endpoint row (mirrors the
    shape tests/application/test_endpoints.py's `_controller_facts` builds)."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/orders/OrderController.java",
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
    controller = "com/acme/orders/OrderController#"
    list_ = "com/acme/orders/OrderController#list(sig_08c5be17)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=list_,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RestController#",
                args={},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=controller,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RequestMapping#",
                args={"value": ["/v1/orders"]},
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=list_,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={},
            ),
        ),
    ]
    write_fact_file(root / "OrderController.jsonl", document, facts)


def _workspace_with_an_endpoint(tmp_path: Path) -> DuckDbWorkspace:
    _endpoint_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    spring = next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-web")
    derive_endpoints(workspace, [spring], capabilities={"annotation_args", "type_annotations"})
    return workspace


def _call_site_facts(root: Path) -> None:
    """One call_site fact with a null receiver and result — the shape a
    static call (or, post-6b, a parameter-rooted receiver such as every
    super() call) actually emits — and two arguments, to exercise the
    view's ::INTEGER casts over JSON null and the JSON round trip of
    `arguments` in the same row."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/orders/OrderController.java",
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
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(
            owner="org/springframework/web/client/RestTemplate#",
            name="postForObject",
            descriptor="(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;",
        ),
        invoke_kind="static",
        ordinal=0,
        arguments=[
            CallArgument(kind="string", value="/billing/invoices"),
            CallArgument(kind="unresolved", source=7),
        ],
    )
    write_fact_file(root / "OrderController.jsonl", document, [call_site])


def _config_entry_facts(root: Path) -> None:
    """Two config entries under one document: one a built-in key pattern names
    and one nothing does, so the fact exit can be shown to discriminate rather
    than blank a field."""
    document = Document(
        document_id="doc_config",
        relative_path="application.yml",
        module_id="com.acme:orders-service",
        language="yaml",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="sextant-config-reader",
        content_hash="sha256:d",
        origin_entry="src/main/resources",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )
    write_fact_file(
        root / "application.jsonl",
        document,
        [
            ConfigEntryFact(
                document_id="doc_config",
                key_raw="orders.db.password",
                key_path="orders.db.password",
                value="hunter2",
            ),
            ConfigEntryFact(
                document_id="doc_config",
                key_raw="soap.billing.uri",
                key_path="soap.billing.uri",
                value="http://billing.internal.example.com/ws",
            ),
        ],
    )


def _workspace_with_a_call_site(tmp_path: Path) -> DuckDbWorkspace:
    _call_site_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def _topic_annotation_facts(root: Path, args: dict) -> None:
    """A synthetic messaging annotation on a single method — no type-level
    gate, deliberately not Spring — so `path_from`/`all_methods` can be
    exercised directly against `derive_endpoints.sql` without the mapping
    catalog's other machinery (mirrors test_endpoints.py's invented-listener
    fixtures, trimmed to what Task 3's NULL-verb/multi-valued-path tests
    need)."""
    document = Document(
        document_id="doc_1",
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
    listener = "com/acme/notify/OrderListener#"
    handle = "com/acme/notify/OrderListener#onOrderCreated(sig_3d92af60)."
    facts = [
        SymbolFact(document_id="doc_1", symbol=listener, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handle,
            construct_kind=ConstructKind.METHOD,
            enclosing=listener,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(
                annotation="com/acme/messaging/annotation/OnMessage#",
                args=args,
            ),
        ),
    ]
    write_fact_file(root / "OrderListener.jsonl", document, facts)


# Shared across the derivation, unaffected by which path attribute is used —
# no annotation in these fixtures carries $prefix_annotation, so `prefixes`
# always resolves empty and $prefix_from/$peer_from's exact contents do not
# matter.
_TOPIC_ENDPOINT_KWARGS = {
    "protocol": "kafka",
    "direction": "inbound",
    "type_annotation": None,
    "prefix_annotation": ["com/acme/messaging/annotation/Topic#"],
    # F2 §3.5's relationship conjunct. `prefix` is the default the engine binds
    # for a catalog that declares nothing, and these rows compose a class-level
    # prefix with each method's — so `prefix` is what keeps them describing what
    # they described before the conjunct existed.
    "class_level": "prefix",
    "mapping_annotations": [{"fqn": "com/acme/messaging/annotation/OnMessage#", "methods": None}],
    "prefix_from": [],
    "peer_from": [],
    "method_from": "method",
    # Task 5: no catalog in this file declares media attributes, so both alias
    # lists are empty — the "every non-HTTP catalog derives NULL" default.
    "consumes_from": [],
    "produces_from": [],
    # Task 6: no fixture in this file composes an annotation, so the
    # effective-annotations pre-pass always resolves to nothing here.
    "synthetic_annotations": [],
    # 2H Task 2: the two naming forms, declared at their INERT values — no
    # catalog in this file names a fallback or a qualifier, which is the
    # shape every catalog written before those forms has. Present rather
    # than omitted because a bound parameter has no default; that they are
    # here at all is what keeps the assertions below pinning the ORIGINAL
    # composition (`prefix || suffix`) rather than a new one.
    "path_fallback": None,
    # The 2026-09-06 vocabulary pass's two query-side words, at their inert
    # values for the same reason: no catalog in this file names a sibling
    # source or a fallback that strips anything, so the composition every
    # assertion below pins is the one it always was. The per-annotation
    # `path_fallback` pair rides inside `mapping_annotations` above and is
    # absent there for the same reason.
    "path_from_siblings": [],
    "path_fallback_prefixes": [],
    "qualifier_from": [],
    "qualifier_separator": None,
    # 2I Task 2: the two QName forms, at their inert values for the same
    # reason — no catalog in this file composes a bracketed scope or defaults
    # one from a package, so the composition every assertion below pins stays
    # the one it always was.
    "qualifier_format": None,
    "namespace_template": None,
    # 2I Task 2's class-gate member rule, inert too: no catalog in this file
    # derives an unannotated declaration, so every row below still comes from
    # an annotation the fixture spells out.
    "members": None,
    # The prefix seam, at its inert value too: no catalog in this file
    # composes a segmented address, so the seam stays the bare concatenation
    # every assertion below already pins.
    "path_separator": None,
    # 2O Task 7's constant prefix, inert for the same reason and refused
    # without the separator above in any case: no catalog in this file is
    # served under a framework-fixed base path.
    "path_prefix": None,
    # 2I Task 5's construct gate, inert as well: no catalog in this file
    # confines itself to one construct kind, so every declaration the fixture
    # annotates still derives regardless of what encloses it.
    "declared_on": None,
    # 2I Task 5's SEI fence, inert as well: no catalog in this file is an
    # outbound interface-gated one, so the fence's own `$direction`/
    # `$declared_on` test never reaches this list.
    "locally_implemented": [],
    # 2O Task 2's canonical-address gate, inert too: every catalog in this
    # file addresses a broker TOPIC, which is a name and not a URL, so the
    # composed address is recorded exactly as the annotations spell it — the
    # `path_separator` reasoning one word along.
    "canonical_path": False,
    # 2O Task 10's direction resolution (D02 §2c), inert too: no catalog in
    # this file declares one, and a broker listener's direction is a property
    # of the annotation rather than of what else the module contains. With
    # `flip_direction` NULL and both lists empty the flip predicate is false
    # for every row here, which is what keeps every assertion below pinning
    # the direction the catalog declared.
    "flip_direction": None,
    "flip_owners": [],
    "flip_handlers": [],
    "flip_canonical_path": False,
}


def test_a_multi_valued_path_attribute_derives_one_row_per_value(tmp_path: Path):
    """D02D Task 3: a list-valued path attribute (a Kafka listener's
    `topics = {"order-events", "order-audit"}`) must derive one endpoint row
    per element. Before the fix, `declared.path` took only the first element
    (`list_extract(..., 1)` on the raw value), so a two-topic listener
    silently lost the second topic."""
    _topic_annotation_facts(tmp_path / "facts", {"topics": ["order-events", "order-audit"]})
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    workspace.derive(
        "endpoints",
        **_TOPIC_ENDPOINT_KWARGS,
        path_from=["topics"],
        all_methods=[],
        catalog_id="cat-a",
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [
        (None, "order-audit"),
        (None, "order-events"),
    ]


def test_an_empty_all_methods_derives_one_null_method_row(tmp_path: Path):
    """D02D Task 3: `all_methods=[]` (a mapping annotation that presets no
    method, on a catalog with no per-call method attribute) must derive
    exactly one row with `method` NULL, not zero. Before the fix,
    `UNNEST(d.methods)` over the empty list produced no row at all — the
    method was silently dropped along with the whole endpoint."""
    _topic_annotation_facts(tmp_path / "facts", {"topic": "order-events"})
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    workspace.derive(
        "endpoints",
        **_TOPIC_ENDPOINT_KWARGS,
        path_from=["topic"],
        all_methods=[],
        catalog_id="cat-a",
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [(None, "order-events")]


def test_null_method_rows_dedup_and_merge_on_the_same_identity(tmp_path: Path):
    """D02D Task 3's core invariant: a NULL-verb wire identity must dedup and
    merge exactly like every HTTP identity does. Plain SQL equality treats
    `NULL = NULL` as unknown, so before the fix: re-deriving the same
    NULL-method inbound row twice would double it, deriving the same
    NULL-method outbound row twice via `call_endpoints` would double it too,
    and `merge_endpoints.sql`'s join from outbound back to inbound would
    never find its NULL-method twin to fold into `both`."""
    _topic_annotation_facts(tmp_path / "facts", {"topic": "order-events"})
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    # Derived twice — D02 §5's "two catalogs may both match" case, or simply
    # a second resolve — must still leave one inbound row.
    for _ in range(2):
        workspace.derive(
            "endpoints",
            **_TOPIC_ENDPOINT_KWARGS,
            path_from=["topic"],
            all_methods=[],
            catalog_id="cat-in",
        )

    outbound_row = {
        "protocol": "kafka",
        "direction": "outbound",
        "method": None,
        "path": "order-events",
        "handler": None,
        "caller": "com/acme/notify/OrderPublisher#publish(sig_1a2b3c4d).",
        "peer": None,
        "handler_signature": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "request_shape": None,
        "response_shape": None,
        "catalog_id": "cat-out",
    }
    # Same discipline on the call-site side: two separate derivations of the
    # same identity must still leave one outbound row.
    for _ in range(2):
        workspace.derive("call_endpoints", rows=[outbound_row])

    workspace.derive("endpoints_merge")
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["direction"], r["method"], r["path"]) for r in rows] == [
        ("both", None, "order-events"),
    ]


def test_endpoints_carry_the_catalog_id_that_derived_them(tmp_path: Path):
    """2E-prep spec §1a, Task 1: every endpoints row is stamped with the id
    of the catalog that derived it — an inbound row via `derive("endpoints",
    catalog_id=...)`, an outbound row via `derive("call_endpoints",
    rows=[{..., "catalog_id": ...}])`."""
    _topic_annotation_facts(tmp_path / "facts", {"topic": "order-events"})
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    workspace.derive(
        "endpoints",
        **_TOPIC_ENDPOINT_KWARGS,
        path_from=["topic"],
        all_methods=[],
        catalog_id="cat-a",
    )
    outbound_row = {
        "protocol": "kafka",
        "direction": "outbound",
        "method": None,
        "path": "order-audit",
        "handler": None,
        "caller": "com/acme/notify/OrderPublisher#publish(sig_1a2b3c4d).",
        "peer": None,
        "handler_signature": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "request_shape": None,
        "response_shape": None,
        "catalog_id": "cat-b",
    }
    workspace.derive("call_endpoints", rows=[outbound_row])
    rows = workspace.query("endpoints")
    workspace.close()

    assert {r["path"]: r["catalog_id"] for r in rows} == {
        "order-events": "cat-a",
        "order-audit": "cat-b",
    }


def test_merge_keeps_the_inbound_rows_catalog_id(tmp_path: Path):
    """2E-prep spec §1a: `merge_endpoints.sql` UPDATEs the inbound row in
    place and only DELETEs the outbound one, so a `both` row keeps the
    INBOUND side's `catalog_id` even though the outbound side was derived by
    a different catalog."""
    _topic_annotation_facts(tmp_path / "facts", {"topic": "order-events"})
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    workspace.derive(
        "endpoints",
        **_TOPIC_ENDPOINT_KWARGS,
        path_from=["topic"],
        all_methods=[],
        catalog_id="cat-in",
    )
    outbound_row = {
        "protocol": "kafka",
        "direction": "outbound",
        "method": None,
        "path": "order-events",
        "handler": None,
        "caller": "com/acme/notify/OrderPublisher#publish(sig_1a2b3c4d).",
        "peer": None,
        "handler_signature": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "request_shape": None,
        "response_shape": None,
        "catalog_id": "cat-out",
    }
    workspace.derive("call_endpoints", rows=[outbound_row])
    workspace.derive("endpoints_merge")
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["direction"], r["catalog_id"]) for r in rows] == [("both", "cat-in")]


def test_the_endpoints_ordering_breaks_a_full_tie_on_caller(tmp_path: Path):
    """NFR-1: the `endpoints` query orders by protocol, method, path, handler
    and finally `caller`, and `caller` is the tiebreak that turns an ordering
    with ties into an ordering at all. Two outbound rows can tie on every
    earlier column — a messaging destination nobody could read leaves
    `method`/`path`/`handler` all NULL, which `sendDefault` and a `@SendTo`
    naming nothing both produce — leaving only the calling method to tell
    them apart. Inserted here in REVERSE caller order, so an ORDER BY that
    stopped before `caller` would hand back insert order and the query's
    answer would depend on which call site the resolver reached first.

    Pinned directly rather than through the whole pipeline: the resolve
    fixture's rows already reach the table caller-sorted, so the two-run
    agreement test in `test_pipeline.py` passes with or without this
    tiebreak. Mutation-checked — dropping `caller` from the ORDER BY turns
    this red."""
    _topic_annotation_facts(tmp_path / "facts", {"topic": "order-events"})
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    def _unreadable_destination(caller: str) -> dict:
        return {
            "protocol": "kafka",
            "direction": "outbound",
            "method": None,
            "path": None,
            "handler": None,
            "caller": caller,
            "peer": None,
            "handler_signature": None,
            "resolution": "unresolved",
            "evidence": "compiler",
            "request_shape": None,
            "response_shape": None,
            "catalog_id": "cat-out",
        }

    zulu = "com/acme/notify/ZuluPublisher#publish(sig_1a2b3c4d)."
    alpha = "com/acme/notify/AlphaPublisher#publish(sig_1a2b3c4d)."
    workspace.derive("call_endpoints", rows=[_unreadable_destination(zulu)])
    workspace.derive("call_endpoints", rows=[_unreadable_destination(alpha)])
    rows = workspace.query("endpoints")
    workspace.close()

    assert [r["caller"] for r in rows] == [alpha, zulu]


def test_load_facts_reports_the_row_count_when_a_fact_tree_is_ingested(tmp_path: Path):
    _fixture_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    loaded = workspace.load_facts(tmp_path / "facts")
    workspace.close()
    assert loaded == 2  # one document line, one symbol line


def test_query_returns_the_document_when_documents_are_listed(tmp_path: Path):
    _fixture_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    rows = workspace.query("documents")
    workspace.close()
    assert [row["document_id"] for row in rows] == ["doc_1"]


def test_the_shape_tables_answer_an_empty_query_rather_than_raising(tmp_path: Path):
    """Pre-declared for the same reason `endpoints` is: a scanner too weak to
    populate them must degrade visibly through skipped_catalogs, not crash."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    assert workspace.query("shapes") == []
    assert workspace.query("shape_fields") == []
    workspace.close()


def test_endpoints_carry_the_two_shape_columns(tmp_path: Path):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.derive("endpoints_reset")
    columns = workspace.query("endpoints")
    workspace.close()
    # Empty result, so assert on the declared schema rather than on rows.
    assert columns == []


def test_media_columns_round_trip_and_never_join_into_dedup_identity(tmp_path: Path):
    """Spec §4: `consumes`/`produces` are carried data, never identity — the
    dedup `NOT EXISTS` join in `derive_call_endpoints.sql` compares only wire
    identity. A first row's declared media round-trips through the table, and
    a second row sharing the same wire identity but declaring different media
    must not insert — proving the join really excludes these two columns.

    Two separate `derive` calls, not one two-row batch: `NOT EXISTS` is
    evaluated against the table as it stood before the statement began (the
    file's own documented caveat), so a single batch would never exercise the
    dedup path this test is pinning."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")

    def _row(consumes: str | None, produces: str | None) -> dict:
        return {
            "protocol": "http",
            "direction": "outbound",
            "method": "POST",
            "path": "/orders",
            "handler": None,
            "caller": "com/acme/notify/OrderPublisher#publish(sig_1a2b3c4d).",
            "peer": None,
            "handler_signature": None,
            "resolution": "resolved",
            "evidence": "compiler",
            "catalog_id": "cat-out",
            "request_shape": None,
            "response_shape": None,
            "consumes": consumes,
            "produces": produces,
        }

    workspace.derive("call_endpoints", rows=[_row('["application/json"]', None)])
    workspace.derive("call_endpoints", rows=[_row('["application/xml"]', '["application/json"]')])
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["consumes"], r["produces"]) for r in rows] == [('["application/json"]', None)]


def test_query_rejects_a_name_that_is_not_a_named_query(tmp_path: Path):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        raised = False
        try:
            workspace.query("SELECT 1")
        except KeyError:
            raised = True
        assert raised
    finally:
        workspace.close()


def test_implementations_query_lists_a_classs_declared_interfaces(tmp_path: Path):
    """`implementations` (D00 §5a's `implemented_interfaces` capability, the
    counterpart to `supertypes` above): a class implementing something is
    returned with its interfaces as a JSON list; a class implementing none
    (`Plain` below, whose `SymbolFact.interfaces` default is `[]`, not the
    `None` `supertype` defaults to) is excluded rather than returned with an
    empty list — proving the query's `json_array_length(...) > 0` guard
    handles the empty-array case `supertypes`' null guard does not have to."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/A.java",
        module_id="com.acme:orders",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    receiver = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/Receiver#",
        construct_kind=ConstructKind.CLASS,
        interfaces=["com/google/cloud/pubsub/v1/MessageReceiver#"],
    )
    plain = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/Plain#",
        construct_kind=ConstructKind.CLASS,
    )
    write_fact_file(tmp_path / "facts" / "A.jsonl", document, [receiver, plain])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    rows = workspace.query("implementations")
    workspace.close()

    assert [row["symbol"] for row in rows] == [
        "sextant-jvm maven com.acme/orders 1.0 com/acme/Receiver#"
    ]
    assert json.loads(rows[0]["interfaces"]) == ["com/google/cloud/pubsub/v1/MessageReceiver#"]


def test_call_sites_view_round_trips_every_column_including_arguments_as_json(tmp_path: Path):
    workspace = _workspace_with_a_call_site(tmp_path)
    rows = workspace.query("call_sites")
    workspace.close()
    assert len(rows) == 1
    row = rows[0]
    assert row["document_id"] == "doc_1"
    assert row["caller"] == (
        "sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create()."
    )
    assert row["owner"] == "org/springframework/web/client/RestTemplate#"
    assert row["name"] == "postForObject"
    assert row["descriptor"] == (
        "(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;"
    )
    assert row["invoke_kind"] == "static"
    assert row["ordinal"] == 0
    # A static call carries no receiver, and this fixture leaves result
    # unset too — the view's ::INTEGER cast of a JSON null must come back
    # as SQL NULL, not the string "null" or an error.
    assert row["receiver"] is None
    assert row["result"] is None
    # Capability 9.17's column, on the site that must NOT carry it: an ordinary
    # invoke's `target` already names its callee, so the extractor writes no
    # key and `->>` on the absent key must project SQL NULL rather than the
    # string "null".
    assert row["implementation"] is None
    # Every optional key of the argument grammar is dumped, null included —
    # `elements` (capability 9.15) among them, which is None on every kind but
    # `array`. Pinned exactly rather than by subset: this view is what a
    # consumer reads, and a key silently appearing or vanishing here is the
    # drift the round trip exists to catch.
    assert json.loads(row["arguments"]) == [
        {
            "kind": "string",
            "value": "/billing/invoices",
            "symbol": None,
            "source": None,
            "elements": None,
        },
        {"kind": "unresolved", "value": None, "symbol": None, "source": 7, "elements": None},
    ]


def test_the_method_returns_view_keeps_a_void_return_distinct_from_an_unread_one(
    tmp_path: Path,
):
    """D00 §5's `method_return` (capability 9.18) at the projection. The two
    answers this fact exists to keep apart must survive the round trip through
    DuckDB, because a view that flattened them would put the whole point of the
    grammar back where it was: `value` SQL-NULL is "this return hands nothing
    back", and a `{"kind": "unresolved"}` object is "it hands back something
    the pass could not name".

    Read by reopening the database rather than through `Workspace.query`
    deliberately: there is no consumer yet (`OI-15`), and registering a named
    query for one would add a surface nothing asks for. The VIEW is what §5.1
    requires to move with the schema, and this is what proves it moved
    correctly."""
    _call_site_facts(tmp_path / "facts")
    method = "sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create()."
    document = Document(
        document_id="doc_2",
        relative_path="com/acme/orders/OrderService.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:c",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    write_fact_file(
        tmp_path / "facts" / "OrderService.jsonl",
        document,
        [
            MethodReturnFact(
                document_id="doc_2",
                method=method,
                ordinal=0,
                value=CallArgument(kind="unresolved", source=13),
            ),
            MethodReturnFact(document_id="doc_2", method=method, ordinal=1, value=None),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.close()
    reopened = duckdb.connect(str(tmp_path / "ws.duckdb"))
    rows = reopened.execute("SELECT * FROM method_returns ORDER BY ordinal").fetchall()
    reopened.close()
    assert len(rows) == 2
    document_id, returned_by, ordinal, value = rows[0]
    assert (document_id, returned_by, ordinal) == ("doc_2", method, 0)
    assert json.loads(value)["source"] == 13
    # The void return. `-> 'value'` over an explicit JSON null gives DuckDB's
    # JSON scalar `null`, not SQL NULL — so a reader tells the two apart by the
    # JSON value, and the assertion is written the way a reader would have to.
    assert json.loads(rows[1][3]) is None


def test_exported_tables_include_call_sites(tmp_path: Path):
    workspace = _workspace_with_a_call_site(tmp_path)
    workspace.export_tables(tmp_path / "bundle", Redactor.from_rules())
    workspace.close()
    assert (tmp_path / "bundle" / "graph" / "call_sites.parquet").exists()


def test_every_table_and_view_in_the_schema_is_exported(tmp_path: Path):
    """The export ratchet, running the direction that catches the defect (C10).

    It used to assert a hand-written list of eleven names, which is why the
    seven it omitted — `raw_facts`, `call_edges`, `return_flows`, `roots` and
    the three views — were dropped from every bundle for four phases with the
    suite green. A list compared against a list agrees with itself; this
    compares the export against the SCHEMA, so a new `CREATE TABLE` with no
    export query fails here rather than shipping an incomplete bundle.

    There is no exclusion class. `raw_facts` travels twice — as this table and
    as the per-document `facts/*.parquet` stream — because those are two
    shapes of one thing a reader wants for two different reasons, not an
    exemption.
    """
    workspace = _workspace_with_an_endpoint(tmp_path)
    written = workspace.export_tables(tmp_path / "bundle", Redactor.from_rules())
    assert sorted(written) == workspace.schema_objects()
    for name in written:
        assert (tmp_path / "bundle" / "graph" / f"{name}.parquet").exists(), name
    workspace.close()


def test_exported_tables_read_back_equal_to_the_workspace_query(tmp_path: Path):
    workspace = _workspace_with_an_endpoint(tmp_path)
    workspace.export_tables(tmp_path / "bundle", Redactor.from_rules())
    back = duckdb.sql(
        f"SELECT * FROM read_parquet('{tmp_path / 'bundle' / 'graph' / 'endpoints.parquet'}')"
    ).fetchall()
    workspace_count = len(workspace.query("endpoints"))
    assert len(back) == workspace_count
    assert workspace_count > 0
    workspace.close()


def test_exported_tables_include_open_questions(tmp_path: Path):
    """2G Task 8: `open_questions` joins the D06 bundle the same way every
    other resolve-owned table does — Parquet beside its siblings, read back
    through the same named query the ledger's own row shape already fixes
    (2G design §6)."""
    workspace = _workspace_with_an_endpoint(tmp_path)
    workspace.derive(
        "open_questions_insert",
        rows=[
            {
                "protocol": "kafka",
                "method": None,
                "path": "order-events",
                "question": "format_conflict",
                "candidates": json.dumps(
                    [{"format": "json", "seen_in": "consumes", "why": "application/json"}]
                ),
                "evidence": "rung 2 (declared media): json from consumes (application/json)",
            }
        ],
    )
    written = workspace.export_tables(tmp_path / "bundle", Redactor.from_rules())
    workspace.close()
    assert "open_questions" in written
    back = duckdb.sql(
        f"SELECT * FROM read_parquet('{tmp_path / 'bundle' / 'graph' / 'open_questions.parquet'}')"
    ).fetchall()
    assert len(back) == 1


def _workspace_with_config_values(tmp_path: Path) -> DuckDbWorkspace:
    workspace = _workspace_with_an_endpoint(tmp_path)
    workspace.derive(
        "resolved_config_insert",
        rows=[
            {
                "key": "orders.db.password",
                "value": "hunter2",
                "source": "application.yml",
                "environment": "default",
                "unresolved_reason": None,
            },
            {
                "key": "orders.internal.dsn",
                "value": "host=db.internal;user=orders;pw=hunter2",
                "source": "application.yml",
                "environment": "default",
                "unresolved_reason": None,
            },
            {
                "key": "soap.billing.uri",
                "value": "http://billing.internal.example.com/ws",
                "source": "application.yml",
                "environment": "default",
                "unresolved_reason": None,
            },
        ],
    )
    return workspace


def _exported_config(bundle: Path) -> dict[str, object]:
    rows = duckdb.sql(
        f"SELECT key, value FROM read_parquet('{bundle / 'graph' / 'resolved_config.parquet'}')"
    ).fetchall()
    return dict(rows)


def test_the_export_masks_config_values_and_the_workspace_keeps_them_verbatim(tmp_path: Path):
    """2K design §1's live exposure, closed at the exit it leaks from: the
    bundle is written to LEAVE, so it carries `«redacted»`; the workspace is
    the analyst's own disk and keeps the real value, because resolution and
    peer substitution need it. Masking the table instead would break analysis
    to protect a boundary the table is not on.

    A repo addition (`dsn`) is masked beside a built-in (`password`), and
    `soap.billing.uri` — an address no rule names — travels verbatim, which is
    what says the redactor discriminates rather than blanks a column."""
    workspace = _workspace_with_config_values(tmp_path)
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules(RedactionRules(key_patterns=("dsn",))))
    exported = _exported_config(bundle)
    assert exported["orders.db.password"] == REDACTED
    assert exported["orders.internal.dsn"] == REDACTED
    assert exported["soap.billing.uri"] == "http://billing.internal.example.com/ws"
    in_workspace = {row["key"]: row["value"] for row in workspace.query("resolved_config")}
    assert in_workspace["orders.db.password"] == "hunter2"
    assert in_workspace["orders.internal.dsn"] == "host=db.internal;user=orders;pw=hunter2"
    workspace.close()


def test_a_module_adding_no_rules_still_exports_masked(tmp_path: Path):
    """Default-on, at the exit. The built-in set needs no `.sextant.yml`, so a
    repository that never heard of redaction still does not ship its own
    passwords — and the key nothing built in names ships as written, which is
    exactly what the `redact:` section exists to change."""
    workspace = _workspace_with_config_values(tmp_path)
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules())
    exported = _exported_config(bundle)
    assert exported["orders.db.password"] == REDACTED
    assert exported["orders.internal.dsn"] == "host=db.internal;user=orders;pw=hunter2"
    workspace.close()


def test_the_export_strips_url_userinfo_from_the_address_columns(tmp_path: Path):
    """`path` and `peer` are the two columns that can carry a whole address
    (D01 §3, 2I's unsplit-expression ruling), so they are the two that can
    carry `scheme://user:pass@host`. The host is the answer the bundle exists
    to carry and the credential in front of it is not — and a `${...}`
    expression beside it passes through whole, because an expression is a
    reference to a value, never the value."""
    workspace = _workspace_with_an_endpoint(tmp_path)
    workspace.derive(
        "call_endpoints",
        rows=[
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "GET",
                "path": "https://svc:s3cret@billing.internal/invoices",
                "handler": None,
                "caller": "com/acme/orders/BillingClient#invoices(sig_1).",
                "peer": "https://svc:s3cret@billing.internal",
                "handler_signature": None,
                "resolution": "resolved",
                "evidence": "test",
                "catalog_id": "spring-web",
                "request_shape": None,
                "response_shape": None,
                "consumes": None,
                "produces": None,
            },
            {
                "protocol": "soap",
                "direction": "outbound",
                "method": None,
                "path": "{http://orders.example.com/ws}placeOrderRequest",
                "handler": None,
                "caller": "com/acme/orders/BillingSoapClient#place(sig_2).",
                "peer": "${soap.billing.uri}",
                "handler_signature": None,
                "resolution": "resolved",
                "evidence": "test",
                "catalog_id": "spring-ws-template",
                "request_shape": None,
                "response_shape": None,
                "consumes": None,
                "produces": None,
            },
        ],
    )
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules())
    exported = dict(
        duckdb.sql(
            f"SELECT path, peer FROM read_parquet('{bundle / 'graph' / 'endpoints.parquet'}') "
            "WHERE peer IS NOT NULL"
        ).fetchall()
    )
    assert exported["https://billing.internal/invoices"] == "https://billing.internal"
    assert exported["{http://orders.example.com/ws}placeOrderRequest"] == "${soap.billing.uri}"
    workspace.close()


def test_the_export_strips_userinfo_from_a_call_arguments_json_and_keeps_the_host(
    tmp_path: Path,
):
    """The carried JSON columns (2K Task 1 review, ruled): a hardcoded
    `https://user:pass@host` literal reaches the bundle inside
    `call_sites.arguments`, and stripping its userinfo takes the secret out
    while leaving the host — which is the wire identity the linking tier
    matches services on. Key-based masking here would gut the bundle instead;
    `arguments` is not a configuration key."""
    _call_site_facts(tmp_path / "facts")
    document = Document(
        document_id="doc_2",
        relative_path="com/acme/orders/BillingClient.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:c",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    write_fact_file(
        tmp_path / "facts" / "BillingClient.jsonl",
        document,
        [
            CallSiteFact(
                document_id="doc_2",
                caller="sextant-jvm maven com.acme/orders 1.0 com/acme/BillingClient#call().",
                target=CallTarget(
                    owner="org/springframework/web/client/RestTemplate#",
                    name="getForObject",
                    descriptor="(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;",
                ),
                invoke_kind="virtual",
                ordinal=0,
                arguments=[
                    CallArgument(kind="string", value="https://svc:s3cret@billing.internal/v1")
                ],
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules())
    exported = duckdb.sql(
        f"SELECT arguments::VARCHAR FROM read_parquet('{bundle / 'graph' / 'call_sites.parquet'}')"
    ).fetchall()
    joined = " ".join(row[0] for row in exported)
    assert "s3cret" not in joined
    assert "https://billing.internal/v1" in joined
    # The other call site's ordinary string argument is untouched, so the
    # projection masks a value rather than blanking a column.
    assert "/billing/invoices" in joined
    workspace.close()


def test_the_export_masks_an_open_questions_path_exactly_as_the_endpoint_it_asks_about(
    tmp_path: Path,
):
    """Render and export must agree about one address. The ledger is keyed on
    a wire identity and carries the same `path` an endpoint row does, so it
    masks through the same map — a question rendered against a stripped
    address and exported against a bare one names two different rows."""
    workspace = _workspace_with_an_endpoint(tmp_path)
    workspace.derive(
        "open_questions_insert",
        rows=[
            {
                "protocol": "http",
                "method": "GET",
                "path": "https://svc:s3cret@billing.internal/invoices",
                "question": "format_conflict",
                "candidates": json.dumps(
                    [{"format": "json", "seen_in": "consumes", "why": "application/json"}]
                ),
                "evidence": "rung 2 (declared media): json from consumes (application/json)",
            }
        ],
    )
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules())
    exported = duckdb.sql(
        f"SELECT path FROM read_parquet('{bundle / 'graph' / 'open_questions.parquet'}')"
    ).fetchall()
    assert exported == [("https://billing.internal/invoices",)]
    workspace.close()


def test_the_exported_facts_mask_a_config_entrys_value_and_the_workspace_keeps_it(
    tmp_path: Path,
):
    """Everything that LEAVES is masked (2K Task 1 review, ruled). A masked
    `graph/resolved_config.parquet` beside a `facts/` holding the same values
    in the clear masks nothing, so a `config_entry` payload's value passes
    `redact_value` keyed by its OWN `key_path` — the same key naming the same
    value one derivation earlier. `raw_facts` and the local fact files stay
    verbatim, which is why a document's own `redaction_set_hash` still reads
    `sha256:none`: it describes READ time, and nothing was applied then."""
    _config_entry_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    bundle = tmp_path / "bundle"
    workspace.export_facts(bundle, Redactor.from_rules())
    exported = dict(
        duckdb.sql(
            "SELECT payload ->> 'key_path', payload ->> 'value' FROM read_parquet("
            f"'{bundle / 'facts' / '*.parquet'}')"
        ).fetchall()
    )
    assert exported["orders.db.password"] == REDACTED
    assert exported["soap.billing.uri"] == "http://billing.internal.example.com/ws"
    in_workspace = {str(row["key_path"]): row["value"] for row in workspace.query("config_entries")}
    assert in_workspace["orders.db.password"] == "hunter2"
    workspace.close()


def test_the_two_new_fact_shaped_exports_mask_what_the_fact_stream_masks(tmp_path: Path):
    """C10 put `raw_facts` and the `config_entries` view into the bundle, and a
    table exported in the clear beside a masked `facts/` masks nothing — the
    same argument that put the mask on the fact stream in the first place.

    Both go through the one rule: `raw_facts` joins the SAME
    `_REDACTED_PAYLOADS` map `export_facts` joins, and `config_entries` calls
    the same `redact_value` keyed on the same `key_path`. So the three cannot
    disagree about one value. `soap.billing.uri` travels verbatim in both,
    which is what says this discriminates rather than blanks a column.
    """
    _config_entry_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules())

    from_view = dict(
        duckdb.sql(
            "SELECT key_path, value FROM read_parquet("
            f"'{bundle / 'graph' / 'config_entries.parquet'}')"
        ).fetchall()
    )
    assert from_view["orders.db.password"] == REDACTED
    assert from_view["soap.billing.uri"] == "http://billing.internal.example.com/ws"

    from_table = dict(
        duckdb.sql(
            "SELECT payload ->> 'key_path', payload ->> 'value' FROM read_parquet("
            f"'{bundle / 'graph' / 'raw_facts.parquet'}') WHERE kind = 'config_entry'"
        ).fetchall()
    )
    assert from_table["orders.db.password"] == REDACTED
    assert from_table["soap.billing.uri"] == "http://billing.internal.example.com/ws"

    in_workspace = {str(row["key_path"]): row["value"] for row in workspace.query("config_entries")}
    assert in_workspace["orders.db.password"] == "hunter2"
    workspace.close()


def test_two_exports_of_one_workspace_are_byte_identical(tmp_path: Path):
    """NFR-1 at the bundle boundary (M08). A failure here on one machine and
    not another is DuckDB's Parquet writer differing between versions —
    environment drift, not code."""
    workspace = _loaded_workspace(tmp_path)
    workspace.export_tables(tmp_path / "one", Redactor.from_rules())
    workspace.export_facts(tmp_path / "one", Redactor.from_rules())
    workspace.export_tables(tmp_path / "two", Redactor.from_rules())
    workspace.export_facts(tmp_path / "two", Redactor.from_rules())
    one = {
        p.relative_to(tmp_path / "one"): p.read_bytes()
        for p in sorted((tmp_path / "one").rglob("*.parquet"))
    }
    two = {
        p.relative_to(tmp_path / "two"): p.read_bytes()
        for p in sorted((tmp_path / "two").rglob("*.parquet"))
    }
    assert one == two and one
    workspace.close()


def test_module_dependencies_projects_the_versions_beside_the_coordinates(tmp_path: Path):
    """F1. The two travel on one `module` fact and must reach a reader on one
    row: a version with no coordinate beside it identifies nothing, and a
    coordinate whose version is in a second query could be joined against a
    different run's answer.

    A coordinate ABSENT from the map is a version this analysis could not read
    — a different answer from a dependency that has none — so the projection
    hands the map over whole and lets the reader see which keys are missing."""
    document = Document(
        document_id="doc_module",
        relative_path="module",
        module_id="com.acme:orders",
        language="module",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="detector",
        content_hash="sha256:a",
        origin_entry="com.acme/orders",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    write_fact_file(
        tmp_path / "facts" / "module.jsonl",
        document,
        [
            ModuleFact(
                document_id="doc_module",
                module_id="com.acme:orders",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
                dependency_coordinates=["com.acme:unmanaged", "org.springframework:spring-web"],
                dependency_versions={"org.springframework:spring-web": "6.1.6"},
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    [row] = workspace.query("module_dependencies")
    workspace.close()

    assert json.loads(str(row["dependency_coordinates"])) == [
        "com.acme:unmanaged",
        "org.springframework:spring-web",
    ]
    assert json.loads(str(row["dependency_versions"])) == {
        "org.springframework:spring-web": "6.1.6"
    }


def _multi_release_workspace(tmp_path: Path, *, declared_release: int | None) -> DuckDbWorkspace:
    """A jar holding one class twice — base and an overlay — plus a module fact
    declaring the target. Built here so the test states its own inputs."""
    facts = tmp_path / "facts"
    facts.mkdir(parents=True, exist_ok=True)
    for name, release in (("base", "base"), ("v21", "21"), ("v99", "99")):
        write_fact_file(
            facts / f"{name}.jsonl",
            Document(
                document_id=name,
                relative_path="com/acme/Overlaid.java",
                module_id="com.acme:m",
                language="java",
                sextant_version="0.1.0",
                fact_schema_version=5,
                scanner_id="sextant-jvm-extractor",
                class_release=release,
                class_name="com/acme/Overlaid.class",
                content_hash=f"sha256:{name}",
                origin_entry="target/classes",
                origin_tier=OriginTier.MODULE_OUTPUT,
                redaction_set_hash="sha256:none",
            ),
            [
                SymbolFact(
                    document_id=name,
                    symbol="mod com/acme/Overlaid#",
                    construct_kind="class",
                    visibility="public",
                ),
                # One fact of EVERY class-derived kind, so each filtered view
                # actually has a row to exclude. Without these the views are
                # empty whether or not the filter is applied, and the assertion
                # cannot fail — which is how four of the five went unpinned.
                AnnotationFact(
                    document_id=name,
                    target="mod com/acme/Overlaid#",
                    use=AnnotationUse(annotation="com/acme/Marker#"),
                    retention="runtime",
                ),
                CallSiteFact(
                    document_id=name,
                    caller="mod com/acme/Overlaid#go(sig_1).",
                    target=CallTarget(owner="x/C#", name="m", descriptor="()V"),
                    invoke_kind="virtual",
                    ordinal=0,
                ),
                MethodReturnFact(
                    document_id=name,
                    method="mod com/acme/Overlaid#go(sig_1).",
                    ordinal=0,
                    value=CallArgument(kind="unresolved"),
                ),
                FieldWriteFact(
                    document_id=name,
                    field="mod com/acme/Overlaid#f.",
                    from_parameter=0,
                ),
            ],
        )
    module_document = Document(
        document_id="module",
        relative_path="module",
        module_id="com.acme:m",
        language="module",
        sextant_version="0.1.0",
        fact_schema_version=5,
        scanner_id="sextant-detector",
        content_hash="sha256:module",
        origin_entry="com.acme/m",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )
    write_fact_file(
        facts / "module.jsonl",
        module_document,
        [
            ModuleFact(
                document_id="module",
                module_id="com.acme:m",
                module_kind="service",
                languages=["java"],
                source_roots=[],
                output_dirs=[],
                declared_release=declared_release,
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    return workspace


def test_only_the_selected_copy_of_an_overlaid_class_contributes_symbols(tmp_path: Path):
    """W3c — the half that makes G-62 fixed rather than renamed.

    W3 tagged every copy and dropped none, which by itself left LABELLED
    duplicates: two documents minting the SAME type symbol, and no table
    downstream has a uniqueness constraint. Measured on a jar holding one class
    at base and at release 21: 12 symbols with 6 duplicated, becoming 6 with
    none once the filter applies.

    The JVM's own rule (JEP 238): the highest release not exceeding the target
    wins. Release 99 is above a target of 21 and loses; base loses to the
    reachable 21.
    """
    workspace = _multi_release_workspace(tmp_path, declared_release=21)
    selected = {row["document_id"] for row in workspace.query("selected_documents")}
    assert selected == {"module", "v21"}
    duplicated = workspace._connection.execute(
        "SELECT count(*) FROM (SELECT symbol FROM symbols GROUP BY symbol HAVING count(*) > 1)"
    ).fetchone()
    assert duplicated is not None and duplicated[0] == 0
    workspace.close()


def test_every_copy_is_still_kept_as_a_document(tmp_path: Path):
    """Tag, do not drop, survives selection: the losing copies remain visible in
    `documents` with their release, so a reader can see WHAT was selected
    between rather than only the winner. Selection removes rows from the
    derived tables, never the record that an overlay existed."""
    workspace = _multi_release_workspace(tmp_path, declared_release=21)
    releases = {
        str(row["class_release"]) for row in workspace.query("documents") if row["class_name"]
    }
    assert releases == {"base", "21", "99"}
    workspace.close()


def test_a_module_declaring_no_release_falls_back_to_base(tmp_path: Path):
    """Spec §2.4 rule 4's order, ending where the spec ends it: the build's
    declared release, then the module's own class-file major, then BASE.

    This asserted "the highest overlay wins" until review. That was a
    deviation decided in a commit message rather than a spec amendment, which
    GUIDELINES §1.1 forbids, and it was overturned: base is what the spec
    states, and base is the copy every runtime can load.

    These fixture documents carry no `class_major`, so tier 2 finds nothing and
    the fallback is reached directly.
    """
    workspace = _multi_release_workspace(tmp_path, declared_release=None)
    selected = {row["document_id"] for row in workspace.query("selected_documents")}
    assert selected == {"module", "base"}
    workspace.close()


def test_a_class_overlaid_only_above_the_target_keeps_its_lowest_copy(tmp_path: Path):
    """The case the spec does not cover, decided here and pinned so it is not
    decided again by accident.

    A class can exist ONLY under `META-INF/versions/`, at releases all ABOVE
    the module's target — 626 such names were measured across the cached
    corpus. Dropping the name would assert the class does not exist, which is
    false. Keeping the LOWEST is the choice: it is the copy this module reaches
    first as its target rises, and it makes the answer deterministic rather
    than dependent on row order.
    """
    facts = tmp_path / "facts"
    facts.mkdir(parents=True, exist_ok=True)
    for name, release in (("v24", "24"), ("v25", "25")):
        write_fact_file(
            facts / f"{name}.jsonl",
            Document(
                document_id=name,
                relative_path="com/acme/OnlyNew.java",
                module_id="com.acme:m",
                language="java",
                sextant_version="0.1.0",
                fact_schema_version=5,
                scanner_id="sextant-jvm-extractor",
                class_release=release,
                class_name="com/acme/OnlyNew.class",
                content_hash=f"sha256:{name}",
                origin_entry="target/classes",
                origin_tier=OriginTier.MODULE_OUTPUT,
                redaction_set_hash="sha256:none",
            ),
            [
                SymbolFact(
                    document_id=name,
                    symbol="mod com/acme/OnlyNew#",
                    construct_kind="class",
                    visibility="public",
                )
            ],
        )
    write_fact_file(
        facts / "module.jsonl",
        Document(
            document_id="module",
            relative_path="module",
            module_id="com.acme:m",
            language="module",
            sextant_version="0.1.0",
            fact_schema_version=5,
            scanner_id="sextant-detector",
            content_hash="sha256:module",
            origin_entry="com.acme/m",
            origin_tier=OriginTier.MODULE_OUTPUT,
            redaction_set_hash="sha256:none",
        ),
        [
            ModuleFact(
                document_id="module",
                module_id="com.acme:m",
                module_kind="service",
                languages=["java"],
                source_roots=[],
                output_dirs=[],
                declared_release=21,
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    selected = {row["document_id"] for row in workspace.query("selected_documents")}
    # Kept, not dropped — and exactly one of them, so the symbol is not doubled.
    assert selected == {"module", "v24"}
    workspace.close()


def test_no_exported_table_ships_a_credential_another_one_masks(tmp_path: Path):
    """The leak review found: the bundle masked `call_sites.arguments` and then
    shipped `raw_facts` — which CONTAINS those same call-site facts — verbatim
    in the same directory. A consumer recomputing a derived table from the fact
    stream got different values and could not tell a redaction from a defect.

    Asserted over EVERY exported table rather than the two that were wrong, so
    a table added later cannot reintroduce it quietly: this is the ratchet's
    shape applied to redaction.
    """
    facts = tmp_path / "facts"
    facts.mkdir(parents=True, exist_ok=True)
    document = Document(
        document_id="doc",
        relative_path="com/acme/A.java",
        module_id="com.acme:m",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=5,
        scanner_id="sextant-jvm-extractor",
        class_name="com/acme/A.class",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )
    secret = "https://user:hunter2@billing.internal/pay"
    write_fact_file(
        facts / "A.jsonl",
        document,
        [
            CallSiteFact(
                document_id="doc",
                caller="mod com/acme/A#go(sig_1).",
                target=CallTarget(
                    owner="x/Client#", name="post", descriptor="(Ljava/lang/String;)V"
                ),
                invoke_kind="virtual",
                ordinal=0,
                arguments=[CallArgument(kind="string", value=secret)],
            ),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    bundle = tmp_path / "bundle"
    exported = workspace.export_tables(bundle, Redactor.from_rules())
    workspace.export_facts(bundle, Redactor.from_rules())

    leaked = []
    for parquet in sorted((bundle / "graph").glob("*.parquet")):
        rows = duckdb.sql(f"SELECT * FROM read_parquet('{parquet}')").fetchall()
        if any("hunter2" in str(cell) for row in rows for cell in row):
            leaked.append(parquet.name)
    for parquet in sorted((bundle / "facts").glob("*.parquet")):
        rows = duckdb.sql(f"SELECT * FROM read_parquet('{parquet}')").fetchall()
        if any("hunter2" in str(cell) for row in rows for cell in row):
            leaked.append(f"facts/{parquet.name}")

    assert exported, "nothing was exported, so this proves nothing"
    assert leaked == [], f"a credential left in the clear in: {leaked}"
    # The workspace keeps it verbatim — the analyst's own disk is not the
    # trust boundary, the bundle is.
    assert any("hunter2" in str(row.get("arguments")) for row in workspace.query("call_sites"))
    workspace.close()


def test_every_view_that_reads_class_facts_applies_multi_release_selection(tmp_path: Path):
    """Only ONE of the filtered views was pinned, so reverting the filter on
    `annotations`, `call_sites`, `method_returns` or `field_writes` left the
    suite green — and the review found five MORE readers that had no filter at
    all, including the type-hierarchy queries where a losing overlay does the
    most damage.

    Asserted over the readers as a set rather than one at a time, so a view
    added later that reads class facts and forgets the filter fails here.
    """
    workspace = _multi_release_workspace(tmp_path, declared_release=21)
    losing = {"base", "v99"}
    for view in ("symbols", "annotations", "call_sites", "method_returns", "field_writes"):
        rows = workspace._connection.execute(f"SELECT DISTINCT document_id FROM {view}").fetchall()
        seen = {row[0] for row in rows}
        assert not (seen & losing), f"{view} still reads a copy selection rejected: {seen & losing}"
    # And the named queries that read symbol facts straight from raw_facts.
    for named in ("supertypes", "implementations", "superclasses", "interface_declarations"):
        symbols = {str(row["symbol"]) for row in workspace.query(named)}
        assert len(symbols) == len(list(workspace.query(named))), (
            f"{named} returns a symbol more than once, so a losing copy still contributes"
        )
    workspace.close()


def test_the_three_unpinned_redaction_joins_actually_mask(tmp_path: Path):
    """`roots.path`, `return_flows.value` and `method_returns.value` each gained
    a redaction join in W34, and none was tested — delete any one of the three
    and the suite stayed green. They are the columns most likely to carry an
    address or a bytecode string constant into a published bundle.
    """
    facts = tmp_path / "facts"
    facts.mkdir(parents=True, exist_ok=True)
    document = Document(
        document_id="doc",
        relative_path="com/acme/A.java",
        module_id="com.acme:m",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=5,
        scanner_id="sextant-jvm-extractor",
        class_name="com/acme/A.class",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )
    secret = "https://user:hunter2@billing.internal/pay"
    write_fact_file(
        facts / "A.jsonl",
        document,
        [
            MethodReturnFact(
                document_id="doc",
                method="mod com/acme/A#go(sig_1).",
                ordinal=0,
                value=CallArgument(kind="string", value=secret),
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    workspace._connection.execute(
        "INSERT INTO roots VALUES (?, 'inbound_endpoint', 'http', 'GET', ?)",
        ["mod com/acme/A#go(sig_1).", secret],
    )
    workspace._connection.execute(
        "INSERT INTO return_flows VALUES (?, 0, 1, ?, 0, ?::JSON, 'resolved', 'compiler')",
        [
            "mod com/acme/A#c(sig_1).",
            "mod com/acme/A#go(sig_1).",
            f'{{"kind":"string","value":"{secret}"}}',
        ],
    )
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules())
    for table in ("roots", "return_flows", "method_returns"):
        rows = duckdb.sql(
            f"SELECT * FROM read_parquet('{bundle / 'graph' / (table + '.parquet')}')"
        ).fetchall()
        assert rows, f"{table} exported no row, so this proves nothing"
        assert not any("hunter2" in str(cell) for row in rows for cell in row), (
            f"{table} shipped a credential in the clear"
        )
    workspace.close()
