import dataclasses
import json
from dataclasses import replace
from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.ports.scanner import ScannerProvenance
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.redaction import REDACTED, RedactionRules, Redactor
from sextant.egress.render.document import _GAPS, render_module_document
from sextant.egress.render.metadata import KNOWN_GAPS, write_metadata

# The facilities a fixture workspace's documents claim (D02 §3: capabilities and
# provenance are SCANNER-declared). One entry with libraries, one without, so a
# test exercises both shapes: only a facility running third-party code that can
# move independently of Sextant records versions at all.
SCANNERS = (
    ScannerProvenance("sextant-detector"),
    ScannerProvenance("sextant-jvm-extractor", ("org.ow2.asm:asm:9.10.1",)),
)


MODULE = ModuleModel(
    module_id="com.acme:orders-service",
    coordinates="com.acme/orders-service",
    version="1.0.0",
    root=Path("fixtures/orders-service"),
    kind="service",
    languages=frozenset({"java"}),
    source_roots=(),
    output_dirs=(),
)
REPORT = ResolveReport(
    facts_loaded=42,
    endpoints=[
        {
            "protocol": "http",
            "direction": "inbound",
            "method": "GET",
            "path": "/v1/orders",
            "handler": "s maven c 1 com/acme/C#list().",
            "resolution": "resolved",
            "evidence": "compiler",
        }
    ],
    coverage={"documents": 4, "partial_documents": 0},
    shapes=[{"shape_id": "com/acme/C#", "content_hash": "md5:0", "open": True}],
    unexpanded_types=("org/example/Opaque#",),
)


def test_metadata_records_the_commit_so_staleness_is_visible(tmp_path: Path):
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["provenance"]["commit"] == "a3f91c"
    assert written["coverage"]["documents"] == 4


def test_metadata_environments_are_resolved_configs_own_distinct_set(tmp_path: Path):
    """D06 §3 "environments" (2F Task 9): sibling data to the bundle
    manifest's own field, sorted rather than left in `resolved_config`'s
    row order — a set of profile names, not a row sequence."""
    resolved_config = [
        {"key": "billing.url", "value": "http://billing.internal", "environment": "default"},
        {"key": "billing.url", "value": "http://billing.prod.internal", "environment": "prod"},
        {"key": "only.in.default", "value": None, "environment": "prod"},
    ]
    write_metadata(
        tmp_path / "metadata.json",
        MODULE,
        REPORT,
        SCANNERS,
        "a3f91c",
        resolved_config=resolved_config,
    )
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["environments"] == ["default", "prod"]


def test_metadata_environments_are_empty_when_pass_2_resolved_nothing(tmp_path: Path):
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["environments"] == []


def test_metadata_detect_notes_are_written_sorted_regardless_of_call_order(tmp_path: Path):
    """`detect_notes` is carried out of the detector verbatim (2M design
    §1c) — never sorted at the source, since a detector may find its notes
    in whatever order it happens to read them. `write_metadata` is the one
    place that owes the reader a deterministic key (NFR-1), so the sort has
    to happen HERE, at the write, not merely look sorted by accident because
    every caller so far has passed it in order."""
    write_metadata(
        tmp_path / "metadata.json", MODULE, REPORT, SCANNERS, "a3f91c", detect_notes=("b", "a")
    )
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["detect_notes"] == ["a", "b"]


def test_metadata_names_every_type_expansion_could_not_open(tmp_path: Path):
    """The count says how much was expanded; only the names say what was not,
    and a count cannot be acted on (FR-17, the same rule as `uncovered`)."""
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["shapes"]["count"] == 1
    assert written["shapes"]["unexpanded_types"] == ["org/example/Opaque#"]


def test_document_lists_every_endpoint_and_names_its_gaps():
    text = render_module_document(MODULE, REPORT, "a3f91c")
    assert "GET /v1/orders" in text
    assert "a3f91c" in text
    assert "call graph" in text.lower()
    # Expansion is implemented, so the blanket gap is gone; what remains is
    # the one thing a reader can act on — the type that stopped it.
    assert "shape expansion is not implemented" not in text.lower()
    assert "org/example/Opaque#" in text.split("## Known gaps", 1)[1]


def test_an_unread_source_reaches_both_the_metadata_and_the_gap_list(tmp_path: Path):
    """FR-17's channel, tested where it can be driven directly. The fixture no
    longer has anything uncovered — its nested class is scanned now — but a
    Kotlin class whose `@Metadata` a newer compiler wrote still travels this
    path, and a channel nothing exercises is a channel that rots."""
    unread = ("com/acme/orders/Newer.class: kotlin metadata unreadable (2.9)",)
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, SCANNERS, "a3f91c", unread)
    assert json.loads((tmp_path / "metadata.json").read_text())["uncovered"] == list(unread)

    text = render_module_document(MODULE, REPORT, "a3f91c", unread)
    assert unread[0] in text.split("## Known gaps", 1)[1]


def test_document_is_identical_when_rendered_twice_from_the_same_report():
    assert render_module_document(MODULE, REPORT, "a3f91c") == render_module_document(
        MODULE, REPORT, "a3f91c"
    )


def test_every_machine_readable_gap_has_a_sentence_a_person_can_read():
    """`metadata.json` lists gap keys and the document lists gap sentences, and
    the two are kept in correspondence by a comment alone. A key with no
    sentence is a gap the machine reports and the reader never sees — which is
    a document that reads as complete when it is not (M07)."""
    assert len(KNOWN_GAPS) == len(_GAPS)


