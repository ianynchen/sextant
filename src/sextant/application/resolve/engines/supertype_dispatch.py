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

**A bypass discards a class that declares NO member of the dispatch table**
(CP-9 verdict 8, as amended for `A-M2`). A class overriding the supertype's own
dispatch entry point and declaring nothing else has replaced the lookup the
table describes: measured, it serves every operation alike, and deriving the
table's entries for it would publish the ones it names and withhold the ones it
does not — a wrong answer, not a partial one.

**A class that overrides the entry point AND declares dispatch members derives
them.** That qualifier was missing, and its absence cost such a class its whole
surface. CP-9 rows 35-40 measure the shape on both `service` signatures and all
three containers: a wrapper delegating through `super.service(req, resp)` with
`doGet`/`doPost` declared serves GET and POST and refuses PUT — the dispatch
still runs, and the table describes it exactly. §5.4 in one line: a verdict is
bounded by the configuration it measured.
"""

import json
from dataclasses import dataclass
from typing import Any, cast

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import ancestry_of
from sextant.application.resolve.shapes.rooting import catalog_symbols
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
    # A LIST or a scalar (§3.1): the abstract base may be reachable under more
    # than one name — the javax/jakarta case is NOT this (those are separate
    # catalogs, §3.3), but a base renamed between major versions of one library is.
    supertypes = catalog_symbols(matches["supertype"], f"{catalog.source}: matches.supertype")
    address = matches["address"]
    annotation = type_descriptor(address["annotation"])
    keys = [str(key) for key in address["args"]]
    dispatch = {_selector(entry): str(entry["method"]) for entry in matches["dispatch"]}
    bypass = {_selector(entry) for entry in matches["bypassed_by"]}

    addresses_by_class = _addresses(workspace, annotation, keys)
    members_by_class = _members(workspace)
    delegating = _delegating_members(workspace, supertypes)

    # F3 §4.2 (W22): the CLOSURE, not the direct edge. `superclasses` carries one hop,
    # so a class reaching `HttpServlet` through an intermediate base of its own —
    # `class Orders extends AbstractBaseServlet extends HttpServlet` — was invisible
    # here and derived nothing. That was a stated boundary in `docs/COVERAGE.md` rather
    # than a guess, and it stayed one only because the hierarchy was not available;
    # `type_hierarchy` is that hierarchy, so the boundary closes rather than being
    # restated.
    #
    # It is still not a guess about the intermediate: the walk crosses only ancestors
    # this workspace SCANNED, so a chain running through a class in a jar stops there
    # and derives nothing, exactly as before.
    reaches = _reaching(workspace, supertypes)
    members_by_bare: dict[str, dict[_Selector, str]] = {}
    for enclosing, selectors in members_by_class.items():
        members_by_bare.setdefault(bare_descriptor(enclosing), {}).update(selectors)

    found: list[_ClassMatch] = []
    for row in workspace.query("superclasses"):
        implementer = str(row["symbol"])
        if bare_descriptor(implementer) not in reaches:
            continue
        addresses = addresses_by_class.get(implementer)
        if not addresses:
            # No declaration, or one whose address argument could not be read.
            # Either way nothing registers this class at an address, and an
            # address is what a row asserts.
            continue
        # The leaf's members AND every scanned intermediate's, because the dispatch
        # contract is a property of the whole chain. This also stops a handler declared
        # on the intermediate — `Base.doGet`, address on the leaf — from being invisible,
        # which unioning only for the bypass would have left open.
        members = dict(members_by_class.get(implementer, {}))
        for link in reaches.get(bare_descriptor(implementer), ()):
            # `members_by_class` is keyed by the MODULE-PREFIXED enclosing symbol while
            # a chain link is bare, so the lookup goes through the bare-keyed view built
            # once above rather than through a second pass over the declarations.
            for selector, symbol in members_by_bare.get(link, {}).items():
                members.setdefault(selector, symbol)
        handlers = tuple(
            sorted(
                (dispatch[selector], symbol)
                for selector, symbol in members.items()
                if selector in dispatch
            )
        )
        overridden = {symbol for selector, symbol in members.items() if selector in bypass}
        if not all(symbol in delegating for symbol in overridden):
            # THE BYPASS, and it is the whole measured rule rather than half of
            # it. The dispatch the table describes runs only where EVERY
            # override of its entry point calls back into the supertype's own
            # implementation; an override that does not has replaced the lookup,
            # and the table then describes nothing about the class.
            #
            # Three configurations, all measured, on all three CP-9 containers
            # and BOTH entry-point signatures:
            #
            #   * rows 14-15 — the entry point overridden, no dispatch member
            #     anywhere: GET 200 and PUT 200. Every operation alike.
            #   * rows 35-40 — overridden and DELEGATING through
            #     `super.service(req, resp)`, `doGet`/`doPost` declared: GET
            #     200, POST 200, PUT **405**. The dispatch still runs and the
            #     table describes the class exactly.
            #   * rows 41-43 — the same class with the delegation removed: GET
            #     200, POST 200, PUT **200**. The table would claim GET and
            #     POST and deny PUT, which the container serves.
            #
            # The verdict was generalised past its measurement twice, in
            # OPPOSITE directions. First rows 14-15's "a bypass discards the
            # class" was applied to the delegating wrapper, costing the
            # commonest real form its whole surface (`A-M2`). Then rows 35-40's
            # "such a class derives its operations" was applied to the
            # non-delegating one, publishing operations whose members never run
            # and denying one the container answers. Rows 41-43 are the
            # measurement that separates the two, and the fact that separates
            # them is in the stream: rows 44 and 46 read `invoke_kind: special`
            # on a `<supertype>#service` target out of each delegating
            # override, and row 45 reads ABSENT out of the non-delegating one.
            #
            # NO NEW CATALOG KEY. Which members bypass is `bypassed_by`; what
            # delegation MEANS is this style's own semantics — a call back into
            # the `supertype` the catalog already declares — so a second
            # framework of this shape needs no new word. `call_site` is in both
            # servlet catalogs' `requires`, so a scan that produced no call
            # sites SKIPS the catalog and says so, rather than reading every
            # delegating override as a replacement.
            #
            # THIS IS ALSO WHAT MAKES `bypassed_by` LOAD-BEARING AGAIN. Under
            # the `and not handlers` qualifier it reached only classes the
            # branch below reached anyway — dead catalog vocabulary that looked
            # live (§5.3), and three near-misses claimed to pin it while the
            # guard harness measured that none of them did.
            continue
        if not handlers:
            # Registered, and serving nothing the table describes. "The
            # registration is the evidence" needs both conjuncts.
            continue
        found.append(_ClassMatch(addresses=addresses, handlers=handlers))
    return found


def _reaching(workspace: Workspace, supertypes: tuple[str, ...]) -> dict[str, list[str]]:
    """Every scanned type that reaches one of `supertypes` through any number of
    SCANNED superclasses (F3 §4.2).

    Reads `dispatch.ancestry_of` — the index `type_hierarchy` is built FROM — rather
    than walking `superclasses` again here, which would be a second answer to a question
    D01 says is answered once. *This said it reads the TABLE, which it does not and must
    not: the table is written by `record_call_edges`, so an engine reading it would
    derive nothing whenever that pass had not run first, and an empty table is
    indistinguishable from a genuine no-match.*

    Only `extends` edges: this style's contract is a dispatch an abstract CLASS
    performs (`HttpServlet.service` reading the request method), and an interface
    declares no such body. An unscanned link stops the chain, because what the
    intermediate declares is then genuinely unknown.
    """
    # `dispatch._ancestry`, not the `type_hierarchy` TABLE. One implementation of the
    # walk either way — but the table is written by `record_call_edges`, and an engine
    # reading it would derive NOTHING whenever that pass had not run first. In the
    # pipeline it always has; in a harness calling `derive_endpoints` alone it has not,
    # and the failure is silent: an empty table and an empty result look identical.
    # Reading the index the table is built FROM removes the ordering dependency
    # without duplicating the rule.
    ancestors, _scanned = ancestry_of(workspace)
    parents: dict[str, list[str]] = {
        child: [ancestor for ancestor, kind, _ in edges if kind == "extends"]
        for child, edges in ancestors.items()
    }
    # The chain from each class UP TO the named supertype, exclusive — every scanned
    # link between the two. The bypass below has to see all of them: an intermediate
    # that overrides the entry point and does NOT delegate has replaced the dispatch,
    # and the verb table then describes nothing about the leaf. Returning only the set
    # of matching classes hid exactly that, and it is the commonest reason anyone writes
    # an intermediate base servlet — measured: with `AbstractBaseServlet.service`
    # replacing the lookup, `GET /orders` was published while the container also serves
    # PUT, which is CP-9 rows 41-43's "a wrong answer, not a partial one".
    reaching: dict[str, list[str]] = {}
    for child, direct in parents.items():
        seen: set[str] = set()
        walked: list[str] = []
        frontier = list(direct)
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if current in supertypes:
                reaching[child] = walked
                break
            walked.append(current)
            # A chain through a class this workspace never read STOPS here, and it does
            # so structurally rather than by a test: `parents` is built from the
            # `superclass` facts of DECLARED symbols, so a type we did not scan has no
            # entry and contributes no next link. Measured across both corpora — 62 and
            # 40 types with parent edges, none of them unscanned.
            #
            # An explicit `if current in scanned` stood here and was DEAD: removing it
            # changed no test and no corpus count, because the condition can never be
            # false for a node that has edges. It read as the safety property while
            # being unreachable, which is worse than the structural guarantee stated
            # plainly. The target itself must NOT be gated that way in any case —
            # `HttpServlet` ships in the servlet API and is never scanned.
            frontier.extend(parents.get(current, ()))
    return reaching


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

    `keys` is an ALIAS SET, and EXACTLY ONE of them must be written. They are
    spellings of a single attribute, so there is no union to take; and a
    declaration writing more than one is one the contract itself refuses to
    deploy, so such a class is registered at no address at all and every
    candidate value would be a fabricated one. Order-independent by
    construction, which is what makes the answer the same whichever key the
    compiler happened to write first.
    """
    result: dict[str, tuple[str, ...]] = {}
    for row in workspace.query("annotations"):
        if str(row["annotation"]) != annotation:
            continue
        args = json.loads(str(row["args"])) if row["args"] is not None else {}
        written = [key for key in keys if key in args]
        if len(written) != 1:
            continue
        declared = written[0]
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


