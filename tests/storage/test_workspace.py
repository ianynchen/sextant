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
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
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
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
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
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
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
        fact_schema_version="1.0.0",
        scanner_id="sextant-config-reader",
        scanner_version="0.1.0",
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
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
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
    "prefix_annotation": "com/acme/messaging/annotation/Topic#",
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
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
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


def test_exported_tables_include_call_sites(tmp_path: Path):
    workspace = _workspace_with_a_call_site(tmp_path)
    workspace.export_tables(tmp_path / "bundle", Redactor.from_rules())
    workspace.close()
    assert (tmp_path / "bundle" / "graph" / "call_sites.parquet").exists()


def test_exported_tables_read_back_equal_to_the_workspace_query(tmp_path: Path):
    workspace = _workspace_with_an_endpoint(tmp_path)
    written = workspace.export_tables(tmp_path / "bundle", Redactor.from_rules())
    assert written == [
        "annotations",
        "call_sites",
        "documents",
        "endpoints",
        "error_handlers",
        "open_questions",
        "resolved_config",
        "scheduled_work",
        "shape_fields",
        "shapes",
        "symbols",
    ]
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
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
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
        fact_schema_version="1.0.0",
        scanner_id="detector",
        scanner_version="0",
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
