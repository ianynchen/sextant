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

import pytest

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.effective_annotations import (
    composed_mapping_rows,
    inherited_rows,
    inherited_rows_over,
    type_hierarchy,
)
from sextant.application.resolve.engines.annotation_driven import _inherited_sibling_fqns
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import AnnotationFact, AnnotationUse, Document, SymbolFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
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


def _derive_endpoints_of_one(workspace: DuckDbWorkspace, **catalog: object) -> None:
    """The endpoints derivation for ONE catalog, driven directly: a batch of one
    (`endpoints`, every catalog's rows in one statement), then that catalog's
    turn (`endpoints_insert`) — what the engine's `run` does."""
    workspace.derive("endpoints", catalogs=[catalog])
    workspace.derive("endpoints_insert", catalog_id=catalog["catalog_id"])


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
        fact_schema_version=2,
        scanner_id="asm",
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

    _derive_endpoints_of_one(
        workspace,
        protocol="http",
        direction="inbound",
        type_annotation=None,
        prefix_annotation=["com/acme/rest/Mapping#"],
        class_level="prefix",
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
        # The 2026-09-06 vocabulary pass's two query-side words, inert for the
        # same reason.
        path_from_siblings=[],
        path_fallback_prefixes=[],
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
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        [_REQUEST_MAPPING],
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
        annotation_rows, [], [_extends(_C, _B)], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        annotation_rows, [], [_extends(_C, _B)], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        annotation_rows, [], [_extends(_C, _B)], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        [], [], [_extends(_C, _B)], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
    )

    assert result == []


def test_a_type_level_prefix_is_inherited_from_the_interface_when_the_class_has_none():
    """(v), first half: `_C` carries no own `@RequestMapping`; `_I`'s own
    type-level one is synthesized onto `_C`."""
    annotation_rows = [{"target": _I, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api"]}}]
    implementation_rows = [_implements(_C, [_I])]

    result = inherited_rows(
        annotation_rows, implementation_rows, [], [], _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        annotation_rows, implementation_rows, [], [], _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
    )

    # `_C`'s own `list` is left alone (its own real mapping already covers
    # it — no row) — only `composed`'s inherited mapping and the class-level
    # prefix synthesize, sorted by (target, annotation).
    assert result == [
        {"target": _C, "annotation": _REQUEST_MAPPING, "args": {"value": ["/api"]}},
        {"target": class_method, "annotation": _GET_MAPPING, "args": {"value": ["/composed"]}},
    ]


def test_a_covariant_override_and_its_bridge_both_miss_without_modifiers():
    """The FALLBACK, and only the fallback (OI-47).

    None of these method rows carries `modifiers`, which is true of every
    hand-built fact in this file and of any scanner that reports none. With
    nothing saying which method the compiler generated, the structural rule is
    all there is — same class, same name, same parameters, different return —
    and it cannot tell which of the pair is the bridge, so neither gets a row.

    The bridge (`find(sig_a)`, the interface's exact descriptor) is what the join
    actually hits; the real override (`find(sig_b)`, covariant return) never
    matches the interface's descriptor at all. A REAL scanned fact says which is
    which and the mapping lands on the real override — see
    `test_a_covariant_overrides_mapping_lands_on_the_method_someone_wrote`."""
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
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
    )

    assert result == []


def test_a_generic_covariant_override_and_its_bridge_still_match_as_a_pair():
    """W5's parameter types made this pair stop matching, and this is the pin.

    The rule below recognises a bridge by "same class, same name, same
    parameters, different return". W5 made a parameter's `type` come from the
    `Signature` attribute — so the real override, which carries one, reads the
    symbol `T`, while the bridge javac ships beside it carries no signature and
    still reads the erasure. Measured on javac 26: `Sub<T> extends Base<T>` with
    `String get(T)` gives `(TT;)Ljava/lang/String;` for the override and no
    signature at all for `(Object)Object`.

    Compared on `type.symbol` the two are `T` and `java/lang/Object#`, they do
    not match, and the SYNTHETIC bridge stops being excluded from the walk.
    `erased_symbol` — the descriptor's own answer, which is what the two actually
    share — is what both sides are compared on, so the pair holds.
    """
    interface_method = _I + "find(sig_a)."
    bridge_method = _C + "find(sig_a)."
    override_method = _C + "find(sig_b)."
    # The override states the type VARIABLE and the erasure; the bridge has only
    # the erasure, because a bridge carries no `Signature` attribute at all.
    generic_param = [{"type": {"symbol": "T"}, "erased_symbol": "java/lang/Object#"}]
    erased_param = [{"type": {"symbol": "java/lang/Object#"}, "erased_symbol": "java/lang/Object#"}]
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
            {"parameters": erased_param, "returns": {"symbol": "com/acme/orders/OrderResult#"}},
        ),
        _method(
            bridge_method,
            _C,
            {"parameters": erased_param, "returns": {"symbol": "com/acme/orders/OrderResult#"}},
        ),
        _method(
            override_method,
            _C,
            {
                "parameters": generic_param,
                "returns": {"symbol": "com/acme/orders/DetailedOrderResult#"},
            },
        ),
    ]

    result = inherited_rows(
        annotation_rows,
        [_implements(_C, [_I])],
        [],
        method_rows,
        _MAPPING_FQNS,
        [_REQUEST_MAPPING],
    )

    assert result == []


