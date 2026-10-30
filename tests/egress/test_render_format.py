import json
from pathlib import Path

import pytest

from sextant.application.ports.detector import ModuleModel
from sextant.application.ports.scanner import ScannerProvenance
from sextant.application.resolve.pipeline import ResolveReport
from sextant.egress.render.document import render_module_document
from sextant.egress.render.metadata import write_metadata

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


def _endpoint(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "protocol": "http",
        "direction": "inbound",
        "method": "GET",
        "path": "/v1/orders",
        "handler": "s maven c 1 com/acme/C#list().",
        "resolution": "resolved",
        "evidence": "compiler",
    }
    base.update(overrides)
    return base


def test_a_resolved_format_renders_plain():
    """Rung 1-3's own tier (2G design §5): declared or configured evidence
    named the wire outright, so the column prints the format with no
    hedge."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[_endpoint(format="protobuf", format_resolution="resolved")],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "| `GET /v1/orders` | `C#list` | — → — | protobuf | resolved |" in text


def test_a_narrowed_format_renders_assumed():
    """Rung 4-5's own tier: only a schema's own type or a framework default
    suggested the wire, never a declaration — the design's first rule (2G
    design §5) is that an assumed format must never LOOK observed, so the
    column has to say so rather than printing the bare format string."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[_endpoint(format="protobuf", format_resolution="narrowed")],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert ("| `GET /v1/orders` | `C#list` | — → — | protobuf (assumed) | resolved |") in text


def test_a_null_format_renders_unresolved():
    """Rung 6: nothing described the channel at all. The same
    NULL-renders-`unresolved` rule the Handler column already keeps (2E
    precedent) — never a bare `None`."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[_endpoint(format=None, format_resolution="unresolved")],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "| `GET /v1/orders` | `C#list` | — → — | unresolved | resolved |" in text


@pytest.mark.parametrize(
    "format_resolution",
    ["unresolved", "partial"],
    ids=["merged-row-weaker-marker", "partial-hypothetical"],
)
def test_a_present_format_beside_any_non_resolved_marker_still_hedges(format_resolution):
    """`format_resolution` is the authority on trust (schema.sql's own
    comment), and the rendered document carries no separate trust column —
    this Format cell is the ONLY place a reader ever sees it. So `resolved`
    is the only marker that ever prints unhedged; printing a non-resolved
    marker plain would make an unresolved-trust value typographically
    identical to a resolved one, exactly what "an assumed format must never
    look observed" (2G design §5) forbids (task 8 review round 1).

    Two schema-valid cases: `unresolved` is the `merge_endpoints.sql`
    exception, where a merged row keeps the surviving format beside the
    WEAKER of its two halves' markers (schema.sql's own note), so a merged
    row may carry `(protobuf, unresolved)`. `partial` is D00 §4's closed
    resolution set's fourth member — no pass in this pipeline emits it for
    `format_resolution` today, but the renderer must be correct for any
    schema-valid row, not only the ones live code currently produces."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[_endpoint(format="protobuf", format_resolution=format_resolution)],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert ("| `GET /v1/orders` | `C#list` | — → — | protobuf (assumed) | resolved |") in text


# --- readability rulings from the JHipster field run (2M design §5c) ------


def test_the_handler_column_shows_the_short_human_spelling_not_the_machine_identity():
    """The JHipster field run's own example: a package path, an opaque
    `sig_` hash and a stray trailing `.` in every row is machine identity,
    not something a reader parses at a glance. The column now shows the
    owning type's simple name and the method name alone."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            _endpoint(
                handler=(
                    "s maven c 1 io/github/jhipster/sample/web/rest/"
                    "UserResource#deleteUser(sig_4a71b976)."
                )
            )
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "| `GET /v1/orders` | `UserResource#deleteUser` |" in text
    assert "sig_4a71b976" not in text.split("## Inbound endpoints", 1)[1].split("\n\n", 1)[0]


def test_every_inbound_endpoint_carries_the_full_symbol_in_its_own_detail_block():
    """Moved, not deleted: the full symbol the Handler column no longer
    spells out lives in the endpoint's own detail block instead, and EVERY
    inbound endpoint gets one now — not only the ones with a `Via`/
    `Request`/`Response` line to hang under it (adversarial review C3).

    The header carries BOTH the wire identity and the full symbol (fix
    round 1, MEDIUM 1): the identity alone could not otherwise distinguish
    which endpoint a handler-less block belongs to."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[_endpoint()],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "- `GET /v1/orders` — `com/acme/C#list().`" in text


