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
import re
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from itertools import product
from typing import Any, cast
from weakref import WeakKeyDictionary

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.beans import (
    PARAMETER_TYPE,
    Ambiguous,
    Injection,
    ProvidedBy,
    RecipeCalls,
    injected_parameters,
    recipe_calls,
)
from sextant.application.resolve.dispatch import DYNAMIC, Dispatch, dispatch_of
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.domain.config_keys import carries_expression
from sextant.domain.symbols import (
    bare_descriptor,
    descriptor_slots,
    field_type,
    is_type_descriptor,
    method_descriptor,
    method_name,
    owner_of,
    returned_slot,
    returned_type,
    slot_of_type,
    with_descriptor,
    with_method_name,
)

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

# A construction's name at a call site (D00 §5).
_INIT = "<init>"
# The written types that name no one class (D00 §5a): a union's members are each a type,
# `Any` is every type, and `None` has no method.
_UNION = "typing/Union#"
_ANY = "typing/Any#"
_NONE = "builtins/None#"
# A return written `Self` (D00 §5a): the class the call was made through.
_SELF = "Self"
# A descriptor's method (`_Walk._plain_attribute`).
_GET = "__get__"
# The name the facts give a call of a value (`f(x)` on a value `f`, D00 §5).
_CALL = "__call__"
# `returns_argument`'s three forms (`Catalog.returns_arguments`).
_RETURNS = "returns"
_RESULT_RETURNS = "result_returns"
_RESULT_CALLS = "result_calls"

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
# The mark a `_BINDING` position carries where the field is read on an object from outside
# (`_Walk._unseen_object`): a position of its own, so its answer is never shared with the
# same field's ordinary read.
_UNSEEN = "unseen"
# Contexts a path records a CHOICE for. Two slots of one site may disagree about nothing:
# if both cross out of the same method, they cross through the same call (M-1); if both
# read the same value, they read the same return of the same callee. Different contexts
# are independent, and combining them is not a fabrication but the code's own product.
_CALLER_OF = "caller-of"
_RETURN_OF = "return-of"
# Which recipe's return a container-filled parameter receives (spec 2026-11-05 di-recipe-hop
# §2): one context per parameter, because the container fills each parameter on its own.
_FILLED_BY = "filled-by"
# The framework's own call of a method whose parameters name their recipes (plan 2026-11-08 N5):
# a calling context of that method, as a caller's `caller@ordinal` is, so one execution takes
# every parameter from the framework's fill or every one from one direct caller. Written as a
# `caller@ordinal` label naming no call of the module; it crosses out to no caller in the module
# (`Path.crossed_out_of` leaves it out, `Path.filled_in` names it).
_FRAMEWORK_CALL = "<framework>@-1"
# What a recipe body hands back, its own position, so it is read once per body however many
# parameters it fills (`_Walk._recipe_runs`).
_RECIPE_RUN = "recipe-run"
# What the framework's call hands one parameter (`_Walk._recipe_paths`), its own position read
# with no frame: the framework runs the recipe as an execution of its own, so no call the walk
# descended through is on its stack, and the answer is one for every frame stack that reaches
# the parameter.
_RECIPE_PATHS = "recipe-paths"
# The parts of the index a binding round changes (`receiver_binding._with_new_callers`), as a
# walk records reading them (`_Walk._depends`, `suffixes_kept`): a method's callers, a site's
# callees, whether a site reached a body, a writer's calls.
READ_CALLERS = "callers"
READ_CALLEES = "callees"
READ_REACHED = "reached"
READ_CALLED_AT = "called_at"
# A field read through a getter on one object (ruling 1, `_Walk._object_writes`): WHICH
# construction the read's receiver is, and WHICH write of the field the read takes. Both are
# keyed on the receiver as the reading method holds it, never on the field's class: two
# reads on one receiver are one object and read one write, and two receivers are free to be
# two objects (`pair(a.getCron(), b.getCron())` is `(A, B)`).
_OBJECT_OF = "object-of"
_WRITE_OF = "write-of"
_ELEMENT_OF = "element-of"
# Which candidate of a merge with no root a path took (ruling 7, `_Walk._branched`).
_BRANCH_OF = "branch-of"
# Which body a hand-off with several callees ran (spec 2026-11-02 rule 1, `_Walk._handed_to`):
# one path per callee, never one answer for all of them.
_HANDED_TO = "handed-to"
# A hand-off to a call a catalog STATES the effect of (spec 2026-11-02 rule 7,
# `Catalog.hand_off_effects`): no `escapes`, a step of its own on the path, so a reader of
# the part the call binds finds the call (`Path.stated`).
_STATED = "stated"
# A configuring call gathered INSIDE a body a hand-off entered (spec 2026-11-02 rule 1;
# item 1's review, concern 6): `(_GATHERED, method, ordinal, *entered)`, the calls that entered
# that body innermost first, as `_STATED` carries them. A reader of the call's own arguments
# reads a parameter of that body at the call that entered it on THIS path
# (`Path.entered_into`, `entered_position`), never across every caller of the body.
_GATHERED = "gathered"
# Whether a call that is NOT on every path to the use ran on this path (spec 2026-11-02 rule
# 9, `Flow.paths`): one path where it ran, one where it did not, recorded as a choice so two
# reads on one path agree on it. The context is `(_SPLIT, method, ordinal, counts)`: whether
# the split counts for the reader's row is decided where the split is made, from what the
# call sets (`_counted`), and travels with it.
_SPLIT = "split"
_RAN = "ran"
_SKIPPED = "skipped"
# A split path the facts do not prove a run takes to the use (rule 9, ruled by the user
# 2026-11-03, "A: add post_dominator"): the path is kept, its answers inexact (`partial`).
_UNPROVEN = "unproven"
# A window two or more of whose calls split it (review 3, M2): every path from it is inexact
# whichever way each call went, so the paths are not told apart by their choices — one mark
# instead, and paths that gather the same calls are one.
_SEVERAL = "several"
# The most paths one window enumerates (review 3, M2): each split doubles them, and twenty
# guarded setters on one object were a million paths, 30.9 s and 2.15 GB. Past it the window
# is one path ending `non_enumerable`, stated, never dropped. Measured: the eleven corpora's
# worst window holds 5 paths.
PATH_CAP = 256

# The types nothing can change through a reference to them (spec 2026-11-02 rule 3): the
# primitives, `String` and the boxed primitives, as a descriptor spells a type. A property of
# the TYPE, never of a method: read off the site's own descriptor for the parameter a value is
# handed to, and off the facts for the VALUE's own type (fix round 1, M1 — `_Walk._type_of`).
_UNCHANGEABLE = frozenset(
    {
        "Z",
        "B",
        "C",
        "S",
        "I",
        "J",
        "F",
        "D",
        "Ljava/lang/String;",
        "Ljava/lang/Boolean;",
        "Ljava/lang/Byte;",
        "Ljava/lang/Character;",
        "Ljava/lang/Short;",
        "Ljava/lang/Integer;",
        "Ljava/lang/Long;",
        "Ljava/lang/Float;",
        "Ljava/lang/Double;",
    }
)
# Where in a body a field write sits, which the fact does not say (D00 §5's `field_write`
# carries no ordinal): read only where the window runs to the body's end, it sorts last.
_END_OF_BODY = 2**63 - 1

# §2's `identified_by` table, as the walk is handed it: `{owner?, method, arg, arity?,
# descriptor?, role?}` per producing call, built once by the loader (`yaml_source
# .value_model`) from `value-models/` plus every hop declaration still written on a
# catalog. It is DATA the caller passes in, never knowledge this module holds — the rule
# the module docstring states, and the reason the parameter exists at all.
Identities = Sequence[Mapping[str, Any]]

# A type's DIRECT supertypes, by bare type descriptor, as `dispatch.Dispatch.ancestors` holds
# them: `(supertype, kind, scanned)` in the JVM's search order. Handed to `producers_of` by a
# reader that turns `past_accessors` on; this module never reads the hierarchy itself.
Ancestors = Mapping[str, Sequence[tuple[str, str, bool]]]

