"""Sub-router mounts: a route registered on a router takes the prefix of every mount that
received that same router (Vert.x spec 2026-10-30 §3c). Names no framework: every owner,
method, type and refusal is the catalog's.

**A router is the object a producer made, reached along a call path** (user ruling
2026-10-30, review issue 2) — never which factory made it. A route root's receiver is
followed to its producer with the value walk's producer reader (`values.producer_paths`),
whose stops are derived from the facts by type (`router_producers`); a mount call's router
argument is followed the same way. A route whose receiver reaches the producer a mount's
argument reaches, on paths that agree (`Path.joined`), takes that mount's prefix, and the
prefix is read WITHIN the joined path (`resolve_positions(..., within=)`), as Quartz reads a
trigger's parts where it was scheduled. So a helper that builds and mounts a router per call
gives each caller's routes that caller's prefix, never the other's.

**Where a router is served:**
- under every mount that received it on the route's path, one prefix each, `resolved`
  (enumerable is exact); each prefix behind the prefixes of the router it was mounted on
  (nested mounts compose);
- at its root, as read, on every execution that reaches no mount — built here and never
  mounted, a helper's router on the caller's path that does not mount it, or produced outside
  the module (a path that ends at no call this module made);
- behind a named hole, `<prefix>`, at `partial`, where a mount received it and the mount path
  was not read whole: a placeholder that says what is missing, never a complete-looking path,
  with a `mount_prefix` question naming the mount call and the argument not read.

**A mount the framework refuses** (`refuses`) is recorded and serves nothing (DR-6): the
framework throws at the mount call, so a route reached only through it derives no row, and
one reached through another serving path keeps that row. The refusals are a mount path with
no trailing wildcard (`exact`), a pattern path (`pattern`), a mount point given the wildcard
(`wildcard`), an unrooted mount path where the catalog refuses one, and for a prefix (plan
2026-11-08 N7, ruling R4) a non-empty one not starting with `/` (`unrooted`), one ending in `/`
(`trailing_slash`), and a mount with an empty prefix of a route whose path below it is empty
too (`empty_path`, decided per route: `Prefix.empty_after`).

**A prefix the router holds** (`router_holds`, plan 2026-11-08 N7): a router whose producer is
a construction a hold entry names (`APIRouter(prefix="/orders")`) carries that prefix in front
of every route registered on it and of every mount made on it, behind every prefix it is
served under — the framework composes its prefixes, where two mounts are two serving places.
It is read on the producer the route's receiver reached, within the same path, so a factory
helper's routers each hold their own caller's prefix. A held prefix the framework refuses
(`refuses`) gives the router no serving place at all.

**Cost** (spec §5): one producer read per route-root receiver and one per mount argument and
mount receiver, each cached here and run on the resolve's shared index; one `within=` read of
the mount path per (mount, path) pair actually joined, cached; one read of each mount path on
every path, for its refusals. Nested mounts recurse once per level. A module with no mount
reads nothing: every route serves at its root. Which executions reach no mount is decided
from the mount paths already read and the callers that take a helper's router back
(`ValueIndex.returns`, turned round once per reader): no read of its own.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import Dispatch
from sextant.application.resolve.shapes.inbound_routes import (
    EMPTY_PATH,
    EXACT_MOUNT_PATH,
    PATTERN_MOUNT_PATH,
    TRAILING_SLASH,
    UNROOTED_PATH,
    WILDCARD_MOUNT_POINT,
    WORDS,
    is_unrooted,
    join_prefix,
    validated_path_join,
)
from sextant.application.resolve.shapes.rooting import catalog_symbols
from sextant.application.resolve.values import (
    EXPRESSION,
    EXTERNAL,
    LITERAL,
    RECEIVER,
    STRING,
    UNPACKED_SLOT,
    Answer,
    Path,
    Producer,
    ValueIndex,
    argument_reference,
    argument_slot,
    producer_paths,
    resolve_positions,
    resolve_positions_on_paths,
)
from sextant.domain.closed_sets import Resolution
from sextant.domain.symbols import returned_type, type_descriptor

# Where a mount's prefix comes from: the path of the route the mount call is made ON
# (`prefix_from: receiver_path`, the chain walk's own `url` capture), or one of its own
# arguments (`prefix_arg: N`).
RECEIVER_PATH = "receiver_path"
# A mount whose router is what the chain its ROOT starts returns (`router_arg: chain_result`,
# design 2026-11-06-reading-decorators §4): `@cli.group() def module` makes the `Group`
# `cli.group()`'s result returns when applied to `module`, and mounts it on `cli`.
CHAIN_RESULT = "chain_result"
# The named hole a program's name is where no entry point names the router (design
# 2026-11-06-reading-decorators §4): the program is named by how it is installed.
UNREAD_PROGRAM = "<program>"
# What a mount the framework refuses looks like (`refuses`), each the word its refusal is
# filed under.
_REFUSES = {
    "exact": EXACT_MOUNT_PATH,
    "pattern": PATTERN_MOUNT_PATH,
    "wildcard": WILDCARD_MOUNT_POINT,
    "unrooted": UNROOTED_PATH,
    "trailing_slash": TRAILING_SLASH,
    "empty_path": EMPTY_PATH,
}
# The refusals a held prefix may declare: it is a prefix, read once, with no route below it.
_HOLD_REFUSES = frozenset({"unrooted", "trailing_slash"})
# The named hole a prefix nobody read is published as: `stitch/links.py`'s `_NAMED_HOLE`
# grammar, so a path holding it is never linked by path (the `<host>` refusal applied to a
# path segment).
UNREAD_PREFIX = "<prefix>"
# A template whose LAST piece is a hole (`{}`, `{name}`, `${…}`): what it ends with is unread.
_UNREAD_END = re.compile(r"\{[^{}]*\}$")
# The `open_questions` kind that says why a row's path holds it (`resolve/open_questions.py`
# owns the closed set).
MOUNT_PREFIX = "mount_prefix"

_STRENGTH = (
    str(Resolution.RESOLVED),
    str(Resolution.NARROWED),
    str(Resolution.PARTIAL),
    str(Resolution.UNRESOLVED),
)


@dataclass(frozen=True)
class MountRule:
    """One `mount` entry: the call, which argument is the router it mounts, and where the
    prefix comes from — `prefix_arg`, or None for the receiver route's path."""

    owners: tuple[str, ...]
    method: str
    descriptor: str | None
    # The argument holding the router it mounts, or `CHAIN_RESULT`: the router is what the
    # chain this mount call ROOTS returns, matched on the root rather than the terminal.
    router_arg: Any
    prefix_arg: Any
    # The mount path's trailing wildcard (`*`), removed with a `/` before it; None where the
    # framework's mount path carries none.
    wildcard: str | None
    refuses: frozenset[str]
    # The one character every trailing copy of which the framework strips from the mount
    # path (Starlette's `Mount`: `path.rstrip("/")`); None where it removes one `/` at most.
    strip_trailing: str | None = None
    # The argument holding the dependencies the mount adds to every route below it (plan
    # 2026-11-08 N6), read by the request-requirements reader; None where none is declared.
    dependencies_arg: Any = None

    def matches(self, site: Mapping[str, Any]) -> bool:
        return (
            str(site.get("owner")) in self.owners
            and site["name"] == self.method
            and (self.descriptor is None or site.get("descriptor") == self.descriptor)
        )


