"""The backward value walk (spec 2026-09-22 §1b): the one operation that answers
*what is this value?*

Before this module there was no such operation. There was *follow exactly one hop, in
the direction a catalog named* — measured at §0: six modules follow a `source` id in
twenty places, seven state "one hop" as an explicit cap in eighteen, and the whole
resolve layer contains exactly one multi-hop follow, which runs forwards. Every time a
framework put a value one hop further away than a catalog could reach, the answer was a
new catalog WORD (`channel_via`, `url_via`, `type_carriers`, `call_wrappers`, `getters`,
`indexed`, `compose`), so distance was re-described per catalog and capped per catalog.
This walk replaces the distance half of all seven. It does not replace the other half:
what a value MEANS stays catalog data (§1e, DR-6).

## The rules that carry the design

**The unit of resolution is the PATH, not the position (§1c, ruling M-1).** A helper

    void register(String queue, Class<?> type) { registry.add(queue, type); }
    register("orders",  OrderWorker.class);
    register("billing", BillingWorker.class);

resolved per POSITION gives `queue ∈ {orders, billing}` and `type ∈ {OrderWorker,
BillingWorker}` — four combinations, two of which no code path produces, recorded at
`resolved` and indistinguishable from an observation. Per path it is two bindings. So
**memoisation is keyed on (position, path) and never on position alone**: a per-position
memo is precisely what discards the correlation and mints the fabrication back. The key
is complete because the path records every crossing the walk made, and a crossing is the
only thing that can change a position's answer.

**Multiplicity has exactly one rule, and it is about paths (§1c).** Several paths are
several bindings — several callers, several returns in one callee, several enumerable
array elements — because each is real code that runs. A single path whose value cannot be
enumerated is ONE `unresolved`, with no element list at all. That is D00's array rule
generalised: every index a distinct written constant yields elements; built in a loop,
populated on a branch, left partly unwritten, or handed to another method first yields a
reason instead.

**Termination is the path, not a budget.** A position already on the current path answers
`cycle`; a producer outside what was scanned answers `external`. **There is no cap** (§3a):
`fan_out` and `depth` are deliberately absent from the reason vocabulary, and Task 4's
measurement — on `mall-admin`, 48 MB of facts — is the ruling point for whether one is
ever needed. Adding one here on judgement would settle by default the question that task
exists to answer.

**No false positives.** Every ambiguity is an `unresolved` answer naming one of §1d's six
reasons, never a guess. A reader can act on each: "we cannot see the jar" is not "the code
branches", and today both collapse into a single word.

## What it reads, and why that is more than the edge query

`value_edges` (spec §1a, the query's own file) is where the walk goes NEXT — it normalises
five edge kinds out of three existing tables and stores nothing. It carries no VALUE: the
answers themselves live in D00 §5's argument grammar, on `call_sites` and on
`method_returns`, so the walk reads those too, and `call_edges` for the one question the
edges cannot answer (was a body read at all, which is what separates `external` from
`not_readable`). Five queries, folded into `ValueIndex` once.

Two of the five edge kinds are therefore read off the grammar rather than off the query:
`read_from_binding` and `names_declaration` carry **no `to_index`** (the query's own header
states that `to_index` is meaningful for `bound_to_parameter` alone), so neither can say
WHICH slot it is about, and a walk resolving a slot cannot use them. The same facts are in
the argument entry at that slot, which the walk must read anyway to answer with a literal.

**A FOURTH table, stated because the edge query says three.** `value_edges.sql`'s header
says it is normalised out of `call_sites`, `return_flows` and `call_edges`; this module
reads `call_edges` DIRECTLY as well, for one question the edges cannot answer — whether a
site's body was read at all. That is the whole difference between `external` (we cannot see
the producer) and `not_readable` (we can, and nothing names its value), and it is the
common case rather than a corner: MEASURED on `mall-admin`, 1,411 of 2,065 value-producing
call sites are the third-party boundary, which `call_edges` records with a NULL callee.
A reader tracing this module's inputs finds four, and this is why.

**The sixth edge is missing and its absence is an answer.** `written_by` — a binding
assigned anywhere but an initialiser — is specified as a scanner capability (§4, D00 9.19)
and no backend reports it yet, so `value_edges` emits no such row. Every binding read
therefore ends at `no_writer`, which today means *no writer edge exists to follow* and not
*this binding is never written* — `NO_WRITER` below says so where the reason is defined.
`_binding` is the one place that will follow the edge the day it exists. The walk does NOT
re-derive it from the constructor-only `field_writes` fact: that would be a second spelling
of an edge the design gives one home, which is the disease §0a records.

**It names no framework and no language.** `identified_by` (§2) is catalog data that
arrives later; until it does, a producer whose value nothing names answers with a reason
rather than with framework knowledge this layer is not allowed to hold.

**Nothing consumes this yet, deliberately** (§3a step 1): the walk ships unwired, and
Task 4's measurement is the gate before any engine calls it.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.workspace import Workspace

# §1d's CLOSED vocabulary. Each names a different thing a reader can act on, which is the
# whole point of having six words where today there is one: COVERAGE can say "we cannot
# see the jar" or "the code branches", and a catalog author debugging a NULL address can
# tell which they are looking at. `fan_out` and `depth` are absent by ruling, not by
# oversight — §3a decides whether a cap exists at all, and a reason for one before the
# measurement would be a cap smuggled in as vocabulary.
NOT_READABLE = "not_readable"
NON_ENUMERABLE = "non_enumerable"
ESCAPES = "escapes"
# **What this means TODAY, said where the reason is defined.** §1d reads "a binding nothing
# in this module writes", and that is what it will mean once capability 9.19 lands and
# `value_edges` grows its `written_by` arm. Until then no writer edge exists at all, so the
# answer is *nothing was found to follow* — NOT *this binding is never written*. A reader
# acting on today's answer is reading a missing capability, not a property of the code.
NO_WRITER = "no_writer"
EXTERNAL = "external"
CYCLE = "cycle"
_REASONS = (NOT_READABLE, NON_ENUMERABLE, ESCAPES, NO_WRITER, EXTERNAL, CYCLE)

LITERAL = "literal"
EXPRESSION = "expression"
# **The code STATES there is no value here** — an explicit null, and a zero-length varargs
# call. A resolved answer, not a miss, and it has to be tellable from both: D00 §5 draws
# exactly this line for the empty element list ("the empty list is the FACT, and it is the
# one place in this grammar where an empty value says something an absent key would not,
# because 'called with no values' is a different statement from 'the array could not be
# read'"), so answering `non_enumerable` there would call a known-empty thing ambiguous and
# contradict the facts. Carries no value and no reason (ruled 2026-09-23).
ABSENT = "absent"
UNRESOLVED = "unresolved"

STRING = "string"
INT = "int"
BOOL = "bool"
# **The fourth `literal_kind` — and `kind` is still the set the spec pins.** §1b's answer
# kinds are what they were; this is the `literal_kind` vocabulary gaining a member, and the
# distinction matters to a reader checking the spec against the code. It earns its place by
# what it PREVENTS. A declaration reference (`OrderWorker.class`, a named constant, the
# concrete type a value was built from) IS the value — `value_edges.sql`'s
# `names_declaration` arm says the walk stops there with an answer — and the answer has to
# carry the symbol. Carrying it as a `string` would hand `com/acme/OrderWorker#` to a
# catalog reading a destination out of that slot, which publishes a symbol as an address: a
# fabrication at `resolved`, which is the one failure §7 says this whole work risks. A
# consumer that wants text tests for `string` (approved 2026-09-23).
SYMBOL = "symbol"

# The one slot that is not an argument index (§1b: one entry point, not two — a receiver
# is a slot like any other, and splitting them is how a third form gets added later).
RECEIVER = "receiver"

# D00 §5's argument grammar, read as answers. `long` answers `int` because the
# distinction is a storage width and not a kind of value a consumer branches on; a catalog
# reading a port wants the number either way.
_LITERAL_KINDS = {"string": STRING, "int": INT, "long": INT, "boolean": BOOL}
# The three kinds `names_declaration` is built from (`value_edges.sql`): a type reference,
# a named constant of its own type, and the concrete type a constructed value was built
# from. A `lambda` is NOT one of them, on meaning rather than shape — it names a body, and
# a walk handed that symbol would have a method descriptor where it asked for a value.
_DECLARATION_KINDS = ("class", "enum", "instance")

# Position kinds. A position is what the walk resolves; the memo and the cycle check are
# both keyed on one, so the set is spelled out rather than left to whatever tuple shape a
# call site happens to build.
_SLOT = "slot"
_VALUE = "value"
_PARAMETER = "parameter"
_BINDING = "binding"
# Contexts a path records a CHOICE for. Two slots of one site may disagree about nothing:
# if both cross out of the same method, they cross through the same call (M-1); if both
# read the same value, they read the same return of the same callee. Different contexts
# are independent, and combining them is not a fabrication but the code's own product.
_CALLER_OF = "caller-of"
_RETURN_OF = "return-of"
_ELEMENT_OF = "element-of"


@dataclass(frozen=True)
class Answer:
    """What a slot holds, on one path (§1b).

    `kind` is `literal`, `expression`, `absent` or `unresolved`. A literal is a value the
    code states and `literal_kind` says which sort (`string`, `int`, `bool`, or `symbol`
    for a declaration reference — see `SYMBOL`); `value` carries it. An expression is a
    `${…}` or a composed address, carried **verbatim with its holes unfilled** — §6 as
    amended 2026-09-23 refuses to EVALUATE a concatenation, and §8.2 keeps this repository
    out of guessing deployed values, so no hole is ever filled in and no literal is ever
    minted from one. `absent` is the code stating there is no value (see `ABSENT`). An
    `unresolved` answer carries one of `_REASONS` and no value.
    """

    kind: str
    value: Any = None
    literal_kind: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Binding:
    """One call site's slots, as ONE path reaches them (§1b).

    `path` is the crossings the walk made to reach these answers, outermost first: a call
    it stepped out through, or a callee return it stepped into. An engine reads whichever
    slots it cares about OUT OF ONE binding, so it never sees a loose per-slot set and
    cannot recombine across paths — M-1's fabrication is structurally impossible rather
    than contractually forbidden.

    `slots` is keyed by argument index, or by `RECEIVER`. A site whose facts name no
    receiver has no such key: a slot answering `not_readable` about a position that does
    not exist is noise a reader would have to learn to ignore.
    """

    path: tuple[str, ...]
    slots: dict[int | str, Answer]


@dataclass(frozen=True)
class ValueIndex:
    """The five reads the walk needs, folded once (GUIDELINES §8.7: cost is a design
    input, decided before the code exists — and this walk is asked about one position at
    a time, thousands of times, over an edge query that is 59,254 rows on `mall-admin`).

    It is NOT cached on the workspace: `Workspace.once` refuses a value built from
    anything but fact queries, and two of these five (`value_edges`, which reads
    `return_flows` and `call_edges`, and `call_edges` itself) are derived — a derivation
    run after the fold would leave it stale. So the lifetime is the CALLER's, stated here
    as a parameter rather than hidden in a cache with no invalidation.
    """

    # Every call site, by (method, ordinal) — the site's identity everywhere in D01.
    sites: dict[tuple[str, int], Mapping[str, Any]]
    # (method, value id) -> the ordinals of calls made ON that value, for `escapes`.
    receivers: dict[tuple[str, int], tuple[int, ...]]
    # `produced_by`: (method, value id) -> the ordinals of the sites that produced it.
    producers: dict[tuple[str, int], tuple[int, ...]]
    # `returned_by`: (method, value id) -> (site ordinal, callee) — read its returns.
    returns: dict[tuple[str, int], tuple[tuple[int, str], ...]]
    # `bound_to_parameter`, indexed the way the walk asks it: BACKWARD, from a method's
    # parameter to the call sites that bind it. This is the edge that crosses a method
    # boundary and the one §1c's ruling is about.
    callers: dict[tuple[str, int], tuple[tuple[str, int], ...]]
    # What each method hands back, one entry per return instruction, in the argument
    # grammar. A void return is dropped: it can only answer a site holding no value.
    returned_values: dict[str, tuple[tuple[int, Mapping[str, Any]], ...]]
    # The sites where a body was actually read. `call_edges` writes a row per site with a
    # NULL callee at the third-party boundary, and that boundary is what separates
    # `external` (we cannot see the producer) from `not_readable` (we can, and it names
    # no value) — a distinction §1d exists to make and the edge query cannot.
    reached: frozenset[tuple[str, int]]


def value_index(workspace: Workspace) -> ValueIndex:
    """The index for one resolve. Built by `resolve_site` when it is not handed one."""
    sites: dict[tuple[str, int], Mapping[str, Any]] = {}
    receivers: dict[tuple[str, int], list[int]] = {}
    for row in workspace.query("call_sites"):
        method, ordinal = str(row["caller"]), int(str(row["ordinal"]))
        sites[(method, ordinal)] = row
        if row["receiver"] is not None:
            receivers.setdefault((method, int(str(row["receiver"]))), []).append(ordinal)

    producers: dict[tuple[str, int], list[int]] = {}
    returns: dict[tuple[str, int], list[tuple[int, str]]] = {}
    callers: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for edge in workspace.query("value_edges"):
        kind = str(edge["kind"])
        method, ordinal = str(edge["from_method"]), int(str(edge["to_ordinal"]))
        if kind == "produced_by":
            producers.setdefault((method, int(str(edge["from_value"]))), []).append(ordinal)
        elif kind == "returned_by":
            value = (method, int(str(edge["from_value"])))
            returns.setdefault(value, []).append((ordinal, str(edge["to_symbol"])))
        elif kind == "bound_to_parameter":
            parameter = (str(edge["to_symbol"]), int(str(edge["to_index"])))
            callers.setdefault(parameter, []).append((method, ordinal))
        # `read_from_binding` and `names_declaration` are read off the argument entry at
        # the slot instead — they carry no `to_index`, so neither can say which slot it
        # is about. The module docstring states the consequence.

    returned_values: dict[str, tuple[tuple[int, Mapping[str, Any]], ...]] = {}
    for row in workspace.query("method_returns"):
        # DuckDB hands an explicit JSON null back as the four-character text `null`, not
        # as SQL NULL — the projection's own comment says so — so a void return is read
        # here rather than assumed away.
        text = row["value"]
        entry = None if text is None else json.loads(str(text))
        if not isinstance(entry, dict):
            continue
        method = str(row["method"])
        returned_values[method] = returned_values.get(method, ()) + (
            (int(str(row["ordinal"])), entry),
        )

    reached = frozenset(
        (str(row["caller"]), int(str(row["ordinal"])))
        for row in workspace.query("call_edges")
        if row["callee"] is not None
    )
    return ValueIndex(
        sites=sites,
        receivers={key: tuple(value) for key, value in receivers.items()},
        producers={key: tuple(value) for key, value in producers.items()},
        returns={key: tuple(value) for key, value in returns.items()},
        callers={key: tuple(value) for key, value in callers.items()},
        returned_values=returned_values,
        reached=reached,
    )


def resolve_site(
    workspace: Workspace, site: Mapping[str, Any], index: ValueIndex | None = None
) -> list[Binding]:
    """Every slot of one call site, resolved per path (§1b).

    `site` is a call-site row — the raw fact stream's or the projection's; the slots are
    read off the row handed in. `index` is the fold above, which a caller resolving many
    sites builds once.

    Returns one `Binding` per coherent path, in a deterministic order (NFR-1): the first
    slot's paths drive the outer order, and each slot's answers arrive in the edge query's
    own ordering. An empty list means no path answers every slot at once, which is the
    M-1 ruling taken to its end — the combination a per-position walk would have invented
    is not a row here.
    """
    walk = _Walk(index if index is not None else value_index(workspace))
    combined: list[tuple[_Trail, dict[int | str, Answer]]] = [((), {})]
    for slot in _slots_of(site):
        reached = walk.at(site, slot)
        combined = [
            (merged, {**slots, slot: answer})
            for trail, slots in combined
            for path, answer in reached
            if (merged := _combine(trail, path)) is not None
        ]
    return [Binding(path=_path(trail), slots=slots) for trail, slots in combined]


def _slots_of(site: Mapping[str, Any]) -> list[int | str]:
    """Which positions this site HAS. The arguments by index, and the receiver where the
    facts name one — `receiver` is the value id it came from and `receiver_parameter` the
    enclosing method's parameter index when it is one (D00 §5); a call that names neither
    has no receiver to resolve, and a static call never does."""
    arguments = site["arguments"] or []
    slots: list[int | str] = list(range(len(arguments)))
    if site.get("receiver") is not None or site.get("receiver_parameter") is not None:
        slots.append(RECEIVER)
    return slots


@dataclass(frozen=True)
class _Step:
    """One crossing, and the CHOICE it made.

    `context` is what the choice is about — the calling context of a method, the return
    that answers for a value, the element of an array. `label` is what was chosen, and is
    what a `Binding.path` carries. Two paths agree when they make the same choice in every
    context they share; contexts neither shares are independent, and that is the whole
    difference between M-1's fabricated cross product and the code's own.
    """

    context: tuple[Any, ...]
    label: str


_Trail = tuple[_Step, ...]
_Position = tuple[Any, ...]
_Reached = tuple[_Trail, Answer]


def _combine(left: _Trail, right: _Trail) -> _Trail | None:
    """The two paths as one, or None where they disagree — the coherence rule.

    Disagreement is per CONTEXT: two slots that both crossed out of `register` must have
    crossed through the same call. A context only one of them visited constrains nothing.
    """
    chosen = {step.context: step.label for step in left}
    for step in right:
        if chosen.setdefault(step.context, step.label) != step.label:
            return None
    visited = {step.context for step in left}
    return left + tuple(step for step in right if step.context not in visited)


def _path(trail: _Trail) -> tuple[str, ...]:
    """The path a binding carries: the crossings, OUTERMOST FIRST. The walk discovers the
    nearest crossing first and the furthest last, so the record reads the way a reader
    follows it — from the call that started the chain down to the site in hand."""
    return tuple(step.label for step in reversed(trail))


def _only(trail: _Trail, answer: Answer) -> tuple[_Reached, ...]:
    return ((trail, answer),)


def _unresolved(reason: str) -> Answer:
    return Answer(kind=UNRESOLVED, reason=reason)


class _Walk:
    """One resolve's walk. Not reused across sites: the memo is keyed on (position, path)
    and both are meaningful only within the resolve that built them."""

    def __init__(self, index: ValueIndex) -> None:
        self._index = index
        self._memo: dict[tuple[_Position, _Trail], tuple[_Reached, ...]] = {}
        # The positions the current path is IN THE MIDDLE OF resolving. §1d's `cycle` is
        # exactly a return to one of them.
        self._pending: set[_Position] = set()
        # The pending positions a result below has already answered `cycle` about. A
        # result that depends on one is true of THIS path and not of another that reaches
        # the same position by a different route, so it is not memoised.
        self._open: set[_Position] = set()

    def at(self, site: Mapping[str, Any], slot: int | str) -> tuple[_Reached, ...]:
        """One slot of the site the caller handed in, on the empty path."""
        return self._of_site(site, slot, (), ())

    def _resolve(
        self, position: _Position, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """`position`, on `trail` — memoised, and terminating.

        **The memo key is (position, path) and never position alone** (§1c). A position's
        answer depends on the path that reached it — that is the whole M-1 ruling — so a
        per-position memo would hand `register`'s second caller the first caller's answer
        and call the pair a row.

        `frames` is not part of the key because it is a function of the path: a frame is
        pushed only by a return crossing, and that crossing is on the path with the callee
        and the return it chose.
        """
        key = (position, trail)
        cached = self._memo.get(key)
        if cached is not None:
            return cached
        if position in self._pending:
            self._open.add(position)
            return _only(trail, _unresolved(CYCLE))
        self._pending.add(position)
        outer, self._open = self._open, set()
        reached = self._compute(position, trail, frames)
        unresolved_back_edges = self._open - {position}
        self._open = outer | unresolved_back_edges
        self._pending.discard(position)
        if not unresolved_back_edges:
            self._memo[key] = reached
        return reached

    def _compute(
        self, position: _Position, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        kind = position[0]
        if kind == _SLOT:
            site = self._index.sites.get((position[1], position[2]))
            if site is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return self._of_site(site, position[3], trail, frames)
        if kind == _VALUE:
            return self._value(position[1], position[2], trail, frames)
        if kind == _PARAMETER:
            return self._parameter(position[1], position[2], trail, frames)
        return self._binding(trail)

    def _of_site(
        self, site: Mapping[str, Any], slot: int | str, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        method, ordinal = str(site["caller"]), int(str(site["ordinal"]))
        if slot == RECEIVER:
            receiver = site.get("receiver")
            if receiver is not None:
                return self._through(method, int(str(receiver)), ordinal, trail, frames)
            parameter = site.get("receiver_parameter")
            if parameter is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return self._resolve((_PARAMETER, method, int(str(parameter))), trail, frames)
        arguments = site["arguments"] or []
        if not isinstance(slot, int) or not 0 <= slot < len(arguments):
            # A slot the site does not have. Reachable from data rather than only from a
            # caller's mistake: three of the edge query's arms read the raw fact stream,
            # so at a compiler-emitted default-argument bridge site the slot numbering is
            # the bridge's while the callee is the function it stands for (that query's
            # own stated boundary), and a parameter index can land past the argument list.
            # An answer naming the reason beats an exception a consumer cannot act on.
            return _only(trail, _unresolved(NOT_READABLE))
        return self._entry(arguments[slot], method, (_SLOT, method, ordinal, slot), trail, frames)

    def _entry(
        self,
        argument: Mapping[str, Any],
        method: str,
        origin: _Position,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """One entry of D00 §5's argument grammar, resolved in `method`'s own frame.

        `origin` is where the entry was read — a slot of a site, or a return of a method —
        and is what names the choice when an entry branches, and what says where a value
        is USED when one has to be followed back.
        """
        kind = str(argument.get("kind"))
        literal_kind = _LITERAL_KINDS.get(kind)
        if literal_kind is not None:
            value = argument.get("value")
            if value is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return _only(trail, Answer(kind=LITERAL, value=value, literal_kind=literal_kind))
        if kind == "concat":
            # W4: an address the code ASSEMBLES, whose `value` is the TEMPLATE with a hole
            # per runtime value. Carried verbatim — §1b's `expression` — and never
            # evaluated: §6 as amended 2026-09-23 refuses the EVALUATION, not the template,
            # and no hole is ever filled in (§8.2: this repository does not guess deployed
            # values). It is never a `literal`, so a consumer reading literals is
            # unaffected by it existing — and discarding it would make `produced_by`'s
            # whole reason for reading `call_sites` rather than `call_edges` pointless,
            # since reaching the concat site is exactly what that arm was fixed to do.
            template = argument.get("value")
            if not isinstance(template, str):
                return _only(trail, _unresolved(NOT_READABLE))
            return _only(trail, Answer(kind=EXPRESSION, value=template))
        if kind in _DECLARATION_KINDS:
            symbol = argument.get("symbol")
            if symbol is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return _only(trail, Answer(kind=LITERAL, value=str(symbol), literal_kind=SYMBOL))
        if kind == "field":
            symbol = argument.get("symbol")
            if symbol is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return self._resolve((_BINDING, str(symbol)), trail, frames)
        if kind == "parameter":
            index = argument.get("value")
            if index is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return self._resolve((_PARAMETER, method, int(str(index))), trail, frames)
        if kind == "array":
            return self._elements(argument, method, origin, trail, frames)
        if kind == "lambda":
            # It carries a `source` and a body `symbol`, so it would fit both shapes
            # above, and it is left out of both on MEANING (`value_edges.sql`'s
            # `names_declaration` arm, ruled 2026-09-22): it names a body, not a value.
            return _only(trail, _unresolved(NOT_READABLE))
        if kind == "null":
            # The code STATES there is no value (D00 §5's `null` kind, ACONST_NULL). That
            # is an answer and not a miss, so it is `absent` rather than a reason: a
            # consumer told `not_readable` would look for a value that is not there to be
            # found, which is a different and false claim about the code.
            return _only(trail, Answer(kind=ABSENT))
        source = argument.get("source")
        if source is None:
            return _only(trail, _unresolved(NOT_READABLE))
        used_at = origin[2] if origin[0] == _SLOT else None
        return self._through(method, int(str(source)), used_at, trail, frames)

    def _elements(
        self,
        argument: Mapping[str, Any],
        method: str,
        origin: _Position,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """§1c's rule at an array, which is where D00 states it: every index a distinct
        written constant yields ELEMENTS, each its own path; anything else yields one
        `non_enumerable` with no element list at all.

        **An EMPTY list is `absent`, not `non_enumerable`** (ruled 2026-09-23). D00 §5
        draws the line itself — "the empty list is the FACT, and it is the one place in
        this grammar where an empty value says something an absent key would not, because
        'called with no values' is a different statement from 'the array could not be
        read'" — so calling a known-empty call ambiguous would contradict the facts it was
        read from. A MISSING list is the other half of that sentence and stays a reason.
        """
        elements = argument.get("elements")
        if not isinstance(elements, list):
            return _only(trail, _unresolved(NON_ENUMERABLE))
        if not elements:
            return _only(trail, Answer(kind=ABSENT))
        reached: list[_Reached] = []
        for index, element in enumerate(elements):
            answers = self._entry(element, method, origin, trail, frames)
            if any(answer.kind == UNRESOLVED for _, answer in answers):
                return _only(trail, _unresolved(NON_ENUMERABLE))
            step = _Step((_ELEMENT_OF, *origin), f"element {index}")
            for path, answer in answers:
                merged = _combine(path, (step,))
                if merged is not None:
                    reached.append((merged, answer))
        return tuple(reached)

    def _through(
        self, method: str, value: int, used_at: int | None, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """A value id, followed back — unless something got at it first.

        §1d's `escapes`: between the call that produced the value and the call that uses
        it, a call was made ON the value, and nothing in the facts says what it wrote.
        That is the shape `return_flow.py` records as "responses built by mutation" —
        `result.setFilename(x); return result;` — seen from the consuming end.

        **Only a call whose RECEIVER is the value counts, and the narrowing is stated
        because it can be wrong**: a value handed to another method as an ARGUMENT can be
        mutated too, and no fact says whether that callee writes through the reference.
        Counting every hand-off would make the commonest readable shape — a value logged
        and then used — unresolved, so the wider rule needs §3a's measurement behind it
        rather than a guess here.
        """
        if used_at is not None:
            produced = self._index.producers.get((method, value), ())
            produced_at = min(produced) if produced else -1
            for ordinal in self._index.receivers.get((method, value), ()):
                if produced_at < ordinal < used_at:
                    return _only(trail, _unresolved(ESCAPES))
        return self._resolve((_VALUE, method, value), trail, frames)

    def _value(
        self, method: str, value: int, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """Where a value in `method` came from.

        `returned_by` first: the edge names the callee and stops there, as §1a does ("a
        callee symbol; read its returns"), and a callee with two `return` statements is
        two facts — two PATHS, kept as `method_return` keeps them, on the stated ground
        that picking one would be a fact about code that may never run.

        A callee's return is resolved in the CALLEE's frame, with the site the walk
        descended through pushed as that frame: a callee that hands back its own parameter
        is answered by the argument at this site, never by every caller the callee has.
        Doing it the other way is M-1 again, one edge along.
        """
        reached: list[_Reached] = []
        for ordinal, callee in self._index.returns.get((method, value), ()):
            for return_ordinal, entry in self._index.returned_values.get(callee, ()):
                step = _Step((_RETURN_OF, method, value), f"{callee} returns {return_ordinal}")
                merged = _combine(trail, (step,))
                if merged is None:
                    continue
                reached.extend(
                    self._entry(
                        entry,
                        callee,
                        (_RETURN_OF, callee, return_ordinal),
                        merged,
                        frames + ((callee, (method, ordinal)),),
                    )
                )
        if reached:
            return tuple(reached)
        producers = self._index.producers.get((method, value), ())
        if not producers:
            return _only(trail, _unresolved(NOT_READABLE))
        # The producer is a call. Whether its BODY was read is what separates the two
        # reasons, and `call_edges` is the table that says so — it writes a row per site
        # with a NULL callee at the third-party boundary. MEASURED on `mall-admin`: 1,411
        # of 2,065 value-producing sites are that boundary, so `external` is the common
        # answer and not the corner case. Where the body WAS read and still nothing names
        # the value, the producer is there and unreadable — which is also where
        # `identified_by` will answer once §2 hoists it into `value-models/`.
        site = (method, min(producers))
        return _only(trail, _unresolved(NOT_READABLE if site in self._index.reached else EXTERNAL))

    def _parameter(
        self, method: str, index: int, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """A parameter of `method` — the crossing the whole design turns on (§1c).

        Inside a callee the walk descended into, the frame answers: the parameter is the
        argument at the site it came through. Otherwise each `bound_to_parameter` edge is
        a distinct CALLING CONTEXT, and each is its own path — which is what makes two
        callers two bindings rather than a cross product of their values.

        No edge at all is `external`: nothing this workspace scanned binds this parameter,
        so whatever it receives comes from outside what was scanned — a framework calling
        an entry point, or a caller in a dependency nobody read.
        """
        frame = _frame_of(frames, method)
        if frame is not None:
            return self._resolve((_SLOT, frame[0], frame[1], index), trail, frames)
        callers = self._index.callers.get((method, index), ())
        if not callers:
            return _only(trail, _unresolved(EXTERNAL))
        reached: list[_Reached] = []
        for caller, ordinal in callers:
            step = _Step((_CALLER_OF, method), f"{caller}@{ordinal}")
            merged = _combine(trail, (step,))
            if merged is None:
                # This path already crossed out of `method` through a different call, so
                # this caller is not on it. Another slot's path holds that caller.
                continue
            reached.extend(self._resolve((_SLOT, caller, ordinal, index), merged, frames))
        return tuple(reached)

    def _binding(self, trail: _Trail) -> tuple[_Reached, ...]:
        """A value read out of a named mutable location (§5a: a binding, never a field —
        it is a field in one language, a module-level variable in another, a package var
        or a closure cell elsewhere).

        **This is where the sixth edge is missing, and the miss is the answer.**
        `written_by` is specified as a scanner CAPABILITY (§4, D00 9.19) rather than as
        work on any one backend; no backend reports it, so `value_edges` emits no such row
        and there is nothing to follow. `no_writer` is the reason §1d gives for exactly
        this, and it is the only answer a binding read can get until the capability lands.

        **So today it means "no writer edge exists to follow", NOT "this binding is never
        written"** — the constant's own comment says the same, because that is where a
        reader looks the word up. The day capability 9.19 reports binding writes, this
        method follows the edges and the answer narrows to §1d's literal meaning; nothing
        else here changes.

        The constructor-only `field_write` fact is deliberately NOT read here: it is half
        of that edge, and giving it a second home in the walk is how one answer becomes
        two spellings that drift (§0a's disease, D01 §6's no-copied-fact rule).
        """
        return _only(trail, _unresolved(NO_WRITER))


# The callee frames the walk descended through: (method, the site that called it),
# innermost last. A method appears more than once only where the walk descended into it
# twice on one path, and the innermost is the one that answers.
_Frames = tuple[tuple[str, tuple[str, int]], ...]


def _frame_of(frames: _Frames, method: str) -> tuple[str, int] | None:
    for framed, site in reversed(frames):
        if framed == method:
            return site
    return None