def test_two_overloads_sharing_a_short_spelling_stay_distinguishable_in_their_details():
    """Synthetic overload: two handlers in the same class with the same
    method name (differing only by the compiler's `sig_` disambiguator)
    collide in the table's short spelling — the ruled consequence spec §5c
    states outright — but each keeps its own full symbol in its own detail
    block, so a reader can still tell the two apart there."""
    report = ResolveReport(
        facts_loaded=2,
        endpoints=[
            _endpoint(
                path="/v1/orders",
                handler="s maven c 1 com/acme/C#save(sig_1111aaaa).",
            ),
            _endpoint(
                path="/v1/orders/{id}",
                method="PUT",
                handler="s maven c 1 com/acme/C#save(sig_2222bbbb).",
            ),
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert text.count("| `C#save` |") == 2
    assert "- `GET /v1/orders` — `com/acme/C#save(sig_1111aaaa).`" in text
    assert "- `PUT /v1/orders/{id}` — `com/acme/C#save(sig_2222bbbb).`" in text


def test_a_handler_less_row_carries_the_same_fallback_in_its_detail_block():
    """A row with nothing to move still gets a block — its header names the
    endpoint by its wire identity and then reads the same fallback text the
    Handler column shows, never a bare `- unresolved` naming no endpoint at
    all (fix round 1, MEDIUM 1)."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[_endpoint(handler=None, resolution="unresolved")],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "| `GET /v1/orders` | unresolved |" in text
    assert "- `GET /v1/orders` — unresolved" in text


def test_an_empty_shape_renders_one_line_with_no_header_only_table():
    """NFR-7's empty-section discipline extended to a shape table: a shape
    query that came back with no fields renders one line, never a
    `| Field | Type | Required | Nullable |` header with nothing under it."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            _endpoint(
                method="POST",
                response_shape=json.dumps(
                    {
                        "wire_type": "object",
                        "wire_format": "",
                        "nullable": False,
                        "shape_id": "com/acme/orders/contracts/Empty#",
                    }
                ),
            )
        ],
        coverage={"documents": 1, "partial_documents": 0},
        shapes=[
            {"shape_id": "com/acme/orders/contracts/Empty#", "content_hash": "md5:1", "open": False}
        ],
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "- Response: none recorded" in text
    assert "| Field | Type | Required | Nullable |" not in text