@dataclass(frozen=True)
class HoldRule:
    """One `router_holds` entry (plan 2026-11-08 N7): the construction that makes a router,
    the argument holding the prefix it carries, and the dependencies it adds (N6)."""

    owners: tuple[str, ...]
    method: str
    prefix_arg: Any
    dependencies_arg: Any
    refuses: frozenset[str]

    def matches(self, site: Mapping[str, Any]) -> bool:
        return str(site.get("owner")) in self.owners and site["name"] == self.method


@dataclass(frozen=True)
class MountRules:
    """`router_type`, `mount`, `router_holds` and the `path_join` a prefix is joined by."""

    router_types: frozenset[str]
    mounts: tuple[MountRule, ...]
    path_join: str | None
    holds: tuple[HoldRule, ...] = ()


@dataclass(frozen=True)
class MountPath:
    """One way a mount call is reached: the call whose RECEIVER is the router it mounts on
    (the mount route's root, or the mount call itself) and where its path is read. A mount
    call in a helper, walked back to each caller's route (`ChainEnd.path`), is one of these
    per caller, each read on its own path."""

    parent: Mapping[str, Any] | None
    # `(site, slot)` the mount path is read at; None where the mount names no path (a route
    # with none, which mounts at the parent's root).
    prefix: tuple[Mapping[str, Any], int] | None
    # The mount path is a pattern (the route's `url_is`).
    pattern: bool = False
    # The path the chain walk took to the mount route's root (`ChainEnd.path`).
    within: Path | None = None
    # A mount path the walk captured without a position to read it at: not read.
    unread: bool = False
    # The order the mount route was given, as the engine reads a route's order, or None for
    # its registration order: where the mount stands among the parent's own routes.
    order: Any = None
    # A `chain_result` mount's chain end: the call whose result is the router it mounts.
    made: Mapping[str, Any] | None = None
    # The mount's own word where its route reads no argument for one and the catalog's
    # `path_fallback` names it from the handler (design 2026-11-06-reading-decorators §3c).
    named: str | None = None


@dataclass(frozen=True)
class Mount:
    """One mount call found: the rule it matched, the call itself, and every way it is
    reached (`MountPath`), one per chain end the walk gave for it."""

    rule: MountRule
    site: Mapping[str, Any]
    paths: tuple[MountPath, ...]

    @property
    def key(self) -> tuple[str, int]:
        return (str(self.site["caller"]), int(str(self.site["ordinal"])))


@dataclass(frozen=True)
class UnreadPrefix:
    """Why a prefix is the named hole: the mount call, the argument its prefix is read at, and
    what that argument read as (`mount_prefix`, D01)."""

    mount: str
    mount_ordinal: int
    at: str
    at_ordinal: int
    argument: int
    read: str


# Where a route is served under a prefix: one `(router, mount)` step per router, the
# outermost first, `router` the call that made it (`_identity`) with the path it was reached
# on (`_router`) or None for a router that may be any, and `mount` the place
# `((method, ordinal), order)` on that router of the mount route that serves the next one;
# None on the last step, the router the route itself is on.
Router = tuple[tuple[str, str, int], Path]
Place = tuple[tuple[Router | None, tuple[tuple[str, int], Any] | None], ...]
# The place of a route on a router nothing names.
ANY_ROUTER: Place = ((None, None),)


@dataclass(frozen=True)
class Prefix:
    """A prefix a route serves under, or None for the router's root, with its own word, and
    the mounts whose prefix in it was not read. `places` says on which routers, through which
    mounts (`Place`), and is not part of what the prefix is: empty where nothing was read."""

    text: str | None
    resolution: str
    unread: tuple[UnreadPrefix, ...] = ()
    places: frozenset[Place] = field(default=frozenset(), compare=False)
    # Where in `text` a mount refusing `empty_path` ended with an empty prefix of its own: a
    # route whose served path is empty from there on is refused (`EMPTY_PATH`).
    empty_after: tuple[int, ...] = ()
    # The paths a held prefix was read on (`router_holds`), each a choice of the calls that
    # built the router: folded into the router's `places` path, so whatever else is read on
    # the route is read on the same call (M-1). Not part of what the prefix is.
    read_on: frozenset[Path] = field(default=frozenset(), compare=False)
    # The paths each mount's own prefix value was read on, joined across the mounts the prefix
    # is behind (`_behind`): the calls that gave this prefix its words. Read only to say which
    # calls a row's registration ran through (OI-368, task 10b re-review R1-1); empty where no
    # value was walked. Not part of what the prefix is.
    chosen_on: frozenset[Path] = field(default=frozenset(), compare=False)


ROOT = Prefix(None, str(Resolution.RESOLVED))


def mount_rules_of(
    matches: Mapping[str, Any], source: object, words: bool = False
) -> MountRules | None:
    """The catalog's mount words, validated; None for a catalog declaring neither. `words`
    for a `root_kind: entry_point` catalog, whose prefixes are joined as words are, by one
    space (design 2026-11-06-reading-decorators §4): it declares no `path_join`."""
    declared, types = matches.get("mount"), matches.get("router_type")
    if declared is None and types is None:
        if "router_holds" in matches:
            raise CatalogError(f"loading catalog {source}: `router_holds` without `router_type`")
        return None
    if types is None:
        raise CatalogError(f"loading catalog {source}: `mount` without `router_type`")
    if declared is None:
        raise CatalogError(f"loading catalog {source}: `router_type` without `mount`")
    router_types = frozenset(catalog_symbols(types, f"loading catalog {source}: router_type"))
    if not isinstance(declared, list) or not declared:
        raise CatalogError(f"loading catalog {source}: `mount` must be a non-empty list")
    terminals = {
        entry if isinstance(entry, str) else entry.get("method")
        for entry in matches.get("terminal", [])
    }
    roots = {entry.get("method") for entry in matches.get("roots", []) if isinstance(entry, dict)}
    if words and "path_join" in matches:
        raise CatalogError(
            f"loading catalog {source}: a `root_kind: entry_point` catalog joins its words "
            f"with one space and declares no `path_join`"
        )
    path_join = WORDS if words else validated_path_join(matches, source, "fluent")
    holds = matches.get("router_holds", [])
    if not isinstance(holds, list):
        raise CatalogError(f"loading catalog {source}: `router_holds` must be a list")
    return MountRules(
        router_types,
        tuple(_rule(entry, terminals, roots, source) for entry in declared),
        path_join,
        tuple(_hold(entry, source) for entry in holds),
    )


