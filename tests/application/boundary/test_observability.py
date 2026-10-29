"""The observability map (spec 2026-10-22-boundary-vocabulary-and-diff §4, FR-23): a pure
function of the metadata dictionary `analyze` wrote, so each test hands it a dictionary and
asserts the verdicts and reasons that come back. The fixture-level checks (the map really is
in `metadata.json` and the manifest) live in `tests/egress/test_manifest.py` and
`tests/api/test_facade.py`."""

import copy
import json

import pytest

from sextant.application.boundary.observability import (
    ObservabilityMap,
    Verdict,
    observability_of,
)
from sextant.application.boundary.vocabulary import KINDS
from sextant.domain.version import BOUNDARY_VOCABULARY_VERSION

_CODE_GROUNDED = [name for name, kind in KINDS.items() if kind.grounded_in_code]

# Shaped like the fixture's `metadata.json`: one catalog skipped (it feeds `endpoint` and
# `data-contract`), every kind otherwise fed, formats and peers all resolved.
BASE: dict[str, object] = {
    "boundary_vocabulary_version": 3,
    "module": {"id": "com.acme:orders-service", "dependency_source": "maven"},
    "uncovered": [],
    "coverage": {
        "documents": 4,
        "partial_documents": 0,
        "format_unresolved": 0,
        "inbound_total": 10,
        "peer_unresolved": 0,
        "outbound_total": 3,
    },
    "skipped_catalogs": [
        {
            "catalog_id": "spring-rsocket",
            "missing_capabilities": ["artifact:spring-messaging-rsocket"],
            "feeds": ["endpoint", "data-contract"],
            "cause": "missing_capability",
        }
    ],
    "catalogs_run": {
        "endpoint": 7,
        "dependency": 3,
        "data-contract": 4,
        "schedule": 1,
        "error-handler": 1,
    },
    "gaps": ["config_as_code_not_read"],
}


def _with(**overrides: object) -> dict[str, object]:
    return {**copy.deepcopy(BASE), **overrides}


def test_a_clean_analysis_is_observable_except_what_a_skipped_catalog_would_have_fed():
    m = observability_of(BASE)

    assert m.boundary_vocabulary_version == BOUNDARY_VOCABULARY_VERSION
    assert list(m.kinds) == list(KINDS)
    assert m.kinds["endpoint"] == Verdict(
        "partial", ("catalog skipped: spring-rsocket (artifact:spring-messaging-rsocket)",)
    )
    assert m.kinds["data-contract"].verdict == "partial"
    for name in ("module", "boundary-property", "dependency", "schedule", "error-handler"):
        assert m.kinds[name] == Verdict("observable", ())
    assert m.attributes == {}


def test_an_uncovered_file_degrades_every_code_grounded_kind_and_names_the_first_three():
    m = observability_of(
        _with(uncovered=["z/Z.java", "d/D.java", "a/A.java", "b/B.java", "c/C.java"])
    )

    for name in _CODE_GROUNDED:
        assert "uncovered files: 5 (a/A.java, b/B.java, c/C.java)" in m.kinds[name].reasons
        assert m.kinds[name].verdict == "partial"
    assert m.kinds["module"] == Verdict("observable", ())
    assert m.kinds["boundary-property"] == Verdict("observable", ())


def test_partial_documents_degrade_every_code_grounded_kind_with_the_count():
    coverage = {**BASE["coverage"], "partial_documents": 2}  # type: ignore[dict-item]
    m = observability_of(_with(coverage=coverage))

    for name in _CODE_GROUNDED:
        assert "partial documents: 2" in m.kinds[name].reasons
        assert m.kinds[name].verdict == "partial"


def test_declared_dependencies_degrade_only_dependency_and_data_contract():
    module = {"id": "com.acme:orders-service", "dependency_source": "declared"}
    m = observability_of(_with(module=module, skipped_catalogs=[]))

    reason = "dependencies declared, not resolved by the build tool"
    assert m.kinds["dependency"] == Verdict("partial", (reason,))
    assert m.kinds["data-contract"] == Verdict("partial", (reason,))
    for name in ("endpoint", "schedule", "error-handler", "module", "boundary-property"):
        assert m.kinds[name] == Verdict("observable", ())


