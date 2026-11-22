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


# -- fix round 1 (Task 3 review) -----------------------------------------------------------------


def _questions(workspace, kind: str) -> list[object]:
    return sorted(
        row["path"] for row in workspace.query("open_questions") if row["question"] == kind
    )


def test_include_of_a_list_sum_mounts_every_operand(tmp_path, libraries):
    """Critical 1: `include(a + b)` mounts both lists; nothing of either serves at the root."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "urls.py": "a = [path('a/', v)]\nb = [path('b/', v)]\n"
            "urlpatterns = [path('api/', include(a + b))]\n"
        },
    )

    assert rows == [_row("/api/a/"), _row("/api/b/")]


def test_include_of_a_module_outside_the_scan_files_the_question(tmp_path, libraries):
    """Ruling R6 (a): `include("allauth.urls")` names a module the scan does not hold, so its
    routes are not read: no row, one `mounted_router` question at the prefix."""
    workspace = _program(
        tmp_path,
        libraries,
        {"urls.py": "urlpatterns = [path('accounts/', include('allauth.urls'))]\n"},
    )

    assert _rows(workspace) == []
    assert _questions(workspace, "mounted_router") == ["/accounts/"]


def test_a_list_extended_by_an_unread_value_publishes_what_is_read_and_asks(tmp_path, libraries):
    """Ruling R6 (b): `urlpatterns += router.urls` on an unknown object: the routes read are
    published under the prefix, and the part not read is asked about."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            "api_urls.py": "class Router:\n    urls = []\nrouter = Router()\n"
            "urlpatterns = [path('x/', v)]\nurlpatterns += router.urls\n",
            "urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n",
        },
    )

    assert _rows(workspace) == [_row("/api/x/")]
    assert _questions(workspace, "mounted_router") == ["/api/"]


def test_include_of_an_unread_value_plus_a_list_publishes_the_list_and_asks(tmp_path, libraries):
    """Ruling R6 (c): `include(router.urls + extra)`."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            "urls.py": "class Router:\n    urls = []\nrouter = Router()\n"
            "extra = [path('e/', v)]\n"
            "urlpatterns = [path('api/', include(router.urls + extra))]\n"
        },
    )

    assert _rows(workspace) == [_row("/api/e/")]
    assert _questions(workspace, "mounted_router") == ["/api/"]


def test_a_list_display_unpacking_a_list_holds_both(tmp_path, libraries):
    """Ruling R8: `[*base, path(...)]` is one list holding `base`'s routes and its own."""
    rows = _served(
        tmp_path,
        libraries,
        {
            "api_urls.py": "base = [path('b/', v)]\nurlpatterns = [*base, path('x/', v)]\n",
            "urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n",
        },
    )

    assert rows == [_row("/api/b/"), _row("/api/x/")]


def test_a_list_a_library_call_holds_is_behind_an_unread_prefix(tmp_path, libraries):
    """Ruling R8: a list a call the catalog does not know holds (`format_suffix_patterns`)
    cannot be placed: its route publishes behind `<prefix>` at `partial`, with the
    `mount_prefix` question; never at the root as `resolved`."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            "urls.py": "from django.urls import get_resolver\n"
            "urlpatterns = get_resolver([path('x/', v)])\n"
        },
    )

    assert _rows(workspace) == [_row("/<prefix>x/", "partial")]
    assert _questions(workspace, "mount_prefix") == ["/<prefix>x/"]


def test_include_of_a_function_result_is_behind_an_unread_prefix(tmp_path, libraries):
    """Ruling R8: `include(extra())` where `extra()` returns a list holding a route: the route
    is `partial` behind `<prefix>`, and the mount asks `mounted_router`."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            "urls.py": "def extra():\n    return [path('e/', v)]\n"
            "urlpatterns = [path('api/', include(extra()))]\n"
        },
    )

    assert _rows(workspace) == [_row("/<prefix>e/", "partial")]
    assert _questions(workspace, "mount_prefix") == ["/<prefix>e/"]
    assert _questions(workspace, "mounted_router") == ["/api/"]


# -- fix round 2 (ruling R9) ------------------------------------------------------------------------

