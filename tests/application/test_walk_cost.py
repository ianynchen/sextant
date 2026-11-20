"""The value walk's cost on a strongly-connected region of values.

A ring of classes, each in its own file, passes one dict to the next class's methods, and
the last class calls back into the first. The positions form one strongly-connected region.
A walk that keeps no answer resting on a position still being worked out (`_Walk._guarded`)
recomputes per path inside a region. Measured 2026-11-20 on the code before the fix,
classes=8 and calls_per_method=3: more than 2_000_000 computes (the ceiling below stops
it after about 9 s; the true count is far larger). After the fix, which keeps such answers
for an asker that would work them out the same (`values.Kept`): 139 computes. The question
is a Flask route whose path is parameter `d` of the first class's method, so the walk goes
up through the ring's callers.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

import fixture_python
from fixture_python import FIXTURES
from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve import values
from sextant.application.resolve.pipeline import resolve
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_CEILING = 2_000_000
# The distributions `fixtures/orders-flask` locks. A Flask route is the question that sends the
# walk into the ring: its path is what the ring returns.
_LOCKED = {"flask": "3.1.3", "werkzeug": "3.1.9"}


@pytest.fixture(scope="module")
def libraries() -> tuple[LibraryRoot, ...]:
    root = FIXTURES / "orders-flask"
    fixture_python.synced(root, offline=True)
    (site,) = (root / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _LOCKED.items())


def make_ring_module(tmp_path: Path, classes: int, calls_per_method: int) -> Path:
    """A package of `classes` files. Class `k` has `calls_per_method` methods; each passes its
    dict to every method of class `k + 1` (the last wraps to the first), keeps it on `self`
    and returns what the next class returns."""
    package = tmp_path / "src" / "ring"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    for k in range(classes):
        following = (k + 1) % classes
        lines = [f"from ring.c{following} import C{following}"]
        lines += ["from ring.app import app"] * (k == 0)
        lines += ["", "", f"class C{k}:"]
        lines += [
            "    def __init__(self):",
            f"        self.next = C{following}()",
            "        self.data = {}",
            "",
        ]
        for i in range(calls_per_method):
            lines.append(f"    def m{i}(self, d):")
            lines.append("        self.data = d")
            if k == 0 and i == 0:
                lines.append("        app.route(d['p'])(self.m0)")
            for j in range(calls_per_method):
                lines.append(f"        d = self.next.m{j}(self.data)")
            lines += ["        return d", ""]
        (package / f"c{k}.py").write_text("\n".join(lines), encoding="utf-8")
    (package / "app.py").write_text(
        "from flask import Flask\n\napp = Flask(__name__)\n", encoding="utf-8"
    )
    (package / "main.py").write_text(
        "from ring.c0 import C0\n\nC0().m0({'p': '/x'})\n", encoding="utf-8"
    )
    return tmp_path / "src"


def count_computes(monkeypatch: pytest.MonkeyPatch) -> Callable[[], int]:
    """Count every position compute (`_Walk._guarded`); raise past the ceiling so a walk that
    explodes fails in seconds."""
    seen = [0]
    guarded = values._Walk._guarded

    def counted(self, position, trail, frames):  # type: ignore[no-untyped-def]
        seen[0] += 1
        if seen[0] > _CEILING:
            raise AssertionError(f"walk exceeded {_CEILING} computes")
        return guarded(self, position, trail, frames)

    monkeypatch.setattr(values._Walk, "_guarded", counted)
    return lambda: seen[0]


def analyze(source: Path, libraries: tuple[LibraryRoot, ...]) -> None:
    facts = source.parent / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="ring",
            coordinates="ring",
            version="1",
            classes_dir=source,
            out_dir=facts,
            dependency_archives=libraries,
        )
    )
    module = Document(
        document_id="module",
        relative_path="pyproject.toml",
        module_id="ring",
        language="python",
        sextant_version="0",
        fact_schema_version="0",
        scanner_id="module",
        content_hash="sha256:none",
        origin_entry="ring",
        origin_tier="module_output",
        redaction_set_hash="sha256:none",
    )
    write_fact_file(
        facts / "module.jsonl",
        module,
        [
            ModuleFact(
                document_id="module",
                module_id="ring",
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
    resolve(
        DuckDbWorkspace(source.parent / "ws.duckdb"),
        facts,
        YamlCatalogSource(catalogs_dir()),
        PythonScanner().capabilities(),
    )


def test_cycle_region_cost_is_bounded(tmp_path, monkeypatch, libraries):
    module = make_ring_module(tmp_path, classes=8, calls_per_method=3)
    computes = count_computes(monkeypatch)
    analyze(module, libraries)
    assert computes() < 50_000