def test_metadata_buckets_outbound_and_both_endpoints_into_both_sums(tmp_path: Path):
    """Task 7 ruling: a `both` row (a wire identity this module both exposes
    and calls) counts in both the inbound and outbound sums, so the two sums
    can exceed the row count by the number of merged rows. No test asserted
    the outbound bucket before this task, which is also why metadata could
    report outbound endpoints beside the (now-retired) gap that denied they
    existed."""
    report = ResolveReport(
        facts_loaded=3,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/v1/orders/{id}",
                "handler": "s maven c 1 com/acme/C#get().",
                "resolution": "resolved",
                "evidence": "compiler",
            },
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "POST",
                "path": "/billing/invoices",
                "caller": "s maven c 1 com/acme/BillingClient#create().",
                "peer": "billing",
                "resolution": "resolved",
                "evidence": "compiler",
            },
            {
                "protocol": "http",
                "direction": "both",
                "method": "POST",
                "path": "/v1/orders",
                "handler": "s maven c 1 com/acme/C#create().",
                "caller": "s maven c 1 com/acme/OrdersClient#create().",
                "peer": "orders-loop",
                "resolution": "resolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    write_metadata(tmp_path / "metadata.json", MODULE, report, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    # 3 rows, but the merged `both` row counts on both sides: 2 inbound
    # (GET + the merged POST), 2 outbound (billing + the merged POST) — the
    # sums (4) exceed the row count (3) by exactly the one merged row.
    assert written["endpoints"]["inbound"] == {"http": 2}
    assert written["endpoints"]["outbound"] == {"http": 2}


def test_document_draws_the_contract_class_diagram_and_lists_outbound_calls():
    """Task 8, the first real use of M07's projection -> view model -> emitter
    split: shapes/shape_fields become a Mermaid class diagram, and each
    endpoint's descriptor becomes either a contract table (an object payload)
    or an inline label (a scalar, or a collection of one)."""
    report = ResolveReport(
        facts_loaded=5,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "POST",
                "path": "/v1/orders",
                "handler": "s maven c 1 com/acme/C#create().",
                "resolution": "resolved",
                "evidence": "compiler",
                "request_shape": json.dumps(
                    {
                        "wire_type": "object",
                        "wire_format": "",
                        "nullable": False,
                        "shape_id": "com/acme/orders/contracts/OrderRequest#",
                    }
                ),
                "response_shape": json.dumps(
                    {
                        "wire_type": "array",
                        "wire_format": "",
                        "nullable": False,
                        "item": {
                            "wire_type": "object",
                            "wire_format": "",
                            "nullable": False,
                            "shape_id": "com/acme/orders/contracts/OrderView#",
                        },
                    }
                ),
            },
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "POST",
                "path": "/billing/invoices",
                "caller": "s maven c 1 com/acme/BillingClient#create().",
                "peer": "billing",
                "resolution": "resolved",
                "evidence": "compiler",
            },
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "GET",
                "path": "/v1/inventory/levels",
                "caller": "s maven c 1 com/acme/InventoryClient#levels().",
                "peer": None,
                "resolution": "resolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 2, "partial_documents": 0},
        shapes=[
            {
                "shape_id": "com/acme/orders/contracts/OrderRequest#",
                "content_hash": "md5:1",
                "open": False,
            },
        ],
    )
    shape_fields = [
        {
            "shape_id": "com/acme/orders/contracts/OrderRequest#",
            "ordinal": 0,
            "wire_name": "customer_id",
            "wire_type": "string",
            "wire_format": "",
            "required": True,
            "nullable": False,
            "resolution": "resolved",
            "evidence": "declared",
            "tags": "[]",
            "item": None,
        },
    ]
    text = render_module_document(MODULE, report, "a3f91c", shape_fields=shape_fields)
    assert "## Structure" in text
    assert "classDiagram" in text
    assert "class OrderRequest" in text
    assert "customer_id: string" in text
    assert "| customer_id | string | yes | no |" in text
    assert "array of object OrderView" in text
    assert "## Outbound endpoints" in text
    assert "/billing/invoices" in text
    assert "unresolved" in text  # the inventory base address is builder code


def test_outbound_row_with_no_path_renders_unresolved_in_the_endpoint_column():
    """A `uri(uriBuilder -> …)` call — InventoryWebClient#search in the
    fixture — is real HTTP with no readable path (Task 13, spec §5): the
    fluent engine records the call honestly rather than guessing at the
    literal inside the lambda, so `path` is NULL. The Endpoint column must
    say so rather than rendering the method beside a literal `None`."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "GET",
                "path": None,
                "caller": "s maven c 1 com/acme/orders/clients/InventoryWebClient#search(String).",
                "peer": None,
                "resolution": "unresolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert (
        "| `GET (unresolved)` | unresolved | "
        "`com/acme/orders/clients/InventoryWebClient#search(String).` | "
        "unresolved | unresolved |"
    ) in text


def test_outbound_row_with_no_method_renders_unresolved_in_the_endpoint_column():
    """The verb's own half of the same rule (final review, I2): a call whose
    `HttpMethod` argument arrives as a parameter derives with `method` NULL,
    and the column must say so in the same words the path already uses. A
    bare `None` beside a real path would read as a verb literally named
    None, and dropping the row would hide a call the module demonstrably
    makes."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "http",
                "direction": "outbound",
                "method": None,
                "path": "/billing/passed-verb",
                "caller": "s maven c 1 com/acme/orders/clients/BillingRestTemplate#relay(String).",
                "peer": None,
                "resolution": "unresolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert (
        "| `(unresolved) /billing/passed-verb` | none recorded | "
        "`com/acme/orders/clients/BillingRestTemplate#relay(String).` | "
        "unresolved | unresolved |"
    ) in text


