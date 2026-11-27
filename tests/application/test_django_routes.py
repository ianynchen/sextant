"""Django routes are `fluent` rows: paths and handlers of `path(...)` calls (plan
2026-11-22-python-django-core-inbound, Task 2).

Each test writes a small Django program, scans it with the real Python scanner against the
Django 5.2.8 that `fixtures/orders-django` locks (its own environment is the library read),
and runs the real pipeline with the shipped catalogs. It then reads `endpoints`. The rules are
Django's own, measured in `scripts/probes/django_rules.md`.
"""

import json
from pathlib import Path

import pytest

import fixture_python
from fixture_python import FIXTURES
from sextant.application.ports.artifacts import ReadRequest
from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.pipeline import resolve
from sextant.domain.factfile import config_fact_target, write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.ingress.read.pytest_settings import PytestSettingsReader
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_PREFIX = "sextant-python pypi shop 1 "
# The distribution `fixtures/orders-django` locks, read as the program's library.
_LOCKED = {"django": "5.2.8", "environs": "14.5.0"}


@pytest.fixture(scope="session")
def orders_django_env() -> Path:
    root = FIXTURES / "orders-django"
    fixture_python.synced(root, offline=True)
    return fixture_python.interpreter(root)


@pytest.fixture(scope="module")
def libraries(orders_django_env: Path) -> tuple[LibraryRoot, ...]:
    (site,) = (FIXTURES / "orders-django" / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _LOCKED.items())


# The settings a Django project has: the root its routes are served from (`ROOT_URLCONF`).
_SETTINGS = {"settings.py": "ROOT_URLCONF = 'app.urls'\n"}