def test_a_shape_named_by_two_endpoints_is_emitted_once_under_shapes():
    """Repeated shape tables (2M design §5c): a shape two endpoints both
    return is not tabulated twice — it lives once, under `### Shapes`, and
    each endpoint's own entry names it instead of repeating its table."""
    descriptor = json.dumps(
        {
            "wire_type": "object",
            "wire_format": "",
            "nullable": False,
            "shape_id": "com/acme/orders/contracts/OrderView#",
        }
    )
    report = ResolveReport(
        facts_loaded=2,
        endpoints=[
            _endpoint(path="/v1/orders", response_shape=descriptor),
            _endpoint(path="/v1/orders/{id}", response_shape=descriptor),
        ],
        coverage={"documents": 1, "partial_documents": 0},
        shapes=[
            {
                "shape_id": "com/acme/orders/contracts/OrderView#",
                "content_hash": "md5:1",
                "open": False,
            }
        ],
    )
    shape_fields = [
        {
            "shape_id": "com/acme/orders/contracts/OrderView#",
            "ordinal": 0,
            "wire_name": "id",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", shape_fields=shape_fields)
    assert "### Shapes" in text
    assert text.count("- Response: OrderView") == 2
    assert text.count("| id | string | yes | no |") == 1
    assert text.count("- `OrderView`") == 1
    # Fix round 1, NIT: exactly ONE blank line between the heading and its
    # first entry — the heading's own trailing blank plus the entry's own
    # (formerly hardcoded) leading blank used to stack into two.
    assert "### Shapes\n\n- `OrderView`" in text
    assert "### Shapes\n\n\n" not in text


def test_two_shapes_sharing_a_simple_name_get_disambiguated_entries():
    """Fix round 1, MEDIUM 2: `com/a/Order#` and `com/b/Order#` share the
    simple name `Order` — left alone, `### Shapes` would carry two
    indistinguishable `Order` entries and every citation would read as
    ambiguous as to which one it names. Both fall back to their own full id
    (trailing `#` stripped) instead, which is already guaranteed unique, so
    a reader — and, in HTML, a link's own href
    (`test_two_shapes_sharing_a_simple_name_get_distinct_anchors_and_links`
    in test_render_html.py) — can always tell the two apart."""
    descriptor_a = json.dumps(
        {"wire_type": "object", "wire_format": "", "nullable": False, "shape_id": "com/a/Order#"}
    )
    descriptor_b = json.dumps(
        {"wire_type": "object", "wire_format": "", "nullable": False, "shape_id": "com/b/Order#"}
    )
    report = ResolveReport(
        facts_loaded=2,
        endpoints=[
            _endpoint(path="/a/orders", response_shape=descriptor_a),
            _endpoint(path="/b/orders", response_shape=descriptor_b),
        ],
        coverage={"documents": 1, "partial_documents": 0},
        shapes=[
            {"shape_id": "com/a/Order#", "content_hash": "md5:1", "open": False},
            {"shape_id": "com/b/Order#", "content_hash": "md5:2", "open": False},
        ],
    )
    shape_fields = [
        {
            "shape_id": "com/a/Order#",
            "ordinal": 0,
            "wire_name": "a_field",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        },
        {
            "shape_id": "com/b/Order#",
            "ordinal": 0,
            "wire_name": "b_field",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        },
    ]
    text = render_module_document(MODULE, report, "a3f91c", shape_fields=shape_fields)
    assert "- `com/a/Order`" in text
    assert "- `com/b/Order`" in text
    assert "- `Order`" not in text
    assert "- Response: com/a/Order" in text
    assert "- Response: com/b/Order" in text


def test_media_glyph_forms_the_legend_states():
    """The exact two forms the legend under the table describes: one empty
    side, and both — one glyph, one meaning, never a bare hyphen."""
    report = ResolveReport(
        facts_loaded=2,
        endpoints=[
            _endpoint(path="/v1/orders", consumes='["application/json"]', produces=None),
            _endpoint(path="/v1/orders/{id}", produces=None, consumes=None),
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert "| application/json → — |" in text
    assert "| — → — |" in text


def test_the_media_legend_appears_once_directly_under_the_inbound_table():
    """Fix round 1, HIGH: a paragraph landing IMMEDIATELY under a pipe table
    with no blank line between them is read by GFM as one more row of the
    table itself (verified against cmark-gfm) — four empty cells a reader
    never wrote. The legend must be separated from the table by a real blank
    line, not merely follow it somewhere in the text: the substring-ordering
    checks below would have passed even on the broken, blank-less output, so
    this pins the literal adjacency a GFM parser actually keys on."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[_endpoint()],
        coverage={"documents": 1, "partial_documents": 0},
    )
    text = render_module_document(MODULE, report, "a3f91c")
    assert text.count("Media reads `consumes → produces`; `—` means none recorded.") == 1
    # The exact, literal table-row-then-blank-then-legend adjacency: no line
    # of the table's own body sits directly against the legend text.
    assert (
        "| `GET /v1/orders` | `C#list` | — → — | unresolved | resolved |\n"
        "\n"
        "Media reads `consumes → produces`; `—` means none recorded.\n"
    ) in text
    table_end = text.index("| `GET /v1/orders` |")
    legend_index = text.index("Media reads `consumes → produces`")
    assert table_end < legend_index < text.index("- `GET /v1/orders` — `com/acme/C#list().`")


def test_the_open_questions_section_lists_wire_identity_question_and_candidates():
    """2G design §8: a human reads the 2K inbox in the document itself. Both
    question kinds are exercised because their candidates carry different
    keys (2G design §6) and the renderer switches on the kind rather than
    guessing a shared shape."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "http",
            "method": "GET",
            "path": "/v1/orders/ambiguous",
            "question": "format_conflict",
            "candidates": json.dumps(
                [
                    {"format": "json", "seen_in": "consumes", "why": "application/json"},
                    {"format": "xml", "seen_in": "produces", "why": "application/xml"},
                ]
            ),
            "evidence": "rung 2 (declared media): json from consumes, xml from produces",
        },
        {
            "protocol": "sqs",
            "method": None,
            "path": "order-intake",
            "question": "payload_binding",
            "candidates": json.dumps(
                [
                    {
                        "payload_type": "com/acme/OrderProto#",
                        "hops": "1",
                        "seen_in": "OrderRelay#relay(byte[]).",
                        "why": "parseFrom",
                    }
                ]
            ),
            "evidence": "payload parsed beyond the one-hop horizon",
        },
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert "## Open questions" in text
    assert (
        "- `GET /v1/orders/ambiguous` — format_conflict: "
        "json from consumes (application/json); xml from produces (application/xml)"
    ) in text
    assert (
        "- `sqs order-intake` — payload_binding: "
        "com/acme/OrderProto# in OrderRelay#relay(byte[]). via parseFrom at 1 hop(s)"
    ) in text


def test_a_service_identity_question_renders_the_flagged_class_and_reason():
    """Regression for the live bug: `_candidate_line` had no arm for
    `service_identity` even though three resolve engines
    (`supertype_derived`, `injected_client`, `annotation_driven.gaps`) file
    it, so any module with such a question raised `ValueError` at render.
    Candidate shape (`class`, `reason`) matches what those three engines
    actually put in `candidates`, not only what `open_questions.py`'s
    comment says."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "grpc",
            "method": None,
            "path": "com/acme/OrderServiceGrpc$OrderServiceImplBase.",
            "question": "service_identity",
            "candidates": json.dumps(
                [
                    {
                        "class": "com/acme/OrderServiceImpl",
                        "reason": "SERVICE_NAME constant unreadable",
                    }
                ]
            ),
            "evidence": "SERVICE_NAME constant unreadable",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert "## Open questions" in text
    assert (
        "- `(unresolved) com/acme/OrderServiceGrpc$OrderServiceImplBase.` — service_identity: "
        "com/acme/OrderServiceImpl: SERVICE_NAME constant unreadable"
    ) in text


def test_a_channel_destination_question_renders_the_channel_and_handler():
    """2O §5: the shape `spring-integration.yml` files, with the protocol
    column EMPTY — which is what it carries since OI-1 re-keyed the
    wire-identity rule on what a catalog derives. A channel is an in-process
    pipe and which broker it reaches is the question, so the catalog declares
    no protocol and the ledger row carries none.

    The identity is then the channel name alone. Without `_wire_identity`'s
    no-protocol arm this line reads `(unresolved) orders.inbound` — a verb
    reported as unread on a row that was never going to have one."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "",
            "method": None,
            "path": "orders.inbound",
            "question": "channel_destination",
            "candidates": json.dumps(
                [{"channel": "orders.inbound", "handler": "com/acme/Activator#handle(byte[])."}]
            ),
            "evidence": "no configuration key carries a Spring Integration channel's destination",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert "## Open questions" in text
    assert (
        "- `orders.inbound` — channel_destination: "
        "orders.inbound → com/acme/Activator#handle(byte[])."
    ) in text
    assert "(unresolved)" not in text


def test_an_environment_divergence_question_renders_the_key_and_per_environment_values():
    """2O §2b (Task 6, not yet shipped): pinned ahead of the writer for the
    same reason as `channel_destination` above."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "http",
            "method": "GET",
            "path": "/v1/orders",
            "question": "environment_divergence",
            "candidates": json.dumps(
                [
                    {
                        "key": "spring.data.rest.base-path",
                        "values": {"prod": "/v1", "staging": "/v2"},
                    }
                ]
            ),
            "evidence": "spring.data.rest.base-path differs between environments",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert "## Open questions" in text
    assert (
        "- `GET /v1/orders` — environment_divergence: "
        "spring.data.rest.base-path: prod=/v1, staging=/v2"
    ) in text


def test_the_open_questions_section_is_absent_when_the_ledger_is_empty():
    """Rendered only when rows exist (2G design §8) — the `## Catalogs
    skipped` precedent, not the NFR-7 "looked and found nothing" one this
    document keeps elsewhere: an empty 2K inbox is not itself a finding."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    text = render_module_document(MODULE, report, "a3f91c")
    assert "## Open questions" not in text


def test_a_declared_field_number_shows_beside_the_field_name():
    """2G design §8: declared-shape fields render their `field_number`,
    unobtrusively — the same parenthetical convention `wire_format` already
    uses beside `wire_type`."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            _endpoint(
                method="POST",
                request_shape=json.dumps(
                    {
                        "wire_type": "object",
                        "wire_format": "",
                        "nullable": False,
                        "shape_id": "com/acme/orders/contracts/OrderRequest#",
                    }
                ),
            )
        ],
        coverage={"documents": 1, "partial_documents": 0},
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
            "wire_name": "total_amount",
            "field_number": 1,
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
    assert "| total_amount (1) | string | yes | no |" in text


def test_an_annotation_derived_field_with_no_number_renders_unchanged():
    """The other half of the same rule: a bytecode-derived field never
    carries a `field_number` (schema.sql's own NULL comment), so it must
    render exactly as it did before this task."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            _endpoint(
                method="POST",
                request_shape=json.dumps(
                    {
                        "wire_type": "object",
                        "wire_format": "",
                        "nullable": False,
                        "shape_id": "com/acme/orders/contracts/OrderRequest#",
                    }
                ),
            )
        ],
        coverage={"documents": 1, "partial_documents": 0},
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
            "wire_name": "customerId",
            "field_number": None,
            "wire_type": "string",
            "wire_format": "",
            "required": True,
            "nullable": False,
            "resolution": "resolved",
            "evidence": "compiler",
            "tags": "[]",
            "item": None,
        },
    ]
    text = render_module_document(MODULE, report, "a3f91c", shape_fields=shape_fields)
    assert "| customerId | string | yes | no |" in text


