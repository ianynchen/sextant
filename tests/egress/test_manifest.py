import json
from pathlib import Path

from click.testing import CliRunner

from sextant.cli.app import cli
from sextant.egress.export.manifest import write_manifest

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "orders-service"


def test_the_manifest_carries_provenance_coverage_and_contents(tmp_path: Path):
    metadata = {
        "module": {"id": "com.acme:orders-service", "kind": "service", "languages": ["java"]},
        "provenance": {
            "commit": "a3f91c",
            "sextant_version": "0.1.0",
            "fact_schema_version": 2,
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
        # No render/ shipped — `[]`, never an absent key (2K Task 8 review).
        "render": [],
        # Nor index/ (F8 §9.3, W35), and for the same reason: a consumer reads this list
        # to know what it can load without opening a directory, so an absent key would
        # make "nothing shipped" indistinguishable from "this manifest predates the key".
        "index": [],
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


def test_the_manifest_names_the_render_files_it_ships(tmp_path: Path):
    """2K Task 8 review (Task 4's own review flagged the gap): the bundle
    grew a `render/` subdirectory (2K design §6b) that `contents` never
    declared. `write_manifest` writes exactly what the caller names — the
    same never-re-derive discipline `tables`/`facts_files` already follow —
    so this pins the field existing and carrying what was actually passed,
    not that `cli/app.py` happened to copy the right files (that wiring is
    `tests/cli/test_app.py`'s own job)."""
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
        render=["architecture.md", "architecture.html"],
    )
    written = json.loads((tmp_path / "manifest.json").read_text())
    assert written["contents"]["render"] == ["architecture.md", "architecture.html"]


def test_the_manifest_producer_copies_the_vocabulary_version_from_metadata(tmp_path: Path):
    """FR-21: the producer block names the vocabulary generation the bundle's boundary
    entries were derived under. It is COPIED from `metadata.json`, never recomputed — the
    sentinel is not the current stamp, so a recomputing exporter would fail here."""
    metadata = {
        "module": {"id": "com.acme:orders-service", "kind": "service", "languages": ["java"]},
        "provenance": {"sextant_version": "0.1.0", "fact_schema_version": 5, "scanners": []},
        "boundary_vocabulary_version": 7,
    }
    write_manifest(
        tmp_path / "manifest.json",
        metadata,
        source={},
        catalog_hash="sha256:abc",
        redaction_set_hash="sha256:rules",
        module_commit="a3f91c",
        tables=[],
        facts_files=0,
    )
    written = json.loads((tmp_path / "manifest.json").read_text())
    assert written["producer"]["boundary_vocabulary_version"] == 7


def test_metadata_and_manifest_carry_the_vocabulary_version(analyzed_workspace_copy: Path):
    """End to end on the real fixture: `analyze` stamps `metadata.json` and `export` carries
    the same number into the bundle manifest's `producer`."""
    metadata = json.loads((analyzed_workspace_copy / "metadata.json").read_text())
    assert metadata["boundary_vocabulary_version"] == 1
    result = CliRunner().invoke(
        cli,
        ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((Path(result.output.strip()) / "manifest.json").read_text())
    assert manifest["producer"]["boundary_vocabulary_version"] == 1
