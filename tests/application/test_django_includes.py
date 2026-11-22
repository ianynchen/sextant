"""Django `include`: a list is a router, and `path(prefix, include(x))` serves `x`'s routes
behind `prefix` (plan 2026-11-22-python-django-core-inbound, Task 3; design §5b capabilities
1-3, §5d).

The rules are Django's own, measured in `scripts/probes/django_rules.md` ("Paths",
"`include`"): prefix and child route concatenate with nothing between, the served path is
that string with a leading `/`, `include` takes a dotted string, a module object, a list or a
`(list, app_name)` tuple, the variable read from a module is `urlpatterns`, and one list
included at two prefixes is served at both. A list no `include` names is served at `/`
(design §5d).

Each test writes a small Django program and runs the real scanner and pipeline with the
shipped catalogs (`test_django_routes._resolved`).
"""

import json
from pathlib import Path

import test_django_routes
from test_django_routes import _handler, _resolved, _rows

libraries = test_django_routes.libraries
orders_django_env = test_django_routes.orders_django_env

_HEAD = "from django.urls import include, path\nfrom app.views import v\n\n"
_VIEWS = {"views.py": "def v(request):\n    return None\n"}
_V = _handler("v", "app/views")
_NOT_EVALUATED = "a condition this analysis does not evaluate: "


def _program(tmp_path: Path, libraries, modules: dict[str, str]):
    """`modules` by file name under `app/`, each behind the common imports."""
    files = {**_VIEWS, **{name: _HEAD + body for name, body in modules.items()}}
    return _resolved(tmp_path, libraries, files)


def _served(tmp_path: Path, libraries, modules: dict[str, str]) -> list[tuple[object, ...]]:
    return _rows(_program(tmp_path, libraries, modules))


def _row(path: str, resolution: str = "resolved") -> tuple[object, ...]:
    return (None, "any", path, _V, resolution)


# -- Review Focus 1: the join adds nothing ---------------------------------------------------


def test_a_trailing_slash_prefix_and_a_route_concatenate(tmp_path, libraries):
    """`'api/'` + `'items/'` is `api/items/`, served with a leading `/` (probe, "Paths"). The
    mounting `path` call is no route of its own: it serves only what it includes."""
    rows = _served(
        tmp_path,
        libraries,
        {"urls.py": "items = [path('items/', v)]\nurlpatterns = [path('api/', include(items))]\n"},
    )

    assert rows == [_row("/api/items/")]


def test_a_prefix_without_a_slash_joins_with_nothing_between(tmp_path, libraries):
    """`'api'` + `'items/'` is `apiitems/` (probe, "Paths": `'api'` + `'x'` is `apix`)."""
    rows = _served(
        tmp_path,
        libraries,
        {"urls.py": "items = [path('items/', v)]\nurlpatterns = [path('api', include(items))]\n"},
    )

    assert rows == [_row("/apiitems/")]


def test_a_child_route_starting_with_a_slash_serves_a_double_slash(tmp_path, libraries):
    """Ruling R5 (probe, "Differs from the design" item 3): `'api/'` + `'/lead'` is
    `api//lead`; nothing is stripped."""
    rows = _served(
        tmp_path,
        libraries,
        {"urls.py": "inner = [path('/lead', v)]\nurlpatterns = [path('api/', include(inner))]\n"},
    )

    assert rows == [_row("/api//lead")]


# -- Review Focus 2: one list, two prefixes; by name or by object ----------------------------