def test_kafka_inbound_row_renders_verbless_with_no_unresolved_marker():
    """A protocol in the verbless set (Task 9) defines no verb, so its wire
    identity is `protocol path` — never a bare `None` standing in for a verb
    that was never there to begin with."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "kafka",
                "direction": "inbound",
                "method": None,
                "path": "order-events",
                "handler": "s maven c 1 com/acme/orders/listeners/OrderEventsListener#onMessage(String).",
                "resolution": "resolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert (
        "| `kafka order-events` | `OrderEventsListener#onMessage` | — → — | unresolved | resolved |"
    ) in text
    assert "(unresolved)" not in text


def test_a_graphql_root_operation_renders_protocol_verb_and_field():
    """2H design §1 / D06: `graphql query orders`.

    GraphQL is VERBED — its operation type is part of the wire identity, and a
    caller sending a mutation must not match a query — but its verb is not an
    HTTP method, so the protocol name has to be rendered too. A bare
    `query orders` names nothing in particular; `GET /v1/orders` does, which
    is why HTTP still renders without the prefix.
    """
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "graphql",
                "direction": "inbound",
                "method": "query",
                "path": "orders",
                "handler": "s maven c 1 com/acme/orders/graphql/OrderController#orders().",
                "resolution": "resolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "`graphql query orders`" in text
    assert "(unresolved)" not in text


def test_a_graphql_resolver_renders_verbless_without_an_unresolved_marker():
    """The other half of the same rule. A resolver implements a FIELD — it
    answers no operation — so its NULL method is an absence by design, not a
    verb the analysis failed to read, and `Type.field` is the whole identity.

    This is the case that makes `graphql` different from simply joining the
    verbed set: an HTTP row with no method genuinely is unread and must still
    say so (pinned by the test above this block), while this row must not.
    """
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "graphql",
                "direction": "inbound",
                "method": None,
                "path": "Order.lines",
                "handler": "s maven c 1 com/acme/orders/graphql/OrderController#lines(Order).",
                "resolution": "resolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "`graphql Order.lines`" in text
    assert "(unresolved)" not in text


def test_an_sse_row_renders_its_protocol_and_its_http_verb():
    """2H design §6 / D06: `sse GET /events/stream`.

    An SSE stream is a route a client GETs, so unlike every other protocol
    added this phase it is VERBED with an ordinary HTTP method — falling into
    the derived verbless half would silently drop a verb the row really has.
    It is also protocol-QUALIFIED, for the mirror image of GraphQL's reason:
    `query orders` names nothing without its protocol, while `GET
    /events/stream` names something *wrong* without it — an ordinary REST
    route, which is exactly the reading the reclassification exists to
    correct."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "sse",
                "direction": "inbound",
                "method": "GET",
                "path": "/events/stream",
                "handler": "s maven c 1 com/acme/orders/sse/OrderEventsController#stream().",
                "resolution": "resolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "`sse GET /events/stream`" in text
    assert "(unresolved)" not in text


def test_an_sse_row_with_no_verb_still_reports_the_gap():
    """The half that separates `sse` from `graphql` in the qualified set: a
    GraphQL resolver's NULL verb is an absence by design, an SSE row's is a
    verb the analysis failed to read. Reusing one set for both questions would
    have made this row quietly claim it was never supposed to have a method."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "sse",
                "direction": "inbound",
                "method": None,
                "path": "/events/stream",
                "handler": "s maven c 1 com/acme/orders/sse/OrderEventsController#stream().",
                "resolution": "resolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "`sse (unresolved) /events/stream`" in text


def test_kafka_row_with_null_path_renders_unresolved_identity():
    """The path half of a verbless identity is unresolved the same way an
    HTTP row's method or path is: named, never a bare `None`."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "kafka",
                "direction": "outbound",
                "method": None,
                "path": None,
                "caller": "s maven c 1 com/acme/orders/OrderEventsProducer#send(Order).",
                "peer": None,
                "resolution": "unresolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert (
        "| `kafka (unresolved)` | unresolved | "
        "`com/acme/orders/OrderEventsProducer#send(Order).` | unresolved | unresolved |"
    ) in text