_INCLUDED = {"urls.py": "urlpatterns = [path('api/', include('app.api_urls'))]\n"}


def test_an_aliased_list_is_mounted(tmp_path, libraries):
    """R9 part 1: `urlpatterns = base` is the list `base`; the mount follows the name."""
    workspace = _program(
        tmp_path,
        libraries,
        {**_INCLUDED, "api_urls.py": "base = [path('x/', v)]\nurlpatterns = base\n"},
    )

    assert _rows(workspace) == [_row("/api/x/")]
    assert _questions(workspace, "mounted_router") == []
    assert _questions(workspace, "mount_prefix") == []


def test_a_re_exported_list_is_mounted(tmp_path, libraries):
    """R9 part 1: `from app.other import urlpatterns` binds the name to the other module's
    list, any number of steps."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            **_INCLUDED,
            "other.py": "urlpatterns = [path('x/', v)]\n",
            "middle.py": "from app.other import urlpatterns\n",
            "api_urls.py": "from app.middle import urlpatterns\n",
        },
    )

    assert _rows(workspace) == [_row("/api/x/")]
    assert _questions(workspace, "mounted_router") == []


def test_an_aliased_or_re_exported_list_in_a_root_module_stays_at_the_root(tmp_path, libraries):
    """R9 part 1, unchanged: the same modules used as roots serve `/x/` at `resolved`."""
    alias = _served(
        tmp_path / "alias",
        libraries,
        {"api_urls.py": "base = [path('x/', v)]\nurlpatterns = base\n"},
    )
    reexport = _served(
        tmp_path / "reexport",
        libraries,
        {
            "other.py": "urlpatterns = [path('x/', v)]\n",
            "api_urls.py": "from app.other import urlpatterns\n",
        },
    )

    assert alias == reexport == [_row("/x/")]


def test_a_list_handed_to_a_call_no_catalog_reads_is_behind_an_unread_prefix(tmp_path, libraries):
    """R9 part 2: `urlpatterns = list(base)` included at `api/`: `base` is handed to a call no
    catalog reads, so it cannot be placed; nothing is `resolved` at the root."""
    workspace = _program(
        tmp_path,
        libraries,
        {**_INCLUDED, "api_urls.py": "base = [path('x/', v)]\nurlpatterns = list(base)\n"},
    )

    assert _rows(workspace) == [_row("/<prefix>x/", "partial")]
    assert _questions(workspace, "mount_prefix") == ["/<prefix>x/"]


def test_a_list_unpacked_into_a_call_no_catalog_reads_is_behind_an_unread_prefix(
    tmp_path, libraries
):
    """R9 part 2, the starred form: `wrap(*base)`."""
    workspace = _program(
        tmp_path,
        libraries,
        {
            **_INCLUDED,
            "api_urls.py": "def wrap(*items):\n    return list(items)\n"
            "base = [path('x/', v)]\nurlpatterns = wrap(*base)\n",
        },
    )

    assert [row[2:] for row in _rows(workspace)] == [("/<prefix>x/", _V, "partial")]


def test_a_root_list_passed_nowhere_stays_at_the_root(tmp_path, libraries):
    """R9 part 2 leaves design §5d: a module-level list nothing unread uses is the root."""
    rows = _served(tmp_path, libraries, {"urls.py": "urlpatterns = [path('x/', v)]\n"})

    assert rows == [_row("/x/")]


def test_a_named_list_extended_into_an_included_list_is_mounted(tmp_path, libraries):
    """R9 with the rule `_held_by` states: a call made on a field's value holds its arguments,
    so `urlpatterns.extend(other)` puts `other`'s routes in `urlpatterns`: mounted with it, and
    at the root where it is the root."""
    body = "other = [path('o/', v)]\nurlpatterns = [path('x/', v)]\nurlpatterns.extend(other)\n"
    included = _served(tmp_path / "included", libraries, {**_INCLUDED, "api_urls.py": body})
    root = _served(tmp_path / "root", libraries, {"api_urls.py": body})

    assert included == [_row("/api/o/"), _row("/api/x/")]
    assert root == [_row("/o/"), _row("/x/")]
