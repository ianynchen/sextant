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
itself already declared (`overridden_public_methods`, below); the row's own
`path`/wire method name always carries the literal call-site string, never
the computed candidate. **That lookup is not injective either, and it
REFUSES rather than guesses** (fix round 2, I-1, `_correlated`): where two
wire names decapitalize onto one override, both are refused — the row would
otherwise attribute one handler to two RPCs, at least one of them falsely —
and where an override no wire name reaches (`mixedLower` moved further than
decapitalization) is found beside siblings that correlated, it is filed as a
`service_identity` gap instead of dropped.

**The match itself is gated on the marker CALL's presence, before any of
that** (fix round 2, C-1). Extending a module-local class and publicly
overriding one of its methods is ordinary class inheritance, not evidence of
a gRPC service — every abstract-base/template-method pair in a real
repository is shaped that way — so the supertype's own outer class must be
one this workspace's facts show MAKING the identity-building marker call
before anything matches at all. Whether that call's ARGUMENTS can be read is
a separate question, answered after the match, and it decides only
resolved-versus-unresolved: 2O design §1b states the match as "a class whose
extends target is itself in the module's facts AND declares the marker", and
both conjuncts are load-bearing. No marker call is NO ROW AND NO QUESTION;
an unreadable marker argument is the unresolved row plus the question.

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
nothing at all — now ships beside it, on `annotation_driven.gaps`
(`grpc-spring.yml`), so silence is no longer the outcome for an annotated
service built against published stubs."""

import json
from dataclasses import dataclass, field
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.identity_calls import (
    all_string_arguments,
    calling_classes,
    first_string_arguments,
    outer_class,
    parsed_call_sites,
    split_call,
)
from sextant.domain.symbols import bare_descriptor, method_name

_REQUIRED_MATCHES = ("supertype_marker", "members")
_REQUIRED_MARKER = ("service_name_call", "method_name_call")
_MEMBERS = "overridden_public_methods"

# CP-8(b)/(d) falsifying for one implementer — the marker calls ARE on the
# supertype's own generated class (that is what made this a match at all,
# `_matches`'s own gate), and their arguments could not be read — is what
# earns the `service_identity` gap (2O design §1b). A class whose supertype
# makes no marker call at all earns neither this nor a row: nothing proves it
# is a service, and saying otherwise is the fabrication (fix round 2, C-1).
_UNREADABLE = (
    "SERVICE_NAME/wire method-name constants unreadable — the generated class "
    "this implementer extends makes the ServiceDescriptor.newBuilder/"
    "generateFullMethodName marker call, but no resolved string literal reached "
    "the argument carrying the identity (CP-8(b)/(d))"
)

# Two wire method names decapitalizing onto ONE candidate override name
# (`GetOrder` and `getOrder` are different RPCs and both compile to the one
# override `getOrder` — CP-8(d)'s own caution, and why the reverse derivation is
# refused outright). Deriving a row for each against the one override
# attributes the same handler twice, and at least one of those attributions is
# false — so neither derives, and the ambiguity is what the ledger carries
# instead (fix round 2, I-1).
_AMBIGUOUS = (
    "wire method names {names} all decapitalize to the single override "
    "`{candidate}` — which of them that override serves is not derivable, and "
    "attributing it to each would publish a false handler (CP-8(d))"
)

# An override the generated class names no wire method for: the stub
# generator's own `mixedLower` transform of a proto method name can exceed
# decapitalization (`rpc list_orders` compiles to `listOrders`), and it is not
# invertible. Dropping such a method silently — no row and no gap, while its
# PascalCase siblings derive normally — is the failure this reason refuses
# (fix round 2, I-1).
_UNCORRELATED = (
    "overridden public methods {names} correlate to no wire method name the "
    "generated class declares — the wire-name-to-compiled-name transform is not "
    "invertible by decapitalization alone, so which operation each serves is "
    "unread (CP-8(d))"
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
    # generated class's own call sites named UNAMBIGUOUSLY — empty exactly
    # when CP-8(b)/(d) fell through, or when nothing this class overrides
    # correlates to any of them.
    resolved: dict[str, str] = field(default_factory=dict)
    service_name: str | None = None
    # CP-8(b)/(d) falsified: the marker calls are on the generated class (the
    # gate that made this a match at all), and their identity-carrying
    # arguments are not readable. Distinct from "readable, and nothing
    # correlated" below — a different gap, with a different reason.
    unreadable: bool = False
    # Wire method names refused because two or more of them share a single
    # candidate override name (I-1). BOTH are refused; one is never picked.
    ambiguous: tuple[str, ...] = ()
    # Overridden public method names the readable wire-name inventory does not
    # account for (I-1) — filed as a gap rather than dropped silently.
    uncorrelated: tuple[str, ...] = ()


def run(workspace: Workspace, catalog: Catalog) -> None:
    """One row per `(wire method, overriding method)` pair `_matches` found
    resolved, plus — for an implementer whose identity could not be read at
    all, or one whose wire names collide onto a single override (I-1) — one
    row at `resolution: unresolved`, `path` the supertype's own bare
    descriptor verbatim (2O design §1b's own words: "expression = the
    supertype fqn verbatim"), never a fabricated package.

    `request_shape`/`response_shape` are written NULL here because this style
    contributes the handler symbol only — and, where a descriptor covers the
    same identity, they do NOT stay NULL: `schema_operations` STAMPS both
    columns onto this row afterwards (it is in `resolve/endpoints.py`'s
    `_RUNS_LAST` precisely so it can), so the merged row carries this side's
    handler AND the descriptor's own request/response contracts and streaming
    word. 2O design §1's redundancy is a merge of both halves, not a choice
    between them (fix round 2, C-2)."""
    _validate_matches(catalog)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for match in _matches(workspace, catalog):
        if match.service_name is not None:
            for wire_name, handler in match.resolved.items():
                path = f"{match.service_name}/{wire_name}"
                key = (catalog.protocol, catalog.direction, path, handler)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_row(catalog, path, handler, "resolved"))
        if match.resolved and not match.ambiguous:
            # Everything readable about this class was read, and every wire
            # name it named correlated to exactly one override. An
            # `uncorrelated` override alone earns the ledger row `gaps` files
            # and no endpoint row: its siblings already published this
            # service's presence, and a second row at the supertype's own
            # descriptor would count the same boundary twice (fix round 2,
            # I-1).
            continue
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
        reason = _reason(match)
        if reason is None:
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
                    [{"class": match.implementer, "reason": reason}],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "evidence": reason,
            }
        )
    return rows


def _reason(match: _ClassMatch) -> str | None:
    """What this match leaves unanswered, or `None` when it leaves nothing.

    Three independent failures can co-occur on one class — an unreadable
    identity, an ambiguous wire-name collision, an override no wire name
    accounts for — so the reason is composed rather than picked: a ledger row
    naming only the first would hide the rest, which is the same silent drop
    I-1 exists to refuse.
    """
    reasons: list[str] = []
    if match.unreadable:
        reasons.append(_UNREADABLE)
    if match.ambiguous:
        # Regrouped rather than carried pre-grouped: `ambiguous` is the flat
        # list of REFUSED wire names, which is what `run` reads, and one class
        # can collide on more than one candidate. Sorted so two runs compose
        # the identical sentence (NFR-1).
        grouped: dict[str, list[str]] = {}
        for wire_name in match.ambiguous:
            grouped.setdefault(_decapitalized(wire_name), []).append(wire_name)
        reasons.extend(
            _AMBIGUOUS.format(names=", ".join(names), candidate=candidate)
            for candidate, names in sorted(grouped.items())
        )
    if match.uncorrelated:
        reasons.append(_UNCORRELATED.format(names=", ".join(match.uncorrelated)))
    return "; ".join(reasons) if reasons else None


def _matches(workspace: Workspace, catalog: Catalog) -> list[_ClassMatch]:
    marker = catalog.matches["supertype_marker"]
    service_owner, service_method = split_call(marker["service_name_call"])
    method_owner, method_method = split_call(marker["method_name_call"])

    call_sites = parsed_call_sites(workspace)
    # THE GATE (fix round 2, C-1, and 2O design §1b's own second conjunct:
    # "a class whose extends target is itself in the module's facts AND
    # declares the marker"). Read BEFORE anything is matched, and separately
    # from what the marker says: without it the match is "extends a
    # module-local class and publicly overrides one of its methods", which
    # every abstract-base/template-method pair in an ordinary repository
    # satisfies — and each of them would then mint an inbound gRPC boundary
    # plus a ledger question on no gRPC evidence whatsoever. Marker-call
    # PRESENCE is what makes the supertype a generated service base; the
    # marker's ARGUMENTS only decide resolved-versus-unresolved below.
    marked = calling_classes(call_sites, service_owner, service_method) | calling_classes(
        call_sites, method_owner, method_method
    )
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
        outer = outer_class(bare_descriptor(supertype))
        if outer not in marked:
            # Ordinary class inheritance. No evidence means NO ROW, never an
            # unresolved one (the gate above).
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
        service_name = service_names.get(outer)
        wires = wire_names.get(outer, [])
        if service_name is None or not wires:
            # The marker call is there (the gate) and its argument is not —
            # CP-8(b)/(d) falsified for this class. Unresolved, plus a gap.
            matches.append(
                _ClassMatch(implementer=implementer, supertype=supertype, unreadable=True)
            )
            continue
        matches.append(_correlated(implementer, supertype, service_name, wires, overridden_public))
    return matches


def _correlated(
    implementer: str,
    supertype: str,
    service_name: str,
    wires: list[str],
    overridden_public: dict[str, str],
) -> _ClassMatch:
    """The wire-name-to-override correlation, and the two ways it can refuse
    to answer (fix round 2, I-1).

    The direction is the safe one — a proto-cased wire name bytecode itself
    declared is decapitalized to build a LOOKUP candidate, never the reverse —
    but the lookup is not injective, and both of its failure modes were
    silent before this fix. **Two wire names onto one candidate** (`GetOrder`
    and `get_order` are distinct RPCs and both compile to `getOrder`) refuses
    BOTH rather than attributing one override to each, because at least one of
    those attributions would be false and nothing here can say which. **An
    override no wire name reaches** — the stub generator's `mixedLower` can
    exceed decapitalization — is carried out as `uncorrelated` rather than
    dropped, so a method whose RPC could not be identified is a visible gap
    instead of an absence.
    """
    by_candidate: dict[str, list[str]] = {}
    for wire_name in wires:
        by_candidate.setdefault(_decapitalized(wire_name), []).append(wire_name)
    resolved: dict[str, str] = {}
    ambiguous: list[str] = []
    for candidate, spellings in by_candidate.items():
        if candidate not in overridden_public:
            continue
        if len(spellings) > 1:
            ambiguous.extend(sorted(spellings))
            continue
        resolved[spellings[0]] = overridden_public[candidate]
    # Both the resolved and the refused candidates are ACCOUNTED FOR; what is
    # left is an override the wire-name inventory never named at all.
    uncorrelated = tuple(sorted(set(overridden_public) - set(by_candidate)))
    return _ClassMatch(
        implementer=implementer,
        supertype=supertype,
        resolved=resolved,
        service_name=service_name,
        ambiguous=tuple(ambiguous),
        uncorrelated=uncorrelated,
    )


def _methods_by_class(workspace: Workspace) -> dict[str, dict[str, tuple[str, str]]]:
    """Every declared method, `{name: (full symbol, visibility)}` per
    enclosing class — both `enclosing` and `symbol` module-prefixed exactly
    as `effective_annotations.py`'s own `method_declarations` join already
    relies on, so no strip-then-reprefix step is needed on either side of
    the `superclasses` join above.

    **A class declaring two overloads of one name keeps whichever the query's
    own `symbol` order visits last, and that is safe only because
    `_correlated` refuses the case outright** (fix round 2, I-1). The earlier
    claim here — "RPC methods are never overloaded, so this never arises" —
    was wrong in precisely the situation that matters: proto `GetOrder` and
    `getOrder` are two RPCs, both compile to one `getOrder`, and since their
    request messages differ they are two legal overloads of it. So the
    overload IS reachable, this map does drop one of the two, and the
    correlation above therefore attributes NEITHER — both wire names are
    refused and the ambiguity is filed as a gap, so which of the two symbols
    survived here can never reach a row."""
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
    which is never done here.

    Not injective, and both directions of that are handled rather than
    assumed (`_correlated`, fix round 2's I-1): two wire names can produce one
    candidate, and a wire name whose real compiled spelling the `mixedLower`
    transform moved further than decapitalization produces a candidate that
    matches nothing. The first refuses both; the second leaves the override
    `uncorrelated`, which is a gap."""
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
