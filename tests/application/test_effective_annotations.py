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

from sextant.application.resolve.effective_annotations import composed_mapping_rows, inherited_rows
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import AnnotationFact, AnnotationUse, Document, SymbolFact
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_REQUEST_MAPPING = "org/springframework/web/bind/annotation/RequestMapping#"
_GET_MAPPING = "org/springframework/web/bind/annotation/GetMapping#"
_API_GET = _MODULE + "com/acme/orders/composed/ApiGet#"
_API_GET_DESCRIPTOR = "com/acme/orders/composed/ApiGet#"
_HANDLER = _MODULE + "com/acme/orders/composed/ComposedController#composed()."
_MAPPING_FQNS = {_REQUEST_MAPPING, _GET_MAPPING}


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
        # 2H Task 2's two naming forms, inert — this regression is about the
        # PREFIX join, so both stay at the values every pre-2H catalog has.
        path_fallback=None,
        qualifier_from=[],
        qualifier_separator=None,
        # 2I Task 2's two QName forms and its member rule, inert for the
        # same reason.
        qualifier_format=None,
        namespace_template=None,
        members=None,
        # Inert for the same reason: this regression is about WHETHER a
        # prefix joins at all, not what joins it — and 2O Task 7's constant
        # prefix is inert on the same grounds, at the value every catalog
        # declaring none binds.
        path_separator=None,
        path_prefix=None,
        # 2I Task 5's construct gate, inert — this regression's own facts
        # declare no enclosing type at all, and NULL applies the rules to
        # every construct exactly as every pre-2I catalog gets.
        declared_on=None,
        # 2I Task 5's SEI fence, inert for the same reason — this regression's
        # catalog is inbound and gates on no construct kind.
        locally_implemented=[],
        # 2O Task 2's canonical-address gate, at the value this catalog's own
        # declared protocol and direction imply (inbound http). Inert against
        # the assertion below either way: `/plain` is already the URL it is
        # served at, and a leaked prefix would still fail the same equality.
        canonical_path=True,
        # 2O Task 10's direction resolution, inert — this regression's catalog
        # declares none, so the flip predicate is false for every row and the
        # direction, handler and canonical answers are the ones it always had.
        flip_direction=None,
        flip_owners=[],
        flip_handlers=[],
        flip_canonical_path=False,
    )
    rows = workspace.query("endpoints")
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [("GET", "/plain")]


# --- Task 7: `inherited_rows` (spec §3) -----------------------------------
#
# Pure over hand-built rows, the same way `composed_mapping_rows` is tested
# above — no workspace. `annotation_rows` here always plays the role of the
# COMPOSED universe `annotation_driven._synthetic_annotations` builds (real
# `annotations` rows plus `composed_mapping_rows`'s own output); scenario
# (vii) below is the one that actually puts a composed-shaped row in it.

_I = _MODULE + "com/acme/orders/inherit/OrdersApi#"
_I2 = _MODULE + "com/acme/orders/inherit/OtherApi#"
_IX = _MODULE + "com/acme/orders/inherit/BaseApi#"
_C = _MODULE + "com/acme/orders/inherit/OrdersApiController#"
_B = _MODULE + "com/acme/orders/inherit/BaseController#"
_A = _MODULE + "com/acme/orders/inherit/RootController#"


def _method(symbol: str, enclosing: str, signature: dict | None = None) -> dict:
    return {"symbol": symbol, "enclosing": enclosing, "signature": signature}


def _implements(symbol: str, interfaces: list[str]) -> dict:
    return {"symbol": symbol, "interfaces": interfaces}


def _extends(symbol: str, superclass_symbol: str) -> dict:
    # Capability 9.13's `superclass` field, module-prefixed on BOTH sides
    # (`ClassScanner.erasedSuperclassJson` writes it through `symbolOf`), and
    # emitted for every non-`Object` superclass whether or not it is generic
    # — see `inherited_rows`'s docstring, and `A-C4` for the `supertypes`
    # edge this replaced.
    return {"symbol": symbol, "superclass": superclass_symbol}


