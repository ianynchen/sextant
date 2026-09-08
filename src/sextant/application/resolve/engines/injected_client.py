"""`injected_client` engine for endpoint derivation (D02 §2's
`injected_client` style, 2O design §1c).

A second, separate style from `supertype_derived` — injection is a different
SHAPE of evidence than supertype-plus-members (a field the module declares
and a framework populates, never a class the module itself extends), and
D02's "a style is a shape of evidence, not a framework" rule forbids fusing
the two into one engine, even though both end up reading the same kind of
identity-building call site (`shapes/identity_calls.py`).

**One row per injected stub, at the SERVICE level.** `method` stays NULL and
`path` is `<protoPackage>.<Service>` — the stub type's own OUTER class marker
call, read exactly as `supertype_derived` reads it (R11: a call-site argument,
never a field value) — or, where that call cannot be read, the stub type's
own bare descriptor verbatim. The injection declares that the module TALKS TO
the service; it does not declare which methods, and deriving one row per
service method would fabricate a boundary nothing here observes — per-method
outbound rows wait on 2Q's call graph, which can read the stub's own calls.

**The fence** (SEI precedent, `interface_implementation`'s registration-is-
the-evidence sibling): an outbound row derives only for a service this module
does NOT itself implement. Stated by SYMBOL NAME rather than by identity —
`supertype_derived`'s own match cannot be reused here, because the fence must
still fire when the injected stub's own identity is UNREADABLE (a module
implementing a service against PUBLISHED stubs has no local `SERVICE_NAME` to
read either, 2O design §1b's own boundary) — so the test is: does any of this
module's OWN classes carry an `extends` edge (capability 9.13's `superclass`,
read directly off `superclasses`, not gated on `supertype_derived`'s own
richer "is the target itself in this workspace" test) whose OUTER class
matches the injected stub type's own outer class
(`…OrderServiceGrpc$OrderServiceImplBase#` against
`…OrderServiceGrpc$OrderServiceBlockingStub#`, both stripping to
`…OrderServiceGrpc#`)? The extends RELATIONSHIP is a fact of the module's own
class even when its target lives in an unscanned jar — what the jar withholds
is the identity, not the edge — so this test survives the published-stubs-jar
case the identity-based version could not.

**Bare `newBlockingStub(channel)` without `@GrpcClient`** is a stated
boundary this task does not derive from: no engine here reads from a type
reference alone, and the call's own argument is a `Channel` object, not an
address (COVERAGE §5.7)."""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.identity_calls import (
    first_string_arguments,
    outer_class,
    parsed_call_sites,
    split_call,
)
from sextant.application.resolve.shapes.rooting import catalog_symbols
from sextant.domain.symbols import bare_descriptor

_REQUIRED_MATCHES = ("field_annotation", "identity_marker")
_REQUIRED_MARKER = ("service_name_call",)

_UNREADABLE = (
    "SERVICE_NAME constant unreadable — no ServiceDescriptor.newBuilder call "
    "site found on the injected stub's own generated class (CP-8(b))"
)


@dataclass(frozen=True)
class _FieldMatch:
    """One `@GrpcClient`-annotated field this workspace's own facts describe
    — `field`'s own FULL symbol is what a `service_identity` gap flags, and
    `stub_type` (bare) is what a row's own fallback `path` carries verbatim
    when the identity cannot be read."""

    field: str
    stub_type: str
    service_name: str | None


def run(workspace: Workspace, catalog: Catalog) -> None:
    """One outbound, service-level row per distinct identity `_matches`
    found, fenced entries already excluded. `handler`/`caller`/`peer` are all
    NULL: the injection names no calling method of its own (a field
    declaration, not a call site) and no handler (this is the outbound
    side)."""
    _validate_matches(catalog)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for match in _matches(workspace, catalog):
        path = match.service_name if match.service_name is not None else match.stub_type
        resolution = "resolved" if match.service_name is not None else "unresolved"
        key = (catalog.protocol, catalog.direction, path)
        if key in seen:
            continue
        seen.add(key)
        rows.append(_row(catalog, path, resolution))
    workspace.derive("call_endpoints", rows=rows)