def with_heirs(rules: MountRules, dispatch: Dispatch) -> MountRules:
    """`rules` with each mount's and hold's owners widened by `Dispatch.heirs` (declared
    owners first), as a root's are (`chains._with_heirs`): a subclass that inherits the method
    — `class App(FastAPI)`'s `include_router`, `class S(APIRouter)`'s constructor — is called
    through its own name and runs the owner's."""

    def widened(owners: tuple[str, ...], method: str) -> tuple[str, ...]:
        heirs = [heir for owner in owners for heir in dispatch.heirs(owner, method)]
        return tuple(dict.fromkeys((*owners, *heirs))) if heirs else owners

    return replace(
        rules,
        mounts=tuple(
            replace(rule, owners=widened(rule.owners, rule.method)) for rule in rules.mounts
        ),
        holds=tuple(
            replace(rule, owners=widened(rule.owners, rule.method)) for rule in rules.holds
        ),
    )


def _hold(entry: Any, source: object) -> HoldRule:
    where = f"loading catalog {source}: router_holds[]"
    if not isinstance(entry, dict) or not isinstance(entry.get("method"), str):
        raise CatalogError(f"{where} must be a mapping naming `owner` and `method`")
    dependencies = _dependencies_arg(entry, where)
    # A construction may hold dependencies and no prefix (N6: `FastAPI(dependencies=...)`).
    if argument_reference(entry.get("prefix_arg"), spelled=False) is None and not (
        "prefix_arg" not in entry and dependencies is not None
    ):
        raise CatalogError(
            f"{where} `{entry['method']}` must name its `prefix_arg`, or only a `dependencies_arg`"
        )
    refuses = entry.get("refuses", [])
    if not isinstance(refuses, list) or any(word not in _HOLD_REFUSES for word in refuses):
        raise CatalogError(
            f"{where} `{entry['method']}` `refuses` must list words of {sorted(_HOLD_REFUSES)}"
        )
    return HoldRule(
        owners=catalog_symbols(entry.get("owner"), f"{where} `{entry['method']}` owner"),
        method=entry["method"],
        prefix_arg=entry.get("prefix_arg"),
        dependencies_arg=dependencies,
        refuses=frozenset(refuses),
    )


def _dependencies_arg(entry: Mapping[str, Any], where: str) -> Any:
    """An entry's `dependencies_arg` (plan 2026-11-08 N6): absent, or an argument reference."""
    declared = entry.get("dependencies_arg")
    if declared is not None and argument_reference(declared, spelled=False) is None:
        raise CatalogError(
            f"{where} `{entry['method']}` `dependencies_arg` must be a position, "
            f"`{{keyword: name}}` or `{{arg: N, keyword: name}}`"
        )
    return declared


def _rule(entry: Any, terminals: set[Any], roots: set[Any], source: object) -> MountRule:
    where = f"loading catalog {source}: mount[]"
    if not isinstance(entry, dict) or not isinstance(entry.get("method"), str):
        raise CatalogError(f"{where} must be a mapping naming `owner` and `method`")
    router_arg = entry.get("router_arg")
    if router_arg != CHAIN_RESULT and argument_reference(router_arg, spelled=False) is None:
        raise CatalogError(
            f"{where} `{entry['method']}` must name its `router_arg`: a position, "
            f"`{{keyword: name}}`, `{{arg: N, keyword: name}}` or `{CHAIN_RESULT}`"
        )
    prefix_arg, prefix_from = entry.get("prefix_arg"), entry.get("prefix_from")
    if (prefix_arg is None) == (prefix_from is None) or (
        prefix_arg is not None and argument_reference(prefix_arg, spelled=False) is None
    ):
        raise CatalogError(
            f"{where} `{entry['method']}` must name exactly one of `prefix_arg: N` and "
            f"`prefix_from: {RECEIVER_PATH}`"
        )
    if router_arg == CHAIN_RESULT and (
        prefix_from != RECEIVER_PATH or entry["method"] not in roots
    ):
        raise CatalogError(
            f"{where} `{entry['method']}` takes `router_arg: {CHAIN_RESULT}` only as a declared "
            f"root with `prefix_from: {RECEIVER_PATH}`: the router is what the chain it starts "
            f"returns, and its prefix is that chain's own path"
        )
    if (
        router_arg != CHAIN_RESULT
        and prefix_from is not None
        and (prefix_from != RECEIVER_PATH or entry["method"] not in terminals)
    ):
        raise CatalogError(
            f"{where} `{entry['method']}` takes `prefix_from: {RECEIVER_PATH}` only as a "
            f"declared `terminal`, so the chain walk reads the route it is called on"
        )
    refuses = entry.get("refuses", [])
    wildcard = entry.get("wildcard")
    if (
        not isinstance(refuses, list)
        or any(word not in _REFUSES for word in refuses)
        or (wildcard is None and {"exact", "wildcard"} & set(refuses))
        or (wildcard is not None and (not isinstance(wildcard, str) or not wildcard))
    ):
        raise CatalogError(
            f"{where} `{entry['method']}` `refuses` must list words of {sorted(_REFUSES)}, "
            f"`exact` and `wildcard` beside a `wildcard`"
        )
    descriptor = entry.get("descriptor")
    if descriptor is not None and not isinstance(descriptor, str):
        raise CatalogError(f"{where} `{entry['method']}` `descriptor` must be a string")
    strip = entry.get("strip_trailing")
    if strip is not None and (not isinstance(strip, str) or len(strip) != 1):
        raise CatalogError(
            f"{where} `{entry['method']}` `strip_trailing` is the one character the framework "
            f"strips from the end of a mount path, got {strip!r}"
        )
    return MountRule(
        owners=catalog_symbols(entry.get("owner"), f"{where} `{entry['method']}` owner"),
        method=entry["method"],
        descriptor=str(descriptor) if descriptor is not None else None,
        router_arg=router_arg,
        prefix_arg=prefix_arg,
        wildcard=wildcard,
        refuses=frozenset(refuses),
        strip_trailing=strip,
        dependencies_arg=_dependencies_arg(entry, where),
    )


def router_producers(
    index: ValueIndex,
    router_types: frozenset[str],
    ancestors: Mapping[str, Sequence[tuple[str, str, bool]]],
    configuring: frozenset[tuple[str, str, str]] = frozenset(),
) -> frozenset[tuple[str, str]]:
    """The calls that MAKE a router, as the producer reader's `declared` stops (spec §3c),
    derived from the facts by type in one pass over the sites: every call whose body this
    module does not read and whose declared return is a router type, and every constructor
    of a class the facts show implementing one (`ancestors`, the dispatch hierarchy).

    A module method that returns a router is not one: it hands back a router something in
    its body made, and the walk descends into it, which is what lets a route and a mount in
    two methods meet at the call that made the router. Nor is a call that returns its own
    receiver (`configuring`, the catalog's `returns_receiver` calls: `router.errorHandler(…)`):
    it hands back the router it was called on, and the walk goes on through that receiver
    (coordinator ruling 2026-10-31: identity wins over the return type)."""
    found: set[tuple[str, str]] = set()
    for site in index.sites.values():
        call = (str(site.get("owner")), str(site["name"]))
        descriptor = site.get("descriptor")
        if call in found or not descriptor or (*call, str(descriptor)) in configuring:
            continue
        if site["name"] == "<init>":
            if _is_a(call[0], router_types, ancestors):
                found.add(call)
        elif call in index.unscanned:
            returned = returned_type(str(descriptor))
            if returned is not None and _is_a(returned, router_types, ancestors):
                found.add(call)
    return frozenset(found)


