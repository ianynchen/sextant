"""Test code by pytest's own collection rules (`pytest_collection.py`; plan 2, final review M1).

Each case is one of `scripts/probes/pytest_collection.py`'s projects: the settings file pytest
9.2.0 chose there, and the `testpaths` and `python_files` it read, decide the test code here.
Beyond what pytest collects, every file below a `testpaths` entry or a `tests`/`test` folder is
test code (the user's ruling of 2026-11-09), so a helper beside the tests is too."""

from pathlib import Path

import pytest

from sextant.ingress.extract.python.pytest_collection import PytestCollection

_FILES = (
    "app/main.py",
    "app/test_inline.py",
    "app/inline_test.py",
    "app/check_names.py",
    "app/sub/conftest.py",
    "tests/helpers.py",
    "tests/test_api.py",
    "tests/conftest.py",
    "test/test_old.py",
    "spec/test_spec.py",
    "spec/deep/check_deep.py",
)
# Test code under every rule set: `conftest.py` and the `tests`/`test` folders.
_ALWAYS = {
    "app/sub/conftest.py",
    "tests/helpers.py",
    "tests/test_api.py",
    "tests/conftest.py",
    "test/test_old.py",
}


def _test_code(project: Path, top: Path | None = None) -> set[str]:
    for relative in _FILES:
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    rules = PytestCollection.of(project, top or project)
    return {relative for relative in _FILES if rules.holds(project / relative)}


def _write(project: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_no_settings_takes_the_default_patterns(tmp_path: Path):
    assert _test_code(tmp_path) == _ALWAYS | {
        "app/test_inline.py",
        "app/inline_test.py",
        "spec/test_spec.py",
    }


def test_pyproject_testpaths_and_python_files(tmp_path: Path):
    """`python_files` replaces the default patterns; every file below `testpaths` is test
    code."""
    _write(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "p"\n\n[tool.pytest.ini_options]\n'
            'testpaths = ["spec"]\npython_files = "check_*.py"\n'
        },
    )

    assert _test_code(tmp_path) == _ALWAYS | {
        "app/check_names.py",
        "spec/test_spec.py",
        "spec/deep/check_deep.py",
    }


def test_pyproject_native_toml_table(tmp_path: Path):
    _write(
        tmp_path,
        {"pyproject.toml": '[project]\nname = "p"\n\n[tool.pytest]\ntestpaths = ["spec"]\n'},
    )

    assert "spec/deep/check_deep.py" in _test_code(tmp_path)


def test_a_pyproject_with_no_pytest_table_is_passed_over_for_one_above(tmp_path: Path):
    """pytest goes on up past a `pyproject.toml` that holds no pytest settings."""
    _write(
        tmp_path,
        {
            "project/pyproject.toml": '[project]\nname = "p"\n',
            "pytest.ini": "[pytest]\ntestpaths = project/spec\n",
        },
    )

    assert "spec/deep/check_deep.py" in _test_code(tmp_path / "project", tmp_path)


def test_the_search_stops_at_the_analysed_root(tmp_path: Path):
    _write(tmp_path, {"pytest.ini": "[pytest]\ntestpaths = project/spec\n"})

    assert "spec/deep/check_deep.py" not in _test_code(tmp_path / "project")


def test_pytest_ini_comes_before_pyproject(tmp_path: Path):
    _write(
        tmp_path,
        {
            "pytest.ini": "[pytest]\npython_files = check_*.py\n",
            "pyproject.toml": '[tool.pytest.ini_options]\npython_files = "*_test.py"\n',
        },
    )

    assert _test_code(tmp_path) == _ALWAYS | {"app/check_names.py", "spec/deep/check_deep.py"}


def test_a_pytest_ini_with_no_section_is_still_the_settings_file(tmp_path: Path):
    """An empty `pytest.ini` is chosen, so a `setup.cfg` beside it is not read."""
    _write(
        tmp_path,
        {"pytest.ini": "[other]\nx = 1\n", "setup.cfg": "[tool:pytest]\npython_files = check_*\n"},
    )

    assert _test_code(tmp_path) == _ALWAYS | {
        "app/test_inline.py",
        "app/inline_test.py",
        "spec/test_spec.py",
    }


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("tox.ini", "[tox]\n\n[pytest]\ntestpaths = tests spec\n"),
        ("setup.cfg", "[metadata]\nname = p\n\n[tool:pytest]\ntestpaths =\n    tests\n    spec\n"),
    ],
)
def test_tox_ini_and_setup_cfg_sections(tmp_path: Path, name: str, text: str):
    _write(tmp_path, {name: text})

    assert "spec/deep/check_deep.py" in _test_code(tmp_path)


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("tox.ini", "[tox]\nenvlist = py\n"),
        ("setup.cfg", "[metadata]\nname = p\n"),
        ("pyproject.toml", "not toml ["),
    ],
)
def test_a_file_without_pytest_settings_gives_the_defaults(tmp_path: Path, name: str, text: str):
    _write(tmp_path, {name: text})

    assert "app/test_inline.py" in _test_code(tmp_path)


def test_testpaths_are_globs(tmp_path: Path):
    _write(tmp_path, {"pytest.ini": "[pytest]\ntestpaths = sp*\n"})

    assert "spec/deep/check_deep.py" in _test_code(tmp_path)


def test_a_python_files_pattern_with_a_separator_matches_the_whole_path(tmp_path: Path):
    _write(tmp_path, {"pytest.ini": "[pytest]\npython_files = spec/*/check_*.py test_*.py\n"})

    assert _test_code(tmp_path) == _ALWAYS | {
        "app/test_inline.py",
        "spec/test_spec.py",
        "spec/deep/check_deep.py",
    }