def test_metadata_carries_the_two_analyze_side_gap_lists(tmp_path: Path):
    """Task 4 left `schema_sources_not_compiled`/`descriptors_not_interpreted`
    on `AnalyzeResult` unrendered; this task surfaces them in metadata.json
    the same way `uncovered` already surfaces its own list — named in full,
    not counted, so each can be acted on (FR-17)."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    write_metadata(
        tmp_path / "metadata.json",
        MODULE,
        report,
        SCANNERS,
        "a3f91c",
        schema_sources_not_compiled=("broken.proto",),
        descriptors_not_interpreted=("pkg.Widget",),
    )
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["schema_sources_not_compiled"] == ["broken.proto"]
    assert written["descriptors_not_interpreted"] == ["pkg.Widget"]


def test_metadata_gap_lists_are_empty_by_default(tmp_path: Path):
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    write_metadata(tmp_path / "metadata.json", MODULE, report, SCANNERS, "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["schema_sources_not_compiled"] == []
    assert written["descriptors_not_interpreted"] == []


def test_a_binder_protocol_question_renders_the_binding_and_the_binder():
    """F2 §3.4's kind, and this test is the reason it has one at all: the whole
    suite passed with the arm disabled. `open_questions.py`'s own comment says
    the renderer is the ONLY switch on question kind, so an arm reading a key the
    writer does not produce raises `KeyError` on the first real module with an
    unmapped binder and nothing else would catch it — which is exactly the live
    bug `service_identity`'s own arm test records.

    `protocol` is EMPTY on purpose: a question reporting that a protocol was not
    read must not name one."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "",
            "method": None,
            "path": "orders-in-0",
            "question": "binder_protocol",
            "candidates": json.dumps([{"binding": "orders-in-0", "binder": "rocketmq"}]),
            "evidence": "the configured binder `rocketmq` is absent from binder_protocols",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert (
        "- `orders-in-0` — binder_protocol: orders-in-0: binder `rocketmq` maps to no protocol"
    ) in text
    assert "(unresolved)" not in text


