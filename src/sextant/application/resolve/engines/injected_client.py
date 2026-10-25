"""`injected_client` engine for endpoint derivation (D02 §2's
`injected_client` style, 2O design §1c).

A second, separate style from `supertype_derived` — injection is a different
SHAPE of evidence than supertype-plus-members (a field or a method or
constructor parameter the module declares and a framework populates, never a
class the module itself extends), and
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
case the identity-based version could not. An edge whose subclass is nested in
that SAME outer class is not one: it is the generated class's own structure
(protoc's `<Service>FileDescriptorSupplier extends
<Service>BaseDescriptorSupplier`, in every full-protobuf `<Service>Grpc`), and
it does not fence (`_fenced_outer_classes`).

**An injection point is a FIELD or a PARAMETER, one rule.** The annotation is
joined to the type its own injection point declares: a field's, through the
`fields` table, or a method's or constructor's parameter, through the
`parameters[].annotations` its signature carries (D00 §5a — where the extractor
records parameter annotations; they are not annotation facts). Both then go
through the same fence and the same identity read. A framework whose annotation
cannot target a parameter simply never has one to match, so there is no
per-catalog switch.

**A wrapper's identity is the identity it delegates to** (spec 2026-10-25
§3a). Where the injected type's outer class makes no marker call, the row is
the one marked class its nest's code reaches (`delegated_outers`): a generated
wrapper stub's constructor builds the generated service class's own stub.

**Two optional `matches` keys** (spec 2026-10-25 §3b, CP-53) serve a
framework that generates a client class around the stubs:
- `interface_client: {implements}`: an injected interface is answered by the
  one module class that implements `implements` and declares that interface
  as its first other one. That class's identity is the row's. Two such classes
  answer nothing, and the injected type keeps today's unresolved row.
- `served_by_annotation`: an `extends` edge fences only when the subclass
  declares this annotation itself. A generated bean extending a generated
  base carries none, so it serves nothing and fences nothing.
A catalog declaring neither reads exactly as before.

**Bare `newBlockingStub(channel)` without `@GrpcClient`** is a stated
boundary this task does not derive from: no engine here reads from a type
reference alone, and the call's own argument is a `Channel` object, not an
address (COVERAGE §5.7)."""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.engines.supertype_derived import _served
from sextant.application.resolve.shapes.identity_calls import (
    calling_classes,
    delegated_outers,
    first_string_arguments,
    nest_hosts,
    outer_of,
    parsed_call_sites,
    split_call,
)
from sextant.application.resolve.shapes.rooting import _catalog_symbol, catalog_symbols
from sextant.domain.symbols import bare_descriptor

_REQUIRED_MATCHES = ("field_annotation", "identity_marker")
_REQUIRED_MARKER = ("service_name_call",)

_UNREADABLE = (
    "SERVICE_NAME constant unreadable — no ServiceDescriptor.newBuilder call "
    "site found on the injected stub's own generated class (CP-8(b))"
)


@dataclass(frozen=True)
class _FieldMatch:
    """One `@GrpcClient`-annotated injection point this workspace's own facts
    describe — a field, or a method or constructor with an annotated parameter.
    `site`'s own FULL symbol (the field's, or the declaring method's) is what a
    `service_identity` gap flags, and `stub_type` (bare) is what a row's own
    fallback `path` carries verbatim when the identity cannot be read."""

    site: str
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
                    [{"class": match.site, "reason": _UNREADABLE}],
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
    hosts = nest_hosts(workspace)
    # Spec §3a: an outer class making no marker call of its own -> the one
    # marked class its nest's code reaches.
    delegated = delegated_outers(
        call_sites, calling_classes(call_sites, service_owner, service_method), hosts
    )
    clients = _interface_clients(workspace, catalog.matches.get("interface_client"))
    fenced = _fenced_outer_classes(workspace, catalog.matches.get("served_by_annotation"))

    injected: list[tuple[str, str]] = []
    for annotation in workspace.query("annotations"):
        if str(annotation["annotation"]) not in field_annotations:
            continue
        field = str(annotation["target"])
        stub_type = field_types.get(field)
        if stub_type is None:
            # No declared type for this field reached the workspace — a
            # capture failure, never a fabricated stub type. (A parameter
            # has no `annotations` row of its own: it is read below.)
            continue
        injected.append((field, stub_type))
    injected.extend(_annotated_parameters(workspace, field_annotations))

    matches: list[_FieldMatch] = []
    for site, stub_type in injected:
        outer = outer_of(stub_type, hosts)
        if outer in fenced:
            # The fence: this module implements the very service the stub
            # would otherwise appear to call.
            continue
        answered = sorted(clients.get(bare_descriptor(stub_type), ()))
        if len(answered) == 1:
            # The framework injects this class for the interface (CP-53
            # row 6), so its identity is the row's.
            outer = outer_of(answered[0], hosts)
        matches.append(
            _FieldMatch(
                site=site,
                stub_type=stub_type,
                service_name=service_names.get(delegated.get(outer, outer)),
            )
        )
    return matches


