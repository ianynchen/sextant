"""Which handler on a route chain answers (Vert.x spec 2026-10-30 §3b, plan Task 10).

A framework that runs a route's handlers in order calls each with the request's context, and
a handler that calls a declared method on that context (`passes_on`, Vert.x's
`RoutingContext.next()`, Express's `next()`) hands the request to the next handler: it is
middleware. The chain's row names the first handler that does not. Three outcomes, each a
statement about one handler:

- **passes on** — a `passes_on` call is reached on the context the handler received, in its
  own body, in a module method it hands the context to, or in a lambda that captured it; or
  the handler is an object of the framework's own handler packages (`framework_handlers`),
  which by contract carry the request on or fail it;
- **answers** — the handler's body is in the module and nothing above is reached;
- **not readable here** — the context is handed to a method whose body this analysis does not
  read, or the handler object is produced there and is not the framework's.

**Computed backwards, once per run.** Each `passes_on` call site's receiver is walked back to
where it came from (`values.producers_of`), stopping at a handler's parameters
(`stop_at_parameters_of`), so a `next()` on a context some other request handed in never
counts. The hand-off test reads the same calling edges the walk crosses
(`ValueIndex.callers`), turned round once: from the handler's own call sites to the module
methods it passes the context to, and on through theirs. No walk runs forward through
everything a handler calls.

Nothing here names a framework type: the calls, the packages and the method a framework calls
on a handler object are the catalog's (`pass_through_of`).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.application.resolve.values import RECEIVER, ValueIndex, producers_of
from sextant.domain.symbols import (
    dotted_package,
    method_descriptor,
    method_name,
    owner_of,
    returned_type,
)

Outcome = Literal["passes_on", "answers", "unreadable"]
PASSES_ON: Outcome = "passes_on"
ANSWERS: Outcome = "answers"
UNREADABLE: Outcome = "unreadable"


@dataclass(frozen=True)
class PassThroughRule:
    """A catalog's pass-through words, read once per run (`pass_through_of`)."""

    # `(owner symbol, method)` of every call that passes the request on, one per owner.
    calls: frozenset[tuple[str, str]]
    # The dotted packages whose handler objects pass on by the framework's contract; a
    # subpackage is inside its package.
    framework: tuple[str, ...]
    # The method a framework calls on a handler OBJECT with the context (`handle`).
    handler_methods: frozenset[str]


@dataclass(frozen=True)
class Handler:
    """What one handler argument runs: the module methods the framework hands the context to,
    and which of their parameters receives it — or an outcome decided without a body."""

    # The methods, the row's own handler first. Empty where the outcome is already decided.
    symbols: tuple[str, ...] = ()
    context: int = 0
    outcome: Outcome | None = None
    # The producer outside the module, for an `unreadable` object; None where nothing names one.
    unread: str | None = None


def pass_through_of(matches: Mapping[str, Any], source: object) -> PassThroughRule | None:
    """`matches.passes_on`, `framework_handlers` and `handler_methods`, validated, or None for a
    catalog declaring no `passes_on` — whose every handler answers, as before the rule."""
    declared = matches.get("passes_on")
    where = f"loading catalog {source}:"
    if declared is None:
        for word in ("framework_handlers", "handler_methods"):
            if word in matches:
                raise CatalogError(f"{where} `{word}` is read only beside `passes_on`")
        return None
    if not isinstance(declared, list) or not declared:
        raise CatalogError(f"{where} `passes_on` is a non-empty list of {{owner, method}}")
    calls = set()
    for entry in declared:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"owner", "method"}
            or not all(isinstance(entry[key], str) and entry[key] for key in entry)
        ):
            raise CatalogError(
                f"{where} a `passes_on` entry is {{owner, method}}, each a name; got {entry!r}"
            )
        calls.add((_catalog_symbol(entry["owner"]), entry["method"]))
    framework = matches.get("framework_handlers", [])
    methods = matches.get("handler_methods", [])
    for word, value in (("framework_handlers", framework), ("handler_methods", methods)):
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            raise CatalogError(f"{where} `{word}` is a list of names; got {value!r}")
    return PassThroughRule(frozenset(calls), tuple(framework), frozenset(methods))


