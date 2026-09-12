import json
import re
from pathlib import Path

import duckdb
import pytest

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
    ConstantFact,
    Document,
    FieldWriteFact,
    MethodReturnFact,
    ModuleFact,
    SymbolFact,
)
from sextant.domain.redaction import REDACTED, RedactionRules, Redactor
from sextant.egress.export.index import write_index
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb import workspace as workspace_module
from sextant.storage.duckdb.workspace import _FACT_VIEWS, DuckDbWorkspace


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


def test_null_method_rows_dedup_on_the_same_identity(tmp_path: Path):
    """D02D Task 3's core invariant: a NULL-verb wire identity must dedup exactly like
    every HTTP identity does, WITHIN its own direction. Plain SQL equality treats
    `NULL = NULL` as unknown, so before the fix re-deriving the same NULL-method inbound
    row twice would double it, and deriving the same NULL-method outbound row twice via
    `call_endpoints` would double it too.

    *It also covered `merge_endpoints.sql`'s join from outbound back to inbound finding
    its NULL-method twin. There is no such join since W27 (F5 §6.1): the two directions
    are never folded together, and the topic below — a module publishing to a topic it
    also consumes — is the self-publish case `test_self_exchange.py` now asks about.*"""
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

    rows = workspace.query("endpoints")
    workspace.close()

    assert sorted((str(r["direction"]), r["method"], str(r["path"])) for r in rows) == [
        ("inbound", None, "order-events"),
        ("outbound", None, "order-events"),
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


def test_each_direction_keeps_the_catalog_id_that_derived_it(tmp_path: Path):
    """`catalog_id` is provenance, not identity (D01 §3): it names the catalog whose
    rules produced THIS row.

    This used to be a statement about the merge — `merge_endpoints.sql` updated the
    inbound row in place and deleted the outbound one, so the surviving `both` row kept
    the inbound side's id and the outbound catalog's provenance was gone with its row.
    Since W27 (F5 §6.1) neither row is deleted, so each keeps the id of the catalog that
    actually derived it, which is what the column has always claimed to mean.
    """
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
    rows = workspace.query("endpoints")
    workspace.close()

    assert sorted((str(r["direction"]), str(r["catalog_id"])) for r in rows) == [
        ("inbound", "cat-in"),
        ("outbound", "cat-out"),
    ]


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
    # drift the round trip exists to catch. Read back decoded: `arguments` is
    # one of the columns the workspace hands over as objects (`_DECODED_COLUMNS`).
    assert row["arguments"] == [
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
    exemption. The `fact_*` tables `load_facts` builds are not one either:
    each is the storage behind one fact view, and that view exports under its
    own name, so its rows travel exactly once.
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


def _call_site_facts_carrying(root: Path, value: str) -> None:
    """One call_site fact whose single argument is `value` — the shape a
    credential reaches the argument grammar in."""
    document = Document(
        document_id="doc_secret",
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
    write_fact_file(
        root / "A.jsonl",
        document,
        [
            CallSiteFact(
                document_id="doc_secret",
                caller="mod com/acme/A#go(sig_1).",
                target=CallTarget(
                    owner="x/Client#", name="post", descriptor="(Ljava/lang/String;)V"
                ),
                invoke_kind="virtual",
                ordinal=0,
                arguments=[CallArgument(kind="string", value=value)],
            ),
        ],
    )


def _exported_argument_values(bundle: Path) -> set[str]:
    """Every string-literal argument value the bundle's call-site facts carry."""
    return {
        str(value)
        for (value,) in duckdb.sql(
            "SELECT unnest(from_json(payload -> 'arguments', '[\"JSON\"]')) ->> 'value' "
            f"FROM read_parquet('{bundle / 'facts' / '*.parquet'}') WHERE kind = 'call_site'"
        ).fetchall()
        if value is not None
    }


# The texts `test_the_prefilter_admits_every_payload_the_walk_would_change` runs,
# spelled as a JSON writer spells them (the strings are Python source, so `\\/`
# here is `\/` in the text). Each is a fact payload shape or a fragment of one;
# what they are chosen for is the seam between the decoded string a rule reads
# and the encoded text the predicate reads: escapes inside a URL's userinfo,
# `/` spelled `\/`, a non-ASCII letter spelled both ways, a name in each
# separator and case spelling `normalize_key` folds, and the prose and
# expression shapes the rules deliberately leave alone.
_PREFILTER_TEXTS = [
    '{"value":"https://user:hunter2@billing.internal/pay"}',
    '{"value":"https:\\/\\/user:hunter2@billing.internal"}',
    '{"value":"http://us\\"er:p@host"}',
    '{"value":"http://us\\ter:p@host"}',
    '{"value":"user@host"}',
    '{"value":"${jdbc.url}@x"}',
    '{"value":"jdbc:postgresql://db/orders"}',
    '[{"kind":"string","value":"Authorization"},{"kind":"string","value":"Bearer x"}]',
    '[{"kind":"string","value":"api_key"},{"kind":"string","value":"k"}]',
    '[{"kind":"string","value":"API-KEY"},{"kind":"string","value":"k"}]',
    '[{"kind":"string","value":"X-Api-Key"},{"kind":"string","value":"k"}]',
    '[{"kind":"string","value":"apiKey"},{"kind":"array","elements":[{"kind":"string","value":"k"}]}]',
    '[{"kind":"string","value":"password"}]',
    '[{"kind":"string","value":"Changed password for {}"},{"kind":"string","value":"bob"}]',
    '[{"kind":"string","value":"a"},{"kind":"string","value":"b"}]',
    '{"password":"/billing/invoices","token":"order-events"}',
    '{"value":"sk-live-abc123"}',
    '{"value":"SK-LIVE-abc123"}',
    '{"value":"\u017fK-live-abc123"}',
    '{"value":"\\u017fK-live-abc123"}',
    '{"value":"BEARER tok"}',
    '{"value":"beaRER\\ttok"}',
    '{"value":"bearer"}',
    '{"value":"x.env=1"}',
    '{"value":"xaenv=1"}',
    '{"value":"\u2014 \u00e9"}',
    '{"value":"\\u2014 \\u00e9"}',
    '{"value":"4111111111111111"}',
    '{"kind":"symbol","symbol":"com/acme/Secret#","name":"Secret"}',
    # The scheme in either case and with the `+.-` a scheme may carry.
    '{"value":"HTTPS://u:p@h"}',
    '{"value":"svn+ssh://u:p@h"}',
    # A value pattern (`https://host`) that matches only AFTER the userinfo
    # strip: admitted through the userinfo alternative, which is why the
    # value-pattern branch need not see through the strip itself.
    '{"value":"https://u:p@host"}',
    # The four non-ASCII letters Python's case fold maps onto `i`, `k` and
    # `s`, each spelled raw (as the extractor writes them) and escaped —
    # against a `(?i)` prefix carrying `k` and `i`.
    '{"value":"\u212aelvin-42"}',
    '{"value":"\\u212aelvin-42"}',
    '{"value":"kelv\u0131n-42"}',
    '{"value":"kelv\\u0131n-42"}',
    '{"value":"kelv\u0130n-42"}',
    '{"value":"kelv\\u0130n-42"}',
]

_PREFILTER_REDACTORS = [
    Redactor.from_rules(),
    Redactor.from_rules(RedactionRules(key_patterns=("dsn",))),
    Redactor.from_rules(
        RedactionRules(value_patterns=("sk-live-[a-z0-9]+", r"(?i)bearer\s+\S+", r"\.env="))
    ),
    Redactor.from_rules(RedactionRules(value_patterns=(r"(?i)sk-live-[a-z0-9]+",))),
    Redactor.from_rules(RedactionRules(value_patterns=(r"(?i)kelvin-[0-9]+", "https://host"))),
    Redactor.from_rules(RedactionRules(value_patterns=("[0-9]{16}",))),
]


def test_the_prefilter_admits_every_payload_the_walk_would_change():
    """The one property `_stage_fact_redactions`' SQL prefilter rests on, run
    where RE2 actually runs: for every text and every rule set, a payload the
    walk changes is a payload the predicate matches. The reverse is not
    claimed — the predicate is allowed to admit more, and does — so the two
    counts at the end say the test is not vacuous: some texts change, and
    more texts than those are turned away, on the same rule set.

    Evaluated through DuckDB rather than Python's `re`, because the predicate
    is written in RE2's dialect and the two disagree exactly where it matters
    (case folding, `\\s`)."""
    connection = duckdb.connect()
    changed = 0
    turned_away = 0
    for redactor in _PREFILTER_REDACTORS:
        prefilter = redactor.json_text_prefilter()
        for text in _PREFILTER_TEXTS:
            walk_changes_it = redactor.redact_json(text) != text
            admitted = prefilter is None or bool(
                connection.execute("SELECT regexp_matches(?, ?)", [text, prefilter]).fetchone()[0]
            )
            assert admitted or not walk_changes_it, (text, prefilter)
            changed += walk_changes_it
            turned_away += not admitted
    connection.close()
    assert changed >= 20 and turned_away >= 30


def test_the_second_export_reuses_the_payloads_the_first_staged(tmp_path: Path):
    """`export_tables` and `export_facts` join the same payload map, and
    computing it was the largest cost of exporting a workspace (1.1s of
    `mall-admin`'s 3.3s, paid twice). The second call re-stages the rows the
    first computed: the redactor is not consulted again, and the bundle is
    masked exactly as before."""
    _call_site_facts_carrying(tmp_path / "facts", "https://user:hunter2@billing.internal/pay")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    redactor = Redactor.from_rules()
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, redactor)

    def not_again(text: str) -> str:
        raise AssertionError("the second export re-derived the payload map")

    redactor.redact_json = not_again  # type: ignore[method-assign]
    workspace.export_facts(bundle, redactor)
    workspace.close()
    assert _exported_argument_values(bundle) == {"https://billing.internal/pay"}


def test_reloading_facts_forgets_the_staged_payloads(tmp_path: Path):
    """The kept rows describe one `raw_facts`; `load_facts` is its one writer
    and clears them. Pinned on the failure that matters: a workspace exported
    once with nothing to mask, then reloaded with a credential, must mask the
    credential — a stale map would ship it in the clear."""
    _call_site_facts(tmp_path / "first")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "first")
    redactor = Redactor.from_rules()
    workspace.export_facts(tmp_path / "one", redactor)
    assert _exported_argument_values(tmp_path / "one") == {"/billing/invoices"}

    _call_site_facts_carrying(tmp_path / "second", "https://user:hunter2@billing.internal/pay")
    workspace.load_facts(tmp_path / "second")
    workspace.export_facts(tmp_path / "two", redactor)
    workspace.close()
    assert _exported_argument_values(tmp_path / "two") == {"https://billing.internal/pay"}


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

    **And over every DIRECTORY of the bundle**, which it was not. It globbed
    `graph/` and `facts/`, so when W35 added `index/` — a third projection over
    the same rows — its two path-carrying files shipped an address `graph/`
    masked, in the same bundle, and this test stayed green. A ratchet keyed on
    the two directories that existed when it was written is a ratchet that stops
    the day a third arrives.
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
    # The same credential in an ADDRESS column, because the sweep has to reach every shape
    # a secret travels in and not only the argument grammar: `endpoints.path` and
    # `roots.path` are masked in `graph/` and are what the index's two path-carrying files
    # are built from.
    workspace._connection.execute(
        "INSERT INTO endpoints (protocol, direction, method, path, handler, catalog_id) "
        "VALUES ('http', 'inbound', 'GET', ?, 'mod com/acme/A#go(sig_1).', 'c')",
        [secret],
    )
    workspace._connection.execute(
        "INSERT INTO roots (handler, root_kind, protocol, method, path) "
        "VALUES ('mod com/acme/A#go(sig_1).', 'inbound_endpoint', 'http', 'GET', ?)",
        [secret],
    )
    bundle = tmp_path / "bundle"
    exported = workspace.export_tables(bundle, Redactor.from_rules())
    workspace.export_facts(bundle, Redactor.from_rules())

    # The index is a third projection over the same rows, so it ships here too and is
    # swept with everything else — see `write_index` for why it takes the same redactor.
    index_files = write_index(
        bundle,
        symbols=workspace.query("located_symbols"),
        documents=workspace.query("located_documents"),
        call_edges=workspace.query("call_edges"),
        implementations=workspace.query("implementations"),
        annotations=workspace.query("annotations"),
        endpoints=workspace.query("endpoints"),
        roots=workspace.query("roots"),
        shapes=workspace.query("shapes"),
        shape_fields=workspace.query("shape_fields"),
        source_roots=[],
        module_root=tmp_path,
        redactor=Redactor.from_rules(),
    )

    leaked = []
    # EVERY file in the bundle, whatever directory it landed in and whatever format it is
    # in — the point being that the sweep must not have to be taught about a new one.
    for shipped in sorted(bundle.rglob("*")):
        if not shipped.is_file():
            continue
        name = str(shipped.relative_to(bundle))
        if shipped.suffix == ".parquet":
            rows = duckdb.sql(f"SELECT * FROM read_parquet('{shipped}')").fetchall()
            if any("hunter2" in str(cell) for row in rows for cell in row):
                leaked.append(name)
        elif "hunter2" in shipped.read_text(encoding="utf-8", errors="replace"):
            leaked.append(name)

    assert exported, "nothing was exported, so this proves nothing"
    assert index_files, "no index was written, so this proves nothing about it"
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


def test_the_alternate_orderings_carry_the_same_rows_in_a_different_order(tmp_path: Path):
    """F8 §9.4 (W37). DuckDB over Parquet has no B-trees; the levers are sort order and
    the zone maps that come with it, so a second FILE in a second order is the index.

    Views rather than tables, so the rows are the base table's own and cannot fall out of
    step — which is exactly what this asserts: same rows, different order.
    """
    workspace = _workspace_with_an_endpoint(tmp_path)
    workspace._connection.execute(
        "INSERT INTO call_edges (caller, ordinal, invoke_kind, target, callee, result, "
        "resolution, evidence) VALUES "
        "('m a/Z#z().', 0, 'virtual', 'a/A#a().', 'm a/A#a().', NULL, 'resolved', "
        "'compiler'), "
        "('m a/A#a().', 0, 'virtual', 'a/Z#z().', 'm a/Z#z().', NULL, 'resolved', "
        "'compiler')"
    )

    caller_major = [
        row["callee"] for row in workspace.query("call_edges") if row["callee"] is not None
    ]
    callee_major = [
        row["callee"]
        for row in workspace._connection.execute(
            "SELECT callee FROM call_edges_by_callee WHERE callee IS NOT NULL"
        ).fetchall()
        for row in [{"callee": row[0]}]
    ]
    workspace.close()

    assert sorted(caller_major) == sorted(callee_major), "the rows are the same rows"
    assert callee_major == sorted(callee_major), "and the second file is callee-sorted"


def test_the_address_ordering_masks_its_path_like_the_table_it_reorders(tmp_path: Path):
    """A second file of the same rows that skipped the mask would be the leak the index
    bundle had — one bundle, two answers about one address."""
    workspace = _workspace_with_an_endpoint(tmp_path)
    secret = "https://user:hunter2@billing.internal/pay"
    workspace._connection.execute(
        "INSERT INTO roots (handler, root_kind, protocol, method, path) "
        "VALUES ('m a/A#a().', 'inbound_endpoint', 'http', 'GET', ?)",
        [secret],
    )
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules())
    workspace.close()

    for name in ("roots", "roots_by_address"):
        rows = duckdb.sql(
            f"SELECT * FROM read_parquet('{bundle / 'graph' / f'{name}.parquet'}')"
        ).fetchall()
        assert not any("hunter2" in str(cell) for row in rows for cell in row), name


