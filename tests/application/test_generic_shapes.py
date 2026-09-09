"""A generic envelope's parameterisations are distinct shapes (F4 §5.2, W25).

## What one id for every parameterisation costs

`mall-admin`'s 160 endpoints all return `CommonResult<T>`. Before this, every one of
them carried the SAME response shape id — `CommonResult#`, with no arguments — so
`CommonResult<UmsAdmin>` and `CommonResult<List<UmsRole>>` were indistinguishable in the
output. DR-5 gates stitching on payload equality, and one id standing for 59 different
payloads says two services exchange the same thing when they do not.

Measured after: 160 endpoints, **58** distinct response shape ids.

## What it must NOT do

100 of those 160 handlers return **raw** `CommonResult` — the source declares no
argument. A raw type binds nothing, and its `data` field holds an unbound `T`. That
field gets no shape id at all: a type variable's name means something only inside the
declaration that introduced it, so rooting one would collide every unrelated `T` in the
module onto a single shape. The owner is marked OPEN instead, which is the honest answer
and a visible one.
"""

import json
from pathlib import Path

from test_shapes import (  # noqa: F401
    _CATALOG,
    _MODULE,
    _field,
    _ref,
    _string,
    _type,
    _write,
)

from sextant.application.resolve.shapes.expansion import (
    bindings_of,
    derive_shapes,
    parameterised_id,
)
from sextant.domain.closed_sets import OriginTier
from sextant.domain.facts import Document
from sextant.storage.duckdb.workspace import DuckDbWorkspace

ENVELOPE = "com/acme/orders/Envelope#"
PAYLOAD = "com/acme/orders/Payload#"
OTHER = "com/acme/orders/Other#"
HOLDER = "com/acme/orders/Holder#"


def _document(document_id: str, tier: OriginTier = OriginTier.MODULE_OUTPUT) -> Document:
    return Document(
        document_id=document_id,
        relative_path=f"{document_id}.java",
        module_id="com.acme:orders",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=tier,
        origin=None if tier is OriginTier.MODULE_OUTPUT else "com.acme:orders-common",
        redaction_set_hash="sha256:b",
    )


def _generic_type(document_id: str, owner: str, *names: str) -> dict:
    """A type declaring formal parameters, as `ClassScanner` emits them (W5)."""
    fact = _type(document_id, owner)
    fact["type_parameters"] = [
        {"name": name, "bounds": [_ref("java/lang/Object#", "object")]} for name in names
    ]
    return fact