def test_inbound_row_with_no_handler_renders_unresolved_in_the_handler_column():
    """The Handler column's own half of the same rule (final review, I1): a
    route the resolver could not map to a method — a cross-method row, or a
    functional route the fluent engine could not read — derives with
    `handler` NULL, and the column must say so rather than running
    `bare_descriptor(str(None))` and printing the literal word `None`, the
    same honesty the outbound table already gives a NULL peer."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/v1/orders",
                "handler": None,
                "resolution": "unresolved",
                "evidence": "compiler",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "| `GET /v1/orders` | unresolved | — → — | unresolved | unresolved |" in text


def test_a_schema_declared_row_with_no_handler_says_so_rather_than_unresolved():
    """2H Task 4's other half of the same column. `schema_operations` derives a
    row whose address the schema stated OUTRIGHT — `resolution: resolved` — and
    which names no code at all, because a schema never does and the wiring that
    would is deliberately not read.

    `unresolved` beside `resolved` would report a gap that does not exist, the
    same mistake `_wire_identity` already refuses to make for a GraphQL
    resolver's NULL verb. `none recorded` rather than `none`: the claim is
    about what this evidence carries, never that the service implements
    nothing. The row above keeps `unresolved` because its address really was
    unread — the two cases are told apart by the row's own columns, not by its
    protocol.
    """
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "graphql",
                "direction": "inbound",
                "method": "query",
                "path": "auditTrail",
                "handler": None,
                "caller": None,
                "resolution": "resolved",
                "evidence": "declared",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "| `graphql query auditTrail` | none recorded | — → — | unresolved | resolved |" in text


def test_messaging_gap_retires_and_both_lists_rotate_together():
    """The messaging-not-read gap closes now that annotation_driven reads
    Kafka/JMS/SQS/pub-sub catalogs: it drops from both lists at the same
    position (spec ruling I3), so the equal-length pairing in
    `test_every_machine_readable_gap_has_a_sentence_a_person_can_read` never
    masks a key that lost its sentence."""
    assert "messaging_endpoints_not_read" not in KNOWN_GAPS
    # Twelve became fourteen with 2G Task 7: the two boundaries the
    # parse-binding pass refuses to cross — a payload parsed past the
    # one-hop horizon, and a payload reaching two different parses — each
    # arrive with their own sentence in the same position. Nothing retired.
    #
    # Fourteen became seventeen when `## Traces` landed, and this is the
    # first ROTATION the rule was written for rather than a widening: TWO
    # keys retired by name — `sequence_diagrams_pending_call_graph` and
    # `call_graph_not_implemented`, both of which said the call graph does
    # not exist — and FIVE narrower ones took their place, because what is
    # still true of a trace is five separate things a reader can act on.
    assert "sequence_diagrams_pending_call_graph" not in KNOWN_GAPS
    assert "call_graph_not_implemented" not in KNOWN_GAPS
    assert not any("await the call graph" in gap for gap in _GAPS if "Reactive" not in gap)
    # Seventeen became sixteen with W27 (F5 §6.1), a retirement with nothing taking its
    # place: `merged_endpoints_keep_only_the_handlers_contract` said a path the module
    # both exposes and calls keeps only the handler's declared contract. There is no
    # merge to discard the client's any more — the two rows stand and each keeps its
    # own — so the gap is gone rather than narrowed.
    assert "merged_endpoints_keep_only_the_handlers_contract" not in KNOWN_GAPS
    assert not any("keeps only the handler" in gap for gap in _GAPS)
    # Sixteen became fifteen with W31 (F7 §8.1), and this is a RETIREMENT with nothing
    # taking its place: `trace_depth_is_bounded` said a trace stops at 64 edges, which
    # FR-6 says it should not. The walk is an explicit stack now and stops where the
    # evidence does — measured before removing it, the deepest trace across three real
    # repositories is 9 edges and none was ever truncated.
    assert "trace_depth_is_bounded" not in KNOWN_GAPS
    assert not any("bounded at 64" in gap for gap in _GAPS)
    # And one NARROWED rather than retiring: W30 classified terminals and left the key
    # alone, so the rename lands here in W31. Terminals are classified now, so
    # "trace terminals are unclassified" stopped being true while the sibling-module half
    # of the same sentence did not.
    assert "trace_terminals_are_unclassified_and_cross_module_stops_look_third_party" not in (
        KNOWN_GAPS
    )
    assert "cross_module_stops_look_third_party" in KNOWN_GAPS
    assert len(KNOWN_GAPS) == 15
    assert len(_GAPS) == 15
    assert not any("Messaging endpoints" in gap for gap in _GAPS)


def test_the_base_address_gap_retires_into_the_two_boundaries_that_remain():
    """2F Task 8: `client_base_addresses_not_resolved` retires — an
    imperatively-fed base address now climbs the field ladder to the
    configuration key behind it, so "base addresses are not resolved" would
    read as a gap where there is a capability. What is left is narrower and
    is named rather than allowed to vanish (spec §4's rotation): a base built
    by COMPUTATION reaches no key, and configuration written as code reaches
    no reader at all. Eleven becomes twelve because one key retires and two
    arrive, each with its own sentence in the same position."""
    assert "client_base_addresses_not_resolved" not in KNOWN_GAPS
    assert KNOWN_GAPS[1:3] == ["computed_base_addresses_not_traced", "config_as_code_not_read"]
    assert _GAPS[1].startswith("Base addresses built by computation")
    assert _GAPS[2].startswith("Configuration constructed in code")
    assert not any("configured in builder code" in gap for gap in _GAPS)


def test_inbound_media_column_joins_declared_lists():
    """The Media column reads `consumes → produces`, each side the JSON
    list's comma-joined members (Task 10, brief Step 1)."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "POST",
                "path": "/v1/orders/detailed",
                "handler": "s maven c 1 com/acme/C#createDetailed().",
                "resolution": "resolved",
                "evidence": "compiler",
                "consumes": '["application/json"]',
                "produces": '["application/json"]',
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert (
        "| `POST /v1/orders/detailed` | `C#createDetailed` | "
        "application/json → application/json | unresolved | resolved |"
    ) in text


def test_inbound_media_column_shows_a_dash_on_either_or_both_null_sides():
    """NULL means no declaration derivable, never a guessed default (spec
    §4) — the column must say `-` rather than silently going blank, on one
    side or both."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/v1/orders/{id}",
                "handler": "s maven c 1 com/acme/C#get().",
                "resolution": "resolved",
                "evidence": "compiler",
                "consumes": None,
                "produces": '["application/json"]',
            },
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/v1/orders",
                "handler": "s maven c 1 com/acme/C#list().",
                "resolution": "resolved",
                "evidence": "compiler",
                "consumes": None,
                "produces": None,
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert (
        "| `GET /v1/orders/{id}` | `C#get` | — → application/json | unresolved | resolved |"
    ) in text
    assert "| `GET /v1/orders` | `C#list` | — → — | unresolved | resolved |" in text


def test_coverage_section_names_environments_and_the_unresolved_key_with_its_reason():
    """2F Task 9, the renderer half of I-1's ledgered carry: the fixture's own
    `only.in.default` key resolves in `default` and reads `missing_key` in
    `prod` — D01's own "unresolved for prod, resolved for dev" example
    (`resolve/config.py`), so the line has to name the reason AND the
    environment, never a bare "unresolved"."""
    resolved_config = [
        {
            "key": "billing.url",
            "value": "http://billing.internal",
            "environment": "default",
            "unresolved_reason": None,
        },
        {
            "key": "only.in.default",
            "value": "yes",
            "environment": "default",
            "unresolved_reason": None,
        },
        {
            "key": "only.in.default",
            "value": None,
            "environment": "prod",
            "unresolved_reason": "missing_key",
        },
    ]
    text = render_module_document(MODULE, REPORT, "a3f91c", resolved_config=resolved_config)
    assert "Environments resolved: `default`, `prod`." in text
    assert "only.in.default — missing_key in prod" in text
    # The row that DID resolve must not also read as unresolved.
    assert "billing.url" not in text.split("## Coverage", 1)[1].split("## Structure", 1)[0]


def test_coverage_section_is_honest_about_no_environments_and_no_unresolved_keys():
    text = render_module_document(MODULE, REPORT, "a3f91c")
    assert "Environments resolved: none." in text
    assert "Configuration keys unresolved: none." in text
    # The lead-in (F2, review round 1) always renders, even where the list
    # under it is empty — the same NFR-7 "looked and found nothing" rule
    # every other section in this document follows.
    assert (
        "Unresolved endpoint derivations — across every engine, whatever "
        "their evidence, not configuration alone:\n- None."
    ) in text


def test_coverage_section_names_an_unresolved_config_join_derivation_by_catalog_and_site():
    """2F Task 9 / I-1: a config_join engine's own unresolved rows — a
    missing binding key (a bean method exists, no key names it) and a
    composed `pipeA|pipeB` selection (no single bean at all) — are named by
    the catalog that derived them, since neither the key nor the composed
    expression is a column any row carries (Task 7 review's own finding:
    there is no engine-to-report channel)."""
    report = ResolveReport(
        facts_loaded=2,
        endpoints=[
            {
                "protocol": "kafka",
                "direction": "inbound",
                "method": None,
                "path": None,
                "handler": "s maven c 1 com/acme/orders/Bindings#orphanConsumer(sig_1).",
                "caller": None,
                "resolution": "unresolved",
                "evidence": "compiler",
                "catalog_id": "spring-cloud-stream",
            },
            {
                "protocol": "kafka",
                "direction": "inbound",
                "method": None,
                "path": None,
                "handler": None,
                "caller": None,
                "resolution": "unresolved",
                "evidence": "compiler",
                "catalog_id": "spring-cloud-stream",
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    # F2, review round 1: the list is a disclosed superset — every engine's
    # own unresolved rows land here, not config_join's alone — and the page
    # itself says so, not only the docstring.
    assert (
        "Unresolved endpoint derivations — across every engine, whatever "
        "their evidence, not configuration alone:"
    ) in text
    assert (
        "Unresolved endpoint derivation: `spring-cloud-stream` — "
        "handler `com/acme/orders/Bindings#orphanConsumer(sig_1).`."
    ) in text
    assert (
        "Unresolved endpoint derivation: `spring-cloud-stream` — a composed selection expression."
    ) in text


def test_structure_and_outbound_sections_state_looked_and_found_nothing():
    """NFR-7: a section whose machinery exists but found nothing is empty and
    present, never absent — distinct from a gap, which says the machinery
    itself is missing."""
    empty_report = ResolveReport(facts_loaded=0, endpoints=[], coverage={})
    text = render_module_document(MODULE, empty_report, "a3f91c")
    assert "## Structure" in text
    assert "None derived." in text
    assert "## Outbound endpoints" in text
    assert "None found." in text


# --- Opt-in library extraction (2I Task 6) -------------------------------

_LIBRARY_ROW = {
    "protocol": "soap",
    "direction": "outbound",
    "method": None,
    "path": "{http://billing.example.com/ws}stubCharge",
    "handler": None,
    "caller": "s maven com.example/orders-soap-client 1 com/example/billing/BillingPort#charge().",
    "peer": None,
    "resolution": "resolved",
    "evidence": "compiler",
}
_LIBRARY_SYMBOLS = [
    {
        "symbol": (
            "s maven com.example/orders-soap-client 1 com/example/billing/BillingPort#charge()."
        ),
        "origin": "com.example:orders-soap-client",
    }
]


def _report_with(row: dict[str, object]) -> ResolveReport:
    return ResolveReport(
        facts_loaded=42,
        endpoints=[row],
        coverage={"documents": 4, "partial_documents": 0},
        shapes=[],
        unexpanded_types=(),
    )


def test_a_row_a_library_contributed_says_which_library():
    """An endpoint derived from an extracted jar is otherwise indistinguishable
    from one this module's own code declares — same table, same resolution —
    and the difference is what a reader has to know: the operation is real, and
    nothing in this repository declares it."""
    text = render_module_document(
        MODULE, _report_with(_LIBRARY_ROW), "a3f91c", library_symbols=_LIBRARY_SYMBOLS
    )
    assert "- `soap {http://billing.example.com/ws}stubCharge`" in text
    assert "  - Via: `com.example:orders-soap-client`" in text


def test_a_row_the_module_itself_declares_carries_no_attribution():
    """The mirror image, and the pin that keeps the mark meaningful: with no
    library symbols to join against, the same row renders exactly as it did
    before this existed. A `Via:` on every row would say nothing."""
    text = render_module_document(MODULE, _report_with(_LIBRARY_ROW), "a3f91c")
    assert "Via:" not in text


def test_a_library_that_resolved_to_nothing_is_named_among_the_gaps():
    """FR-17, the same rule an uncovered source keeps: a coordinate nobody
    could resolve is the difference between "this module calls nothing through
    that library" and "nobody looked", and only the name says which dependency
    to build or install to close it."""
    module = replace(MODULE, libraries_not_resolved=("com.example:missing-client",))
    text = render_module_document(module, REPORT, "a3f91c")
    assert (
        "- Not resolved, so nothing above accounts for it: library `com.example:missing-client`."
        in text
    )


def test_metadata_names_every_library_that_resolved_to_nothing(tmp_path: Path):
    """Carried on metadata.json rather than re-derived at render time, the way
    every other analyze-side gap is: `render` never re-runs detection, so a
    coordinate that resolved to nothing would otherwise vanish from the
    document it was recorded for."""
    module = replace(MODULE, libraries_not_resolved=("com.example:missing-client",))
    write_metadata(tmp_path / "metadata.json", module, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["libraries_not_resolved"] == ["com.example:missing-client"]


_LIBRARY_CALLER = (
    "s maven com.example/orders-soap-client 1 com/example/billing/BillingPort#charge()."
)


def test_a_both_row_this_module_handles_is_locally_declared_and_carries_no_attribution():
    """RULED. A merged `both` row keeps the HANDLER's declaration and carries
    the caller onto it (D02 §3) — so a path this module serves is locally
    declared even when the client that calls it came out of a jar. Attributing
    it to the library would hand this module's own endpoint to a dependency,
    which is the opposite of what the marking exists to say. The attribution
    keys on the surviving evidence, and the handler is it."""
    row = {
        **_LIBRARY_ROW,
        "direction": "both",
        "handler": "s maven com.acme/orders-service 1 com/acme/O#serve().",
        "caller": _LIBRARY_CALLER,
    }
    text = render_module_document(
        MODULE, _report_with(row), "a3f91c", library_symbols=_LIBRARY_SYMBOLS
    )
    assert "Via:" not in text


def test_a_both_row_with_no_handler_still_names_the_library_that_derived_it():
    """The other side of the same rule, so it is a rule and not a filter that
    happens to say no: with no handler there IS no local declaration, and the
    caller becomes the deriving side."""
    row = {**_LIBRARY_ROW, "direction": "both", "handler": None, "caller": _LIBRARY_CALLER}
    text = render_module_document(
        MODULE, _report_with(row), "a3f91c", library_symbols=_LIBRARY_SYMBOLS
    )
    assert text.count("  - Via: `com.example:orders-soap-client`") == 1


def test_an_attribution_is_stated_once_per_identity_not_once_per_section():
    """A `both` row is listed in BOTH endpoint tables — it is one wire this
    module exposes and calls — so an attribution written under the inbound
    table must not be written again under the outbound one. The same finding
    twice reads as two.

    The detail block's own header still carries the wire identity (fix
    round 1, MEDIUM 1 restores it beside the full symbol — or, as here with
    no handler, beside the fallback text), so the header bullet itself is
    once again the thing to check for dedup, the same way it always was."""
    row = {**_LIBRARY_ROW, "direction": "both", "handler": None, "caller": _LIBRARY_CALLER}
    text = render_module_document(
        MODULE, _report_with(row), "a3f91c", library_symbols=_LIBRARY_SYMBOLS
    )
    assert text.count("- `soap {http://billing.example.com/ws}stubCharge` — unresolved") == 1


def test_a_library_that_could_not_be_scanned_is_named_beside_one_that_did_not_resolve():
    """Two lists, because they fail at two stages and are closed by two
    different actions: nothing resolved the coordinate to an archive (declare
    it, pin the version, install it) versus the archive was found and could not
    be read (it is corrupt). One list would leave a reader to work out which
    from the reason text alone.

    The reason renders as prose beside the coordinate rather than inside the
    backticks: typesetting a sentence as an identifier is how a document
    teaches its reader to skip it."""
    module = replace(
        MODULE,
        libraries_not_resolved=(
            "com.example:missing: this module's pom.xml declares no such dependency",
        ),
    )
    text = render_module_document(
        module,
        REPORT,
        "a3f91c",
        libraries_not_scanned=("com.example:broken: extractor failed: bad magic",),
    )
    assert (
        "- Not resolved, so nothing above accounts for it: library `com.example:missing` "
        "— this module's pom.xml declares no such dependency." in text
    )
    assert (
        "- Not scanned, so nothing above accounts for it: library `com.example:broken` "
        "— extractor failed: bad magic." in text
    )


def test_metadata_keeps_the_two_library_gap_lists_apart(tmp_path: Path):
    module = replace(MODULE, libraries_not_resolved=("com.example:missing: no such dependency",))
    write_metadata(
        tmp_path / "metadata.json",
        module,
        REPORT,
        SCANNERS,
        "a3f91c",
        libraries_not_scanned=("com.example:broken: unreadable",),
    )
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["libraries_not_resolved"] == ["com.example:missing: no such dependency"]
    assert written["libraries_not_scanned"] == ["com.example:broken: unreadable"]


def test_the_document_strips_url_userinfo_from_both_address_columns():
    """The render exit (2K design §1). A rendered document is shared — pasted
    into a ticket, committed beside the code — so the two columns that can
    carry a whole address carry it without its credential. `path` reaches the
    Endpoint column through `_wire_identity`; `peer` is its own cell, and both
    are the same 2I unsplit-expression shape."""
    report = replace(
        REPORT,
        endpoints=[
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "GET",
                "path": "https://svc:s3cret@billing.internal/invoices",
                "handler": None,
                "caller": "s maven c 1 com/acme/BillingClient#invoices().",
                "peer": "https://svc:s3cret@billing.internal",
                "resolution": "resolved",
                "evidence": "compiler",
            }
        ],
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "s3cret" not in text
    assert "`GET https://billing.internal/invoices`" in text
    assert "| https://billing.internal |" in text


def test_the_document_leaves_an_address_expression_exactly_as_the_row_carries_it():
    """The negative half, and the 2I ruling restated: a `${...}` peer is a
    REFERENCE to a value, never the value, so there is nothing in it to mask —
    and masking it would delete the only thing the row says about where it
    points."""
    report = replace(
        REPORT,
        endpoints=[
            {
                "protocol": "soap",
                "direction": "outbound",
                "method": None,
                "path": "{http://orders.example.com/ws}placeOrderRequest",
                "handler": None,
                "caller": "s maven c 1 com/acme/BillingSoapClient#place().",
                "peer": "${soap.billing.uri}",
                "resolution": "resolved",
                "evidence": "compiler",
            }
        ],
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "| ${soap.billing.uri} |" in text
    assert "`soap {http://orders.example.com/ws}placeOrderRequest`" in text


def test_a_repo_value_pattern_reaches_the_rendered_addresses_too():
    """`.sextant.yml`'s additions are not export-only: the composition root
    hands the SAME redactor to both exits, so a repo that knows the shape of
    its own secrets is protected in the document it shares as well as in the
    bundle it ships."""
    report = replace(
        REPORT,
        endpoints=[
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "GET",
                "path": "/v1/invoices?key=ACME_A1B2",
                "handler": None,
                "caller": "s maven c 1 com/acme/BillingClient#invoices().",
                "peer": "billing.internal",
                "resolution": "resolved",
                "evidence": "compiler",
            }
        ],
    )
    redactor = Redactor.from_rules(RedactionRules(value_patterns=(r"ACME_[A-Z0-9]{4}",)))
    text = render_module_document(MODULE, report, "a3f91c", redactor=redactor)
    assert f"`GET /v1/invoices?key={REDACTED}`" in text


def test_metadata_records_what_the_module_builds_against_and_which_release(tmp_path: Path):
    """F1. `metadata.json` is the one place a reader can see the CONDITIONS
    every framework rule in this run was applied under — a rule is true of a
    version, and until F1 the estate had no way to say which. The two keys are
    read together: `dependencies` is what resolved, and
    `dependencies_not_resolved` is why the rest did not, so a short map is
    never mistaken for a short build."""
    module = replace(
        MODULE,
        dependency_coordinates=("com.acme:unmanaged", "org.springframework:spring-web"),
        dependency_versions={"org.springframework:spring-web": "6.1.6"},
        dependencies_not_resolved=("com.acme:unmanaged: no version on the declaration",),
    )
    write_metadata(tmp_path / "metadata.json", module, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())

    assert written["module"]["dependencies"] == {"org.springframework:spring-web": "6.1.6"}
    assert written["dependencies_not_resolved"] == [
        "com.acme:unmanaged: no version on the declaration"
    ]


def test_metadata_writes_both_dependency_keys_even_when_nothing_was_recorded(tmp_path: Path):
    """The key never depends on whether this run had anything to put in it: an
    absent key reads as "no dependencies", which is a different and stronger
    claim than "none recorded" (the same distinction the dependency gate keeps
    between an empty list and no module fact at all)."""
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())

    assert written["module"]["dependencies"] == {}
    assert written["dependencies_not_resolved"] == []


def test_metadata_records_where_the_sources_live_so_the_index_can_open_one(tmp_path: Path):
    """F8 §9.3 (W35). The whole basis of placement, and it had no test at all: replacing
    the field with `[]` left 1,840 tests green while every `file` in every index quietly
    became null.

    A `document`'s `relative_path` is a package path, openable against nothing on its own;
    these are what it is relative TO. Recorded at analyze time because `export` reads what
    `analyze` left and never re-detects (M08), so a root the detector found then has to be
    written down then or it is gone.

    RELATIVE and POSIX-spelled, because a bundle travels: an absolute path names a
    directory that exists on exactly one computer.
    """
    module = dataclasses.replace(
        MODULE,
        source_roots=(
            Path("fixtures/orders-service/src/main/kotlin"),
            Path("fixtures/orders-service/src/main/java"),
        ),
    )

    write_metadata(tmp_path / "metadata.json", module, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())

    # Sorted (NFR-1), relative to the module root, forward slashes.
    assert written["module"]["source_roots"] == ["src/main/java", "src/main/kotlin"]


def test_a_module_declaring_no_source_root_records_an_empty_list(tmp_path: Path):
    """`[]`, never an absent key — the `render`/`index` precedent one file over. An absent
    key would make "this build declares none" indistinguishable from "this metadata
    predates the field", and the index would read both as "place nothing"."""
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())

    assert written["module"]["source_roots"] == []


