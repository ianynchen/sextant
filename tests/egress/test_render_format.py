import json
from pathlib import Path

import pytest

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.egress.render.document import render_module_document
from sextant.egress.render.metadata import write_metadata

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
    assert "| `GET /v1/orders` | `com/acme/C#list().` | - → - | protobuf | resolved |" in text


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
    assert (
        "| `GET /v1/orders` | `com/acme/C#list().` | - → - | protobuf (assumed) | resolved |"
    ) in text


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
    assert "| `GET /v1/orders` | `com/acme/C#list().` | - → - | unresolved | resolved |" in text


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
    assert (
        "| `GET /v1/orders` | `com/acme/C#list().` | - → - | protobuf (assumed) | resolved |"
    ) in text


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
        "asm",
        "9.7",
        "a3f91c",
        schema_sources_not_compiled=("broken.proto",),
        descriptors_not_interpreted=("pkg.Widget",),
    )
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["schema_sources_not_compiled"] == ["broken.proto"]
    assert written["descriptors_not_interpreted"] == ["pkg.Widget"]


def test_metadata_gap_lists_are_empty_by_default(tmp_path: Path):
    report = ResolveReport(facts_loaded=0, endpoints=[], coverage={"documents": 0})
    write_metadata(tmp_path / "metadata.json", MODULE, report, "asm", "9.7", "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["schema_sources_not_compiled"] == []
    assert written["descriptors_not_interpreted"] == []
