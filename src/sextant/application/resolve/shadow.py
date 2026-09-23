"""Shadow mode (spec 2026-09-22 §7a) and the `value_resolutions` table it writes (§3d).

**Why this exists, in one sentence.** Everything this project does rests on *misses are
acceptable, fabrications are not* — and this work's whole purpose is to convert misses
into ANSWERS, so every conversion is a new assertion, made at scale, across nineteen
shipped catalogs — every catalog that carries a hop declaration, which is what the whole
work migrates (spec §0's corrected hop-declaration row; the sentence read "fourteen"
until 2026-09-23, on a count that omitted one of the four keys).
§3c's per-engine diff catches MOVEMENT; it does not catch WRONGNESS,
because a wrong address looks exactly like a right one in a diff. Shadow mode is the
mitigation the design names: the walk runs, writes down what it WOULD resolve, and
**publishes nothing**. Every candidate conversion is reviewable as data, on the real
corpus, before a single row of `endpoints`, `endpoint_metadata` or `shapes` changes.

It is a RECORDER, not a consumer. No engine reads what it writes, no row it produces
reaches a document, and an analysis run with it on derives byte-identical rows to one run
with it off. Tasks 7-9 are the consumers, and each of them begins by READING this table
rather than by changing code.

## What bounds the table, and why the bound is the point

§3d is explicit: the rows are written **only for positions a catalog asked about** —
bounded by what catalogs ASK, not by the facts. How narrow that bound is, estate-wide, is a
measured figure and is **not restated here**: it lives in
`docs/research/2026-09-23-value-walk-measurement.md` §2, beside the ceiling it is a fraction
of, and every other site in this repository cites that section rather than carrying its own
copy. Four copies of one number went stale across three fix rounds; one source cannot. A
writer that found itself emitting a row per fact would have lost the bound, and the table
would be a second copy of the argument grammar rather than a review list.

## How an ask is found — six shapes, audited, not derived

The shipped catalogs spell a position in six shapes, **found by auditing all 101 files
rather than derived from a grammar**, which is the standing caveat on every count above: a
catalog that invents a seventh spelling is missed until the list is re-audited. The first
version of this reader had three of the six and under-counted by 20 positions, which is
how the caveat came to be written down.

* a `methods`/`entries`/`vocabulary` row carrying `arg` or a `<name>_arg` integer beside a
  method name (`single_call`, `combinator`, `interface_implementation`,
  `supertype_dispatch`, `config_join`);
* a `fluent` root/step/terminal carrying `captures: {name: argN}`;
* a NESTED capture, `captures: {channel_link: {bean_via: arg0}}` — the same position, with
  what to do with it afterwards (eleven rows, the `spring-integration-*` catalogs);
* a SUB-OBJECT of a row, carrying slots while the method name stays on the parent:
  `ktor-routing`'s `request_requirement: {kind: header, name_arg: 1, value_arg: 2}` and
  `spring-kafka-message`'s `when: {arg: 0, equals: "kafka_topic"}` (count in
  `docs/research/2026-09-23-value-walk-measurement.md` §1.3, row four, which is where
  every per-shape count is stated);
* `arg: all_strings` — EVERY positional argument of the call, a varargs array read as its
  own elements. Thirteen rows, all `List.of`/`Arrays.asList`/`Subscriptions.topics` topic
  lists, and the one spelling where a single catalog row asks about an unbounded number of
  positions;
* a `call_wrappers`/`record_wrappers` entry carrying a `<name>_ctor_arg` against a wrapper
  `type` — a position on that type's CONSTRUCTOR call, so the method name is `<init>`.
  `payload_ctor_arg: last` is a rule rather than an index, resolved per site. The
  `_ctor_arg` key is REQUIRED for this arm, and the branch below says why: without it a
  `payload_arg` beside a `type` would be read as a call slot, and where such nodes live it
  is a generic type-argument index. MEASURED: **7 `_ctor_arg` occurrences**, in 4 nodes
  across 4 catalogs, naming `ProducerRecord` and `HttpEntity`. Seven, not five: the count
  is of KEY OCCURRENCES, which is the convention that reproduces the neighbouring shapes
  exactly (139 plain `captures`, 11 nested, 13 `all_strings`, all re-derived 2026-09-23).

**Shape one is also read outside `matches`, in `parse_calls`** — the one block this reader
opens beside it, because its entries spell a position exactly as shape one does and the code
that consumes them indexes a call's arguments. Which blocks are read, which are refused and
why is the next section.

**This reader is WIDER than the engines, deliberately, and that is the safe direction for
a shadow review.** It matches on the keys the engines match on — owner where declared,
method name, and the JVM descriptor or arity where the row declares either — but it does
not model the engines' REACHABILITY: a `fluent` step whose real scope is a chain the
engine has already rooted is matched here by method name alone, and a `channel_via` row an
engine reaches only by following a `source` link back from a matched site is matched here
against every call site in the module. A review that sees more candidates than will ever
be published is a review with slack in it; one that sees fewer is a review with a hole.
Both over-matches, and what they cost, are measured in
`docs/research/2026-09-23-value-walk-measurement.md` §1.3.

## Which blocks are read, and which are refused

A `Catalog` has more than `matches`, and arg-shaped keys live in four other blocks.
**Each was judged from the code that READS it, never from the key's name** — an index into
a type reference's type arguments and an annotation attribute name are not positions this
walk can answer, and including one would be a wrong answer rather than conservative slack.
Measured over the 101 shipped catalogs, 2026-09-23.

**Read:**

* **`matches`** — the five shapes above and shape six.
* **`parse_calls`** — `bytes_arg` x4 and `class_arg` x4, all in `spring-web.yml`'s
  `parse_calls.calls`, spelled exactly as shape one. `shapes/parse_binding.py` reads them as
  CALL-ARGUMENT indices: `_argument_at(site, entry.bytes_arg)` at `:264`,
  `_argument_at(site, entry.class_arg)` at `:329`, and `_argument_at` itself reads
  `site["arguments"]` at `:349` and indexes it at `:352`. Eight real call positions,
  invisible here until 2026-09-23.

**Refused, each with the line that settles it:**

* **`wrappers[].payload_arg` — 151 occurrences across 55 catalog files**, and the largest
  arg-shaped population outside `matches` by an order of magnitude. It is a GENERIC
  TYPE-ARGUMENT index, not a call slot: `shapes/rooting.py:118-132` sets
  `arguments = current["arguments"]` — a TYPE reference's own type arguments — and then
  reads `arguments[wrapper["payload_arg"]]`. (The raw file count for `payload_arg` is 156:
  these 151, plus 3 inside `matches` and 2 in comments.)
* **`wrappers[].when.annotation_arg` (1) and `protocol_hint.hint_when.annotation_arg` (2)** —
  an annotation ATTRIBUTE, not an index at all. `conditions.py:131-168` parses the block into
  `AnnotationArg(annotation, names, equals, parses_true)`, where `names` are attribute names.
* **`serialization.name_from[].arg` — 70 occurrences in 70 files** — likewise an attribute
  NAME, a string such as `"value"`: `shapes/expansion.py:903-904` reads
  `json.loads(use["args"]).get(source["arg"])`.
* **`suffix[].payload_arg` — 3 occurrences, inside `matches`** (`spring-cloud-stream.yml`), so
  this reader DOES see the key and drops it. It is refused for the same reason as `wrappers`,
  one level along: `engines/config_join.py:677-679` indexes `returns["arguments"]`, the
  functional type's type arguments.

  **What actually drops them is the method name, not the value's type** — measured, because
  the sentence that stood here named the wrong mechanism for two of the three. Two are
  `payload_arg: 0` (`spring-cloud-stream.yml:62` and `:64`) and `_slots_of` returns `(0,)`
  for each; they are dropped by `if slots and names` below, because `_names_of` is `()` at
  the `suffix[]` node and at every ancestor it could inherit from — `binding`,
  `address_from_config` and `matches` — and the node carries no `type`, so the `<init>` arm
  does not fire either. Only the third (`:72`, `payload_arg: [0, 1]`) is dropped for being a
  list. Either way the justification is the consuming line above and never the accident, and
  now the stated accident is the one that happens.

**`bean_model`** sits outside `matches` too and carries no arg-shaped key in any shipped
model. Step models ARE merged into `matches` and so are seen. `shape_model` is immaterial
rather than merely empty: `shape-models/json.yml` carries no positional slot of any kind.

**What remains latent.** This reader is an audit of the shipped files, not a grammar, so a
catalog that spells a position a seventh way — or puts one in a block not named above — is
silently not shadowed. The alarm is the per-catalog ask baseline in
`tests/application/test_shadow_mode.py`.

Telling a call slot from a type-argument index by its key NAME remains impossible, and that
classification belongs to Task 10, where the hop declarations become invalid and it has to
be made anyway. **The example this paragraph used to give was wrong twice over and is
withdrawn:** it said `payload_arg` is a call slot under `wrappers:` and a type-argument
index under `suffix:`, "two lines apart in one file". No `payload_arg` in the 101 shipped
catalogs is a call slot — both spellings are type-argument indices, which is the whole
reason both are refused above — and in `spring-cloud-stream.yml` the two blocks are not
adjacent: `suffix[]` at `:62`, `:64`, `:72` and `wrappers[]` at `:110`, `:111`, in different
top-level blocks. What is really impossible is deciding from the NAME alone, which the
refusals above settle from each key's consuming line instead.

## Cost, and the condition the measurement attached to it

**The `ValueIndex` is built ONCE and threaded into every `resolve_site` call** — Task 4's
ruling condition §6.2, and this module is the first code that keeps it. The fold costs
0.16 s on `mall-admin`, more than walking every position in that corpus put together, and
`resolve_site` rebuilds it whenever a caller passes none. An engine resolving
`mall-admin`'s 52 asked sites without threading one would pay about 8 s where the work
itself is under a millisecond.

**No cost column.** The same ruling's other half is that wall time is not reproducible at
these magnitudes — six runs on identical input gave per-position maxima from 2.1 ms to
32.7 ms while `visits` reproduced to the row — so a time column here would record noise
and invite a reader to compare two runs by it. `visits` is the figure that reproduces, and
Task 4 has measured it for the whole estate; re-recording it per row would put a second
answer beside that one for no reader who has asked.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.shapes.rooting import catalog_symbols, names_a_type
from sextant.application.resolve.values import UNRESOLVED, resolve_site, value_index

# `outcome`, and the two words are the review question rather than the walk's vocabulary
# (§1b's answer kinds are carried beside them, in `answer_kind`). A reviewer reading this
# table is asking one thing — **is this row a new claim?** — and every `would_resolve` row
# is one: a value an engine does not publish today and would once it is migrated. The
# `unresolved` rows are the other half of the same review, because a miss that STAYS a
# miss after migration is the thing COVERAGE reports (§3d), and a reader comparing two
# shadow runs needs both or the table only ever grows.
WOULD_RESOLVE = "would_resolve"
UNRESOLVED_OUTCOME = "unresolved"

_ARG_CAPTURE = re.compile(r"^arg(\d+)$")
# `payload_ctor_arg: last` — a rule, not an index. Resolved per site below.
_LAST = "last"
# `arg: all_strings` — EVERY positional argument, a varargs array read as its elements.
# Also a rule rather than an index, and also resolved per site.
_ALL_STRINGS = "all_strings"


@dataclass(frozen=True)
class Ask:
    """One catalog row's question: these slots, of this method, on these owners."""

    catalog: str
    owners: tuple[str, ...]
    names: tuple[str, ...]
    arity: int | None
    descriptor: str | None
    slots: tuple[int | str, ...]


