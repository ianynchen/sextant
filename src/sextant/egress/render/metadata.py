"""metadata.json — what a module *is* (D05 §3). Written by `analyze` as the
final act of the pipeline, never by `render`, so the invariant holds
regardless of whether anyone renders (M07): the file exists if and only if
the workspace does, and it always describes the graph beside it."""

import json
from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.version import FACT_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION, SEXTANT_VERSION

# What Sextant knowingly did not do in phase 1. Every entry here has a
# matching human-readable sentence in document.py's _GAPS, so a catalog that
# cannot be complete never reads as complete (M07 "Honesty obligations").
PHASE_1_GAPS = [
    "shape_expansion_not_implemented",
    "outbound_endpoints_not_implemented",
    "call_graph_not_implemented",
    "maven_parent_and_profile_resolution_not_implemented",
]


def write_metadata(
    path: Path,
    module: ModuleModel,
    report: ResolveReport,
    scanner_id: str,
    scanner_version: str,
    commit: str,
) -> None:
    """Written as the final act of analyze (D05 §3), so it exists whenever the
    workspace does and always describes the graph beside it."""
    inbound: dict[str, int] = {}
    for endpoint in report.endpoints:
        protocol = str(endpoint["protocol"])
        inbound[protocol] = inbound.get(protocol, 0) + 1

    document: dict[str, object] = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "module": {
            "id": module.module_id,
            "kind": module.kind,
            "languages": sorted(module.languages),
        },
        "provenance": {
            "commit": commit,
            "sextant_version": SEXTANT_VERSION,
            "fact_schema_version": FACT_SCHEMA_VERSION,
            "scanners": [{"id": scanner_id, "version": scanner_version}],
        },
        "coverage": report.coverage,
        "gaps": PHASE_1_GAPS,
        "endpoints": {"inbound": inbound, "outbound": {}},
        "skipped_catalogs": [
            {"catalog_id": skipped.catalog_id,
             "missing_capabilities": list(skipped.missing_capabilities)}
            for skipped in report.skipped_catalogs
        ],
        "query": ["sextant module render"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
