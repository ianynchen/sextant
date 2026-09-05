"""`supertype_dispatch` engine for endpoint derivation (D02 §2's
`supertype_dispatch` style, 2O design §3b, Task 7b).

A sibling of `supertype_derived`, not a widening of it. Both read a supertype,
and there the resemblance stops: that style's evidence is a generated base
class the module COMPILES IN, whose own identity-building call sites carry the
address, and its match is gated on those calls being present in the module's
facts at all. Here the supertype is an abstract base shipped in a
**dependency**, which the workspace never scans and which makes no call the
module could read — so the address cannot come from it and does not: **a
TYPE-LEVEL annotation carries the address, the supertype fixes a dispatch
contract, and the members the class overrides name the operations.** Three
pieces of evidence, jointly, and none of them is what `supertype_derived`
joins.

That is also why `annotation_driven` cannot serve this: its derivation joins
METHOD symbols and states so itself — a type-level annotation mints no row of
its own (`derive_endpoints.sql:398-400`). Routing this shape through that
engine's `members` + `path_fallback` pair would compose the type's address with
each member's own NAME, minting one address per member that nobody serves
(2O design §3b).

**Everything specific is catalog data** (D02 §5): the supertype, the address
annotation and the argument spellings that carry it, the dispatch method
table — each entry a `{name, parameters, method}` triple — and the signatures
whose override bypasses dispatch entirely. This module names none of them.

**The member selector matches a name AND its parameter types, in order**
(GUIDELINES §8.1's language rule, and CP-9 rows 18/26 measuring it):
a same-named member whose parameter types differ overrides nothing, the
supertype's own implementation still applies, and a selector keyed on the name
alone would publish an address the container answers 405 to. Arity is a
consequence of the parameter list, never the rule.

**It reads no visibility at all, and that is mirroring rather than relaxing.**
CP-9 row 24: D00 §5a's `visibility` column is two-valued, so a handler
declared at a reduced-but-legal visibility is recorded as `other` and the
column cannot say which. It need not: an override may only widen the
visibility of the member it overrides, never narrow it, so a member declared
under the supertype's own name and parameter types IS the override at every
visibility the language permits. Checking the column would exclude the common
case and prove nothing about the rest.

**One row per handler the MODULE DECLARES** — which is the ruling CP-9 was run
to settle (`scripts/probes/cp9_servlet_shapes.md`, verdict 5). A dispatch
supertype may also serve operations IMPLICITLY, off a member the module never
overrode; measured, it does. Those derive nothing, for a reason that is about
evidence rather than taste: the code serving them is in a dependency this
workspace never scanned, so such a row could carry either no handler at all or
the symbol of a DIFFERENT member the implicit path happens to call — and the
second is false. It is a stated under-report in `docs/COVERAGE.md`, on the
same terms as the identical ruling 2O Task 6 made for `derived_resource`, and
it is falsified the day an endpoint row can name a handler outside the module.

**A bypass discards the CLASS, never merely the member** (CP-9 verdict 8). A
class overriding the supertype's own dispatch entry point has replaced the
lookup the table describes: measured, it serves every operation alike. Deriving
the table's entries for it anyway would publish the ones it names and withhold
the ones it does not — a wrong answer, not a partial one — so the class derives
nothing and `docs/COVERAGE.md` records the shape.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.domain.symbols import bare_descriptor, method_name, type_descriptor

_REQUIRED_MATCHES = ("supertype", "address", "members", "dispatch", "bypassed_by")
_MEMBERS = "overridden_dispatch_methods"

# A member as this style selects one: its name and its parameter types, in
# declaration order, both sides in the SCIP form the facts carry.
type _Selector = tuple[str, tuple[str, ...]]


@dataclass(frozen=True)
class _ClassMatch:
    """One class this workspace's facts show extending the catalog's declared
    supertype, carrying its address annotation, and overriding at least one
    entry of its dispatch table.

    `addresses` and `handlers` are both tuples so the row order two runs
    produce is the same one (NFR-1); `handlers` is sorted by operation, which
    is the only field of it that reaches a row's identity.
    """

    addresses: tuple[str, ...]
    handlers: tuple[tuple[str, str], ...]


def run(workspace: Workspace, catalog: Catalog) -> None:
    """One row per `(address, declared dispatch override)` pair.

    `caller`/`peer` are NULL (this is the inbound side, and the declaration is
    not a call site). `handler_signature`, `request_shape` and `response_shape`
    are NULL together and for one reason: a dispatch member's declared
    parameters are the CONTRACT'S own request and response objects, never the
    wire payload — the payload is read off a stream at runtime, which no static
    read can see. A non-NULL `handler_signature` is precisely what tells
    `derive_endpoint_contracts.sql` a row wants owner-keyed shape expansion, so
    writing one here would publish the dependency's API as this module's
    contract.

    `resolution` is always `resolved`: an address argument is a compile-time
    constant of the declaration itself, and the one this style cannot read is
    the one that derives no row at all rather than an unresolved one.
    """
    _validate_matches(catalog)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for match in _matches(workspace, catalog):
        for address in match.addresses:
            for operation, handler in match.handlers:
                key = (catalog.protocol, catalog.direction, operation, address)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_row(catalog, operation, address, handler))
    workspace.derive("call_endpoints", rows=rows)


def _matches(workspace: Workspace, catalog: Catalog) -> list[_ClassMatch]:
    matches = catalog.matches
    supertype = type_descriptor(str(matches["supertype"]))
    address = matches["address"]
    annotation = type_descriptor(str(address["annotation"]))
    keys = [str(key) for key in address["args"]]
    dispatch = {_selector(entry): str(entry["method"]) for entry in matches["dispatch"]}
    bypass = {_selector(entry) for entry in matches["bypassed_by"]}

    addresses_by_class = _addresses(workspace, annotation, keys)
    members_by_class = _members(workspace)

    found: list[_ClassMatch] = []
    for row in workspace.query("superclasses"):
        implementer = str(row["symbol"])
        if bare_descriptor(str(row["superclass"])) != supertype:
            # Ordinary inheritance, or a different contract entirely. The
            # DIRECT edge only: `superclasses` carries one hop, so a class
            # reaching the supertype through an intermediate base of its own
            # is invisible here — a stated boundary in `docs/COVERAGE.md`,
            # never a guess at what the intermediate declares.
            continue
        addresses = addresses_by_class.get(implementer)
        if not addresses:
            # No declaration, or one whose address argument could not be read.
            # Either way nothing registers this class at an address, and an
            # address is what a row asserts.
            continue
        members = members_by_class.get(implementer, {})
        if bypass & set(members):
            continue
        handlers = tuple(
            sorted(
                (dispatch[selector], symbol)
                for selector, symbol in members.items()
                if selector in dispatch
            )
        )
        if not handlers:
            # Registered, and serving nothing the table describes. "The
            # registration is the evidence" needs both conjuncts.
            continue
        found.append(_ClassMatch(addresses=addresses, handlers=handlers))
    return found


def _addresses(
    workspace: Workspace, annotation: str, keys: list[str]
) -> dict[str, tuple[str, ...]]:
    """Every annotated type's own declared addresses, keyed by the type's own
    FULL symbol — the coordinate space `annotations.target` shares with
    `superclasses.symbol`.

    The RAW annotation table, deliberately, not `resolve/effective_annotations`'s
    composed view: the contract that reads this annotation reads the literal
    one written on the class, resolving neither meta-annotations nor
    inheritance (its own declaration is `@Target(TYPE)` and carries no
    `@Inherited`). Reading the composed view would derive rows for a shape the
    contract does not serve, which is §8.1 rule 4 exactly.

    `keys` is a PRECEDENCE list, and the first one present wins rather than
    the union: the spellings are aliases of one attribute, and a declaration
    writing both is one the contract itself refuses to deploy — so there is no
    address to union, and reading past the key the author wrote would answer
    with a different attribute than the one they named.
    """
    result: dict[str, tuple[str, ...]] = {}
    for row in workspace.query("annotations"):
        if str(row["annotation"]) != annotation:
            continue
        args = json.loads(str(row["args"])) if row["args"] is not None else {}
        declared = next((key for key in keys if key in args), None)
        if declared is None:
            continue
        # Non-string entries are dropped rather than published: an address
        # argument is a compile-time constant, so every element the compiler
        # writes is a string, and anything else is a value this read cannot
        # see. That holds as long as the annotation's address attribute stays
        # a string-typed one — an attribute admitting a nested annotation
        # would need a reader, not a filter.
        values = tuple(dict.fromkeys(value for value in _strings(args[declared]) if value))
        if values:
            result[str(row["target"])] = values
    return result


def _strings(value: Any) -> list[str]:
    """An address argument's own string values.

    Both spellings are accepted because both are legal facts: a multi-valued
    attribute reaches the stream as a list even when one value was written
    (CP-9 row 23), and D00 §5's `LiteralValue` also admits a bare string, which
    a hand-built or non-scanner-written fact may carry.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, str)]
    return []


