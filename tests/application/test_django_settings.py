"""Django settings modules are the module's environments (ruling R3 of 2026-11-25, design note
approved 2026-11-25).

Each module that holds the root setting (`root_setting`, Django's `ROOT_URLCONF`) is a source
of configuration, and its module name is the environment: one `resolved_config` row per
setting name per settings module, the value read by the value walk, through `from .base
import *`. A read of `settings.X` on `django.conf.settings` is the configuration key `X`. A
test on a setting is a `property` condition, never decided, with each environment's value as
evidence, and the routes of a root exist where `ROOT_URLCONF` is that root.

Each test writes a small Django program and runs the real scanner and pipeline with the
shipped catalogs (`test_django_routes._resolved`).
"""

import json
from pathlib import Path

import pytest
import test_django_routes
from test_django_routes import _resolved

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.values import resolve_site, value_index
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir

libraries = test_django_routes.libraries
orders_django_env = test_django_routes.orders_django_env

_URLS = (
    "from django.urls import path\n\ndef v(request):\n    return None\n\n"
    "urlpatterns = [path('u/', v)]\n"
)


def _config(workspace) -> dict[tuple[str, str], tuple[object, object]]:
    """`resolved_config` as (environment, key) -> (value, reason)."""
    return {
        (str(row["environment"]), str(row["key"])): (row["value"], row["unresolved_reason"])
        for row in workspace.query("resolved_config")
    }


def test_each_module_holding_the_root_setting_is_an_environment(tmp_path: Path, libraries):
    """Two settings modules are two environments named by the module; a module with no root
    setting (`urls`, `helpers`) is none. Each name the module writes is a key: a literal is
    its text, an environment read its expression, with the default where one is written."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "import os\nROOT_URLCONF = 'app.urls'\nDEBUG = False\n"
            "HOST = os.environ.get('APP_HOST', 'localhost')\nLIMIT = 5\n",
            "settings_dev.py": "ROOT_URLCONF = 'app.urls'\nDEBUG = True\n",
            "helpers.py": "OTHER = 1\n",
            "urls.py": _URLS,
        },
    )

    config = _config(workspace)
    assert sorted({environment for environment, _ in config}) == [
        "app.settings",
        "app.settings_dev",
    ]
    assert config[("app.settings", "DEBUG")] == ("False", None)
    assert config[("app.settings", "LIMIT")] == ("5", None)
    assert config[("app.settings", "HOST")] == ("${APP_HOST:-localhost}", None)
    assert config[("app.settings", "ROOT_URLCONF")] == ("app.urls", None)
    assert config[("app.settings_dev", "DEBUG")] == ("True", None)
    # A key another environment sets and this one does not: `external`, as a profile's is.
    assert config[("app.settings_dev", "LIMIT")] == (None, "external")
    assert not [key for _, key in config if key in ("OTHER", "urlpatterns")]


def test_a_settings_module_holds_what_a_star_import_gives_it(tmp_path: Path, libraries):
    """`from app.settings import *`, then one name written again (weblate's `settings_test`; a file a test runner collects is not read):
    the module holds the root setting through the star, so it is an environment; its own
    write wins, every other name has the value of the module it comes from."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "ROOT_URLCONF = 'app.urls'\nDEBUG = False\nLIMIT = 5\n",
            "settings_ci.py": "from app.settings import *\nDEBUG = True\n",
            "urls.py": _URLS,
        },
    )

    config = _config(workspace)
    assert config[("app.settings_ci", "ROOT_URLCONF")] == ("app.urls", None)
    assert config[("app.settings_ci", "DEBUG")] == ("True", None)
    assert config[("app.settings_ci", "LIMIT")] == ("5", None)
    assert config[("app.settings", "DEBUG")] == ("False", None)


