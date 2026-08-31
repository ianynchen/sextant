"""Tests for M04 pass 2 (D01 "resolved_config", D02 §2i's `config_model`) —
`sextant.application.resolve.config.resolve_config`.

Facts and models are hand-built rather than compiled from the real fixture:
every behaviour here is a property of the GENERIC interpreter, so the model
dicts below invent their own source patterns and profile-activation key
rather than reusing Spring's own names — the same "a generic engine, not a
framework" discipline D02 §1 states for every engine style. Live-fixture
wiring (the real Spring model, `spring-web.yml`) is covered separately by
`test_pipeline.py`'s end-to-end resolve."""

from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.config import normalize_key, resolve_config
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import ConfigEntryFact, Document
from sextant.storage.duckdb.workspace import DuckDbWorkspace


def _document(relative_path: str) -> Document:
    return Document(
        document_id=relative_path,
        relative_path=relative_path,
        module_id="com.acme:orders-service",
        language="yaml",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="sextant-config-reader",
        scanner_version="0.1.0",
        content_hash="sha256:a",
        origin_entry="src/main/resources",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


def _write(root: Path, relative_path: str, entries: list[tuple[str, str, int]]) -> None:
    """One config file's worth of `config_entry` facts — `entries` is
    `(key_path, value, doc_index)`, mirroring a multi-document YAML file's
    own documents when more than one `doc_index` appears."""
    document = _document(relative_path)
    facts = [
        ConfigEntryFact(
            document_id=relative_path, key_raw=key, key_path=key, value=value, doc_index=doc_index
        )
        for key, value, doc_index in entries
    ]
    write_fact_file(root / "facts" / f"{relative_path}.jsonl", document, facts)


def _resolve(
    tmp_path: Path, files: dict[str, list[tuple[str, str, int]]], model: dict
) -> list[dict[str, object]]:
    for relative_path, entries in files.items():
        _write(tmp_path, relative_path, entries)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    catalog = Catalog(
        id="test-model",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("test-model.yml"),
        config_model=model,
    )
    resolve_config(workspace, [catalog])
    rows = workspace.query("resolved_config")
    workspace.close()
    return rows


def _row(rows: list[dict[str, object]], key: str, environment: str) -> dict[str, object]:
    return next(r for r in rows if r["key"] == key and r["environment"] == environment)


# --- Layering: source precedence and profile-variant-over-base ------------


def test_a_later_source_wins_and_a_profile_variant_wins_over_its_own_base(tmp_path: Path):
    """D02 §2i: "a later source in the list, and a profile variant of any
    source, both win over what came before" — the layering-order pin every
    real fixture pin (`boot.layer.probe`) depends on."""
    files = {
        "base.yml": [("probe", "base-value", 0)],
        "layer.yml": [("probe", "layer-value", 0)],
        "layer-prod.yml": [("probe", "layer-prod-value", 0)],
    }
    model = {
        "sources": [{"pattern": "base{-profile}.yml"}, {"pattern": "layer{-profile}.yml"}],
        "profiles": {"from_filename": "{-profile}", "default_profile": "default"},
    }
    rows = _resolve(tmp_path, files, model)
    assert _row(rows, "probe", "default")["value"] == "layer-value"
    assert _row(rows, "probe", "prod")["value"] == "layer-prod-value"


# --- Profile enumeration: filename marker and document-key activation -----


def test_profiles_enumerate_from_both_the_filename_marker_and_the_document_key(
    tmp_path: Path,
):
    """D02 §2i's closed profile-spelling vocabulary: `from_filename` and
    `from_document_key` both contribute to the SAME enumerated set — a
    profile named only by one mechanism still resolves."""
    files = {
        "app.yml": [
            ("probe", "base-value", 0),
            ("activate", "qa", 1),
            ("only.qa", "qa-value", 1),
        ],
        "app-stage.yml": [("probe", "stage-value", 0)],
    }
    model = {
        "sources": [{"pattern": "app{-profile}.yml"}],
        "profiles": {
            "from_filename": "{-profile}",
            "from_document_key": "activate",
            "default_profile": "default",
        },
    }
    rows = _resolve(tmp_path, files, model)
    assert {row["environment"] for row in rows} == {"default", "qa", "stage"}
    assert _row(rows, "probe", "default")["value"] == "base-value"
    assert _row(rows, "probe", "stage")["value"] == "stage-value"
    # `only.qa` is locked to the `qa` document and never leaks into `default`
    # or `stage` — each carries its own `probe`, unaffected by the doc-key
    # activated sibling document sharing its file.
    assert _row(rows, "only.qa", "qa")["value"] == "qa-value"


# --- Placeholder resolution: recursion, defaults, missing, cycles ---------


def test_a_placeholder_chain_resolves_through_to_its_literal(tmp_path: Path):
    """`${a}` -> `${b}` -> a literal: recursive substitution, not one hop."""
    files = {"app.yml": [("a", "${b}", 0), ("b", "literal-value", 0)]}
    model = {"sources": [{"pattern": "app.yml"}], "profiles": {"default_profile": "default"}}
    rows = _resolve(tmp_path, files, model)
    row = _row(rows, "a", "default")
    assert row["value"] == "literal-value"
    assert row["unresolved_reason"] is None


def test_a_missing_placeholder_with_a_default_takes_the_default(tmp_path: Path):
    files = {"app.yml": [("k", "${missing:fallback}", 0)]}
    model = {"sources": [{"pattern": "app.yml"}], "profiles": {"default_profile": "default"}}
    rows = _resolve(tmp_path, files, model)
    row = _row(rows, "k", "default")
    assert row["value"] == "fallback"
    assert row["unresolved_reason"] is None


def test_a_missing_placeholder_with_no_default_resolves_missing_key(tmp_path: Path):
    files = {"app.yml": [("k", "${missing}", 0)]}
    model = {"sources": [{"pattern": "app.yml"}], "profiles": {"default_profile": "default"}}
    rows = _resolve(tmp_path, files, model)
    row = _row(rows, "k", "default")
    assert row["value"] is None
    assert row["unresolved_reason"] == "missing_key"


def test_a_two_key_cycle_resolves_placeholder_cycle_for_both_keys(tmp_path: Path):
    files = {"app.yml": [("a", "${b}", 0), ("b", "${a}", 0)]}
    model = {"sources": [{"pattern": "app.yml"}], "profiles": {"default_profile": "default"}}
    rows = _resolve(tmp_path, files, model)
    assert _row(rows, "a", "default")["unresolved_reason"] == "placeholder_cycle"
    assert _row(rows, "b", "default")["unresolved_reason"] == "placeholder_cycle"
    assert _row(rows, "a", "default")["value"] is None
    assert _row(rows, "b", "default")["value"] is None


def test_an_undefined_env_shaped_placeholder_is_still_missing_key_not_environment(
    tmp_path: Path,
):
    """RULING (2F design §2): `environment` is reserved for a key the
    model's own sources declare as an environment import — this model (like
    Spring's 2F one) declares none, so a `${SOME_ENV_VAR}` chain ending in
    what LOOKS like an env-var name still resolves the same `missing_key`
    every other absent reference does, never the finer, undeclared reason."""
    files = {"app.yml": [("k", "${SOME_ENV_VAR}", 0)]}
    model = {"sources": [{"pattern": "app.yml"}], "profiles": {"default_profile": "default"}}
    rows = _resolve(tmp_path, files, model)
    row = _row(rows, "k", "default")
    assert row["value"] is None
    assert row["unresolved_reason"] == "missing_key"


# --- remote_source: a config-server import URL, never resolved from files -


def test_a_value_matching_a_declared_remote_prefix_resolves_remote_source(tmp_path: Path):
    files = {"app.yml": [("k", "remote:https://config.example/app", 0)]}
    model = {
        "sources": [{"pattern": "app.yml"}],
        "profiles": {"default_profile": "default"},
        "remote_prefixes": ["remote:"],
    }
    rows = _resolve(tmp_path, files, model)
    row = _row(rows, "k", "default")
    assert row["value"] is None
    assert row["unresolved_reason"] == "remote_source"
    assert row["source"] == "app.yml"


# --- "unresolved for prod, resolved for dev" is expressible ---------------


def test_a_key_resolved_in_one_profile_is_missing_key_in_another_where_undeclared(
    tmp_path: Path,
):
    """D01: "resolved for `dev`, unresolved for `prod` is expressible and
    meaningful" — the same key carries a resolved row in one profile's
    layering and an unresolved `missing_key` row in another's, never one
    row forced to answer for both."""
    files = {
        "app.yml": [
            ("activate", "default", 1),
            ("only.default", "v1", 1),
            ("activate", "prod", 2),
            ("only.prod", "v2", 2),
        ],
    }
    model = {
        "sources": [{"pattern": "app.yml"}],
        "profiles": {"from_document_key": "activate", "default_profile": "default"},
    }
    rows = _resolve(tmp_path, files, model)
    resolved = _row(rows, "only.default", "default")
    assert resolved["value"] == "v1"
    assert resolved["unresolved_reason"] is None
    missing = _row(rows, "only.default", "prod")
    assert missing["value"] is None
    assert missing["unresolved_reason"] == "missing_key"


# --- Pass 2's own contract: unconditional, empty in, empty out ------------


def test_resolve_config_is_a_noop_when_no_catalog_declares_a_model(tmp_path: Path):
    files = {"app.yml": [("k", "v", 0)]}
    model: dict = {}
    rows = _resolve(tmp_path, files, model)
    assert rows == []


# --- key_matching: relaxed --------------------------------------------------


def test_normalize_key_strips_case_dash_and_underscore():
    """Exported for reuse (2F design §4's field ladder, Task 8) — a pure
    function, not a method on anything, so it can be imported without
    pulling in the rest of this pass."""
    assert normalize_key("my-key") == normalize_key("MY_KEY") == normalize_key("myKey")


def test_relaxed_key_matching_resolves_a_placeholder_spelled_differently(tmp_path: Path):
    files = {"app.yml": [("myKey", "v1", 0), ("ref", "${MY_KEY}", 0)]}
    model = {
        "sources": [{"pattern": "app.yml"}],
        "profiles": {"default_profile": "default"},
        "key_matching": "relaxed",
    }
    rows = _resolve(tmp_path, files, model)
    row = _row(rows, "ref", "default")
    assert row["value"] == "v1"
    assert row["unresolved_reason"] is None
