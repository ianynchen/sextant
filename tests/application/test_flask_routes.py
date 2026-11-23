"""Flask routes are `fluent` rows: verbs, paths and handlers (plan
2026-11-19-python-flask-inbound.md, Task 2).

Each test writes a small Flask program, scans it with the real Python scanner against the
Flask 3.1.3 that `fixtures/orders-flask` locks (its own environment is the library read),
and runs the real pipeline with the shipped catalogs. It then reads `endpoints`. The rules are
Flask's own, measured in `scripts/probes/flask_rules.md`.
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
from sextant.ingress.detect.python import PythonDetector
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_PREFIX = "sextant-python pypi shop 1 "
# The distributions `fixtures/orders-flask` locks, read as the program's libraries.
_LOCKED = {"flask": "3.1.3", "werkzeug": "3.1.9"}


@pytest.fixture(scope="session")
def orders_flask_env() -> Path:
    root = FIXTURES / "orders-flask"
    fixture_python.synced(root, offline=True)
    return fixture_python.interpreter(root)


@pytest.fixture(scope="module")
def libraries(orders_flask_env: Path) -> tuple[LibraryRoot, ...]:
    (site,) = (FIXTURES / "orders-flask" / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _LOCKED.items())


def _resolved(
    tmp_path: Path,
    libraries: tuple[LibraryRoot, ...],
    files: dict[str, str],
    catalogs: Path | None = None,
    locked: dict[str, str] = _LOCKED,
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
                dependency_coordinates=list(locked),
                dependency_versions=dict(locked),
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(
        workspace,
        facts,
        YamlCatalogSource(catalogs or catalogs_dir()),
        PythonScanner().capabilities(),
    )
    return workspace


def _handler(name: str, module: str = "app/main") -> str:
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
            row["path"],
            _bare(row["handler"]),
            row["resolution"],
        )
        for row in workspace.query("endpoints")
        if row["catalog_id"] == "flask"
    ]
    return sorted(rows, key=lambda row: tuple("" if part is None else str(part) for part in row))


def _questions(workspace: DuckDbWorkspace, question: str) -> list[dict]:
    return [row for row in workspace.query("open_questions") if row["question"] == question]


_APP = "from flask import Flask\napp = Flask(__name__)\n"


def _flask(tmp_path, libraries, body: str, head: str = _APP):
    return _rows(_resolved(tmp_path, libraries, {"main.py": head + body}))


@pytest.mark.declines("flask")
@pytest.mark.pins("fluent.root-owner-is-the-declared-type")
def test_a_route_on_anything_but_an_app_or_a_blueprint_derives_nothing(tmp_path: Path, libraries):
    """`route` and `get` are common names: a dict's `get`, and a route-shaped decorator of the
    module's own class, are calls on no Flask type, so they register no route."""
    rows = _flask(
        tmp_path,
        libraries,
        "class Router:\n    def route(self, path):\n        return lambda f: f\n"
        "router = Router()\n"
        "@router.route('/items')\ndef items():\n    return ''\n"
        "CACHE = {}\nCACHE.get('/items')\n",
    )

    assert rows == []