def _is_a(
    type_: str,
    router_types: frozenset[str],
    ancestors: Mapping[str, Sequence[tuple[str, str, bool]]],
) -> bool:
    seen = {type_}
    frontier = [type_]
    while frontier:
        current = frontier.pop()
        if current in router_types:
            return True
        for parent, _, _ in ancestors.get(current, ()):
            if parent not in seen:
                seen.add(parent)
                frontier.append(parent)
    return False


class MountReader:
    """Which prefixes a route serves under, for one resolve's mounts (module docstring)."""

    def __init__(
        self,
        workspace: Workspace,
        index: ValueIndex,
        rules: MountRules,
        declared: frozenset[tuple[str, str]],
        mounts: Sequence[Mount],
        refuses_unrooted: bool,
        configuring: frozenset[tuple[str, str, str]] = frozenset(),
        programs: Mapping[tuple[str, int], str] | None = None,
        dispatch: Dispatch | None = None,
    ) -> None:
        self._workspace = workspace
        # The module's dispatch, for the `__init__` a subclass construction runs
        # (`_held_at`); None where the catalog declares no `router_holds`.
        self._dispatch = dispatch
        self._sites_by_caller: dict[str, list[Mapping[str, Any]]] | None = None
        self._index = index
        self._rules = rules
        self._declared = declared
        self._mounts = tuple(mounts)
        # A `root_kind: entry_point` catalog's program names (design
        # 2026-11-06-reading-decorators §4), by the call whose result an entry point names
        # (`programs_of`); None for every other catalog, whose outermost word is as read.
        self._programs = programs
        # The calls whose results are the routers `chain_result` mounts mount: each a stop of
        # the producer reader, as a router type's maker is (`router_producers`).
        self._made = frozenset(
            (str(at.made["caller"]), int(str(at.made["ordinal"])))
            for mount in self._mounts
            for at in mount.paths
            if at.made is not None
        )
        self._refuses_unrooted = refuses_unrooted
        self._configuring = configuring
        self._producers: dict[tuple[str, int, int | str], tuple[tuple[Producer, Path], ...]] = {}
        self._read: dict[tuple[tuple[str, int], int, Path], tuple[Prefix, ...]] = {}
        self._refused: dict[tuple[str, int], tuple[tuple[int, str, str], ...]] = {}
        self._called_by: dict[str, tuple[tuple[str, int], ...]] | None = None
        self._held: dict[tuple[tuple[str, int], Path], tuple[Prefix, ...] | None] = {}

    def of_route(self, root: Mapping[str, Any], within: Path | None) -> tuple[Prefix, ...]:
        """The prefixes a route whose root call is `root` serves under, each once: its
        receiver followed to the router's producer, on every path the walk takes (and within
        `within`, the path the chain walk took to the root, where it took one). Empty where
        every way the router is reached runs through a mount the framework refuses: nothing
        serves the route. The root alone where the walk reaches no end at all. A prefix
        reached several ways is one, holding every way's `places`."""
        found: dict[Prefix, Prefix] = {}
        ended = False
        for producer, path in self._producers_of(root, RECEIVER):
            joined = path if within is None else path.joined(within)
            if joined is not None:
                ended = True
                for prefix in self._served(producer, joined, frozenset()):
                    kept = found.get(prefix)
                    found[prefix] = (
                        prefix
                        if kept is None
                        else replace(kept, places=kept.places | prefix.places)
                    )
        return tuple(found.values()) if ended else (ROOT,)

    def refusals(self, mount: Mount) -> tuple[tuple[int, str, str], ...]:
        """`(way, mount path, reason)` for every way the framework refuses `mount`, `way`
        being the index of the `MountPath` it was reached by, each path read on every path
        the code gives (one read per way, cached per mount). A path read only in part is
        refused where the part read decides it; a pattern whatever it reads."""
        if mount.key in self._refused:
            return self._refused[mount.key]
        found: list[tuple[int, str, str]] = []
        for way, at in enumerate(mount.paths):
            if at.prefix is None:
                if at.unread and at.pattern and "pattern" in mount.rule.refuses:
                    found.append((way, UNREAD_PREFIX, PATTERN_MOUNT_PATH))
                continue
            for answers in resolve_positions(
                self._workspace, {"prefix": at.prefix}, self._index, within=at.within
            ):
                text = _text_of(answers["prefix"])
                if text is None:
                    if at.pattern and "pattern" in mount.rule.refuses:
                        found.append((way, UNREAD_PREFIX, PATTERN_MOUNT_PATH))
                    continue
                reason = self._refusal(mount, at, *text)
                if reason is not None:
                    found.append((way, text[0], reason))
        self._refused[mount.key] = tuple(dict.fromkeys(found))
        return self._refused[mount.key]

    def held_refusals(self) -> tuple[tuple[Mapping[str, Any], str, str], ...]:
        """`(construction, prefix, reason)` for every router construction a `router_holds`
        entry names whose prefix the framework refuses, read on every path the code gives
        (the construction raises, so nothing on that router is served)."""
        found: dict[tuple[str, int, str, str], tuple[Mapping[str, Any], str, str]] = {}
        for site in self._index.sites.values():
            rule = self._hold_rule(site)
            slot = (
                None
                if rule is None or rule.prefix_arg is None
                else argument_slot(site["arguments"] or [], rule.prefix_arg)
            )
            if rule is None or slot is None or slot == UNPACKED_SLOT:
                continue
            for answers in resolve_positions(
                self._workspace, {"prefix": (site, slot)}, self._index
            ):
                text = _text_of(answers["prefix"])
                reason = None if text is None else _prefix_refusal(rule.refuses, *text)
                if text is not None and reason is not None:
                    key = (str(site["caller"]), int(str(site["ordinal"])), text[0], reason)
                    found.setdefault(key, (site, text[0], reason))
        return tuple(found.values())

    def dependencies_of(self, prefix: Prefix) -> tuple[tuple[Mapping[str, Any], int, Path], ...]:
        """Where the dependencies a route served under `prefix` takes are written (plan
        2026-11-08 N6), as `(call, slot, path)` to read each at, every place once: on each of
        its places (`Prefix.places`), outermost first, each router's own (`router_holds`'
        `dependencies_arg`, read where its prefix is, `_held_at`) and each mount's
        (`mount[].dependencies_arg`). A mount declaring none hands no dependency on, its own
        or any router's above it: it serves its router as an application of its own (a
        Starlette `mount`), where an include registers the router's routes on the router it
        includes them in. A router handed in from outside names no construction, and none."""
        found: dict[tuple[str, int, int, Path], tuple[Mapping[str, Any], int, Path]] = {}
        for place in prefix.places:
            held: list[tuple[Mapping[str, Any], int, Path]] = []
            for step, (router, mount) in enumerate(place):
                if router is not None:
                    held.extend(self._held_dependencies(router))
                if mount is None:
                    continue
                rule_site = self._mount_at(mount[0])
                if rule_site is None:
                    continue
                rule, site = rule_site
                if rule.dependencies_arg is None:
                    held = []
                    continue
                slot = argument_slot(site["arguments"] or [], rule.dependencies_arg)
                below = place[step + 1][0] if step + 1 < len(place) else None
                if slot is not None and slot != UNPACKED_SLOT:
                    held.append((site, slot, Path() if below is None else below[1]))
            for site, slot, path in held:
                key = (str(site["caller"]), int(str(site["ordinal"])), slot, path)
                found.setdefault(key, (site, slot, path))
        return tuple(found.values())

    def _held_dependencies(self, router: Router) -> list[tuple[Mapping[str, Any], int, Path]]:
        """Where the router `router` holds dependencies from its construction (`router_holds`),
        read where its prefix is read (`_held_at`)."""
        made, path = router
        site = self._index.sites.get((made[1], made[2])) if made[0] == "call" else None
        if site is None or not self._rules.holds:
            return []
        found: list[tuple[Mapping[str, Any], int, Path]] = []
        for rule, at, on in self._held_at(site, path, frozenset(), "dependencies_arg") or []:
            slot = argument_slot(at["arguments"] or [], rule.dependencies_arg)
            if slot is not None and slot != UNPACKED_SLOT:
                found.append((at, slot, on))
        return found

    def _mount_at(self, key: tuple[str, int]) -> tuple[MountRule, Mapping[str, Any]] | None:
        """The mount whose call, or one of whose ways' parent call, is `key` (a `Place`'s
        mount), with its rule."""
        for mount in self._mounts:
            if mount.key == key or any(
                at.parent is not None
                and (str(at.parent["caller"]), int(str(at.parent["ordinal"]))) == key
                for at in mount.paths
            ):
                return mount.rule, mount.site
        return None

    def _hold_rule(self, site: Mapping[str, Any], holding: str = "prefix_arg") -> HoldRule | None:
        return next(
            (
                rule
                for rule in self._rules.holds
                if rule.matches(site) and getattr(rule, holding) is not None
            ),
            None,
        )

    def _holds(self, made: tuple[str, str, int], path: Path) -> tuple[Prefix, ...] | None:
        """The prefixes the router `made` holds from its construction (`router_holds`), read
        within `path`, the path its producer was reached on: one per value read, the named
        hole where it is not read whole, none where the framework refuses it. None where the
        router holds no prefix: no hold entry names its producer, or the call writes none (the
        empty prefix, the framework's default)."""
        if made[0] != "call" or not self._rules.holds:
            return None
        key = ((made[1], made[2]), path)
        if key in self._held:
            return self._held[key]
        site = self._index.sites.get((made[1], made[2]))
        reads = None if site is None else self._held_at(site, path, frozenset())
        held: tuple[Prefix, ...] | None = None
        if site is not None and reads is not None:
            found: dict[Prefix, Prefix] = {}
            if not reads:
                hole = self._hole_at(
                    site, MountPath(site, None), "a constructor that hands on no prefix it reads"
                )
                found[hole] = hole
            written = [(self._held_read(*read), read[2]) for read in reads]
            for prefixes, at_path in written:
                # A construction on one path that writes no prefix holds the empty one there.
                for prefix in (
                    prefixes
                    if prefixes is not None
                    else [Prefix("", str(Resolution.RESOLVED), read_on=frozenset({at_path}))]
                ):
                    kept = found.get(prefix, prefix)
                    found[prefix] = replace(kept, read_on=kept.read_on | prefix.read_on)
            # Where no construction writes one at all, the router holds no prefix.
            held = (
                None
                if written and all(prefixes is None for prefixes, _ in written)
                else tuple(found.values())
            )
        self._held[key] = held
        return held

    def _held_at(
        self,
        site: Mapping[str, Any],
        path: Path,
        seen: frozenset[tuple[str, int]],
        holding: str = "prefix_arg",
    ) -> list[tuple[HoldRule, Mapping[str, Any], Path]] | None:
        """Where the prefix a router construction holds is written: the construction itself
        where a hold entry names it (its owners widened to the heirs that inherit the
        constructor, `with_heirs`); else, for a construction of a subclass of a hold owner
        whose own `__init__` runs, each hold-matching construction of a supertype that body
        makes (`super().__init__(prefix=prefix)`), read on the path entering that body from
        this construction, so its parameters are this call's arguments. None where the
        construction makes no router that holds a prefix; empty where it does and the body
        that runs hands none on that can be read (the prefix is then not read). `holding` is
        the hold entries' key read: `prefix_arg`, or `dependencies_arg` for what a router's
        construction holds besides (N6); only the entries declaring it are read."""
        rule = self._hold_rule(site, holding)
        if rule is not None:
            return [(rule, site, path)]
        dispatch = self._dispatch
        owner = str(site.get("owner"))
        holders = frozenset(
            owner
            for rule in self._rules.holds
            if getattr(rule, holding) is not None
            for owner in rule.owners
        )
        if site["name"] != "<init>" or dispatch is None or owner in holders:
            return None
        if not _is_a(owner, holders, dispatch.ancestors):
            return None
        found: list[tuple[HoldRule, Mapping[str, Any], Path]] = []
        for body in dispatch.candidates(dict(site)):
            entered = path.entering(body, str(site["caller"]), int(str(site["ordinal"])))
            if entered is None:
                continue
            for inner in self._body_sites(body):
                key = (str(inner["caller"]), int(str(inner["ordinal"])))
                inner_owner = str(inner.get("owner"))
                if (
                    inner["name"] != "<init>"
                    or key in seen
                    or inner_owner == owner
                    or not _is_a(owner, frozenset({inner_owner}), dispatch.ancestors)
                ):
                    continue
                deeper = self._held_at(inner, entered, seen | {key}, holding)
                if deeper:
                    found.extend(deeper)
        return found

    def _body_sites(self, method: str) -> list[Mapping[str, Any]]:
        """The calls `method`'s body makes, from the shared index, grouped once per reader."""
        if self._sites_by_caller is None:
            grouped: dict[str, list[Mapping[str, Any]]] = {}
            for site in self._index.sites.values():
                grouped.setdefault(str(site["caller"]), []).append(site)
            self._sites_by_caller = grouped
        return self._sites_by_caller.get(method, [])

    def _held_read(
        self, rule: HoldRule, site: Mapping[str, Any], path: Path
    ) -> list[Prefix] | None:
        """The prefixes one hold-matching construction writes, read within `path`: one per
        value read, each with the paths it was read on (`read_on`); the named hole where it
        is not read whole; none where the framework refuses it. None where the call writes
        none (the framework's default, the empty prefix), or the rule reads none."""
        if rule.prefix_arg is None:
            return None
        slot = argument_slot(site["arguments"] or [], rule.prefix_arg)
        at = MountPath(site, None if slot is None or slot == UNPACKED_SLOT else (site, slot))
        if slot == UNPACKED_SLOT:
            return [self._hole_at(site, at, "a value the walk captured at no position")]
        if slot is None:
            return None
        read = resolve_positions_on_paths(
            self._workspace, {"prefix": (site, slot)}, self._index, within=path
        )
        found: dict[Prefix, Prefix] = {}
        for on, answers in read:
            text = _text_of(answers["prefix"])
            if text is not None and _prefix_refusal(rule.refuses, *text) is not None:
                continue
            if text is None or not text[1]:
                prefix = self._hole_at(site, at, _read_as(answers["prefix"]))
            else:
                narrowed = answers["prefix"].narrowed
                prefix = Prefix(
                    text[0], str(Resolution.NARROWED if narrowed else Resolution.RESOLVED)
                )
            kept = found.get(prefix, prefix)
            found[prefix] = replace(kept, read_on=kept.read_on | {on})
        if not read:
            hole = self._hole_at(site, at, "nothing on this path")
            found[hole] = hole
        return list(found.values())

    def _holding(self, prefix: Prefix, held: Prefix) -> Prefix | None:
        """`held`, the router's own prefix, behind `prefix`, one it is served under, the
        router's place narrowed to the paths `held` was read on; None where no such path
        agrees with the one the router was reached on."""
        text = (
            held.text
            if prefix.text is None
            else join_prefix(prefix.text, str(held.text), self._rules.path_join)
        )
        places = prefix.places
        if held.read_on:
            places = frozenset(
                (*place[:-1], (((router[0], joined) if router is not None else None), mount))
                for place in prefix.places
                for router, mount in (place[-1],)
                for on in held.read_on
                if (joined := (on if router is None else router[1].joined(on))) is not None
            )
            if not places:
                return None
        return replace(
            prefix,
            text=text,
            resolution=weaker(prefix.resolution, held.resolution),
            unread=(*prefix.unread, *held.unread),
            places=places,
        )

    def _served(self, producer: Producer, path: Path, mounting: frozenset[Any]) -> list[Prefix]:
        """The prefixes of the router `producer` made, as reached on `path`: one per mount
        that received the same router on a path agreeing with it, behind that mount's own
        router's prefixes; and the root wherever an execution `path` allows reaches no mount
        (`_unmounted`). A mount the framework refuses gives no prefix, and the executions it
        covers serve nothing. `mounting` holds the mounts this read is inside, so a router
        mounted into itself ends rather than recurses.

        The same router is the same producer — or, for a router handed in from outside, the
        same parameter it arrived at (`_identity`): two ends there on agreeing paths are one
        object."""
        made = _identity(producer)
        if made is None:
            return [replace(ROOT, places=frozenset({ANY_ROUTER}))]
        found: list[Prefix] = []
        reached: list[Path] = []
        for mount in self._mounts:
            if mount.key in mounting:
                continue
            for mounted, mount_path, ways in self._mounted(mount):
                if _identity(mounted) != made:
                    continue
                for way, at in ways:
                    joined = path.joined(mount_path)
                    if joined is not None and at.within is not None:
                        joined = joined.joined(at.within)
                    if joined is None:
                        continue
                    reached.append(joined)
                    for own in self._prefixes(mount, way, joined):
                        for parent in self._parents(at, joined, mounting | {mount.key}):
                            # The router's place carries the path the mount agreed on, so
                            # what else the route reads is read on that same call (M-1).
                            prefix = self._behind(parent, own, at, _router(made, joined))
                            if own.text == "" and "empty_path" in mount.rule.refuses:
                                prefix = replace(
                                    prefix,
                                    empty_after=(*prefix.empty_after, len(prefix.text or "")),
                                )
                            found.append(prefix)
        if self._unmounted(path, made[1], reached, frozenset()):
            found.append(replace(ROOT, places=frozenset({((_router(made, path), None),)})))
        held = self._holds(made, path)
        if held is not None:
            found = [
                holding
                for prefix in found
                for own in held
                if (holding := self._holding(prefix, own)) is not None
            ]
        return found

    def _unmounted(
        self, path: Path, method: str, reached: list[Path], entered: frozenset[str]
    ) -> bool:
        """Whether some execution `path` allows reaches none of the mounts in `reached` — the
        router served as read, at its root (enumerable is exact: a helper's router mounted on
        one caller's path and served unmounted on another's is served both ways).

        A path no mount path agrees with reaches none. Otherwise each caller that can run
        `method` (the method holding the producer, then each caller in turn, as the router
        is handed back out) is a choice of its own, and a choice no mount path agrees with
        is such an execution. A method nothing in the module calls ends the search."""
        agreeing = [mounted for mounted in reached if path.joined(mounted) is not None]
        if not agreeing:
            return True
        if method in entered:
            return False
        for caller, ordinal in self._callers(method):
            chosen = path.entering(method, caller, ordinal)
            if chosen is not None and self._unmounted(chosen, caller, agreeing, entered | {method}):
                return True
        return False

    def _callers(self, method: str) -> tuple[tuple[str, int], ...]:
        """The calls that run `method` and take what it hands back (`ValueIndex.returns`,
        turned round once per reader)."""
        if self._called_by is None:
            called_by: dict[str, list[tuple[str, int]]] = {}
            for (caller, _), returned in self._index.returns.items():
                for ordinal, callee in returned:
                    called_by.setdefault(callee, []).append((caller, ordinal))
            self._called_by = {
                callee: tuple(dict.fromkeys(sites)) for callee, sites in called_by.items()
            }
        return self._called_by.get(method, ())

    def _parents(self, at: MountPath, path: Path, mounting: frozenset[Any]) -> list[Prefix]:
        """The prefixes of the router a mount reached by `at` mounts ON, read on `path`; the
        root where the walk reaches no end."""
        if at.parent is None:
            return [ROOT]
        found: list[Prefix] = []
        ended = False
        for producer, parent_path in self._producers_of(at.parent, RECEIVER):
            joined = path.joined(parent_path)
            if joined is not None:
                ended = True
                found.extend(self._served(producer, joined, mounting))
        return found if ended else [ROOT]

    def _prefixes(self, mount: Mount, way: int, path: Path) -> tuple[Prefix, ...]:
        """`mount`'s own prefixes, reached by its `way`, read within `path`: the mount path
        with its trailing wildcard and the `/` before it removed, a refused one giving none,
        one not read whole the named hole."""
        key = (mount.key, way, path)
        if key in self._read:
            return self._read[key]
        at = mount.paths[way]
        found: list[Prefix] = []
        if at.pattern and "pattern" in mount.rule.refuses:
            pass
        elif at.unread:
            found.append(self._hole(mount, at, "a value the walk captured at no position"))
        elif at.named is not None:
            # The mount's own word, named from its handler (`path_fallback`): exact.
            found.append(Prefix(at.named, str(Resolution.RESOLVED)))
        elif at.prefix is None:
            found.append(Prefix("", str(Resolution.RESOLVED)))
        else:
            read = resolve_positions_on_paths(
                self._workspace, {"prefix": at.prefix}, self._index, within=path
            )
            for on, answers in read:
                prefix = self._prefix_of(mount, at, answers["prefix"])
                if prefix is not None:
                    found.append(replace(prefix, chosen_on=frozenset({on})))
            if not read:
                found.append(self._hole(mount, at, "nothing on this path"))
        # One prefix per text, with every path it was read on.
        merged: dict[Prefix, Prefix] = {}
        for prefix in found:
            kept = merged.get(prefix)
            merged[prefix] = (
                prefix
                if kept is None
                else replace(kept, chosen_on=kept.chosen_on | prefix.chosen_on)
            )
        self._read[key] = tuple(merged.values())
        return self._read[key]

    def _hole(self, mount: Mount, at: MountPath, read: str) -> Prefix:
        """The named hole for `mount`'s prefix, saying where it was read and what it read."""
        return self._hole_at(mount.site, at, read)

    def _hole_at(self, call: Mapping[str, Any], at: MountPath, read: str) -> Prefix:
        """The named hole for the prefix the call `call` gives (a mount, or a construction
        holding one), read at `at`."""
        site, argument = at.prefix if at.prefix is not None else (call, -1)
        return Prefix(
            UNREAD_PREFIX,
            str(Resolution.PARTIAL),
            (
                UnreadPrefix(
                    mount=str(call["caller"]),
                    mount_ordinal=int(str(call["ordinal"])),
                    at=str(site["caller"]),
                    at_ordinal=int(str(site["ordinal"])),
                    argument=argument,
                    read=read,
                ),
            ),
        )

    def _prefix_of(self, mount: Mount, at: MountPath, answer: Answer) -> Prefix | None:
        text = _text_of(answer)
        if text is not None and self._refusal(mount, at, *text) is not None:
            return None
        if text is None or not text[1]:
            return self._hole(mount, at, _read_as(answer))
        mounted = text[0]
        wildcard = mount.rule.wildcard
        if wildcard is not None and mounted.endswith(wildcard):
            mounted = mounted[: -len(wildcard)]
        # The `/` before the wildcard, or ending a mount point, is the separator the join
        # supplies: `/api/*`, `/api*` and `/api/` all mount at `/api`. A framework that strips
        # every trailing copy says so (`strip_trailing`): `/api//` mounts at `/api` too.
        strip = mount.rule.strip_trailing
        mounted = mounted.rstrip(strip) if strip is not None else mounted.removesuffix("/")
        resolution = Resolution.NARROWED if answer.narrowed else Resolution.RESOLVED
        return Prefix(mounted, str(resolution))

    def _refusal(self, mount: Mount, at: MountPath, text: str, whole: bool) -> str | None:
        """The word the framework's refusal of a mount path is filed under, or None. A path
        read in part (`whole` False, holes `{…}` unfilled) is refused where the part read
        decides it: an unrooted first piece, or a last piece read without the wildcard (an
        exact path) or with it (a mount point given it)."""
        refuses = mount.rule.refuses
        if at.pattern:
            return PATTERN_MOUNT_PATH if "pattern" in refuses else None
        if self._refuses_unrooted and is_unrooted(text, whole):
            return UNROOTED_PATH
        refused = _prefix_refusal(refuses, text, whole)
        if refused is not None:
            return refused
        wildcard = mount.rule.wildcard
        if wildcard is None or not (whole or not _UNREAD_END.search(text)):
            return None
        if "exact" in refuses and not text.endswith(wildcard):
            return EXACT_MOUNT_PATH
        if "wildcard" in refuses and text.endswith(wildcard):
            return WILDCARD_MOUNT_POINT
        return None

    def _behind(self, parent: Prefix, own: Prefix, at: MountPath, made: Router | None) -> Prefix:
        """`own` joined behind `parent`, at the weaker of their two words. The router `made`
        is served from the parent's, at the mount route's place there (`Place`): the parent
        tries its own routes and the mount route in their order, so a mounted router's routes
        compete with the parent's own at that one place, nested mounts each a step."""
        text = (
            own.text
            if parent.text is None or own.text is None
            else join_prefix(parent.text, own.text, self._rules.path_join)
        )
        resolution = weaker(parent.resolution, own.resolution)
        if self._programs is not None and parent.text is None and own.text is not None:
            text, program = self._outermost(parent, own.text, made)
            if program == UNREAD_PROGRAM:
                resolution = weaker(resolution, str(Resolution.PARTIAL))
        mount = (
            ((str(at.parent["caller"]), int(str(at.parent["ordinal"]))), at.order)
            if at.parent is not None
            else None
        )
        places = frozenset(
            (*place[:-1], (place[-1][0], mount), (made, None))
            for place in parent.places or (ANY_ROUTER,)
        )
        chosen = parent.chosen_on or own.chosen_on
        if parent.chosen_on and own.chosen_on:
            chosen = frozenset(
                joined
                for outer in parent.chosen_on
                for inner in own.chosen_on
                if (joined := outer.joined(inner)) is not None
            )
        return Prefix(
            text,
            resolution,
            (*parent.unread, *own.unread),
            places,
            parent.empty_after,
            chosen_on=chosen,
        )

    def _outermost(self, parent: Prefix, word: str, made: Router | None) -> tuple[str, str]:
        """The outermost word of an entry-point prefix and the program word in it (design
        2026-11-06-reading-decorators §4): a program is started by the name it is installed
        under, so the outermost router's word is that name. Where the parent is a router no
        mount names (`grp = Group()`), it has no word of its own: the program's name goes in
        front of `word`. Where it is no router (the outermost mount sits on nothing), `word`
        is the outermost router's own and is replaced."""
        routers = sorted(
            {place[-1][0] for place in parent.places or (ANY_ROUTER,)} - {None}, key=repr
        )
        if not routers:
            program = self.program(made)
            return program, program
        names = {self.program(router) for router in routers}
        program = names.pop() if len(names) == 1 else UNREAD_PROGRAM
        return join_prefix(program, word, self._rules.path_join), program

    def outermost(self, prefix: Prefix, word: str) -> str:
        """A command's path where its router is served at its root (`prefix.text` None) and
        is a router no mount names: the program's name in front of `word`."""
        return self._outermost(prefix, word, None)[0]

    def program(self, router: Router | None) -> str:
        """The name of the entry point that names the object `router` is (`programs_of`), or
        the named hole `<program>`."""
        if router is None or self._programs is None or router[0][0] != "call":
            return UNREAD_PROGRAM
        return self._programs.get((router[0][1], router[0][2]), UNREAD_PROGRAM)

    def joined(self, prefix: Prefix, path: str, pattern: bool) -> str:
        """A route's own `path` behind `prefix` (`path_join`); a pattern verbatim, since the
        framework matches it against what follows the prefix as written."""
        if prefix.text is None:
            return path
        return join_prefix(prefix.text, path, None if pattern else self._rules.path_join)

    def _mounted(
        self, mount: Mount
    ) -> tuple[tuple[Producer, Path, tuple[tuple[int, MountPath], ...]], ...]:
        """Each router `mount` mounts, with the path it was reached on and the ways to the
        mount it is mounted by: the producers of its router argument, by every way; or, for a
        `chain_result` mount, the call that ends each way's chain, by that way alone."""
        ways = tuple(enumerate(mount.paths))
        if mount.rule.router_arg != CHAIN_RESULT:
            return tuple(
                (producer, path, ways)
                for producer, path in self._producers_of(mount.site, mount.rule.router_arg)
            )
        return tuple(
            (
                Producer(caller=str(at.made["caller"]), ordinal=int(str(at.made["ordinal"]))),
                Path(),
                ((way, at),),
            )
            for way, at in ways
            if at.made is not None
        )

    def _producers_of(
        self, site: Mapping[str, Any], slot: Any
    ) -> tuple[tuple[Producer, Path], ...]:
        """The producers of `site`'s receiver (`RECEIVER`) or of the argument a catalog's
        reference names (`argument_slot`), each with its path."""
        if slot != RECEIVER:
            slot = argument_slot(site["arguments"] or [], slot)
            if slot is None or slot == UNPACKED_SLOT:
                return ()
        key = (str(site["caller"]), int(str(site["ordinal"])), slot)
        if key not in self._producers:
            self._producers[key] = producer_paths(
                self._index,
                site,
                slot,
                self._declared,
                configuring=self._configuring,
                which_object=True,
                declared_sites=self._made,
            )
        return self._producers[key]


