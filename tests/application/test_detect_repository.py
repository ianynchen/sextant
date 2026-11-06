"""`detect_repository`: every detector that recognises a repository is run, and the
modules are merged. Stub detectors stand in for Maven and Gradle; no build tool runs."""

import json
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from sextant import api
from sextant.application.ports.detector import (
    ModuleModel,
    NoModulesFound,
    RepositoryModel,
    detect_repository,
)
from sextant.application.ports.selection import NoAdapterError
from sextant.ingress.detect.python import PythonDetector


def _module(root: Path, module_id: str, kind: str = "maven") -> ModuleModel:
    return ModuleModel(
        module_id=module_id,
        coordinates=module_id,
        version="1",
        root=root,
        kind=kind,
        languages=frozenset({"java"}),
        source_roots=(),
        output_dirs=(),
    )


class _StubBuild:
    """A detector that accepts a repository with `marker` in its root folder and
    reports the modules it was given."""

    def __init__(self, marker: str, modules: list[ModuleModel], notes=(), multi=False) -> None:
        self._marker = marker
        self._modules = modules
        self._notes = tuple(notes)
        self._multi = multi

    def accepts(self, path: Path) -> bool:
        return (path / self._marker).is_file()

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(
            root=path, modules=tuple(self._modules), notes=self._notes, multi_module=self._multi
        )


class _StubRefusing:
    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        raise NoModulesFound("no module here")


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_repository_with_a_maven_build_and_a_python_service_yields_both(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "svc" / "pyproject.toml", '[project]\nname = "svc"\nversion = "1"\n')
    _write(tmp_path / "svc" / "app.py", "x = 1\n")
    maven = _StubBuild("pom.xml", [_module(tmp_path, "com.acme:app")], notes=["maven note"])

    model = detect_repository([maven, PythonDetector()], tmp_path)

    assert [m.module_id for m in model.modules] == ["com.acme:app", "svc"]
    assert model.modules[0].kind == "maven"
    assert model.multi_module is True
    assert "maven note" in model.notes


def test_a_python_only_repository_is_unchanged(tmp_path: Path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "solo"\nversion = "1"\n')
    _write(tmp_path / "app.py", "x = 1\n")
    maven = _StubBuild("pom.xml", [])

    merged = detect_repository([maven, PythonDetector()], tmp_path)

    assert merged == PythonDetector().detect(tmp_path)
    assert merged.multi_module is False


def test_two_modules_with_one_id_are_both_kept_with_their_path(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "gradle.marker")
    other = _StubBuild("gradle.marker", [_module(tmp_path / "lib", "shared", "gradle")])
    first = _StubBuild("pom.xml", [_module(tmp_path, "shared"), _module(tmp_path, "unique")])
    # One case from two detectors.
    model = detect_repository([first, other], tmp_path)
    ids = sorted(m.module_id for m in model.modules)
    assert ids == ["shared@.", "shared@lib", "unique"]
    assert {m.coordinates for m in model.modules} == {"shared", "unique"}

    # One case from the Python detector alone.
    for folder in ("sdk/python", "sdk/generator/python/template"):
        _write(tmp_path / folder / "pyproject.toml", '[project]\nname = "polar-sdk"\n')
        _write(tmp_path / folder / "m.py", "x = 1\n")
    py = detect_repository([PythonDetector()], tmp_path)
    assert sorted(m.module_id for m in py.modules) == [
        "polar-sdk@sdk/generator/python/template",
        "polar-sdk@sdk/python",
    ]
    assert all(m.coordinates == "polar-sdk" for m in py.modules)


def test_a_detector_that_accepts_but_finds_no_module_adds_nothing_when_another_did(
    tmp_path: Path,
):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "docs" / "requirements.txt", "sphinx\n")
    maven = _StubBuild("pom.xml", [_module(tmp_path, "com.acme:app")])

    model = detect_repository([maven, PythonDetector()], tmp_path)

    assert [m.module_id for m in model.modules] == ["com.acme:app"]
    assert model.multi_module is False
    assert any("docs/requirements.txt" in note for note in model.notes)


def test_a_refusal_stays_a_refusal_when_no_detector_found_a_module(tmp_path: Path):
    with pytest.raises(NoModulesFound, match="no module here"):
        detect_repository([_StubRefusing()], tmp_path)


def test_a_repository_no_detector_recognises_is_refused(tmp_path: Path):
    with pytest.raises(NoAdapterError):
        detect_repository([_StubBuild("pom.xml", [])], tmp_path)


def test_a_reactor_naming_one_module_stays_multi_module(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "svc" / "pyproject.toml", '[project]\nname = "svc"\n')
    _write(tmp_path / "svc" / "app.py")
    maven = _StubBuild("pom.xml", [_module(tmp_path / "child", "child")], multi=True)

    assert detect_repository([maven], tmp_path).multi_module is True