_DECLARED = {"static": False, "synthetic": False}
_GENERATED = {"static": False, "synthetic": True}


def _scanned_method(
    symbol: str, enclosing: str, signature: dict, *, generated: bool = False
) -> dict:
    """A method row as the JVM scanner really writes it — `modifiers` included.

    `_method` above omits them, and every test predating OI-47 uses it: those
    exercise the structural fallback, these exercise the shipped path."""
    return {
        "symbol": symbol,
        "enclosing": enclosing,
        "signature": signature,
        "modifiers": _GENERATED if generated else _DECLARED,
    }


def _covariant_pair(*, generated_bridge: bool = True) -> list[dict]:
    """`_C implements _I`, overriding `find(long)` with a covariant return.

    javac emits TWO methods: the real override (`sig_b`, the narrowed return)
    and a bridge (`sig_a`, the interface's exact descriptor) that forwards to it.
    Only the bridge's descriptor matches the interface's, so only the bridge can
    resolve the interface's mapping — and it is not the method anyone wrote."""
    long_param = [{"type": {"symbol": "long#"}, "erased_symbol": "long#"}]
    return [
        _scanned_method(
            _I + "find(sig_a).",
            _I,
            {"parameters": long_param, "returns": {"symbol": "com/acme/orders/OrderResult#"}},
        ),
        _scanned_method(
            _C + "find(sig_a).",
            _C,
            {"parameters": long_param, "returns": {"symbol": "com/acme/orders/OrderResult#"}},
            generated=generated_bridge,
        ),
        _scanned_method(
            _C + "find(sig_b).",
            _C,
            {
                "parameters": long_param,
                "returns": {"symbol": "com/acme/orders/DetailedOrderResult#"},
            },
        ),
    ]


def _mapped_interface() -> list[dict]:
    return [
        {
            "target": _I + "find(sig_a).",
            "annotation": _GET_MAPPING,
            "args": {"value": ["/orders/{id}"]},
        }
    ]


def test_a_covariant_overrides_mapping_lands_on_the_method_someone_wrote():
    """OI-47's first half: a mapping that used to be LOST.

    The interface's `@GetMapping` is reachable only through the bridge, because
    the ancestor join is by name AND descriptor and a covariant override's
    descriptor is by definition not its ancestor's. Excluding the bridge
    therefore threw the mapping away — and publishing it on the bridge would
    name compiler machinery as the handler. It is carried across instead, to the
    method the bridge forwards to."""
    result = inherited_rows(
        _mapped_interface(),
        [_implements(_C, [_I])],
        [],
        _covariant_pair(),
        _MAPPING_FQNS,
        [_REQUEST_MAPPING],
    )

    assert [row["target"] for row in result] == [_C + "find(sig_b)."]
    assert result[0]["annotation"] == _GET_MAPPING