def _workspace(tmp_path: Path) -> DuckDbWorkspace:
    """`Envelope<T> { long code; T data; }`, plus two unrelated payload types."""
    facts = tmp_path / "facts"
    _write(
        facts / "envelope.jsonl",
        _document("envelope"),
        [
            _generic_type("envelope", ENVELOPE, "T"),
            _field("envelope", ENVELOPE, "code", _ref("long#", "integer", "int64")),
            _field("envelope", ENVELOPE, "data", _ref("T", "object")),
        ],
    )
    _write(
        facts / "payload.jsonl",
        _document("payload", OriginTier.DEPENDENCY),
        [_type("payload", PAYLOAD), _field("payload", PAYLOAD, "reference", _string())],
    )
    _write(
        facts / "other.jsonl",
        _document("other"),
        [_type("other", OTHER), _field("other", OTHER, "label", _string())],
    )
    _write(
        facts / "holder.jsonl",
        _document("holder"),
        [
            _type("holder", HOLDER),
            # Two fields of the SAME generic type, differently bound — which is what
            # forces the engine to assign two ids rather than one.
            _field(
                "holder",
                HOLDER,
                "first",
                _ref(ENVELOPE, "object", arguments=[_ref(PAYLOAD, "object")]),
            ),
            _field(
                "holder",
                HOLDER,
                "second",
                _ref(ENVELOPE, "object", arguments=[_ref(OTHER, "object")]),
            ),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    return workspace


def _fields_of(workspace: DuckDbWorkspace, shape_id: str) -> dict[str, object]:
    return {
        str(row["wire_name"]): row["item"]
        for row in workspace.query("shape_fields")
        if str(row["shape_id"]) == shape_id
    }


def test_two_parameterisations_reached_through_fields_are_two_shapes(tmp_path: Path):
    """The identity half, and DR-5's reason for it: one id for both would assert that a
    service returning `Envelope<Payload>` and one returning `Envelope<Other>` exchange
    the same payload.

    Reached through a HOLDER's own fields rather than by passing ids in as roots. An
    earlier version of this test built both roots by calling `parameterised_id` itself
    and then asserted the `shapes` table contained them — which it did whatever the
    engine assigned, because the roots were the assertion. It passed with the
    identity reverted to the bare symbol.
    """
    workspace = _workspace(tmp_path)

    derive_shapes(workspace, _CATALOG, [HOLDER])
    fields = _fields_of(workspace, HOLDER)
    ids = {str(row["shape_id"]) for row in workspace.query("shapes")}
    workspace.close()

    one = json.loads(str(fields["first"]))["shape_id"]
    two = json.loads(str(fields["second"]))["shape_id"]
    assert one != two, (
        "two parameterisations of one envelope must not share a shape id — DR-5 gates "
        "stitching on payload equality"
    )
    assert {one, two} <= ids
    assert one.startswith(ENVELOPE) and PAYLOAD in one


def test_the_bound_argument_replaces_the_variable_in_the_field(tmp_path: Path):
    """The substitution half. `data` is declared `T`; under `Envelope<Payload>` it holds
    a `Payload`, and a reader following the field reaches that shape's own fields."""
    workspace = _workspace(tmp_path)
    rooted = parameterised_id(_ref(ENVELOPE, "object", arguments=[_ref(PAYLOAD, "object")]))

    derive_shapes(workspace, _CATALOG, [rooted])
    fields = _fields_of(workspace, rooted)
    workspace.close()

    assert json.loads(str(fields["data"]))["shape_id"] == PAYLOAD, (
        "the bound argument must replace the type variable; before W25 every "
        "parameterisation shared one shape whose `data` held an unbound `T`"
    )


def test_a_raw_envelope_names_no_shape_for_its_variable_and_is_open(tmp_path: Path):
    """§10's near-miss, and the case that is 100 of `mall-admin`'s 160 handlers.

    A raw `Envelope` binds nothing. Its `data` field holds `T` — a name meaningful only
    inside the declaration that introduced it — so it gets NO shape id: rooting one
    would collide every unrelated `T` in the module onto a single shape, which is this
    module's own stated rule. The owner is `open`, because a field it cannot describe is
    exactly what `open` is for.
    """
    workspace = _workspace(tmp_path)

    derive_shapes(workspace, _CATALOG, [ENVELOPE])
    fields = _fields_of(workspace, ENVELOPE)
    shape = next(row for row in workspace.query("shapes") if str(row["shape_id"]) == ENVELOPE)
    workspace.close()

    assert fields["data"] is None, "an unbound type variable must root no shape"
    assert bool(shape["open"]) is True, (
        "a shape holding a field it cannot describe is open; reporting it closed claims "
        "a complete description of a payload nobody stated"
    )


def test_a_nested_parameterisation_keeps_both_levels(tmp_path: Path):
    """`Envelope<Envelope<Payload>>` — the shape `CommonResult<CommonPage<UmsAdmin>>`
    takes on the real corpus. The id has to carry both levels, and its inverse has to
    give the outer binding back without splitting inside the inner one."""
    inner = _ref(ENVELOPE, "object", arguments=[_ref(PAYLOAD, "object")])
    rooted = parameterised_id(_ref(ENVELOPE, "object", arguments=[inner]))

    base, arguments = bindings_of(rooted)

    assert base == ENVELOPE
    assert arguments == [parameterised_id(inner)]


def test_an_expanded_shape_records_where_its_class_file_came_from(tmp_path: Path):
    """W25's `shapes.origin_tier`.

    Most of a module's contracts are only describable because the module edge was
    crossed — measured on `mall-admin`, **89 of 107** shapes come from a dependency and
    16 from the module itself. Without this column those two read identically, and a
    reader deciding how far to trust a contract cannot see that its fields came from a
    neighbour's compiled output rather than from the module in front of them.
    """
    workspace = _workspace(tmp_path)

    derive_shapes(workspace, _CATALOG, [HOLDER])
    tiers = {str(row["shape_id"]): row["origin_tier"] for row in workspace.query("shapes")}
    workspace.close()

    assert tiers[HOLDER] == "module_output"
    assert tiers[PAYLOAD] == "dependency", (
        "a shape whose class file was read across the module edge must say so"
    )
