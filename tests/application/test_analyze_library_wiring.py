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
from sextant.application.stages.analyze import AnalyzeResult, analyze
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


def _analyzed(root: Path, libraries: tuple[LibraryRoot, ...]) -> AnalyzeResult:
    workspace = DuckDbWorkspace(root / "ws.duckdb")
    try:
        return analyze(
            path=root,
            workspace=workspace,
            detectors=[_FakeDetector(_module(root, libraries))],
            scanners=[AsmScanner(extractor_jar())],
            catalogs=_EmptyCatalogs(),
            fact_root=root / "facts",
            progress=NullProgress(),
        )
    finally:
        workspace.close()


def _analyze(root: Path, libraries: tuple[LibraryRoot, ...]) -> Path:
    _analyzed(root, libraries)
    return root / "facts"


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
      not, because it says nothing off the machine that resolved it — and its
      `origin_tier` reads `dependency`, because a class this module did not
      build is not `module_output` and saying so would be a claim known to be
      false;
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
    assert document["origin_tier"] == "dependency"
    assert document["module_id"] == "com.acme:orders-service"
    assert symbol["symbol"].startswith("sextant-jvm maven com.example/orders-soap-client 1.0.0 ")

    # And the module's own half is untouched by any of it — the tier moves for
    # the library and only for the library.
    own = [
        json.loads(text.splitlines()[0])
        for path, text in _tree(fact_root).items()
        if not path.startswith("lib/")
    ]
    assert own
    assert all(record["origin_tier"] == "module_output" for record in own)
    assert not any("origin" in record for record in own)


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


def test_a_library_whose_archive_holds_no_class_is_named_by_its_coordinate(tmp_path: Path):
    """The loudness rule, reaching the stage that would otherwise swallow it: a
    library that extracts nothing must be distinguishable from one that was
    never configured, and `uncovered` is what carries that out of `analyze`
    into metadata.json and the rendered gaps list (FR-17).

    Named by the COORDINATE, not the archive path. This entry is read by a
    person, and it travels — into metadata.json and into a published bundle —
    where an absolute path under someone's home directory identifies nothing at
    all."""
    empty = tmp_path / "repository" / "empty-1.0.0.jar"
    empty.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    library = LibraryRoot(coordinate="com.example:empty", version="1.0.0", archive=empty)

    result = _analyzed(tmp_path / "run", (library,))

    assert result.uncovered == ("com.example:empty: no class files found",)
    assert str(empty) not in result.uncovered[0]


def test_opting_a_library_out_retracts_its_rows_from_the_same_workspace(
    tmp_path: Path, library: LibraryRoot
):
    """The retraction pin, and the reason the whole `lib/` subtree is discarded
    at the start of every scan.

    A fact file is written WHOLE, so a library still opted in overwrites itself
    — but one removed from `.sextant.yml` overwrites nothing, and the resolve
    reads the whole tree. Re-analyzing the SAME workspace after opting out would
    otherwise read the previous run's library facts straight back and keep
    deriving from a library nobody asked for any more. An opt-in that cannot be
    taken back is not a decision the reader controls."""
    root = tmp_path / "workspace"
    with_library = _analyzed(root, (library,))
    assert (root / "facts" / "lib").is_dir()
    library_documents = with_library.report.coverage["documents"]

    without = _analyzed(root, ())

    assert not (root / "facts" / "lib").exists()
    assert without.report.coverage["documents"] == library_documents - 2
    assert not any(
        json.loads(text.splitlines()[0]).get("origin") for text in _tree(root / "facts").values()
    )
    # And the module's own half came back intact rather than being collateral:
    # the discard runs BEFORE the module's scan, so anything it could reach is
    # rewritten a line later.
    assert _tree(root / "facts")


def test_a_library_that_could_not_be_scanned_names_no_absolute_path(
    tmp_path: Path, library: LibraryRoot
):
    """`libraries_not_scanned` travels the same road every other FR-17 list
    does — metadata.json, the rendered gaps, a published bundle — so D00 §2's
    rule holds for it too: a path under someone's home directory identifies
    nothing off the machine that wrote it.

    The reason here comes from the SCANNER, not from this stage, so this is the
    pin that says the whole channel is clean and not merely the strings
    `analyze` composes itself. It is deliberately the coordinate that must
    appear and the archive path that must not."""
    missing = LibraryRoot(
        coordinate="com.example:gone",
        version="1.0.0",
        archive=tmp_path / "repository" / "gone-1.0.0.jar",
    )

    result = _analyzed(tmp_path / "run", (missing,))

    [reported] = result.libraries_not_scanned
    assert reported.startswith("com.example:gone: ")
    assert str(tmp_path) not in reported


def test_a_library_that_fails_mid_archive_leaves_no_partial_subtree(
    tmp_path: Path, library: LibraryRoot
):
    """A backend writes each document as it reaches it, so a failure on the
    SECOND entry of an archive leaves the first one's facts on disk. A fraction
    of a library is indistinguishable, once loaded, from all of a smaller one —
    the rows it derives look complete and are not. Discarding that coordinate's
    subtree is what makes the failure total rather than partial.

    The corrupt entry is real: valid zip framing around bytes that are not a
    class file, which is what gets the extractor past `names()` and into the
    walk before it fails."""
    broken = tmp_path / "repository" / "broken-1.0.0.jar"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr(
            "com/acme/orders/OrderResult.class",
            (CLASSES / "com/acme/orders/OrderResult.class").read_bytes(),
        )
        archive.writestr("com/acme/orders/Zzz.class", b"not bytecode at all")
    corrupt = LibraryRoot(coordinate="com.example:broken", version="1.0.0", archive=broken)

    result = _analyzed(tmp_path / "run", (corrupt,))

    assert not (tmp_path / "run" / "facts" / "lib" / "com.example" / "broken").exists()
    [reported] = result.libraries_not_scanned
    assert reported.startswith("com.example:broken: ")


def test_a_library_that_cannot_be_scanned_does_not_take_the_module_with_it(
    tmp_path: Path, library: LibraryRoot
):
    """A dependency nobody can open does not make the module's own facts wrong,
    and they are already on disk by the time the library is reached. So a
    library scan that fails is a gap about THAT library — recorded, named, and
    survived — while the module's own scan failing stays what it always was:
    the analysis failing.

    The good library beside it still lands, which is the half that says the
    loop CONTINUES rather than merely not crashing."""
    missing = LibraryRoot(
        coordinate="com.example:gone",
        version="1.0.0",
        archive=tmp_path / "repository" / "gone-1.0.0.jar",
    )

    result = _analyzed(tmp_path / "run", (missing, library))

    assert result.report.coverage["documents"] > 0
    [reported] = result.libraries_not_scanned
    assert reported.startswith("com.example:gone: ")
    assert (tmp_path / "run" / "facts" / "lib" / "com.example" / "orders-soap-client").is_dir()
