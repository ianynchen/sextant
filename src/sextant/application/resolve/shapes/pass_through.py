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
  read, or stored where the walk cannot follow it (a field, a constructor: a later `next()`
  on it is on a `getfield` no fact names), or the handler object is produced outside the
  module and its declared static type is not the framework's (ruling 2026-10-31).

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
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any, Literal

from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import Dispatch
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.application.resolve.values import (
    ESCAPES,
    EXTERNAL,
    NOT_READABLE,
    RECEIVER,
    ValueIndex,
    producer_paths,
    producers_of,
)
from sextant.domain.symbols import (
    bare_descriptor,
    dotted_package,
    method_descriptor,
    method_name,
    owner_of,
    returned_type,
    with_owner,
)

Outcome = Literal["passes_on", "answers", "unreadable"]
PASSES_ON: Outcome = "passes_on"
ANSWERS: Outcome = "answers"
UNREADABLE: Outcome = "unreadable"

# Why a handler is not readable here: what an `unread` entry says, as `(reason, detail)`. The
# reason is one of the general list (`values`); the detail is one sentence for a person, made
# once, here, where the answer is made. No code reads it.
Unread = tuple[str, str]

_HANDED_TO = "hands the request's context to {}, where it is not followed"
_STORED_IN = "stores the request's context in {}, where it is not followed"
_PRODUCED_BY = "is built by {}, whose body is not read"
_OF_TYPE = "is declared as {}, a type whose handler is not read"
_FROM_FIELD = "comes from {}, whose declared type is not a handler read here"
_NO_BODY = "runs {}, which has no body read here and no module override"
_UNREAD_ARGUMENT = "is an argument of {} that is not read"


def _escapes(phrase: str, name: str) -> Unread:
    """The context goes where the walk does not follow it."""
    return (ESCAPES, phrase.format(name))


