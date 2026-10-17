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
answers themselves live in D00 §5's argument grammar, on `method_returns` and on the call
sites, so the walk reads those too, and `call_edges` for the one question the edges cannot
answer (was a body read at all, which is what separates `external` from `not_readable`).
Five queries, folded into `ValueIndex` once.

**A slot is read off the PROJECTION, and that is load-bearing rather than tidy** (fix
round, 2026-09-23). `effective_call_sites` is the row every engine sees: a compiler-emitted
default-argument bridge call re-targeted to the function it stands for, a class-compiled
lambda argument read as the lambda it is. Reading RAW `call_sites` here was a wrong answer,
not a miss — MEASURED on the canonical bridge shape, a walk asking for the sibling's
parameter 0 was handed the bridge's leading RECEIVER, a type symbol where a string belongs,
in range so nothing caught it; and a DEFAULTED parameter answered with the mask value the
bridge pushed instead of the marker the projection writes.

**The invariant that makes the index correct, since the edge carries a RAW slot number
beside a PROJECTED callee.** `call_edges.callee` and this row's argument list are now read
from the SAME row, so the callee's parameter *p* is that row's slot *p* — for a bridge, the
projection builds exactly the sibling's slot list; for an untouched row, the callee is the
raw target and the slots are its own. The edge's `to_index` is used only to SELECT which
call sites bind parameter *p*, never to index into anything, and a projected row is always
shorter than the raw one it came from (a receiver, the masks and the marker go), so an edge
exists for every real parameter and none is missed. MEASURED on the same shape: parameter 0
answers `"y"` and parameter 1 answers `false` at mask 0, and parameter 1 answers a reason
at mask 2 rather than the value the caller never passed.

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

**It names no framework and no language.** `identified_by` (§2) is catalog data, handed in
by the caller as `identities` and never held here: the walk finds the producing call
(distance) and the table says which of its arguments is the value (meaning), which is §1e's
line drawn exactly where DR-6 puts it. A caller that passes none gets the walk as it was
before Task 7 — a producer whose value nothing names answers with a reason.

**One engine consumes this, and the migrations add the rest** (§3c). Task 4's measurement
was the gate before any engine called it and §7a's shadow read is the gate before each
migration; `resolve/engines/interface_implementation.py` is the first through both (Task 7,
one catalog — the smallest pinned surface, so the cheapest place to discover the walk is
wrong). `resolve/shadow.py` is the other caller and is a RECORDER rather than a consumer:
it runs the walk over every position a catalog asks about, writes what it WOULD resolve
into `value_resolutions`, and publishes nothing.

**A caller resolving many sites builds `value_index` ONCE and threads it** — the condition
attached to Task 4's no-cap ruling (`docs/research/2026-09-23-value-walk-measurement.md`
§6.2). `resolve_site` rebuilds the whole five-query fold whenever it is handed none, which
costs 0.16 s on `mall-admin` — more than walking every position in that corpus put
together — so an engine resolving its 52 asked sites without one would pay about 8 s for
work that takes under a millisecond.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_calls import effective_call_sites

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

# §2's `identified_by` table, as the walk is handed it: `{owner?, method, arg, arity?,
# descriptor?, role?}` per producing call, built once by the loader (`yaml_source
# .value_model`) from `value-models/` plus every hop declaration still written on a
# catalog. It is DATA the caller passes in, never knowledge this module holds — the rule
# the module docstring states, and the reason the parameter exists at all.
Identities = Sequence[Mapping[str, Any]]

# The key a hoisted WRAPPER entry carries and a `_via` entry deliberately does not, and
# what it decides here. `role` says "argument N of this producer is the CHANNEL" or "the
# PAYLOAD" — a statement about one of several things a constructed value holds, which the
# consuming row is what selects. A role-free entry says something else and stronger: this
# argument IS the value the call stands for, which is the only claim a walk resolving "what
# is this value" can act on. `new ProducerRecord(topic, …, payload)` carries TWO roled
# entries, and a walk that read them would answer one value twice; `ProjectSubscriptionName
# .of(project, id)` carries one role-free entry, and argument 1 is what that object is.
_ROLE = "role"

