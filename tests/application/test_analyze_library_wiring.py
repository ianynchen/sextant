"""Task 6: opt-in library extraction wired into `analyze` — the scan loop, the
fact subtree it writes into, the origin every one of those documents carries,
and the two guarantees that make the feature safe to ship: a module with no
library configured produces byte-identical facts, and a module with one
produces the same bytes twice.

The REAL scanner runs here, over a REAL jar assembled from the fixture's own
compiled classes. A fake scanner would prove the loop calls something once per
library and nothing about what lands on disk, which is the whole question.

Imports `sextant.ingress.*` freely, for `test_analyze_descriptor_wiring.py`'s
stated reason."""

import json
import zipfile
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.detector import LibraryRoot, ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.stages.analyze import analyze
from sextant.cli.resources import extractor_jar
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
CLASSES = REPO / "fixtures" / "orders-service" / "target" / "classes"
COORDINATE = "com.example:orders-soap-client"


class _FakeDetector:
    def __init__(self, module: ModuleModel) -> None:
        self._module = module

    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(root=path, modules=(self._module,))


class _EmptyCatalogs:
    def load(self) -> list[Catalog]:
        return []


def _library_archive(target: Path) -> Path:
    """A real jar, from real bytecode: two classes out of the fixture's own
    output. Which classes is immaterial — what matters is that they are not the
    ones the module scan below reads, so a fact under `facts/lib/` could only
    have come from the archive."""
    names = ("com/acme/orders/contracts/OrderView.class", "com/acme/orders/OrderResult.class")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as archive:
        for name in names:
            archive.writestr(name, (CLASSES / name).read_bytes())
    return target


def _module(root: Path, libraries: tuple[LibraryRoot, ...]) -> ModuleModel:
    return ModuleModel(
        module_id="com.acme:orders-service",
        coordinates="com.acme/orders-service",
        version="1.0.0",
        root=root,
        kind="service",
        languages=frozenset({"java"}),
        source_roots=(),
        # The module's OWN output is a package of the fixture's classes that
        # the archive above does not hold, so the two halves of the fact tree
        # can never be confused for one another.
        output_dirs=(CLASSES / "com" / "acme" / "orders" / "clients",),
        library_roots=libraries,
    )


def _analyze(root: Path, libraries: tuple[LibraryRoot, ...]) -> Path:
    fact_root = root / "facts"
    workspace = DuckDbWorkspace(root / "ws.duckdb")
    try:
        analyze(
            path=root,
            workspace=workspace,
            detectors=[_FakeDetector(_module(root, libraries))],
            scanners=[AsmScanner(extractor_jar())],
            catalogs=_EmptyCatalogs(),
            fact_root=fact_root,
            progress=NullProgress(),
        )
    finally:
        workspace.close()
    return fact_root


def _tree(fact_root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(fact_root)): path.read_text(encoding="utf-8")
        for path in sorted(fact_root.rglob("*.jsonl"))
    }


@pytest.fixture
def library(tmp_path: Path) -> LibraryRoot:
    return LibraryRoot(
        coordinate=COORDINATE,
        version="1.0.0",
        archive=_library_archive(tmp_path / "repository" / "orders-soap-client-1.0.0.jar"),
    )


def test_a_library_is_scanned_into_its_own_subtree_and_every_document_names_it(
    tmp_path: Path, library: LibraryRoot
):
    """Three things at once, because they are one decision:

    * the library's facts land under `facts/lib/<groupId>/<artifactId>/`, its
      own subtree — a library is free to ship a class whose package matches one
      of the module's, and two documents competing for one fact-file target
      leave only the second on disk;
    * every document written there carries the COORDINATE as its `origin`
      (D00 §2), which is what survives into a bundle — the archive path does
      not, because it says nothing off the machine that resolved it;
    * a scanned symbol's identity carries the LIBRARY's coordinates and
      version, not this module's, so the graph never claims a jar's
      declaration as the module's own.
    """
    fact_root = _analyze(tmp_path / "run", (library,))
    subtree = fact_root / "lib" / "com.example" / "orders-soap-client"
    written = sorted(path.name for path in subtree.rglob("*.jsonl"))
    assert written == ["OrderResult.jsonl", "OrderView.jsonl"]

    document, symbol = (
        json.loads(line)
        for line in (subtree / "com" / "acme" / "orders" / "OrderResult.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[:2]
    )
    assert document["origin"] == COORDINATE
    assert document["module_id"] == "com.acme:orders-service"
    assert symbol["symbol"].startswith("sextant-jvm maven com.example/orders-soap-client 1.0.0 ")


def test_the_modules_own_facts_do_not_move_when_a_library_is_added(
    tmp_path: Path, library: LibraryRoot
):
    """The isolation pin, and the reason this feature can be opt-in at all.
    Turning library extraction on must add facts and change none: a module's
    own documents carry no `origin` KEY (not one spelled null), land in the
    same places, and hash the same. Anything else would re-extract every
    workspace in existence and make "did enabling this change my analysis?"
    unanswerable."""
    without = _tree(_analyze(tmp_path / "without", ()))
    with_library = _tree(_analyze(tmp_path / "with", (library,)))

    module_half = {path: text for path, text in with_library.items() if not path.startswith("lib/")}
    assert module_half == without
    assert all("origin" not in json.loads(text.splitlines()[0]) for text in without.values())
    # And the library half is genuinely there, so the equality above is not
    # passing because nothing was extracted.
    assert len(with_library) == len(without) + 2


def test_two_runs_over_the_same_module_and_library_write_the_same_bytes(
    tmp_path: Path, library: LibraryRoot
):
    """NFR-1, extended over the new subtree. A jar is the one input whose
    natural iteration order is the archiver's rather than the filesystem's, so
    determinism here is a claim about the scan and not only about the walk."""
    assert _tree(_analyze(tmp_path / "one", (library,))) == _tree(
        _analyze(tmp_path / "two", (library,))
    )


def test_a_library_whose_archive_holds_no_class_is_named_rather_than_silently_empty(
    tmp_path: Path,
):
    """The loudness rule, reaching the stage that would otherwise swallow it: a
    library that extracts nothing must be distinguishable from one that was
    never configured, and `uncovered` is what carries that out of `analyze`
    into metadata.json and the rendered gaps list (FR-17)."""
    empty = tmp_path / "repository" / "empty-1.0.0.jar"
    empty.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    library = LibraryRoot(coordinate="com.example:empty", version="1.0.0", archive=empty)

    fact_root = tmp_path / "run" / "facts"
    workspace = DuckDbWorkspace(tmp_path / "run" / "ws.duckdb")
    try:
        result = analyze(
            path=tmp_path / "run",
            workspace=workspace,
            detectors=[_FakeDetector(_module(tmp_path / "run", (library,)))],
            scanners=[AsmScanner(extractor_jar())],
            catalogs=_EmptyCatalogs(),
            fact_root=fact_root,
            progress=NullProgress(),
        )
    finally:
        workspace.close()

    assert result.uncovered == (f"{empty}: no class files found",)
