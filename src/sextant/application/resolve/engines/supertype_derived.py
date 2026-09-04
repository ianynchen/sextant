"""`supertype_derived` engine for endpoint derivation (D02 §2's
`supertype_derived` style, 2O design §1b).

No shipped engine before this one derives from a SUPERCLASS:
`interface_implementation` is registration-gated and joins direct
`implemented_interfaces` only, and gRPC's own generated server base
(`<Service>ImplBase`) is neither — a Spring/net.devh gRPC service registers
by BEAN SCANNING, so there is no registration call to gate on, and it is
reached by `extends`, not `implements`. The evidence this style reads instead
is structural and pattern-free: protoc compiles the generated
`<Service>Grpc`/`<Service>ImplBase` classes INTO the module's own output, so
both the extends edge (capability 9.13's `superclass`, D00 §4's
`relationship_kind: extends`) and the identity-building call sites the
generated class makes are already in the workspace's own facts — no glob
grammar naming a class, no JVM-form name matching either would break D02's
naming rules and neither is needed here.

**Where the identity comes from** — R11, superseding the brief's original
`identity_marker: {constant: SERVICE_NAME}` shape (`shapes/identity_calls.py`
states the general mechanism and why): the service identity is
`ServiceDescriptor.newBuilder("<protoPackage>.<Service>")`'s own first
argument, read on the class whose facts declare the marker call — never a
field-value read. The wire method name is `MethodDescriptor.
generateFullMethodName(SERVICE_NAME, "<Method>")`'s own SECOND argument
(CP-8(d)), proto-cased, verbatim — **never derived by casing the compiled
override's own method name**, which is not invertible (a `mixedLower`-shaped
transform can collapse more than one proto spelling onto one compiled
identifier, `scripts/probes/cp3_cp8_grpc_facts.md`'s own caution). The one
casing operation this module performs runs the OTHER way — decapitalizing
the proto-cased wire name it already read to find the matching CANDIDATE
override name — and its result is used only to LOOK UP a name bytecode
itself already declared (`overridden_public_methods`, below); a candidate
that matches nothing derives nothing, and the row's own `path`/wire method
name always carries the literal call-site string, never the computed
candidate.

**`overridden_public_methods`** (D02 §2's catalog word for this style's
`members` block) is evidence-shaped, not name-shaped: a method the
implementing class declares under the SAME NAME as one the supertype itself
declares (module-local, `superclasses`/`method_visibility`'s own join), with
the implementer's OWN declared visibility `public` — never the supertype's,
since an overriding method may only be at least as visible as the one it
overrides (never narrower), so checking the implementer's own copy is both
sufficient and the only fact this style needs to read once.

**The published-stubs-jar boundary** (2O design §1b, COVERAGE §5.7): a module
whose `OrderServiceImpl` extends a `<Service>ImplBase` shipped in a
dependency jar still carries the extends EDGE — capability 9.13 reads it off
the implementer's own class file regardless of where the target lives — but
that target's own facts never reach this workspace unless the shipped
`.sextant.yml` library opt-in (D02 §4a) is used, so nothing here can read its
`SERVICE_NAME` constant, and inventing an identity from the class's simple
name would be exactly the glob-grammar guess this style refuses. Such a
class derives NOTHING from this engine — not even the unresolved fallback,
which is reserved for a supertype this workspace CAN see but whose marker
calls could not be read (CP-8(b)/(d) falsifying, not the supertype being
absent altogether). COVERAGE states the boundary; the `@GrpcService`/net.devh
annotation corroboration spec §1b describes for this exact case — surfacing
the class as a `service_identity` question when the supertype match sees
nothing at all — is not implemented by this task (see task-5-report.md)."""

import json
from dataclasses import dataclass, field
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.identity_calls import (
    all_string_arguments,
    first_string_arguments,
    outer_class,
    parsed_call_sites,
    split_call,
)
from sextant.domain.symbols import bare_descriptor, method_name

_REQUIRED_MATCHES = ("supertype_marker", "members")
_REQUIRED_MARKER = ("service_name_call", "method_name_call")
_MEMBERS = "overridden_public_methods"