# The PLURAL identity spelling: `arg: all_strings` says the producer's result IS the
# collection of its own arguments, so one producer answers with SEVERAL values. That is a
# statement of the same KIND as a role-free `arg: int` — "this argument IS the value the
# call stands for" — only not singular, which is why it reads here and not as a sixth edge
# kind: §1c's multiplicity is already paths, and `_all_arguments` resolves it into them.
#
# **Spelled in six places** (here, `shadow.py:190`, `shapes/arguments.py`, and the three
# engines' validators), which is §0a's two-spellings disease and is logged as such rather
# than deduplicated in passing — the engines' literals are theirs until their migration
# reaches them, and a cleanup that touches five modules is not this fix (§3).
_ALL_STRINGS = "all_strings"

# The marker `MethodFlow.concatTemplate` writes for a runtime operand it could not fold —
# one per `\u0001` in the bootstrap's recipe. Spelled once here because `_joined` both
# COUNTS them (to check the template against the operand list) and SPLITS on them.
_HOLE = "{}"


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

    # Every call site AS THE ENGINES SEE IT, by (method, ordinal) — the site's identity
    # everywhere in D01, and `effective_call_sites` keeps both columns.
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


# The index, built once per RESOLVE instead of once per catalog that asks for it.
#
# **This is a correctness enabler as much as a saving.** `fluent.run` built its own index
# only where the catalog declared a `channel_via`/`url_via`, because building it per
# catalog was measured as real: removing that gate cost **+1.3s on `mall-admin`** (6.22s
# -> 7.50s end to end, resolve 4.65s -> 6.05s). But the gate also kept the walk away from
# catalogs that need it for an ASSEMBLED address, which is not a hop and declares no key.
# Sharing one index makes the gate unnecessary rather than merely cheaper: `mall-admin`
# built the same index FIVE times before this.
#
# **A WeakKeyDictionary, not `id(workspace)`** — and the difference is a defect this
# cache shipped with for one gate run. Keyed on `id()`, the argument for safety was "the
# pipeline clears it before anything can ask", which is true of a pipeline run and FALSE
# of every test that calls an engine directly: a workspace was freed, a new one landed at
# the same address, and the previous test's index answered for it. Two tests in other
# files failed while passing in isolation, which is how it was found.
#
# A weak key cannot do that. The entry disappears with the workspace it belongs to, so a
# new object at the same address is simply a different key, and no clearing discipline has
# to be remembered by anybody.
_INDEX_BY_WORKSPACE: "WeakKeyDictionary[Workspace, ValueIndex]" = WeakKeyDictionary()


def reset_value_index() -> None:
    """Drops every cached index, so a resolve never answers from facts a previous one
    loaded.

    The weak keys above make this unnecessary for CORRECTNESS across objects — an entry
    dies with its workspace — but a single workspace REUSED for two resolves, with facts
    reloaded in between, is the same object and would keep the first resolve's index.
    `pipeline.resolve` calls this before `load_facts` for that case.
    """
    _INDEX_BY_WORKSPACE.clear()


def cached_value_index(workspace: Workspace) -> "ValueIndex":
    """`value_index`, built at most once per workspace per resolve.

    Every engine that resolves values should ask for this rather than `value_index`
    directly: the fold is the same, and three engines times N catalogs each paid for it
    separately before.
    """
    index = _INDEX_BY_WORKSPACE.get(workspace)
    if index is None:
        index = value_index(workspace)
        _INDEX_BY_WORKSPACE[workspace] = index
    return index