def test_a_wired_channels_questions_render_their_own_reason():
    """Spec 2026-10-24 §3c. A SmallRye channel's candidates carry `reason`, and the
    rendered line is where a reader meets it — the trail (`evidence`) is not printed. Two
    connectors on the classpath each MAP to a protocol, so the `binder_protocol` arm's
    "maps to no protocol" would be false for them; and a wired row whose address is
    unread says why beside the channel and handler."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    unchosen = "`smallrye-amqp` is one of 2 inbound connectors in the dependency set"
    disagreeing = "`mp.messaging.incoming.requests.topic` = `one` and `quarkus…` = `two`"
    open_questions = [
        {
            "protocol": "",
            "method": None,
            "path": "requests",
            "question": "binder_protocol",
            "candidates": json.dumps(
                [{"binding": "requests", "binder": "smallrye-amqp", "reason": unchosen}]
            ),
            "evidence": unchosen,
        },
        {
            "protocol": "kafka",
            "method": None,
            "path": "quotes",
            "question": "channel_destination",
            "candidates": json.dumps(
                [{"channel": "quotes", "handler": "Quotes#process().", "reason": disagreeing}]
            ),
            "evidence": disagreeing,
        },
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert f"binder_protocol: requests: {unchosen}" in text
    assert "maps to no protocol" not in text
    assert f"channel_destination: quotes → Quotes#process(). ({disagreeing})" in text


def test_an_unselected_binding_question_renders_the_candidate_and_the_key():
    """The other kind F2 §3.4 added. It exists because the cardinality count taken
    in the engine is over declared METHODS while the framework counts registered
    BEANS — so a suppression here is not evidence the framework suppressed, and
    the reader needs the key that would settle it."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "",
            "method": None,
            "path": "orders",
            "question": "unselected_binding",
            "candidates": json.dumps(
                [{"candidate": "orders", "selected_by": "spring.cloud.function.definition"}]
            ),
            "evidence": "2 candidates were found and the selection key names none of them",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert (
        "- `orders` — unselected_binding: orders (set `spring.cloud.function.definition` to choose)"
    ) in text


