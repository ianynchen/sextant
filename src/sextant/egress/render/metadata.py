"""metadata.json — what a module *is* (D05 §3). Written by `analyze` as the
final act of the pipeline, never by `render`, so the invariant holds
regardless of whether anyone renders (M07): the file exists if and only if
the workspace does, and it always describes the graph beside it."""

import json
from collections.abc import Sequence
from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.version import FACT_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION, SEXTANT_VERSION

# What Sextant knowingly does not do, rotated whole rather than narrowed as
# capability lands (spec ruling I3): a gap that closes retires by name, and
# every entry here has a matching human-readable sentence in document.py's
# _GAPS in the same order, so a catalog that cannot be complete never reads
# as complete (M07 "Honesty obligations").
KNOWN_GAPS = [
    "http_exchange_inbound_use_not_detected",
    "computed_base_addresses_not_traced",
    "config_as_code_not_read",
    "sequence_diagrams_pending_call_graph",
    "structure_diagram_limited_to_contracts",
    "call_graph_not_implemented",
    # *Renamed by F1 (spec ruling I3: a gap that closes retires BY NAME).*
    # Parent inheritance, `<dependencyManagement>`, imported BOMs and `${…}`
    # interpolation ARE resolved now; profiles and transitives are not, and
    # the name says only what is still true.
    "maven_profile_and_transitive_resolution_not_implemented",
    "catalog_module_matching_not_implemented",
    "module_classification_evidence_incomplete",
    "merged_endpoints_keep_only_the_handlers_contract",
    "shape_rules_unscoped_to_the_producing_catalog",
    "reactive_flow_not_traced",
    "payload_parsed_beyond_horizon",
    "payload_parse_ambiguous",
]


def write_metadata(
    path: Path,
    module: ModuleModel,
    report: ResolveReport,
    scanner_id: str,
    scanner_version: str,
    commit: str,
    uncovered: tuple[str, ...] = (),
    resolved_config: Sequence[dict[str, object]] = (),
    schema_sources_not_compiled: tuple[str, ...] = (),
    descriptors_not_interpreted: tuple[str, ...] = (),
    libraries_not_scanned: tuple[str, ...] = (),
    detect_notes: tuple[str, ...] = (),
) -> None:
    """Written as the final act of analyze (D05 §3), so it exists whenever the
    workspace does and always describes the graph beside it."""
    # A `both` row (D02 §3) is a wire identity this module both exposes and
    # calls, so it counts on both sides — bucketing on direction alone would
    # drop it from whichever side is not its literal `direction` value.
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
        },
        "provenance": {
            "commit": commit,
            "sextant_version": SEXTANT_VERSION,
            "fact_schema_version": FACT_SCHEMA_VERSION,
            "scanners": [{"id": scanner_id, "version": scanner_version}],
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
            }
            for skipped in report.skipped_catalogs
        ],
        "query": ["sextant module render"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
