"""Django settings modules are the module's environments (ruling R3 of 2026-11-25, design note
approved 2026-11-25).

Each module that holds the root setting (`root_setting`, Django's `ROOT_URLCONF`) is a source
of configuration, and its module name is the environment: one `resolved_config` row per
setting name per settings module, the value read by the value walk, through `from .base
import *`. A read of `settings.X` on `django.conf.settings` is the configuration key `X`. A
test on a setting is a `property` condition with each environment's value as evidence,
decided in an environment whose settings module fixes the key, and the routes of a root exist
where `ROOT_URLCONF` is that root.

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


def test_only_an_upper_case_name_is_a_key(tmp_path: Path, libraries):
    """Django takes a name of a settings module as a setting only where it is upper case
    (`Settings.__init__`: `if setting.isupper()`), so a helper name the module holds is no
    key (ruled 2026-11-26; the source's `key_names: upper_case`). bookwyrm's
    `default_loaders` was a row before."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "ROOT_URLCONF = 'app.urls'\nloaders = 'x'\nMixed = 2\n"
            "_private = 3\nAPI_V2 = 'on'\n",
            "settings_dev.py": "ROOT_URLCONF = 'app.urls'\nextra = 1\n",
            "urls.py": _URLS,
        },
    )

    assert sorted({key for _, key in _config(workspace)}) == ["API_V2", "ROOT_URLCONF"]


def test_settings_only_the_tests_select_are_no_environment(tmp_path: Path, libraries):
    """The module the pytest settings name (`DJANGO_SETTINGS_MODULE`) that builds on another
    settings module is test settings (ruled 2026-11-26; weblate's `settings_test`, which
    takes `settings_example` with a star): no environment, and no builder, so the module it
    builds on stays one. A script that starts a process with it (weblate's
    `scripts/benchmark-search.py`) is test code too and keeps nothing."""
    files = {
        "settings.py": "ROOT_URLCONF = 'app.urls'\nDEBUG = False\n",
        "testing.py": "from app.settings import *\nDEBUG = True\n",
        "bench.py": _START.format("app.testing"),
        "urls.py": _URLS,
    }
    named = "[pytest]\nDJANGO_SETTINGS_MODULE = app.testing\n"
    workspace = _resolved(tmp_path / "a", libraries, files, pytest_ini=named)
    assert sorted({environment for environment, _ in _config(workspace)}) == ["app.settings"]

    # bookwyrm: the pytest settings name the module the deployment runs, which builds on
    # no other: it stays an environment.
    workspace = _resolved(
        tmp_path / "b",
        libraries,
        {**files, "manage.py": _START.format("app.settings")},
        pytest_ini="[pytest]\nDJANGO_SETTINGS_MODULE = app.settings\n",
    )
    assert sorted({environment for environment, _ in _config(workspace)}) == [
        "app.settings",
        "app.testing",
    ]