def _not_followed(scanned: AbstractSet[str], owner: str | None, phrase: str, name: str) -> Unread:
    """Code the walk does not follow: `external` where the type that would answer (`owner`) is
    not in the scanned code, `not_readable` where it is there (or is not known)."""
    outside = owner is not None and owner not in scanned
    return (EXTERNAL if outside else NOT_READABLE, phrase.format(name))


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
    # Why it is not readable here: with `outcome` UNREADABLE, the whole answer; beside
    # `symbols`, a handler method with no body, which makes the handler unreadable unless one
    # of the others passes on.
    unread: Unread | None = None
    # The handler method with no body that `unread` is about, beside `symbols`.
    bodiless: str | None = None
    # The bodies that may be the one answering, where dispatch can run more than one — a
    # bodiless method's several implementations, a method and its overrides, or several
    # objects the argument may be. Several is the narrowed case: one row each (`fluent`).
    # A bridge and the method it stands for are one handler, never two alternatives.
    alternatives: tuple[str, ...] = ()


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

    Where the producer walk reaches no call that made the object (an `escapes`, a parameter
    nothing binds), the object is identified by what it IS: the declared static type of the
    parameter, field or factory return it came from (`_declared`), read off the facts the run
    already holds.

    Built once per run: the module's handler methods by type and the producer reader's stops
    are each one pass, over the method symbols and over the index's library calls.
    `parameters` is `declared_parameters_of`; `field_types` reads each field's declared type,
    asked only where a handler comes from a field; `dispatch` is the hierarchy `call_edges`
    reads (`dispatch_of`), and `exact` the methods a reference runs exactly (`exact_methods`),
    so a handler method runs what `Dispatch.candidates` says a call to it would run: from a
    construction, the constructed class's declared or inherited body alone; from a declared
    type or a virtual reference, that body plus every module override below the NAMED type."""

    def __init__(
        self,
        index: ValueIndex,
        rule: PassThroughRule,
        method_symbols: Mapping[str, str],
        parameters: Mapping[str, Sequence[Mapping[str, Any]]],
        field_types: Callable[[], Mapping[str, str]],
        dispatch: Dispatch,
        exact: AbstractSet[str],
    ) -> None:
        self._index = index
        self._dispatch = dispatch
        self._exact = exact
        self._rule = rule
        self._method_symbols = method_symbols
        self._parameters = parameters
        self._field_types = field_types
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
            named = str(argument.get("symbol"))
            symbol = self._method_symbols.get(named)
            if symbol is None:
                return Handler(outcome=UNREADABLE, unread=self._no_body(named))
            # A lambda's body takes what it captured first; the context follows. A private or
            # static method (every synthetic lambda body among them) runs exactly; any other is
            # dispatched on the type the reference names, as a virtual call is.
            return self._runs(
                (symbol,),
                int(argument.get("captures") or 0),
                named=owner_of(bare_descriptor(symbol)),
                dispatched=symbol not in self._exact,
            )
        if isinstance(argument, dict) and argument.get("kind") == "instance":
            return self._object(str(argument.get("symbol")), None, constructed=True)
        at = self._index.sites.get((site[0], site[1])) if site is not None else None
        if at is None or site is None:
            where = site[0] if site is not None else "a registering method"
            return Handler(outcome=UNREADABLE, unread=self._unread_argument(where))
        handlers = []
        unmade = False
        for end in producers_of(self._index, at, site[2], self._declared):
            made = self._index.sites.get((str(end.caller), int(end.ordinal or 0)))
            if end.identity is None or made is None:
                unmade = True
                continue
            owner, name = end.identity
            descriptor = str(made["descriptor"])
            constructed = name == "<init>"
            built = owner if constructed else returned_type(descriptor)
            maker = method_descriptor(owner, name, descriptor)
            handlers.append(self._object(built, maker, constructed=constructed))
        if unmade or not handlers:
            arguments = at.get("arguments") or ()
            argument = arguments[site[2]] if site[2] < len(arguments) else None
            declared = self._declared_type(site[0], argument, set())
            handlers.extend(
                declared or [Handler(outcome=UNREADABLE, unread=self._unread_argument(site[0]))]
            )
        return _either(handlers)

    def _runs(
        self, symbols: Sequence[str], context: int, named: str | None, dispatched: bool
    ) -> Handler:
        """What calling the handler methods `symbols` on an object of the type `named` runs,
        mirroring `Dispatch.candidates`: the body `named` declares or inherits, and — where the
        call is `dispatched` (a declared type, a virtual reference) rather than made on a
        construction or to a private or static method — every module override of it below
        `named`, never a sibling's. A method with none is not readable here, named."""
        found: list[str] = []
        bodiless: list[str] = []
        alternatives: list[str] = []
        for position, symbol in enumerate(symbols):
            bare = bare_descriptor(symbol)
            start = named or owner_of(bare) or ""
            runs = self._inherited(bare, start)
            if dispatched:
                for subtype in self._dispatch.subtypes.get(start, ()):
                    runs.extend(
                        s
                        for s in self._dispatch.bodies.get(with_owner(bare, subtype), ())
                        if s not in runs
                    )
            # The first method is the handler the row names (a bridge comes after the method
            # it stands for): what dispatching to it can run are the alternatives.
            if position == 0:
                alternatives = list(runs)
            if runs:
                found.extend(r for r in runs if r not in found)
            else:
                bodiless.append(symbol)
        if not found:
            return Handler(outcome=UNREADABLE, unread=self._no_body(bodiless[0]))
        return Handler(
            tuple(dict.fromkeys([*alternatives, *found])),
            context=context,
            unread=self._no_body(bodiless[0]) if bodiless else None,
            bodiless=bodiless[0] if bodiless else None,
            alternatives=tuple(alternatives),
        )

    def _inherited(self, bare: str, start: str) -> list[str]:
        """The body of the method `bare` names that an object of type `start` runs: its own
        declaration's, else the nearest superclass's (JVMS 5.4.3.3's class arm)."""
        seen: set[str] = set()
        current: str | None = start
        while current is not None and current not in seen:
            seen.add(current)
            found = self._dispatch.bodies.get(with_owner(bare, current))
            if found:
                return list(found)
            current = self._index.superclasses.get(current)
        return []

    def _declared_type(
        self, method: str, argument: Any, seen: set[tuple[str, int]]
    ) -> list[Handler]:
        """The handler `argument` is by its DECLARED STATIC TYPE, in `method`'s frame: a
        parameter's declared type, and where that says nothing (`Handler`), the static type of
        what each caller hands it; a factory call's declared return; a field's declared type.
        Each is a descriptor the facts already carry. An argument with none of these (a
        `null`) contributes nothing."""
        if not isinstance(argument, dict):
            return []
        kind = argument.get("kind")
        if kind in ("lambda", "instance"):
            return [self.of(argument, None)]
        if kind == "parameter":
            position = int(argument.get("value") or 0)
            if (method, position) in seen:
                return []
            seen.add((method, position))
            declared = self._parameters.get(method, ())
            typed = declared[position].get("erased_symbol") if position < len(declared) else None
            found = self._typed(None if typed is None else str(typed), constructed=False)
            if found is not None:
                return [found]
            handed: list[Handler] = []
            for caller, ordinal, slot in self._index.callers.get((method, position), ()):
                bound = (self._index.sites.get((caller, ordinal)) or {}).get("arguments") or ()
                if slot < len(bound):
                    handed.extend(self._declared_type(caller, bound[slot], seen))
            return handed or [
                Handler(
                    outcome=UNREADABLE,
                    unread=(
                        self._unread_argument(method)
                        if typed is None
                        else self._of_type(str(typed))
                    ),
                )
            ]
        if kind == "field" and argument.get("symbol") is not None:
            field = str(argument["symbol"])
            typed = self._field_types().get(field)
            found = None if typed is None else self._typed(typed, constructed=False)
            return [found or Handler(outcome=UNREADABLE, unread=self._from_field(field, typed))]
        if argument.get("source") is not None:
            handlers = []
            for ordinal in self._index.producers.get((method, int(argument["source"])), ()):
                made = self._index.sites.get((method, ordinal))
                if made is None:
                    continue
                descriptor = str(made["descriptor"])
                owner, name = str(made.get("owner")), str(made["name"])
                # A construction builds its owner, as `of` reads one, and runs exactly its
                # class's body; a factory's declared return is a type, dispatched.
                constructed = name == "<init>"
                built = owner if constructed else returned_type(descriptor)
                maker = method_descriptor(owner, name, descriptor)
                handlers.append(self._object(built, maker, constructed=constructed))
            return handlers
        return []

    def _object(self, built: str | None, maker: str | None, *, constructed: bool) -> Handler:
        """A handler object of type `built` (made by `maker`, where a call made it; exactly
        that class where `constructed`): the framework's own passes on; a type of this
        module, or one it extends, runs its handler method; any other was produced where this
        analysis does not read."""
        if maker is not None:
            unread = _not_followed(self._dispatch.scanned, owner_of(maker), _PRODUCED_BY, maker)
        else:
            unread = self._of_type(built)
        return self._typed(built, constructed=constructed) or Handler(
            outcome=UNREADABLE, unread=unread
        )

    def _no_body(self, symbol: str) -> Unread:
        """A handler method with no body read: `external` where its type is not scanned. A
        method found through a scanned type (`_runs`) is always `not_readable`; `external` is
        reached by a method reference or lambda whose type is not scanned."""
        return _not_followed(
            self._dispatch.scanned, owner_of(bare_descriptor(symbol)), _NO_BODY, symbol
        )

    def _of_type(self, built: str | None) -> Unread:
        """A handler object of a type nothing here reads a handler of."""
        return _not_followed(self._dispatch.scanned, built, _OF_TYPE, built or "an unread type")

    def _from_field(self, field: str, declared: str | None) -> Unread:
        """A handler object from a field, by the field's declared type where it has one, else by
        the type that owns the field (a static field of a library class is `external`)."""
        owner = declared if declared is not None else owner_of(bare_descriptor(field))
        return _not_followed(self._dispatch.scanned, owner, _FROM_FIELD, field)

    def _unread_argument(self, where: str) -> Unread:
        """An argument of a registering method that nothing read gives a value for. The method
        is in the scanned code, so the answer is there and not followed."""
        return (NOT_READABLE, _UNREAD_ARGUMENT.format(where))

    def _typed(self, built: str | None, *, constructed: bool) -> Handler | None:
        """What a type says on its own: a type of a `framework_handlers` package passes on; a
        type of this module, or one it extends, runs its handler method — exactly the one it
        declares or inherits where it was `constructed`, and every override below it where it
        is only declared; None for any other."""
        named = built
        seen: set[str] = set()
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
                    if any(c in methods for c, _, _ in self._index.callers.get((m, 0), ()))
                ]
                return self._runs(
                    (*stands_for, *(m for m in methods if m not in stands_for)),
                    0,
                    named=named,
                    dispatched=not constructed,
                )
            built = self._index.superclasses.get(built)
        return None