def programs_of(workspace: Workspace, index: ValueIndex) -> dict[tuple[str, int], str]:
    """Each program the module's build declares (`module.entry_points`, design
    2026-11-06-reading-decorators §4 and §7a), by the call whose result its target names:
    `"sextant.cli.app:cli"` names the module-level name `cli`, the field
    `sextant/cli/app#cli.`, and the call whose result is written to it. Extras
    (`"a.b:main [extra]"`) are not part of the target. A target naming a function, an
    attribute path (`a.b:obj.attr`) or a name no call in the module writes names no call: such
    a program is not one this catalog's routers can be."""
    targets: dict[str, str] = {}
    for row in workspace.query("entry_points"):
        written = row["entry_points"]
        declared = json.loads(written) if isinstance(written, str) else written
        if not isinstance(declared, Mapping):
            continue
        for name, target in sorted(declared.items()):
            module, _, attribute = str(target).split("[", 1)[0].strip().partition(":")
            if module and attribute.isidentifier():
                targets.setdefault(type_descriptor(module) + attribute + ".", str(name))
    found: dict[tuple[str, int], str] = {}
    if not targets:
        return found
    for row in workspace.query("field_writes"):
        program = targets.get(str(row["field"]))
        value = row["value"]
        value = json.loads(value) if isinstance(value, str) else value
        source = value.get("source") if isinstance(value, Mapping) else None
        if program is None or source is None:
            continue
        writer = str(row["written_by"])
        for ordinal in index.producers.get((writer, int(str(source))), ()):
            found.setdefault((writer, ordinal), program)
    return found