def value_index(workspace: Workspace) -> ValueIndex:
    """The index for one resolve. Built by `resolve_site` when it is not handed one."""
    sites: dict[tuple[str, int], Mapping[str, Any]] = {}
    receivers: dict[tuple[str, int], list[int]] = {}
    # The PROJECTION, not the raw fact stream — the rows every engine reads (spec
    # 2026-09-19 §3), and the same rows `call_edges` derived every `bound_to_parameter`
    # edge's callee from. Reading the raw list beside a projected callee answered the
    # bridge's receiver for the sibling's parameter 0; the module docstring has the
    # measurement and the invariant.
    for row in effective_call_sites(workspace):
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
    workspace: Workspace,
    site: Mapping[str, Any],
    index: ValueIndex | None = None,
    identities: "Identities" = (),
) -> list[Binding]:
    """Every slot of one call site, resolved per path (§1b).

    `site` NAMES the site — its `caller` and `ordinal` — and the walk resolves the
    PROJECTED row for that pair, whichever row was handed in. That is unconditional on
    purpose (fix round 2, 2026-09-23): this function is the front door, and requiring
    callers to project first would put the Critical back one level out, where a caller
    that hands a raw `call_sites` row for a compiler-emitted bridge call is answered with
    the bridge's receiver, its mask and its marker as though they were the callee's
    arguments. A rule every future caller has to remember is a cause left in place; this
    removes it. A row for a site the workspace does not hold — a caller's own synthesis —
    is resolved as handed in, since there is nothing to project it against.

    `index` is the fold above, which a caller resolving many sites builds once.

    `identities` is §2's `identified_by` table — the MEANING half the walk cannot hold
    (`Identities` below says what it is and what the walk does with it). Empty is the
    walk as it was before Task 7: a producer nothing names answers with a reason.

    Returns one `Binding` per coherent path, in a deterministic order (NFR-1): the first
    slot's paths drive the outer order, and each slot's answers arrive in the edge query's
    own ordering. An empty list means no path answers every slot at once, which is the
    M-1 ruling taken to its end — the combination a per-position walk would have invented
    is not a row here.
    """
    fold = index if index is not None else value_index(workspace)
    walk = _Walk(fold, identities)
    site = fold.sites.get((str(site["caller"]), int(str(site["ordinal"]))), site)
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


def _used_at(origin: _Position) -> int | None:
    """WHERE a value is used, which is what bounds the `escapes` window.

    A slot of a call site is a position in control flow (`ordinal`). A method's RETURN is
    not: `method_returns.ordinal` numbers the return instructions, not the call sites, so
    nothing there says which calls in that method ran before the `return`. `None` is that
    answer, and `_through` reads it as the whole tail of the method (T-6)."""
    return origin[2] if origin[0] == _SLOT else None


