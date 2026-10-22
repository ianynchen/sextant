"""The observability map (spec 2026-10-22-boundary-vocabulary-and-diff §4, FR-23): per
boundary kind, whether THIS analysis could see it — `observable`, `partial` or
`not-observable` — with the reasons, so a quiet diff is never read as "nothing changed"
when the analysis could not have seen the change.

**A pure function of the metadata dictionary `analyze` wrote** (§4c): no file is read here,
so a bundle written before this existed can have its map computed from its manifest alone.
Only measurements of this module are inputs — `uncovered`, `coverage.partial_documents`,
the skipped catalogs and the kinds each would have fed (`feeds`, recorded at `analyze`
because a bundle's reader has no catalogs), `catalogs_run`, and
`module.dependency_source`. `gaps` is a statement about Sextant, identical on every
manifest, so it is listed as `stated_boundaries` and never folded into a verdict.

`module` and `boundary-property` are `observable` with no reasons, always: they are not
code-grounded (`Kind.grounded_in_code`), a module's own metadata and a resolved config
value are read off files rather than derived by a catalog that can be skipped, and none of
the measured inputs reaches them. A class file left uncovered says nothing about whether a
`.properties` file was read.

A skipped catalog is a gap by its recorded `cause` (ruled 2026-10-22): one skipped because
its framework is ABSENT from a classpath the build tool resolved (`module.dependency_source`
`maven` or `gradle`) is not — there is nothing to observe — and takes no part in the map; one
skipped for a missing extractor capability is; on a `declared` classpath (Maven could not be
asked) an absence is not proven, so that skip stays a reason, as do the unrecorded-coordinates
and superseded gates. A skip recorded without a `cause` (metadata written before the field)
is a gap, the old rule, and its reason says the cause was unrecorded.

For a code-grounded kind: any reason makes it `partial`; it is `not-observable` when no
catalog that feeds it ran (`catalogs_run` has none for it) and at least one skipped catalog
that is a gap feeds it. A kind with no catalog run and none skipped is `observable` with no reasons —
nothing could have fed it on this module, which is the truth. Metadata without
`catalogs_run` predates the vocabulary: every code-grounded kind is `partial` with one
reason saying so, never a verdict from the catalogs the machine happens to have today.

Per attribute only where a measurement names one (decision 4): `endpoint.format` from the
ladder's unresolved share, `dependency.peer` from outbound rows with no peer. An attribute
verdict does not move its kind's verdict; the entry exists only where there is something
to say.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from sextant.application.boundary.vocabulary import KINDS
from sextant.domain.version import BOUNDARY_VOCABULARY_VERSION

_UNRECORDED = "catalog kinds unrecorded: manifest predates boundary vocabulary 1"
_CAUSE_UNRECORDED = "cause unrecorded, counted as a gap"

# Why a catalog was skipped (`SkippedCatalog.cause`, written into `metadata.json`'s
# `skipped_catalogs[]`): one value per gate `derive_endpoints_with_runs` asks, the second
# gate split by what it found. A closed set — the map reads it as data, never the message.
SKIP_MISSING_CAPABILITY = "missing_capability"  # the extractor cannot read what it needs
SKIP_FRAMEWORK_ABSENT = "framework_absent"  # none of `detect.coordinates` is in the set
SKIP_DEPENDENCIES_UNRECORDED = "dependencies_unrecorded"  # no coordinates were recorded
SKIP_SUPERSEDED = "superseded"  # a `detect_superseded_by` coordinate is in the build
SKIP_CAUSES = (
    SKIP_MISSING_CAPABILITY,
    SKIP_FRAMEWORK_ABSENT,
    SKIP_DEPENDENCIES_UNRECORDED,
    SKIP_SUPERSEDED,
)
# The dependency sets a build tool resolved, transitives included: an absence there is real.
_RESOLVED_BY_THE_BUILD_TOOL = ("maven", "gradle")
_DECLARED = "dependencies declared, not resolved by the build tool"
# The kinds whose evidence is a type one hop out from the code read (OI-167's own boundary).
_FED_BY_DEPENDENCIES = ("dependency", "data-contract")


VerdictName = Literal["observable", "partial", "not-observable"]


@dataclass(frozen=True)
class Verdict:
    verdict: VerdictName
    reasons: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {"verdict": self.verdict, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ObservabilityMap:
    boundary_vocabulary_version: int
    kinds: dict[str, Verdict]
    attributes: dict[str, dict[str, Verdict]]
    stated_boundaries: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "boundary_vocabulary_version": self.boundary_vocabulary_version,
            "kinds": {name: verdict.to_json() for name, verdict in self.kinds.items()},
            "attributes": {
                kind: {name: verdict.to_json() for name, verdict in found.items()}
                for kind, found in self.attributes.items()
            },
            "stated_boundaries": list(self.stated_boundaries),
        }

    @classmethod
    def from_json(cls, document: Mapping[str, object]) -> "ObservabilityMap":
        """The map `to_json` wrote, read back as it was — for the RECORDED map, which is
        the answer and is never re-derived (`metadata.json` sorts its keys, so the kinds
        are put back in registry order)."""
        order = {name: position for position, name in enumerate(KINDS)}

        def verdicts(found: Mapping[str, object]) -> dict[str, Verdict]:
            return {
                name: Verdict(
                    cast(VerdictName, _mapping(one)["verdict"]),
                    tuple(str(r) for r in cast(list[object], _mapping(one).get("reasons", []))),
                )
                for name, one in found.items()
            }

        kinds = _mapping(document.get("kinds"))
        return cls(
            boundary_vocabulary_version=int(cast(int, document["boundary_vocabulary_version"])),
            kinds=verdicts(
                {
                    name: kinds[name]
                    for name in sorted(kinds, key=lambda n: (order.get(n, len(order)), n))
                }
            ),
            attributes={
                kind: verdicts(_mapping(found))
                for kind, found in _mapping(document.get("attributes")).items()
            },
            stated_boundaries=tuple(
                str(name) for name in cast(list[object], document.get("stated_boundaries") or [])
            ),
        )


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def _count(coverage: Mapping[str, object], key: str) -> int:
    value = coverage.get(key)
    return value if isinstance(value, int) else 0


def _share(
    coverage: Mapping[str, object], unresolved: str, total: str, noun: str
) -> Verdict | None:
    """`N of M <noun> unresolved` where the measured count N is above zero, else nothing: the
    entry exists only where there is something to say."""
    count = _count(coverage, unresolved)
    if count <= 0:
        return None
    return Verdict("partial", (f"{count} of {_count(coverage, total)} {noun} unresolved",))


def _recorded_version(metadata: Mapping[str, object]) -> int:
    """The vocabulary generation the analysis recorded — `metadata.json`'s own key, or a
    manifest's `producer` — and the current one only where neither did: the map describes
    the analysis it was computed from."""
    for found in (
        metadata.get("boundary_vocabulary_version"),
        _mapping(metadata.get("producer")).get("boundary_vocabulary_version"),
    ):
        if isinstance(found, int):
            return found
    return BOUNDARY_VOCABULARY_VERSION


def observability_of(metadata: Mapping[str, object]) -> ObservabilityMap:
    stated = tuple(str(name) for name in cast(list[object], metadata.get("gaps") or []))
    version = _recorded_version(metadata)
    code_grounded = [name for name, kind in KINDS.items() if kind.grounded_in_code]

    if "catalogs_run" not in metadata:
        degraded = {
            name: Verdict("partial", (_UNRECORDED,))
            if name in code_grounded
            else Verdict("observable", ())
            for name in KINDS
        }
        return ObservabilityMap(version, degraded, {}, stated)

    coverage = _mapping(metadata.get("coverage"))
    run = _mapping(metadata.get("catalogs_run"))
    uncovered = sorted(str(path) for path in cast(list[object], metadata.get("uncovered") or []))
    source = _mapping(metadata.get("module")).get("dependency_source")
    declared = source == "declared"
    # A framework absent from a classpath the build tool resolved is nothing to observe:
    # not a gap, and no part of the map (ruled 2026-10-22, the branch's final review).
    skipped = [
        _mapping(one)
        for one in cast(list[object], metadata.get("skipped_catalogs") or [])
        if not (
            _mapping(one).get("cause") == SKIP_FRAMEWORK_ABSENT
            and source in _RESOLVED_BY_THE_BUILD_TOOL
        )
    ]

    shared: list[str] = []
    if uncovered:
        shared.append(f"uncovered files: {len(uncovered)} ({', '.join(uncovered[:3])})")
    partial_documents = _count(coverage, "partial_documents")
    if partial_documents > 0:
        shared.append(f"partial documents: {partial_documents}")

    kinds: dict[str, Verdict] = {}
    for name in KINDS:
        if name not in code_grounded:
            kinds[name] = Verdict("observable", ())
            continue
        reasons = list(shared)
        feeding = [one for one in skipped if name in cast(list[object], one.get("feeds") or [])]
        for one in feeding:
            said = [str(m) for m in cast(list[object], one.get("missing_capabilities") or [])]
            if "cause" not in one:
                said.append(_CAUSE_UNRECORDED)
            reasons.append(f"catalog skipped: {one.get('catalog_id')} ({'; '.join(said)})")
        if declared and name in _FED_BY_DEPENDENCIES:
            reasons.append(_DECLARED)
        if feeding and _count(run, name) == 0:
            verdict: VerdictName = "not-observable"
        else:
            verdict = "partial" if reasons else "observable"
        kinds[name] = Verdict(verdict, tuple(sorted(reasons)))

    attributes: dict[str, dict[str, Verdict]] = {}
    for kind, attribute, unresolved, total, noun in (
        ("endpoint", "format", "format_unresolved", "inbound_total", "formats"),
        ("dependency", "peer", "peer_unresolved", "outbound_total", "peers"),
    ):
        found = _share(coverage, unresolved, total, noun)
        if found is not None:
            attributes[kind] = {attribute: found}
    return ObservabilityMap(version, kinds, attributes, stated)
