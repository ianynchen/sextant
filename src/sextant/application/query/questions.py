"""The six in-process questions (spec 2026-10-22-boundary-vocabulary-and-diff §5, FR-24).

`api.query` is this module's one caller. Each question is a named query over tables a
workspace already holds (D01 §5's rule: shipped with the schema, never written per
consumer), answered at MODULE scope only:

- `source` — the file and line range declaring a symbol;
- `callers`, `callees` — one hop of `call_edges`, either direction;
- `implementations` — the direct subtypes `type_hierarchy` records;
- `uses` — what references a TYPE: a member whose signature takes or returns it, at any
  depth of type arguments (`List<Money>` names `Money`), and a direct subtype;
- `impact` — the walk upstream over `callers` and `uses`, answered as D01 §5 requires: three
  partitions, never one count.

Every list item is `{"symbol", "file", "line_start", "line_end"}`, sorted by symbol. Nothing
else is built here — no `path` between two symbols, no endpoint family — and the spec names
what waits.

## `impact`'s three partitions

A symbol the walk reaches is `definite` when some path to it crossed only `resolved` call
edges and type references, and `possible` when every path crossed at least one `narrowed`
dispatch — a call that may run any of several bodies, so it may not run this one. A symbol
reached both ways is `definite`: the strongest path decides, so a symbol first met through
a narrowed call and later through a resolved chain is moved, and the walk carries the
upgrade on upstream.

The impact of a TYPE starts from the type and every member it encloses — a change to the
type is a change to what its methods' callers depend on — read once, before the first hop.
The subject (with those members) is never in its own impact, which is also what ends a
recursion back to it.

`unknown_regions` is where the walk cannot see, each `{"symbol", "reason"}` and never
folded into a partition — the upstream walk's own boundary stops:

- a call edge whose target names a walked symbol and whose callee is NULL
  (`"callee body not read — dispatch unconfirmed"`): the call may reach the walked symbol,
  and with no body read nothing confirms it. `symbol` is the caller, in full;
- a DIRECT ancestor of a walked symbol's type that this workspace never read
  (`"ancestor not scanned"`): code with no body here may call in through it. `symbol` is the
  ancestor's bare descriptor, the spelling `type_hierarchy` holds, since no `symbols` row
  gives it coordinates.

**Cost (GUIDELINES §8.7), decided here.** One read places the subject; every other question
is then one read, and `impact` is one read per hop of the whole frontier — never one per
symbol reached — plus, for a type, the one read of its members. A symbol joins the frontier when it is first reached and again only if its
classification improves, which can happen once, so the walk terminates on any graph,
cycles included, within two hops per symbol upstream.
"""

from sextant.application.ports.workspace import Workspace
from sextant.domain.closed_sets import Resolution
from sextant.domain.symbols import bare_descriptor, is_type_descriptor, owner_of

QUESTIONS = ("source", "callers", "callees", "implementations", "uses", "impact")

_ITEM = ("symbol", "file", "line_start", "line_end")

# `question_impact_step`'s two arms the walk lists rather than follows, and the reason each
# is given on the answer.
_REGIONS = {
    "unread": "callee body not read — dispatch unconfirmed",
    "unscanned": "ancestor not scanned",
}

type Item = dict[str, object]


class QuestionRefused(ValueError):
    """The question is not one of the six, or the symbol is in no `symbols` row. The facade
    turns it into the api's own error (`api` may name `SextantError`, this layer may not)."""


def answer(
    workspace: Workspace, question: str, *, symbol: str
) -> list[Item] | dict[str, list[Item]]:
    """`question` about `symbol`, a full symbol as `symbols` spells it. Refuses an unknown
    question naming the six, and an unknown symbol naming it — an empty answer would read
    as "nothing calls it" where the truth is that no such symbol exists."""
    if question not in QUESTIONS:
        raise QuestionRefused(
            f"unknown question {question!r} — the questions are: {', '.join(QUESTIONS)}"
        )
    placed = _items(workspace.query("question_source", symbol=symbol))
    if not placed:
        raise QuestionRefused(f"no symbol {symbol!r} in this workspace")
    if question == "source":
        return placed
    if question == "callers":
        return _items(workspace.query("question_callers", callee=symbol))
    if question == "callees":
        return _items(workspace.query("question_callees", caller=symbol))
    if question == "implementations":
        return _items(workspace.query("question_implementations", ancestor=bare_descriptor(symbol)))
    if question == "uses":
        return _items(workspace.query("question_uses", type=bare_descriptor(symbol)))
    return _impact(workspace, symbol)


def _items(rows: list[dict[str, object]]) -> list[Item]:
    # New dicts, never the rows themselves: a workspace may hand the same rows to every
    # caller, and an answer is the caller's to keep.
    return [{key: row[key] for key in _ITEM} for row in rows]


def _impact(workspace: Workspace, subject: str) -> dict[str, list[Item]]:
    seeds = {subject}
    if is_type_descriptor(bare_descriptor(subject)):
        seeds |= {
            str(row["symbol"]) for row in workspace.query("question_members", enclosing=subject)
        }
    definite: dict[str, bool] = dict.fromkeys(seeds, True)
    located: dict[tuple[str, object], Item] = {}
    regions: set[tuple[str, str]] = set()
    frontier = set(seeds)
    while frontier:
        rows = workspace.query(
            "question_impact_step",
            walked=[
                {
                    "symbol": symbol,
                    "bare": bare_descriptor(symbol),
                    "owner": owner_of(bare_descriptor(symbol)),
                }
                for symbol in sorted(frontier)
            ],
        )
        improved: set[str] = set()
        for row in rows:
            reached, arm = str(row["symbol"]), str(row["arm"])
            if arm in _REGIONS:
                regions.add((reached, _REGIONS[arm]))
                continue
            if reached in seeds:
                continue
            located.setdefault((reached, row["file"]), {key: row[key] for key in _ITEM})
            strong = definite[str(row["walked"])] and row["resolution"] == Resolution.RESOLVED
            if reached not in definite or (strong and not definite[reached]):
                definite[reached] = strong
                improved.add(reached)
        frontier = improved
    ordered = sorted(located.values(), key=_order)
    return {
        "definite": [item for item in ordered if definite[str(item["symbol"])]],
        "possible": [item for item in ordered if not definite[str(item["symbol"])]],
        "unknown_regions": [
            {"symbol": symbol, "reason": reason} for symbol, reason in sorted(regions)
        ],
    }


def _order(item: Item) -> tuple[str, bool, str]:
    """By symbol, then file with a missing one last — the named queries' own order."""
    return (str(item["symbol"]), item["file"] is None, str(item["file"] or ""))