class _Walk:
    """One resolve's walk. Not reused across sites: the memo is keyed on (position, path)
    and both are meaningful only within the resolve that built them."""

    def __init__(self, index: ValueIndex, identities: Identities = ()) -> None:
        self._index = index
        self._identities = tuple(identities)
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
            # A slot this site does not have, and **this is the guard that holds the
            # projection boundary** — so what reaches it is worth stating exactly. The
            # back-crossing DOES arrive here: a `bound_to_parameter` edge carries a raw
            # slot index, so at a bridge site there is an edge for the receiver shift, for
            # each mask and for the marker — indices past the projected row's arity. They
            # are unreachable only because nothing ASKS for them: an index comes from the
            # callee's own `{kind: parameter, value: N}` facts, and a method never names a
            # parameter past its own arity. If a future edge ever carries an index from
            # anywhere else, this refusal is what keeps it from reading a neighbouring
            # slot — which is the Critical, and the reason the branch is a refusal rather
            # than an exception a consumer cannot act on.
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
            # per runtime value.
            #
            # **Joined where every hole's operand is a literal the SOURCE states, and
            # carried verbatim otherwise** — ruling 1, granted by the user 2026-10-17 in
            # these words: *"join them when every single piece is a fixed string typed
            # into the source code. If any piece comes from a config file, a method
            # parameter, or anything that changes at runtime — don't join, behave exactly
            # as today."* That amends §6, which forbade evaluating a concatenation at all;
            # the default is unchanged and the exception is exactly the sentence above.
            #
            # Nothing is reverse-engineered. javac emits one `invokedynamic` plus a recipe
            # of literal text, `MethodFlow.concatTemplate` already turns that into this
            # template — already SUBSTITUTING the bootstrap's own constants, because
            # "that constant IS known" — and the operands are the concat site's own
            # arguments, reached exactly as `domain/facts.py` says: "What FILLS the hole is
            # the concat site's own call-site fact, reached by `source` -> `result`."
            #
            # §8.2 is untouched: a `${...}` operand answers `expression`, not `literal`, so
            # it fails the all-literals test by construction and no deployment hole is ever
            # filled in.
            template = argument.get("value")
            if not isinstance(template, str):
                return _only(trail, _unresolved(NOT_READABLE))
            joined = self._joined(template, argument, method, origin, trail, frames)
            if joined is not None:
                return joined
            return _only(trail, Answer(kind=EXPRESSION, value=template))
        if kind in _DECLARATION_KINDS:
            # **An identified CONSTRUCTION is answered before the type symbol, and the
            # order is the whole of the fix** (review round 1, 2026-09-23). An `instance`
            # entry carries both a `symbol` (the concrete type a `NEW` built) and a
            # `source` (the constructed value). Answering the symbol first meant a
            # constructed value never reached `_value`, where the identity arm lives — so
            # **no entry naming an initialiser could ever fire**: a value BUILT from an
            # address answered with the symbol of the type it was built from, while the same
            # address handed to that type's static factory answered with the address.
            # ELEVEN of the twenty-five shipped entries name an initialiser and FOUR of
            # those are reachable here at all — the other seven carry a `role` or a
            # rule-valued `arg`, which `_identified` passes over for its own reasons.
            #
            # **Why this does not break what T-3's symbol answer is for.** That ruling
            # exists so a consumer is never handed a symbol dressed as a string, and that
            # is untouched: an identity answer is a real value and a consumer testing
            # `literal_kind` reads it the same way either way. What the two statements
            # differ in is strength. "The concrete type a value was built from" is true of
            # EVERY constructed value and is a fallback; an `identified_by` entry is a
            # measured claim about ONE producer, carrying the probe row §7b requires. Where
            # both are available the measured one answers; where no entry matches — which
            # is every constructed type in this estate but TWO (`URI`'s one-string
            # constructor, 8 values, and `Queue`'s, 2 — the other two reachable entries
            # match no construction anywhere; four is the count of reachable ENTRIES, which
            # is not a count of types) — the symbol answer stands
            # unchanged, byte for byte. A `class` or an `enum` reference has no
            # construction to find at all and is never affected.
            #
            # The consumers that want the TYPE out of such a slot — a handler's
            # implementing class, a payload's declared type — read types nobody has
            # declared an identity for, and a roled entry (`HttpEntity#<init>`,
            # `ProducerRecord#<init>`) is passed over by `_identified` in any case.
            built = self._identified_construction(argument, method)
            if built is not None:
                return self._through(method, built, _used_at(origin), trail, frames)
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
            # The code STATES there is no value (D00 §5's `null` kind). That is an answer
            # and not a miss, so it is `absent` rather than a reason: a consumer told
            # `not_readable` would look for a value that is not there to be found, which is
            # a different and false claim about the code.
            return _only(trail, Answer(kind=ABSENT))
        source = argument.get("source")
        if source is None:
            return _only(trail, _unresolved(NOT_READABLE))
        return self._through(method, int(str(source)), _used_at(origin), trail, frames)

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
        return self._enumerated(
            [
                (index, self._entry(element, method, origin, trail, frames))
                for index, element in enumerate(elements)
            ],
            origin,
            trail,
            "element",
        )

    def _enumerated(
        self,
        members: list[tuple[int, tuple[_Reached, ...]]],
        origin: _Position,
        trail: _Trail,
        label: str,
    ) -> tuple[_Reached, ...]:
        """§1c's enumeration over an aggregate whose MEMBERSHIP is known, shared by the two
        that have it — an array the scanner read, and a producing call's argument list.

        **One `_ELEMENT_OF` step per member**, so several answers are several PATHS and the
        memo cannot collapse them (§1c, ruling M-1).

        **A member the walk cannot name costs ONE trailing unresolved, not the whole
        aggregate** (ruled 2026-10-16). The line `non_enumerable` draws is about MEMBERSHIP,
        not readability: where the scanner could not read an array's construction at all it
        reports no `elements` and the caller above answers `non_enumerable`, and a
        loop-built or branch-merged value never arrives as an aggregate in the first place —
        the facts carry no "this was a loop" claim, so it is an unread argument and answers
        `not_readable`. What reaches here is a known membership with a member that has no
        name, and discarding its readable siblings would exclude destinations on inference,
        which §8 forbids ("exclude only on proof") in the direction it says is hardest to
        notice: an omission leaves no wrong row and a reader cannot tell it was ever there.

        This is also what the consuming engines already do, so it makes the migration SAFER
        rather than riskier: `shapes/arguments.channels_of` reads an array through
        `_all_string_channels`, whose own contract is "one tuple per readable element, plus
        one trailing unresolved tuple where any element could not be read, never one per
        failure". The walk now says the same thing in the same cases.

        The trailing answer carries the FIRST failing member's own reason in member order —
        `no_writer` for a binding no writer edge reaches, `external` for an unscanned
        producer — because `value_resolutions` has a reason column and "one more member,
        and here is why it has no name" is the §8.1 rule 3 escape a reader can act on.
        Taking the first in order keeps the answer stable rather than dependent on which
        member the walk finished last.
        """
        reached: list[_Reached] = []
        unread: str | None = None
        for index, answers in members:
            step = _Step((_ELEMENT_OF, *origin), f"{label} {index}")
            for path, answer in answers:
                if answer.kind == UNRESOLVED:
                    unread = unread or answer.reason or NOT_READABLE
                    continue
                merged = _combine(path, (step,))
                if merged is not None:
                    reached.append((merged, answer))
        if unread is not None:
            trailing = _Step((_ELEMENT_OF, *origin), f"unread {label}")
            merged = _combine(trail, (trailing,))
            reached.append((merged if merged is not None else trail, _unresolved(unread)))
        return tuple(reached)

    def _joined(
        self,
        template: str,
        argument: Mapping[str, Any],
        method: str,
        origin: _Position,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...] | None:
        """The template with every hole filled from a source literal, or None to leave the
        caller carrying it verbatim.

        **Every refusal below returns None rather than an `unresolved`**, and that is the
        shape of ruling 1: not joining is not a failure, it is the behaviour §6 already
        had, so a template this cannot fill reads exactly as it did before.

        The refusals, each because the alternative is a string nobody wrote:

        * **no producing site for `source`** — the concat's own arguments are where the
          operands live, and without that site there is nothing to fill from;
        * **a hole count that disagrees with the operand count** — the template's `{}`
          come from the recipe's `\u0001` markers, one per runtime argument, so a
          mismatch means one of the two was misread and guessing an alignment would
          publish operands in the wrong places;
        * **an operand that is not exactly one answer** — several enumerable answers are
          several possible addresses, and one row per combination is ruling 1's
          multiplicity rule applied across operands. That product is deliberately NOT
          built here: it needs a path-merge across operands that disagree, nothing in the
          27 measured corpora reaches it, and carrying the template under-reports rather
          than inventing. Recorded rather than silently narrowed;
        * **an operand that is not a `string` literal** — a parameter, a `${...}`
          expression, a symbol, an `absent`, an `unresolved`. The ruling's own boundary;
        * **operand paths that do not cohere** — `_combine`'s rule, unchanged: two
          operands that crossed the same context differently did not happen together.
        """
        source = argument.get("source")
        if source is None:
            return None
        producers = self._index.producers.get((method, int(str(source))), ())
        if not producers:
            return None
        site = self._index.sites.get((method, min(producers)))
        if site is None:
            return None
        operands = site["arguments"] or []
        pieces = template.split(_HOLE)
        if len(pieces) != len(operands) + 1:
            return None

        path = trail
        values: list[str] = []
        for operand in operands:
            reached = self._entry(operand, method, origin, trail, frames)
            if len(reached) != 1:
                return None
            (reached_path, answer) = reached[0]
            if answer.kind != LITERAL or answer.literal_kind != STRING:
                return None
            merged = _combine(path, reached_path)
            if merged is None:
                return None
            path = merged
            values.append(str(answer.value))

        filled = pieces[0] + "".join(
            value + piece for value, piece in zip(values, pieces[1:], strict=True)
        )
        return _only(path, Answer(kind=LITERAL, value=filled, literal_kind=STRING))

    def _through(
        self, method: str, value: int, used_at: int | None, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """A value id, followed back — unless something got at it first.

        §1d's `escapes`: between the call that produced the value and the call that uses
        it, a call was made ON the value, and nothing in the facts says what it wrote.
        That is the shape `return_flow.py` records as "responses built by mutation" —
        `result.setFilename(x); return result;` — seen from the consuming end.

        **`used_at` may be unknown, and then the whole tail of the method counts** (fix
        round, 2026-09-23). A value reached through a callee's RETURN has no comparable use
        point — `method_returns.ordinal` numbers return instructions, not call sites — so
        nothing says which calls ran before the `return`. Skipping the check there answered
        the pre-mutation literal for exactly the shape the paragraph above names, one
        method along: `result.setFilename(x); return result;` read from the caller. So the
        class is refused instead — ANY call on the value after its producer — because
        answering a value that may have been mutated after the point it was read is the
        same defect as reading the wrong slot, and a miss is the acceptable half.

        **Only a call whose RECEIVER is the value counts, and the narrowing is stated
        because it can be wrong**: a value handed to another method as an ARGUMENT can be
        mutated too, and no fact says whether that callee writes through the reference.
        Counting every hand-off would make the commonest readable shape — a value logged
        and then used — unresolved, so the wider rule needs §3a's measurement behind it
        rather than a guess here.

        **A CONSTRUCTOR is a producer, not a mutation** (review round 1). `produced_by` is
        read off `call_sites.result` and an `<init>` has none — D00 §5's "result is null
        for a void one" — so a constructed value has no producer ordinal at all here, and
        the window used to open before its own construction. Every `new Thing(x)` whose
        value is then used therefore answered `escapes` on the constructor itself. The
        construction is where the window opens, and `_construction` is what finds it.
        """
        produced = self._index.producers.get((method, value), ())
        constructed = self._construction(method, value)
        produced_at = min(produced) if produced else (-1 if constructed is None else constructed)
        for ordinal in self._index.receivers.get((method, value), ()):
            if ordinal > produced_at and (used_at is None or ordinal < used_at):
                return _only(trail, _unresolved(ESCAPES))
        return self._resolve((_VALUE, method, value), trail, frames)

    def _construction(self, method: str, value: int) -> int | None:
        """The ordinal of the call that CONSTRUCTED `value` in `method`, or None where
        nothing in this method did.

        The facts say it without this module naming a language's constructor spelling, and
        **it is an APPROXIMATION of one — stated as such, because it over-accepts and the
        size of that is measured** (review round 2). Three conjuncts:

        * **no `produced_by` edge.** A value a call handed back is that edge's business, and
          its earliest receiver-site is an ordinary call ON it (`x = foo(); x.bar()`).
          MEASURED: dropping this conjunct changes **0 of 98,454** ceiling positions across
          all 27 corpora, so it is a boundary against `produced_by` rather than something
          this estate exercises.
        * **the site is the EARLIEST the value is the receiver of.** Nothing can be invoked
          on a value before it exists, so if it was constructed here that call is first. A
          later one is a call on an already-built value and says nothing about what it is.
        * **that site produced no value of its own** — D00 §5's "result is null for a void
          one", which is why `produced_by` carries no edge for a construction and why
          `_linked_constructor` has always joined an initialiser on `receiver` instead.

        **What the third conjunct excludes is a call that HANDS SOMETHING BACK, and that is
        narrower than "is an initialiser".** It is what stops a fabrication, found by
        measuring rather than by reading: without it,
        `session.createProducer(session.createQueue("raw-audit"))` — where `session` is a
        FIELD, so it has no producer edge either — made `createQueue` the "construction" of
        the SESSION, and the identity entry for `Session.createQueue` answered `raw-audit`
        as what the session is. A queue name published as the identity of a connection: a
        wrong answer at `resolved`, which is §7's one failure. `createQueue` hands back a
        `Queue`, so it is excluded.

        **A VOID ORDINARY METHOD is not excluded, and that is an open gap** (`OI-133`). A
        field- or parameter-held value whose first call happens to return nothing —
        a logger call, a cache clear, a repository delete, a void setter — is read here as a
        construction. MEASURED over all 27 corpora: of **3,283** values this rule names,
        **395 are not initialisers** (`clear` 159, `debug` 65, `info` 22, `remove`, `error`,
        `warn`, `delete`, `persist`, `save`, `convertAndSend`...). Nothing acts on them TODAY
        and the whole of why is the catalog side: every shipped non-initialiser identity
        entry has a non-null result at every site it matches in every corpus, and the one
        entry naming a setter matches no site at all. MEASURED both ways — answering only an
        initialiser here changes **0 of 98,454** ceiling positions, so neither an identity
        answer nor the `escapes` window below moves for any of the 395. The day a
        `channel_via` is hoisted onto a void sender or setter, it does: `OI-133` carries the
        demonstration and the measurement that closes it.
        """
        if self._index.producers.get((method, value)):
            return None
        ordinals = self._index.receivers.get((method, value), ())
        if not ordinals:
            return None
        site = self._index.sites.get((method, min(ordinals)))
        return None if site is None or site.get("result") is not None else min(ordinals)

    def _identified_construction(self, argument: Mapping[str, Any], method: str) -> int | None:
        """The VALUE ID where this argument is one built here by a producer the identity
        table names, and None otherwise.

        The value id and not the construction's ordinal, because that is all the caller
        needs: it hands the id to `_through`, which finds the construction again for the
        `escapes` window it has to compute anyway. None is the common answer and the one
        that keeps `_entry`'s declaration branch exactly as it was: no `source`, no
        construction, or no entry claiming it."""
        source = argument.get("source")
        if source is None:
            return None
        value = int(str(source))
        constructed = self._construction(method, value)
        if constructed is None or self._identified((method, constructed)) is None:
            return None
        return value

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
            # No call handed this value back. A CONSTRUCTION is still a producer — one the
            # `produced_by` edge cannot carry, because `call_sites.result` is null for an
            # initialiser — so an identity entry naming it answers here (review round 1,
            # and `_construction` says how the site is found). Where nothing identifies the
            # construction the answer is exactly what it was before: this branch exists to
            # reach a MEASURED claim about one producer, not to give constructed values a
            # second reading of their own.
            constructed = self._construction(method, value)
            slot = None if constructed is None else self._identified((method, constructed))
            if constructed is None or slot is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return self._resolve((_SLOT, method, constructed, slot), trail, frames)
        site = (method, min(producers))
        # **The producer is a call, and this is where the walk used to be stuck** (§0b,
        # and it is the correction that design says it made three times before it stuck).
        # A backward walk reaching `session.createQueue("raw-audit")` has a `Queue` object
        # and nothing in the facts says what string identifies one; only framework
        # knowledge does. So `identified_by` answers here, and the answer is the producer's
        # OWN slot, resolved by the same walk — which is what keeps §1e's line where it is:
        # the walk found the producing call (distance), the table said which argument of it
        # is the value (meaning), and no framework is named in this module either way.
        slot = self._identified(site)
        if slot is not None:
            return self._resolve((_SLOT, site[0], site[1], slot), trail, frames)
        # **The PLURAL identity, and the reason it belongs beside the singular one rather
        # than in a reader of its own.** `consumer.subscribe(List.of("t1", "t2"))` reaches
        # here exactly as `createQueue` does — a producing call whose body is a JDK method
        # the scan never read — and answered `external` until this arm existed. That answer
        # was wrong on its own terms: `external` means "a producer outside what was scanned"
        # (§3a), true of `List.of`'s BODY, but the value does not come from the body. It
        # comes from arguments sitting in the facts at the call site, and claiming we could
        # not see them when we can is the one thing §8's anti-fabrication rule forbids in
        # the negative direction (§8's "exclude only on proof": a miss asserted, not read).
        if self._identified_rule(site) == _ALL_STRINGS:
            return self._all_arguments(site, trail, frames)
        # Nothing identifies it. Whether its BODY was read is what separates the two
        # reasons, and `call_edges` is the table that says so — it writes a row per site
        # with a NULL callee at the third-party boundary. MEASURED on `mall-admin`: 1,411
        # of 2,065 value-producing sites are that boundary, so `external` is the common
        # answer and not the corner case.
        return _only(trail, _unresolved(NOT_READABLE if site in self._index.reached else EXTERNAL))

    def _all_arguments(
        self, site: tuple[str, int], trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """`all_strings` at a producing call: EVERY one of its arguments, each its own path.

        **The two spellings of one topic list answer alike, through machinery that already
        exists.** `List.of("t1", "t2")` binds the FIXED-ARITY `of(Object, Object)` overload,
        so its strings arrive as two positional arguments; `Subscriptions.topics("a", "b")`
        and `Arrays.asList("a", "b")` are genuine varargs and arrive as ONE `array`
        argument. Resolving every slot covers the first directly, and for the second hands
        the single array slot to `_elements`, which has expanded an array into its elements
        since D00. So no expander is written here, and nothing in this module learns what a
        varargs call is.

        **Multiplicity and the half-read rule are `_enumerated`'s**, stated there once for
        both aggregates that have known membership rather than twice here (§0a's disease).
        A producing call's argument list is the clearer of the two: fixed, positional and
        complete at the call site, so `List.of("orders.placed", field)` is a COMPLETE list
        of two with one unnameable member, and `orders.placed` survives.

        An EMPTY argument list is `absent`, the same statement `_elements` makes for an
        empty array and for the same reason: "called with no values" is a fact the facts
        record, and calling it ambiguous would contradict them. This one DOES still diverge
        from the engines' reader, which never returns zero rows and answers one unresolved
        tuple instead; `absent` is a resolved answer in this walk's vocabulary and stays
        distinguishable, which is the ruling of 2026-09-23.
        """
        row = self._index.sites.get(site)
        arguments = (row["arguments"] or []) if row is not None else []
        if not arguments:
            return _only(trail, Answer(kind=ABSENT))
        return self._enumerated(
            [
                (index, self._resolve((_SLOT, site[0], site[1], index), trail, frames))
                for index in range(len(arguments))
            ],
            (_SLOT, site[0], site[1]),
            trail,
            "argument",
        )

    def _identity_matches(self, site: tuple[str, int]) -> tuple[Mapping[str, Any], ...]:
        """Every identity entry that claims `site`'s result, in the table's own order.

        **ONE matching predicate, read by both readers below**, because the alternative is
        a second copy of it that answers the day the first one changes — §0a's disease, and
        the same no-copied-fact rule this module's closing comment states.

        Matched on what the engines already match a call on — the method name, the `owner`
        where the entry declares one, and the `arity` or JVM `descriptor` where it declares
        either. **`owner` is OPTIONAL and its absence matches every owner** (§5a): Go's
        `nats.Connect(url)` and Python's `boto3.client("sqs")` are free functions, and
        requiring one would bake OO into a model the fact grammar does not have.

        A ROLED entry is passed over, and that is not an oversight: the reason is `_ROLE`'s.

        Order is the table's — `value-models/` first, then the catalogs
        (`yaml_source.value_model`), which is stated there to be a reading convenience
        rather than a safety property because `arity` and `descriptor` are part of what an
        entry matches on, so a discriminated entry and a bare one coexist and a site the
        first turns away still meets the second. **Every match is returned rather than the
        first**, so each reader can take the first entry in a form IT can resolve and leave
        the others standing — which is what keeps that coexistence working now that two
        `arg` forms are read: a site carrying an `all_strings` entry and an `arg: int` one
        answers from whichever the asking reader understands, exactly as it did when the
        single reader skipped the form it could not use.
        """
        row = self._index.sites.get(site)
        if row is None:
            return ()
        arguments = row["arguments"] or []
        matched: list[Mapping[str, Any]] = []
        for entry in self._identities:
            owner, arity = entry.get("owner"), entry.get("arity")
            descriptor = entry.get("descriptor")
            if entry.get(_ROLE) is not None:
                continue
            if entry.get("method") != row["name"]:
                continue
            if owner is not None and row["owner"] != owner:
                continue
            if arity is not None and len(arguments) != arity:
                continue
            if descriptor is not None and row.get("descriptor") != descriptor:
                continue
            matched.append(entry)
        return tuple(matched)

    def _identified(self, site: tuple[str, int]) -> int | None:
        """Which SINGLE one of the producing call's own arguments IS the value it handed
        back, or None where no matching entry names one (§2, `Identities` above).

        A non-integer `arg` is a RULE, and the two that exist are not alike:

        * `all_strings` names SEVERAL of the producer's arguments, and `_all_arguments`
          resolves it — §1c's multiplicity is paths, so several is a shape this walk has.
          A slot is what THIS reader returns, which is why the plural form answers there
          and not here.
        * `last` picks one argument by COUNTING the overload that was called. It is
          `record_wrappers`' descriptor discrimination, no walk arm reads it, and the
          engines read that spelling as they always have.
        """
        for entry in self._identity_matches(site):
            slot = entry.get("arg")
            if isinstance(slot, int):
                return slot
        return None

    def _identified_rule(self, site: tuple[str, int]) -> str | None:
        """The RULE a matching entry names in place of a slot, or None — the plural half of
        `_identified`'s contract, kept apart from it because the two answer different
        questions and a caller wanting one must not silently get the other."""
        for entry in self._identity_matches(site):
            rule = entry.get("arg")
            if isinstance(rule, str):
                return rule
        return None

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
