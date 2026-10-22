import json
from pathlib import Path

from click.testing import CliRunner

from sextant.application.boundary.vocabulary import KINDS
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


def test_metadata_carries_the_catalog_hash_the_exporter_then_copies(
    analyzed_workspace_copy: Path,
):
    """`analyze` records the hash of the framework knowledge it ran with, because the diff
    (spec 2026-10-22 §3d) reads it when the catalogs are no longer in hand; `export` COPIES it
    into `producer`. The sentinel written into `metadata.json` is not any hash of the
    shipped catalogs, so an exporter that recomputed would fail here."""
    metadata_path = analyzed_workspace_copy / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    assert metadata["catalog_hash"].startswith("sha256:")
    metadata["catalog_hash"] = "sha256:recorded-at-analyze"
    metadata_path.write_text(json.dumps(metadata))
    result = CliRunner().invoke(
        cli,
        ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((Path(result.output.strip()) / "manifest.json").read_text())
    assert manifest["producer"]["catalog_hash"] == "sha256:recorded-at-analyze"


def test_each_skipped_catalog_names_the_kinds_it_would_have_fed(analyzed_workspace_copy: Path):
    """The map's `not-observable` needs to know what a skipped catalog would have fed, and a
    bundle's reader has no catalogs. `spring-rsocket` is skipped on the fixture; it is an
    inbound `annotation_driven` catalog naming a shape model, so it feeds the endpoint and
    data-contract kinds, in registry order (not alphabetical)."""
    metadata = json.loads((analyzed_workspace_copy / "metadata.json").read_text())
    rsocket = next(s for s in metadata["skipped_catalogs"] if s["catalog_id"] == "spring-rsocket")
    assert rsocket["feeds"] == ["endpoint", "data-contract"]
    assert all("feeds" in skipped for skipped in metadata["skipped_catalogs"])


def test_each_skipped_catalog_records_which_gate_skipped_it(analyzed_workspace_copy: Path):
    """The cause is data the map reads (ruled 2026-10-22), never parsed from the reason. On
    the fixture both skips are the dependency gate on a classpath Maven resolved: neither
    RSocket nor Spring Cloud Gateway is on it."""
    metadata = json.loads((analyzed_workspace_copy / "metadata.json").read_text())
    assert metadata["module"]["dependency_source"] == "maven"
    assert {s["catalog_id"]: s["cause"] for s in metadata["skipped_catalogs"]} == {
        "spring-rsocket": "framework_absent",
        "spring-cloud-gateway-properties": "framework_absent",
    }


def test_the_manifest_carries_feeds_with_the_skipped_catalogs(analyzed_workspace_copy: Path):
    result = CliRunner().invoke(
        cli,
        ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((Path(result.output.strip()) / "manifest.json").read_text())
    rsocket = next(s for s in manifest["skipped_catalogs"] if s["catalog_id"] == "spring-rsocket")
    assert rsocket["feeds"] == ["endpoint", "data-contract"]
    assert rsocket["cause"] == "framework_absent"


def test_catalogs_run_counts_per_kind(analyzed_workspace_copy: Path):
    """How many catalogs that RAN feed each kind. `module` and `boundary-property` are not
    catalog-fed, so they never appear; a kind nothing ran for does not appear either."""
    metadata = json.loads((analyzed_workspace_copy / "metadata.json").read_text())
    run = metadata["catalogs_run"]
    assert run["schedule"] == 1
    assert run["endpoint"] > 5
    assert "module" not in run and "boundary-property" not in run
    assert all(count > 0 for count in run.values())


def test_export_recomputes_the_catalog_hash_only_for_a_workspace_analysed_before_it_was_recorded(
    analyzed_workspace_copy: Path,
):
    """A workspace analysed before `analyze` recorded `catalog_hash` has no such key. The
    exporter then falls back to hashing the catalogs it has now, as it always did — a
    labelled legacy path, not the normal one."""
    metadata_path = analyzed_workspace_copy / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    recorded = metadata.pop("catalog_hash")
    metadata_path.write_text(json.dumps(metadata))
    result = CliRunner().invoke(
        cli,
        ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((Path(result.output.strip()) / "manifest.json").read_text())
    assert manifest["producer"]["catalog_hash"] == recorded


def test_metadata_and_manifest_carry_the_map(analyzed_workspace_copy: Path):
    """`analyze` writes the map into `metadata.json` from the measurements it has in hand
    (spec 2026-10-22 §4); `export` COPIES it, so a sentinel planted in `metadata.json` must
    come out of the manifest unchanged — an exporter that recomputed would not carry it."""
    metadata_path = analyzed_workspace_copy / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    observability = metadata["observability"]
    assert observability["boundary_vocabulary_version"] == 1
    # `metadata.json` is written with sorted keys, so the file cannot hold registry order.
    assert set(observability["kinds"]) == set(KINDS)
    # Re-measured 2026-10-22 (the cause ruling): the fixture's two skipped catalogs,
    # `spring-rsocket` and `spring-cloud-gateway-properties`, are skipped because their
    # frameworks are absent from the classpath Maven resolved — nothing to observe — so no
    # kind is degraded and every one reads `observable`. Before the ruling `endpoint` and
    # `data-contract` read `partial` on these two skips alone.
    assert {
        name: kind["verdict"] for name, kind in observability["kinds"].items()
    } == dict.fromkeys(KINDS, "observable")
    assert all(kind["reasons"] == [] for kind in observability["kinds"].values())
    assert observability["stated_boundaries"] == metadata["gaps"]
    # The two counts the attribute verdicts read are measured off the rows, beside the rest
    # of `coverage`, and the map is computed from them.
    coverage = metadata["coverage"]
    # Counted over the rows the `endpoint` kind holds (inbound and `both`), so the share is
    # never inflated by outbound rows, which belong to `dependency` and carry no format
    # attribute on the map. The fixture's inbound total is strictly below its all-rows total.
    assert 0 < coverage["format_unresolved"] <= coverage["inbound_total"]
    assert coverage["inbound_total"] == sum(metadata["endpoints"]["inbound"].values())
    assert observability["attributes"]["endpoint"]["format"] == {
        "verdict": "partial",
        "reasons": [
            f"{coverage['format_unresolved']} of {coverage['inbound_total']} formats unresolved"
        ],
    }

    observability["stated_boundaries"] = ["planted-sentinel"]
    metadata_path.write_text(json.dumps(metadata))
    result = CliRunner().invoke(
        cli,
        ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((Path(result.output.strip()) / "manifest.json").read_text())
    assert manifest["observability"] == observability
    assert manifest["catalogs_run"] == metadata["catalogs_run"]


def test_the_manifest_copies_the_map_and_the_catalog_counts_it_was_computed_from(tmp_path: Path):
    metadata = {
        "module": {"id": "com.acme:orders-service", "kind": "service", "languages": ["java"]},
        "provenance": {"commit": "a3f91c", "sextant_version": "0.1.0"},
        "coverage": {"documents": 4, "partial_documents": 0},
        "gaps": [],
        "uncovered": [],
        "skipped_catalogs": [],
        "catalogs_run": {"endpoint": 2},
        "observability": {"kinds": {"endpoint": {"verdict": "observable", "reasons": []}}},
    }
    write_manifest(
        tmp_path / "manifest.json",
        metadata,
        source={"repo": "r", "commit": "a3f91c"},
        catalog_hash="sha256:abc",
        redaction_set_hash="sha256:rules",
        module_commit="a3f91c",
        tables=[],
        facts_files=0,
    )
    written = json.loads((tmp_path / "manifest.json").read_text())
    assert written["observability"] == metadata["observability"]
    assert written["catalogs_run"] == {"endpoint": 2}


def test_a_manifest_from_metadata_without_a_map_carries_no_map(tmp_path: Path):
    """Metadata written before the map existed has neither key; the manifest then has
    neither, rather than a placeholder — `api.observability` computes the labelled degraded
    map from what is there."""
    metadata = {
        "module": {"id": "com.acme:orders-service", "kind": "service", "languages": ["java"]},
        "provenance": {"commit": "a3f91c", "sextant_version": "0.1.0"},
        "coverage": {"documents": 4, "partial_documents": 0},
    }
    write_manifest(
        tmp_path / "manifest.json",
        metadata,
        source={"repo": "r", "commit": "a3f91c"},
        catalog_hash="sha256:abc",
        redaction_set_hash="sha256:rules",
        module_commit="a3f91c",
        tables=[],
        facts_files=0,
    )
    written = json.loads((tmp_path / "manifest.json").read_text())
    assert "observability" not in written and "catalogs_run" not in written
