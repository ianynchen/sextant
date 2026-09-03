"""Task 1 (2M): the two pieces of detect-side plumbing `analyze` itself owns —
`allow_resolve` threaded to whichever detector is selected, and the detector's
own `RepositoryModel.notes` carried out unchanged as `AnalyzeResult.notes`.
Both are pass-through: this stage neither computes an `allow_resolve` value
nor edits a note, so the pins here are about the wiring, not the content."""

from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.detector import ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.stages.analyze import analyze
from sextant.cli.resources import extractor_jar
from sextant.ingress.extract.jvm.scanner import AsmScanner
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
