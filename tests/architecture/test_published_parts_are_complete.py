"""Every part a fluent catalog's step can set is one `fluent` says it publishes, or one it says
it does not (review 3 re-review 2, m-3).

The several-splits rule counts only the calls on branches that set a part the reader's rows
publish (ruled by the user 2026-11-03, option A): `fluent.PUBLISHED_PARTS` is that set. A
capture a catalog adds later and nobody adds to the set would be a part no split counts, so a
row varying in it would stay `resolved` beside a combination no run makes. This test makes the
omission fail here instead: each capture a step sets — its `captures`, `collects` (as
`collected`), its `poisons` and the catalog's poisons for an undeclared member — is in
`PUBLISHED_PARTS` or in `fluent.UNPUBLISHED_PARTS`, whose entries each say why.

The options reader (`shapes/client_base.py`) counts its own splits by the parts ITS rows show
(`client_base.PUBLISHED_PARTS`, item 2 of the per-path-truth work): every part a client model's
setter declares must be one of them, or a split on that setter would not count.
"""

from pathlib import Path

from sextant.application.resolve.engines.fluent import PUBLISHED_PARTS, UNPUBLISHED_PARTS
from sextant.application.resolve.shapes import client_base
from sextant.application.resolve.shapes.chains import _declared_entries, _undeclared_steps
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

CATALOGS = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"


def _parts_set_by_steps() -> dict[str, set[str]]:
    """Each fluent catalog's id, with every part one of its steps can set."""
    found: dict[str, set[str]] = {}
    for catalog in YamlCatalogSource(CATALOGS).load():
        # A chain catalog carrying `dispatch_registrations` publishes no endpoint row: its
        # chain ends are registrations (spec 2026-11-05 §2), and its one part, `case`, is the
        # registration call the pass reads, never a column of a row `fluent` writes.
        if catalog.style != "fluent" or catalog.dispatch_registrations:
            continue
        _, _, steps = _declared_entries(catalog)
        parts: set[str] = set()
        for step in steps:
            parts.update(step["captures"])
            if step["collects"]:
                parts.add("collected")
            parts.update(step["poisons"] or ())
        parts.update(_undeclared_steps(catalog.matches, catalog)[1])
        found[catalog.id] = parts
    return found


def test_every_part_a_fluent_step_sets_is_published_or_named_unpublished():
    found = _parts_set_by_steps()
    assert found, "no fluent catalog was read"
    stray = {
        catalog_id: sorted(parts - PUBLISHED_PARTS - UNPUBLISHED_PARTS)
        for catalog_id, parts in found.items()
        if parts - PUBLISHED_PARTS - UNPUBLISHED_PARTS
    }
    assert stray == {}, (
        "a fluent step sets a part neither `fluent.PUBLISHED_PARTS` nor "
        f"`fluent.UNPUBLISHED_PARTS` names: {stray}"
    )


def test_the_two_sets_are_apart():
    assert PUBLISHED_PARTS & UNPUBLISHED_PARTS == frozenset()


def test_every_part_an_options_setter_sets_is_one_the_options_reader_publishes():
    setters = {
        (catalog.id, setter["method"], setter["part"])
        for catalog in YamlCatalogSource(CATALOGS).load()
        for setter in (catalog.matches.get("client_base") or {}).get("setters", ())
    }
    assert setters, "no options-object client model was read"
    stray = sorted(entry for entry in setters if entry[2] not in client_base.PUBLISHED_PARTS)
    assert stray == [], (
        f"an options setter sets a part `client_base.PUBLISHED_PARTS` omits: {stray}"
    )
