import json
from pathlib import Path

from sextant.egress.export.manifest import write_manifest


def test_the_manifest_carries_provenance_coverage_and_contents(tmp_path: Path):
    metadata = {
        "module": {"id": "com.acme:orders-service", "kind": "service", "languages": ["java"]},
        "provenance": {
            "commit": "a3f91c",
            "sextant_version": "0.1.0",
            "fact_schema_version": "1.0.0",
            "scanners": [{"id": "asm", "version": "9.7"}],
        },
        "coverage": {"documents": 4, "partial_documents": 0},
        "environments": ["default", "prod"],
        "gaps": ["reactive_flow_not_traced"],
        "uncovered": [],
        "skipped_catalogs": [],
        "shapes": {"count": 2, "unexpanded_types": []},
    }
    write_manifest(
        tmp_path / "manifest.json",
        metadata,
        source={"repo": "git@github.com:acme/orders.git", "commit": "a3f91c"},
        catalog_hash="sha256:abc",
        redaction_set_hash="sha256:rules",
        module_commit="a3f91c",
        tables=["endpoints", "shapes"],
        facts_files=4,
    )
    written = json.loads((tmp_path / "manifest.json").read_text())
    assert written["producer"]["catalog_hash"] == "sha256:abc"
    # D06 §3 reserved this field and left it unwritten while nothing redacted.
    # 2K design §1 gives it a producer, and the producer is this exit: it names
    # the rule set that masked THESE bytes, beside the catalog hash that
    # derived them (D05 §2 lists the two together).
    assert written["producer"]["redaction_set_hash"] == "sha256:rules"
    assert written["source"]["module_commit"] == "a3f91c"
    assert written["contents"] == {
        "facts": True,
        "graph": True,
        "tables": ["endpoints", "shapes"],
        "facts_files": 4,
    }
    # Carried from metadata.json's own field (2F Task 9), never re-derived —
    # `write_metadata` is the one place `resolved_config`'s distinct
    # environments become this list.
    assert written["environments"] == ["default", "prod"]
    assert written["gaps"] == ["reactive_flow_not_traced"]
    assert written["coverage"]["partial"] is False


def test_the_manifest_reports_no_environments_when_metadata_names_none(tmp_path: Path):
    """A module analysed before pass 2 resolved anything (or with no config
    files at all) writes an honestly empty list — never a guess — the same
    claim `metadata.json` itself made."""
    metadata = {
        "module": {"id": "com.acme:orders-service", "kind": "service", "languages": ["java"]},
        "provenance": {"commit": "a3f91c", "sextant_version": "0.1.0"},
        "coverage": {"documents": 4, "partial_documents": 0},
        "gaps": [],
        "uncovered": [],
        "skipped_catalogs": [],
    }
    write_manifest(
        tmp_path / "manifest.json",
        metadata,
        source={"repo": "git@github.com:acme/orders.git", "commit": "a3f91c"},
        catalog_hash="sha256:abc",
        redaction_set_hash="sha256:rules",
        module_commit="a3f91c",
        tables=["endpoints"],
        facts_files=4,
    )
    written = json.loads((tmp_path / "manifest.json").read_text())
    assert written["environments"] == []