@pytest.mark.parametrize("owner", ["Env", "FileAwareEnv"])
def test_a_read_through_environs_is_the_key_expression(tmp_path: Path, libraries, owner):
    """`env.bool("DEBUG", False)` on an `environs` reader is a read of the key `DEBUG`
    (ruled 2026-11-26; `scripts/probes/environs_reads.md`), as `os.environ.get` is. bookwyrm
    writes its settings this way. `FileAwareEnv` also takes the value from the file
    `DEBUG_FILE` names: the key the deployment sets is still `DEBUG` (OI-578)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": f"from environs import {owner}\nenv = {owner}()\n"
            "ROOT_URLCONF = 'app.urls'\nDEBUG = env.bool('DEBUG', False)\n"
            "SECRET = env('SECRET_KEY')\nPORT = env.int('PORT', 5432)\n"
            "NAME = env.str(name='NAME', default='shop')\n",
            "urls.py": _URLS,
        },
    )

    config = _config(workspace)
    assert config[("app.settings", "DEBUG")] == ("${DEBUG:-False}", None)
    assert config[("app.settings", "SECRET")] == ("${SECRET_KEY}", None)
    assert config[("app.settings", "PORT")] == ("${PORT:-5432}", None)
    assert config[("app.settings", "NAME")] == ("${NAME:-shop}", None)


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


_START = "import os\nos.environ.setdefault('DJANGO_SETTINGS_MODULE', '{}')\n"


def test_a_settings_module_another_builds_on_is_no_environment(tmp_path: Path, libraries):
    """A settings module another settings module builds on is a building block and no
    environment, unless code starts a process with it (ruled 2026-11-26, D3; zulip's
    `computed_settings`, which `settings` takes with a star). The start is a read of the key
    the config model's `profiles.active_keys` names, with the module as its default
    (`os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")`)."""
    files = {
        "base.py": "ROOT_URLCONF = 'app.urls'\nDEBUG = False\n",
        "settings.py": "from app.base import *\nDEBUG = True\n",
        "worker.py": "from app.settings import *\nLIMIT = 5\n",
        "urls.py": _URLS,
    }
    workspace = _resolved(tmp_path / "a", libraries, files)
    assert sorted({environment for environment, _ in _config(workspace)}) == ["app.worker"]
    # The root is written in the building block: its name is still the key `ROOT_URLCONF`,
    # decided in the environment that builds on it (zulip's `computed_settings`).
    assert [row[1:6] for row in _existence(workspace)] == [
        ("property", "ROOT_URLCONF == 'app.urls'", ("ROOT_URLCONF",), "app.worker", "true")
    ]

    # bookwyrm: `celerywyrm.settings` builds on `bookwyrm.settings`, which `manage.py` starts.
    workspace = _resolved(
        tmp_path / "b", libraries, {**files, "manage.py": _START.format("app.settings")}
    )
    config = _config(workspace)
    assert sorted({environment for environment, _ in config}) == ["app.settings", "app.worker"]
    assert config[("app.settings", "LIMIT")] == (None, "external")


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
    assert config[("app.settings", "APPS[0]")] == ("one", None)
    assert config[("app.settings", "APPS[1]")] == ("two", None)
    assert ("app.settings", "APPS") not in config
    assert config[("app.settings", "NAME")][0] is None
    assert config[("app.settings", "NAME")][1] is not None
    assert config[("app.settings", "NOTHING")] == (None, "not_readable")


def test_a_list_setting_is_one_key_for_each_member(tmp_path: Path, libraries):
    """A setting written as a list is one key per member, `K[0]`, `K[1]`, the form a YAML
    list has (ruled 2026-11-25, Q4 part 2), a member that is a list `K[0][1]`. An addition
    to the list is a write of it, so its members are keys too. Where a member is not read,
    the read members are keys and `K` keeps one reason. A list with a member added under a
    test has no one membership: `K` keeps its reason and no member is a key."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "import os\nimport socket\nROOT_URLCONF = 'app.urls'\n"
            "APPS = ['one', 'two']\nAPPS += ['three']\n"
            "LANGUAGES = [('en', 'English'), ('de', 'German')]\n"
            "HOSTS = ['localhost', socket.gethostname()]\n"
            "EXTRA = ['one']\nif os.environ.get('X'):\n    EXTRA += ['two']\n",
            "settings_ci.py": "ROOT_URLCONF = 'app.urls'\nAPPS = ['one']\n",
            # bookwyrm's `celerywyrm.settings`: the list a star import gives, with one more.
            "settings_job.py": "from app.settings import *\nAPPS = APPS + ['job']\n",
            # As bookwyrm's `manage.py`: the module another builds on is started, so it stays.
            "manage.py": _START.format("app.settings"),
            "urls.py": _URLS,
        },
    )

    config = _config(workspace)
    assert config[("app.settings_job", "APPS")] == (None, "not_readable")
    assert ("app.settings_job", "APPS[0]") not in config
    held = {
        key: value for (environment, key), value in config.items() if environment == "app.settings"
    }
    assert {key: held[key] for key in held if key.startswith("APPS")} == {
        "APPS[0]": ("one", None),
        "APPS[1]": ("two", None),
        "APPS[2]": ("three", None),
    }
    assert {key: held[key] for key in held if key.startswith("LANGUAGES")} == {
        "LANGUAGES[0][0]": ("en", None),
        "LANGUAGES[0][1]": ("English", None),
        "LANGUAGES[1][0]": ("de", None),
        "LANGUAGES[1][1]": ("German", None),
    }
    assert held["HOSTS[0]"] == ("localhost", None)
    assert held["HOSTS"][0] is None and held["HOSTS"][1] is not None
    assert "HOSTS[1]" not in held
    assert held["EXTRA"] == (None, "not_readable")
    assert not [key for key in held if key.startswith("EXTRA[")]
    # The other settings module holds the name with one member: no "not set" row for it or
    # for a member it does not have; a name it does not hold at all is not set, as before.
    other = {
        key: value
        for (environment, key), value in config.items()
        if environment == "app.settings_ci"
    }
    assert {key for key in other if key.startswith("APPS")} == {"APPS[0]"}
    assert other["HOSTS"] == (None, "external")
    assert not [key for key in other if key.startswith(("HOSTS[", "LANGUAGES["))]


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


