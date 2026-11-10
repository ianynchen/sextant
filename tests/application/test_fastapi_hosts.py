"""`app.host(host, app)` is a mount with a host (OI-368 second half; key `mount[].host_arg`,
approved by the user 2026-11-09). Starlette 1.6.0's `Host` (probe in the plan 2 final fixes
report): the mounted app's routes are served at their own paths, only on a request whose `Host`
header, port removed, matches; the outer app's `dependencies=` do not run for them.

Each such row carries an `endpoint_metadata` entry of kind `host`, name `Host`, valued with the
host the value walk reads (as vertx-web's `virtualHost` writes one), and the registering call's
tests (Task 10b). A host the walk does not read whole is no value, `unresolved`: never guessed.

Each test writes a small FastAPI program and runs the real scanner and pipeline with the shipped
catalogs (`test_fastapi_routes._resolved`)."""

from pathlib import Path

import test_fastapi_routes
from test_fastapi_conditions import _existence, _open
from test_fastapi_routes import _resolved, _rows

libraries = test_fastapi_routes.libraries

_APP = "from fastapi import Depends, FastAPI\n"
_SETTINGS = (
    "class Settings:\n"
    "    LINK_HOST: str | None = None\n"
    "    BACK_HOST: str | None = None\n"
    "    BACK: bool = True\n"
    "settings = Settings()\n"
)
_SUB = (
    "links = FastAPI()\n@links.get('/{secret}')\ndef link(secret: str) -> str:\n    return secret\n"
)


def _hosts(workspace) -> dict[tuple[object, object], list[tuple[object, ...]]]:
    """Each row's `host` entries, as (name, value, resolution), by (method, path). Every entry
    names its row's handler as its `caller`, which is what binds it to that row."""
    live = {(row["method"], row["path"], row["handler"]) for row in workspace.query("endpoints")}
    found: dict[tuple[object, object], list[tuple[object, ...]]] = {}
    for row in workspace.query("endpoint_metadata"):
        if row["kind"] == "host":
            assert (row["method"], row["path"], row["caller"]) in live, row
            found.setdefault((row["method"], row["path"]), []).append(
                (row["name"], row["value"], row["resolution"])
            )
    return {key: sorted(value, key=repr) for key, value in found.items()}


def test_a_host_mount_serves_the_apps_routes_at_their_own_paths_on_that_host(
    tmp_path: Path, libraries
):
    """The sub-application's route is served at its own path with the host it is mounted
    under; the outer app's own route carries no host."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "app = FastAPI()\n"
            + _SUB
            + "@app.get('/main')\ndef main() -> str:\n    return ''\n"
            + "app.host('links.example.com', links)\n"
        },
    )

    assert [(row[0], row[1], row[3]) for row in _rows(workspace)] == [
        ("GET", "/main", "resolved"),
        ("GET", "/{secret}", "resolved"),
    ]
    assert _hosts(workspace) == {
        ("GET", "/{secret}"): [("Host", "links.example.com", "resolved")],
    }
    assert _existence(workspace) == {}


def test_the_outer_apps_dependencies_do_not_run_under_a_host(tmp_path: Path, libraries):
    """Starlette serves the hosted app as an application of its own: `FastAPI(dependencies=)`
    of the outer app is no recipe of its routes."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + "def outer() -> None:\n    return None\n"
            + "app = FastAPI(dependencies=[Depends(outer)])\n"
            + _SUB
            + "@app.get('/main')\ndef main() -> str:\n    return ''\n"
            + "app.host('links.example.com', app=links)\n"
        },
    )

    roots = {
        (row["method"], row["path"], str(row["handler"]).split(" ")[-1].split("(sig_")[0])
        for row in workspace.query("roots")
    }
    assert ("GET", "/main", "app/main#outer") in roots
    assert not any(path == "/{secret}" and handler.endswith("#outer") for _, path, handler in roots)


def test_a_host_read_from_settings_is_unresolved_and_its_route_not_evaluated(
    tmp_path: Path, libraries
):
    """polar's checkout-link shape: the host is a settings field and the call sits under a test
    of it. The host is not read (no value is guessed) and the route exists "not evaluated"."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "app = FastAPI()\n"
            + _SUB
            + "if settings.LINK_HOST is not None:\n"
            + "    app.host(settings.LINK_HOST, links)\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/{secret}")]
    assert _hosts(workspace) == {("GET", "/{secret}"): [("Host", None, "unresolved")]}
    assert _existence(workspace) == {
        ("GET", "/{secret}"): [_open(0, "settings.LINK_HOST is not None")],
    }


def test_a_mount_or_a_host_by_a_test_gives_both_rows_each_with_its_own_condition(
    tmp_path: Path, libraries
):
    """polar's backoffice shape: mounted at `/backoffice` where no host is set, else served on
    the host at its own paths. The host-scoped copy carries its host and the test's other arm;
    neither row looks like a plain route of the main host."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _APP
            + _SETTINGS
            + "app = FastAPI()\n"
            + "back = FastAPI()\n"
            + "@back.get('/users')\ndef users() -> str:\n    return ''\n"
            + "if settings.BACK:\n"
            + "    if settings.BACK_HOST is None:\n"
            + "        app.mount('/backoffice', back)\n"
            + "    else:\n"
            + "        app.host(settings.BACK_HOST, back)\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [
        ("GET", "/backoffice/users"),
        ("GET", "/users"),
    ]
    assert _hosts(workspace) == {("GET", "/users"): [("Host", None, "unresolved")]}
    assert _existence(workspace) == {
        ("GET", "/backoffice/users"): [
            _open(0, "settings.BACK"),
            _open(0, "settings.BACK_HOST is None"),
        ],
        ("GET", "/users"): [
            _open(0, "settings.BACK"),
            _open(0, "settings.BACK_HOST is None", holds=False),
        ],
    }
