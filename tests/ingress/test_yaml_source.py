"""`YamlCatalogSource` and the bean models (D02 §1c): a catalog names one with
`bean_model: <id>` and the loader hands the model's mapping through as
`Catalog.bean_model`, exactly as a `shape_model` is resolved (D02 §1b) — and
refuses an id no file in `bean-models/` carries, naming the catalog file. The
shape-model half of the same mechanism is pinned in
`tests/application/test_endpoints.py`.
"""

from pathlib import Path

import pytest

from sextant.application.ports.catalogs import CatalogError
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

_HEADER = "id: invented\nstyle: annotation_driven\nprotocol: http\ndirection: inbound\n"
_TINY = (
    "id: tiny\ndeclaring_annotation: com.acme.di.Provides\nname_attrs: [named]\n"
    "qualifier_annotation: com.acme.di.Named\nchannel_types: [com.acme.di.Pipe]\n"
)


def _write_model(directory: Path) -> None:
    (directory / "bean-models").mkdir()
    (directory / "bean-models" / "tiny.yml").write_text(_TINY, encoding="utf-8")


def test_a_catalog_takes_the_bean_model_it_names(tmp_path: Path):
    """The mapping reaches `Catalog.bean_model` whole: the fold that reads it
    (`resolve/beans.py`) is the one place the keys are interpreted, so the
    loader carries them as data rather than learning their meaning."""
    _write_model(tmp_path)
    (tmp_path / "invented-di.yml").write_text(
        _HEADER + "bean_model: tiny\nmatches: {}\n", encoding="utf-8"
    )

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.bean_model == {
        "id": "tiny",
        "declaring_annotation": "com.acme.di.Provides",
        "name_attrs": ["named"],
        "qualifier_annotation": "com.acme.di.Named",
        "channel_types": ["com.acme.di.Pipe"],
    }


def test_a_catalog_naming_a_bean_model_that_does_not_ship_is_refused_by_file(tmp_path: Path):
    """A typo would silently leave the catalog with no DI vocabulary at all —
    every `bean_via` capture unresolved, and nothing to say why. Refused at the
    edge, naming the file and the key, as an unknown `shape_model` is."""
    _write_model(tmp_path)
    (tmp_path / "invented-typo.yml").write_text(
        _HEADER + "bean_model: sprng\nmatches: {}\n", encoding="utf-8"
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "bean_model" in str(raised.value)
    assert "invented-typo.yml" in str(raised.value)
    assert "tiny" in str(raised.value)


def test_a_catalog_naming_no_bean_model_carries_an_empty_one(tmp_path: Path):
    """Every catalog shipped before this key, and a repository's own set with no
    `bean-models/` directory at all (D02 §6): absence is an empty mapping, not
    an error, and no directory is needed to load."""
    (tmp_path / "invented-bare.yml").write_text(_HEADER + "matches: {}\n", encoding="utf-8")

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.bean_model == {}
