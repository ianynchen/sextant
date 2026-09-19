"""A catalog standing aside for another names EXACTLY that catalog's coordinates
(B/C Task 10 fix round 1, final review of Groups B and C).

`jakarta-jaxrs.yml` and `javax-jaxrs.yml` read the same `ws.rs` annotations Quarkus REST
implements with, so on a module declaring Quarkus REST they declare `detect.superseded_by`
and are skipped rather than run and win `insert_endpoints.sql`'s filename tie-break with the
wrong body rule (`docs/RUNBOOK.md`, "Two catalogs reading the same annotations dedupe only
where their rules agree"). The list each declares is a COPY of `quarkus-rest.yml`'s own
`detect.coordinates` — fourteen coordinates, three files — and a copy drifts: a facet added
to `quarkus-rest.yml` alone would leave the plain catalog running on a module declaring
only that facet, which is the exact race `superseded_by` exists to lose on purpose.

Loaded through `YamlCatalogSource`, not read as text, so the comparison is on what the
loader hands the engine.
"""

from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir

# The catalog whose coordinates the others mirror, and the catalogs that mirror it.
_IMPLEMENTATION = "quarkus-rest"
_SUPERSEDED = ("jakarta-jaxrs", "javax-jaxrs")


def test_the_jaxrs_catalogs_supersession_lists_are_quarkus_rests_own_coordinates():
    catalogs = {catalog.id: catalog for catalog in YamlCatalogSource(catalogs_dir()).load()}
    expected = set(catalogs[_IMPLEMENTATION].detect_coordinates)
    assert expected, f"{_IMPLEMENTATION} declares no detect.coordinates"
    for catalog_id in _SUPERSEDED:
        declared = set(catalogs[catalog_id].detect_superseded_by)
        assert declared == expected, (
            f"{catalog_id}'s detect.superseded_by drifted from {_IMPLEMENTATION}'s "
            f"detect.coordinates: missing {sorted(expected - declared)}, "
            f"extra {sorted(declared - expected)}"
        )