def _members(workspace: Workspace) -> dict[str, dict[_Selector, str]]:
    """Every declared method as `{selector: full symbol}` per enclosing type.

    Keyed on name AND parameter types (the module docstring's language rule),
    which also makes the map total: two members of one type can share a name,
    and they can never share a selector, so nothing is silently overwritten
    the way a name-keyed map would overwrite it.
    """
    result: dict[str, dict[_Selector, str]] = {}
    for row in workspace.query("method_declarations"):
        enclosing = row["enclosing"]
        if enclosing is None:
            continue
        symbol = str(row["symbol"])
        signature = json.loads(str(row["signature"])) if row["signature"] is not None else {}
        parameters = tuple(
            str((parameter.get("type") or {}).get("symbol", ""))
            for parameter in signature.get("parameters") or []
        )
        selector = (method_name(bare_descriptor(symbol)), parameters)
        result.setdefault(str(enclosing), {})[selector] = symbol
    return result


def _selector(entry: dict[str, Any]) -> _Selector:
    return (
        str(entry["name"]),
        tuple(type_descriptor(str(parameter)) for parameter in entry["parameters"]),
    )


def _row(catalog: Catalog, operation: str, address: str, handler: str) -> dict[str, Any]:
    return {
        "protocol": catalog.protocol,
        "direction": catalog.direction,
        "method": operation,
        "path": address,
        "handler": handler,
        "caller": None,
        "peer": None,
        "handler_signature": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "catalog_id": catalog.id,
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before any class is matched — the
    `interface_implementation._validate_matches` precedent.

    Every key here could be WRONG without being INVALID (GUIDELINES §10's own
    test for a guard), and the `dispatch` parameter list is the sharpest of
    them: omitted, it would read as a name-only selector, which CP-9 row 18
    measured publishing an address nothing serves.
    """
    matches = catalog.matches
    missing = [key for key in _REQUIRED_MATCHES if key not in matches]
    if missing:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` is missing "
            f"{', '.join(missing)} — `supertype_dispatch` needs `supertype`, `address`, "
            f"`members`, `dispatch` and `bypassed_by` (2O design §3b). `bypassed_by` may "
            f"be empty, but a supertype with no bypass says so rather than omitting it"
        )
    if not isinstance(matches["supertype"], str):
        raise CatalogError(
            f"loading catalog {catalog.source}: `supertype` must be a dotted type name, "
            f"got {matches['supertype']!r} (2O design §3b)"
        )
    if matches["members"] != _MEMBERS:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches.members: {matches['members']}` "
            f"is not `{_MEMBERS}` (2O design §3b's only vocabulary for this style)"
        )
    _validate_address(catalog, matches["address"])
    _validate_selectors(catalog, matches["dispatch"], "dispatch", operation=True)
    _validate_selectors(catalog, matches["bypassed_by"], "bypassed_by", operation=False)


def _validate_address(catalog: Catalog, declared: Any) -> None:
    valid = (
        isinstance(declared, dict)
        and isinstance(declared.get("annotation"), str)
        and isinstance(declared.get("args"), list)
        and bool(declared["args"])
        and all(isinstance(key, str) for key in declared["args"])
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `address` must be "
            f"`{{annotation, args}}` — a dotted annotation name and a non-empty list of "
            f"the argument spellings that carry the address, most preferred first — got "
            f"{declared!r} (2O design §3b)"
        )


def _validate_selectors(catalog: Catalog, declared: Any, key: str, *, operation: bool) -> None:
    """Refuses a member table whose entries the selector cannot honour.

    `dispatch` must be non-empty — a style deriving from overridden members
    with no member to look for derives nothing at all, silently, which is the
    permanently-quiet rule §10 warns about. `bypassed_by` may be empty: that
    is a claim, and an explicit one.
    """
    entries = declared if isinstance(declared, list) else None
    valid = entries is not None and (bool(entries) or not operation)
    if valid:
        assert entries is not None
        for entry in entries:
            if not (
                isinstance(entry, dict)
                and isinstance(entry.get("name"), str)
                and isinstance(entry.get("parameters"), list)
                and all(isinstance(parameter, str) for parameter in entry["parameters"])
                and (not operation or isinstance(entry.get("method"), str))
            ):
                valid = False
                break
    if not valid:
        shape = "{name, parameters, method}" if operation else "{name, parameters}"
        raise CatalogError(
            f"loading catalog {catalog.source}: `{key}` must be a "
            f"{'non-empty ' if operation else ''}list of `{shape}` entries — a member is "
            f"identified by its name AND its parameter types in order, so an entry naming "
            f"no `parameters` is a selector the language does not have (GUIDELINES §8.1) — "
            f"got {declared!r} (2O design §3b)"
        )
