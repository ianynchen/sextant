import json
from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.egress.render.document import _GAPS, render_module_document
from sextant.egress.render.metadata import KNOWN_GAPS, write_metadata

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
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, "asm", "9.7", "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["provenance"]["commit"] == "a3f91c"
    assert written["coverage"]["documents"] == 4


def test_metadata_names_every_type_expansion_could_not_open(tmp_path: Path):
    """The count says how much was expanded; only the names say what was not,
    and a count cannot be acted on (FR-17, the same rule as `uncovered`)."""
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, "asm", "9.7", "a3f91c")
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
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, "asm", "9.7", "a3f91c", unread)
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
    write_metadata(tmp_path / "metadata.json", MODULE, report, "asm", "9.7", "a3f91c")
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
        "`com/acme/orders/clients/InventoryWebClient#search(String).` | unresolved |"
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
        "| `(unresolved) /billing/passed-verb` | unresolved | "
        "`com/acme/orders/clients/BillingRestTemplate#relay(String).` | unresolved |"
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
        "| `kafka order-events` | "
        "`com/acme/orders/listeners/OrderEventsListener#onMessage(String).` | - → - | resolved |"
    ) in text
    assert "(unresolved)" not in text


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
        "`com/acme/orders/OrderEventsProducer#send(Order).` | unresolved |"
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
    assert "| `GET /v1/orders` | unresolved | - → - | unresolved |" in text


def test_messaging_gap_retires_and_both_lists_rotate_together():
    """The messaging-not-read gap closes now that annotation_driven reads
    Kafka/JMS/SQS/pub-sub catalogs: it drops from both lists at the same
    position (spec ruling I3), so the equal-length pairing in
    `test_every_machine_readable_gap_has_a_sentence_a_person_can_read` never
    masks a key that lost its sentence."""
    assert "messaging_endpoints_not_read" not in KNOWN_GAPS
    assert len(KNOWN_GAPS) == 12
    assert len(_GAPS) == 12
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
        "| `POST /v1/orders/detailed` | `com/acme/C#createDetailed().` | "
        "application/json → application/json | resolved |"
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
        "| `GET /v1/orders/{id}` | `com/acme/C#get().` | - → application/json | resolved |"
    ) in text
    assert "| `GET /v1/orders` | `com/acme/C#list().` | - → - | resolved |" in text


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