def _interface_clients(workspace: Workspace, rule: dict[str, Any] | None) -> dict[str, set[str]]:
    """Each interface `interface_client` answers, mapped to every module class
    answering it, both bare (CP-53 row 3).

    The framework reads every class that DIRECTLY implements `rule.implements`
    and keys it by the first other interface that class declares, reading no
    further. Every class under one key is kept, so that `_matches` can refuse
    two: the framework's map keeps one of them, in an order the facts do not
    state."""
    if rule is None:
        return {}
    implements = _catalog_symbol(rule["implements"])
    known = {str(row["symbol"]) for row in workspace.query("declared_symbols")}
    clients: dict[str, set[str]] = {}
    for row in workspace.query("implementations"):
        client = str(row["symbol"])
        raw = row["interfaces"]
        declared = [
            bare_descriptor(str(entry))
            for entry in (raw if isinstance(raw, list) else json.loads(str(raw)))
        ]
        if client not in known or implements not in declared:
            continue
        keyed = next((entry for entry in declared if entry != implements), None)
        if keyed is not None:
            clients.setdefault(keyed, set()).add(bare_descriptor(client))
    return clients


def _annotated_parameters(
    workspace: Workspace, field_annotations: tuple[str, ...]
) -> list[tuple[str, str]]:
    """`(declaring method's symbol, parameter's declared type, BARE)` for every
    method or constructor parameter carrying one of the catalog's annotations.

    The extractor records a parameter's annotations on the method's own
    signature (`parameters[].annotations`, D00 §5a), not as `annotations` rows,
    and the declared type is on the same parameter entry — so the join a field
    makes between two tables is here one entry read. The parameter's own
    `type.symbol` is read, as a field's `returns.symbol` is: both are the type
    the author declared."""
    found: list[tuple[str, str]] = []
    # Two queries because the storage keeps them apart: a constructor is no
    # `method_declarations` row, and its signature arrives as text.
    declared = [
        *workspace.query("method_declarations"),
        *workspace.query("constructor_declarations"),
    ]
    for row in declared:
        raw = row["signature"]
        if raw is None:
            continue
        signature = raw if isinstance(raw, dict) else json.loads(str(raw))
        for parameter in signature.get("parameters") or []:
            uses = parameter.get("annotations") or []
            if not any(use.get("annotation") in field_annotations for use in uses):
                continue
            stub_type = (parameter.get("type") or {}).get("symbol")
            if stub_type:
                found.append((str(row["symbol"]), str(stub_type)))
    return found


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


def _fenced_outer_classes(workspace: Workspace, annotation: str | None) -> set[str]:
    """Every outer class this module's own classes' `extends` edges name
    (capability 9.13's `superclass`), regardless of whether that target's
    own facts reached this workspace — the module docstring's own reason:
    the fence must still fire against a published-stubs jar, where the edge
    is this class's own fact but the target's identity is unreadable.

    An edge whose BOTH ends are nested in one outer class fences nothing: it
    is that class's own structure, not this module implementing it. protoc
    emits two such edges in every full-protobuf `<Service>Grpc`
    (`<Service>FileDescriptorSupplier` and `<Service>MethodDescriptorSupplier`
    each extend `<Service>BaseDescriptorSupplier`), and counting them fenced
    every stub a module compiles itself, so its client rows vanished with no
    question.

    Under a catalog naming `served_by_annotation`, an edge counts only when its
    subclass, or a module class below it, declares that annotation itself: the
    framework serves no other class (CP-52 row 7, CP-53 row 9). An abstract
    base between the generated base and the annotated class is not a bean, so
    the class below it is served through its edge."""
    hosts = nest_hosts(workspace)
    edges = workspace.query("superclasses")
    served = _served(workspace, annotation)
    serving = _serving(served, edges) if served is not None else None
    fenced: set[str] = set()
    for row in edges:
        if serving is not None and bare_descriptor(str(row["symbol"])) not in serving:
            continue
        target = outer_of(bare_descriptor(str(row["superclass"])), hosts)
        if outer_of(bare_descriptor(str(row["symbol"])), hosts) == target:
            continue
        fenced.add(target)
    return fenced


def _serving(served: set[str], edges: list[dict[str, Any]]) -> set[str]:
    """Every class declaring the serving annotation, and every class above one
    of them through `superclasses`, bare."""
    parent = {
        bare_descriptor(str(row["symbol"])): bare_descriptor(str(row["superclass"]))
        for row in edges
    }
    serving: set[str] = set()
    for start in served:
        current: str | None = bare_descriptor(start)
        while current is not None and current not in serving:
            serving.add(current)
            current = parent.get(current)
    return serving


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
    if "served_by_annotation" in matches and not isinstance(matches["served_by_annotation"], str):
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches.served_by_annotation` must name one "
            f"type, got {matches['served_by_annotation']!r} (spec 2026-10-25 §3b)"
        )
    if "interface_client" in matches:
        rule = matches["interface_client"]
        if not (isinstance(rule, dict) and isinstance(rule.get("implements"), str)):
            raise CatalogError(
                f"loading catalog {catalog.source}: `matches.interface_client` must be "
                f"`{{implements}}`, got {rule!r} (spec 2026-10-25 §3b)"
            )


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
