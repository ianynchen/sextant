"""2Q `G3`: cross-method return propagation (D01 §3's `return_flows`).

**The one link the value chain was missing.** Within a method the chain is
already complete and has been since capability 9.9: a `call_site` carries the
value id its call produced (`result`), a receiver id, and the `source` id of
the call that produced each argument — 993 of 1,817 argument slots on the
orders-service fixture carry one. So `OmsOrderController#list` reads, from the
facts alone, as

    ord=0   OmsOrderService#list      result=7
    ord=1   CommonPage#restPage       args=[source:7]     result=12
    ord=2   CommonResult#success      args=[source:12]    result=13

— value 7 into `restPage` into `success` into the response. What nothing said
is where value 7 came FROM: that it is whatever `OmsOrderServiceImpl#list`
hands back, which is in turn whatever `OmsOrderDao#getList` returned. D00 §5's
value ids are meaningless across methods by design, and this table is the only
thing licensed to cross that line — it does so by naming both sides, never by
renumbering either.

**Its inputs are two facts and a hierarchy, and it invents nothing.** G2's
`method_return` (capability 9.18) says what a method hands back; `call_site`
says which call produced which value; the symbol facts' `superclass` and
`interfaces` say which types stand in for which. This pass is the join. It is
the first consumer `method_return` has had (OI-15).

## Which method a call site can dispatch into

The caller-to-callee join is **arithmetic, not a lookup** (`domain/symbols
.method_descriptor`): a `call_site` carries owner, name and JVM descriptor, and
a method's own symbol is that owner and name with the first four bytes of the
SHA-256 of the descriptor. So asking what one site calls costs a hash, and a
callee outside the workspace produces a descriptor that matches nothing rather
than an error.

The JVM's own dispatch rule is mirrored rather than approximated (DR-6):

- `invokestatic` and `invokespecial` name the method that runs, exactly. A
  private call, a `super.` call and a constructor have no virtual dispatch, so
  no implementation of anything is a candidate for them.
- `invokevirtual` and `invokeinterface` dispatch on the receiver's runtime
  class, so the candidates are the declared method **where it has a body** plus
  every in-module override of it. One candidate is `resolved`; several are
  `narrowed`, all listed, none picked — the roadmap's own rule for 2Q, and the
  same refusal the extractor already applies to a merged value.
- `invokedynamic` contributes **nothing**, and that is a fabrication guard
  rather than an omission. Its `result` is the functional-interface INSTANCE
  the bootstrap creates, not anything the lambda body returns; the body runs
  later, somewhere else, if at all. Linking G1's `call_site.implementation`
  returns to this site's result would state that a `Supplier` call site
  produced the supplier's value, which is false at every site that has one.
  Following `implementation` INTO the body is a traversal step, and belongs to
  the walk that takes it (OI-14).

## Where a trace stops, and why absence is an answer here

A call whose callee this workspace never scanned contributes no row. That is
the third-party boundary as ruled: a MyBatis mapper, a Spring Data repository,
a JDBC driver, anything in the JDK — the call IS the terminal, and a row
claiming to know its body would be the cardinal sin. Measured on
`macrozheng/mall`'s `mall-admin`, it is also the common case: 1,411 of 2,065
value-producing call sites.

Three further boundaries this pass does not cross, each stated rather than
silently absent (`docs/COVERAGE.md`):

- **Values through library code.** `stream().map(f).collect()` leaves for the
  JDK and comes back; the `collect` result is visible, per-element provenance
  is not.
- **Values parked in a field** between calls — `field_write` is
  constructors-only by design, so a value stored and re-read later is not
  followed.
- **Responses built by mutation** (`result.setFilename(x); return result;`) get
  no synthesized link, and need none: the returned value entry carries the id
  of the value that was mutated, and every setter that wrote into it is a
  `call_site` in the SAME method whose `receiver` is that id. That is a
  within-method join over facts that already exist — this pass's whole subject
  is the step BETWEEN methods, and adding a second, redundant spelling of a
  within-method fact would put the same claim in two places. Measured on
  `mall-admin`: 17 of 1,014 returns are built that way, all reachable by that
  join.

## Termination

A single-step relation, so nothing here recurses: a self-recursive method
yields a row whose caller and callee are the same symbol, which is the truth
and terminates by construction. The one walk that could not is the hierarchy
descent, which keeps a visited set — real bytecode cannot describe a cycle of
types, and a walk that trusts that is a walk that hangs on a file which does.
Bounded traversal OVER these links is G4's, and is where a cycle costs
something.
"""

import json
from collections import defaultdict

from sextant.application.ports.workspace import Workspace
from sextant.domain.closed_sets import Evidence, Resolution
from sextant.domain.symbols import bare_descriptor, method_descriptor

# D00 §5's dispatch forms, as the extractor spells them (`MethodFlow.invokeKind`).
# The two that dispatch on the receiver's RUNTIME class are the two that admit
# an override; the rest name what runs.
_VIRTUAL_DISPATCH = frozenset({"virtual", "interface"})
# `invokedynamic`. Excluded whole: its `result` is the object the bootstrap
# built, never a value the implementation handed back — see the module
# docstring.
_DYNAMIC = "dynamic"