_DEBUG_URLS = (
    "from django.conf import settings\n" + _URLS + "if settings.DEBUG:\n"
    "    urlpatterns += [path('d/', v)]\n"
)


def _verdicts(workspace, test: str) -> dict[str, tuple[object, object]]:
    """Each environment's (holds, resolution) of the condition `test`."""
    return {
        str(row["environment"]): (row["holds"], row["resolution"])
        for row in workspace.query("endpoint_existence")
        if json.loads(str(row["expression"]))["test"] == test
    }


def test_a_test_on_a_setting_is_decided_per_environment(tmp_path: Path, libraries):
    """`if settings.DEBUG: urlpatterns += [...]` with `DEBUG` written `False` in one settings
    module and `True` in another (the approved note of R3, 2026-11-25): the condition is kind
    `property` on the key `DEBUG`, and it is decided in each environment on that settings
    module's one written value, as a Java `@Profile` condition is decided in its own
    environment: false in one, true in the other. The route exists once: it is never removed
    and never copied per environment. Each environment's value is the evidence."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "ROOT_URLCONF = 'app.urls'\nDEBUG = False\n",
            "settings_dev.py": "ROOT_URLCONF = 'app.urls'\nDEBUG = True\n",
            "urls.py": _DEBUG_URLS,
        },
    )

    assert sorted(row["path"] for row in workspace.query("endpoints")) == ["/d/", "/u/"]
    debug = [row for row in _existence(workspace) if row[2] == "settings.DEBUG"]
    assert debug == [
        ("/d/", "property", "settings.DEBUG", ("DEBUG",), "app.settings", "false",
         f"`DEBUG{_SET}app.settings` configuration sets `False`"),
        ("/d/", "property", "settings.DEBUG", ("DEBUG",), "app.settings_dev", "true",
         f"`DEBUG{_SET}app.settings_dev` configuration sets `True`"),
    ]  # fmt: skip
    assert _verdicts(workspace, "settings.DEBUG") == {
        "app.settings": ("false", "resolved"),
        "app.settings_dev": ("true", "resolved"),
    }


def test_a_test_on_a_setting_is_decided_in_the_forms_of_a_decided_test(tmp_path: Path, libraries):
    """The forms of ruling R2: `x`, `not x`, `x is None`, `x is not None`, by the language's
    truth of the written literal (the text `'False'` is true). Every other form (`==`) stays
    "not evaluated", though the environment's value is one literal."""
    tests = ["not settings.A", "settings.A is None", "settings.A is not None", "settings.T",
             "settings.A == False"]  # fmt: skip
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "ROOT_URLCONF = 'app.urls'\nA = False\nT = 'False'\n",
            "urls.py": "from django.conf import settings\n"
            + _URLS
            + "".join(
                f"if {test}:\n    urlpatterns += [path('p{n}/', v)]\n"
                for n, test in enumerate(tests)
            ),
        },
    )

    assert {test: _verdicts(workspace, test)["app.settings"] for test in tests} == {
        "not settings.A": ("true", "resolved"),
        "settings.A is None": ("false", "resolved"),
        "settings.A is not None": ("true", "resolved"),
        "settings.T": ("true", "resolved"),
        "settings.A == False": ("unresolved", "unresolved"),
    }
    assert len(workspace.query("endpoints")) == 6


