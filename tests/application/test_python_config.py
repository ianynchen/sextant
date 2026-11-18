"""The `.env` file a settings class names is a config source (plan 3 Task 4, N3; Review Focus 5).

Each test writes a small program, runs the real `analyze` stage over it (the Python scanner, the
shipped catalogs, the shipped readers) and reads `resolved_config`. The syntax rules are
python-dotenv's, measured in `scripts/probes/pydantic_settings_rules.md`.
"""

from pathlib import Path

import pytest

from fixture_python import FIXTURES
from sextant.application.ports.detector import LibraryRoot, ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.stages.analyze import analyze
from sextant.domain.factfile import read_fact_tree
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.ingress.read.registry import READERS
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_LOCKED = {"pydantic": "2.14.3", "pydantic-settings": "2.16.3"}
_SETTINGS = (
    "from pydantic_settings import BaseSettings, SettingsConfigDict\n"
    "class Settings(BaseSettings):\n"
    "    model_config = SettingsConfigDict(env_file={env_file})\n"
    "    port: int = 1\n"
)


class _Detector:
    def __init__(self, module: ModuleModel) -> None:
        self._module = module

    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(root=path, modules=(self._module,))


@pytest.fixture(scope="module")
def libraries(orders_fastapi_env: Path) -> tuple[LibraryRoot, ...]:
    (site,) = (FIXTURES / "orders-fastapi" / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _LOCKED.items())


def _analyzed(tmp_path: Path, libraries, files: dict[str, str], coordinates=("pydantic-settings",)):
    """The `resolved_config` rows (key, value, environment, source, reason) and the fact tree's
    config keys of a module whose files are `files`, relative to its root."""
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    src = tmp_path / "src"
    module = ModuleModel(
        module_id="shop",
        coordinates="shop",
        version="1",
        root=tmp_path,
        kind="service",
        languages=frozenset({"python"}),
        source_roots=(src,),
        output_dirs=(src,),
        dependency_coordinates=tuple(coordinates),
        dependency_archives=libraries,
        lookup="c3",
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        analyze(
            path=tmp_path,
            workspace=workspace,
            detectors=[_Detector(module)],
            scanners=[PythonScanner()],
            catalogs=YamlCatalogSource(catalogs_dir()),
            fact_root=tmp_path / "facts",
            progress=NullProgress(),
            readers=READERS,
        )
        rows = [
            (r["key"], r["value"], r["environment"], r["source"], r["unresolved_reason"])
            for r in workspace.query("resolved_config")
        ]
    finally:
        workspace.close()
    keys = {
        fact.key_path
        for _, _, facts in read_fact_tree(tmp_path / "facts")
        for fact in facts
        if fact.kind == "config_entry"
    }
    return sorted(rows, key=repr), keys


def _settings(env_file: str) -> str:
    return _SETTINGS.format(env_file=env_file)


def test_a_named_env_file_yields_resolved_config_rows(tmp_path: Path, libraries):
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {"src/app/settings.py": _settings('".env"'), ".env": "APP_PORT=8080\nNAME=orders\n"},
    )
    assert rows == [
        ("APP_PORT", "8080", "default", ".env", None),
        ("NAME", "orders", "default", ".env", None),
    ]


def test_a_plain_dict_config_names_the_file_too(tmp_path: Path, libraries):
    source = (
        "from pydantic_settings import BaseSettings\n"
        "class Settings(BaseSettings):\n"
        '    model_config = {"env_file": "conf/.env.prod"}\n'
    )
    rows, _ = _analyzed(
        tmp_path, libraries, {"src/app/settings.py": source, "conf/.env.prod": "A=1\n"}
    )
    assert rows == [("A", "1", "default", "conf/.env.prod", None)]


def test_a_tuple_of_files_layers_later_over_earlier(tmp_path: Path, libraries):
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings('(".env", ".env.local")'),
            ".env": "A=1\nB=1\n",
            ".env.local": "B=2\n",
        },
    )
    assert rows == [
        ("A", "1", "default", ".env", None),
        ("B", "2", "default", ".env.local", None),
    ]


def test_a_placeholder_in_the_file_is_filled_the_way_python_dotenv_fills_it(
    tmp_path: Path, libraries
):
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings('".env"'),
            ".env": "HOST=db\nURL=postgres://${HOST}/x\nOTHER=${MISSING:-fallback}\n",
        },
    )
    by_key = {key: (value, reason) for key, value, _, _, reason in rows}
    assert by_key["URL"] == ("postgres://db/x", None)
    assert by_key["OTHER"] == ("fallback", None)