def test_a_source_root_outside_the_module_is_dropped_rather_than_made_absolute(
    tmp_path: Path,
):
    """The one way a declared root is lost, stated rather than left to be discovered.

    A build may point a source root outside the module — a generated tree beside it, a
    shared directory — and there is no relative spelling of that which a bundle can carry
    portably. It is dropped, so the index simply does not place what lives there.
    """
    module = dataclasses.replace(
        MODULE,
        source_roots=(Path("fixtures/orders-service/src/main/java"), Path("/elsewhere/src")),
    )

    write_metadata(tmp_path / "metadata.json", module, REPORT, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())

    assert written["module"]["source_roots"] == ["src/main/java"]


def test_coverage_reports_how_much_was_understood_not_only_how_many_files(tmp_path: Path):
    """FR-17 clause 3 (F8 §9.5, W38). `coverage` carried `{documents, partial_documents}` —
    how many files were OPENED — and nothing about how much of the call graph was read.

    **The reach rate leads and the dispatch distribution follows**, because the second
    alone misleads: `resolution` reads 100% `resolved` on two of the four measured corpora,
    since naming the target a compiler wrote is easy and reading its BODY is the work. A
    reader shown only that would take a blind analysis for a complete one.
    """
    report = dataclasses.replace(
        REPORT,
        coverage={
            "documents": 4,
            "partial_documents": 0,
            "reach": {"body_read": 465, "boundary": 968},
            "resolution": {"resolved": 1431, "narrowed": 2},
            "method_resolution": {"declared_here": 191, "owner_not_scanned": 318},
        },
    )

    text = render_module_document(MODULE, report, "a3f91c")

    assert "Calls whose callee body this workspace read: 465 of 1433 (32%)" in text
    assert "Dispatch, by outcome (call edges): narrowed 2, resolved 1431." in text
    assert "Method lookup, by outcome (methods): declared_here 191, owner_not_scanned 318." in text


