"""metadata.json — what a module *is* (D05 §3). Written by `analyze` as the
final act of the pipeline, never by `render`, so the invariant holds
regardless of whether anyone renders (M07): the file exists if and only if
the workspace does, and it always describes the graph beside it."""

import json
from collections.abc import Sequence
from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.ports.scanner import ScannerProvenance
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.version import (
    BOUNDARY_VOCABULARY_VERSION,
    FACT_SCHEMA_VERSION,
    GRAPH_SCHEMA_VERSION,
    SEXTANT_VERSION,
)

# What Sextant knowingly does not do, rotated whole rather than narrowed as
# capability lands (spec ruling I3): a gap that closes retires by name, and
# every entry here has a matching human-readable sentence in document.py's
# _GAPS in the same order, so a catalog that cannot be complete never reads
# as complete (M07 "Honesty obligations").
KNOWN_GAPS = [
    "http_exchange_inbound_use_not_detected",
    "computed_base_addresses_not_traced",
    "config_as_code_not_read",
    # *Two gaps retired BY NAME here (spec ruling I3), and five narrower ones
    # took their place.* `sequence_diagrams_pending_call_graph` and
    # `call_graph_not_implemented` both said the call graph does not exist;
    # `## Traces` renders one per root, with a sequence diagram apiece, so
    # keeping either would be the catalog lying in the opposite direction from
    # usual. What is still true is smaller and more specific, and each of the
    # five names exactly one thing a reader can act on.
    "traces_are_reachability_not_execution",
    "structure_diagram_limited_to_contracts",
    # *Renamed in W31 (spec ruling I3: a gap that NARROWS gets a narrower name).* W30
    # narrowed the BEHAVIOUR and left this key and its sentence alone; both change here.
    # Terminals
    # are classified now — `Reaches` says `persistence (database)` where a JDK call says
    # `unresolved` — so "terminals are unclassified" stopped being true. What is still
    # true is the half W30 did not touch: a sibling build module's body exists somewhere
    # and reads `boundary` here exactly like a third-party jar.
    "cross_module_stops_look_third_party",
    "a_method_is_expanded_once_per_trace",
    "roots_are_declared_handlers_only",
    # *Renamed by F1 (spec ruling I3: a gap that closes retires BY NAME).*
    # Parent inheritance, `<dependencyManagement>`, imported BOMs and `${…}`
    # interpolation ARE resolved now; profiles and transitives are not, and
    # the name says only what is still true.
    "maven_profile_and_transitive_resolution_not_implemented",
    "catalog_module_matching_not_implemented",
    "module_classification_evidence_incomplete",
    "shape_rules_unscoped_to_the_producing_catalog",
    "reactive_flow_not_traced",
    "payload_parsed_beyond_horizon",
    "payload_parse_ambiguous",
]