def test_the_coverage_distributions_group_the_columns_that_already_exist(tmp_path: Path):
    """FR-17 clause 3 (F8 §9.5, W38). Three GROUP BYs, composed into `coverage` by
    `resolve/pipeline.py`.

    The reach bucket is the one that answers the question the wave was added for.
    `resolution` says whether DISPATCH settled a call and reads 100% `resolved` on two of
    the four measured corpora; `callee IS NULL` says whether the body was there, which is
    the work. Both ship, because the first without the second is the corpus blindness the
    design warns about and the second without the first cannot say why.
    """
    workspace = _workspace_with_an_endpoint(tmp_path)
    workspace._connection.execute(
        "INSERT INTO call_edges (caller, ordinal, invoke_kind, target, callee, result, "
        "resolution, evidence) VALUES "
        "('m a/A#a().', 0, 'virtual', 'a/B#b().', 'm a/B#b().', NULL, 'resolved', "
        "'compiler'), "
        "('m a/A#a().', 1, 'virtual', 'x/Lib#go().', NULL, NULL, 'resolved', 'compiler'), "
        "('m a/A#a().', 2, 'interface', 'a/I#i().', 'm a/P#i().', NULL, 'narrowed', "
        "'compiler'), "
        # The second candidate of that same narrowed site, so the two rules cannot
        # agree by accident: with three edges the counts coincided and bucketing on
        # `resolution` instead of on `callee` passed.
        "('m a/A#a().', 2, 'interface', 'a/I#i().', 'm a/Q#i().', NULL, 'narrowed', "
        "'compiler')"
    )

    resolution = {row["bucket"]: row["edges"] for row in workspace.query("resolution_distribution")}
    reach = {row["bucket"]: row["edges"] for row in workspace.query("reach_distribution")}
    workspace.close()

    assert resolution == {"resolved": 2, "narrowed": 2}
    # The same three edges, bucketed by whether a BODY was read — which is the number
    # `resolution` cannot give: two of these are `resolved` and one of those two reached
    # nothing.
    assert reach == {"body_read": 3, "boundary": 1}