def test_a_module_with_no_call_graph_reports_no_percentage_of_nothing(tmp_path: Path):
    """Absent, not `0 of 0`. A module with no edges has nothing to be understood, and a
    percentage of nothing reads as a failure — NFR-7's "looked and found nothing" is for
    things that were looked FOR."""
    report = dataclasses.replace(
        REPORT, coverage={"documents": 4, "partial_documents": 0, "reach": {}}
    )

    text = render_module_document(MODULE, report, "a3f91c")

    assert "Calls whose callee body" not in text
    assert "Documents analysed: 4" in text


# --- `Fails with:` — the declared and observed exceptions pairing (G-74, Task 17) -------

_THROWS_HANDLER = "s maven c 1 com/acme/C#exits()."

_THROWS_ROW = {
    "protocol": "http",
    "direction": "inbound",
    "method": "GET",
    "path": "/v1/exits",
    "handler": _THROWS_HANDLER,
    "resolution": "resolved",
    "evidence": "compiler",
    "handler_signature": json.dumps({"throws": ["java/io/IOException#"]}),
}


def test_a_handlers_declared_exception_renders_as_fails_with():
    """The DECLARED half alone (JVMS 4.7.5, `Signature.throws`), read off the same
    `handler_signature` JSON the Request/Response lines already parse — no reachable
    throw exit at all, so the line names only what the handler's own signature says."""
    text = render_module_document(MODULE, _report_with(_THROWS_ROW), "a3f91c")
    assert "  - Fails with: `IOException` (declared)" in text