def test_a_flask_declared_only_in_a_dependency_group_applies_the_catalog(tmp_path: Path, libraries):
    """zulip declares Django only under `[dependency-groups]`: the detector reads it, so the
    catalog applies (PEP 735; the declaration is what `detect.coordinates` is matched to)."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "shop"\n[dependency-groups]\nprod = ["flask>=3"]\n', encoding="utf-8"
    )
    (project / "app").mkdir()
    (project / "app" / "main.py").write_text("", encoding="utf-8")
    (module,) = PythonDetector().detect(project).modules
    declared = {name: _LOCKED[name] for name in module.dependency_coordinates}

    rows = _rows(
        _resolved(
            tmp_path,
            libraries,
            {"main.py": _APP + "@app.route('/items')\ndef items():\n    return ''\n"},
            locked=declared,
        )
    )

    assert declared == {"flask": "3.1.3"}
    assert rows == [("GET", "/items", _handler("items"), "resolved")]


def test_bare_route_is_get_only(tmp_path: Path, libraries):
    """No `methods`: GET. The automatic HEAD and OPTIONS rows `url_map` adds are a stated
    boundary (probe: `methods` absent -> `GET, HEAD, OPTIONS`), never published rows."""
    rows = _flask(tmp_path, libraries, "@app.route('/items')\ndef items():\n    return ''\n")

    assert rows == [("GET", "/items", _handler("items"), "resolved")]


def test_methods_are_one_row_each_upper_cased(tmp_path: Path, libraries):
    rows = _flask(
        tmp_path,
        libraries,
        "@app.route('/x', methods=['post', 'delete'])\ndef x():\n    return ''\n",
    )

    assert rows == [
        ("DELETE", "/x", _handler("x"), "resolved"),
        ("POST", "/x", _handler("x"), "resolved"),
    ]


def test_verb_shortcuts_are_fixed_methods(tmp_path: Path, libraries):
    rows = _flask(
        tmp_path,
        libraries,
        "".join(
            f"@app.{v}('/{v}')\ndef {v}_():\n    return ''\n"
            for v in ("get", "post", "put", "patch", "delete")
        ),
    )

    assert [(r[0], r[1]) for r in rows] == [
        ("DELETE", "/delete"),
        ("GET", "/get"),
        ("PATCH", "/patch"),
        ("POST", "/post"),
        ("PUT", "/put"),
    ]


def test_add_url_rule_names_its_view_func(tmp_path: Path, libraries):
    rows = _flask(
        tmp_path,
        libraries,
        "def export():\n    return ''\n"
        "app.add_url_rule('/export', view_func=export)\n"
        "app.add_url_rule('/purge', 'purge', export, methods=['DELETE'])\n",
    )

    assert rows == [
        ("DELETE", "/purge", _handler("export"), "resolved"),
        ("GET", "/export", _handler("export"), "resolved"),
    ]


def test_converters_are_published_as_written(tmp_path: Path, libraries):
    rows = _flask(tmp_path, libraries, "@app.route('/u/<int:id>')\ndef u(id):\n    return ''\n")

    assert rows == [("GET", "/u/<int:id>", _handler("u"), "resolved")]


def test_blueprint_route_rows_at_its_own_path(tmp_path: Path, libraries):
    """A blueprint's route with no prefix and no registration seen rows at its own path."""
    rows = _flask(
        tmp_path,
        libraries,
        "bp = Blueprint('bp', __name__)\n@bp.route('/b')\ndef b():\n    return ''\n"
        "@bp.post('/c')\ndef c():\n    return ''\n"
        "bp.add_url_rule('/d', view_func=b)\n",
        "from flask import Blueprint\n",
    )

    assert rows == [
        ("GET", "/b", _handler("b"), "resolved"),
        ("GET", "/d", _handler("b"), "resolved"),
        ("POST", "/c", _handler("c"), "resolved"),
    ]


def test_a_decorated_function_is_still_the_handler_by_name(tmp_path: Path, libraries):
    """`route` and the verb shortcuts hand the function back, so naming it later is naming it."""
    rows = _flask(
        tmp_path,
        libraries,
        "@app.get('/b')\ndef b():\n    return ''\napp.add_url_rule('/d', view_func=b)\n",
    )

    assert rows == [
        ("GET", "/b", _handler("b"), "resolved"),
        ("GET", "/d", _handler("b"), "resolved"),
    ]


def test_a_blueprint_built_in_another_module_still_routes(tmp_path: Path, libraries):
    """`bp` is made in one module and imported by the one that writes `@bp.route`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "base.py": "from flask import Blueprint\nbp = Blueprint('bp', __name__)\n",
            "views.py": "from app.base import bp\n@bp.route('/b')\ndef b():\n    return ''\n",
        },
    )

    assert _rows(workspace) == [("GET", "/b", _handler("b", "app/views"), "resolved")]


def test_an_app_rule_with_no_leading_slash_and_no_prefix_derives_nothing(tmp_path: Path, libraries):
    """Flask raises `ValueError` at registration for a rule with no leading slash, so no
    route exists to publish (`refuses_unrooted_path`)."""
    rows = _flask(tmp_path, libraries, "@app.route('x')\ndef x():\n    return ''\n")

    assert rows == []