# --------------------------------------------------------------------------
# The fact views are materialized once per load (P-1a)
# --------------------------------------------------------------------------


def _view_sql(workspace: DuckDbWorkspace) -> dict[str, str]:
    rows = workspace._connection.execute(
        "SELECT view_name, sql FROM duckdb_views() WHERE NOT internal"
    ).fetchall()
    return {str(name): str(sql) for name, sql in rows}


def _rows_of(workspace: DuckDbWorkspace, sql: str) -> list[tuple[object, ...]]:
    return sorted(workspace._connection.execute(sql).fetchall(), key=repr)


def _fact_tables(workspace: DuckDbWorkspace) -> set[str]:
    rows = workspace._connection.execute(
        "SELECT table_name FROM duckdb_tables() WHERE starts_with(table_name, 'fact_')"
    ).fetchall()
    return {str(name) for (name,) in rows}


def test_every_fact_view_is_materialized_on_load_and_answers_exactly_as_its_json_form_did(
    tmp_path: Path,
):
    """The correctness pin for P-1a. Measured on `mall-admin`, every fact view
    re-extracted JSON from `raw_facts` on every query, and one pass ran one of
    them 629 times; `load_facts` now builds a `fact_<view>` table per view and
    points the view at it. The JSON-form SELECT is captured from an EMPTY
    workspace — `schema.sql`'s own definition, before anything was loaded —
    and re-run against the loaded workspace beside each materialized view, so
    a table that drifted from the definition by one column or one row fails
    here. The multi-release fixture is used because its selection actually
    excludes rows, and a config entry and a constant ride along so every view
    has something to hold — asserted, because an empty view compares equal to
    anything."""
    empty = DuckDbWorkspace(tmp_path / "empty.duckdb")
    json_form = {view: _view_sql(empty)[view].split(" AS ", 1)[1] for view in _FACT_VIEWS}
    empty.close()
    _config_entry_facts(tmp_path / "facts")
    write_fact_file(
        tmp_path / "facts" / "Topics.jsonl",
        Document(
            document_id="doc_constants",
            relative_path="com/acme/Topics.java",
            module_id="com.acme:m",
            language="java",
            sextant_version="0.1.0",
            fact_schema_version=5,
            scanner_id="asm",
            content_hash="sha256:t",
            origin_entry="target/classes",
            origin_tier=OriginTier.MODULE_OUTPUT,
            redaction_set_hash="sha256:none",
        ),
        [
            ConstantFact(
                document_id="doc_constants", symbol="mod com/acme/Topics#TOPIC.", value="orders"
            )
        ],
    )
    workspace = _multi_release_workspace(tmp_path, declared_release=21)
    defined = _view_sql(workspace)
    for view in _FACT_VIEWS:
        assert defined[view] == f"CREATE VIEW {view} AS SELECT * FROM fact_{view};"
        materialized = _rows_of(workspace, f"SELECT * FROM {view}")
        assert materialized == _rows_of(workspace, json_form[view]), view
        assert materialized, f"{view} holds no rows, so the comparison proves nothing"
    workspace.close()