def test_a_kind_whose_every_catalog_was_skipped_is_not_observable():
    run = {"endpoint": 0, "dependency": 3, "schedule": 1}
    skipped = [
        {"catalog_id": "b-cat", "missing_capabilities": ["y"], "feeds": ["endpoint"],
         "cause": "missing_capability"},
        {"catalog_id": "a-cat", "missing_capabilities": ["x1", "x2"], "feeds": ["endpoint"],
         "cause": "missing_capability"},
    ]  # fmt: skip
    m = observability_of(_with(catalogs_run=run, skipped_catalogs=skipped))

    assert m.kinds["endpoint"] == Verdict(
        "not-observable", ("catalog skipped: a-cat (x1; x2)", "catalog skipped: b-cat (y)")
    )
    # absent from `catalogs_run` counts as zero, and nothing skipped feeds it: nothing could
    # have fed `error-handler` here, which is the truth, not a gap.
    assert m.kinds["error-handler"] == Verdict("observable", ())


def test_a_skipped_catalog_does_not_make_a_kind_not_observable_while_another_ran():
    m = observability_of(BASE)

    assert m.kinds["endpoint"].verdict == "partial"


# --- why a catalog was skipped (`cause`, ruled at the final review 2026-10-22) -------------

_ABSENT = (
    "a build declaration of one of org.springframework.kafka:spring-kafka — none is in this "
    "module's dependency set as the build tool resolved it, transitives included"
)


def _skip(catalog_id: str, cause: str | None, reason: str, feeds: list[str]) -> dict[str, object]:
    skip: dict[str, object] = {"catalog_id": catalog_id, "missing_capabilities": [reason],
                               "feeds": feeds}  # fmt: skip
    if cause is not None:
        skip["cause"] = cause
    return skip


@pytest.mark.parametrize("source", ["maven", "gradle"])
def test_a_framework_absent_from_a_resolved_classpath_is_not_a_gap(source: str):
    """(a) The build tool resolved the classpath, transitives included, and the catalog's
    framework is not on it: there is nothing to observe, so the skip neither degrades the
    kind nor counts toward `not-observable` — even where no catalog feeding it ran."""
    skipped = [_skip("spring-kafka", "framework_absent", _ABSENT, ["endpoint", "dependency"])]
    module = {"id": "com.acme:orders-service", "dependency_source": source}
    m = observability_of(
        _with(module=module, skipped_catalogs=skipped, catalogs_run={"endpoint": 3})
    )

    assert m.kinds["endpoint"] == Verdict("observable", ())
    assert m.kinds["dependency"] == Verdict("observable", ())


def test_a_missing_extractor_capability_still_degrades_the_kinds_it_feeds():
    """(b) The framework may well be in use; the extractor could not read what the catalog
    needs. That is a gap whatever the classpath says."""
    skipped = [_skip("grpc-java", "missing_capability", "proto_services", ["endpoint"])]
    m = observability_of(_with(skipped_catalogs=skipped, catalogs_run={}))

    assert m.kinds["endpoint"] == Verdict(
        "not-observable", ("catalog skipped: grpc-java (proto_services)",)
    )


def test_on_a_declared_classpath_a_framework_absent_skip_stays_a_reason():
    """(c) Maven could not be asked (OI-167's boundary): the dependency set is the build
    FILE's, a starter's transitives are not in it, and absence is not proven."""
    skipped = [_skip("spring-kafka", "framework_absent", _ABSENT, ["endpoint"])]
    module = {"id": "com.acme:orders-service", "dependency_source": "declared"}
    m = observability_of(_with(module=module, skipped_catalogs=skipped))

    assert m.kinds["endpoint"] == Verdict(
        "partial", (f"catalog skipped: spring-kafka ({_ABSENT})",)
    )


def test_unrecorded_coordinates_still_degrade_on_a_resolved_classpath():
    """Recorded no coordinates at all: the question was never answered."""
    skipped = [_skip("jax-rs", "dependencies_unrecorded", "why", ["endpoint"])]
    m = observability_of(_with(skipped_catalogs=skipped))

    assert m.kinds["endpoint"] == Verdict("partial", ("catalog skipped: jax-rs (why)",))


@pytest.mark.parametrize("source", ["maven", "declared"])
def test_a_superseded_catalog_is_not_a_gap_on_any_classpath(source: str):
    """A sibling catalog reading the same annotations ran in its place (`detect.superseded_by`
    — `quarkus-rest` for `jakarta-jaxrs`), so the kind was fed: no reason, and no part in
    `not-observable` even where the counts say nothing else fed it (ruled 2026-10-22)."""
    skipped = [_skip("jakarta-jaxrs", "superseded", "superseded by io.quarkus:quarkus-rest",
                     ["endpoint"])]  # fmt: skip
    module = {"id": "com.acme:orders-service", "dependency_source": source}
    m = observability_of(_with(module=module, skipped_catalogs=skipped, catalogs_run={}))

    assert m.kinds["endpoint"] == Verdict("observable", ())