@dataclass(frozen=True)
class Position:
    """One position a catalog asks about, at a REAL site of this workspace.

    `slot` is an argument index, or the walk's `RECEIVER` (§1b: one entry point, not two).
    No shipped catalog asks about a receiver today, so `_indices_of` only ever produces
    indices — but the measurement harness builds its CEILING out of this same type, and a
    ceiling that left the receiver out would leave out the deepest shape in the corpus.
    """

    catalog: str
    caller: str
    ordinal: int
    slot: int | str


def _names_of(node: dict[str, Any]) -> tuple[str, ...]:
    for key in ("method", "name"):
        value = node.get(key)
        if isinstance(value, str):
            return (value,)
    value = node.get("methods")
    if isinstance(value, list) and all(isinstance(entry, str) for entry in value):
        return tuple(value)
    return ()


def _captured(value: Any, into: list[int | str]) -> None:
    """One `captures` entry's slots. A capture is usually `argN`, and sometimes a NESTED
    dict that says how to reach the value — `channel_link: {bean_via: arg0}`, eleven rows
    across the `spring-integration-*` catalogs. Both name the same position on the same
    call; the nested form only adds what to do with it afterwards."""
    matched = _ARG_CAPTURE.match(value) if isinstance(value, str) else None
    if matched is not None:
        into.append(int(matched.group(1)))
    elif isinstance(value, dict):
        for nested in value.values():
            _captured(nested, into)