def test_a_handler_protocol_question_renders_one_line_per_candidate_wire():
    """F2 §3.6's kind. Added with its arm test in the same change, because the
    review one wave earlier found the two preceding kinds shipping arms that
    nothing exercised — the whole suite passed with each disabled, and a wrong
    key would raise `KeyError` on the first real module to file one.

    The row here is the SHIPPED one, byte for byte: `protocol` is `None` (the
    writer's own value, not the `""` an earlier draft of this test passed, which
    reached the same branch by luck), and the candidates are the two wires
    `service_identity._merged` folds together. Both lines must appear and must
    DIFFER — §3.6 review finding 3 was two byte-identical lines, under which a
    verdict anchors to the first and the second stands unanswered forever.
    """
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    annotation = "org/springframework/messaging/handler/annotation/MessageMapping#"
    open_questions = [
        {
            "protocol": None,
            "method": None,
            "path": "com/acme/orders/LiveController#",
            "question": "handler_protocol",
            "candidates": json.dumps(
                [
                    {
                        "class": "com/acme/orders/LiveController#",
                        "annotation": annotation,
                        "protocol": protocol,
                    }
                    for protocol in ("rsocket", "websocket")
                ]
            ),
            "evidence": "this module's build does not settle whether it declares one of x",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    # Candidates render joined onto the question's own line, so the assertion is
    # that BOTH wires appear on it and that the two halves are not the same text.
    assert (
        "- `com/acme/orders/LiveController#` — handler_protocol: "
        f"`rsocket` — com/acme/orders/LiveController# carries {annotation}; "
        f"`websocket` — com/acme/orders/LiveController# carries {annotation}"
    ) in text


def test_a_registration_activation_question_names_the_method_that_returns_it():
    """`OI-64`'s kind, with its arm test in the same change — the two waves before
    this one each shipped a renderer arm nothing exercised, and the whole suite passed
    with the arm disabled while a wrong key would `KeyError` on the first real module
    to file one.

    The sentence must name the ENCLOSING METHOD, because that is where a reader has to
    look. The question is not "is this subscription real" but "does anyone call what
    this method returns, and start it" — without the method there is nothing to open.
    """
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    enclosing = "com/acme/orders/messaging/raw/RawPubSubSubscribers#withNamedReceiver()."
    open_questions = [
        {
            "protocol": "pubsub",
            "method": None,
            "path": "raw-notify-factory",
            "question": "registration_activation",
            "candidates": json.dumps(
                [
                    {
                        "registration": "com/google/cloud/pubsub/v1/Subscriber#newBuilder",
                        "enclosing": enclosing,
                        "activated_by": (
                            "com.google.cloud.pubsub.v1.Subscriber$Builder.build then "
                            "com.google.cloud.pubsub.v1.Subscriber.startAsync"
                        ),
                    }
                ]
            ),
            "evidence": "constructed, but nothing in this method completes the chain",
        }
    ]

    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)

    assert (
        "- `pubsub raw-notify-factory` — registration_activation: "
        f"com/google/cloud/pubsub/v1/Subscriber#newBuilder in {enclosing} is returned, "
        "not activated — nothing here calls "
        "com.google.cloud.pubsub.v1.Subscriber$Builder.build then "
        "com.google.cloud.pubsub.v1.Subscriber.startAsync"
    ) in text


def test_a_routing_depth_question_names_the_entry_caller_and_the_unread_callee():
    """Spec 2026-09-19 §4a's arm, for the reason every arm here has a test: an arm
    reached by nothing is an arm nobody has run, and the fixture files no `routing_depth`
    question (no fixture chain is seventeen helpers deep). Candidate shape (`callee`,
    `caller`, `depth`) matches what `combinator._routing_depth_rows` writes — the bound
    is the engine's, carried on the candidate, so this arm repeats no constant. Both identity halves
    are NULL and render `(unresolved)` twice, honestly: the walk stopped before it read
    either, and the sentence is where the reader learns which file to open."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "http",
            "method": None,
            "path": None,
            "question": "routing_depth",
            "candidates": json.dumps(
                [
                    {
                        "callee": "com/acme/RoutesKt#h17(sig_11).",
                        "caller": "com/acme/RoutesKt#orders(sig_o0).",
                        "depth": 16,
                    }
                ]
            ),
            "evidence": "com/acme/RoutesKt#orders(sig_o0).",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert "## Open questions" in text
    assert (
        "- `(unresolved) (unresolved)` — routing_depth: a routing helper chain deeper than "
        "16 calls from com/acme/RoutesKt#orders(sig_o0). was not followed; its first unread "
        "callee is com/acme/RoutesKt#h17(sig_11)."
    ) in text


def test_a_web_stack_question_names_each_stack_and_the_keys_it_would_apply():
    """Ruling 3's arm, for the reason every arm here has a test. Candidate shape (`stack`,
    `keys`) matches what `path_prefix._ask_web_stack` writes; both identity halves are NULL
    because the question is the module's, not one row's."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "http",
            "method": None,
            "path": None,
            "question": "web_stack",
            "candidates": json.dumps(
                [
                    {
                        "stack": "servlet",
                        "keys": ["server.servlet.context-path", "spring.mvc.servlet.path"],
                    }
                ]
            ),
            "evidence": "resolved_config",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert (
        "- `(unresolved) (unresolved)` — web_stack: on the servlet stack, "
        "`server.servlet.context-path`, `spring.mvc.servlet.path` would prefix the rows"
    ) in text


