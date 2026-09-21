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


# --- step models (spec 2026-09-21 §5, §6) -----------------------------------------------
#
# The flow definition's members are the core library's, shared by every broker catalog
# that walks a flow; a catalog names the table with `step_model: <id>` and the loader
# merges the model's `steps` and `undeclared_steps` into `matches` — the union with the
# catalog's own steps, because a broker catalog also declares the steps on its own specs.

_STEPS = (
    "id: flows\n"
    "steps:\n"
    "  - { method: transform, owner: com.acme.Flow, captures: {} }\n"
    "  - { method: handle, owner: com.acme.Flow, descriptor: '(Lcom/acme/H;)V', captures: { handler: arg0 } }\n"
    "undeclared_steps: { owner: com.acme.Flow, poisons: [handler] }\n"
)


def _write_step_model(directory: Path) -> None:
    (directory / "step-models").mkdir()
    (directory / "step-models" / "flows.yml").write_text(_STEPS, encoding="utf-8")


def test_a_catalog_takes_the_step_models_steps_beside_its_own(tmp_path: Path):
    """The union, in one `matches.steps` list — the model's after the catalog's — and the
    model's `undeclared_steps` block, so the engine reads one table and learns nothing
    about where each entry came from."""
    _write_step_model(tmp_path)
    (tmp_path / "invented-flows.yml").write_text(
        _HEADER + "step_model: flows\nmatches:\n  steps:\n"
        "    - { method: topic, owner: com.acme.Sink, captures: { channel: arg0 } }\n",
        encoding="utf-8",
    )

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.matches == {
        "steps": [
            {"method": "topic", "owner": "com.acme.Sink", "captures": {"channel": "arg0"}},
            {"method": "transform", "owner": "com.acme.Flow", "captures": {}},
            {
                "method": "handle",
                "owner": "com.acme.Flow",
                "descriptor": "(Lcom/acme/H;)V",
                "captures": {"handler": "arg0"},
            },
        ],
        "undeclared_steps": {"owner": "com.acme.Flow", "poisons": ["handler"]},
    }


def test_a_catalog_naming_a_step_model_that_does_not_ship_is_refused_by_file(tmp_path: Path):
    _write_step_model(tmp_path)
    (tmp_path / "invented-typo.yml").write_text(
        _HEADER + "step_model: flow\nmatches: {}\n", encoding="utf-8"
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "step_model" in str(raised.value)
    assert "invented-typo.yml" in str(raised.value)
    assert "flows" in str(raised.value)


def test_a_step_the_catalog_and_its_model_both_declare_is_refused(tmp_path: Path):
    """One `(owner, method, descriptor)` from both sides is two entries for one overload
    — the silent last-wins the engine's own step check refuses, caught here by file
    before the union hides which side wrote it."""
    _write_step_model(tmp_path)
    (tmp_path / "invented-twice.yml").write_text(
        _HEADER + "step_model: flows\nmatches:\n  steps:\n"
        "    - { method: transform, owner: com.acme.Flow, captures: {} }\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "invented-twice.yml" in str(raised.value)
    assert "transform" in str(raised.value)


def test_a_catalog_may_not_declare_undeclared_steps_beside_a_model_that_does(tmp_path: Path):
    """`undeclared_steps` is one block, not a list: a catalog takes the model's or writes
    its own, never both — the `shape_model` rule for the same reason."""
    _write_step_model(tmp_path)
    (tmp_path / "invented-both.yml").write_text(
        _HEADER + "step_model: flows\nmatches:\n"
        "  undeclared_steps: { owner: com.acme.Other, poisons: [handler] }\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert "undeclared_steps" in str(raised.value)
    assert "invented-both.yml" in str(raised.value)


def test_a_catalog_naming_no_step_model_keeps_its_matches_as_written(tmp_path: Path):
    (tmp_path / "invented-bare.yml").write_text(
        _HEADER + "matches: { steps: [] }\n", encoding="utf-8"
    )

    [catalog] = YamlCatalogSource(tmp_path).load()

    assert catalog.matches == {"steps": []}
