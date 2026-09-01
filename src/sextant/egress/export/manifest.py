"""manifest.json — the D06 §3 contract that lets a bundle be refused instead
of silently joined. Written by `sextant module export` as the last act of the
exporter, from what `analyze` already wrote to metadata.json (M08 "never
re-analyzes") plus what the exporter itself derived (the catalog hash, the
tables and fact files it exported)."""

import json
from pathlib import Path
from typing import cast

from sextant.domain.version import GRAPH_SCHEMA_VERSION


def write_manifest(
    path: Path,
    metadata: dict[str, object],
    source: dict[str, object],
    catalog_hash: str,
    module_commit: str,
    tables: list[str],
    facts_files: int,
) -> None:
    provenance = dict(cast(dict[str, object], metadata.get("provenance", {})))
    # `producer` carries exactly what analyze's provenance recorded, plus
    # graph_schema_version (provenance has none today) and what the exporter
    # itself derived. `redaction_set_hash` has no producer yet (nothing
    # redacts), so it is carried only if a future analyze starts writing it —
    # never invented here.
    producer: dict[str, object] = {
        "sextant_version": provenance.get("sextant_version"),
        "fact_schema_version": provenance.get("fact_schema_version"),
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "scanners": provenance.get("scanners", []),
        "catalog_hash": catalog_hash,
    }
    if "redaction_set_hash" in provenance:
        producer["redaction_set_hash"] = provenance["redaction_set_hash"]

    coverage = dict(cast(dict[str, object], metadata.get("coverage", {})))
    partial = coverage.get("partial")
    if partial is None:
        partial = cast(int, coverage.get("partial_documents", 0)) > 0
    coverage["partial"] = bool(partial)

    document: dict[str, object] = {
        "module": metadata["module"],
        "source": {**source, "module_commit": module_commit},
        "producer": producer,
        # Carried straight from metadata.json (D06 §3 "environments"),
        # which `write_metadata` itself derives from `resolved_config`'s
        # distinct environments — never re-derived here, the same
        # never-re-analyze rule every other field on this manifest follows.
        "environments": metadata.get("environments", []),
        "coverage": coverage,
        "contents": {
            "facts": True,
            "graph": True,
            "tables": list(tables),
            "facts_files": facts_files,
        },
        "gaps": metadata.get("gaps", []),
        "uncovered": metadata.get("uncovered", []),
        "skipped_catalogs": metadata.get("skipped_catalogs", []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
