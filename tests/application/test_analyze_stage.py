"""Task 1 (2M): the two pieces of detect-side plumbing `analyze` itself owns —
`allow_resolve` threaded to whichever detector is selected, and the detector's
own `RepositoryModel.notes` carried out unchanged as `AnalyzeResult.notes`.
Both are pass-through: this stage neither computes an `allow_resolve` value
nor edits a note, so the pins here are about the wiring, not the content."""

import json
from dataclasses import replace
from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.detector import ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.stages.analyze import analyze
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.resources import extractor_jar
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
CLASSES = REPO / "fixtures" / "orders-service" / "target" / "classes"


class _RecordingDetector:
    """Records every `allow_resolve` value it was called with, and returns a
    `RepositoryModel` carrying whatever notes the test hands it — the two
    things this stage must pass through untouched."""

    def __init__(self, module: ModuleModel, notes: tuple[str, ...] = ()) -> None:
        self._module = module
        self._notes = notes
        self.calls: list[bool] = []

    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        self.calls.append(allow_resolve)
        return RepositoryModel(root=path, modules=(self._module,), notes=self._notes)


class _EmptyCatalogs:
    def load(self) -> list[Catalog]:
        return []


def _module(root: Path) -> ModuleModel:
    return ModuleModel(
        module_id="com.acme:orders-service",
        coordinates="com.acme/orders-service",
        version="1.0.0",
        root=root,
        kind="service",
        languages=frozenset({"java"}),
        source_roots=(),
        # A real, already-compiled output dir — the scan below is the real
        # scanner, the same reason `test_analyze_library_wiring.py` uses one.
        output_dirs=(CLASSES / "com" / "acme" / "orders" / "clients",),
    )


def _analyzed(root: Path, detector: _RecordingDetector, allow_resolve: bool):
    workspace = DuckDbWorkspace(root / "ws.duckdb")
    try:
        return analyze(
            path=root,
            workspace=workspace,
            detectors=[detector],
            scanners=[AsmScanner(extractor_jar())],
            catalogs=_EmptyCatalogs(),
            fact_root=root / "facts",
            progress=NullProgress(),
            allow_resolve=allow_resolve,
        )
    finally:
        workspace.close()


def test_allow_resolve_defaults_to_false_and_still_reaches_the_detector(tmp_path: Path):
    """Every existing caller of `analyze` passes no `allow_resolve` at all
    (the default), and the detector must see that as an explicit `False`
    rather than nothing — an offline-only build must never silently gain the
    online retry."""
    detector = _RecordingDetector(_module(tmp_path))
    _analyzed(tmp_path, detector, allow_resolve=False)
    assert detector.calls == [False]


def test_allow_resolve_true_reaches_the_detector(tmp_path: Path):
    """The missing plumbing this task closes (2M design §1 network-posture
    bullet): the port parameter already existed and nothing passed it."""
    detector = _RecordingDetector(_module(tmp_path))
    _analyzed(tmp_path, detector, allow_resolve=True)
    assert detector.calls == [True]


def test_the_detectors_notes_are_carried_out_as_the_analyze_results_notes(tmp_path: Path):
    detector = _RecordingDetector(
        _module(tmp_path), notes=("gradle build files present; maven selected",)
    )
    result = _analyzed(tmp_path, detector, allow_resolve=False)
    assert result.notes == ("gradle build files present; maven selected",)


def test_no_notes_from_the_detector_is_an_empty_tuple_not_a_missing_field(tmp_path: Path):
    detector = _RecordingDetector(_module(tmp_path))
    result = _analyzed(tmp_path, detector, allow_resolve=False)
    assert result.notes == ()


def test_the_detectors_module_conclusions_are_written_as_a_fact(tmp_path: Path):
    """D00 §5's `module` kind, constructed for the first time (2O design §2a,
    ruling R9). Three later components need the detector's conclusions and
    never see the detector, and a stage resumed from disk never runs one — so
    they travel as facts, and this is the fact a dependency-gated catalog
    reads.
    """
    detector = _RecordingDetector(
        replace(
            _module(tmp_path),
            dependency_coordinates=("org.springframework.data:spring-data-rest-core",),
        )
    )
    _analyzed(tmp_path, detector, False)

    document, fact = (
        json.loads(line)
        for line in (tmp_path / "facts" / "module.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert fact["kind"] == "module"
    assert fact["module_id"] == "com.acme:orders-service"
    assert fact["dependency_coordinates"] == ["org.springframework.data:spring-data-rest-core"]
    assert document["document_id"] == fact["document_id"]
    # Portable, not a path: this document was read from no classpath entry,
    # and a machine path would make two runs of one module at two checkout
    # paths write different bytes (D00 §2, NFR-1).
    assert document["origin_entry"] == "com.acme/orders-service"


def test_the_module_fact_is_rewritten_whole_on_every_run(tmp_path: Path):
    """A fact file is written whole, never appended to — so a second analyze
    into the same workspace leaves one module fact, not two, and a dependency
    dropped from the build disappears from the answer."""
    first = _RecordingDetector(
        replace(_module(tmp_path), dependency_coordinates=("com.example:gone",))
    )
    _analyzed(tmp_path, first, False)
    _analyzed(tmp_path, _RecordingDetector(_module(tmp_path)), False)

    lines = (tmp_path / "facts" / "module.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["dependency_coordinates"] == []


def test_the_module_fact_carries_the_resolved_versions_beside_the_coordinates(tmp_path: Path):
    """F1. The coordinates say WHAT the module builds against; the versions say
    WHICH RELEASE, and without them no catalog rule can ever be scoped to the
    versions it was measured against. Both travel on the one fact, because a
    version with no coordinate beside it identifies nothing."""
    detector = _RecordingDetector(
        replace(
            _module(tmp_path),
            dependency_coordinates=("org.springframework:spring-web",),
            dependency_versions={"org.springframework:spring-web": "6.1.6"},
        )
    )
    _analyzed(tmp_path, detector, False)

    _, fact = (
        json.loads(line)
        for line in (tmp_path / "facts" / "module.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert fact["dependency_versions"] == {"org.springframework:spring-web": "6.1.6"}


def test_a_run_that_resolved_a_version_the_last_one_could_not_writes_a_new_content_hash(
    tmp_path: Path,
):
    """The versions are part of the identity this document records. A parent
    pom that was missing and is now in the local repository changes what the
    analysis knows about the module, and a `content_hash` that ignored it would
    tell every downstream reader nothing had changed."""
    unresolved = _RecordingDetector(
        replace(_module(tmp_path), dependency_coordinates=("org.springframework:spring-web",))
    )
    _analyzed(tmp_path, unresolved, False)
    first = json.loads(
        (tmp_path / "facts" / "module.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    resolved = _RecordingDetector(
        replace(
            _module(tmp_path),
            dependency_coordinates=("org.springframework:spring-web",),
            dependency_versions={"org.springframework:spring-web": "6.1.6"},
        )
    )
    _analyzed(tmp_path, resolved, False)
    second = json.loads(
        (tmp_path / "facts" / "module.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )

    assert first["content_hash"] != second["content_hash"]