def test_a_skip_recorded_without_a_cause_is_a_gap_and_says_why():
    """An old manifest's skips carry no `cause`: each is counted as a gap, the old rule,
    honest for data that cannot say otherwise — and the reason says so."""
    skipped = [_skip("spring-kafka", None, _ABSENT, ["endpoint"])]
    m = observability_of(_with(skipped_catalogs=skipped))

    assert m.kinds["endpoint"] == Verdict(
        "partial",
        (f"catalog skipped: spring-kafka ({_ABSENT}; cause unrecorded, counted as a gap)",),
    )


@pytest.mark.pins("boundary.the-static-GAP-list-is-stated-never-a-verdict")
def test_the_static_gap_list_is_stated_never_a_verdict():
    m = observability_of(_with(gaps=["config_as_code_not_read"]))

    assert m.kinds["boundary-property"].verdict == "observable"
    assert m.kinds["boundary-property"].reasons == ()
    assert all("config_as_code_not_read" not in v.reasons for v in m.kinds.values())
    assert m.stated_boundaries == ("config_as_code_not_read",)


def test_an_old_manifest_gets_a_labelled_degraded_map():
    old = {k: v for k, v in BASE.items() if k != "catalogs_run"}
    # The counts were not recorded then either, and `uncovered` is deliberately non-empty
    # to show the single reason stands alone.
    old["uncovered"] = ["a/A.java"]
    old["coverage"] = {"documents": 4, "partial_documents": 0}
    m = observability_of(old)

    reason = "catalog kinds unrecorded: manifest predates boundary vocabulary 1"
    for name in _CODE_GROUNDED:
        assert m.kinds[name] == Verdict("partial", (reason,))
    assert m.kinds["module"] == Verdict("observable", ())
    assert m.kinds["boundary-property"] == Verdict("observable", ())
    assert m.attributes == {}
    assert m.stated_boundaries == ("config_as_code_not_read",)


def test_unresolved_formats_and_peers_are_attribute_verdicts_with_their_share():
    coverage = {
        **BASE["coverage"],  # type: ignore[dict-item]
        "format_unresolved": 4,
        "inbound_total": 10,
        "peer_unresolved": 1,
        "outbound_total": 3,
    }
    m = observability_of(_with(coverage=coverage))

    assert m.attributes == {
        "endpoint": {"format": Verdict("partial", ("4 of 10 formats unresolved",))},
        "dependency": {"peer": Verdict("partial", ("1 of 3 peers unresolved",))},
    }
    # an attribute verdict never moves the kind's own verdict
    assert m.kinds["dependency"] == Verdict("observable", ())


def test_to_json_is_the_documented_shape_in_registry_order():
    coverage = {**BASE["coverage"], "format_unresolved": 4}  # type: ignore[dict-item]
    out = observability_of(_with(coverage=coverage)).to_json()

    assert list(out) == ["boundary_vocabulary_version", "kinds", "attributes", "stated_boundaries"]
    assert list(out["kinds"]) == list(KINDS)  # type: ignore[arg-type]
    assert out["kinds"]["module"] == {"verdict": "observable", "reasons": []}  # type: ignore[index]
    assert out["attributes"] == {  # type: ignore[comparison-overlap]
        "endpoint": {"format": {"verdict": "partial", "reasons": ["4 of 10 formats unresolved"]}}
    }
    assert out["stated_boundaries"] == ["config_as_code_not_read"]
    json.dumps(out)


def test_the_map_is_stamped_with_the_vocabulary_version_the_metadata_recorded():
    """The map describes the analysis it was computed from, so its stamp is that analysis's
    — `metadata.json`'s top-level key, or a manifest's `producer` — and the current
    constant only where neither recorded one."""
    assert observability_of(_with(boundary_vocabulary_version=7)).boundary_vocabulary_version == 7
    manifest = {k: v for k, v in BASE.items() if k != "boundary_vocabulary_version"}
    manifest["producer"] = {"boundary_vocabulary_version": 6}
    assert observability_of(manifest).boundary_vocabulary_version == 6
    del manifest["producer"]
    assert observability_of(manifest).boundary_vocabulary_version == BOUNDARY_VOCABULARY_VERSION
    old = {k: v for k, v in manifest.items() if k != "catalogs_run"}
    assert observability_of(old).boundary_vocabulary_version == BOUNDARY_VOCABULARY_VERSION


def test_a_recorded_map_reads_back_as_the_map_it_was():
    out = observability_of(BASE).to_json()
    assert ObservabilityMap.from_json(out).to_json() == out


def test_the_metadata_is_not_mutated():
    before = copy.deepcopy(BASE)
    observability_of(BASE)

    assert BASE == before
