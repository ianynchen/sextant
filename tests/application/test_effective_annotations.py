"""Tests for `composed_mapping_rows` (2E-prep design §2, §3): the closure
logic is pure over hand-built row lists — no workspace — the same way
`annotation_driven`'s own attribute-merge helpers are tested elsewhere.

Fixture truth substituted per the phase-2E checkpoint (item (2)): the
fixture's `@ApiGet` composes `@RequestMapping(method=[GET], path=["/composed"])`,
not `@GetMapping` (javac rejects `@GetMapping` as a meta-annotation — its own
`@Target` is `METHOD` only). Every scenario below uses `RequestMapping` in
its place."""

from sextant.application.resolve.effective_annotations import composed_mapping_rows

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