def test_one_list_included_at_two_prefixes_serves_at_both(tmp_path, libraries):
    """Probe, "`include`": "One list included at two prefixes mounts at both"."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "urls.py": "leaf = [path('leaf', v)]\n"
            "urlpatterns = [path('twice1/', include(leaf)), path('twice2/', include(leaf))]\n"
        },
    )

    assert rows == [_row("/twice1/leaf"), _row("/twice2/leaf")]


def test_a_module_by_name_and_by_object_give_the_same_rows(tmp_path, libraries):
    """`include("app.api_urls")` and `include(api_urls)` read the same `urlpatterns`."""
    api = {"api_urls.py": "urlpatterns = [path('a/', v)]\n"}
    by_name = _served(
        tmp_path / "name",
        libraries,
        {**api, "urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n"},
    )
    by_object = _served(
        tmp_path / "object",
        libraries,
        {
            **api,
            "urls.py": "from app import api_urls\n"
            "urlpatterns = [path('api/', include(api_urls))]\n",
        },
    )

    assert by_name == by_object == [_row("/api/a/")]


# -- every include form ------------------------------------------------------------------------


def test_include_a_module_by_its_dotted_name(tmp_path, libraries):
    """The variable Django reads from an included module is `urlpatterns` (probe)."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "api_urls.py": "urlpatterns = [path('a/', v), path('b/<int:id>/', v)]\n",
            "urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n",
        },
    )

    assert rows == [_row("/api/a/"), _row("/api/b/<int:id>/")]


def test_include_a_list_written_in_the_call(tmp_path, libraries):
    rows = _served(
        tmp_path,
        libraries,
        {"urls.py": "urlpatterns = [path('l/', include([path('in/', v)]))]\n"},
    )

    assert rows == [_row("/l/in/")]


def test_include_a_list_and_app_name_tuple(tmp_path, libraries):
    """A `(list, app_name)` tuple mounts the list (probe, "`include`")."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "urls.py": "extra = [path('e/', v)]\n"
            "urlpatterns = [path('t/', include((extra, 'shop')))]\n"
        },
    )

    assert rows == [_row("/t/e/")]


def test_include_with_a_namespace(tmp_path, libraries):
    """`namespace=` names the instance; it changes no path."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "api_urls.py": "app_name = 'api'\nurlpatterns = [path('a/', v)]\n",
            "urls.py": "urlpatterns = [path('api/', include('app.api_urls', namespace='n'))]\n",
        },
    )

    assert rows == [_row("/api/a/")]


def test_three_levels_of_include(tmp_path, libraries):
    rows = _served(
        tmp_path,
        libraries,
        {
            "c_urls.py": "urlpatterns = [path('c/', v)]\n",
            "b_urls.py": "urlpatterns = [path('b/', include('app.c_urls'))]\n",
            "urls.py": "urlpatterns = [path('a/', include('app.b_urls'))]\n",
        },
    )

    assert rows == [_row("/a/b/c/")]


# -- capability 1: what a list holds -------------------------------------------------------------


def test_a_list_made_of_two_lists_holds_both(tmp_path, libraries):
    """`urlpatterns = a + b` is one list holding the routes of both."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "api_urls.py": "a = [path('a/', v)]\nb = [path('b/', v)]\nurlpatterns = a + b\n",
            "urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n",
        },
    )

    assert rows == [_row("/api/a/"), _row("/api/b/")]


def test_routes_added_with_plus_equals_are_in_the_list(tmp_path, libraries):
    rows = _served(
        tmp_path,
        libraries,
        {
            "api_urls.py": "urlpatterns = [path('a/', v)]\nurlpatterns += [path('b/', v)]\n",
            "urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n",
        },
    )

    assert rows == [_row("/api/a/"), _row("/api/b/")]


def test_routes_added_with_extend_and_append_are_in_the_list(tmp_path, libraries):
    rows = _served(
        tmp_path,
        libraries,
        {
            "api_urls.py": "urlpatterns = [path('a/', v)]\n"
            "urlpatterns.extend([path('b/', v)])\n"
            "urlpatterns.append(path('c/', v))\n",
            "urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n",
        },
    )

    assert rows == [_row("/api/a/"), _row("/api/b/"), _row("/api/c/")]


def test_routes_added_under_debug_are_not_evaluated(tmp_path, libraries):
    """`if settings.DEBUG: urlpatterns += [...]`: the deployment decides the test (ruling
    2026-10-23), so the row's existence is "not evaluated"; the row itself is unchanged and
    the route outside the test has no condition."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            "api_urls.py": "from django.conf import settings\n"
            "urlpatterns = [path('a/', v)]\n"
            "if settings.DEBUG:\n    urlpatterns += [path('dbg/', v)]\n",
            "urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n",
        },
    )

    assert _rows(workspace) == [_row("/api/a/"), _row("/api/dbg/")]
    live = {row["row_id"]: row["path"] for row in workspace.query("endpoints")}
    conditions = sorted(
        (
            live[row["row_id"]],
            json.loads(str(row["expression"]))["test"],
            row["holds"],
            row["evidence"],
        )
        for row in workspace.query("endpoint_existence")
    )
    assert conditions == [
        ("/api/dbg/", "settings.DEBUG", "unresolved", f"{_NOT_EVALUATED}`settings.DEBUG`")
    ]


