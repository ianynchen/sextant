"""Which method a call site can actually run — the JVM's own dispatch rule,
mirrored rather than approximated (DR-6).

**One rule, one place, because there is already going to be a second.**
[M04](docs/components/M04-resolver.md) §4 designs a `dispatch`/`dispatch_site`
pair with rapid type analysis narrowing candidates to types the program
constructs; none of it is built, and `docs/open-issues.md` OI-16 records that
the day it lands there will be two answers to one question. `G3` answered it
inline for `return_flows`; `G4` needs the identical answer for `call_edges`.
Deriving it twice would have made OI-16 a three-way disagreement, so the rule
moved here and both passes read it. This module is a MOVE of `return_flow`'s
own resolution, not a new rule: its behaviour, its comments and the two guards
that pin it are the ones `G3` shipped.

## The rule

The caller-to-callee join is **arithmetic, not a lookup** (`domain/symbols
.method_descriptor`): a `call_site` carries owner, name and JVM descriptor, and
a method's own symbol is that owner and name with the first four bytes of the
SHA-256 of the descriptor. So asking what one site calls costs a hash, and a
callee outside the workspace produces a descriptor that matches nothing rather
than an error.

- `invokestatic` and `invokespecial` name the method that runs, exactly. A
  private call, a `super.` call and a constructor have no virtual dispatch, so
  no implementation of anything is a candidate for them. A static method is
  HIDDEN by a subclass's, never overridden.
- `invokevirtual` and `invokeinterface` dispatch on the receiver's runtime
  class, so the candidates are the declared method **where it has a body** plus
  every in-module override of it. One candidate is `resolved`; several are
  `narrowed`, all listed, none picked — the roadmap's own rule for 2Q, and the
  same refusal the extractor already applies to a merged value.
- `invokedynamic` names no callee at all in its target: the target is the
  BOOTSTRAP factory, and the body the site creates is `call_site.implementation`
  (capability 9.17). What each reader does with that differs, so it is not
  decided here — `return_flow` excludes such sites whole, `call_edges` follows
  the implementation. Both need the constant, which is why it lives here.

## Where a candidate set stops

A call whose callee this workspace never scanned yields no candidate. That is
the third-party boundary as ruled: a mapper, a repository, a driver, anything
in the JDK — the call IS the terminal, and a candidate claiming to know its
body would be the cardinal sin. Measured on `macrozheng/mall`'s `mall-admin`,
it is also the common case.

A candidate is kept only where the workspace read its BODY, and "read its body"
is asked as "did the extractor emit a `method_return` fact for it": an abstract
or interface declaration is a scanned symbol with no returns, and every
analysable body has at least one return instruction, `void` included. That is
what lets a reader count candidates and get the dispatch tier right, and what
makes an in-module interface with no implementation — a data-access declaration
whose implementation the framework generates — correctly terminal.

## Termination

The one walk that could not terminate is the hierarchy descent, which keeps a
visited set. Valid bytecode cannot describe a cycle of types, and that is
exactly why an unbounded walk here would be a hang triggered by a file nobody
wrote by hand.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sextant.application.ports.workspace import Workspace
from sextant.domain.closed_sets import MethodResolution
from sextant.domain.symbols import bare_descriptor, method_descriptor, method_name

# D00 §5's dispatch forms, as the extractor spells them (`MethodFlow.invokeKind`).
# The two that dispatch on the receiver's RUNTIME class are the two that admit
# an override; the rest name what runs.
VIRTUAL_DISPATCH = frozenset({"virtual", "interface"})
# `invokedynamic`. Its target names the bootstrap factory rather than a callee,
# so every reader has to decide what to do with it and none of them can take
# the target at face value — see the module docstring.
DYNAMIC = "dynamic"
# `G-52`: a throw site is call-site-shaped but dispatches to NO method — its target is
# the thrown exception TYPE and it carries no `name` and no `descriptor` (D00 §5). Every
# place that builds a method descriptor from a site, or asks dispatch to resolve one, has
# to say so: `str(None)` is `"None"`, and a published symbol reading
# `com/acme/OrderNotFound#None(sig_…)` is a method nobody wrote, matched by
# nothing, rendered into the document as an arrow labelled `None`.
THROW = "throw"
# Names that are never inherited, so an ancestor walk for one is always wrong (JLS 8.8).
_NOT_INHERITED = frozenset({"<init>", "<clinit>"})


@dataclass(frozen=True)
class Dispatch:
    """Everything needed to answer "which method can this site run", read once
    per pass rather than per call site.

    `bodies` maps a BARE method descriptor to the module-prefixed symbols of
    every method the workspace read a body for under it, in symbol order
    (NFR-1). `declared` is every declared method symbol, bare. `subtypes` maps
    a bare TYPE descriptor to its transitive in-module descendants, sorted.
    """

    bodies: dict[str, list[str]]
    declared: set[str]
    subtypes: dict[str, list[str]]
    # F3 §4.2. `ancestors` maps a bare type to its direct supertypes in JVMS 5.4.3.3's
    # SEARCH ORDER — superclass first, then each declared interface — each carrying the
    # kind and whether this workspace read it. `scanned` is every type whose own class
    # file was read, which is what separates "external boundary" from "unresolved".
    ancestors: dict[str, list[tuple[str, str, bool]]]
    scanned: set[str]
    # The delivery register's `DefaultImpls` item. A bare INTERFACE-method descriptor to
    # the module-prefixed symbols of the static bodies a compiler-emitted holder
    # (`<Iface>$DefaultImpls`) carries for it — read only where `bodies` holds nothing
    # for that method, see `candidates`. Defaulted so a `Dispatch` built by hand
    # carries none.
    default_bodies: dict[str, list[str]] = field(default_factory=dict)

    def resolve(self, owner: str, name: str, descriptor: str) -> tuple[str | None, str]:
        """Which type declares the method a site names, and — always — why (JVMS
        5.4.3.3).

        **The defect this replaces.** The old rule asked whether the OWNER declared the
        method and answered `[]` otherwise, which is the same answer a genuinely
        third-party call gets. For a method the module declares one hop up, that is
        false: the body is in the workspace. It is 131 call sites in
        `spring-petclinic-rest`, and `Owner#setId` — `setId` on `BaseEntity` — is the
        whole shape.

        **The order is the specification, and a breadth-first walk is not it.** 5.4.3.3
        searches the class, then the ENTIRE superclass chain, and only then the
        superinterfaces. A frontier seeded with every direct supertype at once answers
        from a depth-1 interface while a depth-2 superclass holds the body — measured on
        `A extends B implements I`, `B extends C`, both `C` and `I` declaring the
        method: it returned `I`, where the JVM runs `C`'s. Worse, `candidates` then
        found no body under `I` and returned empty, which is this item's own defect
        recreated one level deeper, with `reason` claiming `inherited` beside a
        declaring class that declares nothing.

        The two arms are therefore walked separately and in order.
        """
        declaring, reason, _ = self._search(owner, name, descriptor)
        return declaring, reason

    def boundary(self, owner: str, name: str, descriptor: str) -> str | None:
        """Where `resolve`'s search LEFT the workspace: the first type, in JVMS 5.4.3.3's
        order, that it reached and could not read — the owner itself, else the first
        unread class on the superclass chain, else the first unread superinterface. None
        wherever `resolve` answers anything but `owner_not_scanned` or
        `ancestor_not_scanned`.

        `resolve` says THAT the declaration is in something unread; a reader whose catalog
        states what one particular jar type does with the call (a framework template
        calling a subclass method) needs to know WHICH. One search answers both, so the two
        can never disagree about the order."""
        return self._search(owner, name, descriptor)[2]

    def _search(self, owner: str, name: str, descriptor: str) -> tuple[str | None, str, str | None]:
        """`resolve`'s answer, and `boundary`'s beside it."""
        if method_descriptor(owner, name, descriptor) in self.declared:
            return owner, MethodResolution.DECLARED_HERE, None
        if owner not in self.scanned:
            # Never read this type at all. The genuine third-party boundary: the call IS
            # the terminal, and nothing further is knowable from this workspace.
            return None, MethodResolution.OWNER_NOT_SCANNED, owner
        if name in _NOT_INHERITED:
            # A constructor is not inherited (JLS 8.8), so walking ancestors for one
            # could only ever produce a wrong answer. No corpus has yet contained a call
            # that would, which is why this is stated rather than discovered later.
            return None, MethodResolution.NO_DECLARATION_FOUND, None

        # The first type the search could not read, in search order (`boundary`).
        unscanned: str | None = None
        # Step 2: the superclass chain, to exhaustion, before any interface.
        chain: list[str] = []
        current: str | None = owner
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            chain.append(current)
            parent = next(
                (a for a, kind, _ in self.ancestors.get(current, ()) if kind == "extends"),
                None,
            )
            if parent is None:
                break
            if parent not in self.scanned:
                unscanned = parent
                break
            if method_descriptor(parent, name, descriptor) in self.declared:
                return parent, MethodResolution.INHERITED, None
            current = parent

        # Step 3: the superinterfaces of the class and of every superclass on that
        # chain, breadth-first — which is the right shape HERE, because interfaces form
        # a lattice rather than a chain and the JVM has no total order over them either.
        frontier = [
            ancestor
            for link in chain
            for ancestor, kind, _ in self.ancestors.get(link, ())
            if kind == "implements"
        ]
        visited: set[str] = set()
        while frontier:
            interface = frontier.pop(0)
            if interface in visited:
                continue
            visited.add(interface)
            if interface not in self.scanned:
                unscanned = unscanned or interface
                continue
            if method_descriptor(interface, name, descriptor) in self.declared:
                return interface, MethodResolution.INHERITED, None
            frontier.extend(a for a, _kind, _ in self.ancestors.get(interface, ()))

        if unscanned is not None:
            # We know MORE than "external": the body is inherited from something we did
            # not open, and `type_hierarchy` names which type that is.
            return None, MethodResolution.ANCESTOR_NOT_SCANNED, unscanned
        return None, MethodResolution.NO_DECLARATION_FOUND, None

    def candidates(self, site: dict[str, object]) -> list[str]:
        """Every method `site` can run and whose body this workspace read, as
        the module-prefixed symbols `method_return` spells them, in a fixed
        order.

        Empty is an ANSWER and the common one: the third-party boundary, or an
        in-module declaration nothing in this module implements. Neither is a
        failure to resolve — the call IS the terminal, and nothing further is
        knowable from this workspace.

        A `dynamic` site is not asked this question: its target names a
        bootstrap factory, so composing a descriptor from it would look up a
        method nobody calls. Callers handle that form themselves.
        """
        name, descriptor = str(site["name"]), str(site["descriptor"])
        owner = bare_descriptor(str(site["owner"]))
        # The DECLARING type, not the named one (F3 §4.2). `Owner#setId` names `Owner`
        # and is declared on `BaseEntity`; asking only about the named owner returned
        # nothing and read as a third-party boundary.
        declaring, _reason = self.resolve(owner, name, descriptor)
        if declaring is None:
            return []
        declared_method = method_descriptor(declaring, name, descriptor)
        found = list(self.bodies.get(declared_method, ()))
        if not found:
            # The register's `DefaultImpls` item: an interface method with no body of
            # its own whose body the workspace DID read — in the `<Iface>$DefaultImpls`
            # holder its compiler emits, where the scanner marked it `bridge_of: "<name>"`
            # beside the holder's `implements_default_of`. Without this the site read as
            # the third-party boundary about a body sitting in the module. ONLY where the
            # interface holds no body, and that is a measurement, not caution: that
            # compiler's 2.2.0 default mode (`-jvm-default=enable`) emits BOTH a JVM
            # default method on the interface and a `@Deprecated` holder stub that calls
            # back into it, so joining the holder unconditionally would turn every call
            # to such an interface's default method from one candidate to two —
            # `resolved` to `narrowed` — on every module built with a current compiler.
            # Under `-jvm-default=disable` (2.4.10, measured) the interface method is
            # abstract and the holder has the body, which is the case this reaches.
            found = list(self.default_bodies.get(declared_method, ()))
        if site["invoke_kind"] not in VIRTUAL_DISPATCH:
            return found
        for subtype in self.subtypes.get(bare_descriptor(str(site["owner"])), ()):
            for override in self.bodies.get(method_descriptor(subtype, name, descriptor), ()):
                if override not in found:
                    found.append(override)
        return found


def dispatch_of(workspace: Workspace) -> Dispatch:
    """Reads the three indices once. Every one of them is a compiler fact —
    there is no framework knowledge in a call site, so nothing here gates on a
    capability or reads a catalog."""
    ancestors, scanned = ancestry_of(workspace)
    bodies = _bodies_by_descriptor(workspace)
    return Dispatch(
        bodies=bodies,
        declared=_declared(workspace),
        subtypes=_subtypes(workspace),
        ancestors=ancestors,
        scanned=scanned,
        default_bodies=_default_bodies(workspace, bodies),
    )


# A method as a holder body is matched to its interface method: the name and the
# erased parameter symbols, in order — `engines/supertype_dispatch._members`'
# selector, copied rather than imported because that engine reads this module.
type _Selector = tuple[str, tuple[str, ...]]


def _selector_of(name: str, signature: object, *, drop: int = 0) -> _Selector:
    """`name` plus the erased symbol of every parameter from `drop` on, bare.

    `erased_symbol` — the DESCRIPTOR's own answer — before `type.symbol`, for the
    reason `supertype_dispatch._members` gives: a generic parameter's `type` names a
    bare type variable, which is scoped to its own declaration and matches nothing.

    `signature` arrives DECODED (a dict) from `method_declarations`, whose JSON columns the
    storage parses once per resolve, and as TEXT from `default_bodies`, which it does not;
    both are accepted here rather than one caller re-encoding what the other decoded.
    """
    if signature is None:
        parsed: dict[str, Any] = {}
    elif isinstance(signature, dict):
        parsed = signature
    else:
        parsed = json.loads(str(signature))
    declared: list[dict[str, Any]] = list(parsed.get("parameters") or [])
    parameters = tuple(
        bare_descriptor(
            str(parameter.get("erased_symbol") or (parameter.get("type") or {}).get("symbol", ""))
        )
        for parameter in declared[drop:]
    )
    return (name, parameters)


def _default_bodies(workspace: Workspace, bodies: dict[str, list[str]]) -> dict[str, list[str]]:
    """Bare interface-method descriptor to the module-prefixed holder bodies that stand
    for it, in symbol order (NFR-1) — the register's `DefaultImpls` item.

    A holder body's own descriptor carries the interface instance at slot 0, so its
    `sig_…` cannot be rewritten into the interface method's: the join is by SELECTOR —
    the name the scanner recorded in `bridge_of`, and the body's erased parameter
    symbols with slot 0 dropped — against the interface's own declared methods, the way
    `supertype_dispatch._members` keys a member. A body is admitted only where the
    workspace read it (`bodies` holds its own descriptor), the same rule every other
    candidate meets; a holder whose interface declares no matching method contributes
    nothing rather than a guess.
    """
    holder_bodies = workspace.query("default_bodies")
    if not holder_bodies:
        # A module with no holder — the common case — skips the pass over
        # `method_declarations` below.
        return {}
    declared_by_type: dict[str, dict[_Selector, str]] = defaultdict(dict)
    for row in workspace.query("method_declarations"):
        if row["enclosing"] is None:
            continue
        symbol = str(row["symbol"])
        selector = _selector_of(method_name(bare_descriptor(symbol)), row["signature"])
        declared_by_type[bare_descriptor(str(row["enclosing"]))][selector] = bare_descriptor(symbol)
    result: dict[str, list[str]] = defaultdict(list)
    for row in holder_bodies:
        body = str(row["symbol"])
        if bare_descriptor(body) not in bodies:
            continue
        selector = _selector_of(str(row["stands_for"]), row["signature"], drop=1)
        interface_method = declared_by_type.get(bare_descriptor(str(row["interface"])), {}).get(
            selector
        )
        if interface_method is not None and body not in result[interface_method]:
            result[interface_method].append(body)
    return {key: sorted(symbols) for key, symbols in result.items()}


def _declared(workspace: Workspace) -> set[str]:
    """Every method-like symbol this workspace scanned, bare — the conjunct
    that keeps a call THROUGH a library-declared type from picking up the
    module's own overrides of it (OI-17).

    **Constructors are in this set, and leaving them out was a silent
    under-report.** D00 §4 gives a constructor its own `construct_kind`, so
    `method_symbols` — whose own job is a receiver lookup — does not list one;
    the JVM does not make that distinction, and `invokespecial` to an in-module
    `<init>` is a call into a body this workspace read like any other. Without
    them every `new` on a type the module declares read as the third-party
    boundary, and a constructor that does real work — validation, defaulting —
    was invisible to a trace. Measured on `macrozheng/mall`'s `mall-admin`,
    including them turns 13 of 1,979 boundary edges into in-module ones — a
    small number precisely because most `new` in a service names a platform or
    dependency type, and the thirteen that do not are the module's own.

    It changes nothing for `return_flows`: a constructor call site carries no
    `result` (the object comes from the preceding `new`, not from `<init>`), so
    that pass drops the site before dispatch is asked anything.
    """
    scanned = workspace.query("method_symbols") + workspace.query("constructor_declarations")
    return {bare_descriptor(str(row["symbol"])) for row in scanned}


def _bodies_by_descriptor(workspace: Workspace) -> dict[str, list[str]]:
    """Bare descriptor to the module-prefixed symbols of every method the
    workspace read a body for, in symbol order (NFR-1) — **the join, and the
    one place a spelling is stripped.**

    **OI-4, discharged by stripping exactly one side.** `method_return.method`
    is a declaration this module made, so it carries the module-prefixed
    spelling — the same one `call_sites.caller` and the method's own symbol
    fact use, measured equal at G2. A call site's target, by contrast, is the
    JVM's own triple, from which `method_descriptor` composes a BARE
    descriptor, and it must stay bare: a callee may live in a library, and D00
    §1 requires that two modules seeing `String#trim` produce one symbol rather
    than two. So the strip happens here and nowhere else, and it is pinned
    against a MODULE-PREFIXED scan rather than a fixture that spells symbols
    bare — the exact shape that cost round 1's `F6` and 2O Task 10 six green
    tests and zero rows. G1 discharged the same trap in the opposite direction
    (`call_site.implementation` is bare), which is why "strip both sides
    always" is not the rule and each join has to say which side it strips.

    The **bare** key is what a call site's target composes to and what a
    subtype's override composes to; the module-prefixed value is what a row
    carries, so a reader can join a callee straight to that method's own
    `call_sites` and take the next hop. One key normally holds one symbol; it
    holds several where a workspace scanned two coordinates that declare the
    same class and method — an opted-in library beside the module's own output
    — and then both are candidates, because both are bodies this workspace
    actually read and choosing between them would be a claim about a classpath
    nobody measured.

    A `void` return counts here, unlike in `return_flow`'s own value index: the
    question this index answers is "did we read a body", and a method that
    hands nothing back has one. Excluding it would make every void call in the
    module read as the third-party boundary.
    """
    bodies: dict[str, list[str]] = defaultdict(list)
    for symbol in sorted({str(row["method"]) for row in workspace.query("method_returns")}):
        bodies[bare_descriptor(symbol)].append(symbol)
    return bodies


def ancestry_of(workspace: Workspace) -> tuple[dict[str, list[tuple[str, str, bool]]], set[str]]:
    """Every type's DIRECT supertypes in JVMS 5.4.3.3's search order, and the set of
    types this workspace actually read (F3 §4.2).

    `_subtypes` above walks the same two facts in the other direction — parent to child,
    for override candidates. This walks child to parent, for resolution. Both are needed
    and neither is the other reversed: `_subtypes` is transitive and sorted for a
    deterministic candidate list, while this is DIRECT and ordered by the search the JVM
    performs, because the first declaration found is the answer and the order decides
    which that is.

    **Order is the whole point.** 5.4.3.3 searches the class, then its superclass chain,
    then its superinterfaces. A dictionary of parents with no order would resolve a
    method declared both on a superclass and on an interface to whichever the iteration
    happened to reach, and that is a coin toss published as a resolution.

    `scanned` holds every type with a class file here. An ancestor absent from it is why
    a method can be genuinely unreachable while its subtype is fully known — the
    `ancestor_not_scanned` answer, which the single old word could not express.
    """
    scanned = {bare_descriptor(str(row["symbol"])) for row in workspace.query("declared_symbols")}
    direct: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
    # The superclass first: position 0 in the search, and the arm the JVM exhausts
    # before it looks at any interface.
    for row in workspace.query("superclasses"):
        child = bare_descriptor(str(row["symbol"]))
        parent = bare_descriptor(str(row["superclass"]))
        direct[child].append((parent, "extends", parent in scanned))
    # Then the declared interfaces, in the order the class file lists them — which is
    # the order `interfaces` preserves, so nothing is sorted here.
    for row in workspace.query("implementations"):
        child = bare_descriptor(str(row["symbol"]))
        for parent in json.loads(str(row["interfaces"])):
            bare = bare_descriptor(str(parent))
            direct[child].append((bare, "implements", bare in scanned))
    return dict(direct), scanned


def _subtypes(workspace: Workspace) -> dict[str, list[str]]:
    """The transitive descendants of every type the module declares, keyed by
    BARE type descriptor and sorted (NFR-1).

    Built from the two halves the symbol facts carry — `interfaces` (capability
    9.10, entries BARE) and `superclass` (capability 9.13, module-prefixed) —
    normalised to one spelling here rather than at each comparison. A type
    outside the module appears only as a PARENT: nothing declares it, so it has
    no row of its own, and asking for its descendants correctly yields only the
    in-module ones.

    The walk keeps a visited set. Valid bytecode cannot describe a cycle of
    types, and that is exactly why an unbounded walk here would be a hang
    triggered by a file nobody wrote by hand.
    """
    children: dict[str, list[str]] = defaultdict(list)
    for row in workspace.query("implementations"):
        child = bare_descriptor(str(row["symbol"]))
        for parent in json.loads(str(row["interfaces"])):
            children[bare_descriptor(str(parent))].append(child)
    for row in workspace.query("superclasses"):
        children[bare_descriptor(str(row["superclass"]))].append(
            bare_descriptor(str(row["symbol"]))
        )
    return {parent: _descendants(parent, children) for parent in children}


def _descendants(root: str, children: dict[str, list[str]]) -> list[str]:
    reached: set[str] = set()
    frontier = [root]
    while frontier:
        for child in children.get(frontier.pop(), ()):
            if child in reached:
                continue
            reached.add(child)
            frontier.append(child)
    return sorted(reached)