def _delegating_members(workspace: Workspace, supertypes: tuple[str, ...]) -> frozenset[str]:
    """Every method symbol that calls the SUPERTYPE's own implementation of the
    method it is — the override that lets the supertype's dispatch keep running.

    `invoke_kind: special` and nothing else, which is the exact mirror rather
    than a convenience: a virtual call on a supertype-typed value is a call to
    somebody ELSE's object, and a virtual self-call would not reach the
    supertype's implementation at all. Measured in the stream (CP-9 rows 44 and
    46, all three containers and both entry-point signatures): a delegating
    override's `super`-call arrives as `special`, with the SUPERTYPE as the
    target's owner and the member's own name.

    The name is compared and the parameter types are not, and that is the one
    place this is deliberately looser than §8.1's language rule. What is being
    asked is "does control return to the supertype's dispatch", and the two
    entry points delegate into each other — the public one's `super` call lands
    on the other signature. Comparing parameter types would read that as no
    delegation at all. The looseness costs an over-report only where an
    override calls a DIFFERENT overload of its own name on the supertype and
    then declines to dispatch, which no measured configuration does.

    An owner outside the module is normal here and is why the comparison is on
    bare descriptors: the supertype ships in a dependency this workspace never
    scans, so only the call site is ours.
    """
    delegating: set[str] = set()
    for row in workspace.query("call_sites"):
        if str(row["invoke_kind"]) != "special":
            continue
        caller = str(row["caller"])
        if bare_descriptor(str(row["owner"] or "")) not in supertypes:
            continue
        if str(row["name"]) != method_name(bare_descriptor(caller)):
            continue
        delegating.add(caller)
    return frozenset(delegating)