class _StubFailing:
    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        raise ValueError("pyproject.toml is not a readable build file: bad toml")


def _root_python_project(root: Path) -> None:
    _write(root / "requirements.txt", "requests\n")
    _write(root / "scripts" / "deploy.py", "x = 1\n")


def test_modules_in_one_folder_each_get_a_results_name(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _root_python_project(tmp_path)
    maven = _StubBuild("pom.xml", [_module(tmp_path, "com.acme:app")])

    model = detect_repository([maven, PythonDetector()], tmp_path)

    assert [m.root for m in model.modules] == [tmp_path, tmp_path]
    names = [m.results_name for m in model.modules]
    assert None not in names and len(set(names)) == 2
    assert all(re.fullmatch(r"[A-Za-z0-9._-]+", name) for name in names)


def test_a_module_with_a_folder_of_its_own_keeps_no_results_name(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "svc" / "pyproject.toml", '[project]\nname = "svc"\n')
    _write(tmp_path / "svc" / "app.py")
    maven = _StubBuild("pom.xml", [_module(tmp_path, "com.acme:app")])

    model = detect_repository([maven, PythonDetector()], tmp_path)

    assert [m.results_name for m in model.modules] == [None, None]


def test_a_skipped_module_leaves_the_results_of_the_one_beside_it(tmp_path: Path, monkeypatch):
    _write(tmp_path / "pom.xml")
    _root_python_project(tmp_path)
    skipped = replace(_module(tmp_path, "com.acme:app"), skip_reason="nothing to scan")
    model = detect_repository([_StubBuild("pom.xml", [skipped]), PythonDetector()], tmp_path)
    python_module = next(m for m in model.modules if m.kind != "maven")
    jvm_module = next(m for m in model.modules if m.kind == "maven")
    kept = api._workspace_dir_of(tmp_path, None, python_module.results_name)
    gone = api._workspace_dir_of(tmp_path, None, jvm_module.results_name)
    for folder in (kept, gone):
        _write(folder / "workspace.duckdb", "results")
    stage = SimpleNamespace(report=SimpleNamespace(endpoints=[], value_resolutions=0))
    monkeypatch.setattr(api, "_run_analyze", lambda *args, **kwargs: stage)
    monkeypatch.setattr(api, "_skip_reason", lambda module: module.skip_reason)

    api._analyze_reactor(tmp_path, model, False, None, None)

    assert (kept / "workspace.duckdb").is_file()
    assert not (gone / "workspace.duckdb").exists()
    rows = json.loads((tmp_path / ".sextant" / "modules.json").read_text())["modules"]
    assert len({row["results"] for row in rows}) == 2


def test_a_jvm_repository_with_a_python_project_is_multi_module(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "tools" / "pyproject.toml", '[project]\nname = "tools"\n')
    _write(tmp_path / "tools" / "run.py")
    maven = _StubBuild("pom.xml", [_module(tmp_path, "com.acme:app")])

    model = detect_repository([maven, PythonDetector()], tmp_path)

    assert len(model.modules) == 2
    assert model.multi_module is True


def test_a_detector_failure_stops_detection_even_when_another_found_modules(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "tools" / "pyproject.toml", '[project]\nname = "tools"\n')
    _write(tmp_path / "tools" / "run.py")

    class _MavenFailing(_StubBuild):
        def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
            raise ValueError("pom.xml is not well formed")

    with pytest.raises(ValueError, match="not well formed"):
        detect_repository([_MavenFailing("pom.xml", []), PythonDetector()], tmp_path)


def test_a_failure_is_a_refusal_when_no_detector_found_a_module(tmp_path: Path):
    with pytest.raises(ValueError, match="bad toml"):
        detect_repository([_StubFailing()], tmp_path)


def test_a_colliding_module_outside_the_root_is_named_by_its_absolute_path(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "gradle.marker")
    outside = tmp_path.parent / "elsewhere"
    one = _StubBuild("pom.xml", [_module(tmp_path, "shared")])
    two = _StubBuild("gradle.marker", [_module(outside, "shared", "gradle")])

    model = detect_repository([one, two], tmp_path)

    assert sorted(m.module_id for m in model.modules) == ["shared@.", f"shared@{outside}"]


def test_ids_that_stay_equal_are_refused_and_every_one_is_named(tmp_path: Path):
    _write(tmp_path / "pom.xml")
    _write(tmp_path / "gradle.marker")
    one = _StubBuild("pom.xml", [_module(tmp_path, "a"), _module(tmp_path, "b")])
    two = _StubBuild("gradle.marker", [_module(tmp_path, "a", "gradle"), _module(tmp_path, "b")])

    with pytest.raises(ValueError, match=r"a@\..*b@\.|b@\..*a@\."):
        detect_repository([one, two], tmp_path)