def _resolved(
    tmp_path: Path,
    libraries: tuple[LibraryRoot, ...],
    files: dict[str, str],
    settings: dict[str, str] | None = _SETTINGS,
    pytest_ini: str | None = None,
) -> DuckDbWorkspace:
    """`files` under `app/`, with `settings` beside them where `files` writes none; None for
    a program with no settings module (a reusable app)."""
    source = tmp_path / "src"
    if settings is not None and "settings.py" not in files:
        files = {**settings, **files}
    for name, text in files.items():
        path = source / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    facts = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates="shop",
            version="1",
            classes_dir=source,
            out_dir=facts,
            dependency_archives=libraries,
        )
    )
    if pytest_ini is not None:
        # As `analyze` does: the test tool's settings file, read by the reader that claims it.
        (tmp_path / "pytest.ini").write_text(pytest_ini, encoding="utf-8")
        request = ReadRequest(
            module_id="shop", version="1", files=(tmp_path / "pytest.ini",), root=tmp_path
        )
        for document, entries in PytestSettingsReader().read(request):
            write_fact_file(config_fact_target(facts, document.relative_path), document, entries)
    module = Document(
        document_id="module",
        relative_path="pyproject.toml",
        module_id="shop",
        language="python",
        sextant_version="0",
        fact_schema_version="0",
        scanner_id="module",
        content_hash="sha256:none",
        origin_entry="shop",
        origin_tier="module_output",
        redaction_set_hash="sha256:none",
    )
    write_fact_file(
        facts / "module.jsonl",
        module,
        [
            ModuleFact(
                document_id="module",
                module_id="shop",
                module_kind="pyproject",
                languages=["python"],
                source_roots=["src"],
                output_dirs=["src"],
                lookup="c3",
                dependency_coordinates=list(_LOCKED),
                dependency_versions=dict(_LOCKED),
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(
        workspace,
        facts,
        YamlCatalogSource(catalogs_dir()),
        PythonScanner().capabilities(),
    )
    return workspace


def _handler(name: str, module: str = "app/urls") -> str:
    return f"{module}#{name}(sig_"


def _bare(symbol: object) -> str | None:
    """A handler's symbol without its package prefix and its signature digest."""
    if symbol is None:
        return None
    text = str(symbol).removeprefix(_PREFIX)
    return text[: text.index("(sig_") + len("(sig_")] if "(sig_" in text else text


def _rows(workspace: DuckDbWorkspace) -> list[tuple[object, ...]]:
    rows = [
        (
            row["method"],
            row["method_kind"],
            row["path"],
            _bare(row["handler"]),
            row["resolution"],
        )
        for row in workspace.query("endpoints")
        if row["catalog_id"] == "django"
    ]
    return sorted(rows, key=lambda row: tuple("" if part is None else str(part) for part in row))


def _not_read(workspace: DuckDbWorkspace) -> list[tuple[object, ...]]:
    """The `not_read` questions: the row's method and path, and each candidate's column,
    reason, the code it names (`at`, bare) and the method that registered the route."""
    return [
        (
            row["method"],
            row["path"],
            [
                (c["column"], c["reason"], _bare(c["at"]), _bare(c["caller"]))
                for c in json.loads(row["candidates"])
            ],
        )
        for row in workspace.query("open_questions")
        if row["question"] == "not_read"
    ]


_HEAD = "from django.urls import path\n\ndef v(request):\n    return None\n\n"


def _django(tmp_path, libraries, body: str):
    return _rows(_resolved(tmp_path, libraries, {"urls.py": _HEAD + body}))


@pytest.mark.declines("django")
@pytest.mark.pins("fluent.root-owner-is-the-declared-type")
def test_a_path_function_that_is_not_djangos_derives_nothing(tmp_path: Path, libraries):
    """`path` is a common name: the module's own `path(route, view)` is no call of
    `django.urls.conf`, so it registers no route."""
    rows = _rows(
        _resolved(
            tmp_path,
            libraries,
            {
                "urls.py": "def path(route, view):\n    return route\n\n"
                "def v(request):\n    return None\n\n"
                "urlpatterns = [path('items/', v)]\n"
            },
        )
    )

    assert rows == []


def test_an_empty_route_is_the_root(tmp_path: Path, libraries):
    """The served path is `/` + the route (probe, "Paths"): `""` serves `/`. A function view
    with no narrowing decorator gets every method (probe, "Function views": a plain function
    answers GET, POST, PUT, DELETE and OPTIONS 200): one row, method NULL, `method_kind` any."""
    rows = _django(tmp_path, libraries, "urlpatterns = [path('', v)]\n")

    assert rows == [(None, "any", "/", _handler("v"), "resolved")]


def test_converters_stay_as_written(tmp_path: Path, libraries):
    """`ResolverMatch.route` keeps converters as written (probe, "Paths")."""
    rows = _django(tmp_path, libraries, "urlpatterns = [path('items/<int:id>/', v)]\n")

    assert rows == [(None, "any", "/items/<int:id>/", _handler("v"), "resolved")]


def test_a_view_imported_from_another_module_is_the_handler(tmp_path: Path, libraries):
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "views.py": "def items(request):\n    return None\n",
            "urls.py": "from django.urls import path\nfrom app import views\n"
            "urlpatterns = [path('items/', views.items)]\n",
        },
    )

    assert _rows(workspace) == [
        (None, "any", "/items/", _handler("items", "app/views"), "resolved")
    ]


def test_route_and_view_by_keyword(tmp_path: Path, libraries):
    """`_path(route, view, kwargs=None, name=None, Pattern=None)` (probe, "Defining symbols")."""
    rows = _django(tmp_path, libraries, "urlpatterns = [path(route='x/', view=v, name='x')]\n")

    assert rows == [(None, "any", "/x/", _handler("v"), "resolved")]


def test_a_stray_path_call_is_behind_the_hole(tmp_path: Path, libraries):
    """A `path` call in no list the root or a mount reaches: Django serves it nowhere this
    code says, so it is behind `<prefix>` at `partial` (design 2026-11-23 §4a), never
    `resolved` at its own path."""
    rows = _django(tmp_path, libraries, "stray = path('stray/', v)\n")

    assert rows == [(None, "any", "/<prefix>stray/", _handler("v"), "partial")]


# -- `re_path` (plan 6, Task 6; design §5c; rulings R15, R16) ---------------------------------

_RE_HEAD = "from django.urls import include, path, re_path\n\ndef v(request):\n    return None\n\n"


def _expression_rows(tmp_path: Path, libraries, body: str, head: str = _RE_HEAD):
    """Every Django row as (method, method_kind, path, path_kind, handler, resolution), and
    each row's own id distinct, with the workspace."""
    workspace = _resolved(tmp_path, libraries, {"urls.py": head + body})
    found = [row for row in workspace.query("endpoints") if row["catalog_id"] == "django"]
    assert len({row["row_id"] for row in found}) == len(found)
    rows = [
        (
            row["method"],
            row["method_kind"],
            row["path"],
            row["path_kind"],
            _bare(row["handler"]),
            row["resolution"],
        )
        for row in found
    ]
    return sorted(rows, key=lambda row: tuple("" if part is None else str(part) for part in row))


def test_a_named_group_is_a_path_parameter(tmp_path: Path, libraries):
    """Read 1: `^` and `$` dropped, `(?P<item_id>...)` becomes `<item_id>`, behind the
    catalog's `/` (probe, "`re_path`": `^named/(?P<id>\\d+)/$` calls the view with `id=`)."""
    rows = _expression_rows(
        tmp_path, libraries, "urlpatterns = [re_path(r'^old/(?P<item_id>\\d+)/$', v)]\n"
    )

    assert rows == [(None, "any", "/old/<item_id>/", None, _handler("v"), "resolved")]


def test_an_optional_slash_gives_two_rows(tmp_path: Path, libraries):
    """Read 2: `^inbox/?$` serves `/inbox` and `/inbox/` (probe: `^opt/?$` answers both)."""
    rows = _expression_rows(tmp_path, libraries, "urlpatterns = [re_path(r'^inbox/?$', v)]\n")

    assert rows == [
        (None, "any", "/inbox", None, _handler("v"), "resolved"),
        (None, "any", "/inbox/", None, _handler("v"), "resolved"),
    ]


def test_an_expression_not_read_exactly_is_published_as_written(tmp_path: Path, libraries):
    """Read 3: an unnamed group that is not optional is published as written, marked as a
    pattern, at `partial`, with no leading `/`."""
    rows = _expression_rows(
        tmp_path, libraries, "urlpatterns = [re_path(r'^(shelf|books)/$', v)]\n"
    )

    assert rows == [(None, "any", "^(shelf|books)/$", "pattern", _handler("v"), "partial")]


def test_an_endpoint_without_a_final_dollar_is_published_as_written(tmp_path: Path, libraries):
    """Ruling R16: `^noend` as an endpoint also serves `/noendx` and `/noend/deeper` (probe,
    "`re_path`"), so its path is not the only one served: one row as written, `partial`."""
    rows = _expression_rows(tmp_path, libraries, "urlpatterns = [re_path(r'^directory/?', v)]\n")

    assert rows == [(None, "any", "^directory/?", "pattern", _handler("v"), "partial")]


def test_a_final_dollar_without_a_caret_is_exact(tmp_path: Path, libraries):
    """Probe: `mid/x$` is matched with `fullmatch` and serves `/mid/x` only."""
    rows = _expression_rows(tmp_path, libraries, "urlpatterns = [re_path(r'mid/x$', v)]\n")

    assert rows == [(None, "any", "/mid/x", None, _handler("v"), "resolved")]


def test_a_re_path_prefix_mounts_its_list(tmp_path: Path, libraries):
    """`re_path(r'^api/v1/', include(x))`: a prefix match, exact as a mount prefix (probe:
    `re_path('^rx/', include([path('x/', v)]))` serves `/rx/x/`)."""
    rows = _expression_rows(
        tmp_path,
        libraries,
        "items = [path('x/', v)]\nurlpatterns = [re_path(r'^api/v1/', include(items))]\n",
    )

    assert rows == [(None, "any", "/api/v1/x/", None, _handler("v"), "resolved")]


def test_a_re_path_prefix_with_an_optional_piece_mounts_under_both(tmp_path: Path, libraries):
    """Probe: `re_path('^opt2/?', include([path('x/', v)]))` serves `/opt2/x/` and `/opt2x/`."""
    rows = _expression_rows(
        tmp_path,
        libraries,
        "items = [path('x/', v)]\nurlpatterns = [re_path(r'^opt2/?', include(items))]\n",
    )

    assert rows == [
        (None, "any", "/opt2/x/", None, _handler("v"), "resolved"),
        (None, "any", "/opt2x/", None, _handler("v"), "resolved"),
    ]


def test_a_re_path_prefix_not_read_exactly_is_the_unread_prefix(tmp_path: Path, libraries):
    """A mount prefix the reads do not make exact is never guessed: the existing `<prefix>`
    hole at `partial`, and the `mount_prefix` question."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _RE_HEAD
            + "items = [path('x/', v)]\nurlpatterns = [re_path(r'^(a|b)/', include(items))]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/<prefix>x/", _handler("v"), "partial")]
    questions = [
        (row["question"], row["path"])
        for row in workspace.query("open_questions")
        if row["question"] == "mount_prefix"
    ]
    assert questions == [("mount_prefix", "/<prefix>x/")]
    (question,) = [r for r in workspace.query("open_questions") if r["question"] == "mount_prefix"]
    (candidate,) = json.loads(str(question["candidates"]))
    assert candidate["read"] == "a route expression not read exactly: ^(a|b)/"


def test_a_path_prefix_over_a_re_path_child_concatenates(tmp_path: Path, libraries):
    """Probe: `path('api/', include([re_path('^x/$', v)]))` serves `/api/x/`."""
    rows = _expression_rows(
        tmp_path,
        libraries,
        "items = [re_path(r'^x/$', v)]\nurlpatterns = [path('api/', include(items))]\n",
    )

    assert rows == [(None, "any", "/api/x/", None, _handler("v"), "resolved")]


def test_a_class_view_behind_an_optional_piece_is_verbs_times_paths(tmp_path: Path, libraries):
    """Each path of read 2 carries the class's verbs (Task 5): two verbs by two paths, four
    rows, each its own id."""
    rows = _expression_rows(
        tmp_path,
        libraries,
        "class Items(View):\n"
        "    def get(self, request):\n        return None\n"
        "    def delete(self, request):\n        return None\n"
        "urlpatterns = [re_path(r'^x/?$', Items.as_view())]\n",
        head=_RE_HEAD + "from django.views import View\n",
    )

    get, delete = _handler("get", "app/urls/Items"), _handler("delete", "app/urls/Items")
    assert rows == [
        ("DELETE", None, "/x", None, delete, "resolved"),
        ("DELETE", None, "/x/", None, delete, "resolved"),
        ("GET", None, "/x", None, get, "resolved"),
        ("GET", None, "/x/", None, get, "resolved"),
    ]


def test_an_f_string_of_constants_is_read_assembled(tmp_path: Path, libraries):
    """Brief step 3: the value walk assembles the text, then the reads apply to it."""
    rows = _expression_rows(
        tmp_path,
        libraries,
        "ID = r'(?P<id>\\d+)'\nurlpatterns = [re_path(rf'^b/{ID}/?$', v)]\n",
    )

    assert rows == [
        (None, "any", "/b/<id>", None, _handler("v"), "resolved"),
        (None, "any", "/b/<id>/", None, _handler("v"), "resolved"),
    ]


def test_bookwyrms_user_path_is_published_as_written(tmp_path: Path, libraries):
    """bookwyrm: `USER_PATH = rf"^user/(?P<username>{regex.USERNAME})"` and
    `rf"^user/{USER_PATH}/?$"`. The assembled text has a `^` that is not first: not exact."""
    rows = _expression_rows(
        tmp_path,
        libraries,
        "USERNAME = r'[\\w\\-_\\.@]+'\n"
        "USER_PATH = rf'^user/(?P<username>{USERNAME})'\n"
        "urlpatterns = [re_path(rf'^{USER_PATH}/?$', v)]\n",
    )

    assert rows == [
        (
            None,
            "any",
            "^^user/(?P<username>[\\w\\-_\\.@]+)/?$",
            "pattern",
            _handler("v"),
            "partial",
        )
    ]


def test_an_f_string_piece_not_read_is_partial(tmp_path: Path, libraries):
    """A piece the value walk does not read is never guessed: the text with the piece's hole,
    as written, `partial` (the reads never see a whole text)."""
    rows = _expression_rows(
        tmp_path,
        libraries,
        "from elsewhere import X\nurlpatterns = [re_path(rf'^b/{X}/$', v)]\n",
    )

    assert rows == [(None, "any", "^b/{}/$", "pattern", _handler("v"), "partial")]


def test_a_prefix_ending_in_a_named_group_is_the_unread_prefix(tmp_path: Path, libraries):
    """Fix round 1, probe: Django does not backtrack across the include boundary, so
    `re_path(r'^(?P<lang>[a-z]{2})?/?', include([path('ab/', v)]))` answers 404 on `/ab/`
    (`lang` takes `ab`): never `/ab/` at `resolved`, the `<prefix>` hole and its question."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _RE_HEAD + "items = [path('ab/', v)]\n"
            "urlpatterns = [re_path(r'^(?P<lang>[a-z]{2})?/?', include(items))]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/<prefix>ab/", _handler("v"), "partial")]
    questions = [
        row["path"]
        for row in workspace.query("open_questions")
        if row["question"] == "mount_prefix"
    ]
    assert questions == ["/<prefix>ab/"]