def _slots_of(node: dict[str, Any]) -> tuple[int | str, ...]:
    """The positions THIS node names — not its children's.

    Three spellings beyond the plain integer, each of which was missed by the first
    version of this reader and each of which is a real ask: `arg: all_strings`,
    `<name>_ctor_arg: last`, and a nested `captures` dict (see `_captured`).
    """
    slots: list[int | str] = []
    for key, value in node.items():
        name = str(key)
        if not (name == "arg" or name.endswith("_arg")):
            continue
        if isinstance(value, bool):  # `parses_true` and friends are not positions
            continue
        if isinstance(value, int):
            slots.append(value)
        elif value == _ALL_STRINGS:
            slots.append(_ALL_STRINGS)
        elif name.endswith("_ctor_arg") and value == _LAST:
            slots.append(_LAST)
    captures = node.get("captures")
    if isinstance(captures, dict):
        for value in captures.values():
            _captured(value, slots)
    return tuple(dict.fromkeys(slots))


def _owner_symbols(declared: Any, where: str) -> tuple[str, ...]:
    """The owners a node declares, converted the way every engine converts them.

    `names_a_type` first, which is the seam's own "does this convert" test: the recursive
    reader below hands it whatever sits under an `owner` key anywhere in a catalog, and
    `via: {owner: …}` nests one under a node that is not an owner declaration. A node that
    does not name a type leaves the match to widen by method name rather than raise."""
    if not names_a_type(declared):
        return ()
    return tuple(catalog_symbols(declared, where))