def test_a_setting_with_no_one_value_states_a_reason(tmp_path: Path, libraries):
    """A name written twice (one write under a test), a list, `None`, and a value a library
    call makes: no one value, so the row is unresolved with a reason, never a guess."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "import sys\nimport socket\nROOT_URLCONF = 'app.urls'\n"
            "MODE = 'a'\nif len(sys.argv) > 1:\n    MODE = 'b'\n"
            "APPS = ['one', 'two']\nNAME = socket.gethostname()\nNOTHING = None\n",
            "urls.py": _URLS,
        },
    )

    config = _config(workspace)
    assert config[("app.settings", "MODE")] == (None, "not_readable")
    assert config[("app.settings", "APPS")] == (None, "not_readable")
    assert config[("app.settings", "NAME")][0] is None
    assert config[("app.settings", "NAME")][1] is not None
    assert config[("app.settings", "NOTHING")] == (None, "not_readable")


def test_a_program_with_no_root_setting_has_no_environment(tmp_path: Path, libraries):
    """A reusable app writes no `ROOT_URLCONF`: no settings module, no row, `default`."""
    workspace = _resolved(
        tmp_path, libraries, {"conf.py": "DEBUG = True\n", "urls.py": _URLS}, None
    )

    assert _config(workspace) == {}


# -- a read of `settings.X` is the configuration key `X` ---------------------------------------


def _sunk(tmp_path: Path, libraries, files: dict[str, str]) -> list[list[tuple[object, ...]]]:
    """What each `sink(...)` call is handed, in the order written: the value walk's answers,
    `(kind, value, reason)`, read with the shipped value models."""
    workspace = _resolved(tmp_path, libraries, files)
    index = value_index(
        workspace,
        returns_arguments=YamlCatalogSource(catalogs_dir()).load()[0].returns_arguments,
    )
    sites = sorted(
        (row for row in workspace.query("call_sites") if row["name"] == "sink"),
        key=lambda row: row["ordinal"],
    )
    return [
        [
            (binding.slots[0].kind, binding.slots[0].value, binding.slots[0].reason)
            for binding in resolve_site(workspace, dict(row), index)
        ]
        for row in sites
    ]


def test_a_read_of_a_django_setting_is_its_key(tmp_path: Path, libraries):
    """`settings.API_HOST` on `django.conf.settings` is the configuration key `API_HOST`,
    the expression `${API_HOST}` (`key_reads` in `value-models/django.yml`; the role of
    `@Value("${k}")` and of a pydantic settings field): which settings module gives the
    value is the deployment's, so no module's literal is the answer. In a text it is a hole
    of that text. An attribute of another object is not a key."""
    sunk = _sunk(
        tmp_path,
        libraries,
        {
            "settings.py": "ROOT_URLCONF = 'app.urls'\nAPI_HOST = 'billing.internal'\n",
            "urls.py": _URLS,
            "client.py": "from django.conf import settings\nfrom app import other\n\n"
            "def sink(x):\n    return None\n\n"
            "def run():\n    sink(settings.API_HOST)\n"
            "    sink('https://' + settings.API_HOST + '/pay')\n    sink(other.API_HOST)\n",
            "other.py": "API_HOST = 'plain'\n",
        },
    )

    assert sunk == [
        [("expression", "${API_HOST}", None)],
        [("expression", "https://${API_HOST}/pay", None)],
        [("literal", "plain", None)],
    ]


def test_the_shipped_key_read_is_djangos_settings_object():
    found = [
        (entry["owner"], entry["form"]) for entry in YamlCatalogSource(catalogs_dir()).key_reads()
    ]
    assert found == [("django/conf/settings#", "key_read")]


@pytest.mark.parametrize(
    "entries",
    [
        "{ owner: a.b }",  # no probe
        "{ owner: a.b, method: get, by: x.md }",  # unknown key
        "{ by: x.md }",  # no owner
        "{ owner: a.b, by: x.md }\n  - { owner: a.b, by: x.md }",  # stated twice
    ],
)
def test_a_malformed_key_read_is_refused(tmp_path: Path, entries):
    (tmp_path / "value-models").mkdir()
    (tmp_path / "value-models" / "invented.yml").write_text(
        f"id: invented\nkey_reads:\n  - {entries}\n", encoding="utf-8"
    )
    with pytest.raises(CatalogError, match="key_reads"):
        YamlCatalogSource(tmp_path).key_reads()


# -- conditions: a test on a setting, and the root ---------------------------------------------


def _existence(workspace) -> list[tuple[object, ...]]:
    """`endpoint_existence` as (path, kind, test, keys, environment, holds, evidence)."""
    live = {row["row_id"]: row["path"] for row in workspace.query("endpoints")}
    found = []
    for row in workspace.query("endpoint_existence"):
        expression = json.loads(str(row["expression"]))
        found.append(
            (
                live[row["row_id"]],
                row["kind"],
                expression["test"],
                tuple(expression.get("keys", ())),
                row["environment"],
                row["holds"],
                row["evidence"],
            )
        )
    return sorted(found)


_SET = "` is set by the deployment; this module's `"


def test_a_test_on_a_setting_is_a_property_condition_never_decided(tmp_path: Path, libraries):
    """`if settings.DEBUG: urlpatterns += [...]` with `DEBUG` written `False` in one settings
    module and `True` in another: the route exists (it is never removed, and never copied
    per environment), its condition is kind `property` on the key `DEBUG`, "not evaluated"
    in every environment (the deployment sets a key, ruled 2026-10-23, as a Java
    `@ConditionalOnProperty` is), and each environment's value is the evidence."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "ROOT_URLCONF = 'app.urls'\nDEBUG = False\n",
            "settings_dev.py": "from app.settings import *\nDEBUG = True\n",
            "urls.py": "from django.conf import settings\n" + _URLS + "if settings.DEBUG:\n"
            "    urlpatterns += [path('d/', v)]\n",
        },
    )

    assert sorted(row["path"] for row in workspace.query("endpoints")) == ["/d/", "/u/"]
    debug = [row for row in _existence(workspace) if row[2] == "settings.DEBUG"]
    assert debug == [
        ("/d/", "property", "settings.DEBUG", ("DEBUG",), "app.settings", "unresolved",
         f"`DEBUG{_SET}app.settings` configuration sets `False`"),
        ("/d/", "property", "settings.DEBUG", ("DEBUG",), "app.settings_dev", "unresolved",
         f"`DEBUG{_SET}app.settings_dev` configuration sets `True`"),
    ]  # fmt: skip


