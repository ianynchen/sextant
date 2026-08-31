"""Tests for `composed_mapping_rows` (2E-prep design §2, §3): the closure
logic is pure over hand-built row lists — no workspace — the same way
`annotation_driven`'s own attribute-merge helpers are tested elsewhere.

Fixture truth substituted per the phase-2E checkpoint (item (2)): the
fixture's `@ApiGet` composes `@RequestMapping(method=[GET], path=["/composed"])`,
not `@GetMapping` (javac rejects `@GetMapping` as a meta-annotation — its own
`@Target` is `METHOD` only). Every scenario below uses `RequestMapping` in
its place."""

import json
from pathlib import Path

from sextant.application.resolve.effective_annotations import composed_mapping_rows
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import AnnotationFact, AnnotationUse, Document, SymbolFact
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_REQUEST_MAPPING = "org/springframework/web/bind/annotation/RequestMapping#"
_API_GET = _MODULE + "com/acme/orders/composed/ApiGet#"
_API_GET_DESCRIPTOR = "com/acme/orders/composed/ApiGet#"
_HANDLER = _MODULE + "com/acme/orders/composed/ComposedController#composed()."


def test_one_hop_composition_synthesizes_a_row_naming_the_base_annotation():
    rows = [
        {
            "target": _API_GET,
            "annotation": _REQUEST_MAPPING,
            "args": {
                "method": ["org/springframework/web/bind/annotation/RequestMethod#GET."],
                "path": ["/composed"],
            },
        },
        {"target": _HANDLER, "annotation": _API_GET_DESCRIPTOR, "args": {}},
    ]

    result = composed_mapping_rows(
        rows, scanned_targets={_API_GET}, mapping_fqns={_REQUEST_MAPPING}
    )

    assert result == [
        {
            "target": _HANDLER,
            "annotation": _REQUEST_MAPPING,
            "args": {
                "method": ["org/springframework/web/bind/annotation/RequestMethod#GET."],
                "path": ["/composed"],
            },
        }
    ]


def test_use_site_attributes_win_over_the_compositions_declared_values():
    composed_type = _MODULE + "com/acme/orders/composed/ApiGetOverride#"
    composed_descriptor = "com/acme/orders/composed/ApiGetOverride#"
    rows = [
        {"target": composed_type, "annotation": _REQUEST_MAPPING, "args": {"path": "/x"}},
        {"target": _HANDLER, "annotation": composed_descriptor, "args": {"path": "/override"}},
    ]

    result = composed_mapping_rows(
        rows, scanned_targets={composed_type}, mapping_fqns={_REQUEST_MAPPING}
    )

    assert result == [
        {"target": _HANDLER, "annotation": _REQUEST_MAPPING, "args": {"path": "/override"}}
    ]


def test_transitive_two_hop_closure_lets_the_nearest_declaration_win_over_the_base():
    base = _MODULE + "com/acme/orders/composed/Base#"
    mid = _MODULE + "com/acme/orders/composed/Mid#"
    mid_descriptor = "com/acme/orders/composed/Mid#"
    outer = _MODULE + "com/acme/orders/composed/Outer#"
    outer_descriptor = "com/acme/orders/composed/Outer#"
    rows = [
        # Mid composes the base mapping annotation, declaring its own path.
        {"target": mid, "annotation": _REQUEST_MAPPING, "args": {"path": "/mid"}},
        # Outer composes Mid, declaring nothing of its own — the base's
        # (here Mid's) folded args must survive untouched. Outer's own row
        # is ALSO a use of a (by then) composed identifier — Outer's type
        # carries the folded RequestMapping too, the same honest consequence
        # as any other use — so it synthesizes its own row alongside the
        # handler's.
        {"target": outer, "annotation": mid_descriptor, "args": {}},
        # The use site composes Outer, also declaring nothing.
        {"target": _HANDLER, "annotation": outer_descriptor, "args": {}},
    ]

    result = composed_mapping_rows(
        rows, scanned_targets={base, mid, outer}, mapping_fqns={_REQUEST_MAPPING}
    )

    # Sorted by (target, annotation) — NFR-1 — so the handler (whose method
    # descriptor sorts before "Outer#") comes first.
    assert result == [
        {"target": _HANDLER, "annotation": _REQUEST_MAPPING, "args": {"path": "/mid"}},
        {"target": outer, "annotation": _REQUEST_MAPPING, "args": {"path": "/mid"}},
    ]