def test_a_generic_overrides_mapping_stops_naming_the_bridge():
    """OI-47's second half, and the one the structural rule could not see at all.

    A class implementing `Api<String>` gets a bridge that differs from the real
    method in its PARAMETER types, not its return type — so "same name, same
    parameters, different return" never matched, the bridge was never excluded,
    and the row was published naming a method nobody wrote. Publishing the
    compiler's forwarder as the handler is a fabrication, not an under-report."""
    obj = [{"type": {"symbol": "java/lang/Object#"}, "erased_symbol": "java/lang/Object#"}]
    string = [{"type": {"symbol": "java/lang/String#"}, "erased_symbol": "java/lang/String#"}]
    void = {"symbol": "void#"}
    result = inherited_rows(
        [{"target": _I + "find(sig_a).", "annotation": _GET_MAPPING, "args": {"value": ["/x"]}}],
        [_implements(_C, [_I])],
        [],
        [
            _scanned_method(_I + "find(sig_a).", _I, {"parameters": obj, "returns": void}),
            _scanned_method(
                _C + "find(sig_a).", _C, {"parameters": obj, "returns": void}, generated=True
            ),
            _scanned_method(_C + "find(sig_b).", _C, {"parameters": string, "returns": void}),
        ],
        _MAPPING_FQNS,
        [_REQUEST_MAPPING],
    )

    assert [row["target"] for row in result] == [_C + "find(sig_b)."]


def test_a_bridge_with_two_same_named_real_overloads_resolves_nothing():
    """The arm that stops the redirect from guessing. A bridge stands for ONE
    method, and with two same-named methods a human wrote there is nothing in
    the fact saying which — §8: produce nothing rather than pick one."""
    string = [{"type": {"symbol": "java/lang/String#"}, "erased_symbol": "java/lang/String#"}]
    result = inherited_rows(
        _mapped_interface(),
        [_implements(_C, [_I])],
        [],
        [
            *_covariant_pair(),
            # A second, unrelated `find` a human wrote.
            _scanned_method(
                _C + "find(sig_c).",
                _C,
                {"parameters": string, "returns": {"symbol": "com/acme/orders/OrderResult#"}},
            ),
        ],
        _MAPPING_FQNS,
        [_REQUEST_MAPPING],
    )

    assert result == []


def test_a_redirected_mapping_never_lands_on_a_method_declaring_its_own():
    """The candidate loop skips a method that carries its own mapping, but the
    BRIDGE forwarding to it carries none of its own to skip on. Without this the
    real method would end up with two mappings — the one it declares and the one
    inherited through its bridge."""
    result = inherited_rows(
        [
            *_mapped_interface(),
            {
                "target": _C + "find(sig_b).",
                "annotation": _GET_MAPPING,
                "args": {"value": ["/its-own"]},
            },
        ],
        [_implements(_C, [_I])],
        [],
        _covariant_pair(),
        _MAPPING_FQNS,
        [_REQUEST_MAPPING],
    )

    assert result == []


