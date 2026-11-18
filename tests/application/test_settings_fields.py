"""A read of a pydantic-settings field is its configuration key (plan 3 Task 5, N2; rulings
R23-R26; Review Focus 4).

`settings.payments_url` on a class whose lookup order reaches the catalog's `settings_base`
is the expression `${PREFIX+NAME}`, its class-body default rendered after the model's
`default_separator` (`${ORDERS_PAYMENTS_URL:-https://payments.example}`). The name rules are
pydantic-settings' own, measured in `scripts/probes/pydantic_settings_rules.md`: an alias
replaces the name and takes no prefix (`env_prefix_target` default `variable`), names compare
case-insensitively unless `case_sensitive=True`. `resolved_peers` then answers per environment:
the named `.env`'s value, else the default, else `external`.

Each test writes a small program, runs the real `analyze` stage over it (scanner, catalogs,
readers) and reads the outbound rows and their per-environment answers."""

from pathlib import Path

import pytest
from test_python_config import _Detector
from test_python_outbound import _CLIENTS

from fixture_python import FIXTURES
from sextant.application.ports.detector import LibraryRoot, ModuleModel
from sextant.application.ports.progress import NullProgress
from sextant.application.resolve.config import scope_config_models
from sextant.application.resolve.resolved_peers import resolved_peers
from sextant.application.stages.analyze import analyze
from sextant.domain.symbols import bare_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.ingress.read.registry import READERS
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_LIBRARIES = {**_CLIENTS, "pydantic-settings": "2.16.3", "python-dotenv": "1.2.4"}


@pytest.fixture(scope="module")
def libraries(orders_fastapi_env: Path) -> tuple[LibraryRoot, ...]:
    (site,) = (FIXTURES / "orders-fastapi" / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _LIBRARIES.items())


def _settings(config: str, fields: str) -> str:
    return (
        "from pydantic import Field\n"
        "from pydantic_settings import BaseSettings, SettingsConfigDict\n"
        "class Settings(BaseSettings):\n"
        f"    model_config = SettingsConfigDict({config})\n"
        f"{fields}"
        "settings = Settings()\n"
    )


def _analyzed(tmp_path: Path, libraries, files: dict[str, str]):
    """Each outbound row (caller, peer, path, resolution) and each per-environment answer
    (caller, environment, resolved peer, resolved path, reason, detail) of the program."""
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
        dependency_coordinates=tuple(_LIBRARIES),
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

        def caller(row) -> str:
            return bare_descriptor(str(row["caller"])).split("(")[0]

        rows = sorted(
            (caller(r), r["peer"], r["path"], r["resolution"])
            for r in workspace.query("endpoints")
            if r["direction"] == "outbound"
        )
        catalogs = scope_config_models(workspace, YamlCatalogSource(catalogs_dir()).load())
        answers = sorted(
            (
                caller(r),
                r["environment"],
                r["resolved_peer"],
                r["resolved_path"],
                r["unresolved_reason"],
                r["unresolved_detail"],
            )
            for r in resolved_peers(workspace, catalogs)
        )
    finally:
        workspace.close()
    return rows, answers


_CLIENT = (
    "import httpx, requests\n"
    "from app.settings import settings\n"
    "payments = httpx.Client(base_url=settings.payments_url)\n"
    "def pay():\n"
    "    payments.post('/charges')\n"
    "def ledger():\n"
    "    requests.get(f'{settings.ledger_url}/entries')\n"
)
_FIELDS = (
    "    payments_url: str = 'https://payments.example'\n"
    "    ledger_url: str = Field(alias='LEDGER_URL')\n"
)


def test_a_settings_field_is_its_key_with_its_default(tmp_path: Path, libraries):
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings("env_prefix='orders_'", _FIELDS),
            "src/app/clients.py": _CLIENT,
        },
    )
    assert rows == [
        ("app/clients#ledger", None, "${LEDGER_URL}/entries", "resolved"),
        # A configuration base is carried, not joined (`against_client_base`): the join
        # depends on whether the deployed value ends in `/`.
        (
            "app/clients#pay",
            None,
            "${ORDERS_PAYMENTS_URL:-https://payments.example}/charges",
            "partial",
        ),
    ]


def test_resolved_peers_reads_the_named_file_then_the_default(tmp_path: Path, libraries):
    _, answers = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings("env_prefix='orders_', env_file='.env'", _FIELDS),
            "src/app/clients.py": _CLIENT,
            ".env": "LEDGER_URL=https://ledger.env\n",
        },
    )
    assert answers == [
        ("app/clients#ledger", "default", None, "https://ledger.env/entries", None, None),
        (
            "app/clients#pay",
            "default",
            None,
            "https://payments.example/charges",
            None,
            None,
        ),
    ]


