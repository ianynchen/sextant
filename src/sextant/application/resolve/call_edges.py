"""2Q `G4`: the call graph a trace walks (D01 §3's `call_edges`).

**One row per (call site, candidate callee), plus a row where there is no
candidate at all** — because that absence is the third-party boundary, and it
is the point at which a trace stops. `return_flows` could leave such a site out
entirely: it explains where a VALUE came from, and where no body was read there
is nothing to say. A walk cannot. "This call leaves the module here" and "this
method makes no calls" are different answers, and a table that recorded neither
would report them identically.

## Why this is not `return_flows` with more columns

`return_flows` is the VALUE chain and this is the CONTROL one, and the control
graph is the larger of the two by a wide margin. A return flow exists only
where a call produced a value; a method that hands nothing back — a write, a
publish, a delete — contributes no row there at all, and those calls are
frequently the whole point of the work a trace is about. On the orders-service
fixture the difference is roughly threefold.

The two share exactly one thing, and share it rather than restating it: which
method a site can run (`resolve/dispatch.py`). M04 §4 designs a third answer to
that question, unbuilt, and `docs/open-issues.md` OI-16 already records the
disagreement that will exist the day it lands — deriving a second one here
would have made it three.

## What a `dynamic` site contributes, and why it is not the bootstrap

An `invokedynamic`'s `target` names the BOOTSTRAP factory, never a callee, so
composing a descriptor from it would look up a method nobody calls and reach a
platform class in every case. Capability 9.17 records what the site actually
creates — `call_site.implementation`, the lambda body — and that is what this
table names as the edge's `target`.

**This is the traversal step OI-14 named, and it is deliberately not the step
`return_flows` refused.** The refusal there was about a VALUE: an
`invokedynamic`'s `result` is the functional-interface instance the bootstrap
built, never anything the body handed back, so linking the body's returns to
that result would state that a `Supplier` call site produced the supplier's
value. Reachability is a different claim and a true one — the body is reached
from here and from nowhere else — and `invoke_kind` is carried on the row so a
reader is never told the body runs AT this line. A lambda body holds business
logic: `list.forEach(x -> mapper.insert(x))` reaches persistence, and without
this row the trace stops at `forEach`.

**A `dynamic` site whose `implementation` is absent contributes no row**, and
that is a refusal rather than an omission. The key is written only where the
bootstrap names a body; where it is missing the site is some other use of
`invokedynamic` — string concatenation is the common one — whose bootstrap is a
compiler artifact rather than a call the program makes. An edge to it would put
a platform factory in a trace at every string a method builds.

**The lambda body is looked up EXACTLY**, with no override walk. A lambda body
is a synthetic private method of the class that declares it; nothing can
override it, and admitting a subtype's same-named body would be a candidate the
JVM cannot reach.

## Where a trace stops, and why the row is still written

Absence of a `callee` is the ruled third-party boundary: a mapper, a
repository, a driver, anything in the JDK — the call IS the terminal, and a row
claiming to know its body would be the cardinal sin. It is also the common
case, measured on `macrozheng/mall`'s `mall-admin`. The row is still written,
with `target` naming exactly what the compiler wrote, because that name is the
terminal a reader wants to see.

The same shape covers an in-module declaration nothing in this module
implements — a data-access interface whose implementation a framework generates
at run time. The workspace read no body, so the call is the terminal, reached
without a special case.

## Termination

Nothing here recurses: a row is one step, and a self-recursive method yields a
row whose caller and callee are the same symbol — the truth, and finite. The
one walk that could not terminate is the hierarchy descent, which keeps a
visited set in `resolve/dispatch.py`. Bounded traversal OVER these rows is
`application/query/trace.py`'s, and is where a cycle costs something.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import DYNAMIC, THROW, Dispatch, dispatch_of
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.terminals import TerminalRules, classify
from sextant.application.resolve.values import EXTERNAL, NOT_READABLE
from sextant.domain.closed_sets import Evidence, Resolution
from sextant.domain.symbols import bare_descriptor, method_descriptor, without_type_marker


@dataclass(frozen=True)
class FunctionCalls:
    """What a `__call__` whose receiver is a function value runs (ruling R29): the function
    bodies its paths ended at, bare, and the site's tier over every path
    (`receiver_binding`)."""

    bodies: tuple[str, ...]
    tier: str


def record_call_edges(
    workspace: Workspace,
    catalogs: Sequence[Catalog] = (),
    functions: Mapping[tuple[str, int], FunctionCalls] | None = None,
) -> None:
    """Derives `call_edges` — one row per (call site, candidate callee) — and
    replaces the table whole.

    Every EDGE is a compiler fact, so the graph itself gates on no framework knowledge and
    a module whose facts carry no call site leaves an empty table rather than a stale one
    (the `resolve_config` discipline).

    `catalogs` is read for one thing only: D00 §4's `terminal_kind` (F7 §8.2, W30), which
    classifies what a terminal REACHES. That is the one question here a compiler fact
    cannot answer — "a data-access call is `persistence` only to something that knows the
    callee is one" (D00's own note, which is why the set had no producer for two phases).
    Defaulted to none so a caller that wants the graph alone still gets it, and every
    terminal then reads `unresolved`, which is what it read before this existed.

    `functions` (ruling R29): for a `__call__` the facts leave without an owner, the
    function bodies receiver binding found its receiver to be. Each is an edge to that body,
    looked up exactly, by the rule a JVM lambda body is (`_edge`): calling a function runs
    it. None where binding found none, which is every JVM module.
    """
    workspace.derive("call_edges_reset")
    dispatch = dispatch_of(workspace)
    # The PROJECTION, not the raw fact stream (spec 2026-09-22 §1a, I-3). An edge is a
    # step a walk takes, and a compiler-emitted `$default` bridge is a step the program
    # does not have: the bridge's body fills in the omitted arguments and then calls the
    # sibling, so an edge stopping at it names a method no author wrote and puts a
    # synthetic hop in every trace through a call that left a parameter to its default.
    # `effective_call_sites` re-targets it, and reads a class-compiled lambda argument
    # as the lambda it is — what every engine has seen since spec 2026-09-19 §3.
    #
    # Where the sibling is an INSTANCE method the projection also hands back
    # `invoke_kind: virtual`, which this pass writes into the row and `dispatch` then
    # walks subtypes for. That is the point: the compiler wrote `invokestatic` against
    # the bridge, which dispatches on nothing, so on the raw site an override is not a
    # candidate at all — one `resolved` edge hiding a call the JVM may send elsewhere.
    sites = list(effective_call_sites(workspace))
    # Built once, outside the loop: two of its three routes are workspace-wide questions,
    # and asking them per site would repeat two queries for each of mall-admin's 24,591
    # edges.
    rules = TerminalRules(workspace, list(catalogs))
    # A call the facts leave without an owner (D00 §5) is read with the owner each path of
    # its receiver was bound to (`resolve/receiver_binding.py`), one edge per owner: the
    # sites as each of their owners makes them. Empty on every JVM module.
    bound = _bound_owners(workspace)
    called = functions or {}
    rows: list[dict[str, object]] = []
    for site in sites:
        rows.extend(_site_rows(site, dispatch, rules, bound, called))
    if rows:
        workspace.derive("call_edges_insert", rows=rows)
    # F3 §4.2's two tables, written from the SAME pass and the same `Dispatch` — "which
    # method can this site run" is answered once (this module's own docstring), and a
    # second pass would be a second answer that could disagree with the edges above.
    _record_hierarchy(workspace, dispatch)
    _record_resolution(workspace, dispatch, [one for site in sites for one in _owned(site, bound)])


# The one invoke kind whose owner the facts may leave to the resolver (D00 §5).
_VIRTUAL = "virtual"

# A bound site's owners, in the order `bound_receivers` lists them, and the site's tier.
_Bound = dict[tuple[str, int], tuple[tuple[str, ...], str]]


def _bound_owners(workspace: Workspace) -> _Bound:
    """Each bound call site's distinct owners, first-seen order (NFR-1), with the
    resolution its binding rows carry."""
    owners: dict[tuple[str, int], dict[str, None]] = {}
    tiers: dict[tuple[str, int], str] = {}
    for row in workspace.query("bound_receivers"):
        if row["owner"] is None:
            continue
        key = (str(row["caller"]), int(str(row["ordinal"])))
        owners.setdefault(key, {})[str(row["owner"])] = None
        tiers[key] = str(row["resolution"])
    return {key: (tuple(found), tiers[key]) for key, found in owners.items()}


def _unowned(site: dict[str, object]) -> bool:
    """A call the facts leave to the resolver to bind: `virtual`, with no owner."""
    return site["owner"] is None and str(site["invoke_kind"]) == _VIRTUAL


def _owned(site: dict[str, object], bound: _Bound) -> list[dict[str, object]]:
    """`site` as each owner makes it: itself where its facts name one, once per bound owner
    where they do not, and not at all where nothing bound it."""
    if not _unowned(site):
        return [site]
    owners, _ = bound.get((str(site["caller"]), int(str(site["ordinal"]))), ((), ""))
    return [{**site, "owner": owner} for owner in owners]


def _site_rows(
    site: dict[str, object],
    dispatch: Dispatch,
    rules: TerminalRules,
    bound: _Bound,
    called: Mapping[tuple[str, int], FunctionCalls] | None = None,
) -> list[dict[str, object]]:
    """`_rows_for`, and for a call the facts leave without an owner, the rows of each owner
    it was bound to, as one site: its tier is over every owner's edges, `partial` where the
    binding was, and its evidence is the binding's (`syntax`, a type worked out by a rule).
    A site nothing bound is one row naming no target and reaching no body, `unresolved`:
    the call is in the code, and what it calls is not known."""
    if not _unowned(site):
        return _rows_for(site, dispatch, rules)
    key = (str(site["caller"]), int(str(site["ordinal"])))
    owners, tier = bound.get(key, ((), str(Resolution.UNRESOLVED)))
    function = (called or {}).get(key)
    if function is not None:
        # The site's tier counts the function bodies too (`receiver_binding._tier`).
        tier = function.tier
    if not owners and function is None:
        return [
            {
                "caller": key[0],
                "ordinal": key[1],
                "invoke_kind": str(site["invoke_kind"]),
                "target": None,
                "callee": None,
                "result": None if site["result"] is None else int(str(site["result"])),
                "resolution": str(Resolution.UNRESOLVED),
                "evidence": str(Evidence.COMPILER),
                **classify(rules, None, None, str(site["invoke_kind"])),
            }
        ]
    rows = [row for owned in _owned(site, bound) for row in _rows_for(owned, dispatch, rules)]
    for body in function.bodies if function is not None else ():
        # Exactly the body the value names, as a lambda body is looked up (`_edge`); the row
        # keeps the site's own invoke kind, since the body runs at this call.
        lambda_site = {**site, "invoke_kind": DYNAMIC, "implementation": body}
        rows.extend(
            {**row, "invoke_kind": str(site["invoke_kind"])}
            for row in _rows_for(lambda_site, dispatch, rules)
        )
    if tier == str(Resolution.PARTIAL):
        resolution = Resolution.PARTIAL
    else:
        resolution = Resolution.NARROWED if len(rows) > 1 else Resolution.RESOLVED
    return [
        {**row, "resolution": str(resolution), "evidence": str(Evidence.SYNTAX)} for row in rows
    ]


def _record_hierarchy(workspace: Workspace, dispatch: Dispatch) -> None:
    """`type_hierarchy` — every type's direct supertypes in the JVM's search order."""
    workspace.derive("type_hierarchy_reset")
    rows = [
        {
            "child": child,
            "ancestor": ancestor,
            "kind": kind,
            "position": position,
            "scanned": scanned,
        }
        for child, parents in sorted(dispatch.ancestors.items())
        for position, (ancestor, kind, scanned) in enumerate(parents)
    ]
    if rows:
        workspace.derive("type_hierarchy_insert", rows=rows)


def _record_resolution(
    workspace: Workspace, dispatch: Dispatch, sites: list[dict[str, object]]
) -> None:
    """`method_resolution` — one row per distinct (class, name, descriptor) an EFFECTIVE
    call site names, with the declaring type. A found body has no reason; any other
    answer has one general reason and a detail (spec 2026-11-05 §3b).

    **Effective, not raw** (spec 2026-09-22 §1a): `sites` is the projection, so a
    compiler-emitted `$default` bridge is named by nothing here and gets no row — the
    triple a reader sees is the one the author's call resolves through. MEASURED on
    `fixtures/orders-ktor`: the `mount$default` row goes and `mount`'s own row was
    already there, so no resolution a reader could ask for is lost.

    Distinct rather than per site: the same method called nine times resolves the same
    way nine times, and nine identical rows would say nothing a reader could use. The
    per-site view is `call_edges`, which already has one row per site.
    """
    workspace.derive("method_resolution_reset")
    asked: dict[tuple[str, str, str], tuple[str | None, str | None]] = {}
    # A `dynamic` site's target names the bootstrap factory rather than a callee, so
    # resolving it would look up a method nobody calls — the same reason
    # `Dispatch.candidates` declines to answer for one. Filtered in the comprehension
    # rather than with a second `== DYNAMIC` statement, because `guard_check.py` anchors
    # `call_edges.a-lambda-site-names-the-body-not-the-bootstrap` on that exact line and
    # a second copy makes the anchor ambiguous — it would disable one of the two and
    # report the guard as still held.
    for site in (
        candidate
        for candidate in sites
        # A `throw` site joins `dynamic` here for a different reason with the same
        # consequence: there is no method to look up. Resolving one asked dispatch for
        # `(IllegalStateException, "None", "None")` and got back a row claiming a method
        # named `None` was inherited from an unscanned ancestor.
        if str(candidate["invoke_kind"]) not in (DYNAMIC, THROW)
    ):
        key = (
            bare_descriptor(str(site["owner"])),
            str(site["name"]),
            str(site["descriptor"]),
        )
        if key not in asked:
            asked[key] = dispatch.resolve(*key)
    rows = [
        {
            "class": owner,
            "name": name,
            "descriptor": descriptor,
            "declaring_class": declaring,
            **_reason_and_detail(owner, name, declaring, unread),
        }
        for (owner, name, descriptor), (declaring, unread) in sorted(asked.items())
    ]
    if rows:
        workspace.derive("method_resolution_insert", rows=rows)


def _type_name(descriptor: str) -> str:
    """A type descriptor for a person: `p/Role#[]` reads `p/Role[]`, `p/Role#` reads `p/Role`."""
    return without_type_marker(descriptor.replace("#[]", "[]"))


def _reason_and_detail(
    owner: str, name: str, declaring: str | None, unread: str | None
) -> dict[str, str | None]:
    """The `reason` and `detail` of one lookup. A found body has neither. A type the
    search could not read means the answer is outside the scanned code: `external`.
    When the search read every type it reached and none declares the method, the code is
    here and we did not find the declaration: `not_readable`. No code reads the detail."""
    if declaring is not None:
        return {"reason": None, "detail": None}
    owner_name = _type_name(owner)
    if unread is None:
        return {
            "reason": NOT_READABLE,
            "detail": f"no declaration of {name}(..) in {owner_name} or its scanned ancestors",
        }
    if unread == owner:
        return {"reason": EXTERNAL, "detail": f"{owner_name} is not in the scanned code"}
    return {
        "reason": EXTERNAL,
        "detail": (
            f"{owner_name} is read, but its ancestor {_type_name(unread)} "
            "is not in the scanned code"
        ),
    }


def _rows_for(
    site: dict[str, object], dispatch: Dispatch, rules: TerminalRules | None = None
) -> list[dict[str, object]]:
    """One call site's rows, in candidate order (NFR-1).

    Every site produces at least one row except a `dynamic` one naming no
    implementation — see the module docstring. A site whose callee's body was
    never read produces exactly one, with a NULL `callee`: that is the boundary,
    and it is what a walk stops at.
    """
    target, callees = _edge(site, dispatch)
    # A THROW whose type could not be read still gets its row. The alternative is the
    # silent absence `test_every_other_call_site_contributes_at_least_one_edge` exists
    # against — the site was extracted, and dropping it here would lose an exit that the
    # fact stream recorded. MEASURED: 5 of 39 throw sites on the fixture, all rethrows,
    # whose type lives in the try-catch table this extractor does not read.
    if target is None and str(site["invoke_kind"]) != THROW:
        return []
    # D01 §3: the tier describes the SITE, not the candidate. NO candidate is
    # `resolved` and not `unresolved` — the compiler named that target exactly,
    # and what is unknown is its BODY, which `callee IS NULL` says on its own.
    # Calling it unresolved would claim we do not know what is called, which is
    # a different and false statement about every third-party call in the
    # module.
    resolution = Resolution.NARROWED if len(callees) > 1 else Resolution.RESOLVED
    # A single NULL where no body was read: the row is still written, because
    # the boundary is the terminal a reader wants to see named.
    reached: list[str | None] = list(callees) or [None]
    return [
        {
            "caller": str(site["caller"]),
            "ordinal": int(str(site["ordinal"])),
            "invoke_kind": str(site["invoke_kind"]),
            "target": target,
            "callee": callee,
            "result": None if site["result"] is None else int(str(site["result"])),
            "resolution": str(resolution),
            "evidence": str(Evidence.COMPILER),
            # F7 §8.2 (W30). Classified here, with the row, because this is where it is
            # already known whether a body was read — a later UPDATE would have to
            # rediscover which rows are terminals.
            **classify(rules, target, callee, str(site["invoke_kind"])),
        }
        for callee in reached
    ]


def _edge(site: dict[str, object], dispatch: Dispatch) -> tuple[str | None, list[str]]:
    """The bare descriptor this edge names, and the bodies it reaches.

    `(None, [])` means the site names nothing an edge could be drawn to, which
    is exactly one shape: an `invokedynamic` whose bootstrap creates no body.
    """
    if str(site["invoke_kind"]) == DYNAMIC:
        implementation = site["implementation"]
        if implementation is None:
            return None, []
        # Looked up EXACTLY, with no override walk: a lambda body is a
        # synthetic private method of the class that declares it, so nothing
        # can override it and a subtype's same-named body is a candidate the
        # JVM cannot reach here.
        return str(implementation), list(dispatch.bodies.get(str(implementation), ()))
    if str(site["invoke_kind"]) == THROW:
        # The TYPE is the target, whole. No candidates: a throw reaches no body, and an
        # empty candidate list is the honest answer rather than a lookup that cannot run.
        # `owner` is itself NULL for a rethrow whose type the try-catch table holds, and
        # that stays NULL rather than becoming the string "None".
        owner = site["owner"]
        return (None if owner is None else str(owner)), []
    target = method_descriptor(str(site["owner"]), str(site["name"]), str(site["descriptor"]))
    return target, dispatch.candidates(site)
