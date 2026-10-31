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
- at its root, as read, where no mount received it — built here and never mounted, or
  produced outside the module (a path that ends at no call this module made);
- behind a named hole, `<prefix>`, at `partial`, where a mount received it and the mount path
  was not read whole: a placeholder that says what is missing, never a complete-looking path.

**A mount the framework refuses** (`refuses`) adds no prefix and is recorded (DR-6): a mount
path with no trailing wildcard (`exact`), a pattern path (`pattern`), a mount point given the
wildcard (`wildcard`), and an unrooted mount path where the catalog refuses one.

**Cost** (spec §5): one producer read per route-root receiver and one per mount argument and
mount receiver, each cached here and run on the resolve's shared index; one `within=` read of
the mount path per (mount, path) pair actually joined, cached; one read of each mount path on
every path, for its refusals. Nested mounts recurse once per level. A module with no mount
reads nothing: every route serves at its root.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.inbound_routes import (
    EXACT_MOUNT_PATH,
    LEADING_SLASH,
    PATTERN_MOUNT_PATH,
    UNROOTED_PATH,
    WILDCARD_MOUNT_POINT,
    is_unrooted,
    join_prefix,
)
from sextant.application.resolve.shapes.rooting import catalog_symbols
from sextant.application.resolve.values import (
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
class Mount:
    """One mount call found: the rule it matched, where its router and its prefix are, and
    the call whose RECEIVER is the router it mounts on (the mount route's root, or the mount
    call itself)."""

    rule: MountRule
    site: Mapping[str, Any]
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

    @property
    def key(self) -> tuple[str, int]:
        return (str(self.site["caller"]), int(str(self.site["ordinal"])))


@dataclass(frozen=True)
class Prefix:
    """A prefix a route serves under, or None for the router's root, with its own word."""

    text: str | None
    resolution: str


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
    path_join = matches.get("path_join")
    if path_join not in (None, LEADING_SLASH):
        raise CatalogError(
            f"loading catalog {source}: `path_join: {path_join!r}` — the only value is "
            f"`{LEADING_SLASH}`; leave it out for verbatim concatenation"
        )
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
) -> frozenset[tuple[str, str]]:
    """The calls that MAKE a router, as the producer reader's `declared` stops (spec §3c),
    derived from the facts by type in one pass over the sites: every call whose body this
    module does not read and whose declared return is a router type, and every constructor
    of a class the facts show implementing one (`ancestors`, the dispatch hierarchy).

    A module method that returns a router is not one: it hands back a router something in
    its body made, and the walk descends into it, which is what lets a route and a mount in
    two methods meet at the call that made the router."""
    found: set[tuple[str, str]] = set()
    for site in index.sites.values():
        call = (str(site.get("owner")), str(site["name"]))
        descriptor = site.get("descriptor")
        if call in found or not descriptor:
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
    ) -> None:
        self._workspace = workspace
        self._index = index
        self._rules = rules
        self._declared = declared
        self._mounts = tuple(mounts)
        self._refuses_unrooted = refuses_unrooted
        self._producers: dict[tuple[str, int, int | str], tuple[tuple[Producer, Path], ...]] = {}
        self._read: dict[tuple[tuple[str, int], Path], tuple[Prefix, ...]] = {}

    def of_route(self, root: Mapping[str, Any], within: Path | None) -> tuple[Prefix, ...]:
        """The prefixes a route whose root call is `root` serves under, each once: its
        receiver followed to the router's producer, on every path the walk takes (and within
        `within`, the path the chain walk took to the root, where it took one)."""
        found: list[Prefix] = []
        for producer, path in self._producers_of(root, RECEIVER):
            joined = path if within is None else path.joined(within)
            if joined is not None:
                found.extend(self._served(producer, joined, frozenset()))
        return tuple(dict.fromkeys(found)) or (ROOT,)

    def refusals(self, mount: Mount) -> list[tuple[str, str]]:
        """`(mount path, reason)` for every way the framework refuses `mount`, its path read
        on every path the code gives (one read per mount)."""
        if mount.prefix is None:
            return []
        found: list[tuple[str, str]] = []
        for answers in resolve_positions(
            self._workspace, {"prefix": mount.prefix}, self._index, within=mount.within
        ):
            text = _literal(answers["prefix"])
            if text is not None and (reason := self._refusal(mount, text)) is not None:
                found.append((text, reason))
        return list(dict.fromkeys(found))

    def _served(self, producer: Producer, path: Path, mounting: frozenset[Any]) -> list[Prefix]:
        """The prefixes of the router `producer` made, as reached on `path`: one per mount
        that received the same router on a path agreeing with it, behind that mount's own
        router's prefixes; the root where none did. `mounting` holds the mounts this read is
        inside, so a router mounted into itself ends rather than recurses."""
        if producer.caller is None or producer.ordinal is None:
            return [ROOT]
        made = (producer.caller, producer.ordinal)
        found: list[Prefix] = []
        for mount in self._mounts:
            if mount.key in mounting:
                continue
            for mounted, mount_path in self._producers_of(mount.site, mount.rule.router_arg):
                if (mounted.caller, mounted.ordinal) != made:
                    continue
                joined = path.joined(mount_path)
                if joined is not None and mount.within is not None:
                    joined = joined.joined(mount.within)
                if joined is None:
                    continue
                for own in self._prefixes(mount, joined):
                    for parent in self._parents(mount, joined, mounting | {mount.key}):
                        found.append(self._behind(parent, own))
        return found or [ROOT]

    def _parents(self, mount: Mount, path: Path, mounting: frozenset[Any]) -> list[Prefix]:
        """The prefixes of the router `mount` mounts ON, read on `path`."""
        if mount.parent is None:
            return [ROOT]
        found: list[Prefix] = []
        for producer, parent_path in self._producers_of(mount.parent, RECEIVER):
            joined = path.joined(parent_path)
            if joined is not None:
                found.extend(self._served(producer, joined, mounting))
        return found or [ROOT]

    def _prefixes(self, mount: Mount, path: Path) -> tuple[Prefix, ...]:
        """`mount`'s own prefixes read within `path`: the mount path with its trailing
        wildcard and the `/` before it removed, a refused one giving none, one not read
        whole the named hole."""
        key = (mount.key, path)
        if key in self._read:
            return self._read[key]
        found: list[Prefix] = []
        if mount.pattern and "pattern" in mount.rule.refuses:
            pass
        elif mount.unread:
            found.append(Prefix(UNREAD_PREFIX, str(Resolution.PARTIAL)))
        elif mount.prefix is None:
            found.append(Prefix("", str(Resolution.RESOLVED)))
        else:
            read = resolve_positions(
                self._workspace, {"prefix": mount.prefix}, self._index, within=path
            )
            for answers in read:
                prefix = self._prefix_of(mount, answers["prefix"])
                if prefix is not None:
                    found.append(prefix)
            if not read:
                found.append(Prefix(UNREAD_PREFIX, str(Resolution.PARTIAL)))
        self._read[key] = tuple(dict.fromkeys(found))
        return self._read[key]

    def _prefix_of(self, mount: Mount, answer: Answer) -> Prefix | None:
        text = _literal(answer)
        if text is None:
            return Prefix(UNREAD_PREFIX, str(Resolution.PARTIAL))
        if self._refusal(mount, text) is not None:
            return None
        wildcard = mount.rule.wildcard
        if wildcard is not None and text.endswith(wildcard):
            text = text[: -len(wildcard)]
        # The `/` before the wildcard, or ending a mount point, is the separator the join
        # supplies: `/api/*`, `/api*` and `/api/` all mount at `/api`.
        text = text.removesuffix("/")
        resolution = Resolution.NARROWED if answer.narrowed else Resolution.RESOLVED
        return Prefix(text, str(resolution))

    def _refusal(self, mount: Mount, text: str) -> str | None:
        """The word the framework's refusal of a mount path is filed under, or None."""
        refuses = mount.rule.refuses
        if mount.pattern:
            return PATTERN_MOUNT_PATH if "pattern" in refuses else None
        if self._refuses_unrooted and is_unrooted(text, True):
            return UNROOTED_PATH
        wildcard = mount.rule.wildcard
        if wildcard is not None and "exact" in refuses and not text.endswith(wildcard):
            return EXACT_MOUNT_PATH
        if wildcard is not None and "wildcard" in refuses and text.endswith(wildcard):
            return WILDCARD_MOUNT_POINT
        return None

    def _behind(self, parent: Prefix, own: Prefix) -> Prefix:
        """`own` joined behind `parent`, at the weaker of their two words."""
        text = (
            own.text
            if parent.text is None or own.text is None
            else join_prefix(parent.text, own.text, self._rules.path_join)
        )
        return Prefix(text, weaker(parent.resolution, own.resolution))

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
                self._index, site, slot, self._declared, which_object=True
            )
        return self._producers[key]


def weaker(one: str, other: str) -> str:
    """The weaker of two resolution words."""
    return max(one, other, key=_STRENGTH.index)


def _literal(answer: Answer) -> str | None:
    """A mount path read whole: an exact string literal, None for anything else."""
    if answer.kind == LITERAL and answer.literal_kind == STRING and not answer.inexact:
        return str(answer.value)
    return None