def test_the_routes_of_a_root_exist_where_the_root_setting_names_it(tmp_path: Path, libraries):
    """Two settings modules name two roots: each root's routes carry the condition
    "`ROOT_URLCONF` is `<root>`", kind `property`, "not evaluated" in every environment, with
    what each environment sets as evidence. No row is removed and none is copied."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "ROOT_URLCONF = 'app.urls'\n",
            "settings_admin.py": "ROOT_URLCONF = 'app.admin_urls'\n",
            "urls.py": _URLS,
            "admin_urls.py": _URLS.replace("'u/'", "'a/'"),
        },
    )

    assert sorted(row["path"] for row in workspace.query("endpoints")) == ["/a/", "/u/"]
    assert _existence(workspace) == [
        ("/a/", "property", "ROOT_URLCONF == 'app.admin_urls'", ("ROOT_URLCONF",), "app.settings",
         "unresolved", f"`ROOT_URLCONF{_SET}app.settings` configuration sets `app.urls`"),
        ("/a/", "property", "ROOT_URLCONF == 'app.admin_urls'", ("ROOT_URLCONF",),
         "app.settings_admin", "unresolved",
         f"`ROOT_URLCONF{_SET}app.settings_admin` configuration sets `app.admin_urls`"),
        ("/u/", "property", "ROOT_URLCONF == 'app.urls'", ("ROOT_URLCONF",), "app.settings",
         "unresolved", f"`ROOT_URLCONF{_SET}app.settings` configuration sets `app.urls`"),
        ("/u/", "property", "ROOT_URLCONF == 'app.urls'", ("ROOT_URLCONF",), "app.settings_admin",
         "unresolved",
         f"`ROOT_URLCONF{_SET}app.settings_admin` configuration sets `app.admin_urls`"),
    ]  # fmt: skip
    expression = json.loads(str(workspace.query("endpoint_existence")[0]["expression"]))
    assert expression["having_value"] in ("app.urls", "app.admin_urls")


def test_two_settings_modules_naming_one_root_give_one_condition(tmp_path: Path, libraries):
    """`ROOT_URLCONF = 'app.urls'` in two settings modules is one condition of the root's
    routes, not the same words twice."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "ROOT_URLCONF = 'app.urls'\n",
            "settings_dev.py": "ROOT_URLCONF = 'app.urls'\n",
            "urls.py": _URLS,
        },
    )

    assert {int(str(row["route"])) for row in workspace.query("endpoint_existence")} == {0}
    assert len(workspace.query("endpoint_existence")) == 2
