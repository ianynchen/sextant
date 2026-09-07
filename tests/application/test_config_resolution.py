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

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.config import resolve_config
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
        fact_schema_version=2,
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
    resolve_config(workspace, [_catalog(model)])
    rows = workspace.query("resolved_config")
    workspace.close()
    return rows


def _row(rows: list[dict[str, object]], key: str, environment: str) -> dict[str, object]:
    return next(r for r in rows if r["key"] == key and r["environment"] == environment)


def _catalog(model: dict) -> Catalog:
    return Catalog(
        id="test-model",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("test-model.yml"),
        config_model=model,
    )


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


def test_a_profile_variant_file_wins_over_an_inline_activated_document_of_its_own_base(
    tmp_path: Path,
):
    """Controller ruling I-1 (fix round 1): a `doc_index` comparison ACROSS
    files is the wrong tiebreak — an inline `on-profile`-activated document
    inside the base file is not automatically "later" than a same-profile
    variant FILE just because its own `doc_index` happens to be numerically
    higher. Spring's own real resource order puts the variant FILE last:
    both `layer.yml` (an inline `prod`-activated second document) and
    `layer-prod.yml` (the filename variant) set `probe` for `prod` — the
    FILE must win, and `source` must name it."""
    files = {
        "layer.yml": [
            ("probe", "inline-prod-value", 1),
            ("activate", "prod", 1),
        ],
        "layer-prod.yml": [("probe", "file-prod-value", 0)],
    }
    model = {
        "sources": [{"pattern": "layer{-profile}.yml"}],
        "profiles": {
            "from_filename": "{-profile}",
            "from_document_key": "activate",
            "default_profile": "default",
        },
    }
    rows = _resolve(tmp_path, files, model)
    row = _row(rows, "probe", "prod")
    assert row["value"] == "file-prod-value"
    assert row["source"] == "layer-prod.yml"


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
    # `probe`'s own value differs per profile — `default` keeps `app.yml`'s
    # unlocked base value, `stage` gets `app-stage.yml`'s filename-locked
    # one — proving both profiles a real key can carry are visible.
    assert _row(rows, "probe", "default")["value"] == "base-value"
    assert _row(rows, "probe", "stage")["value"] == "stage-value"
    # `only.qa` is locked to the `qa` document (`from_document_key`) and
    # resolves only under the `qa` profile that document activated.
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


# --- key_matching scopes LOOKUPS only, never the layering merge -----------


def test_exact_merge_keeps_two_differently_spelled_keys_as_separate_rows(tmp_path: Path):
    """Controller ruling I-2 (fix round 1): `key_matching: relaxed` widens
    `${...}` REFERENCE lookups, never the merge itself — a merge keys on a
    `config_entry`'s own exact `key_path`, always, regardless of
    `key_matching`. `billing.url` and `billing.URL` are genuinely two
    different keys in the files, so they stay two different rows even under
    a `relaxed` model — no case-folding ever collapses them."""
    files = {"app.yml": [("billing.url", "v1", 0), ("billing.URL", "v2", 0)]}
    model = {
        "sources": [{"pattern": "app.yml"}],
        "profiles": {"default_profile": "default"},
        "key_matching": "relaxed",
    }
    rows = _resolve(tmp_path, files, model)
    assert _row(rows, "billing.url", "default")["value"] == "v1"
    assert _row(rows, "billing.URL", "default")["value"] == "v2"


# --- Custom placeholder delimiters (D02 §2i's `placeholders` block) -------


def test_custom_placeholder_delimiters_are_honored_and_the_default_spelling_is_inert(
    tmp_path: Path,
):
    """The `${...}` grammar is not hardcoded — `placeholders` is catalog
    data (D02 §2i). A model declaring `<<`/`>>` substitutes through THOSE
    delimiters, and the ordinary `${...}` spelling — carrying neither — is
    left untouched, plain literal text."""
    files = {
        "app.yml": [
            ("a", "<<b>>", 0),
            ("b", "literal-value", 0),
            ("c", "${b}", 0),
        ]
    }
    model = {
        "sources": [{"pattern": "app.yml"}],
        "profiles": {"default_profile": "default"},
        "placeholders": {"open": "<<", "close": ">>", "default_separator": ":"},
    }
    rows = _resolve(tmp_path, files, model)
    assert _row(rows, "a", "default")["value"] == "literal-value"
    row_c = _row(rows, "c", "default")
    assert row_c["value"] == "${b}"
    assert row_c["unresolved_reason"] is None


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