# CP-8(b)/(d) falsifying for one implementer — the constants themselves
# unreadable, not merely this class's own overrides failing to correlate to
# any of them — is what earns the `service_identity` gap (2O design §1b).
_UNREADABLE = (
    "SERVICE_NAME/wire method-name constants unreadable — no "
    "ServiceDescriptor.newBuilder/generateFullMethodName call site found on "
    "the generated class this implementer extends (CP-8(b)/(d))"
)


@dataclass(frozen=True)
class _ClassMatch:
    """One implementer this workspace's own facts prove overrides at least
    one method of a LOCALLY SCANNED gRPC service base — `run`/`gaps` each
    walk this list once rather than repeating the join, since one is written
    before the 2K ledger reset and the other strictly after it (`resolve/
    service_identity.py`'s own docstring states why the split exists)."""

    implementer: str
    supertype: str
    # wire method name -> the overriding method's own FULL symbol, one entry
    # per RPC method that both (a) this class overrides and (b) the
    # generated class's own call sites named — empty exactly when CP-8(b)/(d)
    # fell through, or when nothing this class overrides correlates to any
    # of them.
    resolved: dict[str, str] = field(default_factory=dict)
    service_name: str | None = None


def run(workspace: Workspace, catalog: Catalog) -> None:
    """One row per `(wire method, overriding method)` pair `_matches` found
    resolved, plus — for an implementer whose identity could not be read at
    all — one row at `resolution: unresolved`, `path` the supertype's own
    bare descriptor verbatim (2O design §1b's own words: "expression = the
    supertype fqn verbatim"), never a fabricated package. `request_shape`/
    `response_shape` stay NULL: this style contributes the handler symbol
    only (2O design §1, the redundancy `grpc-schema.yml`'s `schema_operations`
    row still carries the descriptor-known request/response shapes for
    exactly this reason)."""
    _validate_matches(catalog)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for match in _matches(workspace, catalog):
        if match.service_name is not None and match.resolved:
            for wire_name, handler in match.resolved.items():
                path = f"{match.service_name}/{wire_name}"
                key = (catalog.protocol, catalog.direction, path, handler)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_row(catalog, path, handler, "resolved"))
        else:
            path = bare_descriptor(match.supertype)
            key = (catalog.protocol, catalog.direction, path, "")
            if key in seen:
                continue
            seen.add(key)
            rows.append(_row(catalog, path, None, "unresolved"))
    workspace.derive("call_endpoints", rows=rows)


