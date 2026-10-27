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

**The sixth edge, `written_by`, is a binding's writer** (spec 2026-10-18, D00 §5's
`field_write`). `value_edges` carries a write from a PARAMETER; a write from a constant or a
call's result carries its value in the fact itself and is read straight off `field_writes`
(`ValueIndex.constants` and `.produced`), because there is no parameter for an edge to land
on. `_binding` is the one place that follows any of them, and a binding with no reported write
ends at `no_writer` — `NO_WRITER` below says what that does and does not mean.

**It names no framework and no language.** `identified_by` (§2) is catalog data, handed in
by the caller as `identities` and never held here: the walk finds the producing call
(distance) and the table says which of its arguments is the value (meaning), which is §1e's
line drawn exactly where DR-6 puts it. A caller that passes none gets the walk as it was
before Task 7 — a producer whose value nothing names answers with a reason.

**A second reader shares the walk, and answers the CALL instead** (2026-10-26).
`producers_of` runs the same `_Walk` with one more stop — a producing call the caller declares
— and names that call, because a block argument is not a value and the reader that needs one
reads it off the call itself. The value walk declares nothing, so its answers are unchanged.

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
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from itertools import product
from typing import Any
from weakref import WeakKeyDictionary

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.domain.symbols import with_descriptor

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
# in this module writes", and the facts now report a write from a parameter, a constant or a
# call's result (`_binding` has the history). A write of any other shape — a value built with
# `new`, one parked in a local first, a container's reflective injection — is still not
# reported, so the answer is *no reported write was found to follow* — NOT *this binding is
# never written*. A reader acting on it is reading the fact's reach, not a property of the code.
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
# **Not one of §1b's answer kinds, and it never leaves this module.** The producer reader
# (`producers_of`) runs the same walk with one more stop, and a path that ends at a declared
# call carries that call here as its `value` (a `Producer`) until the reader turns the path
# into its record. The value walk declares nothing, so it never mints one.
_PRODUCED = "produced"

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

# An `identified_by` entry saying its call's result stands for whatever its RECEIVER stands
# for, rather than for one of its own arguments (`OI-142`). The third form, beside an `arg`
# index and the `all_strings` rule.
_FROM_RECEIVER = "from_receiver"

# The marker `MethodFlow.concatTemplate` writes for a runtime operand it could not fold —
# one per `\u0001` in the bootstrap's recipe. Spelled once here because `_joined` both
# COUNTS them (to check the template against the operand list) and SPLITS on them.
_HOLE = "{}"


# WHAT KIND OF THING an identity yields, and why a closed pair rather than a flag.
#
# A URL has parts: `http://customers-service/owners` is a SCHEME, an AUTHORITY (who you
# are calling) and a PATH (what you are asking for). Almost every identity in the table
# yields a whole address — `URI.create("https://…/x")` — and the consumer splits it with
# CP-2's rule. A service-discovery lookup yields only the AUTHORITY: the chain
# `getInstances("customers-service").get(0).getUri()` resolves to `customers-service`,
# which is who, with no scheme and no what.
#
# **Nothing about the STRING says which it is, which is why this is a declared property
# and not a test.** `customers-service` and `/api/v1` both lack a scheme; the first is a
# service and the second is a path prefix, and reading either as the other publishes a
# wrong column at `resolved`. What tells them apart is where the value came from, so the
# entry says it (`OI-142`, ruling 2 — "peer and path from separate evidence").
_YIELDS = "yields"
_ADDRESS = "address"
_AUTHORITY = "authority"
_YIELDS_KINDS = (_ADDRESS, _AUTHORITY)


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
    # `address` (the default, and what every value the code states is) or `authority` — WHO
    # is being called, with no scheme and no path. Set only by an identity entry declaring
    # `yields: authority`, and carried through every hop after it, because a value that
    # stands for a service still stands for one after an accessor hands it on. A consumer
    # reads it to decide which COLUMN the value belongs in; see `_joined`.
    yields: str = _ADDRESS
    # **"Derived from this value; its exact rendering was not read"** (spec 2026-10-21
    # merged values, §3b). Set only by `_merged`, when a merge's candidates share a root —
    # `x` beside a call ON `x` — and the walk answers `x` without knowing what the call did
    # to it. Carried through every hop after, like `yields`; `url_of_answer` publishes an
    # inexact address at `partial`, `channel_of_answer` refuses one, and `_joined` makes a
    # template filled from one an `expression`. Never set on an exact answer.
    inexact: bool = False


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
class Producer:
    """Where one path of the producer reader ENDED (`producers_of`).

    `caller` and `ordinal` name the call site, which is a site's identity everywhere in D01,
    and `identity` is the declared `(owner, method)` it matched. A path that ends anywhere
    else leaves all three None and says where in exactly one of the other two:

    * `reason` — one of §1d's reasons and nothing else (`external`, `no_writer`, …), where
      the path ends unresolved;
    * `ended_at` — the `Answer` itself, where the path ends at a value the code states
      (`literal`, `expression`, `absent`): not a call anyone built, and kept whole so a
      literal end still carries its literal.
    """

    caller: str | None = None
    ordinal: int | None = None
    identity: tuple[str, str] | None = None
    reason: str | None = None
    ended_at: Answer | None = None


