"""Shadow mode (spec 2026-09-22 §7a) and the `value_resolutions` table it writes (§3d).

**Why this exists, in one sentence.** Everything this project does rests on *misses are
acceptable, fabrications are not* — and this work's whole purpose is to convert misses
into ANSWERS, so every conversion is a new assertion, made at scale, across fourteen
shipped catalogs. §3c's per-engine diff catches MOVEMENT; it does not catch WRONGNESS,
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
bounded by what catalogs ASK, not by the facts. Measured (Task 4, 2026-09-23, twenty-seven
corpora including `mall-admin`'s 48 MB of facts): **948 distinct positions asked, against
a ceiling of 98,454** — every argument and receiver of every call site — so the asked
surface is 0.96% of what a row-per-fact table would hold. A writer that found itself
emitting a row per fact would have lost the bound, and the table would be a second copy of
the argument grammar rather than a review list.

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
  `spring-kafka-message`'s `when: {arg: 0, equals: "kafka_topic"}` (26 occurrences);
* `arg: all_strings` — EVERY positional argument of the call, a varargs array read as its
  own elements. Thirteen rows, all `List.of`/`Arrays.asList`/`Subscriptions.topics` topic
  lists, and the one spelling where a single catalog row asks about an unbounded number of
  positions;
* a node that names SLOTS, names no method of its own, and names a `type` — read as a
  position on that type's CONSTRUCTOR, so the method name is `<init>`. The shape it was
  written for is a `call_wrappers`/`record_wrappers` entry carrying a `<name>_ctor_arg`,
  where `payload_ctor_arg: last` is a rule rather than an index and is resolved per site.
  **It is matched by SHAPE and not by key, so it fires more widely than that**: a node
  naming a `type` such as `ResponseEntity`, `Optional` or `Call` beside any slot key mints
  an `<init>` ask on that type across about thirty catalogs. One row of 374 on
  `orders-service`, in the safe direction (below), and stated here because in this
  repository the docstring is the specification and a narrower sentence would not describe
  this code.

**This reader is WIDER than the engines, deliberately, and that is the safe direction for
a shadow review.** It matches on the keys the engines match on — owner where declared,
method name, and the JVM descriptor or arity where the row declares either — but it does
not model the engines' REACHABILITY: a `fluent` step whose real scope is a chain the
engine has already rooted is matched here by method name alone, and a `channel_via` row an
engine reaches only by following a `source` link back from a matched site is matched here
against every call site in the module. A review that sees more candidates than will ever
be published is a review with slack in it; one that sees fewer is a review with a hole.
Both over-matches, and what they cost, are measured in
`docs/research/2026-09-23-value-walk-measurement.md` §1.3; the constructor shape above is
a third of the same kind.

**Two places a position could hide, and neither is covered.** The reader walks
`catalog.matches` alone. A catalog's `bean_model` block is resolved by the loader and sits
OUTSIDE `matches`, so a slot spelled there would be invisible here; no shipped model
carries an arg-shaped key today, and step models are merged into `matches` and so are
seen. And the reader cannot CLASSIFY an arg-shaped key it does see: audited 2026-09-23,
about fifty arg-shaped occurrences across the shipped catalogs are legitimately not call
positions — `spring-cloud-stream.yml`'s `payload_arg: [0, 1]` is a generic TYPE-ARGUMENT
index, and that same key name means a call slot under `wrappers:` and a type-argument
index under `suffix:`. Both are latent rather than live: the same audit found **no missed
call position in any shipped catalog**. The alarm for the day that changes is the
per-catalog ask baseline in `tests/application/test_shadow_mode.py`; the classification
belongs to Task 10, where the hop declarations become invalid and it has to be made
anyway.

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
    row that names the method. Twenty-six occurrences, every one of them a position on the
    PARENT's call."""

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
            if isinstance(node.get("type"), str):
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
    # differ by about a quarter and the distinction matters to a reader: 1,209 distinct
    # (catalog, position) asks over 948 distinct positions, estate-wide.
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
        for binding in resolve_site(workspace, site, index):
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