def test_a_reachable_throw_exit_joins_the_same_line_after_the_declared_half():
    """The OBSERVED half (`G-52`'s throw-exit call sites, joined through
    `reachability` in `reachable_throws`, `G-74`): declared first, both sorted."""
    reachable = [
        {
            "root": _THROWS_HANDLER,
            "caller": _THROWS_HANDLER,
            "ordinal": 0,
            "target": "java/lang/IllegalStateException#",
        }
    ]
    text = render_module_document(
        MODULE, _report_with(_THROWS_ROW), "a3f91c", reachable_throws=reachable
    )
    assert "  - Fails with: `IOException` (declared), `IllegalStateException` (thrown)" in text


def test_a_throw_site_whose_target_was_unread_says_so_in_words():
    """A rethrow whose type lives in the try-catch table nothing here reads (`G-52`)
    still contributes a reachable exit — NULL target and all — and this renders the
    same words `_call_cell` already settled on for it (`bfece6f`), never the type."""
    row = {**_THROWS_ROW, "handler_signature": None}
    reachable = [{"root": _THROWS_HANDLER, "caller": _THROWS_HANDLER, "ordinal": 0, "target": None}]
    text = render_module_document(MODULE, _report_with(row), "a3f91c", reachable_throws=reachable)
    assert "  - Fails with: (type unread) (thrown)" in text


