"""manifest.json — the D06 §3 contract that lets a bundle be refused instead
of silently joined. Written by `sextant module export` as the last act of the
exporter, from what `analyze` already wrote to metadata.json (M08 "never
re-analyzes") plus what the exporter itself derived (the catalog hash, the
tables and fact files it exported)."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from sextant.domain.version import GRAPH_SCHEMA_VERSION


def write_manifest(
    path: Path,
    metadata: dict[str, object],
    source: dict[str, object],
    catalog_hash: str,
    redaction_set_hash: str,
    module_commit: str,
    tables: list[str],
    facts_files: int,
    render: Sequence[str] = (),
    index: Sequence[str] = (),
) -> None:
    provenance = dict(cast(dict[str, object], metadata.get("provenance", {})))
    # `producer` carries exactly what analyze's provenance recorded, plus
    # graph_schema_version (provenance has none today) and what the exporter
    # itself derived.
    #
    # `redaction_set_hash` is one of the exporter's own, beside `catalog_hash`
    # and for the same reason (D05 §2 lists them together). It was reserved and
    # unwritten while nothing redacted; 2K design §1 gives it a producer, and
    # that producer is this exit — the workspace stays verbatim, so `analyze`
    # applies no rule set and its provenance could not honestly claim one.
    # What this field names is the set that masked THESE bytes, read from the
    # module's `.sextant.yml` at the moment they were written.
    producer: dict[str, object] = {
        "sextant_version": provenance.get("sextant_version"),
        "fact_schema_version": provenance.get("fact_schema_version"),
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        # Copied from what `analyze` wrote, never recomputed: the vocabulary the
        # entries were named in is the one that was current when the workspace was
        # built, which a later build of this exporter may not be.
        "boundary_vocabulary_version": metadata.get("boundary_vocabulary_version"),
        "scanners": provenance.get("scanners", []),
        "catalog_hash": catalog_hash,
        "redaction_set_hash": redaction_set_hash,
    }

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
            # What actually shipped under `render/` (2K Task 8 review, D06
            # §3's "names what actually travelled" rule extended to it) —
            # `[]` where `render` was never run, exactly like an empty
            # `tables` list would read, never an absent key. Named by the
            # caller (`cli/app.py`'s `module_export`) rather than derived
            # here, the same never-re-analyze-or-re-derive discipline every
            # other `contents` field already follows: this function writes
            # what it is told, not what it goes and looks for on disk.
            "render": list(render),
            # F8 §9.3 (W35). The index files that actually shipped under
            # `index/`, named by the caller for the same reason `render` is:
            # this function writes what it is told rather than looking on
            # disk. A consumer reads this list to know what it can load
            # WITHOUT opening a directory — which is the point of an index it
            # is meant to load once and grep.
            "index": list(index),
        },
        "gaps": metadata.get("gaps", []),
        "uncovered": metadata.get("uncovered", []),
        "skipped_catalogs": metadata.get("skipped_catalogs", []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
