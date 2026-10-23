"""Every catalog that detects a Spring artifact names the Spring bean model (spec
2026-10-22 conditional-beans §2a, D02 §1c).

The condition vocabulary, the stereotype set and the configuration annotation are the
CONTAINER's knowledge, read by one resolve pass for every bean (`bean-models/spring.yml`). A
catalog reaches that model only by naming it — `bean_model: spring` — so a Spring catalog
that forgets the line is silently outside the pass: a `@Profile` controller its rows come
from reads as always served, and nothing fails. Naming the model on a catalog that resolves
no `bean_via` capture changes nothing it derives (`bean_table` is built only where a
capture spells one), which is why the rule can be uniform instead of a list someone curates.

Loaded through `YamlCatalogSource`, so the comparison is on what the loader hands the engine.
"""

from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir

_SPRING_GROUP = "org.springframework"


def _spring_catalogs_without_the_model(catalogs: list[Catalog]) -> list[str]:
    """The ids of catalogs whose `detect.coordinates` name an `org.springframework` group
    (the group itself or one below it) and whose `bean_model` is not Spring's."""
    return sorted(
        catalog.id
        for catalog in catalogs
        if any(
            group == _SPRING_GROUP or group.startswith(_SPRING_GROUP + ".")
            for group in (coordinate.split(":", 1)[0] for coordinate in catalog.detect_coordinates)
        )
        and catalog.bean_model.get("id") != "spring"
    )


def test_every_catalog_detecting_a_spring_artifact_names_the_spring_bean_model():
    catalogs = YamlCatalogSource(catalogs_dir()).load()
    assert _spring_catalogs_without_the_model(catalogs) == [], (
        "catalogs detecting an `org.springframework` coordinate must name `bean_model: spring` "
        "(D02 §1c) — without it the condition vocabulary never reaches them"
    )


def test_the_check_flags_a_spring_catalog_that_does_not_name_the_model(tmp_path: Path):
    """The rule above is only worth having if it can fail: a catalog naming a Spring
    coordinate and no model is reported, one naming it, or no Spring coordinate, is not."""
    (tmp_path / "bean-models").mkdir()
    (tmp_path / "bean-models" / "spring.yml").write_text("id: spring\n", encoding="utf-8")
    header = "style: annotation_driven\nprotocol: http\ndirection: inbound\nmatches: {}\n"
    for name, body in {
        "forgot": "detect: {coordinates: ['org.springframework.kafka:spring-kafka']}\n",
        "named": "detect: {coordinates: ['org.springframework:spring-web']}\nbean_model: spring\n",
        "elsewhere": "detect: {coordinates: ['io.vertx:vertx-core']}\n",
    }.items():
        (tmp_path / f"{name}.yml").write_text(f"id: {name}\n{header}{body}", encoding="utf-8")

    assert _spring_catalogs_without_the_model(YamlCatalogSource(tmp_path).load()) == ["forgot"]
