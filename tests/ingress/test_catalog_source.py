"""`YamlCatalogSource` reads the catalogs through libyaml where the interpreter
has it (docs/performance.md C: the pure loader cost 0.18s on every analyze,
whichever module was analysed — 16% of an `orders-service` run).

The compiled and the pure loader implement the same YAML subset but are
known to disagree on a few YAML 1.1 corners (implicit-resolver edge cases,
some flow-collection spellings). The proof that switching changes nothing is
therefore not an argument about YAML; it is every shipped file read with BOTH
loaders and the Python objects compared equal. A catalog that ever hits a
corner they disagree on fails here, naming the file."""

from pathlib import Path

import pytest
import yaml

from sextant.ingress.catalogs import yaml_source
from sextant.resources import catalogs_dir

CATALOGS = catalogs_dir()
# The models beside the catalogs are read by the same loader (`_models`), so the
# two-loader proof covers them too.
SHIPPED = sorted(CATALOGS.glob("*.yml")) + [
    path
    for subdirectory in ("shape-models", "bean-models", "step-models", "value-models")
    for path in sorted((CATALOGS / subdirectory).glob("*.yml"))
]


def test_the_compiled_loader_is_present_and_is_the_one_in_use():
    """Without libyaml the source still loads — through the pure loader — but
    silently at the old cost, so its absence is worth a red test rather than
    a skip: PyYAML's published wheels bundle it (every 6.0.x manylinux and
    macOS wheel), so a runner without it installed something else."""
    assert hasattr(yaml, "CSafeLoader"), "PyYAML was built without libyaml"
    assert yaml_source._SAFE_LOADER is yaml.CSafeLoader


@pytest.mark.parametrize("path", SHIPPED, ids=lambda path: path.name)
def test_the_two_safe_loaders_read_every_shipped_catalog_identically(path: Path):
    text = path.read_text(encoding="utf-8")
    pure = yaml.load(text, Loader=yaml.SafeLoader)
    compiled = yaml.load(text, Loader=yaml.CSafeLoader)
    assert compiled == pure, f"{path.name}: the two loaders disagree"
    # Equal by value is not enough on its own: a bool read as a str compares
    # unequal, but an int read as a float compares EQUAL and would still change
    # a bound parameter's type. Compare the scalar types too, structurally.
    assert _typed(compiled) == _typed(pure), f"{path.name}: same values, different types"


def test_every_shipped_file_is_covered():
    assert len(SHIPPED) >= 80, "the catalog set shrank — or this test is looking in the wrong place"


def _typed(value: object) -> object:
    """The value with every scalar replaced by (type name, value), so two
    documents equal by value but different in a scalar's type compare
    unequal."""
    if isinstance(value, dict):
        return {(type(key).__name__, key): _typed(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_typed(item) for item in value]
    return (type(value).__name__, value)