@dataclass(frozen=True)
class _Enclosing:
    """What a nested node inherits when it names slots and no method of its own.

    A call is identified by an owner, a method name and an arity or descriptor, and a
    catalog does not always put all four on the node carrying the slot: `ktor-routing`'s
    `request_requirement: {kind: header, name_arg: 1, value_arg: 2}` and
    `spring-kafka-message`'s `when: {arg: 0, equals: "kafka_topic"}` are sub-objects of a
    row that names the method. Every occurrence is a position on the PARENT's call; how
    many there are is counted in `docs/research/2026-09-23-value-walk-measurement.md`
    §1.3, row four, and is not restated here — it was restated in three places and was
    wrong in all three until 2026-09-23."""

    owners: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    arity: int | None = None
    descriptor: str | None = None


def asks_of(catalog: Catalog) -> list[Ask]:
    """Every position `catalog` asks about, read off the loaded file by SHAPE rather than
    by style — one reader for every catalog, so a style that spells a position somewhere
    new is picked up rather than silently skipped.

    **It is a reader of shapes and not of the engines**, in both directions: the module
    docstring states the caveat and the two over-matches, and neither is a defect here —
    a shadow review wants slack rather than a hole."""
    found: list[Ask] = []

    def walk(node: Any, enclosing: _Enclosing) -> None:
        if isinstance(node, list):
            for entry in node:
                walk(entry, enclosing)
            return
        if not isinstance(node, dict):
            return
        owners = _owner_symbols(node.get("owner"), f"{catalog.source}: owner") or enclosing.owners
        names = _names_of(node)
        arity = node.get("arity") if isinstance(node.get("arity"), int) else None
        descriptor = node["descriptor"] if isinstance(node.get("descriptor"), str) else None
        slots = _slots_of(node)
        if slots and not names:
            # A `call_wrappers`/`record_wrappers` entry: the position is on the wrapper
            # TYPE's constructor, so the owner is that type and the method is `<init>`.
            #
            # **The `_ctor_arg` key is REQUIRED, not incidental** (Task 5 review round 2).
            # Matching on `type` plus any slot key would read a `payload_arg` beside a
            # `type` as a constructor argument — and where such a node lives, `payload_arg`
            # is a GENERIC TYPE-ARGUMENT index, not a call slot, so that would be a wrong
            # answer rather than conservative slack. `_ctor_arg` is what distinguishes the
            # two, and it is the only reason this branch can be trusted to name `<init>`.
            # Four catalogs reach here — `kafka-clients`, `spring-kafka-replying`,
            # `spring-kafka-template` and `spring-resttemplate` — naming `ProducerRecord`
            # and `HttpEntity`. **How many nodes and occurrences that is, is not stated
            # here.** The measured figure at its own snapshot is the research document's
            # (`docs/research/2026-09-23-value-walk-measurement.md` §1.3, shape six), and
            # the LIVE per-catalog counts are pinned in `tests/application/test_shadow_mode.py`'s
            # `_ASKS_PER_CATALOG`, which is the one place that tracks the current estate and
            # fails when it moves. This comment used to carry its own copy — "four nodes,
            # SEVEN occurrences" — and CP-34's descriptor-discriminated `record_wrappers`
            # rows made it false the moment they landed, while the pinned baseline caught
            # the same change and was updated. One source, cited, cannot go stale that way.
            if isinstance(node.get("type"), str) and any(
                str(key).endswith("_ctor_arg") for key in node
            ):
                names = ("<init>",)
                owners = _owner_symbols(node["type"], f"{catalog.source}: type") or owners
            else:
                # A sub-object of the row that names the call (see `_Enclosing`). The
                # arity and descriptor come with the name, because they describe the same
                # call and this node carries neither.
                names, arity, descriptor = enclosing.names, enclosing.arity, enclosing.descriptor
        if slots and names:
            found.append(
                Ask(
                    catalog=catalog.id,
                    owners=owners,
                    names=names,
                    arity=arity,
                    descriptor=descriptor,
                    slots=slots,
                )
            )
        # Only a node that names a method replaces what its children inherit: a row's
        # `via: {owner, method}` filter would otherwise re-parent the row's own sub-objects
        # onto the method the filter names.
        inherited = (
            _Enclosing(owners, names, arity, descriptor)
            if names
            else _Enclosing(owners, enclosing.names, enclosing.arity, enclosing.descriptor)
        )
        for key, value in node.items():
            if str(key) == "captures":
                continue
            walk(value, inherited)

    walk(catalog.matches, _Enclosing())
    # **`parse_calls` too** (widened 2026-09-23, Task 5 review round 3). It is a top-level
    # block rather than part of `matches`, and every entry in it is shape one of the six
    # above — an `_arg` integer beside a method name with an owner —  read by
    # `shapes/parse_binding.py` as a real CALL-ARGUMENT index: `_argument_at(site,
    # entry.bytes_arg)` at `:264` and `_argument_at(site, entry.class_arg)` at `:329`, with
    # `_argument_at` reading `site["arguments"]` at `:349` and indexing it at `:352`. Eight
    # positions in `spring-web.yml`, and the reader's own contract is that a style spelling
    # a position somewhere new is picked up rather than silently skipped — so a miss here is
    # a hole in the review, not slack.
    #
    # An entry that names `owner_hierarchy` instead of `owner` is matched by method name
    # alone here: `_matches` (`parse_binding.py:273`) resolves it through the type's
    # ancestry, which this reader does not model. That is the same widening it already
    # takes for an owner-free `fluent` step, and the same safe direction — but it is WIDE,
    # and a reader of this table must not take a protobuf row for a production candidate
    # without checking. MEASURED by running every matched site through production's own
    # `_vocabulary` + `_matches` + `_facts`: on `orders-service` 24 of the 28 sites this
    # reader asks about are refused there, and on `grpc-probe` all 12 are, because the
    # callee's receiver is `com.google.protobuf.Parser`, which has no ancestry fact at all.
    # The counts and what survives them are in
    # `docs/research/2026-09-23-value-walk-measurement.md` §1.3, over-match 3.
    walk(catalog.parse_calls, _Enclosing())
    return found