def test_an_interface_methods_mapping_lands_on_the_unannotated_implementing_method():
    """(i): the interface's own `@GetMapping` reaches the implementing
    method that repeats none of its own."""
    interface_method = _I + "list()."
    class_method = _C + "list()."
    annotation_rows = [
        {"target": interface_method, "annotation": _GET_MAPPING, "args": {"value": ["/orders"]}}
    ]
    method_rows = [_method(interface_method, _I), _method(class_method, _C)]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [
        {"target": class_method, "annotation": _GET_MAPPING, "args": {"value": ["/orders"]}}
    ]


def test_the_implementing_methods_own_annotation_wins_outright_no_synthesis():
    """(ii): a class method carrying its own mapping is never touched — the
    real `annotations` row already covers it, so `inherited_rows` must add
    nothing."""
    interface_method = _I + "list()."
    class_method = _C + "list()."
    annotation_rows = [
        {"target": interface_method, "annotation": _GET_MAPPING, "args": {"value": ["/orders"]}},
        {"target": class_method, "annotation": _GET_MAPPING, "args": {"value": ["/mine"]}},
    ]
    method_rows = [_method(interface_method, _I), _method(class_method, _C)]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == []


def test_two_interfaces_mapping_the_same_method_resolve_to_declaration_order():
    """(iii): `_C` implements `[_I, _I2]`, both declaring a same-key `list`
    with their own mapping — the first interface in declaration order wins,
    deterministically, never the second even though it is also a match."""
    i1_method = _I + "list()."
    i2_method = _I2 + "list()."
    class_method = _C + "list()."
    annotation_rows = [
        {"target": i1_method, "annotation": _GET_MAPPING, "args": {"value": ["/from-i1"]}},
        {"target": i2_method, "annotation": _GET_MAPPING, "args": {"value": ["/from-i2"]}},
    ]
    method_rows = [
        _method(i1_method, _I),
        _method(i2_method, _I2),
        _method(class_method, _C),
    ]
    implementation_rows = [_implements(_C, [_I, _I2])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [
        {"target": class_method, "annotation": _GET_MAPPING, "args": {"value": ["/from-i1"]}}
    ]


def test_a_direct_interfaces_own_ancestor_is_reached_before_the_next_direct_interface():
    """(M1, Task 7 review): `_C` implements `[_I, _I2]`, and `_I` itself
    extends `_IX` (`_I`'s own `interfaces_of` entry). `_I` declares no own
    `list`, so its own sub-walk descends into `_IX` — which IS mapped —
    BEFORE `_I2`, also mapped, is ever consulted. A shallow "check every
    direct interface's own annotation first, then descend" reading of spec
    §3 would resolve `_I2`'s value instead, since `_I` alone contributes
    nothing at its own level; depth-first, matching Spring's own
    hierarchy-scan order, resolves `_IX`'s."""
    ix_method = _IX + "list()."
    i2_method = _I2 + "list()."
    class_method = _C + "list()."
    annotation_rows = [
        {"target": ix_method, "annotation": _GET_MAPPING, "args": {"value": ["/from-ix"]}},
        {"target": i2_method, "annotation": _GET_MAPPING, "args": {"value": ["/from-i2"]}},
    ]
    method_rows = [
        _method(ix_method, _IX),
        _method(i2_method, _I2),
        _method(class_method, _C),
    ]
    implementation_rows = [_implements(_C, [_I, _I2]), _implements(_I, [_IX])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [
        {"target": class_method, "annotation": _GET_MAPPING, "args": {"value": ["/from-ix"]}}
    ]


def test_superclass_resolution_loses_to_interfaces_and_reaches_transitively():
    """(iv), both halves: `_C` implements `_I` and extends `_B`, which
    itself extends `_A` (spec §3's "applied transitively up scanned
    chains"). `get` is mapped on BOTH `_I` and (reachable through `_B`)
    `_A` — the interface wins, so the superclass path is never taken even
    though it would also resolve. `list` is mapped ONLY on `_A`, two hops up
    from `_C` past `_B` (which declares `list` but no mapping on it) — that
    walk must still be reached and must still win, proving the chain is
    followed past an ancestor with nothing to contribute rather than
    stopping there. `_B`'s OWN `list` is, by the same rule, itself a
    candidate that inherits from `_A` too (it has no own mapping any more
    than `_C`'s does) — a third row, asserted alongside the other two,
    proving resolution is not special-cased to only the one class the test
    happens to be "about"."""
    i_get = _I + "get()."
    a_get = _A + "get()."
    c_get = _C + "get()."
    b_list = _B + "list()."
    a_list = _A + "list()."
    c_list = _C + "list()."
    annotation_rows = [
        {"target": i_get, "annotation": _GET_MAPPING, "args": {"value": ["/from-interface"]}},
        {"target": a_get, "annotation": _GET_MAPPING, "args": {"value": ["/from-superclass"]}},
        {"target": a_list, "annotation": _GET_MAPPING, "args": {"value": ["/from-grandparent"]}},
    ]
    method_rows = [
        _method(i_get, _I),
        _method(a_get, _A),
        _method(c_get, _C),
        _method(b_list, _B),
        _method(a_list, _A),
        _method(c_list, _C),
    ]
    implementation_rows = [_implements(_C, [_I])]
    supertype_rows = [_extends(_C, _B), _extends(_B, _A)]

    result = inherited_rows(
        annotation_rows,
        implementation_rows,
        supertype_rows,
        method_rows,
        _MAPPING_FQNS,
        _REQUEST_MAPPING,
    )

    assert result == [
        # Sorted by (target, annotation) — NFR-1 — so `_B`'s own inherited
        # row (`BaseController`) sorts before either of `_C`'s
        # (`OrdersApiController`).
        {"target": b_list, "annotation": _GET_MAPPING, "args": {"value": ["/from-grandparent"]}},
        {"target": c_get, "annotation": _GET_MAPPING, "args": {"value": ["/from-interface"]}},
        {"target": c_list, "annotation": _GET_MAPPING, "args": {"value": ["/from-grandparent"]}},
    ]


# --- `A-C4` (principles sweep §3.2): a plain `extends` is an edge -----------


def test_a_type_level_prefix_is_inherited_across_a_plain_extends(tmp_path: Path):
    """`A-C4`. A class had a superclass edge only where a `supertype` fact
    existed, and that fact is emitted only when the superclass carries type
    ARGUMENTS — so `class Child extends Base` produced no inheritance edge at
    all, and the walk reached for the field that happened to be in the row
    rather than for JLS 8.1.4/8.2, which gives every class exactly one direct
    superclass whose members it inherits.

    The consequence is a confidently wrong ADDRESS, not a missing row:
    `derive_endpoints.sql`'s `LEFT JOIN prefixes` composes an absent prefix as
    `''`, so `OrderController#get` published `/{id}` where the framework serves
    `/api/orders/{id}`.

    The edge the fact stream has carried since capability 9.13 is the erased
    `superclass` field, written for every non-`Object` superclass whether or
    not it is generic, and module-prefixed on both sides — which is why it
    needs no bare-to-prefixed lookback and why taking it also retires the "a
    scanned ancestor always declares a method" assumption (`A-M11`).
    """
    del tmp_path
    annotation_rows = [
        {"target": _B, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api/orders"]}}
    ]
    method_rows = [_method(_C + "get().", _C), _method(_B + "helper().", _B)]

    result = inherited_rows(
        annotation_rows, [], [_extends(_C, _B)], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [
        {"target": _C, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api/orders"]}}
    ]


def test_a_mapping_on_a_plain_extends_base_reaches_the_overriding_method(tmp_path: Path):
    """`A-C4`'s other direction, and the one that drops a whole row rather
    than mis-addressing one: a non-generic base declaring `@GetMapping("/ping")`
    on a method the child overrides synthesized nothing, so `GET /base/ping`
    was absent from the export entirely. The identical GENERIC pair
    synthesized both, which is what made the defect look like a hierarchy
    subtlety rather than a missing edge."""
    del tmp_path
    base_ping = _B + "ping()."
    child_ping = _C + "ping()."
    annotation_rows = [
        {"target": base_ping, "annotation": _GET_MAPPING, "args": {"value": ["/ping"]}}
    ]
    method_rows = [_method(base_ping, _B), _method(child_ping, _C)]

    result = inherited_rows(
        annotation_rows, [], [_extends(_C, _B)], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [
        {"target": child_ping, "annotation": _GET_MAPPING, "args": {"value": ["/ping"]}}
    ]


def test_an_ancestor_that_declares_no_method_at_all_still_carries_its_prefix(tmp_path: Path):
    """`A-M11`, closed by `A-C4`'s edge rather than separately. The bare-to-
    prefixed lookback the `supertypes` edge needed could only recover an
    ancestor's symbol from somewhere ELSE it appeared — as an interface, an
    implementer, or some method's `enclosing` — so an abstract base whose only
    purpose is to carry a type-level `@RequestMapping` was unreachable. JLS
    8.1.6: a class body may declare no methods at all, and the default
    constructor (8.8.9) is not one.

    The `superclass` edge carries the ancestor's full symbol on both sides, so
    there is nothing to look back through and nothing to be missing."""
    del tmp_path
    annotation_rows = [
        {"target": _B, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api/items"]}}
    ]
    method_rows = [_method(_C + "get().", _C)]

    result = inherited_rows(
        annotation_rows, [], [_extends(_C, _B)], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [
        {"target": _C, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api/items"]}}
    ]


def test_a_plain_extends_of_a_base_that_maps_nothing_synthesizes_nothing(tmp_path: Path):
    """The near-miss for `A-C4`'s new edge. Widening an inheritance walk is
    exactly the change that can start synthesizing rows nobody declared, so
    the edge must carry a mapping across and nothing else: the same plain
    `extends` pair as above with the base's annotations removed derives no row
    at all — not a prefix, not an empty one, nothing."""
    del tmp_path
    method_rows = [_method(_C + "get().", _C), _method(_B + "helper().", _B)]

    result = inherited_rows(
        [], [], [_extends(_C, _B)], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == []


def test_a_type_level_prefix_is_inherited_from_the_interface_when_the_class_has_none():
    """(v), first half: `_C` carries no own `@RequestMapping`; `_I`'s own
    type-level one is synthesized onto `_C`."""
    annotation_rows = [{"target": _I, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api"]}}]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], [], _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [{"target": _C, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api"]}}]


def test_a_type_level_prefix_is_not_inherited_when_the_class_carries_its_own():
    """(v), second half: `_C` already carries its own `@RequestMapping` —
    `_I`'s is never reached, and nothing synthesizes."""
    annotation_rows = [
        {"target": _I, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api"]}},
        {"target": _C, "annotation": _REQUEST_MAPPING, "args": {"value": ["/mine"]}},
    ]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], [], _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == []


def test_a_type_level_prefix_applies_to_both_an_inherited_and_an_own_mapped_method():
    """(M2, Task 7 review): `_C` declares TWO methods — `list` carries its
    own `@GetMapping` directly, `composed` carries none and inherits `_I`'s.
    `_I`'s own class-level `@RequestMapping("/api")` prefix must synthesize
    onto `_C` regardless — Spring resolves a `@RequestMapping` prefix once,
    at the type level, never separately per method, so the SAME prefix
    row applies whether a given method's own mapping is real or inherited."""
    interface_method = _I + "composed()."
    class_method = _C + "composed()."
    own_method = _C + "list()."
    annotation_rows = [
        {"target": _I, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api"]}},
        {"target": interface_method, "annotation": _GET_MAPPING, "args": {"value": ["/composed"]}},
        {"target": own_method, "annotation": _GET_MAPPING, "args": {"value": ["/orders"]}},
    ]
    method_rows = [
        _method(interface_method, _I),
        _method(class_method, _C),
        _method(own_method, _C),
    ]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    # `_C`'s own `list` is left alone (its own real mapping already covers
    # it — no row) — only `composed`'s inherited mapping and the class-level
    # prefix synthesize, sorted by (target, annotation).
    assert result == [
        {"target": _C, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api"]}},
        {"target": class_method, "annotation": _GET_MAPPING, "args": {"value": ["/composed"]}},
    ]


def test_a_covariant_override_and_its_bridge_both_miss_honestly():
    """(vi): checkpoint item (4)'s frozen bytecode shape — the bridge
    (`find(sig_a)`, the interface's exact descriptor) and the real override
    (`find(sig_b)`, the covariant `DetailedOrderResult` return) are BOTH
    declared on `_C`. The bridge's descriptor is what the join actually
    hits, so it is the one that would synthesize without the structural
    exclusion; the real override's descriptor never matches the interface's
    at all, so it was already missing honestly on its own. Neither may end
    up with a row."""
    interface_method = _I + "find(sig_a)."
    bridge_method = _C + "find(sig_a)."
    override_method = _C + "find(sig_b)."
    long_param = [{"type": {"symbol": "long#"}}]
    annotation_rows = [
        {
            "target": interface_method,
            "annotation": _GET_MAPPING,
            "args": {"value": ["/orders/{id}"]},
        }
    ]
    method_rows = [
        _method(
            interface_method,
            _I,
            {"parameters": long_param, "returns": {"symbol": "com/acme/orders/OrderResult#"}},
        ),
        _method(
            bridge_method,
            _C,
            {"parameters": long_param, "returns": {"symbol": "com/acme/orders/OrderResult#"}},
        ),
        _method(
            override_method,
            _C,
            {
                "parameters": long_param,
                "returns": {"symbol": "com/acme/orders/DetailedOrderResult#"},
            },
        ),
    ]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == []


def test_a_same_name_overload_with_different_parameters_is_not_a_bridge():
    """(M3, Task 7 review): `_C` declares two real, legitimate overloads —
    `list()` (no params, its own unrelated method, no mapping) and
    `list(String)` (one param, matching `_I`'s own mapped `list(String)`
    exactly, also no own mapping). `_is_bridge` must not confuse this with
    the covariant-bridge shape: the two share a name but NOT a parameter
    list, so `list(String)` is a genuine synthesis candidate and must
    resolve `_I`'s mapping — a same-name sibling alone is never enough to
    exclude a candidate; the parameter lists have to match too."""
    interface_method = _I + "list(sig_b)."
    no_arg_method = _C + "list(sig_a)."
    candidate_method = _C + "list(sig_b)."
    string_param = [{"type": {"symbol": "java/lang/String#"}}]
    annotation_rows = [
        {"target": interface_method, "annotation": _GET_MAPPING, "args": {"value": ["/orders"]}}
    ]
    method_rows = [
        _method(
            interface_method,
            _I,
            {"parameters": string_param, "returns": {"symbol": "void#"}},
        ),
        _method(no_arg_method, _C, {"parameters": [], "returns": {"symbol": "void#"}}),
        _method(
            candidate_method,
            _C,
            {"parameters": string_param, "returns": {"symbol": "void#"}},
        ),
    ]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [
        {"target": candidate_method, "annotation": _GET_MAPPING, "args": {"value": ["/orders"]}}
    ]


def test_a_composed_interface_side_row_inherits_onto_the_implementation():
    """(vii): `annotation_rows` here plays the COMPOSED universe
    `annotation_driven._synthetic_annotations` actually builds — a row
    shaped exactly like `composed_mapping_rows`'s own output, targeting the
    interface method, standing in for `@ApiGet` having already resolved to
    a real `@RequestMapping` on `OrdersApi#composed`. `inherited_rows` must
    resolve through it exactly as it would a genuinely-declared row."""
    interface_method = _I + "composed()."
    class_method = _C + "composed()."
    annotation_rows = [
        {
            "target": interface_method,
            "annotation": _REQUEST_MAPPING,
            "args": {
                "method": ["org/springframework/web/bind/annotation/RequestMethod#GET."],
                "path": ["/composed"],
            },
        }
    ]
    method_rows = [_method(interface_method, _I), _method(class_method, _C)]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, _REQUEST_MAPPING
    )

    assert result == [
        {
            "target": class_method,
            "annotation": _REQUEST_MAPPING,
            "args": {
                "method": ["org/springframework/web/bind/annotation/RequestMethod#GET."],
                "path": ["/composed"],
            },
        }
    ]