def gaps(workspace: Workspace, catalog: Catalog) -> list[dict[str, Any]]:
    """The `service_identity` open-question rows an unreadable injected
    stub's identity earns — the `supertype_derived.gaps` precedent, re-walking
    `_matches` rather than reading `endpoints` back."""
    _validate_matches(catalog)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _matches(workspace, catalog):
        if match.service_name is not None:
            continue
        if match.stub_type in seen:
            continue
        seen.add(match.stub_type)
        rows.append(
            {
                "protocol": catalog.protocol,
                "method": None,
                "path": match.stub_type,
                "question": "service_identity",
                "candidates": json.dumps(
                    [{"class": match.field, "reason": _UNREADABLE}],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "evidence": _UNREADABLE,
            }
        )
    return rows


def _matches(workspace: Workspace, catalog: Catalog) -> list[_FieldMatch]:
    # A LIST or a scalar (§3.1); plural name so a stale `==` cannot compile away.
    field_annotations = catalog_symbols(
        catalog.matches["field_annotation"], f"{catalog.source}: field_annotation"
    )
    marker = catalog.matches["identity_marker"]
    service_owner, service_method = split_call(marker["service_name_call"])

    call_sites = parsed_call_sites(workspace)
    service_names = first_string_arguments(call_sites, service_owner, service_method, 0)
    field_types = _field_types(workspace)
    fenced = _fenced_outer_classes(workspace)

    matches: list[_FieldMatch] = []
    for annotation in workspace.query("annotations"):
        if str(annotation["annotation"]) not in field_annotations:
            continue
        field = str(annotation["target"])
        stub_type = field_types.get(field)
        if stub_type is None:
            # No declared type for this field reached the workspace — a
            # capture failure, never a fabricated stub type.
            continue
        outer = outer_class(stub_type)
        if outer in fenced:
            # The fence: this module implements the very service the stub
            # would otherwise appear to call.
            continue
        matches.append(
            _FieldMatch(field=field, stub_type=stub_type, service_name=service_names.get(outer))
        )
    return matches


def _field_types(workspace: Workspace) -> dict[str, str]:
    """Every declared field's own type, BARE (D00 §5a — a signature's type
    reference carries no module coordinates, the `single_call.
    _argument_type_identity` precedent), keyed by the field's own FULL
    symbol — the coordinate space `annotations.target` shares, which is what
    an `@GrpcClient` field's own target joins against."""
    result: dict[str, str] = {}
    for row in workspace.query("fields"):
        raw = row["returns"]
        if raw is None:
            continue
        returns = json.loads(str(raw))
        symbol = returns.get("symbol") if isinstance(returns, dict) else None
        if symbol:
            result[str(row["symbol"])] = str(symbol)
    return result


def _fenced_outer_classes(workspace: Workspace) -> set[str]:
    """Every outer class this module's own classes' `extends` edges name
    (capability 9.13's `superclass`), regardless of whether that target's
    own facts reached this workspace — the module docstring's own reason:
    the fence must still fire against a published-stubs jar, where the edge
    is this class's own fact but the target's identity is unreadable."""
    return {
        outer_class(bare_descriptor(str(row["superclass"])))
        for row in workspace.query("superclasses")
    }


def _row(catalog: Catalog, path: str, resolution: str) -> dict[str, Any]:
    return {
        "protocol": catalog.protocol,
        "direction": catalog.direction,
        "method": None,
        "path": path,
        "handler": None,
        "caller": None,
        "peer": None,
        "handler_signature": None,
        "resolution": resolution,
        "evidence": "compiler",
        "catalog_id": catalog.id,
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before any field is matched — the
    `interface_implementation._validate_matches` precedent."""
    matches = catalog.matches
    missing = [key for key in _REQUIRED_MATCHES if key not in matches]
    if missing:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` is missing "
            f"{', '.join(missing)} — `injected_client` needs `field_annotation` and "
            f"`identity_marker` (2O design §1c)"
        )
    marker = matches["identity_marker"]
    missing_marker = (
        [key for key in _REQUIRED_MARKER if key not in marker]
        if isinstance(marker, dict)
        else list(_REQUIRED_MARKER)
    )
    if missing_marker:
        raise CatalogError(
            f"loading catalog {catalog.source}: `identity_marker` is missing "
            f"{', '.join(missing_marker)} — needs `service_name_call`, an `{{owner, method}}` "
            f"marker (2O design §1c, R11)"
        )
    for key in _REQUIRED_MARKER:
        if key in marker:
            _validate_call(catalog, marker[key], key)


def _validate_call(catalog: Catalog, declared: Any, key: str) -> None:
    """Refuses a marker whose shape the read cannot honour — the
    `supertype_derived._validate_call` precedent, and the same reason:
    `test_catalogs_use_one_fqn_notation` refuses any catalog value carrying
    `#`, which is reserved for the SCIP symbol form the fact stream uses."""
    valid = (
        isinstance(declared, dict)
        and isinstance(declared.get("owner"), str)
        and isinstance(declared.get("method"), str)
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `identity_marker.{key}` must be "
            f"`{{owner, method}}`, got {declared!r} (2O design §1c, R11)"
        )