def positions_asked(sites: Sequence[dict[str, Any]], asks: Sequence[Ask]) -> list[Position]:
    """Every `(site, slot)` a shipped catalog asks about, matched on the keys the engines
    match on: owner (where declared), method name, and descriptor or arity where the row
    declares either.

    **Against the PROJECTED sites only** — `effective_call_sites`, the rows the engines
    see. A `$default` bridge site matched on its raw argument list would hand the walk the
    bridge's receiver, its mask and its marker as though they were the callee's arguments,
    which is a wrong answer rather than a miss (`values.py`'s own measurement).
    """
    by_name: dict[str, list[Ask]] = {}
    for ask in asks:
        for name in ask.names:
            by_name.setdefault(name, []).append(ask)
    found: list[Position] = []
    for site in sites:
        candidates = by_name.get(str(site["name"]))
        if not candidates:
            continue
        arguments = site["arguments"] or []
        owner, descriptor = str(site["owner"]), site["descriptor"]
        for ask in candidates:
            if ask.owners and owner not in ask.owners:
                continue
            if ask.descriptor is not None and str(descriptor) != ask.descriptor:
                continue
            if ask.descriptor is None and ask.arity is not None and ask.arity != len(arguments):
                continue
            for slot in ask.slots:
                for index in _indices_of(slot, len(arguments)):
                    found.append(
                        Position(ask.catalog, str(site["caller"]), int(str(site["ordinal"])), index)
                    )
    # Deduped, because one catalog matching a site through two overload rows asks one
    # question twice and a table holding it twice would count it twice. The two BASES
    # differ by about a quarter and the distinction matters to a reader; both are measured
    # estate-wide in `docs/research/2026-09-23-value-walk-measurement.md` §1.4, which is
    # where they are stated and the only place they are.
    return list(dict.fromkeys(found))


