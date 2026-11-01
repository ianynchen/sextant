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
(`wildcard`), and an unrooted mount path where the catalog refuses one.

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
from sextant.application.resolve.shapes.inbound_routes import (
    EXACT_MOUNT_PATH,
    PATTERN_MOUNT_PATH,
    UNROOTED_PATH,
    WILDCARD_MOUNT_POINT,
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
    Answer,
    Path,
    Producer,
    ValueIndex,
    producer_paths,
    resolve_positions,
)
from sextant.domain.closed_sets import Resolution
from sextant.domain.symbols import returned_type

# Where a mount's prefix comes from: the path of the route the mount call is made ON
# (`prefix_from: receiver_path`, the chain walk's own `url` capture), or one of its own
# arguments (`prefix_arg: N`).
RECEIVER_PATH = "receiver_path"
# What a mount the framework refuses looks like (`refuses`), each the word its refusal is
# filed under.
_REFUSES = {
    "exact": EXACT_MOUNT_PATH,
    "pattern": PATTERN_MOUNT_PATH,
    "wildcard": WILDCARD_MOUNT_POINT,
}
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
    router_arg: int
    prefix_arg: int | None
    # The mount path's trailing wildcard (`*`), removed with a `/` before it; None where the
    # framework's mount path carries none.
    wildcard: str | None
    refuses: frozenset[str]

    def matches(self, site: Mapping[str, Any]) -> bool:
        return (
            str(site.get("owner")) in self.owners
            and site["name"] == self.method
            and (self.descriptor is None or site.get("descriptor") == self.descriptor)
        )


@dataclass(frozen=True)
class MountRules:
    """`router_type`, `mount` and the `path_join` a prefix is joined by."""

    router_types: frozenset[str]
    mounts: tuple[MountRule, ...]
    path_join: str | None


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


ROOT = Prefix(None, str(Resolution.RESOLVED))


def mount_rules_of(matches: Mapping[str, Any], source: object) -> MountRules | None:
    """The catalog's mount words, validated; None for a catalog declaring neither."""
    declared, types = matches.get("mount"), matches.get("router_type")
    if declared is None and types is None:
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
    path_join = validated_path_join(matches, source, "fluent")
    return MountRules(
        router_types, tuple(_rule(entry, terminals, source) for entry in declared), path_join
    )