def test_running_resolve_config_twice_leaves_the_same_row_count(tmp_path: Path):
    """Controller ruling I-4 (fix round 1): `resolved_config_reset` runs
    before EVERY pass, not just the first — a second `resolve_config` call
    into the SAME workspace must replace, not double, the previous run's
    rows. Removing the reset would fail this test with `second_count ==
    2 * first_count`."""
    files = {"app.yml": [("k", "v", 0)]}
    model = {"sources": [{"pattern": "app.yml"}], "profiles": {"default_profile": "default"}}
    for relative_path, entries in files.items():
        _write(tmp_path, relative_path, entries)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    catalog = _catalog(model)
    resolve_config(workspace, [catalog])
    first_count = len(workspace.query("resolved_config"))
    resolve_config(workspace, [catalog])
    second_count = len(workspace.query("resolved_config"))
    workspace.close()
    assert first_count > 0
    assert second_count == first_count


# --- key_matching: relaxed and exact ---------------------------------------


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


def test_exact_key_matching_rejects_a_relaxed_spelling_placeholder_lookup(tmp_path: Path):
    """The other half of I-3's pin: `key_matching: exact` (D02 §2i) means
    exactly that — the SAME `${MY_KEY}` spelling that the relaxed test above
    resolves must fail here, since `MY_KEY` is not the literal `myKey`."""
    files = {"app.yml": [("myKey", "v1", 0), ("ref", "${MY_KEY}", 0)]}
    model = {
        "sources": [{"pattern": "app.yml"}],
        "profiles": {"default_profile": "default"},
        "key_matching": "exact",
    }
    rows = _resolve(tmp_path, files, model)
    row = _row(rows, "ref", "default")
    assert row["value"] is None
    assert row["unresolved_reason"] == "missing_key"


# --- The filename marker: undashed `{profile}`, and gated by from_filename -


def test_an_undashed_profile_placeholder_names_the_whole_filename_component(tmp_path: Path):
    """D02 §2i reserves `{profile}` (no dash) for a layout like node-config's
    whole-filename profile, e.g. `{profile}.json` — the bare match names the
    profile whether or not it is empty, unlike `{-profile}`'s dash
    convention. `prod.cfg` names profile `prod`; nothing at all is the base,
    so `k` never resolves for `default`."""
    files = {"prod.cfg": [("k", "v", 0)]}
    model = {
        "sources": [{"pattern": "{profile}.cfg"}],
        "profiles": {"from_filename": "{profile}", "default_profile": "default"},
    }
    rows = _resolve(tmp_path, files, model)
    assert {row["environment"] for row in rows} == {"default", "prod"}
    assert _row(rows, "k", "prod")["value"] == "v"
    assert _row(rows, "k", "default")["unresolved_reason"] == "missing_key"


def test_filename_profile_splitting_only_applies_when_from_filename_is_declared(
    tmp_path: Path,
):
    """Controller ruling M-a (fix round 1): filename splitting is one of
    D02 §2i's three declared profile mechanisms — a model that never
    declares `profiles.from_filename` never gets it, even where a source
    pattern spells `{-profile}`. `app-prod.yml` never becomes a `prod`
    profile here: only `default` ever enumerates, and `app.yml`'s own
    (literally, exactly matched) value is the only one that wins it."""
    files = {
        "app.yml": [("probe", "base-value", 0)],
        "app-prod.yml": [("probe", "variant-value", 0)],
    }
    model = {
        "sources": [{"pattern": "app.yml"}, {"pattern": "app{-profile}.yml"}],
        "profiles": {"default_profile": "default"},  # from_filename NOT declared
    }
    rows = _resolve(tmp_path, files, model)
    assert {row["environment"] for row in rows} == {"default"}
    assert _row(rows, "probe", "default")["value"] == "base-value"


# --- from_key_prefix: reserved, refused loudly, never silently ignored ----


def test_a_declared_from_key_prefix_mechanism_is_refused_as_reserved_unimplemented(
    tmp_path: Path,
):
    """Controller ruling M-a (fix round 1): `from_key_prefix` (Quarkus's
    `%dev.` style) is documented in D02 §2i and reserved, not implemented —
    a model declaring it must be refused loudly, naming the catalog, never
    silently produce a resolve that quietly ignores the mechanism it
    claimed to use."""
    files = {"app.yml": [("k", "v", 0)]}
    model = {
        "sources": [{"pattern": "app.yml"}],
        "profiles": {"default_profile": "default", "from_key_prefix": "%dev."},
    }
    for relative_path, entries in files.items():
        _write(tmp_path, relative_path, entries)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    with pytest.raises(CatalogError, match="from_key_prefix"):
        resolve_config(workspace, [_catalog(model)])
    workspace.close()