def _either(handlers: list[Handler]) -> Handler:
    """Several objects a handler argument may be: one that passes on makes it middleware (a
    row is lost, never invented, spec §3b's admitted incompleteness); then one not readable
    here; else every one's methods."""
    for outcome in (PASSES_ON, UNREADABLE):
        found = [h for h in handlers if h.outcome == outcome]
        if found:
            return found[0]
    bodiless = next((h.unread for h in handlers if h.unread is not None), None)
    return Handler(
        tuple(dict.fromkeys(s for h in handlers for s in h.symbols)),
        unread=bodiless,
        bodiless=next((h.bodiless for h in handlers if h.bodiless is not None), None),
        alternatives=tuple(dict.fromkeys(s for h in handlers for s in h.alternatives)),
    )


def exact_methods(workspace: Workspace) -> frozenset[str]:
    """The module's private and static methods: a reference to one runs it exactly, never an
    override (JVMS: neither is dispatched). The `Workspace.once` builder, one read of
    `method_visibility` per load."""
    return frozenset(
        str(row["symbol"])
        for row in workspace.query("method_visibility")
        if row["visibility"] == "private" or row["static"]
    )


def handler_outcomes(
    index: ValueIndex,
    calls: frozenset[tuple[str, str]],
    handlers: Mapping[str, int],
) -> tuple[dict[str, Outcome], dict[str, tuple[Unread, ...]]]:
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
            # WHICH OBJECT the context is (`which_object`): a call made on it before `next()` —
            # `ctx.put(k, v); ctx.next()` — does not make it another context (spec 2026-11-02
            # fix round 1, C1, which reads a parameter's own window).
            for end, _ in producer_paths(
                index, site, RECEIVER, frozenset(), stop_at_parameters_of=stop, which_object=True
            ):
                if end.parameter is not None:
                    ended.add(end.parameter)
    handed: dict[tuple[str, int], list[tuple[tuple[str, int], int]]] = {}
    for parameter, binders in index.callers.items():
        for caller, ordinal, slot in binders:
            handed.setdefault((caller, ordinal), []).append((parameter, slot))
    # A parameter written into a field (`written_by`): a context stored there is read back by
    # a `getfield` no fact names, so the walk cannot follow it to a `next()`.
    stored: dict[tuple[str, int], list[str]] = {}
    for field, writers in index.writers.items():
        for writer in writers:
            stored.setdefault(writer, []).append(field)
    outcomes: dict[str, Outcome] = {}
    unread: dict[str, tuple[Unread, ...]] = {}
    for symbol, context in handlers.items():
        reached, outside = _handed_on(index, by_method, handed, stored, (symbol, context))
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
    handed: Mapping[tuple[str, int], list[tuple[tuple[str, int], int]]],
    stored: Mapping[tuple[str, int], list[str]],
    start: tuple[str, int],
) -> tuple[set[tuple[str, int]], tuple[Unread, ...]]:
    """Every `(method, parameter)` the context at `start` is handed to as an argument, `start`
    included, and where it goes that the walk cannot follow: a method whose body is not read,
    a field it is written to, a constructor it is handed to (which keeps it in the object,
    as javac's synthetic capture field does). A call ON the context is not a hand-off: the
    receiver is not an argument."""
    reached = {start}
    stack = [start]
    outside: list[Unread] = []
    while stack:
        method, parameter = stack.pop()
        outside.extend(_escapes(_STORED_IN, field) for field in stored.get((method, parameter), ()))
        for site in by_method.get(method, ()):
            key = (method, int(site["ordinal"]))
            for slot, argument in enumerate(site.get("arguments") or ()):
                if not (
                    isinstance(argument, dict)
                    and argument.get("kind") == "parameter"
                    and argument.get("value") == parameter
                ):
                    continue
                targets = [target for target, at in handed.get(key, ()) if at == slot]
                for target in targets:
                    if target not in reached:
                        reached.add(target)
                        stack.append(target)
                if site["name"] == "<init>" or (not targets and key not in index.reached):
                    outside.append(
                        _escapes(
                            _HANDED_TO,
                            method_descriptor(
                                str(site.get("owner")), str(site["name"]), str(site["descriptor"])
                            ),
                        )
                    )
    return reached, tuple(sorted(set(outside)))