def _rule(entry: Any, terminals: set[Any], source: object) -> MountRule:
    where = f"loading catalog {source}: mount[]"
    if not isinstance(entry, dict) or not isinstance(entry.get("method"), str):
        raise CatalogError(f"{where} must be a mapping naming `owner` and `method`")
    if not isinstance(entry.get("router_arg"), int):
        raise CatalogError(f"{where} `{entry['method']}` must name its `router_arg`")
    prefix_arg, prefix_from = entry.get("prefix_arg"), entry.get("prefix_from")
    if (prefix_arg is None) == (prefix_from is None) or (
        prefix_arg is not None and not isinstance(prefix_arg, int)
    ):
        raise CatalogError(
            f"{where} `{entry['method']}` must name exactly one of `prefix_arg: N` and "
            f"`prefix_from: {RECEIVER_PATH}`"
        )
    if prefix_from is not None and (
        prefix_from != RECEIVER_PATH or entry["method"] not in terminals
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
    return MountRule(
        owners=catalog_symbols(entry.get("owner"), f"{where} `{entry['method']}` owner"),
        method=entry["method"],
        descriptor=str(descriptor) if descriptor is not None else None,
        router_arg=int(entry["router_arg"]),
        prefix_arg=prefix_arg,
        wildcard=wildcard,
        refuses=frozenset(refuses),
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
    ) -> None:
        self._workspace = workspace
        self._index = index
        self._rules = rules
        self._declared = declared
        self._mounts = tuple(mounts)
        self._refuses_unrooted = refuses_unrooted
        self._configuring = configuring
        self._producers: dict[tuple[str, int, int | str], tuple[tuple[Producer, Path], ...]] = {}
        self._read: dict[tuple[tuple[str, int], int, Path], tuple[Prefix, ...]] = {}
        self._refused: dict[tuple[str, int], tuple[tuple[int, str, str], ...]] = {}
        self._called_by: dict[str, tuple[tuple[str, int], ...]] | None = None

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
            for mounted, mount_path in self._producers_of(mount.site, mount.rule.router_arg):
                if _identity(mounted) != made:
                    continue
                for way, at in enumerate(mount.paths):
                    joined = path.joined(mount_path)
                    if joined is not None and at.within is not None:
                        joined = joined.joined(at.within)
                    if joined is None:
                        continue
                    reached.append(joined)
                    for own in self._prefixes(mount, way, joined):
                        for parent in self._parents(at, joined, mounting | {mount.key}):
                            found.append(self._behind(parent, own, at, _router(made, path)))
        if self._unmounted(path, made[1], reached, frozenset()):
            found.append(replace(ROOT, places=frozenset({((_router(made, path), None),)})))
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
        elif at.prefix is None:
            found.append(Prefix("", str(Resolution.RESOLVED)))
        else:
            read = resolve_positions(
                self._workspace, {"prefix": at.prefix}, self._index, within=path
            )
            for answers in read:
                prefix = self._prefix_of(mount, at, answers["prefix"])
                if prefix is not None:
                    found.append(prefix)
            if not read:
                found.append(self._hole(mount, at, "nothing on this path"))
        self._read[key] = tuple(dict.fromkeys(found))
        return self._read[key]

    def _hole(self, mount: Mount, at: MountPath, read: str) -> Prefix:
        """The named hole for `mount`'s prefix, saying where it was read and what it read."""
        site, argument = at.prefix if at.prefix is not None else (mount.site, -1)
        return Prefix(
            UNREAD_PREFIX,
            str(Resolution.PARTIAL),
            (
                UnreadPrefix(
                    mount=str(mount.site["caller"]),
                    mount_ordinal=int(str(mount.site["ordinal"])),
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
        # supplies: `/api/*`, `/api*` and `/api/` all mount at `/api`.
        mounted = mounted.removesuffix("/")
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
        mount = (
            ((str(at.parent["caller"]), int(str(at.parent["ordinal"]))), at.order)
            if at.parent is not None
            else None
        )
        places = frozenset(
            (*place[:-1], (place[-1][0], mount), (made, None))
            for place in parent.places or (ANY_ROUTER,)
        )
        return Prefix(
            text,
            weaker(parent.resolution, own.resolution),
            (*parent.unread, *own.unread),
            places,
        )

    def joined(self, prefix: Prefix, path: str, pattern: bool) -> str:
        """A route's own `path` behind `prefix` (`path_join`); a pattern verbatim, since the
        framework matches it against what follows the prefix as written."""
        if prefix.text is None:
            return path
        return join_prefix(prefix.text, path, None if pattern else self._rules.path_join)

    def _producers_of(
        self, site: Mapping[str, Any], slot: int | str
    ) -> tuple[tuple[Producer, Path], ...]:
        key = (str(site["caller"]), int(str(site["ordinal"])), slot)
        if key not in self._producers:
            self._producers[key] = producer_paths(
                self._index,
                site,
                slot,
                self._declared,
                configuring=self._configuring,
                which_object=True,
            )
        return self._producers[key]


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
    path: str,
    prefix: Prefix,
    caller: str,
) -> None:
    """Notes why a row's path holds `<prefix>` (`mount_prefix`, D01), one candidate per
    unread mount, against the row's identity; written by `unread_prefix_rows`."""
    row = unread.setdefault((protocol, method, path), {"candidates": []})
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
                "question": MOUNT_PREFIX,
                "candidates": json.dumps(candidates, sort_keys=True, separators=(",", ":")),
                "evidence": "; and ".join(sorted({str(c["mount"]) for c in candidates})),
            }
        )
    return found


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