def test_a_key_the_file_sets_wins_over_the_default(tmp_path: Path, libraries):
    _, answers = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings("env_prefix='orders_', env_file='.env'", _FIELDS),
            "src/app/clients.py": _CLIENT,
            ".env": "ORDERS_PAYMENTS_URL=https://payments.env\n",
        },
    )
    assert answers == [
        ("app/clients#ledger", "default", None, None, "external", "LEDGER_URL is not set"),
        ("app/clients#pay", "default", None, "https://payments.env/charges", None, None),
    ]


@pytest.mark.parametrize(
    ("config", "field", "expected"),
    [
        # Review Focus 4: the prefix and the name compare case-insensitively by default.
        ("env_prefix='Orders_'", "    payments_url: str\n", "${ORDERS_PAYMENTS_URL}"),
        # An alias replaces the name and takes no prefix (`env_prefix_target` "variable").
        ("env_prefix='orders_'", "    payments_url: str = Field(alias='Pay')\n", "${PAY}"),
        # `validation_alias` before `alias`.
        (
            "env_prefix='orders_'",
            "    payments_url: str = Field(alias='A', validation_alias='V')\n",
            "${V}",
        ),
        # `case_sensitive=True`: the exact spelling.
        (
            "env_prefix='Orders_', case_sensitive=True",
            "    payments_url: str\n",
            "${Orders_payments_url}",
        ),
        # A written `env_prefix_target`: "all" prefixes the alias too, "alias" only the alias.
        (
            "env_prefix='o_', env_prefix_target='all'",
            "    payments_url: str = Field(alias='Pay')\n",
            "${O_PAY}",
        ),
        (
            "env_prefix='o_', env_prefix_target='alias'",
            "    payments_url: str\n",
            "${PAYMENTS_URL}",
        ),
        # No prefix.
        ("", "    payments_url: str = 'https://p.example'\n", "${PAYMENTS_URL:-https://p.example}"),
    ],
)
def test_the_key_follows_pydantic_settings_own_name_rules(
    tmp_path: Path, libraries, config, field, expected
):
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": _settings(config, field),
            "src/app/clients.py": "import requests\n"
            "from app.settings import settings\n"
            "def pay():\n"
            "    requests.get(settings.payments_url)\n",
        },
    )
    assert rows == [("app/clients#pay", None, expected, "resolved")]


@pytest.mark.parametrize(
    "config",
    ["env_prefix=PREFIX", "env_prefix='o_', case_sensitive=FLAG", "env_prefix_target=TARGET"],
)
def test_a_name_rule_written_as_no_literal_leaves_the_key_unresolved(
    tmp_path: Path, libraries, config
):
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": "PREFIX = 'o_'\nFLAG = True\nTARGET = 'all'\n"
            + _settings(config, "    payments_url: str = 'https://p.example'\n"),
            "src/app/clients.py": "import requests\n"
            "from app.settings import settings\n"
            "def pay():\n"
            "    requests.get(settings.payments_url)\n",
        },
    )
    ((_, peer, path, resolution),) = rows
    assert resolution == "unresolved"
    assert "p.example" not in str(peer) + str(path)


def test_a_file_named_through_a_variable_leaves_the_key_external_naming_it(
    tmp_path: Path, libraries
):
    """R26: the default is not rendered (a file not read may set the key), and the per-environment
    answer names the expression the file is chosen by."""
    rows, answers = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/settings.py": "ENV_FILE = '.env'\n"
            + _settings("env_prefix='orders_', env_file=ENV_FILE", _FIELDS),
            "src/app/clients.py": _CLIENT,
            ".env": "ORDERS_PAYMENTS_URL=https://payments.env\n",
        },
    )
    assert ("app/clients#pay", None, "${ORDERS_PAYMENTS_URL}/charges", "partial") in rows
    ((_, environment, _, path, reason, detail),) = [a for a in answers if a[0] == "app/clients#pay"]
    assert (environment, path, reason) == ("default", None, "external")
    assert "ENV_FILE" in str(detail)


def test_a_plain_model_default_is_never_the_value(tmp_path: Path, libraries):
    """R23: a request-parsed model's class-body default is not what a call holds (the
    varies-per-call lie); only a settings field renders its default, as configuration."""
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/clients.py": "import requests\n"
            "from pydantic import BaseModel\n"
            "class Hook(BaseModel):\n"
            "    url: str = 'https://hook.example'\n"
            "def fire(hook: Hook):\n"
            "    requests.post(hook.url)\n",
        },
    )
    ((_, peer, path, resolution),) = rows
    assert resolution != "resolved"
    assert "hook.example" not in str(peer) + str(path)


def test_an_environment_read_renders_its_default(tmp_path: Path, libraries):
    """R25: an environment read's literal default renders after the same separator."""
    rows, _ = _analyzed(
        tmp_path,
        libraries,
        {
            "src/app/clients.py": "import os, requests\n"
            "def audit():\n"
            "    requests.get(f\"http://{os.environ.get('AUDIT_HOST', 'audit.local')}/a\")\n",
        },
    )
    assert rows == [("app/clients#audit", None, "http://${AUDIT_HOST:-audit.local}/a", "resolved")]