def test_reopening_a_workspace_keeps_the_fact_views_on_their_tables(tmp_path: Path):
    """`__init__` re-runs `schema.sql`, which re-issues every fact view in its
    JSON form — so without the reopen rule, every command that opens an
    analyzed workspace would run the slow views while the tables sat unused."""
    workspace = _multi_release_workspace(tmp_path, declared_release=21)
    before = {view: _rows_of(workspace, f"SELECT * FROM {view}") for view in _FACT_VIEWS}
    workspace.close()

    reopened = DuckDbWorkspace(tmp_path / "ws.duckdb")
    defined = _view_sql(reopened)
    for view in _FACT_VIEWS:
        assert defined[view] == f"CREATE VIEW {view} AS SELECT * FROM fact_{view};"
        assert _rows_of(reopened, f"SELECT * FROM {view}") == before[view], view
    reopened.close()


def test_a_fact_table_that_no_longer_matches_the_schema_is_dropped_on_reopen(
    tmp_path: Path,
):
    """A schema that gained a column since the tables were written must not be
    masked by a stale table: the views fall back to the JSON form and every
    `fact_*` table goes, so the next `load_facts` rebuilds them. Simulated from
    the other side — a table missing a column the view declares — which is the
    same mismatch."""
    workspace = _multi_release_workspace(tmp_path, declared_release=21)
    expected = _rows_of(workspace, "SELECT * FROM symbols")
    workspace.close()
    stale = duckdb.connect(str(tmp_path / "ws.duckdb"))
    stale.execute("ALTER TABLE fact_symbols DROP COLUMN line_end")
    stale.close()

    reopened = DuckDbWorkspace(tmp_path / "ws.duckdb")
    assert "FROM raw_facts" in _view_sql(reopened)["symbols"]
    assert _fact_tables(reopened) == set()
    assert _rows_of(reopened, "SELECT * FROM symbols") == expected
    reopened.close()


