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
        module_commit="a3f91c",
        tables=["endpoints", "shapes"],
        facts_files=4,
    )
    written = json.loads((tmp_path / "manifest.json").read_text())
    assert written["producer"]["catalog_hash"] == "sha256:abc"
    assert written["source"]["module_commit"] == "a3f91c"
    assert written["contents"] == {
        "facts": True,
        "graph": True,
        "tables": ["endpoints", "shapes"],
        "facts_files": 4,
    }
    assert written["environments"] == []  # nothing resolves profiles yet — honest
    assert written["gaps"] == ["reactive_flow_not_traced"]
    assert written["coverage"]["partial"] is False