def test_two_ancestors_mapping_one_method_resolve_nothing_rather_than_one_of_them():
    """Finding I1, restated as a rule instead of a side effect.

    A class overriding one method covariantly against BOTH a mapped interface and
    a mapped superclass grows two bridges, one matching each ancestor's
    descriptor, and both now redirect to the same real method. Which mapping the
    framework serves depends on its own annotation search order, which this pass
    does not read — so a method with two different answers gets none.

    The outcome matches what the old blanket exclusion produced. The difference
    is that it is now the stated rule for an ambiguity, rather than a consequence
    of discarding every bridge."""
    long_param = [{"type": {"symbol": "long#"}, "erased_symbol": "long#"}]
    result = inherited_rows(
        [
            *_mapped_interface(),
            {
                "target": _B + "find(sig_x).",
                "annotation": _GET_MAPPING,
                "args": {"value": ["/from-the-superclass"]},
            },
        ],
        [_implements(_C, [_I])],
        [_extends(_C, _B)],
        [
            *_covariant_pair(),
            _scanned_method(
                _B + "find(sig_x).",
                _B,
                {"parameters": long_param, "returns": {"symbol": "com/acme/orders/Base#"}},
            ),
            _scanned_method(
                _C + "find(sig_x).",
                _C,
                {"parameters": long_param, "returns": {"symbol": "com/acme/orders/Base#"}},
                generated=True,
            ),
        ],
        _MAPPING_FQNS,
        [_REQUEST_MAPPING],
    )

    assert result == []


