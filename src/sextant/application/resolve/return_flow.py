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

Answered by `resolve/dispatch.py`, not here. The JVM's rule is mirrored rather
than approximated (DR-6), and it lives in one place because `call_edges` needs
the identical answer: deriving it twice would make `docs/open-issues.md` OI-16
— which already records that M04 §4's designed dispatch pass will one day be a
SECOND answer — a three-way disagreement instead of a two-way one.

**`invokedynamic` contributes nothing HERE, and that is this pass's own
decision rather than the shared rule's.** Its `result` is the
functional-interface INSTANCE the bootstrap creates, not anything the lambda
body returns; the body runs later, somewhere else, if at all. Linking G1's
`call_site.implementation` returns to this site's result would state that a
`Supplier` call site produced the supplier's value, which is false at every
site that has one. Following `implementation` INTO the body is a traversal
step, and `call_edges` is the table that takes it.

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
descent, which keeps a visited set and lives in `resolve/dispatch.py`. Bounded
traversal OVER these links is `application/query/trace.py`'s, and is where a
cycle costs something.
"""

import json
from collections import defaultdict

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import DYNAMIC, Dispatch, dispatch_of
from sextant.domain.closed_sets import Evidence, Resolution


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
    dispatch = dispatch_of(workspace)
    rows: list[dict[str, object]] = []
    for site in workspace.query("call_sites"):
        rows.extend(_rows_for(site, returns, dispatch))
    if rows:
        workspace.derive("return_flows_insert", rows=rows)


def _rows_for(
    site: dict[str, object],
    returns: dict[str, list[tuple[int, str]]],
    dispatch: Dispatch,
) -> list[dict[str, object]]:
    """One call site's rows, in candidate order then return order (NFR-1).

    A site with no `result` produces none: the callee returns `void`, so there
    is no value in the caller for anything to have come from, and a row would
    have nothing to say. That is the same absence a `void` `method_return`
    records on the other side of the join.
    """
    result = site["result"]
    if result is None or site["invoke_kind"] == DYNAMIC:
        return []
    # Only candidates that hand a value back: `dispatch` keeps every body it
    # read, `void` ones included, because its question is "did we read a body".
    # This pass's question is "where did this value come from", and a callee
    # with no non-void return has nothing to say about one. The filter cannot
    # change a tier in practice — an override shares its declared descriptor,
    # so it shares its return type, and a site holding a `result` has none —
    # and it is spelled anyway so the tier is counted over the rows that will
    # actually be written.
    callees = [callee for callee in dispatch.candidates(site) if returns.get(callee)]
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


def _returns_by_method(workspace: Workspace) -> dict[str, list[tuple[int, str]]]:
    """Every `method_return` fact, keyed by its method's symbol EXACTLY as the
    fact spells it — module coordinates included, unstripped. The one place
    that strips is `dispatch._bodies_by_descriptor`, which builds the join key.

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