# Which splits count for a reader's row (ruled by the user 2026-11-03, option A): a call on a
# branch at `(method, ordinal)` counts toward the several-splits rule only where it sets a part
# the reader's row publishes. None, a reader that states no published parts: every split counts.
Counting = Callable[[str, int], bool] | None

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
    # **"One of these runs; which one is not known"** (ruling 7, spec 2026-10-28 quartz §3c) —
    # D00's `narrowed`, the word `dispatch.py` uses for several bodies. Set only by `_merged`,
    # on each candidate of a merge with no root whose candidates are ALL literals, and
    # carried through every hop after, like `inexact`. The candidates are the complete set,
    # but no one of them is the value: `url_of_answer` publishes one at `narrowed`,
    # `channel_of_answer` refuses it, and `_joined` marks a template filled from one.
    narrowed: bool = False
    # **The class the identifying call names beside this value** (spec 2026-11-05 §2): set only
    # by an identity entry declaring `class_arg`, from that SAME producing call's argument,
    # read on the same path in the same walk (`_Walk._with_class`), so a key and the class of
    # what it addresses (`create(Command.class, "stock")`) are never paired afterwards. The
    # class literal's symbol; None where the entry names no class or the argument is not a
    # class literal on any path agreeing with the value's. Carried through every hop after,
    # like `yields`. Part of what the answer is: two keys named alike that address two
    # classes are two answers.
    carried_class: str | None = None
    # **Which parameter an `external` answer ended at**, `(method, index)` — set only by
    # `_Walk._parameter` where nothing in the module binds it, for the producer reader to
    # hand on (`Producer.parameter`). Not part of what the answer IS, so it is outside
    # equality: two `external` answers at two parameters are still one answer to every
    # reader that deduplicates them, exactly as before it existed.
    parameter: tuple[str, int] | None = dataclass_field(default=None, compare=False, repr=False)
    # **Which library call an `external` answer ended at**, `(method, ordinal)` — set only by
    # `_Walk._value` where a value's producer is a call whose body was not read, for the
    # producer reader to hand on (`Producer.made_by`), so a reader can name the decorator a
    # walk stopped at. Outside equality, as `parameter` is.
    made_by: tuple[str, int] | None = dataclass_field(default=None, compare=False, repr=False)
    # **The value IS the class (or module) the symbol names, not an object built from it**
    # (ruling R37): set on a `class` reference and on a name read as the type it is
    # (`_named_type`). A `symbol` answer is both "the class" and "the type a value was built
    # from"; a protocol call Python looks up on the value's type (`xs[i]`, `for x in xs`)
    # differs between the two, so the reader of a receiver tells them apart. Part of what
    # the answer is: a class and an object of it are two values.
    class_object: bool = False
    # **The type a method DECLARES it returns, not one its body was read to give** (OI-324
    # part 2): set only by the type reader (`producer_paths(..., declared_types=True)`), on a
    # return path the body answers with no type, or for a method with no body. Its evidence
    # is `declared`, beside the `syntax` of a type the walk reached. A declared type does not
    # say whether the value is the class or an instance of it (the facts write `type[X]` as
    # `X`), so a reader of syntax calls cannot take it (`receiver_binding`).
    declared: bool = False
    # **The `absent` value is the code's `null` (`None`)**, D00 §5's `null` kind: set only
    # there. An empty array or an empty argument list is `absent` too, and is not `null`; a
    # reader saying which one the code holds tells them apart by this (`receiver_binding`).
    # Part of what the answer is: no value and an empty collection are two values.
    null: bool = False


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

    `parameter` says which parameter a path ended at, beside an `external` reason or alone
    where the reader asked the walk to stop there (`stop_at_parameters_of`).
    """

    caller: str | None = None
    ordinal: int | None = None
    identity: tuple[str, str] | None = None
    reason: str | None = None
    ended_at: Answer | None = None
    # Set only by a reader walking ALONG RECEIVERS (`producers_of(..., along_receivers=True)`):
    # every declared call of the chain that built the value, `(caller, ordinal)`, ROOT FIRST
    # and ending at `caller`/`ordinal` — across methods, in the path's own calling contexts.
    # `rooted` says the first one is a call on no receiver at all (a static factory), so the
    # chain is whole; False where its first call's receiver is something the walk could not
    # follow to another declared call.
    chain: tuple[tuple[str, int], ...] = ()
    rooted: bool = False
    # A branch was passed through on the way (`_Walk._passed_through`): the chain is the
    # shared receiver's, and which of the branch's own calls ran is not known.
    inexact: bool = False
    # The parameter a path ENDED at, `(method symbol, parameter index)`: one nothing in the
    # module calls (with `reason` `external`), or one of a method the reader named in
    # `stop_at_parameters_of` (with no reason — the path ended where it was asked to). After
    # a lambda's capture crossing, the method named is the CAPTURING method, never the body.
    # None everywhere else.
    parameter: tuple[str, int] | None = None
    # The library call an `external` path ended at, `(method, ordinal)` (`Answer.made_by`).
    # Outside equality: two paths ending `external` at two library calls are still one end
    # to every reader that deduplicates them, as before it existed.
    made_by: tuple[str, int] | None = dataclass_field(default=None, compare=False)


@dataclass(frozen=True)
class ParameterValues:
    """What a parameter's `def` evaluates for it (D00 §5a, N1): its `default` and its
    `annotation_value`, each an entry of the argument grammar, and `body`, the method whose
    frame resolves them (`defining_body`): None where the naming rule names two."""

    body: str | None
    default: Mapping[str, Any] | None
    annotation: Mapping[str, Any] | None


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
    # Each entry is `(caller, ordinal, argument)`: the site and WHICH of its arguments is
    # the parameter. For a call that is the parameter's own index; for an instance lambda's
    # capture it is one past it, the site's first argument being the body's `this` (`OI-266`).
    callers: dict[tuple[str, int], tuple[tuple[str, int, int], ...]]
    # Every method's declared PARAMETER NAMES, by symbol — what a hole in a template is
    # named after (`_joined`). The compiler records them (`local_variable_names`), the
    # signature carries them, and a position with no recorded name is `None` rather than a
    # guess: a jar compiled without them is a real case and an invented `arg0` would read as
    # a name the author wrote.
    parameters: dict[str, tuple[str | None, ...]]
    # `field_writes.value`: a binding -> every CONSTANT written into it, as argument-grammar
    # entries (`OI-138` cause 2), each with the method that wrote it where the fact names
    # one. Separate from `writers` below because there is no crossing to make: the value is
    # in the fact, and `_binding` answers with it rather than resolving a parameter in
    # another method's frame. The writer is kept for one question only: whether the write
    # is a constructor's, which every instance gets (`_binding`'s unseen-object rule).
    constants: dict[str, tuple[tuple[str | None, Mapping[str, Any]], ...]]
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
    # The fields the facts mark `static`, as bare descriptors: one value for every reader,
    # so `_binding`'s unseen-object rule (OI-222) never applies to them.
    static_fields: frozenset[str] = frozenset()
    # The `(owner, method)` of every call whose body was not scanned — a library call. The
    # unseen-object rule declares them to the producer reader, so an object a library call
    # HANDS BACK (`List.get`, a mapper) ends at that call rather than at `external`: only an
    # object that arrives from no code at all is from outside.
    unscanned: frozenset[tuple[str, str]] = frozenset()
    # Every method that writes a field -> the call sites that call it, `(caller, ordinal)`,
    # off `call_edges`. A field read on one object answers a setter's write only where the
    # setter was called on that object (`_Walk._object_writes`), so it needs the CALLS of a
    # writer, which `callers` holds only for one that binds a parameter: a setter writing a
    # constant (`useDefault() { cron = "…"; }`) has none there.
    called_at: Mapping[str, tuple[tuple[str, int], ...]] = dataclass_field(default_factory=dict)
    # Which constructions a getter's receiver can be (`_Walk._objects`), per (type, site,
    # reads in progress) and the calling context as far as the walk read it, for as long as
    # this index lives. The answer reads nothing but the index, and every site resolved asks
    # it again: on `apollo-portal` one run asked 1,243 times for 463 distinct walks, each a
    # full walk (GUIDELINES §8.7).
    objects: dict[Any, Any] = dataclass_field(default_factory=dict, compare=False, repr=False)
    # Every type some call site here constructs (`owner` of an `<init>` site), read off
    # `sites`. A receiver can be a construction of a type only where one is in this set, so a
    # read of a field whose type nothing here builds is not walked for its objects at all:
    # every end of that walk would be no construction.
    constructed: frozenset[str] = dataclass_field(init=False, compare=False, repr=False)
    # Each type's direct superclass, as bare symbols (the `superclasses` query).
    superclasses: Mapping[str, str] = dataclass_field(default_factory=dict)
    # Every type -> the types in `constructed` that extend it, at any depth: a receiver of
    # the type can be a construction of one of them (`_Walk._objects`).
    constructed_below: Mapping[str, frozenset[str]] = dataclass_field(
        init=False, compare=False, repr=False
    )
    # **Where a value is HANDED to another method** (spec 2026-11-02 rules 1-3, `_Walk._window`),
    # read off the projected rows, so a slot here is the callee's parameter (the module
    # docstring's invariant): (method, value id) -> `(ordinal, slot)` of every argument whose
    # `source` is the value, and (method, parameter index) -> the same for an argument of kind
    # `parameter`. A slot the site's own descriptor types as one a callee cannot change
    # (`_UNCHANGEABLE`) is left out: it is not a hand-off.
    handed: Mapping[tuple[str, int], tuple[tuple[int, int], ...]] = dataclass_field(
        default_factory=dict
    )
    handed_parameters: Mapping[tuple[str, int], tuple[tuple[int, int], ...]] = dataclass_field(
        default_factory=dict
    )
    # (method, parameter index) -> the ordinals of calls made ON that parameter
    # (`receiver_parameter`): the calls a body the value was handed to makes on it.
    parameter_receivers: Mapping[tuple[str, int], tuple[int, ...]] = dataclass_field(
        default_factory=dict
    )
    # (caller, ordinal) -> every body `call_edges` resolves the site to, in its own order. A
    # site with none is absent: code this module does not have.
    callees: Mapping[tuple[str, int], tuple[str, ...]] = dataclass_field(default_factory=dict)
    # The bodies this workspace read that have NO normal return (review 3, m2): a method with
    # call sites of its own — a throw is one — and no `method_return` fact, by bare symbol.
    # Its callers' own facts read a call to it as one that returns; it never does.
    never_return: frozenset[str] = frozenset()
    # `(writer, value id)` and `(writer, parameter index)` for every field write of that value
    # (`field_writes.value.source`, `field_writes.from_parameter`): once in a field, anything
    # can change it.
    stored: frozenset[tuple[str, int]] = frozenset()
    stored_parameters: frozenset[tuple[str, int]] = frozenset()
    # (method, value id) and (method, parameter index) -> the ordinals of calls the value
    # reaches BELOW the top level of an argument — an array element, a merge candidate (fix
    # round 1, M3). Such a call cannot be followed per element, so it ends the path.
    nested: Mapping[tuple[str, int], tuple[int, ...]] = dataclass_field(default_factory=dict)
    nested_parameters: Mapping[tuple[str, int], tuple[int, ...]] = dataclass_field(
        default_factory=dict
    )
    # A value id's own type as the facts state it, in the JVM's spelling: what the call that
    # produced it is declared to return, or the type a construction built (M1).
    value_types: Mapping[tuple[str, int], str] = dataclass_field(default_factory=dict)
    # Every method's declared parameter types, as erased symbols (`Parameter.erased_symbol`),
    # positionally — the type a parameter value has (M1, M4).
    parameter_types: Mapping[str, tuple[str | None, ...]] = dataclass_field(default_factory=dict)
    # (method, owner type) -> the ordinals of instance calls whose receiver the facts cannot
    # name (no `receiver`, `receiver_parameter` or `receiver_field`): a value merged on a branch
    # — a parameter reassigned with a default — loses its id as a receiver (M4), so such a call
    # on the held value's own type may be a call on it.
    unread_receivers: Mapping[tuple[str, str], tuple[int, ...]] = dataclass_field(
        default_factory=dict
    )
    # (capturing method, capture site ordinal, argument slot) -> (lambda body, its parameter):
    # the capture fold's own mapping (OI-150/OI-266), read forwards (M6).
    captured_as: Mapping[tuple[str, int, int], tuple[str, int]] = dataclass_field(
        default_factory=dict
    )
    # The types a lambda or method reference in this module implements (the return type of a
    # `dynamic` site naming a body): `dispatch` lists no such body as a candidate, so a call
    # through one of these types reaches bodies `call_edges` does not name (M5).
    lambda_types: frozenset[str] = frozenset()
    # The owner classes whose calls take a value WITHOUT handing it off (`Catalog
    # .not_hand_offs`, the user's ruling of 2026-11-02): a compiler's own null checks, which
    # the compiler rather than the author writes and which only test for null and throw. A
    # call to one is no hand-off and no `nested` one; every other call, to any owner, is.
    not_hand_offs: frozenset[str] = frozenset()
    # The hand-offs a catalog states the effect of (`Catalog.hand_off_effects`, spec
    # 2026-11-02 rule 7), as `(owner, name, descriptor, slot)` in the site's own spelling. A
    # value handed to one is not `escapes`: the statement says which part of it the call
    # binds, and that it changes nothing else, so the path goes on with the call recorded.
    stated: frozenset[tuple[str, str, str, int]] = frozenset()
    # Where a stated call hands the value on to an interface method a module may implement
    # (`hand_off_effects`' `hands_to`, spec 2026-11-02 rule 7 as ruled for a listener): per
    # stated hand-off, the module's bodies of that method with the parameter the value lands
    # on, or None where they cannot be listed (a subtype whose method resolves to no body
    # read here). Read as a lambda's capture is (`_Walk._captured`).
    stated_hands: Mapping[tuple[str, str, str, int], tuple[tuple[str, int], ...] | None] = (
        dataclass_field(default_factory=dict)
    )
    # The recipe the container gives each parameter it fills, `(method, index)` -> the
    # `Injection` (`beans.injected_parameters`, spec 2026-11-05 di-recipe-hop §2), read from
    # every bean model. `_parameter` reads it before `callers`.
    injected: Mapping[tuple[str, int], Injection] = dataclass_field(default_factory=dict)
    # Which method a call can run (`resolve/dispatch.py`), for the two questions the facts of
    # one file leave to the resolver (spec 2026-11-06 §3b): what a call whose owner is bound
    # from its receiver returns (`_Walk._bound_returns`), and which type a binding nothing
    # writes names (`_Walk._named_type`). None, neither is asked and the walk reads as before.
    dispatch: Dispatch | None = dataclass_field(default=None, compare=False, repr=False)
    # **Arguments are bound to parameters by NAME as well as by position** (ruling R2, spec
    # 2026-11-06 §3a) where the module's calls may name them: a keyword argument fills the
    # callee's parameter of that name, positional ones fill parameters in order. True for a
    # module whose lookup rule is `c3`; every JVM argument is positional, slot for slot, so
    # there the slot IS the parameter and nothing below is consulted.
    by_name: bool = False
    # Every method's and constructor's parameters as a call fills them, `(name, kind)` in
    # order (D00 §5a `Parameter.kind`), by symbol: what `argument_slots` binds by. A
    # constructor is here as a method is — `Svc(Session())` fills `Svc.__init__`'s `s`.
    call_parameters: Mapping[str, tuple[tuple[str | None, str | None], ...]] = dataclass_field(
        default_factory=dict
    )
    # The methods and constructors that take a `self` the receiver fills (`modifiers.static`
    # false), and the calls made through a class rather than an instance (`_class_receivers`):
    # such a call to such a method hands `self` as its first argument (`call_slots`).
    instance_methods: frozenset[str] = frozenset()
    class_receivers: frozenset[tuple[str, int]] = frozenset()
    # What a stated library call does with one of its arguments (`Catalog.returns_arguments`,
    # design 2026-11-06-reading-decorators §3d/§3e), `(owner, name)` -> `(form, position)`:
    # `returns`, `result_returns` or `result_calls` of its argument at that position. Read by
    # `_Walk._stated_value`; empty, nothing is stated and the walk reads as before.
    stated_returns: Mapping[tuple[str, str], tuple[str, int]] = dataclass_field(
        default_factory=dict
    )
    # The return type each method of a `c3` module declares (`signature.returns`), by bare
    # descriptor, as the fact writes it; a method two facts declare differently has none.
    # Read only by the type reader (`_Walk._declared_answers`). Empty for a JVM module, whose
    # calls the facts own.
    declared_returns: Mapping[str, Mapping[str, Any]] = dataclass_field(default_factory=dict)
    # The type each field of a `c3` module declares (a class-level annotation, `client:
    # HttpClient`, or a module-level one), by bare field symbol, as the fact writes it
    # (`signature.returns`). Read only by the type reader (`_Walk._declared_field`).
    declared_fields: Mapping[str, Mapping[str, Any]] = dataclass_field(default_factory=dict)
    # Each class's type parameters by name, in order (D00 §5a `type_parameters`), and its
    # written parents with their type arguments (`supertype`, `generic_interfaces`), by bare
    # class symbol, for a `c3` module: what a generic class's parameters are on a subclass
    # (`class ProductRepository(RepositoryBase[Product])`), across files (`_Walk._mapping`).
    class_parameters: Mapping[str, tuple[str, ...]] = dataclass_field(default_factory=dict)
    # Each parameter's written type, `(method, index)` (D00 §5 numbering), for a `c3` module:
    # the type reader answers with it on a path the parameter's callers leave open
    # (`_Walk._open_filled`).
    declared_parameters: Mapping[tuple[str, int], Mapping[str, Any]] = dataclass_field(
        default_factory=dict
    )
    generic_bases: Mapping[str, tuple[Mapping[str, Any], ...]] = dataclass_field(
        default_factory=dict
    )
    # Each parameter that writes a `default` or an `annotation_value`, `(method, index)` (D00
    # §5a, N1): what an unfilled argument passes (`_Walk._default`) and what
    # `parameter_markers` reads. Empty for a JVM module, whose parameters write neither.
    parameter_values: Mapping[tuple[str, int], ParameterValues] = dataclass_field(
        default_factory=dict
    )
    # `parameter_markers`' answer for this index, once built (ruling R14): its one entry, or
    # none yet. Emptied with the index each binding round.
    markers: list[Any] = dataclass_field(default_factory=list, compare=False, repr=False)
    # What each parameter's markers were read through that a binding round can change, by
    # `(method, index)`, built with `markers` and emptied with it.
    marker_reads: dict[tuple[str, int], frozenset[Any]] = dataclass_field(
        default_factory=dict, compare=False, repr=False
    )
    # What each generator yields (`method_return.yielded`, plan 2026-11-08 N10), by method, in
    # `returned_values`' form: read only where a framework hands a parameter what a recipe
    # yields (`_Walk._recipe_runs`). Empty for a JVM module.
    yielded_values: Mapping[str, tuple[tuple[int, Mapping[str, Any]], ...]] = dataclass_field(
        default_factory=dict
    )
    # Each function and method of a `c3` module by the name it binds, `(owner, name)` -> bare
    # descriptors: what the call reader answers a read of that name with where nothing else
    # writes it (`_Walk._binding`). Empty for a JVM module, whose names a `def` binds none.
    named_functions: Mapping[tuple[str, str], tuple[str, ...]] = dataclass_field(
        default_factory=dict
    )
    # The calls that name the recipe a parameter is filled with (`beans.recipe_calls`, N5,
    # ruling R14), read at walk time beside the parameter's callers (`_Walk._parameter`).
    recipes: RecipeCalls = dataclass_field(default_factory=RecipeCalls)
    # `recipe_values`' answer per recipe call, for as long as this lives. Emptied with the
    # index each binding round.
    recipes_read: dict[Any, Any] = dataclass_field(default_factory=dict, compare=False, repr=False)
    # `_Walk._mapping`'s answers, per class, for as long as this lives.
    mappings: dict[str, dict[str, dict[str, Mapping[str, Any]]] | None] = dataclass_field(
        default_factory=dict, compare=False, repr=False
    )
    # `argument_slots`' answers, per (caller, ordinal, callee), for as long as this lives.
    slots_memo: dict[Any, Any] = dataclass_field(default_factory=dict, compare=False, repr=False)
    # **Each parameter's and each binding's paths upward, once** (ruling R39, OI-324 part 2
    # round 2): `(reader, position, frames)` -> the paths from that position to where they end,
    # each with its answer, computed on the empty path and joined onto every path that reaches
    # the position (`_Walk._resolve`). Shared by every site a reader walks over this index. A
    # binding round keeps the ones its new edges cannot change (`suffixes_kept`).
    suffixes: dict[Any, tuple["_Reached", ...]] = dataclass_field(
        default_factory=dict, compare=False, repr=False
    )
    # What each `suffixes` entry read that a binding round can change (`_Walk._depends`): the
    # callers of a method, the callees of a site, whether a site reached a body, the calls of a
    # writer. Kept beside the entry, so a round drops only the entries its edges change.
    suffix_deps: dict[Any, frozenset[Any]] = dataclass_field(
        default_factory=dict, compare=False, repr=False
    )
    # `declared_classes_of`'s answers, by the written reference's identity (the reference kept
    # beside its answer, so an identity is never read for another), for as long as this lives.
    declared_memo: dict[int, tuple[Any, tuple[str, ...]]] = dataclass_field(
        default_factory=dict, compare=False, repr=False
    )
    # `_Walk._namespace`'s answers, per field symbol, for as long as this lives.
    namespaces: dict[str, tuple[tuple[str, ...], bool]] = dataclass_field(
        default_factory=dict, compare=False, repr=False
    )

    def argument_slots(self, caller: str, ordinal: int, callee: str) -> tuple[int, ...]:
        """For each of `callee`'s parameters, the argument slot of the call at
        `(caller, ordinal)` that fills it, or `UNFILLED` where none can be said to (R2,
        `parameter_slots`), and for every parameter of a callee whose parameters are not
        known. Slot for slot where arguments are not bound by name."""
        key = (caller, ordinal, callee)
        found = self.slots_memo.get(key)
        if found is None:
            site = self.sites.get((caller, ordinal))
            arguments = (site or {}).get("arguments") or []
            declared = self.call_parameters.get(callee)
            if not self.by_name:
                found = tuple(range(len(arguments)))
            elif declared is None:
                found = ()
            else:
                found = call_slots(
                    arguments,
                    declared,
                    (caller, ordinal) in self.class_receivers and callee in self.instance_methods,
                )
            self.slots_memo[key] = found
        return found

    def argument_slot(self, caller: str, ordinal: int, callee: str, parameter: int) -> int:
        """`argument_slots` for one parameter: `UNFILLED` past the end."""
        slots = self.argument_slots(caller, ordinal, callee)
        if not self.by_name and parameter >= len(slots):
            return parameter
        return slots[parameter] if 0 <= parameter < len(slots) else UNFILLED

    def parameter_of(self, caller: str, ordinal: int, callee: str, slot: int) -> int | None:
        """The parameter of `callee` the argument at `slot` of that call fills, or None
        where it fills none that can be named (an extra keyword, a `**` mapping)."""
        if not self.by_name:
            return slot
        slots = self.argument_slots(caller, ordinal, callee)
        return slots.index(slot) if slot in slots else None

    def __post_init__(self) -> None:
        constructed = frozenset(
            str(row.get("owner")) for row in self.sites.values() if row["name"] == "<init>"
        )
        object.__setattr__(self, "constructed", constructed)
        below: dict[str, set[str]] = {}
        for built in constructed:
            seen = {built}
            ancestor = self.superclasses.get(built)
            while ancestor is not None and ancestor not in seen:
                seen.add(ancestor)
                below.setdefault(ancestor, set()).add(built)
                ancestor = self.superclasses.get(ancestor)
        object.__setattr__(
            self, "constructed_below", {key: frozenset(value) for key, value in below.items()}
        )


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


# A parameter no argument of a call can be said to fill (`ValueIndex.argument_slots`).
UNFILLED = -1
# The `keyword` D00 §5 writes on an argument unpacked from a mapping (`f(**options)`) and
# from a sequence (`f(*items)`).
_UNPACKED_MAPPING = "**"
_UNPACKED_SEQUENCE = "*"


def parameter_slots(
    arguments: Sequence[Mapping[str, Any]],
    parameters: Sequence[tuple[str | None, str | None]],
) -> tuple[int, ...]:
    """Which argument slot fills each parameter, `(name, kind)` in order (ruling R2 and the
    user's ruling A of 2026-11-06), by Python's calling rule (D00 §5a `Parameter.kind`):

    - the positional arguments fill the `positional_only` and `positional` parameters in
      order, and the extra ones go to the `var_positional` parameter;
    - a keyword fills the `positional` or `keyword_only` parameter of its name, and one naming
      none goes to the `var_keyword` parameter;
    - after a `*` argument (an unpacked sequence) no later positional argument's place is
      known, and a `**` argument (an unpacked mapping) may fill any parameter not yet filled.

    `UNFILLED` for every parameter none of this decides: one left to its default, one only
    an unpacked argument may fill, and a `var_positional` or `var_keyword` parameter (it holds
    what is left over, not one argument). A parameter with no kind fills by place, as a JVM
    one does."""
    filled = [UNFILLED] * len(parameters)
    by_place = [
        position
        for position, (_, kind) in enumerate(parameters)
        if kind in (None, "positional_only", "positional")
    ]
    by_name = {
        name: position
        for position, (name, kind) in enumerate(parameters)
        if name is not None and kind in (None, "positional", "keyword_only")
    }
    placed = 0
    unpacked_sequence = False
    for slot, entry in enumerate(arguments):
        keyword = entry.get("keyword")
        if keyword == _UNPACKED_SEQUENCE:
            unpacked_sequence = True
        elif keyword is None:
            if not unpacked_sequence and placed < len(by_place):
                filled[by_place[placed]] = slot
            placed += 1
        elif keyword != _UNPACKED_MAPPING:
            position = by_name.get(str(keyword))
            if position is not None and filled[position] == UNFILLED:
                filled[position] = slot
    return tuple(filled)


def unpacked_may_fill(arguments: Sequence[Mapping[str, Any]], kind: str | None) -> bool:
    """Whether a call's unpacked argument may fill a parameter of `kind` that no written
    argument fills (`parameter_slots`' `UNFILLED`), by Python's calling rule: a `*` value fills
    positional places, so a `positional_only` or `positional` parameter; a `**` mapping fills
    names, so a `positional` or `keyword_only` one. Where one may, the call does not leave the
    parameter to its default."""
    keywords = {entry.get("keyword") for entry in arguments}
    by_place = kind in ("positional_only", "positional") and _UNPACKED_SEQUENCE in keywords
    by_name = kind in ("positional", "keyword_only") and _UNPACKED_MAPPING in keywords
    return by_place or by_name


def held_at_end(body: str, entry: Mapping[str, Any]) -> Mapping[str, Any]:
    """A call row holding one argument, `entry`, a value of `body`'s frame, at the end of
    `body`, where no call of it sits: for a reader of a value no call is handed, such as a
    parameter's default (`parameter_markers`), to read it through `producer_paths`. A `def`
    runs after its defaults are made, so the `escapes` window is the rest of the body, as
    `_Walk._default` reads the same value."""
    return {"caller": body, "ordinal": _END_OF_BODY, "arguments": [entry]}


# The method a body-level `lambda` or nested function is named after where that method is a
# module or class body (`static`) or a constructor (`new`) (D00 §5a, M03).
_NAMED_AFTER = {"static": "<clinit>", "new": "<init>"}
_LAMBDA = "lambda$"


def defining_body(symbol: str, declared: AbstractSet[str]) -> str | None:
    """The method whose body runs the `def` of method `symbol`, and so evaluates its default
    and its annotation (D00 §5a, ruling R15), read from the naming rule D00 §5a and M03 state:

    - a name with no `$` is a module function or a method: its owner's `<clinit>` (the module
      or the class body);
    - `outer$inner` is a function nested in `outer`: `outer`;
    - `lambda$<method>$<n>` is a lambda in `<method>`: `<method>`.

    A Python name holds no `$`, so the split is exact. `static` and `new` name a body
    (`<clinit>`, `<init>`), and a function may also be named `static` or `new`: where both
    are `declared`, the body is not known and the answer is None."""
    if owner_of(bare_descriptor(symbol)) is None:
        return None
    name = method_name(symbol)
    if name.startswith(_LAMBDA):
        outer = name.removeprefix(_LAMBDA).rpartition("$")[0]
    elif "$" in name:
        outer = name.rpartition("$")[0]
    else:
        return with_method_name(symbol, "<clinit>")
    named = [
        with_method_name(symbol, one)
        for one in dict.fromkeys((_NAMED_AFTER.get(outer, outer), outer))
    ]
    found = [one for one in named if one in declared]
    return found[0] if len(found) == 1 else None


# The slot an argument reference names where an unpacked `*`/`**` value may be the argument
# (`argument_slot`): no argument the code writes can be said to be it. Not `UNFILLED`'s
# value, so a slot read from one is never taken for the other (`parameter_of`).
UNPACKED_SLOT = -2
# What a read at `UNPACKED_SLOT` says, for the reader that reports it (design
# 2026-11-06-reading-decorators §3a).
UNPACKED_DETAIL = "the argument may come from an unpacked `*`/`**` value"


def argument_slot(arguments: Sequence[Mapping[str, Any]], reference: Any) -> int | None:
    """Which written argument a catalog's argument reference names (design
    2026-11-06-reading-decorators §3a, approved): its index in `arguments`, None where the
    call writes no such argument, or `UNPACKED_SLOT` where an unpacked value may be it.

    A reference is a position `N` (an integer, or the capture spelling `argN`), `{keyword:
    name}`, or `{arg: N, keyword: name}` — Python's rule for a parameter that is positional or
    named: position N where the call writes more than N positional arguments, else the keyword.

    - A position counts the POSITIONAL arguments only. The facts write a call's positional
      arguments first, then its keyword ones (ruling R27), so counting every argument read
      `True` for `arg1` of `option("--dry-run", is_flag=True)`. A JVM argument has no
      `keyword`, so there a position is the index, as before.
    - A `*` argument at or before the position may hold it, and a missing keyword may be in a
      `**` argument: `UNPACKED_SLOT` for both."""
    position, keyword = _reference_parts(reference)
    if position is not None:
        placed = 0
        for slot, entry in enumerate(arguments):
            written = entry.get("keyword")
            if written == _UNPACKED_SEQUENCE:
                return UNPACKED_SLOT
            if written is None:
                if placed == position:
                    return slot
                placed += 1
        if keyword is None:
            return None
    if keyword is None:
        return None
    mapping = False
    for slot, entry in enumerate(arguments):
        written = entry.get("keyword")
        if written == keyword:
            return slot
        mapping = mapping or written == _UNPACKED_MAPPING
    return UNPACKED_SLOT if mapping else None


def _reference_parts(reference: Any) -> tuple[int | None, str | None]:
    """`(position, keyword)` of a reference already checked at load (`argument_reference`)."""
    if isinstance(reference, Mapping):
        position = reference.get("arg")
        return (None if position is None else int(position)), str(reference["keyword"])
    if isinstance(reference, str):
        return int(reference.removeprefix("arg")), None
    return int(reference), None


def argument_reference(value: Any, *, spelled: bool) -> Any:
    """`value` if it is an argument reference a catalog may write, else None: `argN` where
    `spelled` (a capture's spelling) or an integer where not (a `*_arg` key's), or either
    mapping form `{keyword: name}` / `{arg: N, keyword: name}` (design
    2026-11-06-reading-decorators §3a). A mapping with any other key, a keyword that is not an
    identifier, or a position that is not a non-negative integer is no reference."""
    if isinstance(value, Mapping):
        keyword, position = value.get("keyword"), value.get("arg", 0)
        if (
            set(value) <= {"arg", "keyword"}
            and isinstance(keyword, str)
            and keyword.isidentifier()
            and isinstance(position, int)
            and not isinstance(position, bool)
            and position >= 0
        ):
            return value
        return None
    if spelled:
        return value if isinstance(value, str) and re.fullmatch(r"arg\d+", value) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def reset_value_index() -> None:
    """Drops every cached index, so a resolve never answers from facts a previous one
    loaded.

    The weak keys above make this unnecessary for CORRECTNESS across objects — an entry
    dies with its workspace — but a single workspace REUSED for two resolves, with facts
    reloaded in between, is the same object and would keep the first resolve's index.
    `pipeline.resolve` calls this before `load_facts` for that case.
    """
    _INDEX_BY_WORKSPACE.clear()


def cached_value_index(
    workspace: Workspace,
    not_hand_offs: Sequence[str] = (),
    hand_off_effects: Sequence[Mapping[str, Any]] = (),
    bean_models: Mapping[str, Mapping[str, Any]] | None = None,
    value_annotations: Sequence[str] = (),
    returns_arguments: Sequence[Mapping[str, Any]] = (),
) -> "ValueIndex":
    """`value_index`, built at most once per workspace per resolve.

    Every engine that resolves values should ask for this rather than `value_index`
    directly: the fold is the same, and three engines times N catalogs each paid for it
    separately before.
    """
    index = _INDEX_BY_WORKSPACE.get(workspace)
    if index is None:
        index = value_index(
            workspace,
            not_hand_offs,
            hand_off_effects,
            bean_models,
            value_annotations,
            returns_arguments=returns_arguments,
        )
        _INDEX_BY_WORKSPACE[workspace] = index
    return index


def value_index(
    workspace: Workspace,
    not_hand_offs: Sequence[str] = (),
    hand_off_effects: Sequence[Mapping[str, Any]] = (),
    bean_models: Mapping[str, Mapping[str, Any]] | None = None,
    value_annotations: Sequence[str] = (),
    returns_arguments: Sequence[Mapping[str, Any]] = (),
) -> ValueIndex:
    """The index for one resolve. Built by `resolve_site` when it is not handed one.

    `not_hand_offs` is the catalogs' `not_hand_offs` (every catalog carries the same tuple):
    the owners whose calls take a value without handing it off. Empty, every call that takes
    a value is a hand-off. `hand_off_effects` is the catalogs' `hand_off_effects` (spec
    2026-11-02 rule 7): the hand-offs whose effect a catalog states (`ValueIndex.stated`).
    `bean_models` and `value_annotations` are the catalogs' (`Catalog.bean_models`,
    `Catalog.value_annotations`, the same on every catalog): what each container-filled
    parameter receives (`ValueIndex.injected`). None, no parameter is container-filled.
    `returns_arguments` is the catalogs' (`Catalog.returns_arguments`): the library calls
    that hand back one of their arguments (`ValueIndex.stated_returns`)."""
    sites: dict[tuple[str, int], Mapping[str, Any]] = {}
    receivers: dict[tuple[str, int], list[int]] = {}
    # The PROJECTION, not the raw fact stream — the rows every engine reads (spec
    # 2026-09-19 §3), and the same rows `call_edges` derived every `bound_to_parameter`
    # edge's callee from. Reading the raw list beside a projected callee answered the
    # bridge's receiver for the sibling's parameter 0; the module docstring has the
    # measurement and the invariant.
    shapes = _Shapes(not_hand_offs=frozenset(not_hand_offs))
    parameter_receivers: dict[tuple[str, int], list[int]] = {}
    for row in effective_call_sites(workspace):
        method, ordinal = str(row["caller"]), int(str(row["ordinal"]))
        sites[(method, ordinal)] = row
        if row["receiver"] is not None:
            receivers.setdefault((method, int(str(row["receiver"]))), []).append(ordinal)
        if row.get("receiver_parameter") is not None:
            parameter_receivers.setdefault(
                (method, int(str(row["receiver_parameter"]))), []
            ).append(ordinal)
        _record_hand_offs(row, method, ordinal, shapes)

    producers: dict[tuple[str, int], list[int]] = {}
    returns: dict[tuple[str, int], list[tuple[int, str]]] = {}
    callers: dict[tuple[str, int], list[tuple[str, int, int]]] = {}
    writers: dict[str, list[tuple[str, int]]] = {}
    dispatch = workspace.once(dispatch_of)
    # A module whose calls may name their arguments binds them by name (R2), from the edges
    # and the callees' parameter names below, never slot for slot.
    by_name = dispatch.lookup == "c3"
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
        elif kind == "bound_to_parameter" and not by_name:
            parameter = (str(edge["to_symbol"]), int(str(edge["to_index"])))
            callers.setdefault(parameter, []).append(
                (method, int(str(edge["to_ordinal"])), parameter[1])
            )
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
    # are those values in order. **The captures are the site's LAST `captures` arguments**
    # (`OI-266`): an instance body's capture site hands `this` first, and `this` becomes the
    # body's receiver rather than its parameter 0 — D00's `captures` is the site's argument
    # count minus one for exactly that body. So body parameter *i* is argument
    # *i + (arguments - captures)*: *i* for a static body, *i + 1* for an instance one. Taking
    # *i* for both bound every value an instance lambda closed over to its neighbour's
    # parameter; vertx-examples' `sqlclient` published `POST /products` as answered by
    # `handleGetProduct`, at `resolved`.
    #
    # Parameters at or past the capture count are NOT bound here and must not be: those are
    # the lambda's own arguments, handed in by whoever invokes it, and `external` is the true
    # answer for them. A bound method reference (`captures` 0) binds none: its one argument
    # is the receiver.
    for (method, _), site in sites.items():
        for captured in _captures(site["arguments"]):
            # The entry names its body BARE, and every index here is keyed on full symbols.
            # The body is declared in the same class as the method that captured it, so its
            # coordinates are that method's — exact, where a bare-to-full map would be
            # ambiguous the moment two modules declare the same descriptor.
            body = with_descriptor(method, str(captured["symbol"]))
            count = int(str(captured["captures"]))
            source = captured.get("source")
            if count <= 0 or source is None:
                continue
            for maker in producers.get((method, int(str(source))), ()):
                bound = (sites.get((method, maker)) or {}).get("arguments") or []
                receiver = max(len(bound) - count, 0)
                for position in range(min(count, len(bound))):
                    callers.setdefault((body, position), []).append(
                        (method, maker, receiver + position)
                    )
                    shapes.captured_as[(method, maker, receiver + position)] = (body, position)

    parameters: dict[str, tuple[str | None, ...]] = {}
    parameter_types: dict[str, tuple[str | None, ...]] = {}
    call_parameters: dict[str, tuple[tuple[str | None, str | None], ...]] = {}
    instance_methods: set[str] = {
        str(row["symbol"]) for row in workspace.query("constructor_declarations")
    }
    for row in workspace.query("method_declarations"):
        modifiers = row.get("modifiers")
        if isinstance(modifiers, dict) and modifiers.get("static") is False:
            instance_methods.add(str(row["symbol"]))
    declared_parameters: dict[tuple[str, int], Mapping[str, Any]] = {}
    evaluated: dict[tuple[str, int], tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]] = {}
    for row in (
        *workspace.query("method_declarations"),
        *workspace.query("constructor_declarations"),
    ):
        declared = row.get("signature")
        parsed = json.loads(str(declared)) if isinstance(declared, str) else declared
        if isinstance(parsed, dict) and by_name:
            for position, entry in enumerate(parsed.get("parameters") or []):
                held = entry.get("type") if isinstance(entry, dict) else None
                if isinstance(held, dict):
                    declared_parameters[(str(row["symbol"]), position)] = held
        if isinstance(parsed, dict):
            for position, entry in enumerate(parsed.get("parameters") or []):
                if not isinstance(entry, dict):
                    continue
                default, annotation = entry.get("default"), entry.get("annotation_value")
                if isinstance(default, dict) or isinstance(annotation, dict):
                    evaluated[(str(row["symbol"]), position)] = (
                        default if isinstance(default, dict) else None,
                        annotation if isinstance(annotation, dict) else None,
                    )
        if isinstance(parsed, dict):
            call_parameters[str(row["symbol"])] = tuple(
                (
                    position.get("name") if isinstance(position.get("name"), str) else None,
                    position.get("kind") if isinstance(position.get("kind"), str) else None,
                )
                for position in parsed.get("parameters") or []
                if isinstance(position, dict)
            )
    declared_returns: dict[str, Mapping[str, Any] | None] = {}
    for row in workspace.query("method_declarations"):
        declared = row.get("signature")
        if declared is None:
            continue
        parsed = json.loads(str(declared)) if isinstance(declared, str) else declared
        if not isinstance(parsed, dict):
            continue
        if by_name:
            bare = bare_descriptor(str(row["symbol"]))
            written = parsed.get("returns")
            written = written if isinstance(written, dict) else None
            if bare in declared_returns and declared_returns[bare] != written:
                written = None
            declared_returns[bare] = written
        named: list[str | None] = []
        typed: list[str | None] = []
        for position in parsed.get("parameters") or []:
            found = position.get("name") if isinstance(position, dict) else None
            named.append(str(found) if isinstance(found, str) and found else None)
            erased = position.get("erased_symbol") if isinstance(position, dict) else None
            typed.append(str(erased) if isinstance(erased, str) and erased else None)
        parameters[str(row["symbol"])] = tuple(named)
        parameter_types[str(row["symbol"])] = tuple(typed)

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
    constants: dict[str, list[tuple[str | None, Mapping[str, Any]]]] = {}
    produced: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    stored: set[tuple[str, int]] = set()
    stored_parameters: set[tuple[str, int]] = set()
    for row in workspace.query("field_writes"):
        _record_store(row, stored, stored_parameters)
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
            writer = row.get("written_by")
            constants.setdefault(str(row["field"]), []).append(
                (None if writer is None else str(writer), entry)
            )

    returned_values: dict[str, tuple[tuple[int, Mapping[str, Any]], ...]] = {}
    returning: set[str] = set()
    for row in workspace.query("method_returns"):
        returning.add(bare_descriptor(str(row["method"])))
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

    yielded_values: dict[str, tuple[tuple[int, Mapping[str, Any]], ...]] = {}
    for row in workspace.query("method_yields"):
        text = row["value"]
        entry = None if text is None else json.loads(str(text))
        if isinstance(entry, dict):
            method = str(row["method"])
            yielded_values[method] = yielded_values.get(method, ()) + (
                (int(str(row["ordinal"])), entry),
            )

    edges = [row for row in workspace.query("call_edges") if row["callee"] is not None]
    class_receivers = (
        _class_receivers(sites, dispatch, writers, constants, produced) if by_name else frozenset()
    )
    if by_name:
        bind_by_name(callers, edges, sites, call_parameters, instance_methods, class_receivers)
    reached = frozenset((str(row["caller"]), int(str(row["ordinal"]))) for row in edges)
    writing = (
        {method for entries in writers.values() for method, _ in entries}
        | {str(writer) for entries in constants.values() for writer, _ in entries if writer}
        | {writer for entries in produced.values() for writer, _ in entries}
    )
    called_at: dict[str, list[tuple[str, int]]] = {}
    callees: dict[tuple[str, int], list[str]] = {}
    for row in edges:
        callees.setdefault((str(row["caller"]), int(str(row["ordinal"]))), []).append(
            str(row["callee"])
        )
        if str(row["callee"]) in writing:
            called_at.setdefault(str(row["callee"]), []).append(
                (str(row["caller"]), int(str(row["ordinal"])))
            )
    field_rows = list(workspace.query("fields"))
    static_fields = frozenset(
        bare_descriptor(str(row["symbol"])) for row in field_rows if row["static"]
    )
    declared_fields: dict[str, Mapping[str, Any] | None] = {}
    for row in field_rows if by_name else ():
        written = row.get("returns")
        written = json.loads(str(written)) if isinstance(written, str) else written
        written = written if isinstance(written, dict) else None
        bare = bare_descriptor(str(row["symbol"]))
        if bare in declared_fields and declared_fields[bare] != written:
            written = None
        declared_fields[bare] = written
    unscanned = frozenset(
        (str(row.get("owner")), str(row["name"]))
        for key, row in sites.items()
        if key not in reached and row.get("owner") is not None
    )
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
        static_fields=static_fields,
        unscanned=unscanned,
        called_at={key: tuple(value) for key, value in called_at.items()},
        superclasses={
            bare_descriptor(str(row["symbol"])): bare_descriptor(str(row["superclass"]))
            for row in workspace.query("superclasses")
        },
        handed={key: tuple(value) for key, value in shapes.handed.items()},
        handed_parameters={key: tuple(value) for key, value in shapes.handed_parameters.items()},
        parameter_receivers={key: tuple(value) for key, value in parameter_receivers.items()},
        callees={key: tuple(value) for key, value in callees.items()},
        never_return=frozenset(bare_descriptor(method) for method, _ in sites) - returning,
        stored=frozenset(stored),
        stored_parameters=frozenset(stored_parameters),
        nested={key: tuple(value) for key, value in shapes.nested.items()},
        nested_parameters={key: tuple(value) for key, value in shapes.nested_parameters.items()},
        value_types=shapes.value_types,
        parameter_types=parameter_types,
        unread_receivers={key: tuple(value) for key, value in shapes.unread_receivers.items()},
        captured_as=shapes.captured_as,
        lambda_types=frozenset(shapes.lambda_types),
        not_hand_offs=shapes.not_hand_offs,
        stated=frozenset(
            (str(e["owner"]), str(e["method"]), str(e["descriptor"]), int(e["arg"]))
            for e in hand_off_effects
        ),
        stated_hands=_stated_hands(workspace, hand_off_effects, shapes.lambda_types),
        injected=(
            {}
            if bean_models is None
            else injected_parameters(workspace, bean_models, value_annotations)
        ),
        dispatch=dispatch,
        by_name=by_name,
        call_parameters=call_parameters,
        instance_methods=frozenset(instance_methods),
        class_receivers=class_receivers,
        stated_returns={
            (str(entry["owner"]), str(entry["method"])): (str(entry["form"]), int(entry["arg"]))
            for entry in returns_arguments
        },
        declared_returns={key: value for key, value in declared_returns.items() if value},
        declared_fields={key: value for key, value in declared_fields.items() if value},
        class_parameters=_class_parameters(workspace) if by_name else {},
        declared_parameters=declared_parameters,
        generic_bases=_generic_bases(workspace) if by_name else {},
        parameter_values={
            key: ParameterValues(defining_body(key[0], call_parameters.keys()), *values)
            for key, values in evaluated.items()
        },
        yielded_values=yielded_values,
        named_functions=_named_functions(dispatch) if by_name else {},
        recipes=recipe_calls(bean_models),
    )


def _named(bare: str) -> tuple[str, str]:
    """A field or a method as `(owner, name)`, the name a `def` binds."""
    return (str(owner_of(bare)), method_name(bare))


def _named_functions(dispatch: Dispatch) -> dict[tuple[str, str], tuple[str, ...]]:
    """`ValueIndex.named_functions`: every method the module declares a body for, by the name
    its `def` binds, sorted (NFR-1)."""
    found: dict[tuple[str, str], list[str]] = {}
    for method in sorted(dispatch.bodies):
        found.setdefault(_named(method), []).append(method)
    return {key: tuple(value) for key, value in found.items()}


def named_type(symbol: str, dispatch: Dispatch | None) -> str | None:
    """`_Walk._named_type`'s rule, for a reader with no walk: the type a binding declared as
    no field names, where it names one the workspace declares or holds a header for."""
    bare = bare_descriptor(symbol)
    if dispatch is None or bare in dispatch.scanned:
        return None
    named = field_type(bare)
    if named is None or (named not in dispatch.scanned and named not in dispatch.headers):
        return None
    return named


def call_slots(
    arguments: Sequence[Mapping[str, Any]],
    parameters: Sequence[tuple[str | None, str | None]],
    through_class: bool,
) -> tuple[int, ...]:
    """`parameter_slots` for one call. A method called THROUGH ITS CLASS — `Base.__init__(self,
    x)`, `H.use(h, x)` — is handed its `self` as the first positional argument, which the
    declaration does not list (the receiver takes it on an instance call): so the call fills
    a leading `self` first, and the rest of the rule is unchanged."""
    if through_class:
        return parameter_slots(arguments, ((None, "positional_only"), *parameters))[1:]
    return parameter_slots(arguments, parameters)


def _class_receivers(
    sites: Mapping[tuple[str, int], Mapping[str, Any]],
    dispatch: Dispatch,
    writers: Mapping[str, Any],
    constants: Mapping[str, Sequence[tuple[str | None, Mapping[str, Any]]]],
    produced: Mapping[str, Any],
) -> frozenset[tuple[str, int]]:
    """The calls made through a CLASS rather than an instance: a `static` call naming an
    owner (to an instance method only where the class is the owner — a module function is
    `static` itself), and a `virtual` one whose receiver is a name that is a class on every
    write (`named_type`): an import used as a value, or one bound to classes on branches."""

    def names_classes(field: str) -> bool:
        if writers.get(field) or produced.get(field):
            return False
        written = constants.get(field, ())
        if not written:
            return named_type(field, dispatch) is not None
        return all(
            entry.get("kind") == "field"
            and entry.get("symbol") is not None
            and named_type(str(entry["symbol"]), dispatch) is not None
            for _, entry in written
        )

    return frozenset(
        key
        for key, site in sites.items()
        if (site.get("invoke_kind") == "static" and site.get("owner") is not None)
        or (
            site.get("invoke_kind") == "virtual"
            and site.get("receiver_field") is not None
            and names_classes(str(site["receiver_field"]))
        )
    )


def bind_by_name(
    callers: dict[tuple[str, int], list[tuple[str, int, int]]],
    edges: Sequence[Mapping[str, Any]],
    sites: Mapping[tuple[str, int], Mapping[str, Any]],
    parameters: Mapping[str, tuple[tuple[str | None, str | None], ...]],
    instance_methods: AbstractSet[str],
    class_receivers: AbstractSet[tuple[str, int]],
) -> None:
    """`bound_to_parameter` where arguments are bound by name (R2): each edge's callee's
    parameters, each with the argument slot `parameter_slots` says fills it, or `UNFILLED`
    — a caller whose call fills that parameter with nothing the walk can name, which it
    answers `not_readable` on that path rather than with a neighbour's value. A callee whose
    parameter names are not known binds none. One entry per (call, callee), in the edges'
    order, as `value_edges` orders `bound_to_parameter`; a `dynamic` site binds none there."""
    seen: set[tuple[str, int, str]] = set()
    for row in edges:
        if str(row["invoke_kind"]) == "dynamic":
            continue
        caller, ordinal, callee = str(row["caller"]), int(str(row["ordinal"])), str(row["callee"])
        if (caller, ordinal, callee) in seen:
            continue
        seen.add((caller, ordinal, callee))
        declared = parameters.get(callee)
        site = sites.get((caller, ordinal))
        if declared is None or site is None:
            continue
        slots = call_slots(
            site.get("arguments") or [],
            declared,
            (caller, ordinal) in class_receivers and callee in instance_methods,
        )
        for position, slot in enumerate(slots):
            callers.setdefault((callee, position), []).append((caller, ordinal, slot))


def _stated_hands(
    workspace: Workspace,
    hand_off_effects: Sequence[Mapping[str, Any]],
    lambda_types: AbstractSet[str],
) -> dict[tuple[str, str, str, int], tuple[tuple[str, int], ...] | None]:
    """`ValueIndex.stated_hands`: for each stated hand-off whose entry says the call hands the
    value on (`hands_to`), every body this module has of each named interface method, with
    the parameter the value lands on — found as the JVM would dispatch it, per in-module
    subtype of the interface (`Dispatch.resolve`). None where one cannot be listed: a subtype
    whose method resolves to no body read here, or a type a lambda in the module implements
    (whose body `dispatch` does not list, fix round 1 M5). Built only where an entry names a
    `hands_to`, so a source stating none reads no dispatch here (§8.7)."""
    found: dict[tuple[str, str, str, int], tuple[tuple[str, int], ...] | None] = {}
    named = [e for e in hand_off_effects if e.get("hands_to")]
    if not named:
        return found
    dispatch = workspace.once(dispatch_of)
    for effect in named:
        bodies: list[tuple[str, int]] = []
        listed = True
        for handed in effect["hands_to"]:
            owner, name, descriptor = (
                str(handed["owner"]),
                str(handed["method"]),
                str(handed["descriptor"]),
            )
            if owner in lambda_types:
                listed = False
            for subtype in dispatch.subtypes.get(bare_descriptor(owner), ()):
                declaring, _ = dispatch.resolve(subtype, name, descriptor)
                read = (
                    ()
                    if declaring is None
                    else dispatch.bodies.get(method_descriptor(declaring, name, descriptor), ())
                )
                if not read:
                    listed = False
                bodies.extend((body, int(handed["arg"])) for body in read)
        key = (str(effect["owner"]), str(effect["method"]), str(effect["descriptor"]))
        found[(*key, int(effect["arg"]))] = tuple(dict.fromkeys(bodies)) if listed else None
    return found


@dataclass
class _Shapes:
    """What `_record_hand_offs` gathers from the projected rows, one pass, for `ValueIndex`."""

    handed: dict[tuple[str, int], list[tuple[int, int]]] = dataclass_field(default_factory=dict)
    handed_parameters: dict[tuple[str, int], list[tuple[int, int]]] = dataclass_field(
        default_factory=dict
    )
    nested: dict[tuple[str, int], list[int]] = dataclass_field(default_factory=dict)
    nested_parameters: dict[tuple[str, int], list[int]] = dataclass_field(default_factory=dict)
    value_types: dict[tuple[str, int], str] = dataclass_field(default_factory=dict)
    unread_receivers: dict[tuple[str, str], list[int]] = dataclass_field(default_factory=dict)
    captured_as: dict[tuple[str, int, int], tuple[str, int]] = dataclass_field(default_factory=dict)
    lambda_types: set[str] = dataclass_field(default_factory=set)
    not_hand_offs: frozenset[str] = frozenset()


def _record_hand_offs(row: Mapping[str, Any], method: str, ordinal: int, shapes: _Shapes) -> None:
    """One projected site's contribution to the hand-off maps `ValueIndex` describes.

    A top-level argument naming a value (`source`) or a parameter is a hand-off to the
    callee's parameter at that slot. The parameter's type is read off THIS row's descriptor,
    which the projection keeps in step with its argument list (a bridge row carries the
    sibling's descriptor beside the sibling's slots), so slot *i* is descriptor parameter *i*.
    A slot the descriptor does not reach is kept as a hand-off: nothing says it cannot be
    changed. A `lambda` argument's `source` is the lambda object, not a value a reader asks
    about, and is left out.

    A value or parameter BELOW the top level — an element of an `array`, a candidate of a
    `merge` — is a `nested` hand-off: whatever the callee does with it cannot be followed per
    element."""
    descriptor = row.get("descriptor")
    if row.get("result") is not None and descriptor:
        shapes.value_types[(method, int(str(row["result"])))] = returned_slot(str(descriptor))
    owner = str(row.get("owner"))
    if row["name"] == "<init>" and row.get("receiver") is not None:
        shapes.value_types.setdefault((method, int(str(row["receiver"]))), slot_of_type(owner))
    if row.get("invoke_kind") == "dynamic" and row.get("implementation") and descriptor:
        implemented = returned_type(str(descriptor))
        if implemented is not None:
            shapes.lambda_types.add(implemented)
    if (
        row.get("invoke_kind") not in ("static", "dynamic")
        and row["name"] != "<init>"
        and row.get("receiver") is None
        and row.get("receiver_parameter") is None
        and row.get("receiver_field") is None
    ):
        shapes.unread_receivers.setdefault((method, slot_of_type(owner)), []).append(ordinal)
    # The user's ruling of 2026-11-02: a call to an owner the catalogs declare in
    # `not_hand_offs` (a compiler's null checks) takes the value without handing it off.
    if owner in shapes.not_hand_offs or owner + str(row["name"]) in shapes.not_hand_offs:
        return
    arguments = row["arguments"] or []
    slots: tuple[str, ...] | None = None
    for slot, argument in enumerate(arguments):
        for inner in _nested_entries(argument):
            if inner.get("source") is not None and inner.get("kind") != "lambda":
                shapes.nested.setdefault((method, int(str(inner["source"]))), []).append(ordinal)
            elif inner.get("kind") == _PARAMETER and inner.get("value") is not None:
                shapes.nested_parameters.setdefault((method, int(str(inner["value"]))), []).append(
                    ordinal
                )
        if argument.get("kind") == "lambda":
            continue
        source = argument.get("source")
        parameter = argument.get("value") if argument.get("kind") == _PARAMETER else None
        if source is None and parameter is None:
            continue
        if slots is None:
            slots = descriptor_slots(str(descriptor))[0] if descriptor else ()
        if slot < len(slots) and slots[slot] in _UNCHANGEABLE:
            continue
        if source is not None:
            shapes.handed.setdefault((method, int(str(source))), []).append((ordinal, slot))
        else:
            shapes.handed_parameters.setdefault((method, int(str(parameter))), []).append(
                (ordinal, slot)
            )


def _nested_entries(argument: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Every argument-grammar entry BELOW `argument` itself — array elements, merge
    candidates, at any depth."""
    found: list[Mapping[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            found.append(value)
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    for inner in argument.values():
        walk(inner)
    return found


def _record_store(
    row: Mapping[str, Any], stored: set[tuple[str, int]], stored_parameters: set[tuple[str, int]]
) -> None:
    """One `field_writes` row into `ValueIndex.stored` / `.stored_parameters`: the writer and
    the value id or parameter it stored. A row naming no writer stores nothing anyone can
    place."""
    writer = row.get("written_by")
    if writer is None:
        return
    if row.get("from_parameter") is not None:
        stored_parameters.add((str(writer), int(str(row["from_parameter"]))))
    written = row.get("value")
    entry = json.loads(str(written)) if isinstance(written, str) else written
    if isinstance(entry, dict) and entry.get("source") is not None:
        stored.add((str(writer), int(str(entry["source"]))))


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
    branches: bool = True,
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

    `branches` False answers a branch between literals `non_enumerable` rather than
    `narrowed` (`_Walk.__init__` says which reader needs that).

    Returns one `Binding` per coherent path, in a deterministic order (NFR-1): the first
    slot's paths drive the outer order, and each slot's answers arrive in the edge query's
    own ordering. An empty list means no path answers every slot at once, which is the
    M-1 ruling taken to its end — the combination a per-position walk would have invented
    is not a row here.
    """
    fold = index if index is not None else value_index(workspace)
    walk = _Walk(fold, identities, branches=branches)
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
    within: "Path | None" = None,
    branches: bool = True,
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

    `within` is a path another read took (`producer_paths`), and every answer here must
    agree with it: the positions are read as further steps of THAT path. A cron read where
    a trigger was built, within the path the trigger took to the call that scheduled it,
    is the cron of that one scheduling.

    `branches` is `resolve_site`'s.
    """
    return [
        answers
        for _, answers in resolve_positions_on_paths(
            workspace, positions, index, identities, within, branches
        )
    ]


def resolve_positions_on_paths(
    workspace: Workspace,
    positions: Mapping[str, tuple[Mapping[str, Any], int | str]],
    index: ValueIndex | None = None,
    identities: "Identities" = (),
    within: "Path | None" = None,
    branches: bool = True,
) -> list[tuple["Path", dict[str, Answer]]]:
    """`resolve_positions`, each dict with the path it was read on, for a reader that reads
    another value later on that same path (`resolve_positions(..., within=)`): a router's
    held prefix and a route's verb list one factory call gives (plan 2026-11-08 Task 6)."""
    fold = index if index is not None else value_index(workspace)
    walk = _Walk(fold, identities, branches=branches)
    combined: list[tuple[_Trail, dict[str, Answer]]] = [
        (within.trail if within is not None else (), {})
    ]
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
    entered = within.entered if within is not None else frozenset()
    return [(Path(trail, entered), answers) for trail, answers in combined]


def producers_of(
    index: ValueIndex,
    site: Mapping[str, Any],
    slot: int | str,
    declared: AbstractSet[tuple[str, str]],
    along_receivers: bool = False,
    past_accessors: Ancestors | None = None,
    configuring: AbstractSet[tuple[str, str, str]] = frozenset(),
    stop_at_parameters_of: AbstractSet[str] = frozenset(),
    counting: Counting = None,
    read_sites: AbstractSet[tuple[str, int]] = frozenset(),
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

    **`along_receivers` reads the whole CHAIN of declared calls instead** (Quartz spec
    2026-10-28 §3b). A builder is a chain — `cronSchedule(x).withMisfireHandling…()` — and
    its first call can be in another method than its last: a helper takes the builder as a
    parameter and calls one more step on it. So at a declared call the walk does not stop;
    it goes on through that call's RECEIVER, on the SAME path, and prepends the call to
    whatever the receiver reaches (`Producer.chain`). The path is what keeps the calling
    context: inside a helper the walk descended into, the helper's parameter is the argument
    at the call it came through, never every caller the helper has. And a branch whose every
    candidate is a declared call on one shared receiver passes through to that receiver
    (`_Walk._passed_through`), marked `inexact`.

    **`past_accessors` lets an ACCESSOR on the value past the `escapes` window** (Quartz fix
    rounds 2-3, 2026-10-29), for a reader whose whole question is WHICH CALL built the
    value: `jobDetail.getJobDataMap().put(k, v)` between `build()` and `scheduleJob` writes
    into the detail through the map it handed back, and that does not change which `build()`
    made it. `_Walk._accessor` has the rule; the value is the type hierarchy it needs
    (`Dispatch.ancestors`). None, the default, keeps every call in the window — the right
    answer for a reader that reads the producer's ARGUMENTS as what the value holds, which a
    write through a returned view can change.

    **`configuring` names the calls that return the object they were called on** (ruling 4,
    spec 2026-10-30), as `(owner, name, descriptor)` in the site's own spelling — the exact
    overload, since another overload of one name need not return its receiver. `tb = newTrigger();
    tb.withIdentity("x"); tb.build()` configures `tb` over three statements, and each such
    call is the same object handed back, so one made on the value between its producer and
    its use is not an `escapes`. The chain reader gathers each into `Producer.chain`, in
    ordinal order, after the chain of the call that produced the value, with what is called
    on its result in turn (`_Walk._configured_on`). A call after the use never joins: the
    window `_Walk._through` reads is the same one.

    **A path that ends at a parameter names it** (Vert.x spec 2026-10-30 §3b):
    `Producer.parameter` is the `(method, index)` an `external` end reached where nothing in
    the module binds it. **`stop_at_parameters_of` ends the walk at a parameter of a named
    method** instead of crossing to its callers, for a reader asking whether a value came
    from that parameter — a handler's context — rather than from where its callers got it.
    The stop is one set lookup per parameter crossing; empty, the default, stops nothing.

    **`read_sites` names the calls the reader reads itself**, by `(method, ordinal)`: a call
    made on the value, or handed it, that the reader folds by its own words (the forward
    chain walk's declared steps) opens no `escapes` window. Empty, the default, keeps every
    call in the window.

    `site` is projected first, for the reason `resolve_site` states. Identical ends are one
    record — two paths that reach the same call name the same call — and the record carries
    no path. The order is the walk's own (NFR-1).
    """
    walk = _Walk(
        index,
        declared=declared,
        along_receivers=along_receivers,
        past_accessors=past_accessors,
        configuring=configuring,
        stop_at_parameters_of=stop_at_parameters_of,
        parameters_apart=True,
        counting=counting,
        read_sites=read_sites,
    )
    site = index.sites.get((str(site["caller"]), int(str(site["ordinal"]))), site)
    found: list[Producer] = []
    for _, answer in walk.at(site, slot):
        if answer.kind == _PRODUCED:
            found.append(replace(answer.value, inexact=True) if answer.inexact else answer.value)
        elif answer.kind == UNRESOLVED:
            found.append(Producer(reason=answer.reason, parameter=answer.parameter))
        else:
            found.append(Producer(ended_at=answer))
    return tuple(dict.fromkeys(found))


@dataclass(frozen=True)
class Path:
    """One path a read took, as the coherence rule compares paths (`_combine`) — opaque to
    a caller, which only joins two (`joined`) or reads further within one
    (`resolve_positions(..., within=...)`)."""

    trail: "_Trail" = ()
    # The steps written for a call the path ENTERED a helper through (`_entered`), as
    # against a caller it crossed out to. Empty for every path but `producer_paths`'.
    entered: "frozenset[_Step]" = frozenset()

    def joined(self, other: "Path") -> "Path | None":
        """Both paths as one, or None where they made different choices somewhere."""
        merged = _combine(self.trail, other.trail)
        return None if merged is None else Path(merged, self.entered | other.entered)

    def entering(self, callee: str, caller: str, ordinal: int) -> "Path | None":
        """This path with one more choice made: that `callee` was run by the call at
        `(caller, ordinal)` — the step a descent into that call's return writes (`_entered`).
        None where the path already chose another call of `callee`."""
        step = _Step((_CALLER_OF, callee), f"{caller}@{ordinal}")
        merged = _combine(self.trail, (step,))
        return None if merged is None else Path(merged, self.entered | {step})

    def stated_by_frame(
        self,
    ) -> tuple[tuple[tuple[str, int, int, tuple[tuple[str, int], ...]], ...], ...]:
        """The hand-offs this path passed whose effect a catalog states (spec 2026-11-02
        rule 7, `ValueIndex.stated`), as `(caller, ordinal, slot, entered)`, grouped by the
        FRAME whose window met them, frames in the order the walk met them (review 2, N1).

        The walk runs backward: from the use it reads the use's own frame first, then the
        frame it crosses out to (a caller, through a parameter) or descends into (a call that
        returned the value), each of which RAN before the frame met just before it. Within a
        frame the window's calls are in their run order, a body a hand-off entered included.
        Which call ran first is the reader's to decide from this; the walk names no order.
        `entered` is the calls that entered the body the stated call is in, innermost first
        (review 2, C1): the frame its arguments are read in."""
        frames: list[list[tuple[str, int, int, tuple[tuple[str, int], ...]]]] = [[]]
        for step in self.trail:
            # A recipe's return the container hands a parameter (`_FILLED_BY`) is a frame of
            # its own, as a caller's or a callee's is.
            if step.context[0] in (_CALLER_OF, _RETURN_OF, _FILLED_BY):
                if frames[-1]:
                    frames.append([])
                continue
            if step.context[0] == _STATED:
                frames[-1].append(
                    (
                        str(step.context[1]),
                        int(step.context[2]),
                        int(step.context[3]),
                        tuple(step.context[4:]),
                    )
                )
        return tuple(tuple(frame) for frame in frames if frame)

    def entered_into(self, caller: str, ordinal: int) -> tuple[tuple[tuple[str, int], ...], ...]:
        """For a configuring call at `(caller, ordinal)` that this path gathered inside a body a
        hand-off entered, the calls that entered that body, innermost first — one tuple per
        time the path gathered it (a helper handed the value twice gathers its call twice).
        Empty where the path gathered it in no entered body. `entered_position` reads the
        call's argument through them (item 1's review, concern 6)."""
        return tuple(
            dict.fromkeys(
                tuple(step.context[3:])
                for step in self.trail
                if step.context[0] == _GATHERED and step.context[1:3] == (caller, ordinal)
            )
        )

    def ran_before(
        self,
        index: "ValueIndex",
        stated: tuple[str, int, int, tuple[tuple[str, int], ...]],
        use: tuple[str, int],
    ) -> bool:
        """Whether the stated call `stated` (`stated_by_frame`'s form) ran before the call at
        `use` on every path that reaches both, by the control-flow fact (spec 2026-11-02 rule
        9). False is undecided, never "after".

        - **In one method**, exactly when the call is on `use`'s `dominator` chain.
        - **Inside a body a hand-off entered** (`entered`), where it is `on_every_exit` there,
          and so on out to the hand-off in the frame this path read it in.
        - **In a caller this path crossed out to**, where it is on the `dominator` chain of
          the call that entered the method the use is in, or one enclosing it: everything that
          call ran comes after.
        - **Inside a callee whose return this path read**, where it is `on_every_exit` there
          and that callee's call ran before the use by these same rules.

        Anything else is undecided."""
        caller, ordinal, _, entered = stated
        point = (caller, ordinal)
        for outer in entered:
            if not _on_every_exit(index, *point):
                return False
            point = outer
        entering: dict[str, tuple[str, int]] = {}
        returned: dict[str, list[tuple[str, int]]] = {}
        for step in self.trail:
            if step.context[0] == _CALLER_OF:
                by, at = step.label.rsplit("@", 1)
                entering[str(step.context[1])] = (by, int(at))
            elif step.context[0] == _RETURN_OF:
                method, value = str(step.context[1]), int(step.context[2])
                callee = step.label.rsplit(" returns ", 1)[0]
                returned.setdefault(callee, []).extend(
                    (method, at)
                    for at, by in index.returns.get((method, value), ())
                    if by == callee
                )
        return _ran_before_use(index, point, use, entering, returned, set())

    def calls_out_of(self, method: str) -> tuple[int, ...]:
        """The ordinals of the calls in `method` that this path crossed into a callee through:
        where `method` hands the value on toward the end of the path. Empty where the path
        leaves `method` by no call (it reached the value through a return, or not at all)."""
        found: list[int] = []
        for step in self.trail:
            if step.context[0] != _CALLER_OF:
                continue
            by, at = step.label.rsplit("@", 1)
            if by == method and int(at) not in found:
                found.append(int(at))
        return tuple(found)

    def labels(self) -> tuple[str, ...]:
        """The path as `Binding.path` carries one: each crossing's label, outermost first."""
        return _path(self.trail)

    def crossed_out_of(self) -> tuple[str, ...]:
        """The methods this path crossed out of to one of their callers (`_Walk._parameter`),
        nearest first — never a helper it descended into, whose call is written as one
        (`entered`). A reader asking whether a calling context the module does not show could
        have run a method reads them (`resolve/receiver_binding.py`)."""
        return tuple(
            dict.fromkeys(
                str(step.context[1])
                for step in self.trail
                if step.context[0] == _CALLER_OF
                and step not in self.entered
                and step.label != _FRAMEWORK_CALL
            )
        )

    def filled_in(self) -> tuple[str, ...]:
        """The methods this path read a parameter of as the framework's call fills it (a recipe,
        plan 2026-11-08 N5), nearest first: it crossed out to no caller in the module, and still
        depends on the method's callers, which a later round may add beside it."""
        return tuple(
            dict.fromkeys(
                str(step.context[1])
                for step in self.trail
                if step.context[0] == _CALLER_OF and step.label == _FRAMEWORK_CALL
            )
        )

    def two_calls_of_one_helper(self, other: "Path") -> bool:
        """Whether the two paths disagree ONLY on which call entered a helper — each value
        handed back by its own call of one helper (`id(job)` beside `id(trigger)`), which one
        binding cannot hold (the M-1 bound) — rather than on a caller either crossed out
        to, which says they come from two different executions. False where they agree
        everywhere (`joined` answers then)."""
        chosen = {step.context: step for step in self.trail}
        clashes = [
            (chosen[step.context], step)
            for step in other.trail
            if step.context in chosen and chosen[step.context].label != step.label
        ]
        return bool(clashes) and all(
            mine in self.entered and theirs in other.entered for mine, theirs in clashes
        )


def _ran_before_use(
    index: "ValueIndex",
    point: tuple[str, int],
    use: tuple[str, int],
    entering: Mapping[str, tuple[str, int]],
    returned: Mapping[str, list[tuple[str, int]]],
    seen: set[tuple[str, int]],
) -> bool:
    """`Path.ran_before`'s rules for a call at `point`, given the calls that entered each
    method the path crossed out of (`entering`) and the calls whose return it read
    (`returned`, by callee)."""
    if point in seen:
        return False
    seen.add(point)
    method, ordinal = point
    if method == use[0]:
        chain = _dominators(index, *use)
        return chain is not None and ordinal in chain
    inner, crossed = use[0], {use[0]}
    while inner in entering:
        by, at = entering[inner]
        if by == method:
            chain = _dominators(index, by, at)
            return chain is not None and ordinal in chain
        if by in crossed:
            break
        inner = by
        crossed.add(by)
    calls = returned.get(method, [])
    return (
        len(set(calls)) == 1
        and _on_every_exit(index, *point)
        and _ran_before_use(index, calls[0], use, entering, returned, seen)
    )


def producer_paths(
    index: ValueIndex,
    site: Mapping[str, Any],
    slot: int | str,
    declared: AbstractSet[tuple[str, str]],
    along_receivers: bool = False,
    past_accessors: Ancestors | None = None,
    configuring: AbstractSet[tuple[str, str, str]] = frozenset(),
    stop_at_parameters_of: AbstractSet[str] = frozenset(),
    which_object: bool = False,
    counting: Counting = None,
    read_sites: AbstractSet[tuple[str, int]] = frozenset(),
    dropped: list[Producer] | None = None,
    functions: bool = False,
    declared_sites: AbstractSet[tuple[str, int]] = frozenset(),
    declared_types: bool = False,
    shared: Any = None,
    reads: set[Any] | None = None,
) -> tuple[tuple[Producer, Path], ...]:
    """`producers_of`, with the PATH each producer was reached by, one pair per distinct
    path — for a reader that goes on to read other positions on that same path.

    **A descent into a callee is written as the call that entered it.** The walk reaches
    a value a helper hands back by descending into the helper's return in the frame of the
    call it came through (`_Walk._value`); a read that starts INSIDE that helper crosses out
    of it through its callers (`_Walk._parameter`). The two name one choice — which call
    ran the helper — so the path carries both spellings, and a later read within it
    (`resolve_positions(..., within=)`) reaching the helper's parameter agrees only with the
    call the descent came through. A path that descends into ONE helper on two different
    calls cannot be held by one binding, which is the M-1 ruling's own bound; the path
    records which steps were written for an entry (`Path.entered`), so a reader can tell
    that bound from two paths through different callers (`Path.two_calls_of_one_helper`).

    **`which_object` is for a reader asking "which object is this"** (Vert.x spec 2026-10-30
    §3c), the object reader's own switch (`_Walk._objects`): a call made ON the value does not
    make it another object, so the `escapes` window does not apply — a router given its
    routes and then mounted is the router its producer made, routes and all. It ignores no
    call that hands back a DIFFERENT object: that object is the call's result, and a walk
    from it ends at that call, so the identity ends there. Off, the default, every reader
    keeps the window it had.

    `dropped`, where handed a list, receives the end of every path left out because it
    entered one helper through two of its calls — so a reader can tell a complete answer
    from one missing a path.

    `functions` is for the reader asking what a CALL of the value runs (ruling R29, task 9a
    fix round 2): a function value (`lambda`) ends its path as a `symbol` literal naming the
    function's body, the way a JVM functional interface's method on a lambda reaches the
    lambda's body. Off, the default, a function value is a body and not a value (ruled
    2026-09-22), as every other reader has it.

    `declared_sites` are stops by site, `(method, ordinal)`, beside `declared`'s by call: a
    call that makes an object its `(owner, name)` cannot name, as a `__call__` applying a
    group decorator makes a router (design 2026-11-06-reading-decorators §4).

    `declared_types` is for the reader asking a receiver's TYPE (OI-324 part 2): a call's
    result is what its callee's body returns, path by path, and on a return path the body
    answers with no type, or for a callee with no body, the type the method declares it
    returns (`Answer.declared`). Off, the default, a declaration is never read as a value.

    `reads`, where handed a set, receives every part of the index the walk read that a binding
    round can change (`_Walk._depends`), for a reader that keeps what it built on the answer."""
    walk = _Walk(
        index,
        declared=declared,
        along_receivers=along_receivers,
        past_accessors=past_accessors,
        which_object=which_object,
        configuring=configuring,
        stop_at_parameters_of=stop_at_parameters_of,
        parameters_apart=True,
        counting=counting,
        read_sites=read_sites,
        functions=functions,
        declared_sites=declared_sites,
        declared_types=declared_types,
        shared=shared,
    )
    if reads is not None:
        walk._deps.append(reads)
    site = index.sites.get((str(site["caller"]), int(str(site["ordinal"]))), site)
    found: list[tuple[Producer, Path]] = []
    for trail, answer in walk.at(site, slot):
        if answer.kind == _PRODUCED:
            producer = replace(answer.value, inexact=True) if answer.inexact else answer.value
        elif answer.kind == UNRESOLVED:
            producer = Producer(
                reason=answer.reason, parameter=answer.parameter, made_by=answer.made_by
            )
        else:
            producer = Producer(ended_at=answer)
        entered = _entered(trail, index)
        if entered is not None:
            found.append((producer, Path(entered, frozenset(entered) - frozenset(trail))))
        elif dropped is not None:
            # A path no `Path` can hold (one helper entered through two calls) is left out of
            # the answer; a caller that must know the answer is incomplete asks for these.
            dropped.append(producer)
    # Keyed with `made_by`, which is outside `Producer`'s equality: two paths ending at two
    # library calls are two ends to this reader (`_Walk._distinct`).
    return tuple({(pair, pair[0].made_by): pair for pair in found}.values())


def decorators_passed(
    index: ValueIndex, site: Mapping[str, Any], slot: int
) -> tuple[tuple[str, int], ...]:
    """The stated decorators a value at `site`'s argument `slot` passed through, nearest
    first, as `(method, ordinal)` of the call that made each (design
    2026-11-06-reading-decorators §3d): the calls `_Walk._stated_value` goes through by
    `result_returns`, read by the same rule — an argument made by a `__call__` in this method
    whose receiver a `result_returns` call made, then that `__call__`'s own argument. Ends at
    the first value made any other way (the function itself, module code, a library call no
    value model states), which the value walk reads on its own."""
    return _stated_decorators(index, site, slot)[0]


def undecorated_maker(
    index: ValueIndex, site: Mapping[str, Any], slot: int
) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    """The call that made the value the stated decorators at `site`'s argument `slot` were
    applied to (`decorators_passed`), where a call in this method made it, and the call that
    names it: the call itself, or, for a decorator applied with `__call__`, the call that made
    that decorator (`click/decorators#pass_context`). None where the value is the function
    itself or was not made by a call — for a reader naming in a detail what the walk ended at."""
    method = str(site["caller"])
    held = _stated_decorators(index, site, slot)[1]
    if held is None or held.get("source") is None or held.get("kind") == "lambda":
        return None
    made = index.producers.get((method, int(str(held["source"]))))
    row = index.sites.get((method, min(made))) if made else None
    if row is None:
        return None
    if row["name"] != _CALL or row.get("owner") is not None:
        return row, row
    receiver = row.get("receiver")
    makers = index.producers.get((method, int(str(receiver)))) if receiver is not None else None
    maker = index.sites.get((method, min(makers))) if makers else None
    return None if maker is None else (row, maker)


def _stated_decorators(
    index: ValueIndex, site: Mapping[str, Any], slot: int
) -> tuple[tuple[tuple[str, int], ...], Mapping[str, Any] | None]:
    """`decorators_passed`'s walk: the stated decorators, nearest first, and the argument it
    stopped at (None where there is none)."""
    method = str(site["caller"])
    found: list[tuple[str, int]] = []
    arguments = site["arguments"] or []
    held = arguments[slot] if 0 <= slot < len(arguments) else None
    while held is not None and held.get("source") is not None and held.get("kind") != "lambda":
        made = index.producers.get((method, int(str(held["source"]))))
        row = index.sites.get((method, min(made))) if made else None
        if row is None or row["name"] != _CALL or row.get("owner") is not None:
            break
        receiver = row.get("receiver")
        makers = index.producers.get((method, int(str(receiver)))) if receiver is not None else None
        maker = index.sites.get((method, min(makers))) if makers else None
        applied = (
            None
            if maker is None
            else index.stated_returns.get((str(maker.get("owner")), str(maker["name"])))
        )
        if maker is None or applied is None or applied[0] != _RESULT_RETURNS:
            break
        found.append((method, int(str(maker["ordinal"]))))
        at = argument_slot(row["arguments"] or [], applied[1])
        held = None if at is None or at == UNPACKED_SLOT else (row["arguments"] or [])[at]
    return tuple(found), held


def _entered(trail: "_Trail", index: ValueIndex) -> "_Trail | None":
    """`trail` with each descent into a callee's return also written as the caller crossing
    that call is (`producer_paths`); None where it entered one callee on two calls."""
    entered: _Trail = trail
    for step in trail:
        if step.context[0] != _RETURN_OF:
            continue
        method, value = step.context[1], step.context[2]
        callee = step.label.rsplit(" returns ", 1)[0]
        for ordinal, returned_by in index.returns.get((method, value), ()):
            if returned_by != callee:
                continue
            merged = _combine(entered, (_Step((_CALLER_OF, callee), f"{method}@{ordinal}"),))
            if merged is None:
                return None
            entered = merged
    return entered


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
# One path through the `escapes` window (`_Walk._window`): the choices it made at hand-offs
# with several callees, and either the configuring calls it gathered — `(method, ordinal)`, in
# the order they run — or the reason it ended (`escapes`, `cycle`).
_Window = tuple[_Trail, tuple[tuple[str, int], ...] | str]
# One thing done to a value in a window (`_Walk._events`, `Flow.paths`): its ordinal, the paths
# it takes (`_Window`s), and the configuring call whose result it is made on, None for one made
# on the value itself.
_Event = tuple[int, tuple[_Window, ...], int | None]


def _entered_through(steps: _Trail, method: str, ordinal: int) -> _Trail:
    """`steps`, read in a body a hand-off at `(method, ordinal)` entered, with that call
    added to each stated step's frame (`Path.stated`'s `entered`), outermost last — and to
    each split's (rule 9), so two calls of one helper choose apart whether its call ran, and to
    each gathered call's (`_GATHERED`), so its arguments are read through this call."""
    return tuple(
        _Step((*step.context, (method, ordinal)), step.label)
        if step.context[0] in (_STATED, _SPLIT, _GATHERED)
        else step
        for step in steps
    )


def _gathered_steps(body: str, outcome: tuple[tuple[str, int], ...] | str) -> _Trail:
    """A `_GATHERED` step for each call `body` itself gathered on one path through it, for
    `_entered_through` to name the call that entered `body`. A call gathered deeper already has
    its step, written where the hand-off into that deeper body was read."""
    if isinstance(outcome, str):
        return ()
    return tuple(
        _Step((_GATHERED, made_in, at), _GATHERED) for made_in, at in outcome if made_in == body
    )


def entered_position(
    index: ValueIndex,
    site: Mapping[str, Any],
    slot: int,
    entered: tuple[tuple[str, int], ...],
) -> tuple[Mapping[str, Any], int]:
    """Where a call's argument at `slot` is read when the call is inside a body a hand-off
    entered: at the call itself, or — while that argument is a parameter of the body the call
    is in, and the path records which call entered that body (`entered`, innermost first) — at
    that entering call's own argument, in ITS frame (review 2, C1; item 1's review, concern 6).
    So a helper called twice reads each call's own value. A stated call's `entered` comes from
    `Path.stated_by_frame`, a gathered call's from `Path.entered_into`."""
    for outer in entered:
        arguments = site["arguments"] or []
        argument = arguments[slot] if slot < len(arguments) else None
        if not isinstance(argument, Mapping) or argument.get("kind") != "parameter":
            break
        entering = index.sites.get(outer)
        if entering is None:
            break
        # The body's parameter, as the slot of the entering call that fills it (R2).
        filled = index.argument_slot(
            outer[0], outer[1], str(site["caller"]), int(argument["value"])
        )
        if filled == UNFILLED:
            break
        site, slot = entering, filled
    return site, slot


# The argument kinds whose fact IS the value, wherever it is written: two entries handing a
# call one of these alike hand it one value.
_STATED_KINDS = frozenset({"string", "int", "long", "boolean"})


def read_through_hand_off(
    index: ValueIndex, path: "Path", site: Mapping[str, Any], slot: int
) -> tuple[Mapping[str, Any], int] | None:
    """Where argument `slot` of a call `path` gathered is read (item 1's review, concern 6; the
    one rule both the options reader and the forward chain walk read, item 2 re-review): at the
    call itself where the path gathered it in no entered body; else at the argument the call
    that entered the body handed in (`entered_position`). Where the path entered the body more
    than once and the entries hand the call different arguments, which one this call ran with is
    not known: None, the argument unread. Entries handing it one stated value alike are one."""
    caller, ordinal = str(site["caller"]), int(str(site["ordinal"]))
    found: dict[tuple[str, str | None], tuple[Mapping[str, Any], int]] = {}
    for entered in path.entered_into(caller, ordinal) or ((),):
        at, at_slot = entered_position(index, site, slot, entered)
        arguments = at["arguments"] or []
        argument = arguments[at_slot] if at_slot < len(arguments) else None
        stated = (
            isinstance(argument, Mapping)
            and argument.get("kind") in _STATED_KINDS
            and argument.get("source") is None
        )
        key = (
            json.dumps(argument, sort_keys=True, default=str),
            None if stated else f"{at['caller']}@{at['ordinal']}",
        )
        found.setdefault(key, (at, at_slot))
    return next(iter(found.values())) if len(found) == 1 else None


def _dominators(index: ValueIndex, method: str, ordinal: int) -> frozenset[int] | None:
    """Every call in `method` that ran before the call at `ordinal` on EVERY path to it —
    its `dominator` chain (spec 2026-11-02 rule 9, D00 §5) — or None where the facts do not
    compute the call's position (no `on_every_exit`): undecided, never "every path"."""
    row = index.sites.get((method, ordinal))
    if row is None or row.get("on_every_exit") is None:
        return None
    chain: list[int] = []
    above = row.get("dominator")
    while above is not None:
        chain.append(int(str(above)))
        row = index.sites.get((method, chain[-1]))
        above = None if row is None else row.get("dominator")
    return frozenset(chain)


def several_or_unproven(splits: int, unproven: bool) -> bool:
    """Rule 9's "not claimed" (ruled by the user 2026-11-03, "A: every row partial"): a path
    with two or more calls on branches, or a side of a split no fact proves, is inexact
    (`partial`). The one statement of the rule, for the value walk (`_unsure`) and the forward
    chain walk (`shapes.chains`) alike."""
    return splits > 1 or unproven


def counts_split(parts: AbstractSet[str] | None, published: AbstractSet[str] | None) -> bool:
    """Whether a split whose call sets `parts` counts for a row publishing `published` (the
    user's ruling of 2026-11-03, option A): it does where it sets a part the row shows. Where
    either is not known — a reader that states no published parts, a call whose parts are not
    read — it counts, the conservative default."""
    return published is None or parts is None or bool(set(parts) & set(published))


def path_splits(path: "Path") -> int:
    """How many calls on branches a value walk's `path` split at that count for the reader it
    was walked for (`_counted`, decided at each split), a window that held two or more such
    (`_SEVERAL`) counting as two — for a reader adding its own splits to the path's.
    `split_sites` lists them all."""
    return _split_count(path.trail, counted_only=True)


def split_sites(path: "Path") -> int:
    """How many calls on branches a value walk's `path` split at, whatever they set — the
    count the path cap bounds."""
    return _split_count(path.trail, counted_only=False)


def inexact(path: "Path") -> bool:
    """Whether an answer on `path` is inexact by rule 9 (`_unsure`) — for a reader holding a
    path of its own, such as the forward chain walk's (`shapes.chains`)."""
    return _unsure(path.trail)


def _split_count(trail: _Trail, counted_only: bool) -> int:
    splits = len(
        {
            step.context
            for step in trail
            if step.context[0] == _SPLIT and (not counted_only or step.context[3])
        }
    )
    return splits + (2 if any(step.context[0] == _SEVERAL for step in trail) else 0)


def _counted(method: str, outcomes: "tuple[_Window, ...]", counting: Counting) -> bool:
    """Whether a split in `method` whose sides are `outcomes` counts for the reader's row (the
    user's ruling of 2026-11-03, option A; review 3 re-review 2, C-1): where the reader states
    no parts (`counting` None), always; else where some outcome gathers a call that sets a part
    the row shows, or ends in a reason (`escapes`, `cycle`, the cap), whose parts are not known.
    A hand-off into a body the walk read is so judged by the calls the body makes on the value,
    in whichever `method` they are, and one into code we do not have by its `escapes`."""
    if counting is None:
        return True
    return any(
        isinstance(gathered, str)
        or any(counting(made_in, ordinal) for made_in, ordinal in gathered)
        for _, gathered in outcomes
    )


def _unsure(path: _Trail) -> bool:
    """Whether an answer on `path` is inexact by rule 9 (`_Walk._window`).

    - **Two or more calls on branches anywhere on the PATH** (ruled by the user 2026-11-03,
      "A: every row partial", per path from the producer to the use — review 3, C1): the
      facts say whether a call is on every path, never which branch it is on, so the splits
      give every combination, including ones no run makes, whichever PUBLISHED parts the calls
      set (narrowed by the user's ruling of 2026-11-03, option A: a split that sets no part the
      reader's row publishes does not count, `_counted`) and whichever frames they are in. A
      window that held two or more counted splits itself is marked once (`_SEVERAL`).
    - **A side of a split the facts do not prove a run takes to the use** (`_UNPROVEN`)."""
    # One pass over the path: `_split_count(path, counted_only=True)` and the unproven test.
    splits: set[Any] = set()
    several = unproven = False
    for step in path:
        kind = step.context[0]
        if kind == _SPLIT:
            if step.context[3]:
                splits.add(step.context)
        elif kind == _SEVERAL:
            several = True
        elif kind == _UNPROVEN:
            unproven = True
    return several_or_unproven(len(splits) + (2 if several else 0), unproven)


def _post_dominators(index: ValueIndex, method: str, ordinal: int) -> list[int] | None:
    """Every call in `method` that runs after the call at `ordinal` on EVERY path from it to
    a normal return, nearest first — its `post_dominator` chain (rule 9, ruled by the user
    2026-11-03) — or None where the facts do not compute the call's position."""
    row = index.sites.get((method, ordinal))
    if row is None or row.get("on_every_exit") is None:
        return None
    chain: list[int] = []
    below = row.get("post_dominator")
    while below is not None:
        chain.append(int(str(below)))
        row = index.sites.get((method, chain[-1]))
        below = None if row is None else row.get("post_dominator")
    return chain


def _never_returns(index: ValueIndex, method: str, ordinal: int) -> bool:
    """Whether the call at `(method, ordinal)` names a body this workspace read that has no
    normal return (review 3, m2): its static target, as the call site spells it. A virtual
    call whose override does return is read the same way, which errs towards `partial`."""
    row = index.sites.get((method, ordinal))
    if row is None or not row.get("name") or not row.get("descriptor") or row["owner"] is None:
        return False
    target = method_descriptor(str(row["owner"]), str(row["name"]), str(row["descriptor"]))
    return target in index.never_return


def _reaches_return(index: ValueIndex, method: str, ordinal: int) -> bool:
    """Whether every path from the call at `(method, ordinal)` ends at a normal return (rule 9,
    ruled by the user 2026-11-03, option A); False where the facts do not say."""
    row = index.sites.get((method, ordinal))
    return row is not None and row.get("reaches_return") is True


def _on_every_exit(index: ValueIndex, method: str, ordinal: int) -> bool:
    """Whether the call at `(method, ordinal)` runs on every path to a normal return (rule 9);
    False where the facts do not say."""
    row = index.sites.get((method, ordinal))
    return row is not None and row.get("on_every_exit") is True


def _combine(left: _Trail, right: _Trail) -> _Trail | None:
    """The two paths as one, or None where they disagree — the coherence rule.

    Disagreement is per CONTEXT: two slots that both crossed out of `register` must have
    crossed through the same call. A context only one of them visited constrains nothing.
    """
    if not right:
        return left
    chosen = {step.context: step.label for step in left}
    visited = set(chosen)
    for step in right:
        if chosen.setdefault(step.context, step.label) != step.label:
            return None
    if not left:
        return right
    return left + tuple(step for step in right if step.context not in visited)


def _path(trail: _Trail) -> tuple[str, ...]:
    """The path a binding carries: the crossings, OUTERMOST FIRST. The walk discovers the
    nearest crossing first and the furthest last, so the record reads the way a reader
    follows it — from the call that started the chain down to the site in hand."""
    return tuple(step.label for step in reversed(trail))


def _call_of(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """A site's call as `configuring` names it: owner, name and descriptor, so one overload
    declared to return its receiver never stands for another."""
    return (str(row.get("owner")), str(row["name"]), str(row.get("descriptor")))


def _only(trail: _Trail, answer: Answer) -> tuple[_Reached, ...]:
    return ((trail, answer),)


def _unresolved(reason: str) -> Answer:
    return Answer(kind=UNRESOLVED, reason=reason)


def _class_parameters(workspace: Workspace) -> dict[str, tuple[str, ...]]:
    """Each class's type parameters by name, in order, by bare class symbol."""
    found: dict[str, tuple[str, ...]] = {}
    for row in workspace.query("type_parameters"):
        bare = bare_descriptor(str(row["symbol"]))
        written = row["type_parameters"]
        listed = json.loads(str(written)) if isinstance(written, str) else written
        if is_type_descriptor(bare) and isinstance(listed, list):
            found[bare] = tuple(str(one.get("name")) for one in listed if isinstance(one, Mapping))
    return found


def _generic_bases(workspace: Workspace) -> dict[str, tuple[Mapping[str, Any], ...]]:
    """Each class's written parents that carry type arguments, by bare class symbol."""
    found: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for row in workspace.query("generic_bases"):
        bases: list[Mapping[str, Any]] = []
        for column in ("supertype", "generic_interfaces"):
            written = row[column]
            parsed = json.loads(str(written)) if isinstance(written, str) else written
            for one in parsed if isinstance(parsed, list) else [parsed]:
                if isinstance(one, Mapping) and one.get("symbol"):
                    bases.append(one)
        found[bare_descriptor(str(row["symbol"]))] = tuple(bases)
    return found


def _substituted(
    written: Mapping[str, Any], mapping: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any]:
    """`written` with a type variable at its top, or as a member of its union, replaced by
    what `mapping` gives it; one `mapping` does not fill is left as it is."""
    symbol = str(written.get("symbol"))
    if symbol == _UNION:
        members = [
            _substituted(m, mapping)
            for m in written.get("arguments") or []
            if isinstance(m, Mapping)
        ]
        return {**written, "arguments": members}
    if not is_type_descriptor(symbol) and symbol in mapping:
        return mapping[symbol]
    return written


def declared_classes_of(index: ValueIndex, written: Mapping[str, Any]) -> tuple[str, ...]:
    """`_declared_classes` over `index`'s dispatch, kept per written reference for as long as
    the index lives (`ValueIndex.declared_memo`): the type reader asks it of one declaration on
    every path through it."""
    held = index.declared_memo.get(id(written))
    if held is not None and held[0] is written:
        return held[1]
    found = _declared_classes(written, index.dispatch)
    index.declared_memo[id(written)] = (written, found)
    return found


def _declared_classes(written: Mapping[str, Any], dispatch: Dispatch | None) -> tuple[str, ...]:
    """The classes a declared type reference (`TypeRef`, as a fact writes it) names: itself,
    or each member of a union, `None` aside. Empty where one names no class the workspace
    knows: `Any`, the root type every value is, a type variable, a type the file did not
    name, or a name no class of the module or type header carries (an alias another file
    assigns, `Logger = structlog.stdlib.BoundLogger`, is a field, not a class)."""
    if dispatch is None:
        return ()
    symbol = str(written.get("symbol"))
    members = (
        [str(m.get("symbol")) for m in written.get("arguments") or [] if isinstance(m, Mapping)]
        if symbol == _UNION
        else [symbol]
    )
    members = [m for m in members if m != _NONE]
    if not members or not all(
        is_type_descriptor(m)
        and m not in (_ANY, dispatch.root)
        and (m in dispatch.scanned or m in dispatch.headers)
        for m in members
    ):
        return ()
    return tuple(dict.fromkeys(members))


def bound_owner(answer: Answer) -> str | None:
    """The type a receiver answer binds a call to (spec 2026-11-06 §3b): a `symbol` literal
    naming a TYPE — the class a value was built from, or the class itself — and nothing
    else. A symbol naming a member is no owner."""
    if answer.kind != LITERAL or answer.literal_kind != SYMBOL:
        return None
    named = str(answer.value)
    return named if is_type_descriptor(named) else None


def called_function(answer: Answer) -> str | None:
    """The body a call of a function value runs (ruling R29): a `symbol` literal naming a
    METHOD, which only the call reader (`producer_paths(..., functions=True)`) answers a
    function value with. None for anything else, a type among them."""
    if answer.kind != LITERAL or answer.literal_kind != SYMBOL:
        return None
    named = str(answer.value)
    # A method descriptor ends with its parameter list: `app/a#f(sig_…).`.
    return named if named.endswith(").") else None


# The descriptor every Python method is called by (D00 §5a): its arguments are bound by name and
# position at the call, not by a written signature.
_ANY_ARGUMENTS = "(*)"
# The reader a recipe's value is read by (`recipe_values`): the call reader, its upward paths
# shared under this key.
_RECIPE_READER = "values:recipe"


def suffixes_kept(
    index: ValueIndex, changed: frozenset[Any]
) -> tuple[dict[Any, tuple["_Reached", ...]], dict[Any, frozenset[Any]]]:
    """The shared upward paths (`ValueIndex.suffixes`) a binding round keeps, with their reads:
    every entry that read none of `changed`, the round's new edges as reads (`(callers,
    method)`, `(callees, site)`, `(reached, site)`, `(called_at, writer)`). An entry built on
    another records that one's reads too, so a changed caller anywhere beneath drops it."""
    kept = {key: deps for key, deps in index.suffix_deps.items() if deps.isdisjoint(changed)}
    return {key: index.suffixes[key] for key in kept}, kept


def recipe_values(
    index: ValueIndex, site: Mapping[str, Any], parameter: tuple[str, int] | None
) -> tuple["_Reached", ...]:
    """The recipe a recipe call `site` names (`beans.RecipeCalls`, N5), one answer per path:
    its `recipe_arg` read by the call reader (`producer_paths(..., functions=True)`), so a
    function value names its body, a class is the class object and a construction its
    instance. A call handed no recipe, or `None`, names the type `parameter` is written to
    hold under `empty_recipe: parameter_type`, a class object each; `not_readable` where the
    parameter writes none, or the call's argument may be in an unpacked one. Read once per
    call and parameter for as long as `index` lives; a recipe whose value is read through
    itself is a `cycle`."""
    return _recipe_values(index, site, parameter)[0]


def _recipe_values(
    index: ValueIndex, site: Mapping[str, Any], parameter: tuple[str, int] | None
) -> tuple[tuple["_Reached", ...], frozenset[Any]]:
    """`recipe_values`, with what the reading read that a binding round can change."""
    key = (str(site["caller"]), int(str(site["ordinal"])), parameter)
    if key in index.recipes_read:
        held = index.recipes_read[key]
        return (
            cast(tuple[tuple[_Reached, ...], frozenset[Any]], held)
            if held is not None
            else ((((), _unresolved(CYCLE)),), frozenset())
        )
    index.recipes_read[key] = None
    reference = index.recipes.calls.get((str(site.get("owner")), str(site["name"])))
    slot = argument_slot(site["arguments"] or [], reference)
    found: list[_Reached] = []
    if slot == UNPACKED_SLOT:
        found.append(((), _unresolved(NOT_READABLE)))
    elif slot is None:
        found.extend(_parameter_type(index, parameter))
    reads: set[Any] = set()
    if slot is not None and slot != UNPACKED_SLOT:
        walk = _Walk(index, functions=True, shared=_RECIPE_READER)
        walk._deps.append(reads)
        for path, answer in walk.at(site, slot):
            if answer.kind == ABSENT and answer.null:
                found.extend((path, one) for _, one in _parameter_type(index, parameter))
            else:
                found.append((path, answer))
    held = (tuple(found), frozenset(reads))
    index.recipes_read[key] = held
    return held


def _parameter_type(index: ValueIndex, parameter: tuple[str, int] | None) -> tuple["_Reached", ...]:
    """`empty_recipe: parameter_type`'s recipe: each class `parameter` is written to hold, as
    the class object; `not_readable` where the rule is not declared or no class is written."""
    written = None if parameter is None else index.declared_parameters.get(parameter)
    classes = (
        _declared_classes(written, index.dispatch)
        if written is not None and index.recipes.empty == PARAMETER_TYPE
        else ()
    )
    if not classes:
        return (((), _unresolved(NOT_READABLE)),)
    return tuple(
        ((), Answer(kind=LITERAL, value=one, literal_kind=SYMBOL, class_object=True))
        for one in classes
    )


def recipe_runs(index: ValueIndex, answer: Answer) -> tuple[str, ...]:
    """The bodies calling the recipe value `answer` runs, by the call-of-a-value rules: a
    function its own body (ruling R29), a class its constructor by lookup order (ruling R37),
    an instance its class's `__call__` by lookup order. Empty where no such body was read."""
    dispatch = index.dispatch
    if dispatch is None:
        return ()
    function = called_function(answer)
    if function is not None:
        return tuple(dispatch.bodies.get(function, ()))
    owner = bound_owner(answer)
    if owner is None:
        return ()
    name = _INIT if answer.class_object else _CALL
    call: dict[str, object] = {
        "owner": owner,
        "name": name,
        "descriptor": _ANY_ARGUMENTS,
        "invoke_kind": "virtual",
    }
    return tuple(dispatch.candidates(call))


def recipe_bodies(
    index: ValueIndex, site: Mapping[str, Any], parameter: tuple[str, int] | None
) -> tuple[str, ...]:
    """Every body a recipe call `site` makes the framework run (`recipe_values`, then
    `recipe_runs`), each once, in the order its paths give them."""
    found: dict[str, None] = {}
    for _, answer in recipe_values(index, site, parameter):
        found.update(dict.fromkeys(recipe_runs(index, answer)))
    return tuple(found)


def _used_at(origin: _Position) -> int | None:
    """WHERE a value is used, which is what bounds the `escapes` window.

    A slot of a call site is a position in control flow (`ordinal`). A method's RETURN is
    not: `method_returns.ordinal` numbers the return instructions, not the call sites, so
    nothing there says which calls in that method ran before the `return`. `None` is that
    answer, and `_through` reads it as the whole tail of the method (T-6)."""
    return origin[2] if origin[0] == _SLOT else None


def _fills(answer: Answer) -> bool:
    """Whether a concatenation hole takes this answer's text: a string literal, or an
    expression that carries a `${…}` placeholder (a nested concat built one)."""
    if answer.kind == LITERAL:
        return answer.literal_kind == STRING
    return answer.kind == EXPRESSION and carries_expression(str(answer.value))


class Flow:
    """Rule 9's split and proof (spec 2026-11-02 rule 9, the user's rulings of 2026-11-02 and
    2026-11-03): the ONE place a reader asks whether a call on a value runs on every path to
    its use, whether it is in the use's window at all, and whether the facts prove a run takes
    each side of a split to the use. The value walk (`_Walk._window`) and the forward chain
    walk (`shapes.chains`) both call it; neither carries a copy (review 3, the forward walk's
    branch blindness).

    Built once per walk or per chain run over one `ValueIndex`; it keeps each use's
    `dominator` chain it has read."""

    def __init__(self, index: "ValueIndex") -> None:
        self._index = index
        self._chains: dict[tuple[str, int], frozenset[int] | None] = {}

    def reaches_use(
        self,
        method: str,
        held: tuple[str, int] | None,
        ordinal: int,
        used_at: int | None,
        in_body: bool,
    ) -> tuple[bool, bool]:
        """Whether the facts prove a run takes each side of a split at `ordinal` to the use:
        `(with the call, without it)` (rule 9, ruled by the user 2026-11-03, "A: add
        post_dominator"). The call is not on every path to the use, so a run reaches the use
        without it wherever the use is one place — a call (`used_at`) or the end of a body a
        hand-off entered, whose every normal return is the caller's next step. A run reaches it
        WITH the call only where every path from the call to a normal return passes the use:

        - **a call in this frame** (`used_at`): the use is on the call's `post_dominator` chain.
          `if (tls) { o.setPort(443); return; } use(o)` fails it, so that path is `partial`;
        - **the end of an entered body** (`in_body`): a normal return follows the call — proven
          by a `post_dominator` (a return is reachable and every such path passes it) or by
          `reaches_return` (every path ends at one; ruled by the user 2026-11-03, option A),
          which is what a setter with no call after it has;
        - **a call that never returns** (a body this workspace read with no normal return) on
          the way, before the use or anywhere on the chain, fails either: the method's own facts
          read it as a call that returns (review 3, m2);
        - **a RETURN of the value** (`used_at` None otherwise): that, and every normal return of
          the method returns the held value, so whichever return a run reaches is its use; the
          path without the call needs the second half too.

        - **a call AFTER the use by ordinal** (in the window only by the loop it shares with the
          use, `inside`) is never proven WITH: the ordinal order the window gathers in is not
          the run order across the back edge, so no proof read off it holds (review 3
          re-review, C-A).

        Where the facts do not compute the call's position, neither side is proven. `held` is
        what a RETURN use hands back; a reader whose use is always a call passes None."""
        if used_at is not None and ordinal > used_at:
            return False, True
        chain = _post_dominators(self._index, method, ordinal)
        # A call on the way that never returns (its body has no normal return) is a throw the
        # method's own facts cannot see (review 3, m2): no run gets past it.
        if used_at is not None:
            if chain is None or used_at not in chain:
                return False, True
            passed = chain[: chain.index(used_at)]
            return not any(_never_returns(self._index, method, at) for at in passed), True
        returns = (bool(chain) or _reaches_return(self._index, method, ordinal)) and not any(
            _never_returns(self._index, method, at) for at in chain or ()
        )
        if in_body or held is None:
            return returns, True
        every = self.returned_everywhere(method, held)
        return returns and every, every

    def returned_everywhere(self, method: str, held: tuple[str, int]) -> bool:
        """Whether every return of `method` hands back `held` — a value id, or a parameter."""
        kind, key = held
        entries = self._index.returned_values.get(method, ())
        return bool(entries) and all(
            (entry.get("source") == key and entry.get("kind") != "parameter")
            if kind == _VALUE
            else (entry.get("kind") == "parameter" and entry.get("value") == key)
            for _, entry in entries
        )

    def always(self, method: str, used_at: int | None) -> Callable[[int], bool]:
        """Whether a call at an ordinal of `method` runs on every path to the use (spec
        2026-11-02 rule 9): on the use's `dominator` chain, or, where the window runs to the
        end of the body (`used_at` None), `on_every_exit`. Undecided where the facts do not
        compute the position, which is "not on every path"."""
        if used_at is None:
            return lambda ordinal: _on_every_exit(self._index, method, ordinal)
        key = (method, used_at)
        if key not in self._chains:
            self._chains[key] = _dominators(self._index, method, used_at)
        chain = self._chains[key]
        return lambda ordinal: chain is not None and ordinal in chain

    def inside(self, method: str, after: int, used_at: int | None) -> Callable[[int], bool]:
        """Whether a call at an ordinal of `method` is in the window from after `after` to the
        use at `used_at` (None: the end of the body).

        **Ordinal order, and the loop** (rule 9, ruled by the user 2026-11-03, option A for
        review 3's M1). Between the producer and the use by ordinal is in the window. A call
        AFTER the use by ordinal is too where it shares the use's `loop_group`: it can run before
        a later run of the use — `for (…) { use(o); o.setPort(443); }` — so it is one more call
        on a branch for that use (it is never on the use's `dominator` chain, so it splits), and
        a path that ran it is never exact (`reaches_use`). **Also where the value is produced in
        that loop group** (review 3 re-review, M-A): nested loops are ONE group, so a producer in
        the outer loop shares the group with an inner loop whose later call reaches the next use
        on the same object, and the five facts cannot tell that from a value built again each
        time round — so the call stays in, its path `partial`, and nothing is dropped."""
        group = None if used_at is None else self.loop_group(method, used_at)

        def inside(ordinal: int) -> bool:
            if ordinal <= after:
                return False
            if used_at is None or ordinal < used_at:
                return True
            return (
                ordinal != used_at
                and group is not None
                and self.loop_group(method, ordinal) == group
            )

        return inside

    def loop_group(self, method: str, ordinal: int) -> int | None:
        """The `loop_group` of the call at `(method, ordinal)`, None where it is in no loop."""
        row = self._index.sites.get((method, ordinal))
        group = None if row is None else row.get("loop_group")
        return None if group is None else int(str(group))

    def paths(
        self,
        method: str,
        held: tuple[str, int] | None,
        events: "Sequence[_Event]",
        used_at: int | None,
        in_body: bool,
        counting: Counting = None,
        width: int = 1,
    ) -> "tuple[_Window, ...]":
        """Every path through `events` — what happens to one value in `method` between its
        producer and its use at `used_at` (None: the end of the body), in run order, each event
        `(ordinal, outcomes, parent)` — as `(choices, gathered calls or the reason it ended)`.
        The one enumeration of rule 9 (spec 2026-11-02), for the value walk's window
        (`_Walk._window`) and the forward chain walk's forks (`shapes.chains`) alike (review 3
        re-review 2, check 4):

        - **A call not on every path to the use** (`always`) SPLITS the path: one where it ran,
          one where it did not, the choice recorded (`_SPLIT`, with whether it counts for the
          reader, `_counted`), each side proven or marked `_UNPROVEN` (`reaches_use`). An event
          that changes nothing on any path (`(((), ()),)`) is no split.
        - **A call made on a configuring call's result** (`parent`) runs only where that call
          did, and where it is on that call's `post_dominator` chain BEFORE the use it runs
          wherever that call does: it is no split of its own (review 3 re-review 2, m-1,
          accepted by the user 2026-11-03). `if (x) b.setUri("/b").setUri("/c")` is ONE split.
          A child after the use in its loop keeps its own split (re-review 3, N-1).
        - **Two or more counted splits** make every path inexact whatever each call did
          (`_unsure`), so the choices are not recorded one by one: one `_SEVERAL` mark, and
          paths that gather the same calls are one (review 3, M2).
        - **The path cap** (`PATH_CAP`) counts the paths the reader already holds beside this
          window's (`width`, 1 for a window read on its own): past it, one path ending
          `non_enumerable`, the parts unknown, stated, never dropped."""
        always = self.always(method, used_at)

        def follows(parent: int | None, ordinal: int) -> bool:
            # Only BEFORE the use (review 3 re-review 3, N-1): a child after the use by ordinal
            # reaches it only on a later pass of a loop, so it keeps its own split, never
            # proven (`reaches_use`, C-A), however surely it follows its parent.
            if parent is None or (used_at is not None and ordinal > used_at):
                return False
            chain = _post_dominators(self._index, method, parent)
            return chain is not None and ordinal in chain

        splitting = {
            ordinal
            for ordinal, outcomes, parent in events
            if ordinal != _END_OF_BODY
            and outcomes != (((), ()),)
            and not always(ordinal)
            and not follows(parent, ordinal)
        }
        counted = {
            ordinal
            for ordinal, outcomes, _ in events
            if ordinal in splitting and _counted(method, outcomes, counting)
        }
        several = len(counted) > 1
        # Which ordinals a later event is made on the result of: only those need remembering
        # as skipped, so two paths differing only in a skip nothing reads are one.
        parents = {parent for _, _, parent in events if parent is not None}
        # Each path, with the events it did NOT run.
        start: _Trail = (_Step((_SEVERAL,), _SEVERAL),) if several else ()
        paths: list[tuple[_Trail, tuple[tuple[str, int], ...] | str, frozenset[int]]] = [
            (start, (), frozenset())
        ]
        for ordinal, outcomes, parent in events:
            skip: _Trail | None = None
            if ordinal in splitting:
                skip = ()
                if not several:
                    ran_proven, skip_proven = self.reaches_use(
                        method, held, ordinal, used_at, in_body
                    )
                    split = (_SPLIT, method, ordinal, ordinal in counted)
                    ran: _Trail = (_Step(split, _RAN),)
                    if not ran_proven:
                        ran += (_Step((_UNPROVEN, method, ordinal, used_at, _RAN), _UNPROVEN),)
                    outcomes = tuple(((*ran, *more_steps), more) for more_steps, more in outcomes)
                    skip = (_Step(split, _SKIPPED),)
                    if not skip_proven:
                        skip += (_Step((_UNPROVEN, method, ordinal, used_at, _SKIPPED), _UNPROVEN),)
            remembered = frozenset({ordinal}) if ordinal in parents else frozenset()
            following: list[tuple[_Trail, tuple[tuple[str, int], ...] | str, frozenset[int]]] = []
            for steps, gathered, skipped in paths:
                if isinstance(gathered, str):
                    following.append((steps, gathered, skipped))
                    continue
                if parent in skipped:
                    following.append((steps, gathered, skipped | remembered))
                    continue
                for more_steps, more in outcomes:
                    merged = _combine(steps, more_steps)
                    if merged is not None:
                        following.append(
                            (merged, more if isinstance(more, str) else (*gathered, *more), skipped)
                        )
                if skip is not None and (merged := _combine(steps, skip)) is not None:
                    following.append((merged, gathered, skipped | remembered))
            paths = list(dict.fromkeys(following))
            if len(paths) * width > PATH_CAP:
                # Past the bound: one path, the parts this window sets unknown, the reason
                # stated (review 3, M2). Never dropped.
                return (((), NON_ENUMERABLE),)
        return tuple(dict.fromkeys((steps, gathered) for steps, gathered, _ in paths))


class HandOffs:
    """What is done to a value OTHER than calls made on it (spec 2026-11-02 rules 1-3), as the
    value walk reads it (`_Walk._handed_events`), for a reader that walks the calls made on it
    itself: the forward chain walk (`shapes.chains`, review 3 re-review 2, C-2). One rule, not a
    second copy: a hand-off into a body this workspace read is that body's window over its
    parameter, by rule 9 there; one into code we do not have, or a call that reaches the value
    below an argument's top level or through a receiver the facts cannot name, is `escapes`.

    `configuring` gives the calls that configure the value, as the value walk takes them: inside
    an entered body, one of them is gathered and any other call on the parameter is `escapes`.
    It is asked, and the walk built, the first time a value has anything done to it, since
    most chains hand their value nowhere (GUIDELINES §8.7). One per chain run; it keeps each
    entered body's window it has read."""

    def __init__(
        self,
        index: ValueIndex,
        configuring: Callable[[], AbstractSet[tuple[str, str, str]]],
        counting: Counting = None,
    ) -> None:
        self._index = index
        self._configuring = configuring
        self._counting = counting
        self._walk: _Walk | None = None

    def of(self, method: str, value: int, after: int) -> "list[tuple[int, tuple[_Window, ...]]]":
        """Each thing done to `value` in `method` after the ordinal `after`, other than a call on
        it, in ordinal order: `(ordinal, outcomes)`, each outcome one path's choices and the
        configuring calls it gathered, `(method, ordinal)` in run order, or the reason it
        ended. Nothing for a value no hand-off can change (rule 3)."""
        key = (method, value)
        held_type = self._index.value_types.get(key)
        if (
            not self._index.handed.get(key)
            and not self._index.nested.get(key)
            and (held_type is None or not self._index.unread_receivers.get((method, held_type)))
        ) or held_type in _UNCHANGEABLE:
            return []
        if self._walk is None:
            self._walk = _Walk(
                self._index, configuring=self._configuring(), counting=self._counting
            )
        events = self._walk._handed_events(method, (_VALUE, value), lambda ordinal: ordinal > after)
        return [(ordinal, outcomes) for ordinal, outcomes, _ in sorted(events, key=lambda e: e[0])]


class _Walk:
    """One resolve's walk. Not reused across sites: the memo is keyed on (position, path)
    and both are meaningful only within the resolve that built them."""

    def __init__(
        self,
        index: ValueIndex,
        identities: Identities = (),
        declared: AbstractSet[tuple[str, str]] = frozenset(),
        branches: bool = True,
        along_receivers: bool = False,
        past_accessors: Ancestors | None = None,
        which_object: bool = False,
        configuring: AbstractSet[tuple[str, str, str]] = frozenset(),
        asking: frozenset[tuple[str, tuple[str, int]]] = frozenset(),
        stop_at_parameters_of: AbstractSet[str] = frozenset(),
        parameters_apart: bool = False,
        counting: Counting = None,
        read_sites: AbstractSet[tuple[str, int]] = frozenset(),
        functions: bool = False,
        declared_sites: AbstractSet[tuple[str, int]] = frozenset(),
        declared_types: bool = False,
        shared: Any = None,
    ) -> None:
        self._index = index
        # The reader's key in the index's shared upward paths (`ValueIndex.suffixes`, R39):
        # every walk of one reader over one index shares them. None, they are this walk's own.
        self._shared = shared
        self._suffixes: dict[Any, tuple[_Reached, ...]] = (
            index.suffixes if shared is not None else {}
        )
        self._suffix_deps: dict[Any, frozenset[Any]] = (
            index.suffix_deps if shared is not None else {}
        )
        # What the positions being worked out read that a binding round can change, innermost
        # last (`_depends`): each finished position hands its reads to the one that asked.
        self._deps: list[set[Any]] = []
        self._memo_deps: dict[Any, frozenset[Any]] = {}
        # The type reader (`producer_paths(..., declared_types=True)`): where a body gives a
        # call's result no type, the callee's declared return does. False for every other
        # reader, which never reads a declaration as a value.
        self._declared_types = declared_types
        # The producer reader's stop set by site, `(method, ordinal)`: a call that makes an
        # object although its `(owner, name)` names no type (a mount's chain result, design
        # 2026-11-06-reading-decorators §4). Empty for every other reader.
        self._declared_sites = frozenset(declared_sites)
        # The call reader (`producer_paths(..., functions=True)`): a function value ends its
        # path naming the function's body. False for every other reader.
        self._functions = functions
        # The calls the reader itself reads, by `(method, ordinal)` (the forward chain walk's
        # declared steps, for the execute-join `chains._joined_through_values` reads): one made
        # on the value, or handed the value, does not open `escapes`, since what it does is
        # read where the reader reads it. Empty for every other reader.
        self._read_sites = frozenset(read_sites)
        # False answers a branch between literals `non_enumerable`, as before ruling 7 — for
        # the one reader that can carry a single address and must not lose the one it had
        # (`fluent`'s assembled url, OI-134). Every other reader takes the default.
        self._branches = branches
        self._identities = tuple(identities)
        # The producer reader's stop set (`producers_of`). Empty for the value walk, which is
        # what keeps its answers exactly what they were: `_declared_producer` matches nothing.
        self._declared = frozenset(declared)
        # The chain reader (`producers_of(..., along_receivers=True)`): a declared call is
        # followed on through its receiver rather than ending the path.
        self._along_receivers = along_receivers
        # The producer-identity reader (`producers_of(..., past_accessors=...)`): an accessor
        # on the value does not open `escapes`. None for every other reader.
        self._past_accessors = past_accessors
        # The calls that return the object they were called on (ruling 4, spec 2026-10-30),
        # as `(owner, name, descriptor)`: one made on the value does not open `escapes`, and
        # the chain reader gathers it into the chain (`_configured_on`). Empty for every other
        # reader.
        self._configuring = frozenset(configuring)
        # The methods whose parameters END a path (`producers_of(..., stop_at_parameters_of=)`)
        # rather than cross to their callers. Empty for every other reader.
        self._stop_at_parameters_of = frozenset(stop_at_parameters_of)
        # The producer reader (`producers_of`, `producer_paths`): two ends that differ only in
        # the parameter an `external` answer ended at are two ends (`_distinct`). False for
        # every other reader, whose answers stay exactly what they were.
        self._parameters_apart = parameters_apart
        # Which splits count for the reader's row (`counts_split`); None, every one.
        self._counting = counting
        # The object reader (`_Walk._objects`): which construction a receiver IS. No call made
        # on an object changes which `new` built it, so the `escapes` window does not apply.
        self._which_object = which_object
        # The object reads `(field, getter site)` the walks above this one are in the middle
        # of: a read that would ask one of them again answers as it did before ruling 1
        # rather than recurse.
        self._asking = asking
        # Set on an object walk (`_objects`) only: how many of the frames it was started in
        # are the asker's, and every read this walk made of those frames (`_frame_in`,
        # `_object_site`, `_object_writes`). What the walk answers depends on the asker's
        # frames through these reads and nothing else, so its answer serves every asker
        # whose frames read the same.
        self._base: int | None = None
        self._reads: list[tuple[Any, ...]] = []
        # Per field: each call of a method writing it, with the objects that call was made on
        # (`_Walk._setter_calls_of`), per field and reads in progress.
        self._setter_calls: dict[
            tuple[str, frozenset[tuple[str, tuple[str, int]]]], tuple[_SetterCall, ...]
        ] = {}
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
        # What a body does to the parameter a value was handed to (`_entered_window`), per
        # `(callee, parameter)`, and the ones being read right now: entering one again is
        # `cycle`. An answer holding a `cycle` is not kept, for `_open`'s reason above.
        self._windows: dict[tuple[str, int], tuple[_Window, ...]] = {}
        self._entering: set[tuple[str, int]] = set()
        # `_touched_in`'s memo and its guard: the bodies read for what they do to a parameter,
        # and those being read now.
        self._touched: dict[tuple[str, int], str | None] = {}
        self._entering_bodies: set[tuple[str, int]] = set()
        # Rule 9's split and proof, shared with the forward chain walk (`Flow`).
        self._flow = Flow(index)

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
        if self._upward(position):
            return self._joined_upward(position, trail, frames)
        key = (position, trail)
        cached = self._memo.get(key)
        if cached is not None:
            self._read(self._memo_deps[key])
            return cached
        if position in self._pending:
            self._open.add(position)
            return _only(trail, _unresolved(CYCLE))
        self._pending.add(position)
        outer, self._open = self._open, set()
        self._deps.append(set())
        reached = self._compute(position, trail, frames)
        deps = frozenset(self._deps.pop())
        self._read(deps)
        unresolved_back_edges = self._open - {position}
        self._open = outer | unresolved_back_edges
        self._pending.discard(position)
        if not unresolved_back_edges:
            self._memo[key] = reached
            self._memo_deps[key] = deps
        return reached

    def _depends(self, read: Any) -> None:
        """Record that the position being worked out read `read`, a part of the index a binding
        round can change (`ValueIndex.suffix_deps`)."""
        if self._deps:
            self._deps[-1].add(read)

    def _depended(self, site: tuple[str, int]) -> tuple[str, ...]:
        """`site`'s callees, the read recorded (`_depends`)."""
        self._depends((READ_CALLEES, site))
        return tuple(self._index.callees.get(site, ()))

    def _read(self, reads: frozenset[Any]) -> None:
        """Hand a finished position's reads to the position that asked for it."""
        if self._deps and reads:
            self._deps[-1].update(reads)

    def _upward(self, position: _Position) -> bool:
        """Whether `position`'s answer is the same set of paths upward whatever path reached
        it (R39): a parameter, read through its callers, and a binding read plainly (not on an
        object, not unseen), outside an object walk, whose answers depend on the asker's
        frames through reads it records."""
        if self._base is not None:
            return False
        return position[0] in (_PARAMETER, _RECIPE_RUN, _RECIPE_PATHS) or (
            position[0] == _BINDING and len(position) == 2
        )

    def _joined_upward(
        self, position: _Position, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """`position`'s paths upward (ruling R39), each joined onto `trail` by the coherence
        rule: a path that chose another context than `trail` already chose is not on it, and
        is dropped, as the walk would have dropped it at that crossing. The paths are kept
        apart, never combined (ruling M-1). They are worked out once per `(position, frames)`
        on the empty path, which the prefix can change only through those refusals, so the
        work is bounded by the positions, not by the paths through them: polar's
        `self.session` was 833,097 paths over 4,655 parameters. An answer resting on a
        position still being worked out (a cycle) is not kept, as before."""
        key = (self._shared, position, frames)
        upward = self._suffixes.get(key)
        if upward is not None:
            self._read(self._suffix_deps[key])
        else:
            if position in self._pending:
                self._open.add(position)
                return _only(trail, _unresolved(CYCLE))
            self._pending.add(position)
            outer, self._open = self._open, set()
            self._deps.append(set())
            upward = self._compute(position, (), frames)
            deps = frozenset(self._deps.pop())
            self._read(deps)
            unresolved_back_edges = self._open - {position}
            self._open = outer | unresolved_back_edges
            self._pending.discard(position)
            if not unresolved_back_edges:
                self._suffixes[key] = upward
                self._suffix_deps[key] = deps
        found: list[_Reached] = []
        for path, answer in upward:
            merged = _combine(trail, path)
            if merged is not None:
                found.append((merged, answer))
        return tuple(found)

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
        if kind == _RECIPE_RUN:
            return self._recipe_returns(position[1], trail, frames)
        if kind == _RECIPE_PATHS:
            return self._recipe_paths(position[1], position[2], trail, frames)
        # `(_BINDING, symbol)` — the symbol the `field` argument carried, which the sixth
        # edge is keyed on — marked `_UNSEEN`, or carrying the getter site the read was made
        # through (`_Walk._object_site`).
        mark = position[2] if len(position) > 2 else None
        return self._binding(
            position[1],
            trail,
            frames,
            unseen=mark == _UNSEEN,
            read_on=mark if isinstance(mark, tuple) else None,
        )

    def _of_site(
        self, site: Mapping[str, Any], slot: int | str, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        method, ordinal = str(site["caller"]), int(str(site["ordinal"]))
        if slot == RECEIVER:
            # A receiver read from a static field, or from a field of `this`, is that field
            # (D00 §5's `receiver_field`), resolved as the same field read as an ARGUMENT is: the
            # read's own value id names nothing any other fact joins to.
            field = site.get("receiver_field")
            if field is not None:
                return self._resolve((_BINDING, str(field)), trail, frames)
            # A receiver that is the method's parameter is that parameter, whether or not the
            # facts also name a value id for it: a call left for the resolver to bind must name
            # a receiver (D00 §5), so a call on an untyped parameter carries both, and the id
            # is produced by nothing. A JVM site never names both (`receiver_parameter` is the
            # other half of a null `receiver` there), so for it the order is no change.
            parameter = site.get("receiver_parameter")
            if parameter is not None:
                return self._through_parameter(method, int(str(parameter)), ordinal, trail, frames)
            receiver = site.get("receiver")
            if receiver is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return self._through(method, int(str(receiver)), ordinal, trail, frames)
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
            # §8.2 is untouched: a `${...}` operand answers `expression`, not `literal`.
            # `_joined` may print its text into a hole, and then marks the result
            # `expression` (never `literal`), so no deployment hole is ever filled in.
            template = argument.get("value")
            if not isinstance(template, str):
                return _only(trail, _unresolved(NOT_READABLE))
            joined = self._joined(template, argument, method, trail, frames)
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
            return _only(
                trail,
                Answer(
                    kind=LITERAL,
                    value=str(symbol),
                    literal_kind=SYMBOL,
                    class_object=kind == "class",
                ),
            )
        if kind == "field":
            symbol = argument.get("symbol")
            if symbol is None:
                return _only(trail, _unresolved(NOT_READABLE))
            # The unseen-object rule (`_binding`, OI-222) is decided HERE, where the reading
            # method is known, and marks the position only when it applies: every other read
            # keeps the one position a binding has always had, so memo and cycle detection
            # are unchanged wherever the rule does not fire.
            if self._unseen_object(str(symbol), frames, method):
                return self._resolve((_BINDING, str(symbol), _UNSEEN), trail, frames)
            # A read placed on an object carries the getter site in its position: what it
            # answers depends on that site's receiver (ruling 1), so two reads of one field
            # through two sites are two positions, for the memo and for cycle detection.
            read_on = self._object_site(str(symbol), frames, method)
            if read_on is not None:
                return self._resolve((_BINDING, str(symbol), read_on), trail, frames)
            return self._resolve((_BINDING, str(symbol)), trail, frames)
        if kind == "parameter":
            index = argument.get("value")
            if index is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return self._through_parameter(method, int(str(index)), _used_at(origin), trail, frames)
        if kind == "array":
            return self._elements(argument, method, origin, trail, frames)
        if kind == "merge":
            return self._merged(argument, method, origin, trail, frames)
        if kind == "lambda":
            # It carries a `source` and a body `symbol`, so it would fit both shapes
            # above, and it is left out of both on MEANING (`value_edges.sql`'s
            # `names_declaration` arm, ruled 2026-09-22): it names a body, not a value.
            # The one reader asking what a CALL of the value runs is answered that body
            # (ruling R29): calling a function runs it, as a lambda on the JVM.
            if self._functions and argument.get("symbol") is not None:
                return _only(
                    trail, Answer(kind=LITERAL, literal_kind=SYMBOL, value=str(argument["symbol"]))
                )
            return _only(trail, _unresolved(NOT_READABLE))
        if kind == "null":
            # The code STATES there is no value (D00 §5's `null` kind). That is an answer
            # and not a miss, so it is `absent` rather than a reason: a consumer told
            # `not_readable` would look for a value that is not there to be found, which is
            # a different and false claim about the code.
            return _only(trail, Answer(kind=ABSENT, null=True))
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

        **A merge with no root whose candidates are ALL literals is `narrowed`** (ruling 7,
        2026-10-29, amending the 2026-10-21 design): `c ? A.class : B.class`, `c ? "x" :
        "y"`. One answer per candidate, each the literal the code states, marked `narrowed`,
        on this path plus the choice it made — the candidates are the complete set and no
        one of them is THE value, which is D00's `narrowed`. Picking one would still be a fact about code that
        may never run (the Phase 2G ruling holds); listing them all is not a pick.

        **Any other merge with no root is `non_enumerable`**: a literal beside a call, two
        unrelated calls. A literal here means a candidate whose grammar kind is a literal or
        a declaration reference AND which answers a `literal` on the spot; a candidate that
        answers anything else — an `instance` whose identified construction is not a
        literal, a `class` with no symbol, a value reached by crossing out of this method —
        leaves the merge `non_enumerable` as it was.
        """
        candidates = argument.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return _only(trail, _unresolved(NON_ENUMERABLE))
        root = self._root_of(candidates, method)
        if root is None:
            passed = self._passed_through(candidates, method, trail, frames)
            if passed is not None:
                return passed
            return self._branched(candidates, method, origin, trail, frames)
        return tuple(
            (
                crossed,
                replace(answer, inexact=True) if answer.kind in (LITERAL, EXPRESSION) else answer,
            )
            for crossed, answer in self._entry(root, method, origin, trail, frames)
        )

    def _branched(
        self,
        candidates: "list[Mapping[str, Any]]",
        method: str,
        origin: _Position,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """A merge with no root: every candidate `narrowed` where all are literals, else ONE
        `non_enumerable` (ruling 7; `_merged` states the rule).

        **Each candidate is a CHOICE on the path, recorded as a crossing** (fix round 1, M-1).
        Without it two reads of one branch combine in every pairing: `p = c ? "/a" : "/b";
        … p + "/x/" + p` minted `/a/x/b`, which no execution builds. The step's context is
        the branch — the method and its candidate list, since a `merge` carries no value id —
        so `_combine` keeps one choice per branch on a path: the same branch read twice gives
        `(/a, /a)` and `(/b, /b)`. Two branches with the SAME candidates in one method share a
        context and are held to one choice too; that can drop a real pairing and never
        invents one, which is the direction the walk is allowed to err in. Branches with
        different candidates are independent, as nothing in the facts says otherwise.

        **Candidates answering ONE value are that value, exactly** — `c ? 1 : 1L` is `1` on
        every branch, so there is no choice to record and nothing to narrow.
        """
        if not self._branches:
            return _only(trail, _unresolved(NON_ENUMERABLE))
        if not all(
            str(candidate.get("kind")) in _LITERAL_KINDS
            or str(candidate.get("kind")) in _DECLARATION_KINDS
            for candidate in candidates
        ):
            return _only(trail, _unresolved(NON_ENUMERABLE))
        reached = [
            (index, crossed, answer)
            for index, candidate in enumerate(candidates)
            for crossed, answer in self._entry(candidate, method, origin, trail, frames)
        ]
        if any(answer.kind != LITERAL or crossed != trail for _, crossed, answer in reached):
            return _only(trail, _unresolved(NON_ENUMERABLE))
        distinct = list(dict.fromkeys(answer for _, _, answer in reached))
        if len(distinct) == 1:
            return _only(trail, distinct[0])
        branch = (_BRANCH_OF, method, json.dumps(list(candidates), sort_keys=True, default=str))
        chosen: list[_Reached] = []
        for index, _, answer in reached:
            merged = _combine(trail, (_Step(branch, f"branch {index}"),))
            if merged is not None:
                chosen.append((merged, replace(answer, narrowed=True)))
        return tuple(dict.fromkeys(chosen))

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
        per_hole: list[tuple[tuple[_Trail, str | None, str, bool, bool, bool], ...]] = []
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
        for at, (operand, hole) in enumerate(zip(operands, unfilled, strict=True)):
            # Read where the concat USES it (spec 2026-11-02 rule 1): the concat site is the
            # call that consumes the operand, so the `escapes` window ends there, and its own
            # hand-off of the operand is that use rather than a call that might change it.
            used = (_SLOT, method, int(str(site["ordinal"])), at)
            reached = self._entry(operand, method, used, trail, frames)
            # An INEXACT literal fills its hole like an exact one — the text is the value the
            # code states, read through a merge whose root it is — and taints the result
            # below: a template filled from one is never `literal`, because part of what
            # was sent (what the call on the root did to it) was not read. A NARROWED literal
            # fills its hole the same way and marks the result `narrowed` (ruling 7): one
            # template per candidate, of which one is sent.
            #
            # **A path this hole cannot fill is REPLACED, never dropped** (ruling 6, the
            # rule `_value` applies to `preserves`). Every path the operand reached is one
            # calling context of this helper, and each gives its own template: the text
            # where it read one (a string literal, or an expression that already carries
            # a `${…}`), the hole's spelling where it read none. Dropping the unreadable
            # ones whenever another path read text published ONE address for a helper
            # that is called with two — and a consumer asking "who is called" then saw a
            # single answer where the code gives two.
            settled = tuple(
                (
                    crossed,
                    str(answer.value) if _fills(answer) else None,
                    answer.yields,
                    answer.inexact,
                    answer.narrowed,
                    answer.kind == EXPRESSION,
                )
                for crossed, answer in reached
            )
            per_hole.append(settled or ((trail, None, _ADDRESS, False, False, False),))
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
        filled = any(value is not None for hole in per_hole for _, value, _, _, _, _ in hole)
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
            for crossed, _, _, _, _, _ in combination:
                joined = _combine(merged, crossed)
                if joined is None:
                    coherent = False
                    break
                merged = joined
            if not coherent:
                continue
            text = pieces[0] + "".join(
                (value if value is not None else hole) + piece
                for (_, value, _, _, _, _), hole, piece in zip(
                    combination, self._holes, pieces[1:], strict=True
                )
            )
            # A hole a placeholder EXPRESSION filled is read text, but not a value the code
            # states: `${key}` is a deployment's to set, so the result is never `literal`.
            whole = all(value is not None for _, value, _, _, _, _ in combination) and not any(
                keyed for _, _, _, _, _, keyed in combination
            )
            inexact = any(inexact for _, _, _, inexact, _, _ in combination)
            narrowed = any(narrowed for _, _, _, _, narrowed, _ in combination)
            # **An AUTHORITY joined to a path is written scheme-relative** (`OI-142`,
            # ruling 2). `//customers-service/owners` is RFC 3986 §4.2's scheme-relative
            # reference — a real URI form, not an invention — and the `//` says exactly
            # where the authority ends, so `split_url` separates the two columns with no
            # second shape for any consumer to learn. Only where the result carries no
            # scheme of its own: `"http://" + host + "/x"` already says where the
            # authority starts and prefixing that would be wrong.
            if any(kind == _AUTHORITY for _, _, kind, _, _, _ in combination) and "://" not in text:
                text = f"//{text}"
            # **`literal` only when EVERY hole was read from a string literal; otherwise
            # `expression`** (a hole a `${key}` expression filled counts as not read), and that
            # is the whole safety of a partial fill (§3). A half-filled template is not a
            # value the code states, it is a statement about part of one — and
            # `channel_of_answer` refuses an expression, so no messaging catalog can read
            # one as a destination. A broker resolves a destination it is GIVEN and half of
            # one is not a destination.
            reached_out.append(
                (
                    merged,
                    Answer(
                        kind=LITERAL,
                        value=text,
                        literal_kind=STRING,
                        inexact=inexact,
                        narrowed=narrowed,
                    )
                    if whole
                    else Answer(kind=EXPRESSION, value=text, inexact=inexact, narrowed=narrowed),
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

        **A value HANDED to another method is followed into it** (spec 2026-11-02 rules 1-3,
        replacing the narrowing that counted only calls ON the value). A call in the window
        that passes the value as an argument may change it as surely as a call on it, so a
        body this module has — or a library named in `extract_libraries` — is walked into
        and what it does to its parameter is judged by this same rule; code we do not have
        ends the path at `escapes`. `_window` has the rules, and a `String`, a primitive or
        a boxed primitive parameter is not a hand-off at all, so a value logged and then used
        still resolves.

        **A CONSTRUCTOR is a producer, not a mutation** (review round 1). `produced_by` is
        read off `call_sites.result` and an `<init>` has none — D00 §5's "result is null
        for a void one" — so a constructed value has no producer ordinal at all here, and
        the window used to open before its own construction. Every `new Thing(x)` whose
        value is then used therefore answered `escapes` on the constructor itself. The
        construction is where the window opens, and `_construction` is what finds it.

        **For a producer-identity reader, an ACCESSOR is not in the window** (Quartz fix
        rounds 2-3, 2026-10-29): `producers_of(..., past_accessors=...)` only. `_accessor`
        has the rule and why it is a reader's switch rather than the default.

        **Nor is a call that CONFIGURES the value** (ruling 4, spec 2026-10-30), for a reader
        that declares which calls do (`configuring`): `_window` has the rule. A chain
        answered for the value gains those calls after its own — those a body it was handed
        to makes on it at the hand-off's place — so reading `tb.build()`'s receiver gives the
        chain `_along` puts `build` after.

        **Each path through the window is its own answer.** A hand-off whose call reaches
        two bodies is two paths, one per body, each recorded on the trail; they are never
        folded into one.
        """
        produced = self._index.producers.get((method, value), ())
        constructed = self._construction(method, value)
        produced_at = min(produced) if produced else (-1 if constructed is None else constructed)
        return self._windowed(
            method, (_VALUE, value), produced_at, used_at, (_VALUE, method, value), trail, frames
        )

    def _through_parameter(
        self, method: str, index: int, used_at: int | None, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """A parameter of `method`, read at `used_at` (None: a return, so the whole body) —
        followed out through `_parameter`, unless something got at it first INSIDE `method`
        (fix round 1, C1). A parameter is produced when the method is entered, so its window
        runs from the entry to the use: in `send(o) { configure(o); create(vertx, o); }` the
        hand-off to `configure` is in it, as it would be had the caller made it."""
        return self._windowed(
            method, (_PARAMETER, index), -1, used_at, (_PARAMETER, method, index), trail, frames
        )

    def _windowed(
        self,
        method: str,
        held: tuple[str, int],
        after: int,
        used_at: int | None,
        position: _Position,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """`position` resolved once per path through `held`'s window, with that path's
        gathered calls appended to a chain answer, or the reason the path ended."""
        reached: list[_Reached] = []
        windows = self._window(method, held, after, used_at)
        for steps, gathered in windows:
            if len(reached) > PATH_CAP:
                # The cap counts the WHOLE path (review 3 re-review, m-B): each window keeps
                # under it, but the windows of the frames a path crosses multiply. Past it, one
                # answer, the parts unknown, the reason stated — and no more enumerated.
                return ((trail, _unresolved(NON_ENUMERABLE)),)
            crossed = _combine(trail, steps)
            if crossed is None:
                # This path already chose another body at one of these hand-offs.
                continue
            if isinstance(gathered, str):
                reached.extend(self._identities_past(gathered, position, crossed, frames))
                continue
            reached.extend(
                (path, replace(answer, inexact=True) if _unsure(path) else answer)
                for path, answer in (
                    (
                        path,
                        replace(
                            answer,
                            value=replace(answer.value, chain=(*answer.value.chain, *gathered)),
                        ),
                    )
                    if gathered and answer.kind == _PRODUCED and answer.value.chain
                    else (path, answer)
                    for path, answer in self._resolve(position, crossed, frames)
                )
            )
        if len(reached) > PATH_CAP:
            return ((trail, _unresolved(NON_ENUMERABLE)),)
        return tuple(reached)

    def _identities_past(
        self, reason: str, position: _Position, trail: _Trail, frames: "_Frames"
    ) -> list[_Reached]:
        """A window path that ended at `reason` (`escapes`, `cycle`): the reason, except where
        the value IS a declaration the code names (rule 8, ruled by the user 2026-11-02:
        "identity is not content").

        **Which declaration a value is cannot be changed by anything done to it.** The JVM hands
        a callee a copy of the reference, so no hand-off and no call on the value can make the
        caller's variable another object; rules 1-3 are about an object's CONTENTS. A `symbol`
        answer is the walk saying the value IS a declaration (`_DECLARATION_KINDS`: an enum
        constant, a class, the type a value was built from), never what an object holds, so
        each path's symbol answer stands and every other answer on the path is `reason`.
        apollo-portal's `doExecute(HttpMethod method, …)` runs `HttpMethod.GET.equals(method)`
        before `exchange(…, method, …)`: the verb is the constant each caller hands in.

        **Only `symbol`, not every literal.** A string or number answer may be an object's
        contents read through an identity arm — `new Name("x")` IS `"x"` until something
        changes it (`test_a_value_written_to_between_its_construction_and_its_use_escapes`)
        — and a `String` value no call can change already has an empty window (rule 3). One
        rule on the answer's kind, so no reader and no type is named."""
        found: list[_Reached] = []
        other = False
        for path, answer in self._resolve(position, trail, frames):
            if answer.kind == LITERAL and answer.literal_kind == SYMBOL:
                found.append((path, answer))
            else:
                other = True
        if other or not found:
            found.append((trail, _unresolved(reason)))
        return found

    def _window(
        self,
        method: str,
        held: tuple[str, int],
        after: int,
        used_at: int | None,
        in_body: bool = False,
    ) -> tuple[_Window, ...]:
        """Every path through the window over `held` — a value id `(_VALUE, id)` or a parameter
        `(_PARAMETER, index)` of `method` — from after `after` to before `used_at` (None: to
        the end of the body). Each is the configuring calls it gathered, in the order they run,
        or the reason it ended.

        **A value nothing can change has an empty window** (rule 3, fix round 1 M1): a value
        whose own type is a primitive, `String` or a boxed primitive (`_type_of`) — no call on
        it and no hand-off of it can change it, whatever the parameter it is handed to is typed.

        **A call made ON the value** configures it, is an accessor, or ends the path at
        `escapes` (`_events`). So a body that only READS its parameter — `validate(o)` calling
        `o.getHost()` — is `escapes` for a reader that does not let accessors past, exactly as
        the same call written in the caller is.

        **A call the walk cannot follow ends the path at `escapes`** (rule 2, fix round 1): one
        reaching the value below the top level of an argument (an array element, a merge
        candidate — M3), and an instance call on the value's own type whose receiver the facts
        cannot name (M4: a parameter reassigned on a branch loses its id as a receiver; a call
        on `this` of the same type is read the same way, which can only err towards a miss).

        **A call that CONFIGURES the value returns the object it was called on** (ruling 4,
        spec 2026-10-30): the reader declared it so (`configuring`), and its result is the
        same object, so what is called on that result in the window is gathered too, under the
        same rule. The chain reader appends these to the chain of the call that produced the
        value (`_through`); for every other reader they only stay out of `escapes`, since which
        call built the value is unchanged.

        **A call that HANDS the value on** (spec 2026-11-02 rule 1) is walked into
        (`_handed_to`): the calls the body makes on its parameter are judged by this rule, in
        their order, at the hand-off's place in this one; its own hand-offs are followed the
        same way. Several bodies at one call are several paths. A body that cannot be read
        (rule 2) ends the path at `escapes`.

        **A field write of the value ends the path at `escapes`** (rule 2) inside a body the
        value was handed to (`in_body`), whose window is the whole body — the fact carries no
        ordinal, so only there is a write known to be inside the window. In the method the
        walk started from it is not read: where the window ends at a use, a write may come
        after it, and where it runs to the end the value may be reached THROUGH that very
        write (`_binding_writes`), which is its use, not a change. **Only as wide as D00 §5's
        `field_write`**: `this.f = p` and a static store. `holder.f = o`, `arr[0] = o` and a
        store from a parked local emit no fact, so such a body reads as storing nothing.

        **A recursion is `cycle`, even one that does nothing** (`_entered_window`):
        `walk(Node n, Opts o) { for (c : n.kids) walk(c, o); }` answers `cycle`, not "nothing".

        **A call not on every path to the use SPLITS the path** (spec 2026-11-02 rule 9, the
        fact approved by the user that day): one path where it ran, one where it did not, the
        choice recorded on the trail (`_SPLIT`) so two reads of one path agree on it. "Every
        path" is the use's `dominator` chain, or, where the window runs to the end of a body,
        `on_every_exit` — so a call inside a body the value was handed to splits the caller's
        path where it is not on every exit there (`_always`). A call made on a configuring
        call's result runs only where that call did. An event that changes nothing on any
        path (a capture the lambda does nothing with) is no split, and a field write in an
        entered body, which carries no ordinal, never splits. A side of the split the facts
        do not prove a run takes to the use (`_reaches_use`, ruled 2026-11-03) carries an
        `_UNPROVEN` step, and `_windowed` makes its answers inexact.

        **Cost.** Each event multiplies the paths by the distinct outcomes it has, so *n*
        sequential hand-offs each reaching bodies that disagree give up to 2^*n* paths, each
        resolved on its own trail; bodies that agree are one path. A split is one more
        outcome, so *n* split calls give up to 2^*n* paths too; measured on the six pinned
        corpora and the five unpinned ones (rule 9), the worst window holds 4 split calls and
        5 paths (`yudao-module-infra`), and no published row moved. Entered windows are kept
        per walk (`_windows`). No bound is set, for the reason the module docstring gives for
        having none.

        The object reader (`which_object`) reads no window: no call changes which construction
        an object IS."""
        if self._which_object or self._type_of(method, held) in _UNCHANGEABLE:
            return (((), ()),)
        return self._flow.paths(
            method,
            held,
            self._events(method, held, after, used_at, in_body),
            used_at,
            in_body,
            self._counting,
        )

    def _events(
        self,
        method: str,
        held: tuple[str, int],
        after: int,
        used_at: int | None,
        in_body: bool,
    ) -> list[tuple[int, tuple[_Window, ...], int | None]]:
        """What happens to `held` in the window `_window` reads, as `(ordinal, outcomes,
        parent)` in the order it happens: each outcome is one path's step — a gathered call, a
        reason, or one body's whole window — and `parent` the configuring call whose result a
        call is made on, None for a call on `held` itself."""
        inside = self._flow.inside(method, after, used_at)
        kind, key = held
        if kind == _VALUE:
            on = self._index.receivers.get((method, key), ())
            stored = (method, key) in self._index.stored
        else:
            on = self._index.parameter_receivers.get((method, key), ())
            stored = (method, key) in self._index.stored_parameters
        events = self._handed_events(method, held, inside)
        for ordinal in on:
            if not inside(ordinal):
                continue
            if self._accessor((method, ordinal)):
                continue
            if (method, ordinal) in self._read_sites:
                continue
            row = self._index.sites.get((method, ordinal))
            if row is None or _call_of(row) not in self._configuring:
                events.append((ordinal, (((), ESCAPES),), None))
                continue
            events.append((ordinal, (((), ((method, ordinal),)),), None))
            result = row.get("result")
            if result is not None:
                events.extend(
                    (later, outcomes, ordinal if parent is None else parent)
                    for later, outcomes, parent in self._events(
                        method, (_VALUE, int(str(result))), ordinal, used_at, in_body
                    )
                )
        if stored and in_body:
            events.append((_END_OF_BODY, (((), ESCAPES),), None))
        return sorted(events, key=lambda event: event[0])

    def _handed_events(
        self, method: str, held: tuple[str, int], inside: Callable[[int], bool]
    ) -> list[_Event]:
        """What `_events` reads other than the calls made ON `held`, at the ordinals `inside`
        keeps: a call that may change it and cannot be followed (`escapes`), and each hand-off
        of it, as the paths it takes (`_handed_to`)."""
        kind, key = held
        if kind == _VALUE:
            handed = self._index.handed.get((method, key), ())
            nested = self._index.nested.get((method, key), ())
        else:
            handed = self._index.handed_parameters.get((method, key), ())
            nested = self._index.nested_parameters.get((method, key), ())
        held_type = self._type_of(method, held)
        unread = (
            () if held_type is None else self._index.unread_receivers.get((method, held_type), ())
        )
        events: list[_Event] = []
        # A call reaching the value below the top level of an argument (M3), and a call on a
        # receiver the facts cannot name, of the value's own type (M4): either may be what
        # changes it, and neither can be followed.
        for ordinal in (*nested, *unread):
            if not inside(ordinal):
                continue
            events.append((ordinal, (((), ESCAPES),), None))
        for ordinal, slot in handed:
            if not inside(ordinal) or (method, ordinal) in self._read_sites:
                continue
            events.append((ordinal, self._handed_to(method, ordinal, slot), None))
        return events

    def _handed_to(self, method: str, ordinal: int, slot: int) -> tuple[_Window, ...]:
        """The paths a hand-off at `(method, ordinal)`, argument `slot`, takes: one step where
        a catalog states the call's effect at that argument (rule 7); else one body's
        window per callee `call_edges` resolves (rule 1), or `escapes` where there is none —
        code this module does not have — or where the call is through a type a lambda in this
        module implements, whose bodies `dispatch` does not list (fix round 1, M5). A `dynamic`
        site is a lambda's capture, read by `_captured`.

        Bodies that all do the same thing are one path; otherwise each path records which
        body it took (`_HANDED_TO`), so two reads of one hand-off agree on the body."""
        row = self._index.sites.get((method, ordinal))
        self._depends((READ_CALLEES, (method, ordinal)))
        callees = self._index.callees.get((method, ordinal), ())
        # Rule 7 (ruled by the user 2026-11-02): a call a catalog states the effect of is not
        # code we do not have, whatever its body. The statement says the parts it does not
        # bind stay as they were, so the path goes on, with the call written on it for the
        # reader of the part it binds (`Path.stated`).
        if row is not None and (*_call_of(row), slot) in self._index.stated:
            # Where the statement says the call hands the value on to a method the module
            # may implement (a listener), each such body is read as a lambda's capture is
            # (`_captured`): one that does anything to its parameter, or bodies that cannot
            # be listed, make the hand-off `escapes` (rule 2).
            stated = (*_call_of(row), slot)
            if stated in self._index.stated_hands:
                bodies = self._index.stated_hands[stated]
                if bodies is None:
                    return (((), ESCAPES),)
                for body, parameter in bodies:
                    touched = self._touched_in(body, parameter)
                    if touched is not None:
                        return (((), touched),)
            return (((_Step((_STATED, method, ordinal, slot), _STATED),), ()),)
        if row is not None and row.get("invoke_kind") == "dynamic":
            return self._captured(method, ordinal, slot)
        if row is None or not callees:
            return (((), ESCAPES),)
        if str(row.get("owner")) in self._index.lambda_types:
            return (((), ESCAPES),)
        # A stated call inside the entered body records the call that ENTERED it (review 2,
        # C1): each call of one helper is its own execution, so a reader of what that stated
        # call was handed reads it through this hand-off, never through another call of the
        # helper (`Path.stated`).
        # So does each call the body itself gathered (concern 6): its arguments are read through
        # this hand-off.
        found = [
            (
                callee,
                _entered_through((*steps, *_gathered_steps(callee, outcome)), method, ordinal),
                outcome,
            )
            for callee in callees
            for steps, outcome in self._window_at(method, ordinal, callee, slot)
        ]
        alike = tuple(dict.fromkeys((steps, outcome) for _, steps, outcome in found))
        if len(alike) == 1:
            return alike
        context = (_HANDED_TO, method, ordinal)
        return tuple(
            dict.fromkeys(
                (merged, outcome)
                for callee, steps, outcome in found
                if (merged := _combine((_Step(context, callee),), steps)) is not None
            )
        )

    def _window_at(self, method: str, ordinal: int, callee: str, slot: int) -> tuple[_Window, ...]:
        """`_entered_window` for the parameter of `callee` the argument at `slot` fills (R2:
        by name where the module's calls name arguments); `escapes` where it fills none that
        can be named, since then what the callee does with it is not read."""
        parameter = self._index.parameter_of(method, ordinal, callee, slot)
        if parameter is None:
            return (((), ESCAPES),)
        return self._entered_window(callee, parameter)

    def _captured(self, method: str, ordinal: int, slot: int) -> tuple[_Window, ...]:
        """A value handed to a `dynamic` site (spec 2026-11-02 rule 2 as amended in fix round
        1, M6): a lambda's capture. The capture fold (`value_index`, OI-150/OI-266) says which
        parameter of which body it lands on. A body that does NOTHING to that parameter — no
        call on it, no hand-off of it, no field write — cannot change the value, so the capture
        is no hand-off. A body that does anything is `escapes`, gathered or not: when the body
        runs is not known, so what it does cannot be placed in the window. A capture the fold
        does not map (a receiver `this`, a site with no body) is `escapes`."""
        mapped = self._index.captured_as.get((method, ordinal, slot))
        if mapped is None:
            return (((), ESCAPES),)
        touched = self._touched_in(*mapped)
        if touched is not None:
            return (((), touched),)
        return (((), ()),)

    def _touched_in(self, body: str, parameter: int) -> str | None:
        """Whether a body that runs at a time the window cannot place — a lambda's, a
        listener's — does anything to its `parameter`: None where it does nothing, `escapes`
        where it does, and `cycle` where the walk is already reading that body for that
        parameter (review 2, M2: a listener that schedules the job it is handed is handed it
        again). Read once per walk, as `_entered_window` is, and guarded the same way."""
        key = (body, parameter)
        if key in self._touched:
            return self._touched[key]
        if key in self._entering_bodies:
            return CYCLE
        self._entering_bodies.add(key)
        try:
            events = self._events(body, (_PARAMETER, parameter), -1, None, True)
        finally:
            self._entering_bodies.discard(key)
        found = ESCAPES if events else None
        self._touched[key] = found
        return found

    def _type_of(self, method: str, held: tuple[str, int]) -> str | None:
        """`held`'s own type, in a descriptor's spelling, where the facts state it: what its
        producer is declared to return or the type a construction built, or a parameter's
        declared type."""
        kind, key = held
        if kind == _VALUE:
            return self._index.value_types.get((method, key))
        declared = self._index.parameter_types.get(method, ())
        erased = declared[key] if key < len(declared) else None
        return None if erased is None else slot_of_type(erased)

    def _entered_window(self, callee: str, parameter: int) -> tuple[_Window, ...]:
        """What `callee` does to its `parameter` over its whole body — the window of a value
        handed to it, since the body runs to its end before the caller's next call. Entering
        one already being read on this path is `cycle`."""
        key = (callee, parameter)
        cached = self._windows.get(key)
        if cached is not None:
            return cached
        if key in self._entering:
            return (((), CYCLE),)
        self._entering.add(key)
        try:
            found = self._window(callee, (_PARAMETER, parameter), -1, None, in_body=True)
        finally:
            self._entering.discard(key)
        if all(outcome != CYCLE for _, outcome in found):
            self._windows[key] = found
        return found

    def _accessor(self, site_key: tuple[str, int]) -> bool:
        """Whether a call made ON a value is an accessor: it takes no argument and hands back
        an object of a type that is neither its owner nor one of the owner's supertypes.

        **What an accessor does NOT do is change which call produced the value — and that
        is all it is safe to say.** It does not follow that it writes nothing into the
        value: `getJobDataMap()` hands back a LIVE view, and `.put(k, v)` on it writes into
        the `JobDetail`; `list.listIterator().set(x)`, `map.keySet().remove(k)` and MyBatis
        `createCriteria()` write the same way. So whether a write through a returned view
        matters depends on the QUESTION, and this is a reader's switch like `branches` and
        `along_receivers`, never the default:

        * **which call built the value** (`producers_of(..., past_accessors=...)`: the
          Quartz job and trigger pairing, the `fluent` execute-join) — no write after the
          fact changes it, so the accessor is let past. RuoYi-Vue, NBlog and aurora all
          write `jobDetail.getJobDataMap().put(KEY, job)` between building the job and
          scheduling it, and each lost its job to the window before this.
        * **what the value holds** (`resolve_site`, its `identified_by` producers, and every
          `producers_of` reader that reads the producer's arguments as the value's content)
          — a write through a view can change it: `topics = Arrays.asList("a", "b");
          topics.listIterator().set("c"); subscribe(topics)` would publish `a`, `b` as
          exact. The window keeps refusing it.

        **Why each half of the rule is there**, for the reader that turns it on:

        * **No argument.** A call taking anything (`setFilename(x)`, `map.put(k, v)`) can
          write what its caller hands it, and stays in the window. A void call stays too
          (`touch()`, `clear()`): with no result it has nothing to be FOR but its effect.
        * **A result of another reference type.** A result of the owner's own type, or of
          one of its supertypes (an inherited fluent step, an erased self-type bound), may
          be the receiver itself — the fluent `builder.repeatForever()` — so the call may
          have REPLACED what the reader would pair. The supertypes are read off `ancestors`,
          which holds the types this workspace read; a jar owner's supertypes are not known
          and only the owner itself is excluded for one. A primitive result
          (`incrementAndGet()`) and an array are left in the window: `returned_type` names
          no type for either.
        """
        ancestors = self._past_accessors
        site = self._index.sites.get(site_key)
        if ancestors is None or site is None or site.get("result") is None or site["arguments"]:
            return False
        descriptor = site.get("descriptor")
        returned = returned_type(str(descriptor)) if descriptor else None
        if returned is None or site.get("owner") is None:
            return False
        owner = str(site.get("owner"))
        seen = {owner}
        frontier = [owner]
        while frontier:
            for parent, _, _ in ancestors.get(frontier.pop(), ()):
                if parent not in seen:
                    seen.add(parent)
                    frontier.append(parent)
        return returned not in seen

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
                return self._along(stopped, trail, frames)
        reached: list[_Reached] = []
        for ordinal, callee in self._index.returns.get((method, value), ()):
            row = self._index.sites.get((method, ordinal))
            selfish = () if row is None else self._self_answers(row, callee, row.get("owner"))
            if selfish:
                step = _Step((_RETURN_OF, method, value), f"{callee} returns Self")
                merged = _combine(trail, (step,))
                if merged is not None:
                    reached.extend((merged, answer) for answer in selfish)
                continue
            for return_ordinal, entry in self._index.returned_values.get(callee, ()):
                step = _Step((_RETURN_OF, method, value), f"{callee} returns {return_ordinal}")
                merged = _combine(trail, (step,))
                if merged is None:
                    continue
                reached.extend(
                    self._typed_returns(
                        self._entry(
                            entry,
                            callee,
                            (_RETURN_OF, callee, return_ordinal),
                            merged,
                            frames + ((callee, (method, ordinal)),),
                        ),
                        (method, ordinal),
                        callee,
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
                if stopped is not None and self._along_receivers:
                    # A construction is a chain's first call (ruling 5, spec 2026-10-30):
                    # nothing is called before the object exists, so the chain is whole.
                    # Its `receiver` is the object it builds, which `_along` would read
                    # as a value the chain was called on.
                    here = (method, constructed)
                    return _only(
                        trail,
                        replace(stopped, value=replace(stopped.value, chain=(here,), rooted=True)),
                    )
                if stopped is not None:
                    return _only(trail, stopped)
            slot = None if constructed is None else self._identified((method, constructed))
            if constructed is None or slot is None:
                return _only(trail, _unresolved(NOT_READABLE))
            return self._with_class(
                (method, constructed),
                slot,
                self._resolve((_SLOT, method, constructed, slot), trail, frames),
                trail,
                frames,
            )
        site = (method, min(producers))
        # **A call that returns its own receiver hands back that same object** (ruling 4,
        # spec 2026-10-30), for the reader asking which object a value is (`which_object`):
        # `router.errorHandler(500, h)` IS `router`, so the walk goes on through its receiver.
        # The value walk declares no such call and never reaches this.
        row = self._index.sites.get(site)
        if self._which_object and row is not None and _call_of(row) in self._configuring:
            return self._resolve((_SLOT, site[0], site[1], RECEIVER), trail, frames)
        # **A stated library call hands back one of its arguments** (design
        # 2026-11-06-reading-decorators §3d, §3e): the value is that argument, read on.
        stated = None if row is None else self._stated_value(site, row, trail, frames)
        if stated is not None:
            return stated
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
            identified = self._with_class(
                site,
                slot,
                self._resolve((_SLOT, site[0], site[1], slot), trail, frames),
                trail,
                frames,
            )
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
                self._depends((READ_REACHED, site))
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
        # **A construction that hands its object back is that object** (spec 2026-11-06 §3b):
        # a call of a class, read as its `<init>` by the projection (`effective_calls`), with
        # the `result` a JVM construction never has, holds an instance of the class it names —
        # what an `instance` entry answers for a `new`. After every identity arm, as a `new`'s
        # symbol answer is after its identified construction (`_entry`).
        if (
            row is not None
            and row["name"] == _INIT
            and row.get("invoke_kind") == "special"
            and row.get("owner") is not None
        ):
            return _only(trail, Answer(kind=LITERAL, value=str(row["owner"]), literal_kind=SYMBOL))
        # **A class object called is a construction of the class it was called through**
        # (ruling R37): `cls()` in a classmethod, or `c()` with `c: type[X]`, written as a
        # `virtual` `<init>` on `X`. Which class that is is the closed list of `X` and its
        # subtypes, one answer each, with `external` beside them where a type in their lookup
        # orders was not read and may be one more (the shape R33 reads an attribute by).
        if (
            row is not None
            and row["name"] == _INIT
            and row.get("invoke_kind") == "virtual"
            and row.get("owner") is not None
        ):
            return self._constructed_through(str(row["owner"]), trail)
        # **A call whose owner the facts left to the resolver returns what the method its
        # receiver's type runs returns**, on each path the receiver is read by.
        if row is not None and row.get("owner") is None and row.get("invoke_kind") != DYNAMIC:
            return self._bound_returns(site, row, value, trail, frames)
        # **A method with no body read here answers with the type it declares** (OI-324 part
        # 2), for the type reader: a `Protocol` or abstract method, whose declaration is the
        # only answer the code gives.
        if row is not None and row.get("owner") is not None:
            declared = self._declared_answers(row, str(row["owner"]), None)
            if declared:
                return tuple((trail, answer) for answer in declared)
        # Nothing identifies it. Whether its BODY was read is what separates the two
        # reasons, and `call_edges` is the table that says so — it writes a row per site
        # with a NULL callee at the third-party boundary. MEASURED on `mall-admin`: 1,411
        # of 2,065 value-producing sites are that boundary, so `external` is the common
        # answer and not the corner case.
        self._depends((READ_REACHED, site))
        if site in self._index.reached:
            return _only(trail, _unresolved(NOT_READABLE))
        return _only(trail, replace(_unresolved(EXTERNAL), made_by=site))

    def _stated_value(
        self,
        site: tuple[str, int],
        row: Mapping[str, Any],
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...] | None:
        """The value a call a value model states makes (`ValueIndex.stated_returns`, design
        2026-11-06-reading-decorators §3d and §3e), or None where no statement applies:

        - `returns: N` on the call: the value is its argument N (`Objects.requireNonNull`);
        - `result_returns: N` on the call that made this call's RECEIVER, in this method: this
          call applies a decorator that hands its argument back, so the value is this call's
          argument N (click's `option(...)` applied to a function is the function);
        - `result_calls: N` on the call, for the reader asking what a CALL of the value runs
          (`functions`): calling the wrapper runs the call's argument N, so the value stands
          for that function (`functools.cache(f)` runs `f`). Only an answer naming a function
          is kept: a factory spelling whose argument N is no function (`lru_cache(128)`)
          states nothing here, and the call ends as any library call does.

        Positions count positional arguments only (`argument_slot`); an argument the call does
        not write, or one an unpacked value may be, is `not_readable`. The decorator's receiver
        is matched in the same method because that is where a decorator stack is written: the
        decorator expression is evaluated beside the `def`."""
        stated = self._index.stated_returns
        if not stated:
            return None
        method = site[0]
        own = stated.get((str(row.get("owner")), str(row["name"])))
        if own is not None and own[0] == _RETURNS:
            return self._stated_slot(site, row, own[1], trail, frames)
        if own is not None and own[0] == _RESULT_CALLS and self._functions:
            runs = tuple(
                reached
                for reached in self._stated_slot(site, row, own[1], trail, frames)
                if called_function(reached[1]) is not None
            )
            return runs or None
        receiver = row.get("receiver")
        if row["name"] != _CALL or row.get("owner") is not None or receiver is None:
            return None
        made = self._index.producers.get((method, int(str(receiver))))
        maker = self._index.sites.get((method, min(made))) if made else None
        applied = (
            None if maker is None else stated.get((str(maker.get("owner")), str(maker["name"])))
        )
        if applied is None or applied[0] != _RESULT_RETURNS:
            return None
        return self._stated_slot(site, row, applied[1], trail, frames)

    def _stated_slot(
        self,
        site: tuple[str, int],
        row: Mapping[str, Any],
        position: int,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """The value of `row`'s positional argument `position`, read on this path."""
        slot = argument_slot(row["arguments"] or [], position)
        if slot is None or slot == UNPACKED_SLOT:
            return _only(trail, _unresolved(NOT_READABLE))
        return self._resolve((_SLOT, site[0], site[1], slot), trail, frames)

    def _constructed_through(self, owner: str, trail: _Trail) -> tuple[_Reached, ...]:
        """The classes a call of the class object `owner` may construct: `owner` and each of
        its subtypes, one answer each, and `external` where one of their lookup orders left
        the scanned code."""
        dispatch = self._index.dispatch
        types = [owner, *(() if dispatch is None else dispatch.subtypes.get(owner, ()))]
        reached: list[_Reached] = [
            (trail, Answer(kind=LITERAL, value=type_, literal_kind=SYMBOL)) for type_ in types
        ]
        if dispatch is not None and any(dispatch.order_boundary(t) is not None for t in types):
            reached.append((trail, _unresolved(EXTERNAL)))
        return tuple(reached)

    def _bound_returns(
        self,
        site: tuple[str, int],
        row: Mapping[str, Any],
        value: int,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """What a call with no owner in its facts hands back (spec 2026-11-06 §3b): its
        receiver, read on this path, names the type whose method runs (`bound_owner`); the
        answer is that method's returns, read in its frame, on the receiver's own path — so
        a helper called with a `Session` on one path and a `Client` on another returns what
        `Session`'s method returns on the first and `Client`'s on the second, never both on
        either (ruling M-1). The step written is a return crossing's, as `_value` writes for
        a call `return_flows` names. A receiver path naming no type answers its own reason;
        a type whose method has no body read here answers `external` where the lookup left
        the scanned code, and `not_readable` where it did not."""
        method, ordinal = site
        dispatch = self._index.dispatch
        reached: list[_Reached] = []
        for path, answer in self._resolve((_SLOT, method, ordinal, RECEIVER), trail, frames):
            # **Calling a function value runs that function** (ruling R29): the call returns
            # what its body returns, read in its frame — a decorator factory's inner
            # `decorator(endpoint)` hands back the function it was applied to. The body is the
            # one `call_edges` bound this call to, named by the value.
            function = called_function(answer) if row["name"] == _CALL else None
            bodies = [
                callee
                for callee in self._depended(site)
                if function is not None and bare_descriptor(callee) == function
            ]
            if bodies:
                entered = False
                for callee in bodies:
                    for return_ordinal, entry in self._index.returned_values.get(callee, ()):
                        step = _Step(
                            (_RETURN_OF, method, value), f"{callee} returns {return_ordinal}"
                        )
                        merged = _combine(path, (step,))
                        if merged is None:
                            continue
                        entered = True
                        reached.extend(
                            self._entry(
                                entry,
                                callee,
                                (_RETURN_OF, callee, return_ordinal),
                                merged,
                                frames + ((callee, (method, ordinal)),),
                            )
                        )
                if not entered:
                    # A body that states no return this path can enter (none written, or every
                    # one on another path): the value is not read, and the path says so.
                    reached.append((path, _unresolved(NOT_READABLE)))
                continue
            owner = bound_owner(answer)
            if owner is not None and row["name"] == _CALL and answer.class_object:
                # Calling a class constructs it (ruling R37): an instance of that class.
                reached.append((path, Answer(kind=LITERAL, value=owner, literal_kind=SYMBOL)))
                continue
            if owner is None or dispatch is None:
                reached.append(
                    (path, answer if answer.kind == UNRESOLVED else _unresolved(NOT_READABLE))
                )
                continue
            bound = {**row, "owner": owner}
            found = False
            for callee in dispatch.candidates(bound):
                selfish = self._self_answers(row, callee, owner)
                if selfish:
                    found = True
                    reached.extend((path, answer) for answer in selfish)
                    continue
                for return_ordinal, entry in self._index.returned_values.get(callee, ()):
                    found = True
                    step = _Step((_RETURN_OF, method, value), f"{callee} returns {return_ordinal}")
                    merged = _combine(path, (step,))
                    if merged is None:
                        continue
                    reached.extend(
                        self._typed_returns(
                            self._entry(
                                entry,
                                callee,
                                (_RETURN_OF, callee, return_ordinal),
                                merged,
                                frames + ((callee, (method, ordinal)),),
                            ),
                            site,
                            callee,
                            owner,
                        )
                    )
            if not found:
                declared = self._declared_answers(row, owner, None)
                if declared:
                    reached.extend((path, answer) for answer in declared)
                    continue
                unread = dispatch.boundary(owner, str(row["name"]), str(row["descriptor"]))
                reached.append((path, _unresolved(NOT_READABLE if unread is None else EXTERNAL)))
        return tuple(reached)

    def _self_answers(
        self, row: Mapping[str, Any], callee: str, owner: object
    ) -> tuple[Answer, ...]:
        """For the type reader, what a call of a method declared `-> Self` gives on this
        path: the class the call was made through, `owner` — exactly, where the walk bound
        it; where the call is made on the method's own receiver (`self.m()`, `cls.m()`, no
        receiver in the facts), that class or any subclass, one answer each (ruling R37's
        list). The body is not read for it: what it builds (`cls()`) is that same class.
        Empty where the method does not declare `Self`, or nothing named the class."""
        if not self._declared_types or owner is None:
            return ()
        written = self._index.declared_returns.get(bare_descriptor(callee))
        if written is None or written.get("symbol") != _SELF:
            return ()
        if str(row["name"]) != method_name(bare_descriptor(callee)):
            return ()
        if f"{owner_of(bare_descriptor(callee))}{row['name']}." in self._index.static_fields:
            return ()
        named = str(owner)
        if (
            row.get("invoke_kind") == "virtual"
            and row.get("receiver") is None
            and row.get("receiver_parameter") is None
            and row.get("receiver_field") is None
        ):
            return tuple(
                replace(answer, declared=True) if answer.kind == LITERAL else answer
                for _, answer in self._constructed_through(named, ())
            )
        return (Answer(kind=LITERAL, value=named, literal_kind=SYMBOL, declared=True),)

    def _typed_returns(
        self,
        reached: tuple[_Reached, ...],
        site: tuple[str, int],
        callee: str,
        owner: str | None = None,
    ) -> tuple[_Reached, ...]:
        """For the type reader, each return path of `callee` the body answers with no type
        answered instead with the type the method declares (`_declared_answers`): the body's
        own answer stays wherever it names a type, a function or `None`. Every other reader
        gets `reached` as it is. Only a call that names the method takes its declaration: a
        `__call__` that reaches a function's body through a value (a wrapper a decorator made,
        ruling R29) gives what the wrapper returns, which the function does not declare."""
        if not self._declared_types:
            return reached
        row = self._index.sites.get(site)
        if row is None or str(row["name"]) != method_name(bare_descriptor(callee)):
            return reached
        found: list[_Reached] = []
        for path, answer in reached:
            if answer.kind != UNRESOLVED:
                found.append((path, answer))
                continue
            named = owner if owner is not None else row.get("owner")
            declared = self._declared_answers(
                row, None if named is None else str(named), bare_descriptor(callee)
            )
            if declared:
                found.extend((path, one) for one in declared)
            if not declared or answer.reason == EXTERNAL:
                # A path the body answers from code not scanned (`return Mock()`) is an answer
                # of its own: it stays beside the declaration, which may not hold for it.
                found.append((path, answer))
        return tuple(found)

    def _declared_answers(
        self, row: Mapping[str, Any], owner: str | None, body: str | None
    ) -> tuple[Answer, ...]:
        """The types a call's result is DECLARED to be, for the type reader: what `body`
        (the method a return path came from) declares, else what the method the call names
        on `owner` declares (its lookup order's first declaration). One answer per class of a
        written union; none where the type names no class: `Any`, the root type, `None`, a
        type variable left unfilled, a type the file did not name."""
        dispatch = self._index.dispatch
        if not self._declared_types or dispatch is None or not self._index.declared_returns:
            return ()
        name = str(row["name"])
        written = None if body is None else self._index.declared_returns.get(body)
        if written is not None and body is not None and owner is not None:
            written = self._mapped(written, owner, owner_of(body))
        if written is None and owner is not None:
            declaring, _ = dispatch.resolve(owner, name, str(row["descriptor"]))
            if declaring is None:
                return ()
            body = method_descriptor(declaring, name, str(row["descriptor"]))
            written = self._index.declared_returns.get(body)
            if written is not None:
                written = self._mapped(written, owner, declaring)
        if written is None or body is None:
            return ()
        if f"{owner_of(body)}{name}." in self._index.static_fields:
            # A decorated name holds what its decorators made (`f = dec(f)`, design
            # 2026-11-06-reading-decorators §3e): its call is that value's, which the
            # function's own declaration does not describe.
            return ()
        return tuple(
            Answer(kind=LITERAL, value=member, literal_kind=SYMBOL, declared=True)
            for member in declared_classes_of(self._index, written)
        )

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

    def _along(self, stopped: Answer, trail: _Trail, frames: "_Frames") -> tuple[_Reached, ...]:
        """A declared producer, as the reader asked for it: the end of the path, or — for the
        chain reader — the last call of a chain followed on through its receiver.

        The receiver is resolved on THIS path, in THIS frame stack, so a receiver that is a
        parameter of a helper the walk descended into is the argument at the call it came
        through. Each receiver answer that is itself a declared chain gets this call
        appended; anything else (an unread value, a parameter nothing binds) leaves this
        call as the first one found, not rooted.
        """
        producer = stopped.value
        if not self._along_receivers or producer.caller is None or producer.ordinal is None:
            return _only(trail, stopped)
        here = (producer.caller, producer.ordinal)
        row = self._index.sites.get(here)
        if row is None or (
            row.get("receiver") is None
            and row.get("receiver_parameter") is None
            and row.get("receiver_field") is None
        ):
            return _only(
                trail, replace(stopped, value=replace(producer, chain=(here,), rooted=True))
            )
        reached: list[_Reached] = []
        for crossed, answer in self._resolve((_SLOT, here[0], here[1], RECEIVER), trail, frames):
            if answer.kind == _PRODUCED and answer.value.chain:
                chained = replace(
                    producer, chain=(*answer.value.chain, here), rooted=answer.value.rooted
                )
                reached.append((crossed, replace(stopped, value=chained, inexact=answer.inexact)))
            else:
                reached.append((crossed, replace(stopped, value=replace(producer, chain=(here,)))))
        return tuple(reached) or _only(
            trail, replace(stopped, value=replace(producer, chain=(here,)))
        )

    def _passed_through(
        self,
        candidates: "list[Mapping[str, Any]]",
        method: str,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...] | None:
        """For the chain reader only: a merge whose every candidate is the result of a
        DECLARED call on one shared receiver — `c ? b.stepA() : b.stepB()` — is that
        receiver's chain, followed on the same path, `inexact` because which step ran is not
        known. None for any other merge, and always for every other reader, whose answers are
        unchanged.

        This is `_merged`'s shared-root rule one step further out: there the root is one of
        the candidates (`x` beside `f(x)`); here it is what every candidate is a call ON. A
        reader asking for the call that BUILT a value cannot be given the receiver's producer
        in its place, so the rule stays with the reader that asked for the chain.
        """
        if not self._along_receivers:
            return None
        sites: list[tuple[str, int]] = []
        for candidate in candidates:
            source = candidate.get("source")
            ordinals = (
                self._index.producers.get((method, int(str(source))), ())
                if source is not None
                else ()
            )
            if not ordinals or self._declared_producer((method, min(ordinals))) is None:
                return None
            sites.append((method, min(ordinals)))
        receivers = {
            (
                self._index.sites[site].get("receiver"),
                self._index.sites[site].get("receiver_parameter"),
                self._index.sites[site].get("receiver_field"),
            )
            for site in sites
        }
        if len(receivers) != 1 or receivers == {(None, None, None)}:
            return None
        return tuple(
            (crossed, replace(answer, inexact=True))
            for crossed, answer in self._resolve(
                (_SLOT, sites[0][0], sites[0][1], RECEIVER), trail, frames
            )
        )

    def _declared_producer(self, site: tuple[str, int]) -> Answer | None:
        """The path's end where `site` is a call the producer reader declared, else None.

        Matched on the projected row's `owner` and `name`, exactly — the pair the caller
        declared, with no arity or descriptor, because the question is which call built the
        value and not which overload. The value walk declares nothing, so this answers None
        there before reading anything."""
        if not self._declared and not self._declared_sites:
            return None
        row = self._index.sites.get(site)
        if row is None:
            return None
        identity = (row.get("owner"), row["name"])
        if identity not in self._declared and site not in self._declared_sites:
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

    def _identified_class(self, site: tuple[str, int], slot: int) -> int | None:
        """Which argument of the producing call holds the class literal of what its value
        addresses, or None: the `class_arg` of a matching entry whose `arg` is the slot
        `_identified` picked (spec 2026-11-05 §2). Any such entry, not only the first: one
        producer may be hoisted twice, from a row that reads its class and a row that does
        not, and both spell the same value."""
        for entry in self._identity_matches(site):
            class_arg = entry.get("class_arg")
            if entry.get("arg") == slot and isinstance(class_arg, int):
                return class_arg
        return None

    def _with_class(
        self,
        site: tuple[str, int],
        slot: int,
        identified: tuple[_Reached, ...],
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """`identified`, each answer carrying the class literal the same producing call names
        at its entry's `class_arg` (`Answer.carried_class`), read IN THE SAME CALLING CONTEXT
        (`trail`, `frames`) and paired only where the two paths agree (`_combine`): a helper
        building two keys from its callers' arguments gives each the class its own caller
        passed. An answer no class path agrees with carries none. Unchanged where no entry
        names a class."""
        class_slot = self._identified_class(site, slot)
        if class_slot is None:
            return identified
        classes = self._resolve((_SLOT, site[0], site[1], class_slot), trail, frames)
        carried: list[_Reached] = []
        for crossed, answer in identified:
            agreeing = [
                (merged, class_answer)
                for class_crossed, class_answer in classes
                if (merged := _combine(crossed, class_crossed)) is not None
            ]
            if not agreeing:
                carried.append((crossed, answer))
            for merged, class_answer in agreeing:
                named = (
                    str(class_answer.value)
                    if class_answer.kind == LITERAL and class_answer.literal_kind == SYMBOL
                    else None
                )
                carried.append((merged, replace(answer, carried_class=named)))
        return tuple(dict.fromkeys(carried))

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

    def _distinct(self, reached: list[_Reached]) -> tuple[_Reached, ...]:
        """`reached` with repeats removed, keeping the first of each. For the producer reader
        two `external` answers at two parameters are two ends — the parameter is outside the
        answer's equality (`Answer.parameter`), so it is keyed here too: two field writers
        nothing calls, `m1(p)` and `m2(q)`, name both. So is the library call an `external`
        answer ended at (`Answer.made_by`): one writer writing a field from `a()` on one branch
        and `b()` on the other, both library calls, has two ends (plan 2026-11-08 Task 4). Every other
        reader dedupes on the answer alone, as before, since `resolve_site` does not dedupe
        again and two equal `external` answers would be two bindings saying one thing."""
        if not self._parameters_apart:
            return tuple(dict.fromkeys(reached))
        return tuple(
            {
                (path, answer, answer.parameter, answer.made_by): (path, answer)
                for path, answer in reached
            }.values()
        )

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
        an entry point, or a caller in a dependency nobody read. The answer carries which
        parameter it was (`Answer.parameter`), for the producer reader to name.

        A parameter of a method the producer reader named (`stop_at_parameters_of`) is where
        the path ends, before any caller is read: the reader asked whether the value came
        from this parameter, and every crossing past it answers a different question. **The
        frame answers first**: inside a callee the walk entered through its return, the
        parameter IS the argument at that call — `log(ctx).next()` — and stopping there would
        name a handler that never received this value.
        """
        frame = self._frame_in(frames, method)
        if frame is not None:
            slot = self._index.argument_slot(frame[0], frame[1], method, index)
            if slot == UNFILLED:
                return self._default(method, index, frame, trail, frames)
            return self._resolve((_SLOT, frame[0], frame[1], slot), trail, frames)
        if method in self._stop_at_parameters_of:
            return _only(trail, Answer(kind=_PRODUCED, value=Producer(parameter=(method, index))))
        # **A parameter the container fills receives what the container's recipe makes** (spec
        # 2026-11-05 di-recipe-hop §2), before any caller: its callers are the container's
        # generated code, which the hop mirrors and does not follow. Several recipes of its key
        # in the module is `non_enumerable` (which one the container uses is not in the module).
        # A parameter with no recipe in the module reads as before.
        injected = self._index.injected.get((method, index))
        if isinstance(injected, ProvidedBy):
            return self._filled_by(method, index, injected.provider, trail, frames)
        if isinstance(injected, Ambiguous):
            return _only(trail, _unresolved(NON_ENUMERABLE))
        # **A parameter that names its recipe is also what the framework's call of it hands
        # over** (plan 2026-11-08 N5, ruling R14): one more path BESIDE the callers in the
        # module, never before them, so a caller passing an argument stays its own path. With
        # no caller, it is the only path: the framework's fill is no longer outside the code.
        recipe = (
            self._resolve((_RECIPE_PATHS, method, index), trail, ())
            if self._index.recipes.calls and (method, index) in self._index.parameter_values
            else ()
        )
        self._depends((READ_CALLERS, method))
        callers = self._index.callers.get((method, index), ())
        if not callers:
            return self._open_filled(
                method,
                index,
                trail,
                recipe
                or _only(
                    trail, Answer(kind=UNRESOLVED, reason=EXTERNAL, parameter=(method, index))
                ),
            )
        reached: list[_Reached] = []
        for caller, ordinal, argument in callers:
            if len(reached) > PATH_CAP:
                # The cap bounds the work, not only the answer (R39): past it no more paths
                # are enumerated, and the parameter is one path, `non_enumerable`.
                return self._open_filled(
                    method, index, trail, _only(trail, _unresolved(NON_ENUMERABLE))
                )
            step = _Step((_CALLER_OF, method), f"{caller}@{ordinal}")
            merged = _combine(trail, (step,))
            if merged is None:
                # This path already crossed out of `method` through a different call, so
                # this caller is not on it. Another slot's path holds that caller.
                continue
            if argument == UNFILLED:
                reached.extend(self._default(method, index, (caller, ordinal), merged, frames))
                continue
            reached.extend(self._resolve((_SLOT, caller, ordinal, argument), merged, frames))
        reached.extend(recipe)
        if len(reached) > PATH_CAP:
            return self._open_filled(
                method, index, trail, _only(trail, _unresolved(NON_ENUMERABLE))
            )
        return self._open_filled(method, index, trail, tuple(reached))

    def _default(
        self, method: str, index: int, call: tuple[str, int], trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """Parameter `index` of `method`, which the call at `call` fills with no argument: it
        passes the parameter's `default` (Python's rule, N1), resolved in the frame of the body
        that runs the `def` (`defining_body`), on this caller's path. The origin names the
        parameter and has no ordinal, so the `escapes` window is the rest of that body, as for
        a field a call's result is written to. `_unfilled` where there is no default (every
        JVM parameter), where the body is not known, and where the call's `*` or `**` argument
        may fill the parameter (`unpacked_may_fill`): then no default is passed for certain."""
        held = self._index.parameter_values.get((method, index))
        if held is None or held.default is None or held.body is None:
            return _only(trail, self._unfilled(method, index))
        site = self._index.sites.get(call)
        declared = self._index.call_parameters.get(method, ())
        kind = declared[index][1] if index < len(declared) else None
        if site is None or unpacked_may_fill(site.get("arguments") or [], kind):
            return _only(trail, self._unfilled(method, index))
        return self._entry(held.default, held.body, (_PARAMETER, method, index), trail, frames)

    @staticmethod
    def _unfilled(method: str, index: int) -> Answer:
        """A parameter a caller's call fills with nothing that can be named (R2): its default,
        a `**` mapping, or a place the facts do not decide. `not_readable`, naming the
        parameter, so a reader can say which one."""
        return Answer(kind=UNRESOLVED, reason=NOT_READABLE, parameter=(method, index))

    def _filled_by(
        self, method: str, index: int, recipe: str, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """Parameter `index` of `method` is what `recipe` returns: each of its returns is a path,
        resolved in the recipe's own body with no frame pushed, because no call site in the
        module hands the value over. The recipe's own parameters are container-filled again,
        and a recipe that returns to a position already on the path ends as `cycle`."""
        reached: list[_Reached] = []
        for return_ordinal, entry in self._index.returned_values.get(recipe, ()):
            step = _Step((_FILLED_BY, method, index), f"{recipe} returns {return_ordinal}")
            merged = _combine(trail, (step,))
            if merged is None:
                continue
            reached.extend(
                self._entry(entry, recipe, (_RETURN_OF, recipe, return_ordinal), merged, frames)
            )
        return tuple(reached) if reached else _only(trail, _unresolved(NOT_READABLE))

    def _recipe_paths(
        self, method: str, index: int, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """What the framework hands parameter `index` of `method` where a marker call names its
        recipe (N5): each recipe the parameter's markers name (`recipe_sites`), read as a value
        (`recipe_values`), then run (`_recipe_runs`), one path each. Empty where no marker
        names one, which is every JVM parameter and every Python one no `names_recipe` model
        reads."""
        # Imported here: `parameter_markers` reads every value through this module's walk.
        from sextant.application.resolve.parameter_markers import (
            parameter_markers,
            recipe_sites,
        )

        markers = parameter_markers(self._index).get((method, index), ())
        sites = recipe_sites(markers, self._index.recipes.calls)
        # The framework's call of `method` is a calling context of it (`_FRAMEWORK_CALL`).
        called = _combine(trail, (_Step((_CALLER_OF, method), _FRAMEWORK_CALL),))
        if not sites or called is None:
            return ()
        self._read(self._index.marker_reads.get((method, index), frozenset()))
        reached: list[_Reached] = []
        for site in sites:
            found, reads = _recipe_values(self._index, site, (method, index))
            self._read(reads)
            for path, answer in found:
                merged = _combine(called, path)
                if merged is not None:
                    reached.extend(self._recipe_runs(answer, method, index, merged, frames))
        return tuple(reached)

    def _recipe_runs(
        self, answer: Answer, method: str, index: int, trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...]:
        """What calling the recipe `answer` hands parameter `index` of `method`, by the
        call-of-a-value rules: a class constructs an instance of it (ruling R37); a function
        gives its returns, a generator its yields (N10: the framework enters it as a context
        manager, which allows one yield per run, so every yield is a first one); an instance
        gives what its class's `__call__` returns (ruling R29). Each return is a path, read in
        the recipe's own body with no frame pushed, as `_filled_by` reads a container's recipe.
        A recipe whose body is not read is `external` where its lookup left the scanned code,
        else `not_readable`; an answer naming no callable keeps its own reason."""
        owner = bound_owner(answer)
        if called_function(answer) is None and owner is not None and answer.class_object:
            return _only(trail, Answer(kind=LITERAL, value=owner, literal_kind=SYMBOL))
        if called_function(answer) is None and owner is None:
            return _only(trail, answer if answer.kind == UNRESOLVED else _unresolved(NOT_READABLE))
        reached: list[_Reached] = []
        for body in recipe_runs(self._index, answer):
            reached.extend(self._resolve((_RECIPE_RUN, body), trail, frames))
        if reached:
            return tuple(reached)
        dispatch = self._index.dispatch
        if (
            owner is not None
            and dispatch is not None
            and dispatch.boundary(owner, _CALL, _ANY_ARGUMENTS)
        ):
            return _only(trail, _unresolved(EXTERNAL))
        return _only(trail, _unresolved(NOT_READABLE))

    def _recipe_returns(self, body: str, trail: _Trail, frames: "_Frames") -> tuple[_Reached, ...]:
        """What the recipe `body` hands the framework (`_recipe_runs`): each return, a
        generator's each yield, a path with a `filled-by` step naming it, read in the body's own
        frame with no frame pushed. One position per body, so it is read once and joined onto
        every parameter's path (R39); the framework runs a recipe once per request for every
        parameter it fills (`use_cache`), so two parameters of one execution agree on it."""
        entries = self._index.yielded_values.get(body) or self._index.returned_values.get(body, ())
        reached: list[_Reached] = []
        for return_ordinal, entry in entries:
            step = _Step((_FILLED_BY, body), f"{body} returns {return_ordinal}")
            merged = _combine(trail, (step,))
            if merged is not None:
                reached.extend(
                    self._entry(entry, body, (_RETURN_OF, body, return_ordinal), merged, frames)
                )
        return tuple(reached)

    def _binding(
        self,
        symbol: str,
        trail: _Trail,
        frames: "_Frames",
        unseen: bool = False,
        read_on: tuple[str, int] | None = None,
    ) -> tuple[_Reached, ...]:
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
        namespace, beyond = self._namespace(symbol)
        written_ones = [
            one
            for one in namespace
            if self._index.writers.get(one)
            or self._index.constants.get(one)
            or self._index.produced.get(one)
        ]
        # **A declared attribute is its declaration's type where no write says more**
        # (OI-324 part 2), for the type reader: `client: HttpClient` in a class body (PEP 526),
        # on every type of the read's namespace (ruling R33), one answer per class. A write
        # whose value the walk reads no type of, a write by code nothing scanned, and no write
        # at all (a dataclass's generated `__init__`) take it.
        declared = self._declared_field(namespace)
        if not written_ones and declared:
            return tuple((trail, answer) for answer in declared)
        if not written_ones:
            if beyond:
                return _only(trail, _unresolved(EXTERNAL))
            # **A name a `def` binds is that function** (Python's rule), for the call reader: a
            # file importing it reads it as a field, which nothing writes because the `def` is
            # the binding (`from deps import get_db`, then `Depends(get_db)`). One answer per
            # function of the name, as a `lambda` entry names its body.
            named_functions = (
                self._index.named_functions.get(_named(bare_descriptor(symbol)), ())
                if self._functions
                else ()
            )
            if named_functions:
                return tuple(
                    (trail, Answer(kind=LITERAL, literal_kind=SYMBOL, value=function))
                    for function in named_functions
                )
            named = self._named_type(symbol)
            if named is not None:
                return _only(
                    trail,
                    Answer(kind=LITERAL, value=named, literal_kind=SYMBOL, class_object=True),
                )
            return _only(trail, _unresolved(NO_WRITER))
        reached: list[_Reached] = []
        for one in written_ones:
            reached.extend(self._attribute(one, trail, frames, unseen, read_on))
        if beyond:
            reached.append((trail, _unresolved(EXTERNAL)))
        if declared:
            reached = [
                typed
                for path, answer in reached
                for typed in (
                    [(path, one) for one in declared]
                    + ([(path, answer)] if answer.reason == EXTERNAL else [])
                    if answer.kind == UNRESOLVED
                    else [(path, answer)]
                )
            ]
        return self._distinct(reached)

    def _mapped(
        self, written: Mapping[str, Any], owner: str, declaring: str | None
    ) -> Mapping[str, Any] | None:
        """`written`, declared on `declaring`, as it reads on an `owner`: each type variable
        of `declaring` replaced by what `owner`'s written parents give it (`_mapping`). None
        where two parents give one variable two types: no one answer."""
        own: dict[str, Mapping[str, Any]] = {_SELF: {"symbol": owner}}
        if declaring is None or declaring == owner:
            return _substituted(written, own)
        mappings = self._mapping(owner)
        if mappings is None:
            return None
        return _substituted(written, {**(mappings.get(declaring) or {}), **own})

    def _mapping(self, owner: str) -> dict[str, dict[str, Mapping[str, Any]]] | None:
        """What each generic ancestor of `owner`'s type parameters are on an `owner`, by
        the typing specification: a written parent `RepositoryBase[Product]` gives
        `RepositoryBase`'s parameters its arguments by position, read through the mapping of
        the class that writes it, up every parent with type arguments. None where two paths
        give one class different arguments."""
        memo = self._index.mappings
        if owner in memo:
            return memo[owner]
        found: dict[str, dict[str, Mapping[str, Any]]] = {owner: {}}
        pending = [owner]
        conflict = False
        while pending and not conflict:
            current = pending.pop(0)
            for base in self._index.generic_bases.get(current, ()):
                parent = bare_descriptor(str(base.get("symbol")))
                parameters = self._index.class_parameters.get(parent, ())
                arguments = [
                    _substituted(a, found[current])
                    for a in base.get("arguments") or []
                    if isinstance(a, Mapping)
                ]
                if not parameters or len(parameters) != len(arguments):
                    continue
                given = dict(zip(parameters, arguments, strict=True))
                if parent in found and found[parent] != given:
                    conflict = True
                    break
                if parent not in found:
                    found[parent] = given
                    pending.append(parent)
        memo[owner] = None if conflict else found
        return memo[owner]

    def _open_filled(
        self, method: str, index: int, trail: _Trail, reached: tuple[_Reached, ...]
    ) -> tuple[_Reached, ...]:
        """For the type reader, each path the callers of parameter `index` of `method` leave
        with no value — none calls it, or the path ends `external`, `not_readable`,
        `non_enumerable`, `cycle` or any other reason but `escapes` — keeps its row and gains
        the classes the parameter is written to hold beside it, `declared` (ruling R40, OI-324
        part 2 round 3): the written type is the code's own statement, and replaces nothing;
        the callers' values come first, path by path (`repo: Base` given a `Sub()` is a `Sub`).
        An `escapes` path has a value, changed after it was made, and gains nothing. A written
        type naming no class the workspace knows adds nothing. The written type holds on every
        path into the parameter, so it is one row per class on the parameter's own path, not one
        per open path: the caller paths are not multiplied (the path cap counts them)."""
        if not self._declared_types:
            return reached
        written = self._index.declared_parameters.get((method, index))
        if written is None:
            return reached
        if not any(answer.kind == UNRESOLVED and answer.reason != ESCAPES for _, answer in reached):
            return reached
        declared = tuple(
            Answer(kind=LITERAL, value=member, literal_kind=SYMBOL, declared=True)
            for member in declared_classes_of(self._index, written)
        )
        if not declared:
            return reached
        return (*reached, *((trail, one) for one in declared))

    def _plain_attribute(self, declared: str) -> bool:
        """Whether reading an attribute declared `declared` gives a `declared`: its class is
        one of the module, every type of its lookup order was read, and none defines
        `__get__`. A descriptor's read runs `__get__` (SQLAlchemy's `Mapped[T]` gives a
        `T`), and a library class's methods are not read here, so it may be one."""
        dispatch = self._index.dispatch
        if dispatch is None or declared not in dispatch.scanned:
            return False
        if dispatch.order_boundary(declared) is not None:
            return False
        return not any(
            _GET in dispatch.declared_names.get(type_, ())
            for type_ in dispatch.lookup_order(declared)
        )

    def _declared_field(self, namespace: tuple[str, ...]) -> tuple[Answer, ...]:
        """The classes the fields of `namespace` are declared to hold, for the type reader:
        each declaration's class, or each class of its union. None where the reader is
        another, no field of it is declared, or one declaration names no class (`Any`, a
        type variable, a type the file did not name): the list would not be closed."""
        if not self._declared_types or not self._index.declared_fields:
            return ()
        found: dict[str, None] = {}
        for one in namespace:
            written = self._index.declared_fields.get(one)
            if written is None:
                continue
            members = declared_classes_of(self._index, written)
            if not members or not all(self._plain_attribute(member) for member in members):
                return ()
            found.update(dict.fromkeys(members))
        return tuple(
            Answer(kind=LITERAL, value=member, literal_kind=SYMBOL, declared=True)
            for member in found
        )

    def _attribute(
        self,
        symbol: str,
        trail: _Trail,
        frames: "_Frames",
        unseen: bool,
        read_on: tuple[str, int] | None,
    ) -> tuple[_Reached, ...]:
        """The answers one written binding of `_binding`'s read gives."""
        if unseen:
            return self._from_outside(symbol, trail, frames)
        if read_on is not None:
            scoped = self._object_writes(symbol, read_on, trail, frames)
            if scoped is not None:
                return scoped
        return self._binding_writes(
            self._index.writers.get(symbol, ()),
            self._index.constants.get(symbol, ()),
            self._index.produced.get(symbol, ()),
            symbol,
            trail,
            frames,
        )

    def _namespace(self, symbol: str) -> tuple[tuple[str, ...], bool]:
        """The bindings a read of `symbol` takes the writes of, and whether code nothing
        scanned may write it too (ruling R33).

        **In Python an object's attributes are one namespace**, whichever class's code wrote
        them: `self.d` read in `B` is what `B.__init__` wrote on a `B`, and what `D.__init__`
        wrote over it on a `D(B)`; a class attribute `D` overrides is `D`'s on a `D`. The
        scanner names each write after the class whose body makes it, so a read in `C` takes
        the writes of the same name on every type in the lookup order of `C` and of each of
        its subtypes: `C`, its ancestors, its subtypes, and their other parents. Several are a
        closed list, one answer each. A type in one of those orders that was not read (a
        library parent, `parents_unread`) may write it as well: `external` beside them.

        Only for a `c3` module, and only for a field of a class: javac names the field a JVM
        read resolves to, and a module-level name has no other class. Everywhere else, the
        symbol alone."""
        dispatch = self._index.dispatch
        if dispatch is None or dispatch.lookup != "c3":
            return (symbol,), False
        cached = self._index.namespaces.get(symbol)
        if cached is not None:
            return cached
        owner = owner_of(symbol)
        found: tuple[tuple[str, ...], bool] = ((symbol,), False)
        if owner is not None and (owner in dispatch.ancestors or owner in dispatch.subtypes):
            name = symbol[len(owner) :]
            types: dict[str, None] = {}
            beyond = False
            for type_ in (owner, *dispatch.subtypes.get(owner, ())):
                for each in dispatch.lookup_order(type_):
                    if each != dispatch.root:
                        types[each] = None
                beyond = beyond or dispatch.order_boundary(type_) is not None
            found = (tuple(type_ + name for type_ in types), beyond)
        self._index.namespaces[symbol] = found
        return found

    def _named_type(self, symbol: str) -> str | None:
        """The type a binding nothing writes IS, where it is one (spec 2026-11-06 §3b): a
        name a file imports from another and uses as a value is read as that module's field
        (`app/a#Session.`), because the file cannot see that the name is a class, and no field
        of that name exists. So a binding with no write, declared as no field, whose name is
        a type of its owner's module (`field_type`) that the workspace declares or holds a
        header for, is that type — the answer a `class` entry gives. None anywhere else, so
        `no_writer` keeps its meaning: a declared field, or a name that is no type. On the JVM
        a read field is declared wherever its class was read, and no type is named after a
        member of a class (`member_type`), so nothing there reaches this."""
        return named_type(symbol, self._index.dispatch)

    def _from_outside(self, symbol: str, trail: _Trail, frames: "_Frames") -> tuple[_Reached, ...]:
        """**A field read on an object from outside what was scanned borrows no other
        object's writes** (OI-222, ruled 2026-10-29). A write a setter or a constructor's
        PARAMETER makes is a value for the object that call was made on, and nothing ties
        that object to this one: DolphinScheduler's `CronUtils` sets a default cron on a
        `Schedule` it builds itself, and a trigger reading `schedule.getCrontab()` off a row
        from the database published that default as its schedule. What a constructor writes
        WITHOUT a parameter (an initialiser) every instance gets, so it stays; where anything
        was dropped, `external` stands beside it and the kept value is INEXACT, because the
        dropped writes are proof the value can be something else: an entity's field default
        read off a database row is a default, never the row's value.

        Read for an object every path to which is from outside (`_binding`'s `unseen`), and
        for each such path to an object that other paths place (`_object_writes`)."""
        written = self._index.writers.get(symbol, ())
        constants = self._index.constants.get(symbol, ())
        produced = self._index.produced.get(symbol, ())
        kept_constants = tuple(
            (writer, entry) for writer, entry in constants if _constructs(writer, symbol)
        )
        kept_produced = tuple(
            (writer, entry) for writer, entry in produced if _constructs(writer, symbol)
        )
        overwritten = bool(
            written or len(kept_constants) < len(constants) or len(kept_produced) < len(produced)
        )
        kept = self._binding_writes((), kept_constants, kept_produced, symbol, trail, frames)
        if not overwritten:
            return kept
        return tuple(
            dict.fromkeys(
                [(path, replace(answer, inexact=True)) for path, answer in kept]
                + [(trail, _unresolved(EXTERNAL))]
            )
        )

    def _binding_writes(
        self,
        written: "tuple[tuple[str, int], ...]",
        constants: "tuple[tuple[str | None, Mapping[str, Any]], ...]",
        produced: "tuple[tuple[str, Mapping[str, Any]], ...]",
        symbol: str,
        trail: _Trail,
        frames: "_Frames",
    ) -> tuple[_Reached, ...]:
        """The answers `_binding`'s writes give: each constant as its literal, each parameter
        write through the writer's callers, each call-result write in the writer's frame."""
        reached: list[_Reached] = []
        for _, entry in constants:
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
            # A write of a name that is a type (`_named_type`: an import a file binds on a
            # branch, `try: from a import Session as S`) is that type, the answer its read
            # would give.
            named = (
                self._named_type(str(entry["symbol"]))
                if entry.get("kind") == "field" and entry.get("symbol") is not None
                else None
            )
            if literal_kind is not None and entry.get("value") is not None:
                reached.append(
                    (trail, Answer(kind=LITERAL, value=entry["value"], literal_kind=literal_kind))
                )
            elif named is not None:
                reached.append(
                    (
                        trail,
                        Answer(kind=LITERAL, value=named, literal_kind=SYMBOL, class_object=True),
                    )
                )
            # A container a binding is written with (`VERBS = ["GET"]`) is NOT read element by
            # element: the code may change it after the write (`VERBS.append(...)`, `VERBS[0] =
            # ...`, `del`, `+=`, a callee it is handed to, another file), and the facts state
            # neither an index store nor whether the literal was a tuple, so they cannot show
            # it unchanged. Its first value read at `resolved` would be a lie (task 5
            # re-review).
            else:
                reached.append((trail, _unresolved(NOT_READABLE)))
        for method, index in written:
            if len(reached) > PATH_CAP:
                return _only(trail, _unresolved(NON_ENUMERABLE))
            reached.extend(self._resolve((_PARAMETER, method, index), trail, frames))
        for method, entry in produced:
            # The origin names the write and has no ordinal, so `_through`'s `escapes` window
            # is the whole of the writing method after the call: a call made on the stored
            # object anywhere there changes what every later reader of the field sees.
            reached.extend(self._entry(entry, method, (_BINDING, symbol, method), trail, frames))
        if len(reached) > PATH_CAP:
            return _only(trail, _unresolved(NON_ENUMERABLE))
        return self._distinct(reached)

    def _object_site(
        self, symbol: str, frames: "_Frames", reader: str | None
    ) -> tuple[str, int] | None:
        """The getter call the instance field `symbol` was read through, where the read can
        be placed on an object, and None everywhere else.

        It can be placed in the method that READS the field (`reader`), when that is the
        method the walk descended into through an instance call (`frames`' innermost),
        declared by the field's own type — a getter, `schedule.getCrontab()`. A read anywhere
        else is the method's own `this`, or a shape this does not place, and is answered as
        it always was. A field the facts mark `static` holds one value for every reader and
        is never placed."""
        if self._base is not None and len(frames) <= self._base:
            self._reads.append((_LAST, frames[-1] if frames else None))
        if not frames or reader is None or symbol in self._index.static_fields:
            return None
        callee, (caller, ordinal) = frames[-1]
        if callee != reader or owner_of(bare_descriptor(callee)) != owner_of(symbol):
            return None
        site = self._index.sites.get((caller, ordinal))
        if site is None or site.get("invoke_kind") == "static":
            return None
        return (caller, ordinal)

    def _unseen_object(self, symbol: str, frames: "_Frames", reader: str | None) -> bool:
        """Whether the instance field `symbol` is read on an object that arrives from no code
        this module has — a parameter of a method nothing here calls, through any number of
        locals, parameters and fields.

        Asked only where the read can be placed on an object (`_object_site`).

        The object is followed by the producer reader with every library call declared
        (`ValueIndex.unscanned`), so one a library call hands back — `List.get`, a mapper —
        ends at that call and is NOT unseen: it may be an object this module built and put
        there. Only every path ending `external` with no call at all is. Telling two objects
        the module builds apart is `_object_writes`, not this rule."""
        read_on = self._object_site(symbol, frames, reader)
        if read_on is None:
            return False
        site = self._index.sites[read_on]
        # Asked as WHICH OBJECT (`which_object`): a call made on it before the read — now read
        # inside the reading method too (fix round 1, C1) — does not make it another object.
        ends = [
            end
            for end, _ in producer_paths(
                self._index, site, RECEIVER, self._index.unscanned, which_object=True
            )
        ]
        return bool(ends) and all(end.caller is None and end.reason == EXTERNAL for end in ends)

    def _object_writes(
        self, symbol: str, site: tuple[str, int], trail: _Trail, frames: "_Frames"
    ) -> tuple[_Reached, ...] | None:
        """A field read through the getter call `site` answers only the writes made on the
        object that call was made on (ruling 1, 2026-10-30), or None where the read cannot
        be held to one object and answers as it did before.

        `Row a = new Row(); a.setCron("A"); Row b = new Row(); b.setCron("B");
        one(a.getCron())` is `A`. Keyed on the field symbol alone, the read was `A` and `B`,
        both exact, and `pair(a.getCron(), a.getZone())` paired one object's cron with the
        other's zone.

        **Which objects.** The getter's receiver is followed to the constructions of the
        field's own type (`_objects`). An end that is not one — a parameter nothing binds, a
        library call — is an object from outside and answers as one (`_from_outside`,
        OI-250). An end at a construction of a SUBTYPE built here is not from outside: it
        answers every write of the field, as the read did before (final review, Minor 5).
        Only where no end is a construction is the read not placed, and it answers as
        before.

        **What each object holds.** For each construction `C`:

        * what the constructors write. A parameter write reads the argument at `C`, through
          the frame of the constructor `C` calls; a write without a parameter is every
          instance's.
        * what each CALL of another writing method writes, where that call was made on `C`:
          a setter's parameter is the argument at that call. A call made on an object the
          walk cannot place may be made on any object, so it stays for every `C`, INEXACT.
          A writing method nothing here calls is answered as before: whatever calls it is
          outside what was scanned.

        **Coherence.** Each answer is on the path its receiver took, and on two steps keyed on
        the receiver as the reading method holds it (`_receiver_of`): `_OBJECT_OF` names `C`
        and `_WRITE_OF` names the write. Two reads on one receiver are one object reading one
        write; two receivers are free to be two objects, which `pair(a.getCron(),
        b.getCron())` needs.

        **Recorded, not handled.** A constructor overload `C` does not call, and does not
        delegate to, still contributes its writes, as before.
        """
        owner = owner_of(symbol)
        if owner is None or (symbol, site) in self._asking:
            return None
        if str(owner) not in self._index.constructed:
            # Nothing here builds the type, so no end of the object walk could be a
            # construction: answered as before without walking (GUIDELINES §8.7).
            return None
        # **This read is in progress in every walk it starts**, the receiver's and each
        # setter call's: a setter called on an object read through a getter of the same field
        # (`a.getNext().setNext(…)`), or a cycle through two fields, reaches this read again,
        # and the walk that would ask it answers as it did before ruling 1 instead.
        asking = self._asking | {(symbol, site)}
        # `_base` is None outside an object walk, and 0 for one started with no frames of the
        # asker's: neither has asker's frames to record a read of.
        if self._base:
            # What follows reads the asker's frames whole (an object walk keyed on them, the
            # receiver's frame): this walk's answer serves only the very same frames.
            self._reads.append((_WHOLE,))
        outer = frames[:-1]
        read = self._objects(symbol, site, outer, asking)
        if all(built is None for built, _, _, _ in read):
            return None
        receiver = self._receiver_of(self._index.sites[site], outer)
        groups = self._writes_by(symbol)
        calls = self._setter_calls_of(symbol, asking)
        reached: list[_Reached] = []
        for built, crossed, entered, subtype in read:
            on_path = _combine(trail, crossed)
            if on_path is None:
                continue
            step = _Step(
                (_OBJECT_OF, *receiver), "-" if built is None else f"{built[0]}@{built[1]}"
            )
            on_object = _combine(on_path, (step,))
            if on_object is None:
                continue
            if subtype:
                # **A subtype built here is not an object from outside** (final review, Minor
                # 5): `new AdminProps()` where the field is `BaseProps`'s. Its own writes are
                # not told apart from the other objects' yet, so that end answers what the read
                # answered before ruling 1, every write of the field — never `external`.
                written, constants, produced = (
                    self._index.writers.get(symbol, ()),
                    self._index.constants.get(symbol, ()),
                    self._index.produced.get(symbol, ()),
                )
                reached.extend(
                    self._binding_writes(written, constants, produced, symbol, on_object, frames)
                )
                continue
            if built is None:
                # **One path from outside does not unplace the others** (OI-250): ruoyi's
                # `adminApi` is the object `WebProperties` builds, or whatever its `@Data`
                # setter, which nothing here calls, is handed. That second object is from
                # outside, and answers what one does (`_from_outside`), never the other
                # construction's `/app-api`.
                reached.extend(self._from_outside(symbol, on_object, frames))
                continue
            constructed = self._index.sites[built]
            constructor = with_descriptor(
                frames[-1][0],
                method_descriptor(
                    str(constructed["owner"]),
                    str(constructed["name"]),
                    str(constructed["descriptor"]),
                ),
            )
            for writer, writes in groups.items():
                if writer is None or _constructs(writer, symbol):
                    entered_by = (constructor, built)
                    reached.extend(
                        self._written(
                            symbol, writer, "-", writes, on_object, receiver, frames, entered_by
                        )
                    )
                    continue
                self._depends((READ_CALLED_AT, writer))
                if writer not in self._index.called_at:
                    # Called by nothing here, so by something outside what was scanned, on
                    # an object nothing says: what a call on an unplaced object writes.
                    reached.extend(
                        (path, replace(answer, inexact=True))
                        for path, answer in self._written(
                            symbol, writer, "-", writes, on_object, receiver, frames, None
                        )
                    )
                    continue
                for called, call, ends in calls:
                    if called != writer:
                        continue
                    for target, made, made_entered, _ in ends:
                        if target is not None and (
                            target != built or _combine(entered, made_entered) is None
                        ):
                            continue
                        merged = _combine(on_object, made)
                        if merged is None:
                            continue
                        answers = self._written(
                            symbol,
                            writer,
                            f"{call[0]}@{call[1]}",
                            writes,
                            merged,
                            receiver,
                            frames,
                            (writer, call),
                        )
                        reached.extend(
                            answers
                            if target is not None
                            else [(path, replace(answer, inexact=True)) for path, answer in answers]
                        )
        return self._distinct(reached)

    def _written(
        self,
        symbol: str,
        writer: str | None,
        at: str,
        writes: "_Writes",
        trail: _Trail,
        receiver: tuple[Any, ...],
        frames: "_Frames",
        entered_by: tuple[str, tuple[str, int]] | None,
    ) -> tuple[_Reached, ...]:
        """One writing method's writes of `symbol`, on the step naming that write for this
        receiver, answered in the frame of the call that ran it (`entered_by`) where there
        is one: its parameter is the argument at that call."""
        step = _Step((_WRITE_OF, symbol, *receiver), f"{writer or '-'}@{at}")
        merged = _combine(trail, (step,))
        if merged is None:
            return ()
        written, constants, produced = writes
        entered = frames if entered_by is None else frames + (entered_by,)
        return self._binding_writes(written, constants, produced, symbol, merged, entered)

    def _receiver_of(self, row: Mapping[str, Any], frames: "_Frames") -> tuple[Any, ...]:
        """The receiver of a getter call as the reading method holds it, in this calling
        context of that method: a value id, a parameter, or a static field. Two reads on one
        such receiver read one object."""
        caller = str(row["caller"])
        if row.get("receiver") is not None:
            held: tuple[str, Any] = ("value", int(str(row["receiver"])))
        elif row.get("receiver_parameter") is not None:
            held = ("parameter", int(str(row["receiver_parameter"])))
        else:
            held = ("field", row.get("receiver_field"))
        return (caller, _frame_of(frames, caller), held)

    def _objects(
        self,
        symbol: str,
        site: tuple[str, int],
        frames: "_Frames",
        asking: frozenset[tuple[str, tuple[str, int]]],
    ) -> tuple["_End", ...]:
        """Which constructions of the type declaring `symbol` the receiver of `site` can be:
        one end per path, the construction or None where the path ends anywhere else.

        The receiver is followed in `frames`, so a receiver that is a parameter of a helper
        the walk descended into is the argument at the call it came through. Every call
        made on the object is let past (`which_object`): a call on an object does not change
        which `new` built it, and the setter calls this rule is about are such calls.

        `asking` is every object read in progress, the one this serves included.

        Kept on the index (`ValueIndex.objects`): the walk below starts from nothing but
        these four, and reads `frames` only where it records doing so (`_Walk._reads`). An
        answer is reused for any frames that read the same, which is most of them: a receiver
        that never reaches a parameter of a framed method reads none."""
        owner = owner_of(symbol)
        key = (owner, site, asking)
        cached: tuple[_End, ...]
        for held, reads, cached in self._index.objects.get(key, ()):
            if _reads_alike(frames, held, reads):
                return cached
        declared = (str(owner), "<init>")
        # A construction of a subtype built here ends the walk too, so that end is told from
        # one the walk cannot read (final review, Minor 5).
        subtypes = frozenset(
            (below, "<init>") for below in self._index.constructed_below.get(str(owner), ())
        )
        walk = _Walk(
            self._index,
            declared=frozenset({declared}) | subtypes,
            which_object=True,
            asking=asking,
        )
        walk._base = len(frames)
        ends: list[_End] = []
        for crossed, answer in walk._of_site(self._index.sites[site], RECEIVER, (), frames):
            entered = _entered(crossed, self._index)
            built: tuple[str, int] | None = None
            subtype = False
            if answer.kind == _PRODUCED and entered is not None:
                producer = answer.value
                if (
                    producer.identity == declared
                    and producer.caller is not None
                    and producer.ordinal is not None
                ):
                    built = (producer.caller, producer.ordinal)
                subtype = producer.identity in subtypes
            ends.append((built, crossed, crossed if entered is None else entered, subtype))
        found = tuple(dict.fromkeys(ends))
        self._index.objects.setdefault(key, []).append(
            (frames, tuple(dict.fromkeys(walk._reads)), found)
        )
        return found

    def _frame_in(self, frames: "_Frames", method: str) -> tuple[str, int] | None:
        """`_frame_of`, recording on an object walk which of the asker's frames it read."""
        if self._base is None:
            return _frame_of(frames, method)
        found = _frame_of(frames[self._base :], method)
        if found is None:
            found = _frame_of(frames[: self._base], method)
            self._reads.append((_FRAME, method, found))
        return found

    def _writes_by(self, symbol: str) -> "dict[str | None, _Writes]":
        """Every write of `symbol`, by the method that made it (None for a write naming no
        method), in the three shapes `_binding_writes` answers."""
        groups: dict[str | None, tuple[list[Any], list[Any], list[Any]]] = {}
        for method, index in self._index.writers.get(symbol, ()):
            groups.setdefault(method, ([], [], []))[0].append((method, index))
        for writer, entry in self._index.constants.get(symbol, ()):
            groups.setdefault(writer, ([], [], []))[1].append((writer, entry))
        for method, entry in self._index.produced.get(symbol, ()):
            groups.setdefault(method, ([], [], []))[2].append((method, entry))
        return {
            writer: (tuple(written), tuple(constants), tuple(produced))
            for writer, (written, constants, produced) in groups.items()
        }

    def _setter_calls_of(
        self, symbol: str, asking: frozenset[tuple[str, tuple[str, int]]]
    ) -> tuple["_SetterCall", ...]:
        """Every call of a method other than a constructor that writes `symbol`, with the
        objects it was made on — once per field and reads in progress per walk (GUIDELINES
        §8.7): the object walks are bounded by the calls of that field's writers, and every
        read of the field under the same reads in progress shares them. Keyed on `asking`
        too, because what a call's object walk answers depends on which reads it may not
        ask again."""
        key = (symbol, asking)
        cached = self._setter_calls.get(key)
        if cached is not None:
            return cached
        writing = sorted(
            writer
            for writer in self._writes_by(symbol)
            if writer is not None and not _constructs(writer, symbol)
        )
        calls: list[_SetterCall] = []
        for writer in writing:
            self._depends((READ_CALLED_AT, writer))
            for call in self._index.called_at.get(writer, ()):
                if call in self._index.sites:
                    calls.append((writer, call, self._objects(symbol, call, (), asking)))
        found = tuple(calls)
        self._setter_calls[key] = found
        return found


def _constructs(writer: str | None, field: str) -> bool:
    """Whether `writer` is a constructor of the type that declares `field`: a write there,
    made without a parameter, is what every instance of the type holds."""
    return (
        writer is not None
        and owner_of(bare_descriptor(writer)) == owner_of(field)
        and method_name(bare_descriptor(writer)) == "<init>"
    )


# The callee frames the walk descended through: (method, the site that called it),
# innermost last. A method appears more than once only where the walk descended into it
# twice on one path, and the innermost is the one that answers.
_Frames = tuple[tuple[str, tuple[str, int]], ...]

# One end of an object read (`_Walk._objects`): the construction the receiver is, or None
# where the path ends anywhere else; the path as the walk took it; the same path as
# `producer_paths` writes it (`_entered`), which is what two object reads compare; and
# whether the path ends at a construction of a subtype of the field's type built here
# (`built` is None there: the object is not one of the type's own constructions).
_End = tuple[tuple[str, int] | None, _Trail, _Trail, bool]
# One call of a method writing a field (`_Walk._setter_calls_of`): the writing method, the
# call site, and the objects the call was made on.
_SetterCall = tuple[str, tuple[str, int], tuple[_End, ...]]
# One method's writes of one field, in the three shapes `_Walk._binding_writes` answers.
_Writes = tuple[
    tuple[tuple[str, int], ...],
    tuple[tuple[str | None, Mapping[str, Any]], ...],
    tuple[tuple[str, Mapping[str, Any]], ...],
]


# What an object walk read of its asker's frames (`_Walk._reads`): the frame of a method, the
# innermost frame, or the frames whole.
_FRAME = "frame"
_LAST = "last"
_WHOLE = "whole"


def _reads_alike(frames: _Frames, held: _Frames, reads: tuple[tuple[Any, ...], ...]) -> bool:
    """Whether `frames` read as `held` did, at every read an object walk made of `held`."""
    for read in reads:
        if read[0] == _WHOLE:
            return frames == held
        if read[0] == _LAST:
            if (frames[-1] if frames else None) != read[1]:
                return False
        elif _frame_of(frames, read[1]) != read[2]:
            return False
    return True


def _frame_of(frames: _Frames, method: str) -> tuple[str, int] | None:
    for framed, site in reversed(frames):
        if framed == method:
            return site
    return None
