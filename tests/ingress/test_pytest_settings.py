"""The reader of the test tool's settings file (ruled 2026-11-26): pytest's, claimed by name,
so the resolve can tell the settings module only the tests select."""

from pathlib import Path

from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.domain.resource_files import TEST_TOOL_SETTINGS
from sextant.ingress.read.pytest_settings import PytestSettingsReader
from sextant.ingress.read.registry import READERS


def _read(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, dict[str, str]]]:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    offered = tuple(tmp_path / name for name in TEST_TOOL_SETTINGS if name in files)
    return [
        (document.relative_path, {fact.key_path: fact.value for fact in facts})
        for document, facts in PytestSettingsReader().read(
            ReadRequest(module_id="shop", version="1", files=offered, root=tmp_path)
        )
        if document.language == "pytest"
    ]


def test_the_reader_claims_the_names_pytest_looks_for_and_no_extension():
    reader = PytestSettingsReader()
    assert all(reader.accepts(name) for name in TEST_TOOL_SETTINGS)
    assert not reader.accepts("ini") and not reader.accepts("toml") and not reader.accepts("cfg")
    walked = [Path("a/pytest.ini"), Path("a/pyproject.toml"), Path("a/x.yml")]
    assert not [
        owned
        for reader, owned in group_files_by_reader(walked, READERS)
        if isinstance(reader, PytestSettingsReader)
    ]


def test_an_ini_setting_keeps_its_case_as_pytest_reads_it(tmp_path: Path):
    text = "[pytest]\nDJANGO_SETTINGS_MODULE = app.settings_test\naddopts = -q\n"
    assert _read(tmp_path, {"pytest.ini": text}) == [
        ("pytest.ini", {"DJANGO_SETTINGS_MODULE": "app.settings_test", "addopts": "-q"})
    ]


def test_the_first_file_that_holds_pytest_settings_is_the_one_read(tmp_path: Path):
    """pytest's own choice: a `pyproject.toml` with no pytest table is passed over, and a
    setting that is no one text (a list) is no entry."""
    files = {
        "pyproject.toml": "[tool.other]\nx = 1\n",
        "setup.cfg": "[tool:pytest]\nDJANGO_SETTINGS_MODULE = app.ci\n",
    }
    assert _read(tmp_path, files) == [("setup.cfg", {"DJANGO_SETTINGS_MODULE": "app.ci"})]
    table = '[tool.pytest.ini_options]\nDJANGO_SETTINGS_MODULE = "app.t"\ntestpaths = ["t"]\n'
    assert _read(tmp_path, {"pyproject.toml": table}) == [
        ("pyproject.toml", {"DJANGO_SETTINGS_MODULE": "app.t"})
    ]


def test_no_pytest_settings_gives_no_document(tmp_path: Path):
    assert _read(tmp_path, {"pyproject.toml": "[project]\nname = 'x'\n"}) == []