def _indices_of(slot: int | str, arity: int) -> tuple[int, ...]:
    """The argument indices one declared slot resolves to AT THIS SITE.

    `all_strings` is the whole positional list, so this is the one place a single ask can
    cost more than one position: a `List.of` with seven arguments is seven positions from
    one catalog row, and a codebase calling one with a long topic list would be more. It
    is the only spelling in the ask grammar with no bound on how many positions one row
    claims, and `docs/research/2026-09-23-value-walk-measurement.md` §6.3 names it as one
    of the things that would reopen the no-cap ruling."""
    if slot == _ALL_STRINGS:
        return tuple(range(arity))
    index = arity - 1 if slot == _LAST else slot
    if not isinstance(index, int) or not 0 <= index < arity:
        return ()
    return (index,)


def _every_identity(catalogs: Sequence[Catalog]) -> list[dict[str, Any]]:
    """§2's table across every SOURCE the analysis loaded, in catalog order, deduplicated
    by what an entry matches on — `by` is provenance and not part of the claim, which is
    the same key `yaml_source._matching_keys` deduplicates one source's table with.

    One source hands every catalog it builds the same list object, so this is one pass over
    a handful of tables and not one per catalog."""
    found: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, Any], ...]] = set()
    for catalog in catalogs:
        for entry in catalog.value_model:
            key = tuple(sorted((name, value) for name, value in entry.items() if name != "by"))
            if key not in seen:
                seen.add(key)
                found.append(entry)
    return found