def gaps(workspace: Workspace, catalog: Catalog) -> list[dict[str, Any]]:
    """The `service_identity` open-question rows this catalog's own
    unresolved matches earn (2O design §1b, 2G design §6) — re-walks
    `_matches` rather than reading `endpoints` back (`resolve/
    service_identity.py`'s own docstring: the unresolved row's `path` names
    the SUPERTYPE, and this ledger's own vocabulary — `open_questions.py`'s
    comment beside `service_identity` — wants the flagged CLASS, which only
    the match itself still carries)."""
    _validate_matches(catalog)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _matches(workspace, catalog):
        if match.service_name is not None and match.resolved:
            continue
        path = bare_descriptor(match.supertype)
        if path in seen:
            continue
        seen.add(path)
        rows.append(
            {
                "protocol": catalog.protocol,
                "method": None,
                "path": path,
                "question": "service_identity",
                "candidates": json.dumps(
                    [{"class": match.implementer, "reason": _UNREADABLE}],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "evidence": _UNREADABLE,
            }
        )
    return rows


def _matches(workspace: Workspace, catalog: Catalog) -> list[_ClassMatch]:
    marker = catalog.matches["supertype_marker"]
    service_owner, service_method = split_call(marker["service_name_call"])
    method_owner, method_method = split_call(marker["method_name_call"])

    call_sites = parsed_call_sites(workspace)
    service_names = first_string_arguments(call_sites, service_owner, service_method, 0)
    wire_names = all_string_arguments(call_sites, method_owner, method_method, 1)

    methods_by_class = _methods_by_class(workspace)
    known_symbols = {str(row["symbol"]) for row in workspace.query("declared_symbols")}

    matches: list[_ClassMatch] = []
    for row in workspace.query("superclasses"):
        implementer = str(row["symbol"])
        supertype = str(row["superclass"])
        if supertype not in known_symbols:
            # The published-stubs-jar boundary (module docstring): the
            # extends EDGE is this class's own fact regardless, but the
            # target's own facts never reached this workspace, so nothing
            # here proves it is a gRPC service at all.
            continue
        supertype_names = set(methods_by_class.get(supertype, {}))
        implementer_methods = methods_by_class.get(implementer, {})
        overridden_public = {
            name: symbol
            for name, (symbol, visibility) in implementer_methods.items()
            if name in supertype_names and visibility == "public"
        }
        if not overridden_public:
            # "The registration is the evidence" restated one level over: a
            # class merely extending the generated base without overriding
            # any of its methods proves nothing this style derives from.
            continue
        outer = outer_class(bare_descriptor(supertype))
        resolved = {
            wire_name: overridden_public[candidate]
            for wire_name in wire_names.get(outer, [])
            if (candidate := _decapitalized(wire_name)) in overridden_public
        }
        matches.append(
            _ClassMatch(
                implementer=implementer,
                supertype=supertype,
                resolved=resolved,
                service_name=service_names.get(outer),
            )
        )
    return matches


def _methods_by_class(workspace: Workspace) -> dict[str, dict[str, tuple[str, str]]]:
    """Every declared method, `{name: (full symbol, visibility)}` per
    enclosing class — both `enclosing` and `symbol` module-prefixed exactly
    as `effective_annotations.py`'s own `method_declarations` join already
    relies on, so no strip-then-reprefix step is needed on either side of
    the `superclasses` join above. A class declaring two overloads of one
    name keeps whichever the query's own `symbol` order visits last — RPC
    methods are never overloaded, so this never arises on a real generated
    service."""
    result: dict[str, dict[str, tuple[str, str]]] = {}
    for row in workspace.query("method_visibility"):
        enclosing = row["enclosing"]
        if enclosing is None:
            continue
        symbol = str(row["symbol"])
        name = method_name(bare_descriptor(symbol))
        result.setdefault(str(enclosing), {})[name] = (symbol, str(row["visibility"]))
    return result


def _decapitalized(name: str) -> str:
    """The one casing transform this module performs, and only to build a
    LOOKUP candidate against a name bytecode itself already declared — the
    module docstring's own distinction from deriving a WIRE name by casing,
    which is never done here."""
    return name[:1].lower() + name[1:] if name else name


def _row(catalog: Catalog, path: str, handler: str | None, resolution: str) -> dict[str, Any]:
    return {
        "protocol": catalog.protocol,
        "direction": catalog.direction,
        "method": None,
        "path": path,
        "handler": handler,
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
    """Refuses a broken catalog before any class is matched — the
    `interface_implementation._validate_matches` precedent."""
    matches = catalog.matches
    missing = [key for key in _REQUIRED_MATCHES if key not in matches]
    if missing:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` is missing "
            f"{', '.join(missing)} — `supertype_derived` needs `supertype_marker` and "
            f"`members` (2O design §1b)"
        )
    if matches["members"] != _MEMBERS:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches.members: {matches['members']}` "
            f"is not `{_MEMBERS}` (2O design §1b's only vocabulary for this style)"
        )
    marker = matches["supertype_marker"]
    missing_marker = (
        [key for key in _REQUIRED_MARKER if key not in marker]
        if isinstance(marker, dict)
        else list(_REQUIRED_MARKER)
    )
    if missing_marker:
        raise CatalogError(
            f"loading catalog {catalog.source}: `supertype_marker` is missing "
            f"{', '.join(missing_marker)} — needs `service_name_call` and `method_name_call`, "
            f"each an `{{owner, method}}` marker (2O design §1b, R11)"
        )
    for key in _REQUIRED_MARKER:
        if key in marker:
            _validate_call(catalog, marker[key], key)


def _validate_call(catalog: Catalog, declared: Any, key: str) -> None:
    """Refuses a marker whose shape the read cannot honour — `owner`/`method`
    both present and both strings. `test_catalogs_use_one_fqn_notation`
    (`tests/architecture`) is why this is `{owner, method}` rather than a
    single `Owner.Fqn#method` string: every catalog value is refused if it
    carries a `#`, which is reserved for the SCIP symbol form the fact stream
    itself uses."""
    valid = (
        isinstance(declared, dict)
        and isinstance(declared.get("owner"), str)
        and isinstance(declared.get("method"), str)
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `supertype_marker.{key}` must be "
            f"`{{owner, method}}`, got {declared!r} (2O design §1b, R11)"
        )
