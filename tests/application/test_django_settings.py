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

from pathlib import Path

import test_django_routes
from test_django_routes import _resolved

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