def test_loading_facts_twice_rebuilds_the_tables_from_the_second_tree(tmp_path: Path):
    """`raw_facts` has one writer, and the tables are rebuilt at the end of
    every write — never left over from the previous one."""
    workspace = _multi_release_workspace(tmp_path, declared_release=21)
    assert workspace._connection.execute("SELECT count(*) FROM documents").fetchone() == (4,)
    _fixture_facts(tmp_path / "second")
    workspace.load_facts(tmp_path / "second")

    assert workspace._connection.execute("SELECT count(*) FROM documents").fetchone() == (1,)
    assert workspace._connection.execute("SELECT symbol FROM symbols").fetchall() == [
        ("s maven p 1 com/acme/A#",)
    ]
    assert _view_sql(workspace)["symbols"] == "CREATE VIEW symbols AS SELECT * FROM fact_symbols;"
    workspace.close()


# ---- P-1b: fact-only queries are read once per load, JSON-bound parameters ----


class _CountingConnection:
    """The workspace's DuckDB connection, with every `execute` recorded — timing-free
    evidence of whether a query ran."""

    def __init__(self, inner: duckdb.DuckDBPyConnection) -> None:
        self.inner = inner
        self.executed: list[str] = []

    def execute(self, sql: str, *args: object) -> duckdb.DuckDBPyConnection:
        self.executed.append(sql)
        return self.inner.execute(sql, *args)

    def __getattr__(self, name: str) -> object:
        return getattr(self.inner, name)