def _members(workspace: Workspace) -> dict[str, dict[_Selector, str]]:
    """Every declared method as `{selector: full symbol}` per enclosing type.

    Keyed on name AND parameter types (the module docstring's language rule),
    which also makes the map total: two members of one type can share a name,
    and they can never share a selector, so nothing is silently overwritten
    the way a name-keyed map would overwrite it.

    Both halves of the key are BARE descriptors, matching the coordinate space
    `_matches` compares the supertype in: D00 §5a's symbol is module
    coordinates then a descriptor, and only the descriptor is ever compared.
    Normalising one side and not the other would be a rule the language does
    not have, and its failure mode is a member that matches nothing —
    silently.
    """
    result: dict[str, dict[_Selector, str]] = {}
    for row in workspace.query("method_declarations"):
        enclosing = row["enclosing"]
        if enclosing is None:
            continue
        symbol = str(row["symbol"])
        signature = cast(dict[str, Any], row["signature"] or {})
        # `erased_symbol` — the DESCRIPTOR's own answer — not `type.symbol`, which
        # is the signature's where there is one and so reads a bare type VARIABLE
        # for a generic parameter. This selector is matched against a
        # catalog-declared parameter type, which names a real type; a variable's
        # name is scoped to its own declaration and can match nothing.
        parameters = tuple(
            bare_descriptor(
                str(
                    parameter.get("erased_symbol")
                    or (parameter.get("type") or {}).get("symbol", "")
                )
            )
            for parameter in signature.get("parameters") or []
        )
        selector = (method_name(bare_descriptor(symbol)), parameters)
        result.setdefault(str(enclosing), {})[selector] = symbol
    return result


def _selector(entry: dict[str, Any]) -> _Selector:
    return (
        str(entry["name"]),
        tuple(type_descriptor(parameter) for parameter in entry["parameters"]),
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
    if not isinstance(matches["supertype"], (str, list)):
        raise CatalogError(
            f"loading catalog {catalog.source}: `supertype` must be a dotted type name "
            f"or a list of them (§3.1), got {matches['supertype']!r} (2O design §3b)"
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
            f"the argument spellings that carry the address, of which a declaration "
            f"writes exactly one — got {declared!r} (2O design §3b)"
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