_ABSENT = "try:\n    from .local_settings import *\nexcept ImportError:\n    pass\n"
_ROOT = "ROOT_URLCONF = 'app.urls'\n"
_DOORS = {
    "an environment read": {"settings.py": "import os\n" + _ROOT + "DEBUG = os.environ.get('D')\n"},
    "a star import of a file that is absent": {"settings.py": _ROOT + "DEBUG = False\n" + _ABSENT},
    "a text run as the module's code": {
        "settings.py": _ROOT + "DEBUG = False\nwith open('/etc/app.py') as handle:\n"
        "    exec(handle.read())\n"
    },
    "a text run in the module's names it is handed": {
        "settings.py": _ROOT + "DEBUG = False\nexec(open('/etc/app.py').read(), globals())\n"
    },
    "two written values": {"settings.py": "import sys\n" + _ROOT + "DEBUG = False\n"
                           "if sys.argv:\n    DEBUG = True\n"},
    "a door in the module the star takes it from": {
        "base.py": "DEBUG = False\n" + _ABSENT,
        "settings.py": "from app.base import *\n" + _ROOT,
    },
    "a write, then a star import that binds it": {
        "base.py": "DEBUG = False\n",
        "settings.py": _ROOT + "DEBUG = True\nfrom app.base import *\n",
    },
}  # fmt: skip


@pytest.mark.parametrize("door", sorted(_DOORS))
def test_a_test_on_a_setting_with_a_door_in_its_chain_is_not_evaluated(
    tmp_path: Path, libraries, door: str
):
    """Not decided, "not evaluated" as before, where the environment's value is not one
    written literal or something outside the repository can give the key another value: an
    environment read, a write a star import can replace (ruling R10) anywhere in the chain
    of settings modules the key is read through, a text the module runs as its own code
    (`exec`), a name with two values. The last case is the limit of OI-565: a write, then a
    star import that binds the name, is not read as the star's value."""
    workspace = _resolved(tmp_path, libraries, {**_DOORS[door], "urls.py": _DEBUG_URLS})

    assert sorted(row["path"] for row in workspace.query("endpoints")) == ["/d/", "/u/"]
    assert _verdicts(workspace, "settings.DEBUG") == {"app.settings": ("unresolved", "unresolved")}


def test_a_setting_written_after_the_star_import_is_decided_on_its_own_write(
    tmp_path: Path, libraries
):
    """`from app.base import *`, then `DEBUG = False` (ruled 2026-11-26): what runs last binds
    the name, so the settings module's own write is its one value and the test is decided on
    it, whatever the star gives. The common layout of a derived settings module."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "base.py": "ROOT_URLCONF = 'app.urls'\nDEBUG = True\n",
            "settings.py": "from app.base import *\nDEBUG = False\n",
            "urls.py": _DEBUG_URLS,
            "manage.py": _START.format("app.base"),
        },
    )

    assert _verdicts(workspace, "settings.DEBUG") == {
        "app.base": ("true", "resolved"),
        "app.settings": ("false", "resolved"),
    }


def test_a_setting_a_star_import_alone_gives_is_decided_on_its_source(tmp_path: Path, libraries):
    """`from app.base import *` with no write of `DEBUG` in the settings module: the key has
    the one value the source writes, and the test is decided in that environment."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "base.py": "DEBUG = True\n",
            "settings.py": "from app.base import *\n" + _ROOT,
            "urls.py": _DEBUG_URLS,
        },
    )

    assert _verdicts(workspace, "settings.DEBUG") == {"app.settings": ("true", "resolved")}