def test_a_bridge_forwarding_into_a_superclass_redirects_to_nothing():
    """A bridge does not always forward to a method in its OWN class, and the
    redirect must not reach for the nearest same-named one when it does.

    Measured, javac 26 — `class Sub extends Base implements IGet<String>` where
    `Base` declares `get()` and `Sub` declares only an unrelated `get(int)`:

        Sub:  public String get(int)   (I)Ljava/lang/String;   ACC_PUBLIC
              public Object get()      ()Ljava/lang/Object;    ACC_BRIDGE, ACC_SYNTHETIC

    The bridge forwards to `Base.get()`, which is not in this class at all. Its
    only same-named sibling here is `get(int)`, which has nothing to do with the
    mapping — publishing there swaps one fabrication for another, and a worse
    one: the old code at least named a method of the right arity.

    A bridge always carries its target's arity, so the arity is what refuses it.
    The mapping is then lost rather than misplaced, which is the §8 direction —
    a bridge whose target is inherited is a boundary, recorded in COVERAGE.
    """
    no_args: list[dict] = []
    int_arg = [{"type": {"symbol": "int#"}, "erased_symbol": "int#"}]
    result = inherited_rows(
        [{"target": _I + "get(sig_a).", "annotation": _GET_MAPPING, "args": {"value": ["/thing"]}}],
        [_implements(_C, [_I])],
        [_extends(_C, _B)],
        [
            _scanned_method(
                _I + "get(sig_a).",
                _I,
                {"parameters": no_args, "returns": {"symbol": "java/lang/Object#"}},
            ),
            # The bridge: arity 0, forwarding to `_B`'s method, not to anything here.
            _scanned_method(
                _C + "get(sig_a).",
                _C,
                {"parameters": no_args, "returns": {"symbol": "java/lang/Object#"}},
                generated=True,
            ),
            # The only same-named method this class declares, and unrelated.
            _scanned_method(
                _C + "get(sig_int).",
                _C,
                {"parameters": int_arg, "returns": {"symbol": "java/lang/String#"}},
            ),
            _scanned_method(
                _B + "get(sig_b).",
                _B,
                {"parameters": no_args, "returns": {"symbol": "java/lang/String#"}},
            ),
        ],
        _MAPPING_FQNS,
        [_REQUEST_MAPPING],
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
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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
        annotation_rows, implementation_rows, [], method_rows, _MAPPING_FQNS, [_REQUEST_MAPPING]
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


# --- siblings inherit with the mapping, all or nothing (spec 2026-09-18 §3b word 3) ---
#
# Over `inherited_rows_over` directly, with a `TypeHierarchy` folded once by
# `type_hierarchy`, because the sibling rule is the walk's own and the rows it
# reads are hand-built exactly as above. JAX-RS symbols, since the rule is
# JAX-RS §3.6's: the path and media live BESIDE the verb (`@Path`, `@Produces`
# next to `@GET`), so an inherited `@GET` alone is a wrong address.

_RS_GET = "com/acme/rs/GET#"
_RS_PATH = "com/acme/rs/Path#"
_RS_PRODUCES = "com/acme/rs/Produces#"
_RS_SIBLINGS = frozenset({_RS_PATH, _RS_PRODUCES})
_RS_API = "com/acme/OrdersApi#"
_RS_RESOURCE = "com/acme/OrdersResource#"
_RS_API_METHOD = _RS_API + "byId(sig_1)."
_RS_RESOURCE_METHOD = _RS_RESOURCE + "byId(sig_1)."
_RS_HIERARCHY = type_hierarchy(
    [_implements(_RS_RESOURCE, [_RS_API])],
    [],
    [_method(_RS_API_METHOD, _RS_API), _method(_RS_RESOURCE_METHOD, _RS_RESOURCE)],
)
_RS_INTERFACE_ROWS = [
    {"target": _RS_API_METHOD, "annotation": _RS_GET, "args": {}},
    {"target": _RS_API_METHOD, "annotation": _RS_PATH, "args": {"value": "/{id}"}},
    {"target": _RS_API_METHOD, "annotation": _RS_PRODUCES, "args": {"value": ["application/json"]}},
]


def test_siblings_inherit_with_the_mapping_when_the_target_carries_nothing_of_its_own():
    """The interface's `@GET @Path("/{id}") @Produces("application/json")` reaches
    the unannotated implementor whole — all three rows, never the verb alone."""
    rows = inherited_rows_over(
        _RS_HIERARCHY, _RS_INTERFACE_ROWS, {_RS_GET}, [_RS_PATH], sibling_fqns=_RS_SIBLINGS
    )
    method = _RS_RESOURCE_METHOD
    assert {
        (r["target"], r["annotation"], json.dumps(r["args"], sort_keys=True))
        for r in rows
        if r["target"] == method
    } == {
        (method, _RS_GET, "{}"),
        (method, _RS_PATH, '{"value": "/{id}"}'),
        (method, _RS_PRODUCES, '{"value": ["application/json"]}'),
    }


@pytest.mark.pins("effective_annotations.siblings-inherit-all-or-nothing")
def test_an_own_sibling_blocks_all_inheritance_for_that_method():
    """JAX-RS §3.6 (CP-18 row 8): ANY own JAX-RS annotation makes the interface's set
    ignored — so an implementor method carrying only its own @Produces inherits no
    mapping and derives nothing, which is the framework's answer."""
    annotation_rows = [
        *_RS_INTERFACE_ROWS,
        {
            "target": _RS_RESOURCE_METHOD,
            "annotation": _RS_PRODUCES,
            "args": {"value": ["text/plain"]},
        },
    ]
    rows = inherited_rows_over(
        _RS_HIERARCHY, annotation_rows, {_RS_GET}, [_RS_PATH], sibling_fqns=_RS_SIBLINGS
    )
    assert [r for r in rows if r["target"] == _RS_RESOURCE_METHOD] == []


def test_without_sibling_fqns_the_walk_is_unchanged():
    """A catalog declaring no sibling list keeps today's walk: the mapping row alone,
    and an own sibling would not have blocked it either (Spring's own merge)."""
    rows = inherited_rows_over(_RS_HIERARCHY, _RS_INTERFACE_ROWS, {_RS_GET}, [_RS_PATH])
    assert {r["annotation"] for r in rows if r["target"].endswith("#byId(sig_1).")} == {_RS_GET}


def _sibling_catalog(**mapping: object) -> Catalog:
    """A catalog naming the two JAX-RS-shaped sibling lists above — and only what a
    test layers on beyond them."""
    return Catalog(
        id="invented-siblings",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        source=Path("tests/invented-siblings.yml"),
        matches={
            "mapping": {
                "path_from_siblings": [{"annotation": "com.acme.rs.Path", "arg": "value"}],
                "produces_from_siblings": [{"annotation": "com.acme.rs.Produces", "arg": "value"}],
                "annotations": [{"fqn": "com.acme.rs.GET"}],
                **mapping,
            }
        },
    )


def test_a_catalog_naming_siblings_without_inherit_siblings_keeps_the_mapping_only_walk():
    """Word 3 is OPT-IN (amended after the final review): a sibling list says where a
    name lives, not how the framework inherits. A catalog naming siblings and no
    `inherit_siblings` hands the walk an EMPTY sibling set, and the walk is then
    today's — the mapping row alone, Spring's own merge — while the same catalog with
    `inherit_siblings: all_or_nothing` hands it both declared siblings."""
    assert _inherited_sibling_fqns(_sibling_catalog()) == frozenset()
    assert _inherited_sibling_fqns(_sibling_catalog(inherit_siblings="all_or_nothing")) == (
        _RS_SIBLINGS
    )
    rows = inherited_rows_over(
        _RS_HIERARCHY,
        _RS_INTERFACE_ROWS,
        {_RS_GET},
        [_RS_PATH],
        sibling_fqns=_inherited_sibling_fqns(_sibling_catalog()),
    )
    assert {r["annotation"] for r in rows if r["target"] == _RS_RESOURCE_METHOD} == {_RS_GET}


def test_the_shipped_microprofile_graphql_catalog_hands_the_walk_no_siblings():
    """The catalog that forced the amendment: `microprofile-graphql.yml` declares
    `path_from_siblings` (`OI-35`) and a type gate, and SmallRye GraphQL has no
    JAX-RS §3.6 — an implementor method carrying only its own `@Name` must still
    inherit the interface's `@Query`. Read off the REAL loaded catalog, so a later
    edit opting it in is a deliberate change here rather than a silent one."""
    catalog = next(
        c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "microprofile-graphql"
    )
    assert catalog.matches["mapping"].get("path_from_siblings")
    assert _inherited_sibling_fqns(catalog) == frozenset()


@pytest.mark.pins("effective_annotations.inherited-set-agreed-as-a-whole")
def test_two_ancestors_agreeing_on_the_verb_but_not_on_a_sibling_resolve_nothing():
    """I1's shape over siblings (Task 5 fix round 1): `_C extends _B implements _I`,
    covariant overrides against BOTH, so two bridges redirect to the one real
    `find(sig_b).`. Interface and superclass both carry `@GET` — the mapping
    agrees — but `@Path("/from-interface")` against `@Path("/from-superclass")`.

    §3.6 inherits an ancestor method's annotation set WHOLE, so agreement is
    measured on the whole set: two different sets are the same ambiguous
    evidence two different verbs are, and the target gets nothing — never the
    verb with two paths beside it, which downstream would pick between on a
    tied ordinal."""
    long_param = [{"type": {"symbol": "long#"}, "erased_symbol": "long#"}]
    hierarchy = type_hierarchy(
        [_implements(_C, [_I])],
        [_extends(_C, _B)],
        [
            *_covariant_pair(),
            _scanned_method(
                _B + "find(sig_x).",
                _B,
                {"parameters": long_param, "returns": {"symbol": "com/acme/orders/Base#"}},
            ),
            _scanned_method(
                _C + "find(sig_x).",
                _C,
                {"parameters": long_param, "returns": {"symbol": "com/acme/orders/Base#"}},
                generated=True,
            ),
        ],
    )
    annotation_rows = [
        {"target": _I + "find(sig_a).", "annotation": _RS_GET, "args": {}},
        {
            "target": _I + "find(sig_a).",
            "annotation": _RS_PATH,
            "args": {"value": "/from-interface"},
        },
        {"target": _B + "find(sig_x).", "annotation": _RS_GET, "args": {}},
        {
            "target": _B + "find(sig_x).",
            "annotation": _RS_PATH,
            "args": {"value": "/from-superclass"},
        },
    ]

    rows = inherited_rows_over(
        hierarchy, annotation_rows, {_RS_GET}, [_RS_PATH], sibling_fqns=_RS_SIBLINGS
    )

    assert [r for r in rows if r["target"] == _C + "find(sig_b)."] == []
