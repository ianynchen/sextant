"""Django routes are `fluent` rows: paths and handlers of `path(...)` calls (plan
2026-11-22-python-django-core-inbound, Task 2).

Each test writes a small Django program, scans it with the real Python scanner against the
Django 5.2.8 that `fixtures/orders-django` locks (its own environment is the library read),
and runs the real pipeline with the shipped catalogs. It then reads `endpoints`. The rules are
Django's own, measured in `scripts/probes/django_rules.md`.
"""

from pathlib import Path

import pytest

import fixture_python
from fixture_python import FIXTURES
from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.pipeline import resolve
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_PREFIX = "sextant-python pypi shop 1 "
# The distribution `fixtures/orders-django` locks, read as the program's library.
_LOCKED = {"django": "5.2.8"}


@pytest.fixture(scope="session")
def orders_django_env() -> Path:
    root = FIXTURES / "orders-django"
    fixture_python.synced(root, offline=True)
    return fixture_python.interpreter(root)


@pytest.fixture(scope="module")
def libraries(orders_django_env: Path) -> tuple[LibraryRoot, ...]:
    (site,) = (FIXTURES / "orders-django" / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _LOCKED.items())


def _resolved(
    tmp_path: Path, libraries: tuple[LibraryRoot, ...], files: dict[str, str]
) -> DuckDbWorkspace:
    source = tmp_path / "src"
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


def test_a_stray_path_call_rows_at_its_own_path(tmp_path: Path, libraries):
    """A `path` call in no list that reaches a `urlpatterns` is published at its own path, as
    Flask's blueprint that nothing registers is (`test_flask_routes`: "A blueprint's route with
    no prefix and no registration seen rows at its own path"). Django serves no such route;
    the list-is-a-router rule (design §5b capability 1, Task 3) finds no list holding it, so
    this reading stands."""
    rows = _django(tmp_path, libraries, "stray = path('stray/', v)\n")

    assert rows == [(None, "any", "/stray/", _handler("v"), "resolved")]