def write_metadata(
    path: Path,
    module: ModuleModel,
    report: ResolveReport,
    scanners: Sequence[ScannerProvenance],
    commit: str,
    uncovered: tuple[str, ...] = (),
    resolved_config: Sequence[dict[str, object]] = (),
    schema_sources_not_compiled: tuple[str, ...] = (),
    descriptors_not_interpreted: tuple[str, ...] = (),
    libraries_not_scanned: tuple[str, ...] = (),
    detect_notes: tuple[str, ...] = (),
    catalog_hash: str | None = None,
) -> None:
    """Written as the final act of analyze (D05 §3), so it exists whenever the
    workspace does and always describes the graph beside it."""
    # A `both` row is a wire identity this module both exposes and calls, so it counts
    # on both sides — bucketing on direction alone would drop it from whichever side is
    # not its literal `direction` value. **No pass produces one today** (F5 §6.1, W27):
    # a module that serves and calls one identity keeps two rows and
    # `resolve/self_exchange.py` files the question. The arm stays because `both` stays
    # in D00 §4 for the linking tier, which is where the claim can be justified.
    inbound: dict[str, int] = {}
    outbound: dict[str, int] = {}
    for endpoint in report.endpoints:
        protocol = str(endpoint["protocol"])
        direction = str(endpoint["direction"])
        if direction in ("inbound", "both"):
            inbound[protocol] = inbound.get(protocol, 0) + 1
        if direction in ("outbound", "both"):
            outbound[protocol] = outbound.get(protocol, 0) + 1

    document: dict[str, object] = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        # The vocabulary generation (FR-21) the boundary entries a reader derives from
        # this workspace are named in; `export` copies it into the manifest's `producer`.
        "boundary_vocabulary_version": BOUNDARY_VOCABULARY_VERSION,
        "module": {
            "id": module.module_id,
            "kind": module.kind,
            "languages": sorted(module.languages),
            # What this module builds against, with the version each
            # coordinate resolved to (F1). Here rather than only in the
            # `module` fact because it is the one place a reader — a person, a
            # later phase, or 2K's seat — can see the CONDITIONS every
            # framework rule in this run was applied under: a rule is true of a
            # version, and the estate has had no way to say which.
            #
            # A coordinate the resolution could not settle a version for is
            # absent from this map and named, with why, in
            # `dependencies_not_resolved` below. Sorted by the detector
            # (NFR-1); the key is always present, empty where nothing was
            # recorded, so it never reads as "no dependencies" by omission.
            "dependencies": dict(module.dependency_versions),
            # F8 §9.3 (W35). Where this module's sources live, RELATIVE TO ITS
            # ROOT — whatever directories the build declares as source.
            #
            # A `document`'s `relative_path` is a package path
            # (`com/macro/mall/OmsOrderController.<ext>`), which is relative to
            # one of these and openable against nothing on its own. The index
            # joins the two, and it is recorded here because `export` reads
            # what `analyze` left and never re-detects (M08) — so a root the
            # detector found at analyze time has to be written down then or it
            # is gone.
            #
            # Relative and POSIX-spelled, so a bundle moved to another machine
            # still resolves: an absolute path names a directory that exists on
            # exactly one computer, which is not what a portable bundle can
            # carry. Sorted for NFR-1, and empty for a module whose build
            # declares none rather than defaulted to a convention nobody read.
            "source_roots": sorted(
                root.relative_to(module.root).as_posix()
                for root in module.source_roots
                if root.is_relative_to(module.root)
            ),
            # Who answered for `dependencies` (spec 2026-10-21 §3c), and why the build tool
            # did not when it did not. Written down here because `render` reconstructs the
            # module from this file and never re-detects (M00), and the document's
            # coverage line needs the label — the same numbers mean different things on
            # the two answers.
            "dependency_source": module.dependency_source,
            "dependency_source_reason": module.dependency_source_reason,
        },
        "provenance": {
            "commit": commit,
            "sextant_version": SEXTANT_VERSION,
            "fact_schema_version": FACT_SCHEMA_VERSION,
            # EVERY facility that produced a document, not the one the class
            # scanner happened to report. This field has always been a LIST and
            # was always handed a single entry, so `sextant-config-reader` and
            # `sextant-detector` — which between them wrote 11 of a fixture
            # module's 117 documents — were absent from a bundle's provenance.
            #
            # `libraries` is present only where a facility runs THIRD-PARTY
            # code that can move without Sextant moving — each backend reports
            # its own, and which they are is that adapter's business
            # (ARCHITECTURE §10). Omitted, not written empty, for a facility
            # that ships inside the wheel: its version is `sextant_version`
            # beside it, and a second copy of that number is what this change
            # removes.
            "scanners": [
                {"id": one.id, **({"libraries": list(one.libraries)} if one.libraries else {})}
                for one in scanners
            ],
        },
        "coverage": report.coverage,
        # The profiles this module resolved (D06 §3 "environments" — the
        # sibling field the bundle manifest carries), sorted rather than
        # left in `resolved_config`'s own environment-then-key order: this
        # is a set of names, not a row sequence, and a sorted list is
        # deterministic without depending on the query's own ORDER BY.
        "environments": sorted({str(row["environment"]) for row in resolved_config}),
        "gaps": KNOWN_GAPS,
        # Detect-time observations (2M design §1c) — build-system coexistence,
        # a wrapper fallback, a boundary refusal — sorted so the key is
        # deterministic regardless of what order the detector found them in.
        # Always present, empty where the detector had nothing to remark on:
        # the key never depends on whether this run produced a note.
        "detect_notes": sorted(detect_notes),
        # Which compiled sources the facts do not account for (FR-17). Listed
        # in full rather than counted: a count cannot be acted on.
        "uncovered": list(uncovered),
        # Task 4's own two analyze-side gap fields, carried the same way
        # `uncovered` is (FR-17): named in full, never counted, so a `.proto`
        # root protoc refused to compile or an embedded schema the
        # interpreter could not turn into a shape can be acted on by name.
        "schema_sources_not_compiled": list(schema_sources_not_compiled),
        "descriptors_not_interpreted": list(descriptors_not_interpreted),
        # The libraries `.sextant.yml` asked for that never became facts (2I
        # design §5), named the same way and for the same FR-17 reason: a
        # library nobody could read is the difference between "this module
        # calls nothing through it" and "nobody looked", and only the name and
        # the reason say what to do about it.
        #
        # Two lists, because they fail at two stages and are closed by two
        # different actions: `_resolved` is the detector finding no archive
        # (declare the dependency, pin the version, install it), `_scanned` is
        # the scanner failing on an archive it did find (the file is corrupt).
        "libraries_not_resolved": list(module.libraries_not_resolved),
        "libraries_not_scanned": list(libraries_not_scanned),
        # F1's own gap list, carried for the same FR-17 reason and read the
        # same way: a coordinate whose VERSION this analysis could not settle,
        # and every ancestor pom or imported BOM it could not open. It is what
        # makes `module.dependencies` an honest map rather than a silently
        # short one — a reader comparing the two can see exactly which
        # dependencies have no version and why, which is the difference
        # between "this rule does not apply" and "nobody could tell".
        "dependencies_not_resolved": list(module.dependencies_not_resolved),
        "endpoints": {"inbound": inbound, "outbound": outbound},
        # The count says how much was expanded; the list says what was not, by
        # name. Both, because a reader who only knows how many shapes exist
        # cannot tell a module whose payloads are fully described from one
        # whose every payload stopped at a third-party type — and only the
        # names can be acted on (FR-17, the same rule as `uncovered`).
        "shapes": {
            "count": len(report.shapes),
            "unexpanded_types": list(report.unexpanded_types),
        },
        "skipped_catalogs": [
            {
                "catalog_id": skipped.catalog_id,
                "missing_capabilities": list(skipped.missing_capabilities),
                # What the skipped catalog would have fed (spec 2026-10-22 §4b): the map
                # reads this when the catalogs are not in hand.
                "feeds": list(skipped.feeds),
            }
            for skipped in report.skipped_catalogs
        ],
        # How many catalogs that ran feed each kind; a kind nothing ran for is absent.
        "catalogs_run": dict(sorted(report.catalogs_run.items())),
        "query": ["sextant module render"],
    }
    # The identity of the framework knowledge this run used (spec 2026-10-22 §3d), recorded
    # here because the diff reads it long after the catalogs are gone, and `export` copies
    # it. Absent, never a placeholder, where a caller did not compute one.
    if catalog_hash is not None:
        document["catalog_hash"] = catalog_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