# -- design §5d: the roots -------------------------------------------------------------------------


def test_a_list_nothing_includes_is_served_at_the_root(tmp_path, libraries):
    """Design §5d: `ROOT_URLCONF` is not needed to find the root; a list no `include` names is
    served at `/`, beside the lists that are included."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "api_urls.py": "urlpatterns = [path('a/', v)]\n",
            "urls.py": "urlpatterns = [path('home/', v), path('api/', include('app.api_urls'))]\n",
            "other_urls.py": "urlpatterns = [path('o/', v)]\n",
        },
    )

    assert rows == [_row("/api/a/"), _row("/home/"), _row("/o/")]


# -- what is not read ------------------------------------------------------------------------------


def test_an_unread_prefix_row_and_its_question_carry_the_leading_slash(tmp_path, libraries):
    """A mount whose route is not read gives `<prefix>` at `partial` (never a guessed path),
    and the `mount_prefix` question names the row by the path the row publishes: with the
    catalog's leading `/` (Task 2 review)."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            "urls.py": "import os\n"
            "extra = [path('e/', v)]\n"
            "urlpatterns = [path(os.environ['P'], include(extra))]\n"
        },
    )

    assert _rows(workspace) == [_row("/<prefix>e/", "partial")]
    questions = [
        (row["question"], row["path"])
        for row in workspace.query("open_questions")
        if row["question"] == "mount_prefix"
    ]
    assert questions == [("mount_prefix", "/<prefix>e/")]


def test_include_of_an_object_the_catalog_does_not_know_gives_no_row_and_one_question(
    tmp_path, libraries
):
    """`include(router.urls)` on an object no catalog reads (Django REST Framework's router,
    plan 7): its routes are not read, so no row, the mount's own included; and never silent,
    one `mounted_router` question at the prefix as served, naming the mount, the inner call
    and what its argument read as."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            "urls.py": "class Router:\n    urls = []\n"
            "router = Router()\n"
            "urlpatterns = [path('home/', v), path('api/', include(router.urls))]\n"
        },
    )

    assert _rows(workspace) == [_row("/home/")]
    questions = [
        (row["protocol"], row["method"], row["path"], row["question"])
        for row in workspace.query("open_questions")
    ]
    assert questions == [("http", None, "/api/", "mounted_router")]
    (row,) = workspace.query("open_questions")
    (candidate,) = json.loads(str(row["candidates"]))
    assert candidate["mount"] == candidate["caller"] == candidate["at"]
    assert candidate["mount"].endswith("app/urls#<clinit>(sig_dd69782a).")
    assert candidate["at_ordinal"] != candidate["mount_ordinal"]
    assert candidate["argument"] == 0
    assert candidate["read"].startswith("no value")


def test_the_app_name_of_a_tuple_is_no_module(tmp_path, libraries):
    """`include((patterns, "app"))`: only the tuple's first element is the router (probe,
    "`include`": the tuple is `(list, app_name)`). A package named like the app name, with a
    `urlpatterns` of its own, is not mounted there: it serves at the root, as a list no
    `include` names does."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "__init__.py": "urlpatterns = [path('own/', v)]\n",
            "urls.py": "extra = [path('e/', v)]\n"
            "urlpatterns = [path('t/', include((extra, 'app')))]\n",
        },
    )

    assert rows == [_row("/own/"), _row("/t/e/")]


def test_a_path_whose_view_is_not_an_include_is_a_route_not_a_mount(tmp_path, libraries):
    """Only an `include` call in the view position mounts; a view is a route as before."""
    rows = _served(tmp_path, libraries, {"urls.py": "urlpatterns = [path('x/', v)]\n"})

    assert rows == [_row("/x/")]