def test_no_fails_with_line_where_neither_half_has_anything():
    """Nothing declared and nothing reachable renders no line at all — the same
    restraint `_via_entry` keeps for a row with no library to name."""
    text = render_module_document(MODULE, REPORT, "a3f91c")
    assert "Fails with" not in text


def test_a_temporal_row_renders_its_kind_and_an_eventbus_row_does_not():
    """`_VERBLESS_PROTOCOLS` is COMPUTED as the complement of `_VERBED_PROTOCOLS` over
    every `Protocol` member (spec 2026-09-22 §1c), and that is what this test notices —
    exactly one thing, not two.

    The rationale here used to read the other way round, as though the eventbus half
    guarded something. It cannot: a member in neither list is in the verbless half by
    construction, so `"eventbus" in _VERBLESS_PROTOCOLS` passes whether or not anyone ever
    classified it. `"temporal" in _VERBED_PROTOCOLS` is the whole assertion — the eventbus
    line is documentation of the pair, kept because deleting it would read as a claim that
    eventbus was never considered."""
    from sextant.egress.render.document import _VERBED_PROTOCOLS, _VERBLESS_PROTOCOLS

    assert "temporal" in _VERBED_PROTOCOLS
    assert "eventbus" in _VERBLESS_PROTOCOLS