class HandlerReader:
    """What a handler argument runs (spec §3b, user ruling 2026-10-30): a method reference
    runs the method, a lambda its synthetic body, `new X(…)` (an `instance`) X's handler
    method, and anything else the object its producer builds, read with the producer reader.

    Built once per run: the module's handler methods by type and the producer reader's stops
    are each one pass, over the method symbols and over the index's library calls."""

    def __init__(
        self, index: ValueIndex, rule: PassThroughRule, method_symbols: Mapping[str, str]
    ) -> None:
        self._index = index
        self._rule = rule
        self._method_symbols = method_symbols
        self._by_type: dict[str, list[str]] = {}
        for bare, symbol in method_symbols.items():
            owner = owner_of(bare)
            if owner is not None and method_name(bare) in rule.handler_methods:
                self._by_type.setdefault(owner, []).append(symbol)
        # A call whose body is not read, or a construction, ends the producer walk at the
        # call that made the object, whose type then says what it is.
        self._declared = index.unscanned | {(built, "<init>") for built in index.constructed}

    def of(self, argument: Any, site: tuple[str, int, int] | None) -> Handler:
        """The handler `argument` is, captured at `site`, `(caller, ordinal, slot)`."""
        if isinstance(argument, dict) and argument.get("kind") == "lambda":
            symbol = self._method_symbols.get(str(argument.get("symbol")))
            if symbol is None:
                return Handler(outcome=UNREADABLE)
            # A lambda's body takes what it captured first; the context follows.
            return Handler((symbol,), context=int(argument.get("captures") or 0))
        if isinstance(argument, dict) and argument.get("kind") == "instance":
            return self._object(str(argument.get("symbol")), None)
        at = self._index.sites.get((site[0], site[1])) if site is not None else None
        if at is None or site is None:
            return Handler(outcome=UNREADABLE)
        handlers = []
        for end in producers_of(self._index, at, site[2], self._declared):
            made = self._index.sites.get((str(end.caller), int(end.ordinal or 0)))
            if end.identity is None or made is None:
                handlers.append(Handler(outcome=UNREADABLE))
                continue
            owner, name = end.identity
            descriptor = str(made["descriptor"])
            built = owner if name == "<init>" else returned_type(descriptor)
            handlers.append(self._object(built, method_descriptor(owner, name, descriptor)))
        return _either(handlers)

    def _object(self, built: str | None, maker: str | None) -> Handler:
        """A handler object of type `built` (made by `maker`, where a call made it): the
        framework's own passes on; a type of this module, or one it extends, runs its handler
        method; any other was produced where this analysis does not read."""
        made, seen = built, set[str]()
        while built is not None and built not in seen:
            seen.add(built)
            package = dotted_package(built)
            if package is not None and any(
                package == framework or package.startswith(framework + ".")
                for framework in self._rule.framework
            ):
                return Handler(outcome=PASSES_ON)
            methods = sorted(self._by_type.get(built, ()))
            if methods:
                # A compiler's bridge (`handle(Object)`) hands the context to the method it
                # stands for, which is the one the row names.
                stands_for = [
                    m
                    for m in methods
                    if any(c in methods for c, _ in self._index.callers.get((m, 0), ()))
                ]
                return Handler((*stands_for, *(m for m in methods if m not in stands_for)))
            built = self._index.superclasses.get(built)
        return Handler(outcome=UNREADABLE, unread=maker or made)


def _either(handlers: list[Handler]) -> Handler:
    """Several objects a handler argument may be: one that passes on makes it middleware (a
    row is lost, never invented, spec §3b's admitted incompleteness); then one not readable
    here; else every one's methods."""
    for outcome in (PASSES_ON, UNREADABLE):
        found = [h for h in handlers if h.outcome == outcome]
        if found:
            return found[0]
    if not handlers:
        return Handler(outcome=UNREADABLE)
    return Handler(tuple(dict.fromkeys(s for h in handlers for s in h.symbols)))