@dataclass(frozen=True)
class ValueIndex:
    """The six reads the walk needs, folded once (GUIDELINES §8.7: cost is a design
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
    #
    # It carries one more kind of binding than the fact of that name: a lambda's CAPTURE,
    # which binds a synthetic body's leading parameters to the arguments of the site that
    # captured them (`value_index`, and `OI-150` for what it cost to be missing). The walk
    # treats the two identically because they ARE identical to it — a parameter, and the
    # sites that hand it a value — and a capture is one calling context like any other.
    callers: dict[tuple[str, int], tuple[tuple[str, int], ...]]
    # Every method's declared PARAMETER NAMES, by symbol — what a hole in a template is
    # named after (`_joined`). The compiler records them (`local_variable_names`), the
    # signature carries them, and a position with no recorded name is `None` rather than a
    # guess: a jar compiled without them is a real case and an invented `arg0` would read as
    # a name the author wrote.
    parameters: dict[str, tuple[str | None, ...]]
    # `field_writes.value`: a binding -> every CONSTANT written into it, as argument-grammar
    # entries (`OI-138` cause 2). Separate from `writers` below because there is no crossing
    # to make: the value is in the fact, and `_binding` answers with it rather than
    # resolving a parameter in another method's frame.
    constants: dict[str, tuple[Mapping[str, Any], ...]]
    # `field_writes.value` again, for a write whose value is a CALL'S RESULT (CP-33 rows 6-7,
    # 2026-10-26): a binding -> (the writing method, the entry), because the entry's `source`
    # is a value id in THAT method's frame and means nothing anywhere else. `_binding`
    # resolves it there, as it would the same entry at a call site in that method.
    produced: dict[str, tuple[tuple[str, Mapping[str, Any]], ...]]
    # `written_by`: a binding -> the method that wrote it and the PARAMETER it wrote from,
    # one entry per writer. Several entries is several possible values, which §4 of spec
    # 2026-10-18 rules is the exact answer where every writer is in this module rather than
    # an ambiguity to hedge. Keyed on the binding symbol alone, which is what a `field`
    # argument carries and all the walk has to ask with.
    writers: dict[str, tuple[tuple[str, int], ...]]
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
    writers: dict[str, list[tuple[str, int]]] = {}
    for edge in workspace.query("value_edges"):
        kind = str(edge["kind"])
        method = str(edge["from_method"])
        # **`to_ordinal` is parsed per BRANCH, not once above**, because not every edge is
        # about a call site: `written_by` is about a field, and a field has no ordinal. The
        # unconditional parse crashed the whole resolve on the first module carrying one —
        # `invalid literal for int() with base 10: 'None'` — which is a reminder that this
        # loop is a union of shapes rather than one shape with optional columns.
        if kind == "produced_by":
            ordinal = int(str(edge["to_ordinal"]))
            producers.setdefault((method, int(str(edge["from_value"]))), []).append(ordinal)
        elif kind == "returned_by":
            value = (method, int(str(edge["from_value"])))
            returns.setdefault(value, []).append(
                (int(str(edge["to_ordinal"])), str(edge["to_symbol"]))
            )
        elif kind == "bound_to_parameter":
            parameter = (str(edge["to_symbol"]), int(str(edge["to_index"])))
            callers.setdefault(parameter, []).append((method, int(str(edge["to_ordinal"]))))
        elif kind == "written_by":
            # The sixth edge: `binding -> (writing method, its parameter N)`. Several
            # writers of one binding are several entries, which is what the walk then
            # answers as several values — spec 2026-10-18 §4, where every writer in this
            # module makes the enumeration closed and therefore exact.
            writers.setdefault(str(edge["to_symbol"]), []).append(
                (method, int(str(edge["to_index"])))
            )
        # `read_from_binding` and `names_declaration` are read off the argument entry at
        # the slot instead — they carry no `to_index`, so neither can say which slot it
        # is about. The module docstring states the consequence.

    # **The seventh edge: a lambda's CAPTURE** (`OI-150`). A lambda body is a synthetic
    # method whose leading parameters are the values the enclosing method closed over, and
    # nothing in `value_edges` binds them — `callers` held no entry for any lambda body's
    # parameters, so the walk answered `external` for every captured value. Measured on a
    # module shaped like `ruoyi`'s own declaration: the prefix (an argument) resolved to both
    # its values and the pattern (captured) to nothing, so two controllers differing only by
    # prefix collapsed onto one published path.
    #
    # The facts carry the whole edge already, which is why this is a fold and not a schema
    # change: a `lambda` entry of the argument grammar names its body and how many values it
    # captured, and the value it came from was PRODUCED by the capture site, whose arguments
    # are those values in order. So body parameter *i* is argument *i* of the capture site —
    # identity, measured on four shapes, and `captures` corroborates the count rather than
    # being trusted alone.
    #
    # Parameters at or past the capture count are NOT bound here and must not be: those are
    # the lambda's own arguments, handed in by whoever invokes it, and `external` is the true
    # answer for them.
    for (method, _), site in sites.items():
        for captured in _captures(site["arguments"]):
            # The entry names its body BARE, and every index here is keyed on full symbols.
            # The body is declared in the same class as the method that captured it, so its
            # coordinates are that method's — exact, where a bare-to-full map would be
            # ambiguous the moment two modules declare the same descriptor.
            body = with_descriptor(method, str(captured["symbol"]))
            count = int(str(captured["captures"]))
            source = captured.get("source")
            if not count or source is None:
                continue
            for maker in producers.get((method, int(str(source))), ()):
                bound = (sites.get((method, maker)) or {}).get("arguments") or []
                for position in range(min(count, len(bound))):
                    callers.setdefault((body, position), []).append((method, maker))

    parameters: dict[str, tuple[str | None, ...]] = {}
    for row in workspace.query("method_declarations"):
        declared = row.get("signature")
        if declared is None:
            continue
        parsed = json.loads(str(declared)) if isinstance(declared, str) else declared
        if not isinstance(parsed, dict):
            continue
        named: list[str | None] = []
        for position in parsed.get("parameters") or []:
            found = position.get("name") if isinstance(position, dict) else None
            named.append(str(found) if isinstance(found, str) and found else None)
        parameters[str(row["symbol"])] = tuple(named)

    # Every method something in this module calls, which the dead-write test below reads.
    called = {
        str(row["callee"]) for row in workspace.query("call_edges") if row["callee"] is not None
    }

    # The constants written into bindings, read straight off the fact: a write from a
    # constant has no parameter and therefore no `written_by` edge in `value_edges`, which
    # is why this is a read of its own rather than a seventh arm of that query.
    #
    # **A write by a method that cannot run is skipped**, which the parameter arm gets for
    # free and this one has to ask for: crossing to a writer's callers answers `external`
    # when there are none, while a constant needs no crossing and would otherwise be
    # published however dead the write. The test is `private` AND never called — private is
    # unreachable from outside its class, so no caller means no execution, where a public
    # method with no caller is merely called by something unscanned (a container, a test).
    # Found by review: `private void switchToBackup() { this.topic = "backup"; }`, called by
    # nothing, published `backup` as a `resolved` destination.
    private = {
        str(row["symbol"])
        for row in workspace.query("method_visibility")
        if str(row["visibility"]) == "private"
    }
    dead = private - called
    constants: dict[str, list[Mapping[str, Any]]] = {}
    produced: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for row in workspace.query("field_writes"):
        written = row.get("value")
        if written is None or row["field"] is None:
            continue
        if row.get("written_by") is not None and str(row["written_by"]) in dead:
            continue
        entry = json.loads(str(written)) if isinstance(written, str) else written
        if not isinstance(entry, dict):
            continue
        # **A `source` makes the entry a value of the WRITER's frame**, which is the one
        # thing that separates the two maps: a constant is a value anywhere, a call's result
        # is a value id that only the method that produced it can resolve. A write naming no
        # method cannot be resolved there, so it stays with the constants and reads as the
        # unreadable entry it is.
        if entry.get("source") is not None and row.get("written_by") is not None:
            produced.setdefault(str(row["field"]), []).append((str(row["written_by"]), entry))
        else:
            constants.setdefault(str(row["field"]), []).append(entry)

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

    edges = [row for row in workspace.query("call_edges") if row["callee"] is not None]
    reached = frozenset((str(row["caller"]), int(str(row["ordinal"]))) for row in edges)
    return ValueIndex(
        sites=sites,
        receivers={key: tuple(value) for key, value in receivers.items()},
        producers={key: tuple(value) for key, value in producers.items()},
        returns={key: tuple(value) for key, value in returns.items()},
        callers={key: tuple(value) for key, value in callers.items()},
        parameters=parameters,
        constants={key: tuple(value) for key, value in constants.items()},
        produced={key: tuple(value) for key, value in produced.items()},
        writers={key: tuple(value) for key, value in writers.items()},
        returned_values=returned_values,
        reached=reached,
    )


def _captures(arguments: Any) -> list[Mapping[str, Any]]:
    """Every `lambda` entry in one site's arguments that captured something.

    The argument grammar NESTS and recurs — an array's `elements`, a lambda handed inside a
    varargs array — so this is a walk over the whole structure rather than a scan of the top
    level, the way `scripts/probes/fact_additivity`'s own reader walks it.

    It reads the spelling where the capture list is a fact: an entry of kind `lambda`
    carrying `captures`. A compiler that lowers a closure to a CLASS instead emits an
    `instance` entry with no capture list at all, so there is nothing here to read — the
    register's `OI-150` carries that bound, which belongs to the extractor rather than to
    this fold.
    """
    found: list[Mapping[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if (
                value.get("kind") == "lambda"
                and isinstance(value.get("symbol"), str)
                and value.get("captures") is not None
            ):
                found.append(value)
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    walk(arguments)
    return found


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


def resolve_positions(
    workspace: Workspace,
    positions: Mapping[str, tuple[Mapping[str, Any], int | str]],
    index: ValueIndex | None = None,
    identities: "Identities" = (),
) -> list[dict[str, Answer]]:
    """Slots of SEVERAL sites, resolved together on one coherent path.

    `resolve_site` is this function's one-site case: it combines the slots of a single call
    site and refuses any combination no single path reaches. The two values a caller needs
    are not always slots of one site, and when they are not, pairing them by anything other
    than the path is M-1's fabricated cross product under another name.

    **The case this exists for** (spec 2026-10-18 §4, measured on
    `yudao-spring-boot-starter-web`). A prefix declaration is a key and a predicate:

        pathPrefixes.put(api.getPrefix(),                       // the key, here
                clazz -> matcher.match(api.getController(),     // the pattern, THERE
                        clazz.getPackage().getName()));

    One `put` site is called twice with two different `api` objects, so the key resolves to
    `/admin-api` AND `/app-api`, and the pattern — a slot of a site inside the lambda body,
    a different method — to `**.controller.admin.**` AND `**.controller.app.**`. Four
    pairings exist and two of them are wrong. Both walks cross the same context on the way
    out (the two `new Api(…)` sites in `WebProperties#<init>`, reached through the sixth
    edge), so the coherence rule separates them exactly: the crossed pairs are refused and
    the two true ones survive. Measured, and the reason the per-site pairing the spec first
    wrote down is not enough — ruoyi has ONE `put` site, not one per prefix.

    `positions` is `{label: (site, slot)}` and the answers come back under those labels, one
    dict per coherent path, in a deterministic order (NFR-1): the first label's paths drive
    the outer order. A label whose position no path reaches at all yields no dict rather than
    an `unresolved` entry — the empty list is the M-1 ruling's own answer, as it is in
    `resolve_site`.
    """
    fold = index if index is not None else value_index(workspace)
    walk = _Walk(fold, identities)
    combined: list[tuple[_Trail, dict[str, Answer]]] = [((), {})]
    for label, (named, slot) in positions.items():
        # Projected for the reason `resolve_site` states: a caller that hands in a raw
        # `call_sites` row for a bridge call is otherwise answered with the bridge's own
        # arguments.
        site = fold.sites.get((str(named["caller"]), int(str(named["ordinal"]))), named)
        reached = walk.at(site, slot)
        combined = [
            (merged, {**answers, label: answer})
            for trail, answers in combined
            for path, answer in reached
            if (merged := _combine(trail, path)) is not None
        ]
    return [answers for _, answers in combined]


def producers_of(
    index: ValueIndex,
    site: Mapping[str, Any],
    slot: int | str,
    declared: AbstractSet[tuple[str, str]],
) -> tuple[Producer, ...]:
    """The calls that produced one slot of one site: one `Producer` per distinct end.

    `resolve_site` answers what a value IS. Some readers need the call that BUILT it
    instead, because what they read is that call's own arguments — a block argument, which
    is not a value (ruled 2026-09-22): this reader names the call, and the caller reads its
    block. So this is the same walk, with the same crossings and the same single distance
    rule (§0a) — locals, parameters, returns and bindings — and one more stop: a producing
    call whose `(owner, method)` is in `declared`. Owners are spelled as the site's own
    `owner` column, as the identity table's are (`io/acme/Factory#`).

    **The stop comes before the call's body is read.** A declared call whose body is in this
    module is still where the path ends, since the caller asked for the call and not for
    what its body hands back. A construction is a call like any other: a declared `<init>`
    stops the path where the value walk would answer the constructed type.

    No identity table is applied: an `identified_by` entry says what a value MEANS, and a
    rendering of a client is not the client.

    `site` is projected first, for the reason `resolve_site` states. Identical ends are one
    record — two paths that reach the same call name the same call — and the record carries
    no path. The order is the walk's own (NFR-1).
    """
    walk = _Walk(index, declared=declared)
    site = index.sites.get((str(site["caller"]), int(str(site["ordinal"]))), site)
    found: list[Producer] = []
    for _, answer in walk.at(site, slot):
        if answer.kind == _PRODUCED:
            found.append(answer.value)
        elif answer.kind == UNRESOLVED:
            found.append(Producer(reason=answer.reason))
        else:
            found.append(Producer(ended_at=answer))
    return tuple(dict.fromkeys(found))


def _slots_of(site: Mapping[str, Any]) -> list[int | str]:
    """Which positions this site HAS. The arguments by index, and the receiver where the
    facts name one — `receiver` is the value id it came from and `receiver_parameter` the
    enclosing method's parameter index when it is one (D00 §5); a call that names neither
    has no receiver to resolve, and a static call never does. A `getstatic` receiver carries
    both its id and `receiver_field`, so it needs no test of its own here."""
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

    def __init__(
        self,
        index: ValueIndex,
        identities: Identities = (),
        declared: AbstractSet[tuple[str, str]] = frozenset(),
    ) -> None:
        self._index = index
        self._identities = tuple(identities)
        # The producer reader's stop set (`producers_of`). Empty for the value walk, which is
        # what keeps its answers exactly what they were: `_declared_producer` matches nothing.
        self._declared = frozenset(declared)
        self._memo: dict[tuple[_Position, _Trail], tuple[_Reached, ...]] = {}
        # The positions the current path is IN THE MIDDLE OF resolving. §1d's `cycle` is
        # exactly a return to one of them.
        self._pending: set[_Position] = set()
        # The hole spellings of the template `_joined` is assembling, one per operand. Held
        # on the walk rather than threaded through `product` because the text is built in a
        # comprehension whose shape the coherence rule owns.
        self._holes: tuple[str, ...] = ()
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
        # `(_BINDING, symbol)` — the symbol the `field` argument carried, which the sixth
        # edge is keyed on.
        return self._binding(position[1], trail, frames)

    def _of_site(
        self, site: Mapping[str, Any], slot: int | str, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        method, ordinal = str(site["caller"]), int(str(site["ordinal"]))
        if slot == RECEIVER:
            # A receiver read from a static field is that field (D00 §5's
            # `receiver_field`), resolved as the same field read as an ARGUMENT is: the
            # read's own value id names nothing any other fact joins to.
            field = site.get("receiver_field")
            if field is not None:
                return self._resolve((_BINDING, str(field)), trail, frames)
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
        if kind == "merge":
            return self._merged(argument, method, origin, trail, frames)
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

    def _merged(
        self,
        argument: Mapping[str, Any],
        method: str,
        origin: _Position,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """Capability 9.19's `merge`: a value with several producers, each a candidate in
        the argument grammar (spec 2026-10-21 merged values, §3b).

        **A merge whose candidates share a ROOT resolves to the root, inexactly.** Look at
        what the facts say about the candidates without knowing what any call does: in
        `if (path.startsWith("/")) path = path.substring(1);` the candidates are parameter 2
        and the result of call site 41, and call site 41's own fact says its RECEIVER is
        parameter 2. So the merge is `x` or `f(x)` for the same `x` and an unknown `f` —
        both branches are the same value, possibly re-rendered. That is read off two
        existing facts, never off the method's semantics (ruling 3, dropped: no `substring`
        entry anywhere, nor one per string manipulation). The root is answered through every
        edge the walk already has — a parameter root crosses `bound_to_parameter` to every
        caller, ruling 1's multiplicity — and every answer is marked `inexact`, which
        `url_of_answer` publishes at `partial` and `channel_of_answer` refuses.

        **A merge with no root is `non_enumerable`**: two literals on two branches, two
        unrelated calls. Picking one would be a fact about code that may never run — the
        Phase 2G ruling, unchanged; the candidates stay in the fact for a reader.
        """
        candidates = argument.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return _only(trail, _unresolved(NON_ENUMERABLE))
        root = self._root_of(candidates, method)
        if root is None:
            return _only(trail, _unresolved(NON_ENUMERABLE))
        return tuple(
            (
                crossed,
                replace(answer, inexact=True) if answer.kind in (LITERAL, EXPRESSION) else answer,
            )
            for crossed, answer in self._entry(root, method, origin, trail, frames)
        )

    def _root_of(
        self, candidates: "list[Mapping[str, Any]]", method: str
    ) -> "Mapping[str, Any] | None":
        """The candidate every other candidate is a call ON — or None.

        `x` is a root when each other candidate `c` is either `x` spelled again or a value
        some call in this method produced (`c.source`) whose receiver, or one of whose
        arguments, is `x`. A root is a PARAMETER (matched by the site's `receiver_parameter`
        or an argument naming the same index) or a value with its own id (matched by the
        site's `receiver` or an argument carrying the same `source`); a bare literal has no
        id to be matched on, and two different literals are no root at all — the extractor
        already folds two identical ones.
        """
        for root in candidates:
            if all(
                other == root or self._is_a_call_on(other, root, method) for other in candidates
            ):
                return root
        return None

    def _is_a_call_on(
        self, candidate: Mapping[str, Any], root: Mapping[str, Any], method: str
    ) -> bool:
        source = candidate.get("source")
        if source is None:
            return False
        producers = self._index.producers.get((method, int(str(source))), ())
        if not producers:
            return False
        site = self._index.sites.get((method, min(producers)))
        if site is None:
            return False
        if root.get("kind") == _PARAMETER and root.get("value") is not None:
            index = int(str(root["value"]))
            if (
                site.get("receiver_parameter") is not None
                and int(str(site["receiver_parameter"])) == index
            ):
                return True
            return any(
                argument.get("kind") == _PARAMETER
                and argument.get("value") is not None
                and int(str(argument["value"])) == index
                for argument in site.get("arguments") or []
            )
        if root.get("source") is not None:
            root_id = int(str(root["source"]))
            if site.get("receiver") is not None and int(str(site["receiver"])) == root_id:
                return True
            return any(
                argument.get("source") is not None and int(str(argument["source"])) == root_id
                for argument in site.get("arguments") or []
            )
        return False

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

        **Returning None is not a failure**, and that is the shape of ruling 1: not
        joining leaves the behaviour §6 already had, so a template this cannot fill reads
        exactly as it did before.

        The refusals, each because the alternative is a string nobody wrote:

        * **no producing site for `source`** — the concat's own arguments are where the
          operands live, and without that site there is nothing to fill from;
        * **a hole count that disagrees with the operand count** — the template's `{}`
          come from the recipe's `\u0001` markers, one per runtime argument, so a
          mismatch means one of the two was misread and guessing an alignment would
          publish operands in the wrong places;
        * **an operand that is not a `string` literal** — a parameter, a `${...}`
          expression, a symbol, an `absent`, an `unresolved` — contributes NO candidate,
          and its hole stays a hole (§3). Where every hole is like that the answer is
          None and the caller carries the template, which is what this arm did before it
          filled holes at all.

        **Two refusals became behaviours on 2026-10-18** (spec 2026-10-18, `OI-143`), and
        both were wrong in the same direction — discarding what WAS read:

        * *several answers for one hole* was a refusal, on the reason "nothing in the 27
          measured corpora reaches it". `apolloconfig/apollo` reaches it 64 times at one
          call site, and the corpora could not have contained the shape — all three field
          pins are inbound-only. It is now the product, which is ruling 1's multiplicity
          unchanged and already the rule for a single position;
        * *one unresolvable operand* discarded the whole template. It now fills what it
          can: `{}apps/{appId}` says "something, then `apps/{appId}`", which is true and
          strictly more than `{}{}` says.

        **Paths that do not cohere are still dropped** — `_combine`'s rule, unchanged: two
        holes that crossed the same context differently did not happen together, so the
        string they would make was never assembled by any single run.
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

        # **One candidate list per hole: every `string` literal the walk reached there, or
        # the hole itself where it reached none** (spec 2026-10-18 §3, §4). The second half
        # is what makes a partly-known address possible — an unresolvable hole no longer
        # discards the holes beside it that ARE known.
        per_hole: list[tuple[tuple[_Trail, str | None, str, bool], ...]] = []
        # **A hole nobody filled is NAMED after the value that fills it at runtime**, where
        # the facts name that value (ruled by the user 2026-10-18, one position over from
        # `<host>`). `"/owners/" + ownerId + "/pets"` is the most ordinary outbound address
        # there is, and `{}` said "something here" about a parameter the signature names:
        # `/owners/{ownerId}/pets` is both readable and the SERVER's own spelling of the
        # same route, so the two sides of one call can finally be compared.
        #
        # Only a PARAMETER is named. A hole filled by a call's result — `"?petId=" +
        # join(petIds)` — has no name to take, and naming it after the method would be
        # inventing a variable the code does not have.
        unfilled = [
            # **A LEADING hole is never named, and that is the user's `<host>` ruling held
            # one layer down** (`OI-152`). Where the template begins with a hole, that hole
            # is the authority — `parseHost(service) + "/health"`,
            # `metaServerAddress + "/services/admin"` — and a reader of an address needs to
            # know WHO is called, which the local name of the value does not say. Measured
            # on `apollo-portal`: naming it turned four rows into
            # `{metaServerAddress}/services/admin`, which reads like a route variable and
            # answers nothing. The address layer prints `<host>` there instead.
            _HOLE if at == 0 and template.startswith(_HOLE) else self._named_hole(operand, method)
            for at, operand in enumerate(operands)
        ]
        for operand, hole in zip(operands, unfilled, strict=True):
            reached = self._entry(operand, method, origin, trail, frames)
            # An INEXACT literal fills its hole like an exact one — the text is the value the
            # code states, read through a merge whose root it is — and taints the result
            # below: a template filled from one is never `literal`, because part of what
            # was sent (what the call on the root did to it) was not read.
            settled = tuple(
                (crossed, str(answer.value), answer.yields, answer.inexact)
                for crossed, answer in reached
                if answer.kind == LITERAL and answer.literal_kind == STRING
            )
            per_hole.append(settled or ((trail, None, _ADDRESS, False),))
        self._holes = tuple(unfilled)

        # Nothing anywhere: the caller carries the template unchanged, which is what it
        # did before this arm resolved holes at all.
        #
        # **"Nothing" now includes being unable to NAME a hole.** A template whose every
        # hole is anonymous says exactly what the extractor's own `value` says, so handing
        # it back changes nothing and the caller's existing path is shorter. But where a
        # hole takes a name, the answer is strictly better than the fact —
        # `/owners/{ownerId}/pets` against `/owners/{}/pets` — and the caller must be given
        # it even though no hole was FILLED. That is why this is two tests rather than one.
        filled = any(value is not None for hole in per_hole for _, value, _, _ in hole)
        if not filled and all(hole == _HOLE for hole in unfilled):
            return None

        reached_out: list[_Reached] = []
        for combination in product(*per_hole):
            # §4: paths merged by `_combine`'s coherence rule, and an incoherent
            # combination DROPPED rather than answered. Two holes that crossed the same
            # context differently did not happen together, so the string they would make
            # was never assembled by any single run.
            merged: _Trail = trail
            coherent = True
            for crossed, _, _, _ in combination:
                joined = _combine(merged, crossed)
                if joined is None:
                    coherent = False
                    break
                merged = joined
            if not coherent:
                continue
            text = pieces[0] + "".join(
                (value if value is not None else hole) + piece
                for (_, value, _, _), hole, piece in zip(
                    combination, self._holes, pieces[1:], strict=True
                )
            )
            whole = all(value is not None for _, value, _, _ in combination)
            inexact = any(inexact for _, _, _, inexact in combination)
            # **An AUTHORITY joined to a path is written scheme-relative** (`OI-142`,
            # ruling 2). `//customers-service/owners` is RFC 3986 §4.2's scheme-relative
            # reference — a real URI form, not an invention — and the `//` says exactly
            # where the authority ends, so `split_url` separates the two columns with no
            # second shape for any consumer to learn. Only where the result carries no
            # scheme of its own: `"http://" + host + "/x"` already says where the
            # authority starts and prefixing that would be wrong.
            if any(kind == _AUTHORITY for _, _, kind, _ in combination) and "://" not in text:
                text = f"//{text}"
            # **`literal` only when EVERY hole was read; otherwise `expression`**, and that
            # is the whole safety of a partial fill (§3). A half-filled template is not a
            # value the code states, it is a statement about part of one — and
            # `channel_of_answer` refuses an expression, so no messaging catalog can read
            # one as a destination. A broker resolves a destination it is GIVEN and half of
            # one is not a destination.
            reached_out.append(
                (
                    merged,
                    Answer(kind=LITERAL, value=text, literal_kind=STRING, inexact=inexact)
                    if whole
                    else Answer(kind=EXPRESSION, value=text, inexact=inexact),
                )
            )
        # Deduplicated on (path, answer): several combinations routinely agree, and two
        # identical answers are one answer (§1c's own rule for distinct destinations).
        return tuple(dict.fromkeys(reached_out)) or None

    def _named_hole(self, operand: Mapping[str, Any], method: str) -> str:
        """What an unfilled hole PRINTS: `{name}` where the operand is a parameter the
        facts name, `{}` otherwise.

        The name is the declaration's, read off the signature the compiler recorded — never
        synthesised. A jar built without parameter names, and an operand that is not a
        parameter at all, both fall to the anonymous hole, which says exactly as much as it
        did before: a runtime value belongs here.
        """
        if operand.get("kind") != _PARAMETER or operand.get("value") is None:
            return _HOLE
        declared = self._index.parameters.get(method, ())
        position = int(str(operand["value"]))
        if position >= len(declared) or declared[position] is None:
            return _HOLE
        return "{" + str(declared[position]) + "}"

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
        construction, or no entry claiming it. A constructor the producer reader declared
        claims it too, so that reader reaches the construction through `_value` as well."""
        source = argument.get("source")
        if source is None:
            return None
        value = int(str(source))
        constructed = self._construction(method, value)
        if constructed is None:
            return None
        site = (method, constructed)
        if self._identified(site) is None and self._declared_producer(site) is None:
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

        **A DECLARED producer ends the path before anything else is read** — the one stop
        `producers_of` adds to this walk, checked ahead of the returns because that reader
        asks for the call and not for what its body hands back. The value walk declares
        nothing, so for it both checks below answer None and nothing else changes.
        """
        producers = self._index.producers.get((method, value), ())
        if producers:
            stopped = self._declared_producer((method, min(producers)))
            if stopped is not None:
                return _only(trail, stopped)
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
        if not producers:
            # No call handed this value back. A CONSTRUCTION is still a producer — one the
            # `produced_by` edge cannot carry, because `call_sites.result` is null for an
            # initialiser — so an identity entry naming it answers here (review round 1,
            # and `_construction` says how the site is found). Where nothing identifies the
            # construction the answer is exactly what it was before: this branch exists to
            # reach a MEASURED claim about one producer, not to give constructed values a
            # second reading of their own.
            constructed = self._construction(method, value)
            if constructed is not None:
                stopped = self._declared_producer((method, constructed))
                if stopped is not None:
                    return _only(trail, stopped)
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
            identified = self._resolve((_SLOT, site[0], site[1], slot), trail, frames)
            # **A RENDERING carries one KIND of identity and stamps none** (`OI-138` cause
            # 3, CP-39). `String.valueOf(x)` returns `x.toString()` — the TEXT of whatever
            # `x` stands for — so an entry over it may propagate an identity and must never
            # mint one. `OI-142` refused such an entry outright and was right about the
            # danger: for a JMS `Queue` identified as `"orders"` the text is a vendor debug
            # string, and carrying it would publish an address that never existed.
            #
            # `preserves: authority` is the bound. An identity that yields an AUTHORITY
            # names WHO is called, and who is called does not change when the value is
            # rendered; an identity that yields an `address` is dropped here and reaches no
            # further. Where nothing survives, the answer is the one a site with no entry
            # gets — for a JDK method `external`, its body being outside what was scanned,
            # which stays true.
            preserved = self._preserved_kind(site)
            if preserved is not None:
                # **A path this entry cannot carry is REPLACED, never dropped**, and that
                # distinction is the whole soundness of the key. Filtering the pairs let a
                # second path vanish, and a reader of the result then saw ONE answer where
                # the code had two — which is how `authority_of`'s "several peers for one
                # call is not a peer" refusal was defeated without ever being reached.
                #
                # MEASURED, on the most ordinary shape there is: a private helper
                # `fetch(URI host)` whose concat is the address, called once with a
                # discovery lookup and once with a `URI` its own caller supplied. The
                # parameter is two calling contexts, so the operand answers on two paths —
                # `customers-service` yielding an authority, and `external` from the
                # unbound parameter. The filter kept the first, and the row published peer
                # `customers-service` for a helper half of whose calls go somewhere the
                # code never states.
                #
                # `external` is the right word for the replacement and not a stand-in: an
                # identity that yields an `address` says the TEXT of this value is a vendor
                # string rather than a destination, so what this rendering produces is a
                # value no fact in the workspace reads — which is what `_unresolved` says.
                # The same word the no-answer case below used, now said per path.
                unreadable = _unresolved(NOT_READABLE if site in self._index.reached else EXTERNAL)
                return tuple(
                    (crossed, answer if answer.yields == preserved else unreadable)
                    for crossed, answer in identified
                ) or _only(trail, unreadable)
            # The ENTRY says what kind of thing this producer yields, so it is stamped here
            # rather than carried by the slot's own answer: argument 0 of
            # `getInstances("customers-service")` is an ordinary string literal, and what
            # makes it an AUTHORITY is the entry, not the string.
            kind = self._identified_yields(site)
            if kind == _ADDRESS:
                return identified
            return tuple(
                (crossed, replace(answer, yields=kind) if answer.kind == LITERAL else answer)
                for crossed, answer in identified
            )
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
        # **The identity its RECEIVER carries** (`OI-142`), for a call that hands back
        # something still standing for the same thing. Below the two arms above because
        # they are more specific: a call naming its own identifying argument answers from
        # that argument, never from what it was invoked on.
        if self._preserves_receiver(site):
            return self._through_receiver(site, trail, frames)
        # Nothing identifies it. Whether its BODY was read is what separates the two
        # reasons, and `call_edges` is the table that says so — it writes a row per site
        # with a NULL callee at the third-party boundary. MEASURED on `mall-admin`: 1,411
        # of 2,065 value-producing sites are that boundary, so `external` is the common
        # answer and not the corner case.
        return _only(trail, _unresolved(NOT_READABLE if site in self._index.reached else EXTERNAL))

    def _through_receiver(
        self, site: tuple[str, int], trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """The receiver's own identity, handed on as this call's — or `not_readable` where
        the receiver does not resolve to exactly one.

        **EXACTLY ONE, and that single condition is what makes an entry on `List.get` safe.**
        It is the user's own argument of 2026-10-17: element access on a list of a service's
        instances yields the same service, because every instance of a service IS that
        service. What makes it sound in general is that the identity table already separates
        the two cases, and the walk's multiplicity separates them again at resolve time:

        * a SINGLE-VALUED identity resolves to one answer, and an element of a collection
          identified as one thing is that thing. MEASURED over the shipped table: of 23
          entries, the only single-valued one producing a collection is
          `Collections.singletonList` at `arg: 0` — and `singletonList("x").get(0)` IS `x`,
          so propagating is right there too;
        * an ENUMERATING identity (`all_strings`) resolves to several, and an element of a
          collection identified as MANY things is one of them, which one being unknowable.
          MEASURED: all three such entries are topic lists — `List.of`, `Arrays.asList`,
          `Subscriptions.topics` — and propagating would answer every topic for one element,
          a wrong answer at `resolved`, which is the one failure §7 names.

        So the refusal is not caution about a case nobody has: it is the exact line between
        the three entries that must not propagate and the rest. A future entry that breaks
        it would have to declare a single-valued identity on a producer whose elements differ
        from it, and `by:` means no entry lands without a measurement saying otherwise.
        """
        row = self._index.sites.get(site)
        receiver = None if row is None else row.get("receiver")
        if receiver is None:
            # A static or unreadable receiver. `not_readable` rather than `external`: the
            # call IS in what was scanned, and the thing that is missing is the value it
            # was invoked on.
            return _only(trail, _unresolved(NOT_READABLE))
        reached = self._through(site[0], int(str(receiver)), site[1], trail, frames)
        if len(reached) != 1:
            return _only(trail, _unresolved(NOT_READABLE))
        # Handed back WHOLE, which is what carries `yields` along the chain: a value that
        # stands for a service still stands for one after `.get(0)` and after `.getUri()`.
        return reached

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

    def _declared_producer(self, site: tuple[str, int]) -> Answer | None:
        """The path's end where `site` is a call the producer reader declared, else None.

        Matched on the projected row's `owner` and `name`, exactly — the pair the caller
        declared, with no arity or descriptor, because the question is which call built the
        value and not which overload. The value walk declares nothing, so this answers None
        there before reading anything."""
        if not self._declared:
            return None
        row = self._index.sites.get(site)
        if row is None:
            return None
        identity = (row.get("owner"), row["name"])
        if identity not in self._declared:
            return None
        return Answer(
            kind=_PRODUCED,
            value=Producer(
                caller=site[0], ordinal=site[1], identity=(str(identity[0]), str(identity[1]))
            ),
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

    def _identified_yields(self, site: tuple[str, int]) -> str:
        """What KIND of thing the entry that answered for `site` yields — `address` unless
        it says `authority`.

        Read beside `_identified` rather than returned with it, so the slot reader keeps
        the one-line contract every caller already has. The two always agree: both walk
        `_identity_matches` in the table's order and take the first entry in a form they
        understand.
        """
        for entry in self._identity_matches(site):
            if isinstance(entry.get("arg"), int):
                return str(entry.get(_YIELDS, _ADDRESS))
        return _ADDRESS

    def _preserved_kind(self, site: tuple[str, int]) -> str | None:
        """The `preserves` word of the entry that answers for `site`, or None.

        Read off the SAME entry `_identified` picks — the first in the table's order with an
        integer `arg` — so the two cannot disagree about which entry is in force. An entry
        declaring `preserves` propagates an identity of that kind and mints none, which is
        what makes a rendering call safe to cross (`_value`, CP-39 Q3).
        """
        for entry in self._identity_matches(site):
            if isinstance(entry.get("arg"), int):
                preserved = entry.get("preserves")
                return None if preserved is None else str(preserved)
        return None

    def _preserves_receiver(self, site: tuple[str, int]) -> bool:
        """Whether a matching entry says this call's result stands for whatever its
        RECEIVER stands for.

        The third form `arg` cannot express, and the one a discovery chain needs
        (`OI-142`). `discoveryClient.getInstances("customers-service")` names its service
        at argument 0, but the two calls after it name it nowhere: `.get(0)`'s argument is
        an int index and `.getUri()` has no arguments at all. What both say is "I hand back
        something that is still about the same service", and an identity model built only
        out of positions has no way to say it.

        **The caller gates this on the receiver resolving to exactly ONE answer, and that
        gate is the whole safety argument** — see `_through_receiver`.
        """
        return any(entry.get(_FROM_RECEIVER) is True for entry in self._identity_matches(site))

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

    def _binding(self, symbol: str, trail: _Trail, frames: "_Frames") -> tuple[_Reached, ...]:
        """A value read out of a named mutable location (§5a: a binding, never a field —
        it is a field in one language, a module-level variable in another, a package var
        or a closure cell elsewhere).

        **THE SIXTH EDGE, as of 2026-10-18.** Each `written_by` entry says which method
        wrote this binding and from which of its parameters, and the answer is that
        parameter resolved in the writing method — `_parameter`'s own crossing, so nothing
        new follows the edge. What this method adds is one hop, not a mechanism.

        **Several writers are several answers**, and spec 2026-10-18 §4 rules that this is
        exactness rather than doubt where every writer is in this module: a field assigned
        by two constructions holds two values, both real, and one row each is what ruling 1
        has always said about an enumerable set. Where a writer's own callers are outside
        what was scanned, the crossing answers `external` and the row says so.

        **A CONSTANT write is answered without crossing anything** (`OI-138` cause 2, 2026-10-18):
        `private String hostname = "http://visits-service/"` compiles to `ALOAD 0; LDC;
        PUTFIELD`, the fact now carries that constant, and the answer is the literal itself.
        Before it, the fact could only point at a parameter, so this write emitted nothing and
        this method answered `no_writer` about a literal one line above the read — measured on
        `spring-petclinic-microservices`, where it cost an outbound host and left the row with
        no address at all.

        **A write from a CALL'S RESULT is resolved in the writing method** (CP-33 rows 6-7,
        2026-10-26). A file-level `val client = HttpClient(CIO) { … }` compiles to
        `invokestatic; putstatic` in `<clinit>`, and the fact carries the value as the
        argument entry a call result already is — `unresolved` with its `source` — so the
        answer is that entry resolved in `<clinit>`'s frame by the same `_entry` a call
        argument there would get: through an in-module callee's returns, an identity entry,
        or `external` for a factory nobody scanned. A STATIC field needs nothing extra: its
        read and its `putstatic` carry the same symbol, and no receiver is compared for any
        binding.

        **`no_writer` still means something, and it is narrower again:** no write of this
        binding was REPORTED. The remaining shapes are a value built with `new`, a value
        parked in a local before the write, a computed assignment, plus a container writing
        the field reflectively, which no bytecode can show (`@Autowired` field injection,
        §8.2's territory, and the reason `mall-admin` answers nothing here).

        **The frame travels with the hop.** A binding write is resolved in the WRITING
        method's frame, which is not this read's: the parameter index means something only
        inside the declaration that introduced it, so handing `frames` on unchanged is what
        lets a nested descent stay correct.
        """
        written = self._index.writers.get(symbol, ())
        constants = self._index.constants.get(symbol, ())
        produced = self._index.produced.get(symbol, ())
        if not written and not constants and not produced:
            return _only(trail, _unresolved(NO_WRITER))
        reached: list[_Reached] = []
        for entry in constants:
            # **A CONSTANT write needs no crossing** (`OI-138` cause 2): the value is in the
            # fact, so the answer is that literal on the path already travelled.
            #
            # **An entry this walk cannot read answers `not_readable`, and never nothing.**
            # The grammar carries kinds the walk has no literal for — `class` is one, and
            # `private Class<Order> t = Order.class` is ordinary code — and contributing no
            # answer there was a measured defect: with no answer and no other writer this
            # method returned an EMPTY tuple, which `resolve_site` reads as "no path answers
            # every slot" and drops every slot of the site. Found by review before this
            # shipped: a `getForObject(url, responseType)` whose `url` field resolved
            # through the sixth edge lost its ADDRESS because the response-type field beside
            # it held a class constant. One unreadable write is one unreadable answer, which
            # is also what the parameter arm does with a writer it cannot follow.
            literal_kind = _LITERAL_KINDS.get(str(entry.get("kind")))
            if literal_kind is not None and entry.get("value") is not None:
                reached.append(
                    (trail, Answer(kind=LITERAL, value=entry["value"], literal_kind=literal_kind))
                )
            else:
                reached.append((trail, _unresolved(NOT_READABLE)))
        for method, index in written:
            reached.extend(self._resolve((_PARAMETER, method, index), trail, frames))
        for method, entry in produced:
            # The origin names the write and has no ordinal, so `_through`'s `escapes` window
            # is the whole of the writing method after the call: a call made on the stored
            # object anywhere there changes what every later reader of the field sees.
            reached.extend(self._entry(entry, method, (_BINDING, symbol, method), trail, frames))
        return tuple(dict.fromkeys(reached))


# The callee frames the walk descended through: (method, the site that called it),
# innermost last. A method appears more than once only where the walk descended into it
# twice on one path, and the innermost is the one that answers.
_Frames = tuple[tuple[str, tuple[str, int]], ...]


def _frame_of(frames: _Frames, method: str) -> tuple[str, int] | None:
    for framed, site in reversed(frames):
        if framed == method:
            return site
    return None
