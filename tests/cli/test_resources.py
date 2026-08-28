import zipfile
from pathlib import Path

import pytest

from sextant.cli import resources
from sextant.cli.resources import MissingResourceError, catalogs_dir, extractor_jar

REPO = Path(__file__).parents[2]


def test_catalogs_resolve_inside_the_installed_package():
    """Not from this file's position on disk. `parents[3]` pointed above
    site-packages from a wheel, and a catalog directory that is merely absent
    globs to nothing — so a packaged Sextant reported no endpoints and no
    skipped catalogs, which is the failure the reporting exists to prevent."""
    directory = catalogs_dir()

    assert directory.is_dir()
    assert directory.parent.name == "sextant"
    assert {path.name for path in directory.glob("*.yml")} >= {"spring-web.yml"}


def test_extractor_jar_is_found_where_the_build_puts_it():
    assert extractor_jar().is_file()


def test_a_missing_extractor_says_how_to_build_it(monkeypatch: pytest.MonkeyPatch):
    """Silence is the defect being fixed here: the old code resolved to a path
    that was simply not there, and the run continued. A clone that has not built
    the extractor is an ordinary state, so the error carries the remedy."""
    monkeypatch.setattr(resources, "_package_root", lambda: Path("/nonexistent/package"))

    with pytest.raises(MissingResourceError) as raised:
        resources.extractor_jar()

    assert "gradlew build" in str(raised.value)


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