def test_an_env_file_nothing_names_is_never_opened(tmp_path: Path, libraries):
    """The built-in ignore layer still hides every `.env` from the walk, and a settings class
    that names a DIFFERENT file does not reopen it: the other file's keys never appear."""
    rows, keys = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings('"conf/app.env"'),
            ".env": "UNNAMED_SECRET=x\n",
            ".env.local": "UNNAMED_LOCAL=x\n",
            "src/main/resources/.env": "UNNAMED_RESOURCE=x\n",
            "conf/app.env": "NAMED=1\n",
        },
    )
    assert keys == {"NAMED"} and [row[0] for row in rows] == ["NAMED"]


def test_no_settings_class_means_no_env_file_is_read(tmp_path: Path, libraries):
    rows, keys = _analyzed(
        tmp_path,
        libraries,
        {"src/app/main.py": "X = 1\n", ".env": "UNNAMED_SECRET=x\n"},
    )
    assert rows == [] and keys == set()


def test_a_file_named_through_a_variable_is_not_read(tmp_path: Path, libraries):
    """Review Focus 5: the name is a value the walk cannot be sure of, so no file is opened and
    no row is written. The call's own argument keeps the expression for the field that reads
    the file to name."""
    source = (
        "from pydantic_settings import BaseSettings, SettingsConfigDict\n"
        'ENV = ".env"\n'
        "class Settings(BaseSettings):\n"
        "    model_config = SettingsConfigDict(env_file=ENV)\n"
    )
    rows, keys = _analyzed(
        tmp_path, libraries, {"src/app/settings.py": source, ".env": "SECRET=x\n"}
    )
    assert rows == [] and keys == set()


def test_a_missing_named_file_is_silently_absent(tmp_path: Path, libraries):
    """pydantic-settings ignores a missing `env_file` (probe, "missing env_file")."""
    rows, _ = _analyzed(tmp_path, libraries, {"src/app/settings.py": _settings('".env"')})
    assert rows == []


def test_a_file_named_outside_the_module_is_not_read(tmp_path: Path, libraries):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.env").write_text("LEAK=1\n", encoding="utf-8")
    module = tmp_path / "module"
    module.mkdir()
    rows, keys = _analyzed(
        module, libraries, {"src/app/settings.py": _settings('"../outside/secret.env"')}
    )
    assert rows == [] and keys == set()


@pytest.mark.declines("pydantic-settings")
@pytest.mark.pins("pydantic-settings.env-file-is-read-from-the-model-config-field")
def test_a_call_outside_a_settings_field_names_nothing(tmp_path: Path, libraries):
    """Only the call written as the class's `model_config` names its file."""
    source = (
        "from pydantic_settings import SettingsConfigDict\n"
        'OTHER = SettingsConfigDict(env_file=".env")\n'
    )
    rows, keys = _analyzed(tmp_path, libraries, {"src/app/settings.py": source, ".env": "A=1\n"})
    assert rows == [] and keys == set()


@pytest.mark.declines("pydantic-settings")
@pytest.mark.pins("pydantic-settings.model-is-selected-by-the-modules-dependencies")
def test_a_module_without_the_settings_library_reads_no_env_file(tmp_path: Path, libraries):
    """The model comes from the catalogs the module's own dependencies select."""
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {"src/app/settings.py": _settings('".env"'), ".env": "A=1\n"},
        coordinates=("fastapi",),
    )
    assert rows == []


def test_a_named_file_the_repos_own_ignore_file_lists_is_not_read(tmp_path: Path, libraries):
    """The carve-out covers the built-in `.env` shapes and nothing else: what the user excluded
    stays excluded even when the code names it."""
    rows, keys = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings('"deploy/prod.env"'),
            "deploy/prod.env": "LEAK=1\n",
            ".sextantignore": "deploy/*.env\n",
        },
    )
    assert rows == [] and keys == set()


def test_a_named_file_under_another_built_in_pattern_is_not_read(tmp_path: Path, libraries):
    rows, keys = _analyzed(
        tmp_path,
        libraries,
        {"src/app/settings.py": _settings('"secrets/app.env"'), "secrets/app.env": "LEAK=1\n"},
    )
    assert rows == [] and keys == set()


def test_a_named_dot_env_under_the_user_layer_negation_is_still_read(tmp_path: Path, libraries):
    """The carve-out itself: a plain named `.env` is read although the built-in layer lists it."""
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings('".env"'),
            ".env": "A=1\n",
            ".sextantignore": "# nothing here names it\nbuild/\n",
        },
    )
    assert rows == [("A", "1", "default", ".env", None)]