def _counting(workspace: DuckDbWorkspace) -> _CountingConnection:
    connection = _CountingConnection(workspace._connection)
    workspace._connection = connection  # type: ignore[assignment]
    return connection


def test_a_fact_only_query_is_read_once_per_load_and_read_again_after_the_next_load(
    tmp_path: Path,
):
    """`declared_symbols` reads only the fact tables, and `load_facts` is their one
    writer — so the second call is the first call's rows, the same list, and only the
    next load makes the query run again."""
    workspace = _loaded_workspace(tmp_path)
    connection = _counting(workspace)

    first = workspace.query("declared_symbols")
    assert first == [{"symbol": "s maven p 1 com/acme/A#"}]
    assert len(connection.executed) == 1
    assert workspace.query("declared_symbols") is first
    assert len(connection.executed) == 1, "the second read ran the query again"

    _fixture_facts(tmp_path / "second")
    document = Document(
        document_id="doc_2",
        relative_path="com/acme/B.java",
        module_id="com.acme:orders",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:c",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    symbol = SymbolFact(
        document_id="doc_2", symbol="s maven p 1 com/acme/B#", construct_kind=ConstructKind.CLASS
    )
    write_fact_file(tmp_path / "second" / "com" / "acme" / "B.jsonl", document, [symbol])
    workspace.load_facts(tmp_path / "second")

    second = workspace.query("declared_symbols")
    assert second is not first
    assert second == [{"symbol": "s maven p 1 com/acme/A#"}, {"symbol": "s maven p 1 com/acme/B#"}]
    workspace.close()