def weaker(one: str, other: str) -> str:
    """The weaker of two resolution words."""
    return max(one, other, key=_STRENGTH.index)


def _read_as(answer: Answer) -> str:
    """What an argument not read whole read as, in words: its text with the holes unfilled,
    or why the walk gave no value."""
    if answer.kind == EXPRESSION or answer.inexact:
        return f"`{answer.value}`"
    if answer.kind == LITERAL:
        return f"`{answer.value}`, not a string"
    return f"no value ({answer.reason or answer.kind})"


def file_unread_prefix(
    unread: dict[tuple[str, str | None, str], dict[str, Any]],
    *,
    protocol: str,
    method: str | None,
    method_kind: str | None,
    path: str,
    path_kind: str | None,
    prefix: Prefix,
    caller: str,
) -> None:
    """Notes why a row's path holds `<prefix>` (`mount_prefix`, D01), one candidate per
    unread mount, against the row's identity; written by `unread_prefix_rows`."""
    row = unread.setdefault(
        (protocol, method, path),
        {"method_kind": method_kind, "path_kind": path_kind, "candidates": []},
    )
    for entry in prefix.unread:
        candidate = {
            "mount": entry.mount,
            "mount_ordinal": entry.mount_ordinal,
            "at": entry.at,
            "at_ordinal": entry.at_ordinal,
            "argument": entry.argument,
            "read": entry.read,
            "caller": caller,
        }
        if candidate not in row["candidates"]:
            row["candidates"].append(candidate)


