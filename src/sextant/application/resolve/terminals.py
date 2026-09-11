"""What a call REACHES, where the call is a terminal (D00 §4's `terminal_kind`, F7 §8.2).

## Why this needed a wave rather than a line

D00 has declared `terminal_kind` since the fact schema existed and nothing produced one.
Its own note says exactly why, and the note is right: three of the members "need framework
knowledge no pass has applied at a call site — a data-access call is `persistence` only to
something that knows the callee is one". Publishing a guess under that name would be a
classification a reader takes as measured.

So the knowledge arrives as catalog data (D02 §2j) and the classification is READ.

## Three routes, because three frameworks answer differently

Measured across `mall-admin`, `spring-petclinic-rest` and `jhipster-sample-app` before any
of this was written — and each route exists because one of them needs it:

* **`owner`** — the call lands on a library type. `EntityManager` (82 terminals in
  petclinic-rest, 2 in jhipster), `RedisTemplate` (41 in mall-admin), `ResultSet` (17 in
  petclinic-rest) and `JdbcTemplate` (3 there).
* **`supertype`** — the owner implements a declared type. jhipster's repositories are its
  own interfaces and carry no annotation; the class file says they implement
  `JpaRepository`, which is 68 of its 70 classified terminals.
* **`scanned_by`** — an annotation names PACKAGES and every type inside them qualifies.
  mall-admin's mappers carry **no annotation at all** — `@MapperScan({"com.macro.mall.
  mapper", "com.macro.mall.dao"})` on a config class is how MyBatis registers them, and
  that annotation is in the fact stream with its package list. 199 terminals: 172 in
  `mapper` and 27 in `dao`.

**None of the three is a name match**, and that is deliberate: `*Mapper` and `*Repository`
are naming conventions, and §8.1 forbids a rule weaker than the one the framework applies.
Matching mall-admin's mappers by name would also have matched anything else ending in
`Mapper`, and matching jhipster's repositories by name would have missed any repository
named otherwise.

## What it is worth, measured

Re-measured whole after W30's review found five published figures disagreeing with each
other; these are the numbers `call_edges` actually holds, and every count above is a slice
of the same run.

| Corpus | terminals | classified | by what |
|---|---|---|---|
| `mall-admin` | 5,352 | 240 (4%) | 199 scanned package, 41 owner |
| `spring-petclinic-rest` | 2,074 | 102 (5%) | 102 owner |
| `jhipster-sample-app` | 1,141 | 70 (6%) | 68 supertype, 2 owner |

The remaining 94-96% is `StringBuilder`, `Object`, `List`, `Iterator` — and that is the
point rather than a shortfall. Those are not unclassified persistence; they are ordinary
library calls, and they carry `unresolved`, which says *this is a terminal we looked at and
could not classify* rather than pretending they were never examined.

**Two of `TerminalKind`'s eight members have a producer** — `persistence` and
`unresolved` — because one catalog declares `terminals` and all twelve of its rules say
`persistence`. Of `TargetKind`'s three, `database` and `cache` are produced and `file` is
not. The six that are absent split in two, and the split is the honest part: `outbound_call`,
`throws`, `async_handoff` and `TargetKind.FILE` are all a catalog rule away — an owner
rule naming `ExecutorService` or `MinioClient` would mint one today — while `cycle`,
`returns` and `ends_silently` are unreachable BY CONSTRUCTION. A cyclic edge has a
non-NULL `callee`, so `classify` returns NULL for it and always will; the other two
describe how a BODY exits, and all three routes here are predicates on the callee's TYPE,
which cannot express that. `closed_sets.py` names them at the enum and
`docs/open-issues.md` carries `OI-75`.

## Not `TraceStop`

`TraceStop` answers why the WALK stopped and is decided entirely from what the walk did.
This answers what the CALLEE is. One edge carries both, and before this a JDK call and a
MyBatis mapper call read alike — the renderer said so in as many words: "the distinction is
the reader's to make".
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import ancestry_of
from sextant.application.resolve.shapes.expansion import _closure_of
from sextant.domain.closed_sets import TerminalKind
from sextant.domain.symbols import (
    bare_descriptor,
    owner_of,
    package_path,
    type_descriptor,
    without_type_marker,
)


class TerminalRules:
    """Every catalog's `terminals` block, resolved against this workspace once.

    Built once per resolve and asked per edge, because two of the three routes are
    workspace-wide questions — which packages a scan annotation named, and what each type
    implements — and answering them per call site would repeat the same two queries for
    every one of `mall-admin`'s 24,591 edges.
    """

    def __init__(self, workspace: Workspace, catalogs: list[Catalog]) -> None:
        self._owners: dict[str, tuple[str, str | None]] = {}
        self._supertypes: dict[str, tuple[str, str | None]] = {}
        scans: list[dict[str, Any]] = []
        for catalog in catalogs:
            for rule in catalog.terminals:
                answer = (str(rule["kind"]), rule.get("target"))
                for owner in _symbols(rule.get("owner")):
                    self._owners[owner] = answer
                for supertype in _symbols(rule.get("supertype")):
                    self._supertypes[supertype] = answer
                if "scanned_by" in rule:
                    scans.append(rule)
        self._packages: list[tuple[str, tuple[str, str | None]]] = []
        if scans:
            self._packages = _scanned_packages(workspace, scans)
        self._ancestors: dict[str, list[str]] = {}
        if self._supertypes:
            self._ancestors = _ancestry(workspace)

    def of(self, target: str) -> tuple[str | None, str | None]:
        """One terminal's `(terminal_kind, target_kind)`.

        Routes are tried owner-first, then supertype, then scanned package — most
        specific to least. A type named outright by a catalog is a stronger statement
        than one reached through a supertype it shares with everything else in a
        framework, and both are stronger than membership of a scanned package.
        """
        owner = owner_of(bare_descriptor(target))
        if owner is None:
            return None, None
        direct = self._owners.get(owner)
        if direct is not None:
            return direct
        for ancestor in self._ancestors.get(owner, ()):
            answer = self._supertypes.get(ancestor)
            if answer is not None:
                return answer
        # A package prefix, `/`-terminated so `com/acme/mapper` never matches
        # `com/acme/mappers` — a scan names a package and its subpackages, never a
        # neighbour whose name merely starts the same way. Compared in the FACTS'
        # notation, which is what `package_path` converts a catalog's dotted package to:
        # the two grammars meet in `domain/symbols` and nowhere else.
        path = without_type_marker(owner)
        for package, answer in self._packages:
            if path.startswith(package):
                return answer
        return None, None


def classify(rules: TerminalRules | None, target: str, callee: str | None) -> dict[str, str | None]:
    """The two columns for one `call_edges` row.

    **Both NULL where the edge is not a terminal.** An edge whose callee's body was read
    is expanded by the walk, so there is nothing to classify and `unresolved` would be
    wrong — it would say a terminal was examined and could not be named.
    """
    if callee is not None:
        return {"terminal_kind": None, "target_kind": None}
    kind, target_kind = (None, None) if rules is None else rules.of(target)
    return {
        # `unresolved` rather than NULL: this IS a terminal, and it was looked at. A
        # reader distinguishing "not classified" from "not a terminal" is the whole
        # reason the two are spelled differently.
        "terminal_kind": kind or str(TerminalKind.UNRESOLVED),
        "target_kind": target_kind,
    }


def _symbols(declared: object) -> tuple[str, ...]:
    """A rule's type names as bare descriptors, scalar or list (§3.1).

    A scalar stays valid because one rule usually names one type; the list form is for a
    library reachable under more than one name, the same asymmetry `catalog_symbols`
    describes for every other catalog site.
    """
    if isinstance(declared, str):
        return (type_descriptor(declared),)
    if isinstance(declared, list):
        # Each entry passed through UNCONVERTED. `type_descriptor` refuses a non-string
        # on purpose — `str(['a.B'])` is a perfectly well-formed conversion of nonsense,
        # producing a descriptor that matches no fact and says nothing — and the first
        # version mapped `str` over the list before calling it, which meant that guard
        # could never fire on this path (W30 review).
        return tuple(type_descriptor(name) for name in declared)
    return ()


def _scanned_packages(
    workspace: Workspace, scans: list[dict[str, Any]]
) -> list[tuple[str, tuple[str, str | None]]]:
    """The packages each scan annotation actually named, in this module.

    mall-admin's mappers carry no annotation of their own — `@MapperScan` on a config
    class is how MyBatis registers them, and its `value` is the package list. Read from
    the annotation's own arguments rather than assumed: a module that scans one package
    gets one, and a module with no such annotation gets none rather than a convention.
    """
    wanted = {
        type_descriptor(str(rule["scanned_by"])): (str(rule["kind"]), rule.get("target"))
        for rule in scans
    }
    attribute = {
        type_descriptor(str(rule["scanned_by"])): str(rule.get("packages_from", "value"))
        for rule in scans
    }
    found: list[tuple[str, tuple[str, str | None]]] = []
    for row in workspace.query("annotations"):
        annotation = bare_descriptor(str(row["annotation"]))
        answer = wanted.get(annotation)
        if answer is None:
            continue
        args = json.loads(str(row["args"] or "{}"))
        declared = args.get(attribute[annotation])
        if declared is None:
            continue
        for package in declared if isinstance(declared, list) else [declared]:
            # In the FACTS' notation and `/`-terminated: a scan covers a package and
            # everything under it, and an unterminated prefix would also match a sibling
            # whose name merely starts the same way.
            found.append((package_path(str(package).rstrip(".")) + "/", answer))
    # Sorted so two runs classify in one order where two scans overlap (NFR-1).
    return sorted(set(found))


def _ancestry(workspace: Workspace) -> dict[str, list[str]]:
    """Every type's transitive ancestors IN JVMS 5.4.3.3's search order, from the same
    facts `type_hierarchy` is built from — NOT from that table.

    **Ordered, not a set.** `of` returns the first ancestor a catalog claims, so the
    order decides the answer wherever a type reaches two declared supertypes with
    different answers — and iterating a `set` made that a coin toss the hash seed decided:
    measured over six `PYTHONHASHSEED` values, one input classified `database` three times
    and `cache` three times. Not reachable with today's catalog, where all nine Spring
    Data bases share one answer, and reachable the first time a rule ships a different
    `target` — which this file's own comments already anticipate. `_scanned_packages`
    sorts for exactly this reason (NFR-1); this route was the half that did not.

    The order is `_closure_of`'s, which is the order `dispatch.resolve` walks and the one
    `ancestry_of`'s docstring calls the whole point: the superclass chain to exhaustion,
    then the interfaces. Answering from a depth-1 interface while a depth-2 superclass
    holds the declaration is the defect W22's review found one level down.

    **The table is written by the same pass that writes the edges, and written after
    them**, so reading it here returned nothing and every repository call came back
    `unresolved`: 2 classified where 75 were measured. `ancestry_of` reads the
    `superclasses`/`implementations` facts directly, so there is no ordering to get right.

    Transitive rather than direct, which earns its keep for a user-defined intermediate —
    jhipster's `OperationRepositoryWithBagRelationships` sits between a repository and
    `JpaRepository`. It does NOT reach a framework's own hierarchy: an unscanned ancestor
    has no rows of its own, so the walk stops at the first type outside this workspace.
    That is why a catalog must name the level a user actually extends.
    """
    direct_pairs, _scanned = ancestry_of(workspace)
    # `[1:]` drops `child` itself, which `_closure_of` returns first: this map holds a
    # type's ANCESTORS, and a type is not its own supertype.
    return {child: _closure_of(child, direct_pairs)[1:] for child in direct_pairs}