def test_a_pattern_child_under_a_prefix_drops_its_caret(tmp_path: Path, libraries):
    """Probe: `URLResolver._join_route` drops the child's leading `^` (`a/` + `^in$` is
    `a/in$`), so the row is Django's own route text."""
    rows = _expression_rows(
        tmp_path,
        libraries,
        "items = [re_path(r'^(a|b)/$', v)]\nurlpatterns = [path('api/', include(items))]\n",
    )

    assert rows == [(None, "any", "api/(a|b)/$", "pattern", _handler("v"), "partial")]


def test_an_f_string_piece_from_another_module_is_read(tmp_path: Path, libraries):
    """Brief step 3: the value walk reads a constant imported from another module."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "consts.py": "ID = r'(?P<id>\\d+)'\n",
            "urls.py": _RE_HEAD
            + "from app.consts import ID\nurlpatterns = [re_path(rf'^b/{ID}/$', v)]\n",
        },
    )

    assert _rows(workspace) == [(None, "any", "/b/<id>/", _handler("v"), "resolved")]


_ROUTES_IN_A_LOOP = {
    "for": "RS = ['a/', 'b/']\nurlpatterns = []\nfor r in RS:\n    urlpatterns += [path(r, v)]\n",
    "comprehension": "RS = ['a/', 'b/']\nurlpatterns = [path(r, v) for r in RS]\n",
}


@pytest.mark.pins("inbound_routes.a-registration-in-a-loop-files-its-reason")
@pytest.mark.parametrize("written", list(_ROUTES_IN_A_LOOP))
def test_a_registration_in_a_loop_whose_path_is_not_read_files_a_question(
    tmp_path: Path, libraries, written: str
):
    """Ruled not supported (2026-11-23): the row keeps no path, `unresolved`. The question
    names the registration (ruled 2026-11-25, R4, OI-502): column `path`, `non_enumerable`."""
    workspace = _resolved(tmp_path, libraries, {"urls.py": _HEAD + _ROUTES_IN_A_LOOP[written]})

    assert _rows(workspace) == [(None, "any", None, _handler("v"), "unresolved")]
    assert _not_read(workspace) == [
        (
            None,
            None,
            [("path", "non_enumerable", "app/urls#<clinit>(sig_", "app/urls#<clinit>(sig_")],
        )
    ]
    (question,) = [r for r in workspace.query("open_questions") if r["question"] == "not_read"]
    (candidate,) = json.loads(question["candidates"])
    site = next(
        row
        for row in workspace.query("call_sites")
        if row["name"] == "path" and row["caller"] == candidate["at"]
    )
    assert candidate["ordinal"] == site["ordinal"]


def test_two_loops_of_one_wire_identity_share_one_question(tmp_path: Path, libraries):
    """One question per wire identity, each registration a candidate of it."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HEAD + "def w(request):\n    return None\nRS = ['a/', 'b/']\n"
            "urlpatterns = [path(r, v) for r in RS] + [path(r, w) for r in RS]\n"
        },
    )

    ((method, path, candidates),) = _not_read(workspace)
    assert (method, path, len(candidates)) == (None, None, 2)


def test_a_route_whose_path_is_read_files_no_not_read_question(tmp_path: Path, libraries):
    workspace = _resolved(
        tmp_path, libraries, {"urls.py": _HEAD + "urlpatterns = [path('x/', v)]\n"}
    )

    assert _rows(workspace) == [(None, "any", "/x/", _handler("v"), "resolved")]
    assert _not_read(workspace) == []