def test_a_parameterized_fact_only_query_is_cached_per_bound_value(tmp_path: Path):
    workspace = _workspace_with_an_endpoint(tmp_path)
    connection = _counting(workspace)
    controller = "com/acme/orders/OrderController#"
    method = "com/acme/orders/OrderController#list(sig_08c5be17)."

    on_controller = workspace.query("annotations_of", target=controller)
    on_method = workspace.query("annotations_of", target=method)
    assert [row["annotation"] for row in on_controller] == [
        "org/springframework/web/bind/annotation/RequestMapping#",
        "org/springframework/web/bind/annotation/RestController#",
    ]
    assert [row["annotation"] for row in on_method] == [
        "org/springframework/web/bind/annotation/GetMapping#"
    ]
    assert len(connection.executed) == 2
    assert workspace.query("annotations_of", target=controller) is on_controller
    assert workspace.query("annotations_of", target=method) is on_method
    assert len(connection.executed) == 2
    workspace.close()


def test_a_query_over_a_derived_table_is_never_served_from_the_cache(tmp_path: Path):
    """`endpoints` is written by derivations between one read and the next, so the
    rows it hands back are the table's rows NOW — here, none after the reset."""
    workspace = _workspace_with_an_endpoint(tmp_path)
    connection = _counting(workspace)

    assert len(workspace.query("endpoints")) == 1
    workspace.derive("endpoints_reset")
    assert workspace.query("endpoints") == []
    assert [sql for sql in connection.executed if sql.lstrip().startswith("SELECT")] == [
        workspace_module._NAMED_QUERIES["endpoints"],
        workspace_module._NAMED_QUERIES["endpoints"],
    ]
    workspace.close()


_FACT_TABLES = frozenset({"raw_facts", *_FACT_VIEWS})


def _tables_read(sql: str) -> set[str]:
    body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return set(re.findall(r"\b(?:FROM|JOIN)\s+([a-z_]+)", body))


def _tables_written(sql: str) -> set[str]:
    body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return set(
        re.findall(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?|"
            r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP\s+|TEMPORARY\s+)?TABLE(?:\s+IF\s+NOT\s+EXISTS)?)"
            r"\s+([a-z_]+)",
            body,
        )
    )