def handler_outcomes(
    index: ValueIndex,
    calls: frozenset[tuple[str, str]],
    handlers: Mapping[str, int],
) -> tuple[dict[str, Outcome], dict[str, tuple[str, ...]]]:
    """Each handler method's outcome, keyed by its symbol, and for each one not readable here
    the methods outside the module it hands the context to. `handlers` maps a handler method
    to the parameter that receives the context.

    Cost (GUIDELINES §8.7): one producer walk per `passes_on` call site in the module, one
    pass over the sites to find them and to group them by method, and one inversion of the
    calling edges; then, per handler, the call sites of the methods its context is handed to."""
    if not handlers:
        return {}, {}
    stop = frozenset(handlers)
    ended: set[tuple[str, int]] = set()
    by_method: dict[str, list[Mapping[str, Any]]] = {}
    for (method, _), site in sorted(index.sites.items(), key=lambda item: item[0][1]):
        by_method.setdefault(method, []).append(site)
        if (str(site.get("owner")), str(site["name"])) in calls:
            for end in producers_of(index, site, RECEIVER, frozenset(), stop_at_parameters_of=stop):
                if end.parameter is not None:
                    ended.add(end.parameter)
    handed: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for parameter, binders in index.callers.items():
        for binder in binders:
            handed.setdefault(binder, []).append(parameter)
    outcomes: dict[str, Outcome] = {}
    unread: dict[str, tuple[str, ...]] = {}
    for symbol, context in handlers.items():
        reached, outside = _handed_on(index, by_method, handed, (symbol, context))
        if reached & ended:
            outcomes[symbol] = PASSES_ON
        elif outside:
            outcomes[symbol] = UNREADABLE
            unread[symbol] = outside
        else:
            outcomes[symbol] = ANSWERS
    return outcomes, unread


def _handed_on(
    index: ValueIndex,
    by_method: Mapping[str, list[Mapping[str, Any]]],
    handed: Mapping[tuple[str, int], list[tuple[str, int]]],
    start: tuple[str, int],
) -> tuple[set[tuple[str, int]], tuple[str, ...]]:
    """Every `(method, parameter)` the context at `start` is handed to as an argument, `start`
    included, and the methods outside the module it is handed to. A call ON the context is
    not a hand-off: the receiver is not an argument."""
    reached = {start}
    stack = [start]
    outside: list[str] = []
    while stack:
        method, parameter = stack.pop()
        for site in by_method.get(method, ()):
            key = (method, int(site["ordinal"]))
            for slot, argument in enumerate(site.get("arguments") or ()):
                if not (
                    isinstance(argument, dict)
                    and argument.get("kind") == "parameter"
                    and argument.get("value") == parameter
                ):
                    continue
                targets = [target for target in handed.get(key, ()) if target[1] == slot]
                for target in targets:
                    if target not in reached:
                        reached.add(target)
                        stack.append(target)
                if not targets and key not in index.reached:
                    outside.append(
                        method_descriptor(
                            str(site.get("owner")), str(site["name"]), str(site["descriptor"])
                        )
                    )
    return reached, tuple(sorted(set(outside)))


# The `open_questions` kind a row whose handler is not readable here is filed under
# (`resolve/open_questions.py` owns the closed set; this is the one name it holds for it).
HANDLER_PASS_THROUGH = "handler_pass_through"


def file_unread(
    questions: dict[tuple[str, str | None, str], dict[str, Any]],
    row: Mapping[str, Any],
    unread: tuple[str, ...],
) -> None:
    """Notes one row whose handler is not readable here (spec §3b), against the row's own
    wire identity: the handler, the method that registered it and the code outside the module
    it depends on. `questions` is the run's accumulator, written once by `unread_rows`; rows
    sharing one identity share one question, each a candidate of it."""
    question = questions.setdefault(
        (str(row["protocol"]), row["method"], str(row["path"])),
        {
            "protocol": row["protocol"],
            "method": row["method"],
            "path": row["path"],
            "candidates": [],
        },
    )
    candidate = {"handler": row["handler"], "caller": row["caller"], "unread": list(unread)}
    if candidate not in question["candidates"]:
        question["candidates"].append(candidate)


def unread_rows(
    questions: Mapping[tuple[str, str | None, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """The `open_questions` rows of a run's unreadable handlers, in a stable order (NFR-1). The
    evidence names the code a reader would have to open to answer each."""
    rows = []
    for key in sorted(questions, key=lambda k: (k[0], k[1] or "", k[2])):
        candidates = sorted(
            questions[key]["candidates"], key=lambda c: json.dumps(c, sort_keys=True)
        )
        rows.append(
            {
                "protocol": key[0],
                "method": key[1],
                "path": key[2],
                "question": HANDLER_PASS_THROUGH,
                "candidates": json.dumps(candidates, sort_keys=True, separators=(",", ":")),
                "evidence": "; and ".join(_unread_sentence(c) for c in candidates),
            }
        )
    return rows


def _unread_sentence(candidate: Mapping[str, Any]) -> str:
    handler = candidate["handler"] or "a handler object"
    if candidate["unread"]:
        return (
            f"{handler}, registered by {candidate['caller']}, depends on "
            f"{', '.join(candidate['unread'])}, whose body this analysis does not read"
        )
    return (
        f"{handler}, registered by {candidate['caller']}, is produced where this analysis "
        f"does not read"
    )