def test_a_meta_annotation_cycle_terminates_and_synthesizes_no_false_row():
    """Two annotation types meta-annotate each other (`X` composes `Y`, `Y`
    composes `X`), and `Y` additionally composes the real base annotation.
    The fixpoint must terminate — a missing cycle guard hangs the test,
    rather than merely failing it — and every row it does synthesize must
    fold to the one real base annotation with the one real declared value;
    nothing invented, nothing dropped."""
    x = _MODULE + "com/acme/orders/composed/X#"
    x_descriptor = "com/acme/orders/composed/X#"
    y = _MODULE + "com/acme/orders/composed/Y#"
    y_descriptor = "com/acme/orders/composed/Y#"
    rows = [
        {"target": y, "annotation": _REQUEST_MAPPING, "args": {"path": "/y"}},
        {"target": y, "annotation": x_descriptor, "args": {}},
        {"target": x, "annotation": y_descriptor, "args": {}},
        {"target": _HANDLER, "annotation": x_descriptor, "args": {}},
    ]

    result = composed_mapping_rows(rows, scanned_targets={x, y}, mapping_fqns={_REQUEST_MAPPING})

    # Sorted by (target, annotation) — NFR-1. Every synthesized row folds to
    # the same single base value ("/y") regardless of which cyclic path
    # reached it — the cycle produces no divergent or duplicated answer.
    assert result == [
        {"target": _HANDLER, "annotation": _REQUEST_MAPPING, "args": {"path": "/y"}},
        {"target": x, "annotation": _REQUEST_MAPPING, "args": {"path": "/y"}},
        {"target": y, "annotation": _REQUEST_MAPPING, "args": {"path": "/y"}},
    ]


def test_a_composed_type_outside_scanned_targets_yields_nothing():
    """The jar half (D02 §7): a composed annotation whose own type was never
    scanned — it lives in a jar, not this module — must not synthesize,
    however its use sites look."""
    jar_type = _MODULE + "com/acme/orders/composed/JarComposed#"
    jar_descriptor = "com/acme/orders/composed/JarComposed#"
    rows = [
        {"target": jar_type, "annotation": _REQUEST_MAPPING, "args": {"path": "/jar"}},
        {"target": _HANDLER, "annotation": jar_descriptor, "args": {}},
    ]

    result = composed_mapping_rows(rows, scanned_targets=set(), mapping_fqns={_REQUEST_MAPPING})

    assert result == []


def test_a_plain_direct_use_of_a_mapping_fqn_yields_no_synthetic_row():
    """Never duplicate what the `annotations` view already carries: a
    handler using `@RequestMapping` directly, with no composition involved
    at all, must not roundtrip through this pass."""
    rows = [{"target": _HANDLER, "annotation": _REQUEST_MAPPING, "args": {"path": "/plain"}}]

    result = composed_mapping_rows(
        rows, scanned_targets={_HANDLER}, mapping_fqns={_REQUEST_MAPPING}
    )

    assert result == []


def test_a_type_targeted_synthetic_prefix_row_does_not_leak_a_prefix(tmp_path: Path):
    """Regression (Task 6 review, round 1): the docstring above states the
    invariant this pins — a type-targeted synthetic row (a composing type's
    own declaration row, folded through pass 2) can carry `annotation` equal
    to `$prefix_annotation` itself, whenever a catalog's prefix annotation is
    also one of its mapping fqns (every shipped catalog). That row then
    genuinely reaches `derive_endpoints.sql`'s `prefixes` CTE, not just the
    `mappings` one `construct_kind IN ('method', 'function')` already guards.
    It must still not leak: `prefixes.type_symbol` only ever joins a real
    handler's `enclosing`, and an annotation TYPE never encloses a method.

    Driven through `workspace.derive("endpoints", ...)` directly — the SQL
    itself, not `composed_mapping_rows` — with a hand-built
    `synthetic_annotations` row targeting an annotation-type symbol that
    carries no method of its own, exactly the shape pass 2 can produce."""
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/rest/PlainController.java",
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
    controller = "com/acme/rest/PlainController#"
    handle = "com/acme/rest/PlainController#handle()."
    facts = [
        # The controller carries NO prefix annotation of its own — the only
        # source of a prefix in this fixture is the synthetic row below.
        SymbolFact(document_id="doc_1", symbol=controller, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc_1",
            symbol=handle,
            construct_kind=ConstructKind.METHOD,
            enclosing=controller,
        ),
        AnnotationFact(
            document_id="doc_1",
            target=handle,
            retention="runtime",
            use=AnnotationUse(annotation="com/acme/rest/Get#", args={"value": "/plain"}),
        ),
    ]
    write_fact_file(tmp_path / "facts" / "PlainController.jsonl", document, facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")

    workspace.derive(
        "endpoints",
        protocol="http",
        direction="inbound",
        type_annotation=None,
        prefix_annotation="com/acme/rest/Mapping#",
        mapping_annotations=[{"fqn": "com/acme/rest/Get#", "methods": ["GET"]}],
        path_from=["value"],
        prefix_from=["value"],
        peer_from=[],
        method_from="method",
        all_methods=["GET"],
        catalog_id="task6-regression",
        consumes_from=[],
        produces_from=[],
        # A type-targeted row (never a real symbol fact — an annotation type
        # composing another annotation needs no `SymbolFact` for the SQL
        # itself to accept it), carrying $prefix_annotation as its own
        # `annotation` — pass 2's own shape, per the docstring above.
        synthetic_annotations=[
            {
                "target": "com/acme/rest/ComposedMapping#",
                "annotation": "com/acme/rest/Mapping#",
                "args": json.dumps({"value": "/should-not-leak"}),
            }
        ],
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [("GET", "/plain")]