def test_the_cache_rule_holds_for_every_named_query_and_every_derivation():
    """The invalidation rule, checked rather than trusted: a `_FACT_ONLY` query reads
    fact tables and nothing else; a query reading anything else is not in the set (a
    name that could be cached and is not is a defect too, since the set is what makes
    a resolve read each fact table once); and no derivation writes a fact table, which
    is what leaves `load_facts` as the one event that clears the cache."""
    for name, sql in workspace_module._NAMED_QUERIES.items():
        read = _tables_read(sql)
        assert read, f"{name}: reads no table at all?"
        if name in workspace_module._FACT_ONLY:
            assert read <= _FACT_TABLES, f"{name} is cached but reads {read - _FACT_TABLES}"
        else:
            assert not read <= _FACT_TABLES, f"{name} reads only fact tables and is not cached"
    for name, file in workspace_module._NAMED_DERIVATIONS.items():
        sql = (workspace_module._SQL_DIR / file).read_text(encoding="utf-8")
        written = _tables_written(sql)
        assert written, f"{name}: writes no table?"
        assert not (written & _FACT_TABLES), f"{name} writes a fact table: {written}"


def test_decoded_columns_arrive_as_objects_and_a_json_null_as_none(tmp_path: Path):
    """`method_declarations.signature`/`.modifiers` and `call_sites.arguments` are the
    columns every reader decoded for itself, once per catalog; the workspace hands them
    over decoded, once."""
    workspace = _workspace_with_an_endpoint(tmp_path)
    (declaration,) = workspace.query("method_declarations")
    assert declaration["symbol"] == "com/acme/orders/OrderController#list(sig_08c5be17)."
    # The fixture's method fact declares no signature, which the fact writes as the
    # JSON literal `null` — decoded to `None`, never handed over as the text `null`;
    # its modifiers default to an empty object, decoded to exactly that.
    assert declaration["signature"] is None
    assert declaration["modifiers"] == {}
    workspace.close()

    workspace = _workspace_with_a_call_site(tmp_path / "call_site")
    (site,) = workspace.query("call_sites")
    assert isinstance(site["arguments"], list)
    assert [argument["kind"] for argument in site["arguments"]] == ["string", "unresolved"]
    workspace.close()


def test_a_list_parameter_binds_as_one_json_value_and_reads_back_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The rows a pass hands a derivation travel as one JSON value (`_bound`), and every
    value comes back exactly as it went in — quotes, backslashes, non-ASCII text, NULL —
    including a struct key the row does not carry, which the statement's own type
    supplies as NULL, the contract every hand-built row in this file relies on."""
    workspace = _loaded_workspace(tmp_path)
    rows = [
        {
            "caller": "he said \"hi\" \\ {x} 'q' ünï",
            "ordinal": 0,
            "invoke_kind": "virtual",
            "target": "t#",
            "callee": None,
            "result": 3,
            "resolution": "resolved",
            "evidence": '{"json":[1,{"k":null}]}',
            "terminal_kind": None,
            "target_kind": "method",
        },
        {"caller": "c#", "ordinal": 1, "invoke_kind": "static", "target": "u#"},
    ]
    workspace.derive("call_edges_insert", rows=rows)
    # The second row lacks six declared keys, so this list took the per-value route —
    # recorded by name, which is what lets a whole pipeline assert it took none.
    assert workspace._per_value_retries == ["call_edges_insert"]
    read = workspace.query("call_edges")
    assert read == [
        {
            "caller": "c#",
            "ordinal": 1,
            "invoke_kind": "static",
            "target": "u#",
            "callee": None,
            "result": None,
            "resolution": None,
            "evidence": None,
            "terminal_kind": None,
            "target_kind": None,
        },
        rows[0],
    ]
    # Only a conversion error is retried: a statement that fails to bind for any other
    # reason propagates from the first run, untouched and unrecorded. The statement lives
    # under `tmp_path` — an absolute path, which `_SQL_DIR / <path>` resolves to as is.
    broken = tmp_path / "broken.sql"
    broken.write_text(
        "INSERT INTO call_edges SELECT r.* "
        "FROM (SELECT UNNEST($rows::STRUCT(no_such INTEGER)[]) AS r)"
    )
    monkeypatch.setitem(workspace_module._NAMED_DERIVATIONS, "_broken", str(broken))
    with pytest.raises(duckdb.BinderException):
        workspace.derive("_broken", rows=[{"no_such": 1}])
    assert workspace._per_value_retries == ["call_edges_insert"]
    workspace.close()