def record_value_resolutions(
    workspace: Workspace, catalogs: Sequence[Catalog], *, shadow: bool
) -> int:
    """Spec §7a. Writes what the walk WOULD resolve at every position a catalog asks
    about, and publishes nothing. Returns how many rows it wrote, so a `--shadow` run can
    SAY so: a flag that silently did not arrive leaves an empty table, and a reviewer
    reads "nothing would resolve" as good news.

    **The reset is unconditional and the insert is not.** A workspace analysed once with
    shadow mode and again without it must not keep the first run's rows — they would be a
    review list describing a walk this analysis did not run, which is the same defect
    `reset_reachability.sql` records at length. Reset and insert both run from here, the
    `resolve/roots.py` precedent: this table has exactly one writer.

    Off, the pass costs one `DELETE` over an empty table and reads nothing at all — not
    the index fold, not the catalogs, not a single site. That is what makes an ordinary
    analysis byte-identical to one built before this pass existed.
    """
    workspace.derive("value_resolutions_reset")
    if not shadow:
        return 0
    asks = [ask for catalog in catalogs for ask in asks_of(catalog)]
    asked = positions_asked(effective_call_sites(workspace), asks)
    if not asked:
        return 0
    # §2's identity table, resolved through exactly as a migrated engine resolves through
    # it (Task 7). **A preview that left it out would under-report the conversions it
    # exists to put in front of a reviewer**, and by the one kind that matters most: an
    # identity entry is what unsticks the walk at a producer whose result is opaque (§0b),
    # which is precisely the position a catalog wrote a hop declaration for.
    #
    # **Every SOURCE's table, not the first catalog's** (review round 1). Each catalog
    # carries its own source's (`Catalog.value_model`), and D02 §6 loads two sets together
    # and privileges neither — so reading `catalogs[0]` would shadow one source's engines
    # against another source's identities the day a repository ships its own. One catalog's
    # table is one list object shared by all of that source's catalogs, so the union is at
    # most as long as the sources' tables put together, and it is deduplicated on what an
    # entry matches on, exactly as the loader deduplicates within one source.
    identities = _every_identity(catalogs)
    # Grouped by SITE, because `resolve_site` is the entry point every migrated engine
    # calls (§1b: one entry point, not two) and it resolves a site's slots TOGETHER — a
    # binding is the site's slots as one path reaches them, and resolving two asked slots
    # of one site separately is exactly the per-position recombination M-1 forbids.
    by_site: dict[tuple[str, int], list[Position]] = {}
    for position in asked:
        by_site.setdefault((position.caller, position.ordinal), []).append(position)
    index = value_index(workspace)
    rows: list[dict[str, object]] = []
    # Sorted so two runs over one workspace write one order whatever the catalogs' own
    # was (NFR-1); the bindings within a site arrive in the walk's own deterministic
    # order, and the asked slots within a binding in catalog-then-slot order.
    for site_key, positions in sorted(by_site.items()):
        site = index.sites[site_key]
        for binding in resolve_site(workspace, site, index, identities):
            for position in sorted(positions, key=lambda p: (p.catalog, p.slot)):
                answer = binding.slots.get(position.slot)
                if answer is None:
                    # A slot the PROJECTED row does not have. An ask carrying an arity
                    # matched the raw row's length at a bridge site, where the projection
                    # is shorter; a row saying `not_readable` about a position that does
                    # not exist is noise a reviewer would have to learn to ignore.
                    continue
                unresolved = answer.kind == UNRESOLVED
                rows.append(
                    {
                        "catalog": position.catalog,
                        "caller": position.caller,
                        "ordinal": position.ordinal,
                        "slot": str(position.slot),
                        "path": " -> ".join(binding.path),
                        "outcome": UNRESOLVED_OUTCOME if unresolved else WOULD_RESOLVE,
                        "answer_kind": answer.kind,
                        "literal_kind": answer.literal_kind,
                        "value": None if answer.value is None else str(answer.value),
                        "reason": answer.reason,
                    }
                )
    workspace.derive("value_resolutions_insert", rows=rows)
    return len(rows)


__all__ = [
    "UNRESOLVED_OUTCOME",
    "WOULD_RESOLVE",
    "Ask",
    "Position",
    "asks_of",
    "positions_asked",
    "record_value_resolutions",
]