def test_a_prefix_not_measured_question_names_the_key_and_both_versions():
    """Ruling 3's version-bound arm. Candidate shape (`key`, `framework`,
    `module_versions`, `declared_for`) matches `path_prefix._ask_prefix_not_measured`."""
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "http",
            "method": None,
            "path": None,
            "question": "prefix_not_measured",
            "candidates": json.dumps(
                [
                    {
                        "key": "spring.jersey.application-path",
                        "framework": "org.springframework.boot",
                        "module_versions": ["4.1.1"],
                        "declared_for": [">=2.0 <4.0"],
                    }
                ]
            ),
            "evidence": "resolved_config",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert (
        "- `(unresolved) (unresolved)` — prefix_not_measured: `spring.jersey.application-path` "
        "is configured but not applied: it is declared for org.springframework.boot "
        ">=2.0 <4.0, and the module runs 4.1.1"
    ) in text


def test_a_routing_conflict_question_renders_both_handlers():
    """W28's arm, for the reason `test_a_service_identity_question_renders_the_flagged_
    class_and_reason` exists: a missing `_candidate_line` arm was a live render-time
    `ValueError`, and W28 added an arm with no test because the fixture files zero
    conflicts. An arm reached by nothing is an arm nobody has run.

    The verb is NULL here, which is the shape a conflict between two VERBLESS mappings
    files — the case `_verbs_of` reports once rather than eight times — so this also pins
    that `_wire_identity` renders such a row without inventing a verb for it.
    """
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    open_questions = [
        {
            "protocol": "http",
            "method": None,
            "path": "/orders",
            "question": "routing_conflict",
            "candidates": json.dumps(
                [
                    {"handler": "com/acme/Controller#first(sig_1)."},
                    {"handler": "com/acme/Controller#second(sig_2)."},
                ]
            ),
            "evidence": "one address, two handlers",
        }
    ]
    text = render_module_document(MODULE, report, "a3f91c", open_questions=open_questions)
    assert "## Open questions" in text
    assert (
        "- `any /orders` — routing_conflict: com/acme/Controller#first(sig_1).; "
        "com/acme/Controller#second(sig_2)."
    ) in text