def test_a_setting_written_with_no_one_value_says_why_in_the_evidence(tmp_path: Path, libraries):
    """A setting the settings module writes, but with no one value (a list, a name written
    twice, `None`): the evidence of a test on it says what the `resolved_config` row says.
    The module does write the name, so it is no placeholder the module does not fill."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "settings.py": "import sys\nROOT_URLCONF = 'app.urls'\nAPPS = ['one', 'two']\n"
            "MODE = 'a'\nif len(sys.argv) > 1:\n    MODE = 'b'\nNOTHING = None\n",
            "urls.py": "from django.conf import settings\n" + _URLS + "if 'one' in settings.APPS:\n"
            "    urlpatterns += [path('a/', v)]\n"
            "if settings.MODE:\n    urlpatterns += [path('m/', v)]\n"
            "if settings.NOTHING:\n    urlpatterns += [path('n/', v)]\n",
        },
    )

    details = {
        str(row["key"]): str(row["unresolved_detail"]) for row in workspace.query("resolved_config")
    }
    evidence = {row[3]: row[6] for row in _existence(workspace) if row[3] != ("ROOT_URLCONF",)}
    details["APPS"] = "APPS is a list, one key for each member"
    assert evidence == {
        (key,): f"`{key}{_SET}app.settings` configuration sets no readable value: {details[key]}"
        for key in ("APPS", "MODE", "NOTHING")
    }
    assert "placeholder" not in "".join(evidence.values())


def test_the_routes_of_a_root_exist_where_the_root_setting_names_it(tmp_path: Path, libraries):
    """Two settings modules name two roots: each root's routes carry the condition
    "`ROOT_URLCONF` is `<root>`", kind `property`, with what each environment sets as
    evidence. It is decided in each environment on the one text that settings module writes
    for the root (ruled 2026-11-26), by the rule of a test on a setting: true where the module
    names this root, false where it names the other. No row is removed and none is copied."""
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
         "false", f"`ROOT_URLCONF{_SET}app.settings` configuration sets `app.urls`"),
        ("/a/", "property", "ROOT_URLCONF == 'app.admin_urls'", ("ROOT_URLCONF",),
         "app.settings_admin", "true",
         f"`ROOT_URLCONF{_SET}app.settings_admin` configuration sets `app.admin_urls`"),
        ("/u/", "property", "ROOT_URLCONF == 'app.urls'", ("ROOT_URLCONF",), "app.settings",
         "true", f"`ROOT_URLCONF{_SET}app.settings` configuration sets `app.urls`"),
        ("/u/", "property", "ROOT_URLCONF == 'app.urls'", ("ROOT_URLCONF",), "app.settings_admin",
         "false",
         f"`ROOT_URLCONF{_SET}app.settings_admin` configuration sets `app.admin_urls`"),
    ]  # fmt: skip
    expression = json.loads(str(workspace.query("endpoint_existence")[0]["expression"]))
    assert expression["having_value"] in ("app.urls", "app.admin_urls")


def test_a_root_a_star_import_can_replace_is_not_decided(tmp_path: Path, libraries):
    """The door of every decided test (ruling R10): a root the settings module writes before
    a star import of a file that is not read has no one value there. "Not evaluated"."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {"settings.py": "ROOT_URLCONF = 'app.urls'\n" + _ABSENT, "urls.py": _URLS},
    )

    assert _verdicts(workspace, "ROOT_URLCONF == 'app.urls'") == {
        "app.settings": ("unresolved", "unresolved")
    }


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
