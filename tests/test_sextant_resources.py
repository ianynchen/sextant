"""`sextant.resources` (2N Task 5 fix round 1, MAJOR-2 — this module's own
docstring has the full delegation story): the ONE implementation, since 2N
Task 6 retired `sextant.cli.resources`, its delegating copy, and repointed
every importer here directly. `test_a_missing_extractor_says_how_to_build_it_via_package_root`
below is `tests/cli/test_resources.py`'s own whitebox pin, ported verbatim
(2N Task 6 carry (a)) — `cli.resources._package_root` no longer exists to
whitebox, so it now monkeypatches THIS module's own `_package_root`,
exercising the `root=None` default path the `tmp_path`-override test just
above does not."""

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
    """The `root` override — this module's own seam for a caller that wants
    a different package root, distinct from `_package_root` itself, which
    the test below whiteboxes directly."""
    with pytest.raises(resources.MissingResourceError) as raised:
        resources.extractor_jar(root=tmp_path)
    assert "gradlew build" in str(raised.value)


def test_a_missing_extractor_says_how_to_build_it_via_package_root(
    monkeypatch: pytest.MonkeyPatch,
):
    """Ported from `tests/cli/test_resources.py` (2N Task 6 carry (a),
    retired along with `cli.resources`): silence is the defect being fixed
    here — the old code resolved to a path that was simply not there, and
    the run continued. A clone that has not built the extractor is an
    ordinary state, so the error carries the remedy. Unlike the `root=`
    override test above, this exercises the `root=None` default — the path
    every real caller (`cli.resources` while it existed, `sextant.api`
    today) actually takes."""
    monkeypatch.setattr(resources, "_package_root", lambda: Path("/nonexistent/package"))

    with pytest.raises(resources.MissingResourceError) as raised:
        resources.extractor_jar()

    assert "gradlew build" in str(raised.value)


def test_a_missing_catalogs_dir_says_so(tmp_path: Path):
    with pytest.raises(resources.MissingResourceError) as raised:
        resources.catalogs_dir(root=tmp_path)
    assert str(tmp_path / "catalogs") in str(raised.value)


def test_missing_instructions_say_so(tmp_path: Path):
    with pytest.raises(resources.MissingResourceError) as raised:
        resources.instructions_path(root=tmp_path)
    assert str(tmp_path / "enrich" / "INSTRUCTIONS.md") in str(raised.value)


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