def record_return_flows(workspace: Workspace) -> None:
    """Derives `return_flows` — one row per (call site, candidate callee,
    callee return) — and replaces the table whole.

    Runs unconditionally and reads no catalog: every input is a compiler fact,
    so there is no framework knowledge to gate on and nothing to skip. A module
    whose every call leaves for a third party leaves an empty table rather than
    a stale one, the `resolve_config` discipline.
    """
    workspace.derive("return_flows_reset")
    returns = _returns_by_method(workspace)
    bodies = _bodies_by_descriptor(returns)
    declared_methods = {
        bare_descriptor(str(row["symbol"])) for row in workspace.query("method_symbols")
    }
    subtypes = _subtypes(workspace)
    rows: list[dict[str, object]] = []
    for site in workspace.query("call_sites"):
        rows.extend(_rows_for(site, returns, bodies, declared_methods, subtypes))
    if rows:
        workspace.derive("return_flows_insert", rows=rows)


def _rows_for(
    site: dict[str, object],
    returns: dict[str, list[tuple[int, str]]],
    bodies: dict[str, list[str]],
    declared_methods: set[str],
    subtypes: dict[str, list[str]],
) -> list[dict[str, object]]:
    """One call site's rows, in candidate order then return order (NFR-1).

    A site with no `result` produces none: the callee returns `void`, so there
    is no value in the caller for anything to have come from, and a row would
    have nothing to say. That is the same absence a `void` `method_return`
    records on the other side of the join.
    """
    result = site["result"]
    if result is None or site["invoke_kind"] == _DYNAMIC:
        return []
    callees = _callees(site, bodies, declared_methods, subtypes)
    if not callees:
        return []
    # D01 §3: the tier describes the SITE, not the candidate — it says how much
    # is known about the call, and does not rank one candidate above another.
    # Denormalised onto every row because a row is what a reader has in hand.
    resolution = Resolution.RESOLVED if len(callees) == 1 else Resolution.NARROWED
    return [
        {
            "caller": str(site["caller"]),
            "ordinal": int(str(site["ordinal"])),
            "result": int(str(result)),
            "callee": callee,
            "return_ordinal": ordinal,
            "value": value,
            "resolution": str(resolution),
            "evidence": str(Evidence.COMPILER),
        }
        for callee in callees
        for ordinal, value in returns[callee]
    ]


def _callees(
    site: dict[str, object],
    bodies: dict[str, list[str]],
    declared_methods: set[str],
    subtypes: dict[str, list[str]],
) -> list[str]:
    """Every method this site can run and whose body this workspace read, as
    the module-prefixed symbols `method_return` spells them, in a fixed order.

    A candidate is kept only when it has `method_return` facts. That is the
    same question as "did we read its body": an abstract or interface
    declaration is a scanned SYMBOL with no returns, and a candidate with no
    returns would contribute no row anyway — filtering here is what lets the
    caller count candidates and get the dispatch tier right.
    """
    name, descriptor = str(site["name"]), str(site["descriptor"])
    declared = method_descriptor(str(site["owner"]), name, descriptor)
    if declared not in declared_methods:
        # The third-party boundary. Not a failure to resolve — the call IS the
        # terminal, and nothing further is knowable from this workspace.
        return []
    candidates = list(bodies.get(declared, ()))
    if site["invoke_kind"] not in _VIRTUAL_DISPATCH:
        return candidates
    for subtype in subtypes.get(bare_descriptor(str(site["owner"])), ()):
        for override in bodies.get(method_descriptor(subtype, name, descriptor), ()):
            if override not in candidates:
                candidates.append(override)
    return candidates


def _bodies_by_descriptor(returns: dict[str, list[tuple[int, str]]]) -> dict[str, list[str]]:
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
    """
    bodies: dict[str, list[str]] = defaultdict(list)
    for symbol in sorted(returns):
        bodies[bare_descriptor(symbol)].append(symbol)
    return bodies


def _returns_by_method(workspace: Workspace) -> dict[str, list[tuple[int, str]]]:
    """Every `method_return` fact, keyed by its method's symbol EXACTLY as the
    fact spells it — module coordinates included, unstripped. The one place
    that strips is `_bodies_by_descriptor`, which builds the join key.

    A void return is dropped rather than kept as a null: it can only appear
    against a call site with no `result`, which contributes no row at all, and
    keeping it would put "this callee returns nothing" beside a caller that is
    holding a value.
    """
    by_method: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in workspace.query("method_returns"):
        value = row["value"]
        # DuckDB hands an explicit JSON null back as the four-character text
        # `null`, not as SQL NULL — the projection's own comment says so — so
        # the void case is read here rather than assumed away.
        if value is None or json.loads(str(value)) is None:
            continue
        by_method[str(row["method"])].append((int(str(row["ordinal"])), str(value)))
    return by_method


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
