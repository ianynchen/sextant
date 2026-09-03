"""`sextant.resources` (2N Task 5 fix round 1, MAJOR-2): the one real
implementation `sextant.cli.resources` now delegates to — direct tests
here, on top of `tests/cli/test_resources.py`'s own untouched whitebox pin
(`cli.resources._package_root`, still reached through the `root` parameter
this module's own docstring explains)."""

import zipfile
from pathlib import Path

import pytest

from sextant import resources

REPO = Path(__file__).parents[1]


def test_catalogs_resolve_inside_the_installed_package():
    directory = resources.catalogs_dir()

    assert directory.is_dir()
    assert directory.parent.name == "sextant"
    assert {path.name for path in directory.glob("*.yml")} >= {"spring-web.yml"}


def test_extractor_jar_is_found_where_the_build_puts_it():
    assert resources.extractor_jar().is_file()


def test_instructions_resolve_inside_the_installed_package():
    path = resources.instructions_path()

    assert path.is_file()
    assert path.parent.name == "enrich"
    assert path.parent.parent.name == "sextant"


def test_a_missing_extractor_says_how_to_build_it(tmp_path: Path):
    """The `root` override — not `_package_root`, which stays private to
    each caller (`cli.resources` keeps its own, whiteboxed by
    `tests/cli/test_resources.py`) — is this module's own seam for a
    caller that wants a different package root."""
    with pytest.raises(resources.MissingResourceError) as raised:
        resources.extractor_jar(root=tmp_path)
    assert "gradlew build" in str(raised.value)


def test_a_missing_catalogs_dir_says_so(tmp_path: Path):
    with pytest.raises(resources.MissingResourceError) as raised:
        resources.catalogs_dir(root=tmp_path)
    assert str(tmp_path / "catalogs") in str(raised.value)


def test_missing_instructions_say_so(tmp_path: Path):
    with pytest.raises(resources.MissingResourceError) as raised:
        resources.instructions_path(root=tmp_path)
    assert str(tmp_path / "enrich" / "INSTRUCTIONS.md") in str(raised.value)


def test_cli_resources_raises_the_same_missingresourceerror_class():
    """`cli.resources.MissingResourceError` is an IMPORT of this module's
    own class, never a second definition (MAJOR-2's own fix) — so
    `tests/cli/test_resources.py`'s `pytest.raises(MissingResourceError)`
    still catches what `sextant.resources` actually raises."""
    from sextant.cli.resources import MissingResourceError as CliMissingResourceError

    assert CliMissingResourceError is resources.MissingResourceError


def test_the_wheel_carries_the_catalogs_and_the_extractor():
    """The force-include in pyproject.toml is a claim about an artifact nobody
    looks inside. ARCHITECTURE §9 ships the extractor with the code because
    version drift between the two is a silent correctness fault, so the wheel
    is opened rather than trusted."""
    wheels = sorted((REPO / "dist").glob("sextant-*.whl"))
    if not wheels:
        pytest.skip("no wheel built; `pip wheel . --no-deps -w dist` to check packaging")

    names = zipfile.ZipFile(wheels[-1]).namelist()

    assert "sextant/catalogs/spring-web.yml" in names
    assert "sextant/extractor-jvm/sextant-extractor.jar" in names
    assert "sextant/enrich/INSTRUCTIONS.md" in names