def unread_prefix_rows(
    unread: Mapping[tuple[str, str | None, str], dict[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The `open_questions` rows of the unread prefixes, for the rows the run kept, in a
    stable order."""
    kept = {(row["protocol"], row["method"], row["path"]) for row in rows}
    found = []
    for key in sorted(unread, key=lambda k: (k[0], k[1] or "", k[2])):
        if key not in kept:
            continue
        candidates = sorted(unread[key]["candidates"], key=lambda c: json.dumps(c, sort_keys=True))
        found.append(
            {
                "protocol": key[0],
                "method": key[1],
                "path": key[2],
                "method_kind": unread[key]["method_kind"],
                "path_kind": unread[key]["path_kind"],
                "question": MOUNT_PREFIX,
                "candidates": json.dumps(candidates, sort_keys=True, separators=(",", ":")),
                "evidence": "; and ".join(sorted({str(c["mount"]) for c in candidates})),
            }
        )
    return found


def _prefix_refusal(refuses: frozenset[str], text: str, whole: bool) -> str | None:
    """The word a framework's refusal of a PREFIX is filed under (plan 2026-11-08 N7, ruling
    R4), or None. The empty prefix is no prefix and is never refused here. `unrooted`: one not
    starting with `/`, decided where its first character was read (`is_unrooted`);
    `trailing_slash`: one ending in `/`, a lone `/` included (a text whose last piece is unread
    ends in its hole, never in `/`)."""
    if not text:
        return None
    if "unrooted" in refuses and is_unrooted(text, whole):
        return UNROOTED_PATH
    if "trailing_slash" in refuses and text.endswith("/"):
        return TRAILING_SLASH
    return None


def _text_of(answer: Answer) -> tuple[str, bool] | None:
    """A mount path's text and whether it was read whole: an exact string literal (True), a
    template with its holes unfilled (False); None where nothing was read."""
    if answer.kind == LITERAL and answer.literal_kind == STRING and not answer.inexact:
        return str(answer.value), True
    if answer.kind == EXPRESSION and isinstance(answer.value, str):
        return answer.value, False
    return None


def _router(made: tuple[str, str, int], path: Path) -> Router | None:
    """A router as a `Place` names it: the call that made it and the path it was reached on,
    or None for one handed in from outside — two such parameters are two names, and the
    caller outside the module may hand both the same router, so it may be any router
    (`OI-263`)."""
    return (made, path) if made[0] == "call" else None


def same_router(router: Router, other: Router) -> bool:
    """Whether two `Place` routers are one object: the same producer reached on agreeing
    paths (the user's ruling, 2026-10-30; the mount join's own test, `Path.joined`). Two calls
    of one factory helper run its producer twice, so their paths choose two calls of the
    helper and the routers are two (final review I1)."""
    return router[0] == other[0] and router[1].joined(other[1]) is not None


def _identity(producer: Producer) -> tuple[str, str, int] | None:
    """Which object a producer-reader end names: the call that made it, or — for a router
    handed in from outside — the parameter it arrived at, `(method, index)`, the same object
    wherever it is read on agreeing paths. None for an end that names neither. The method is
    always the second element, for the callers that hand it back (`_unmounted`)."""
    if producer.caller is not None and producer.ordinal is not None:
        return ("call", producer.caller, producer.ordinal)
    if producer.parameter is not None and producer.reason == EXTERNAL:
        return ("parameter", producer.parameter[0], producer.parameter[1])
    return None