# The `open_questions` kind a row whose handler is not readable here is filed under
# (`resolve/open_questions.py` owns the closed set; this is the one name it holds for it).
HANDLER_PASS_THROUGH = "handler_pass_through"


def file_unread(
    questions: dict[tuple[str, str | None, str | None], dict[str, Any]],
    row: Mapping[str, Any],
    unread: tuple[Unread, ...],
) -> None:
    """Notes one row whose handler is not readable here (spec §3b), against the row's own
    wire identity: the handler, the method that registered it and the code outside the module
    it depends on. `questions` is the run's accumulator, written once by `unread_rows`; rows
    sharing one identity share one question, each a candidate of it."""
    question = questions.setdefault(
        (str(row["protocol"]), row["method"], row["path"]),
        {
            "protocol": row["protocol"],
            "method": row["method"],
            "path": row["path"],
            "method_kind": row.get("method_kind"),
            "path_kind": row.get("path_kind"),
            "candidates": [],
        },
    )
    candidate = {
        "handler": row["handler"],
        "caller": row["caller"],
        "unread": [{"reason": reason, "detail": detail} for reason, detail in unread],
    }
    if candidate not in question["candidates"]:
        question["candidates"].append(candidate)


def unread_rows(
    questions: Mapping[tuple[str, str | None, str | None], dict[str, Any]],
) -> list[dict[str, Any]]:
    """The `open_questions` rows of a run's unreadable handlers, in a stable order (NFR-1). The
    evidence names the code a reader would have to open to answer each."""
    rows = []
    for key in sorted(questions, key=lambda k: (k[0], k[1] or "", k[2] or "")):
        candidates = sorted(
            questions[key]["candidates"], key=lambda c: json.dumps(c, sort_keys=True)
        )
        rows.append(
            {
                "protocol": key[0],
                "method": key[1],
                "path": key[2],
                "method_kind": questions[key]["method_kind"],
                "path_kind": questions[key]["path_kind"],
                "question": HANDLER_PASS_THROUGH,
                "candidates": json.dumps(candidates, sort_keys=True, separators=(",", ":")),
                "evidence": "; and ".join(_unread_sentence(c) for c in candidates),
            }
        )
    return rows


def _unread_sentence(candidate: Mapping[str, Any]) -> str:
    handler = candidate["handler"] or "a handler object"
    reasons = ", and ".join(entry["detail"] for entry in candidate["unread"])
    return f"{handler}, registered by {candidate['caller']}, {reasons}"
