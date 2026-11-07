from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.selection import NoAdapterError
from sextant.domain.ignorefile import IgnoreRules


@dataclass(frozen=True)
class ReuseRecord:
    """What a scan keeps about one document it wrote, so that a later scan into the same
    folder can keep the document instead of reading its source again (OI-325; D00 §2: "the
    source file is the unit of incremental reuse"). Stored by the workspace between runs and
    handed back unread: what it means is the backend's.

    `target` is the fact file, relative to the scan's `out_dir`. `key` is the backend's
    digest of every input the document's facts were read from, the source file's bytes and
    the document record's stamps among them: a document is kept only where a fresh read
    would write the same bytes. `detail` is the backend's own text: what it needs to check
    the key again, and what the document added to the scan's report."""

    target: str
    key: str
    detail: str


@dataclass(frozen=True)
class ScanRequest:
    module_id: str
    coordinates: str
    version: str
    # A directory tree of compiled classes, or a single library archive — the
    # scanner backend says which forms it reads. Named `classes_dir` since
    # Phase 1, when a directory was the only form.
    classes_dir: Path
    out_dir: Path
    # The library this request scans, as its coordinate — recorded on every
    # document the scan writes (D00 §2's `origin`). NULL for the module's own
    # output, which is what a scan has always been, so an unset origin leaves
    # a document exactly as it was.
    origin: str | None = None
    # The resolved dependency jars (`ModuleModel.dependency_archives`), for the HEADER read
    # of every type this scan's classes refer to and did not compile (D00 §5
    # `type_header`). Empty for a library scan and wherever nothing resolved, and then the
    # scan is byte-for-byte what it was before the read existed.
    dependency_archives: "tuple[LibraryRoot, ...]" = ()
    # Further classes directories of the SAME module, read in the same scan as
    # `classes_dir` (OI-273 fix round 1): Gradle reports one per compiling plugin, and
    # one scan is what lets the header read see every class's references and count
    # every directory's own types as the module's. Each document still records the
    # directory it was read from.
    more_classes_dirs: tuple[Path, ...] = ()
    # `.sextantignore` and its built-in layer (D04 §3), for a backend that walks the
    # repository's own files: a file they exclude is not read. A class-file scan reads build
    # output and library archives, which the rules do not govern (2K design §2). None reads
    # every file, as before.
    ignore: IgnoreRules | None = None
    # The installed environment the module's libraries are read from
    # (`ModuleModel.environment`, a Python module's): its Python decides the standard
    # library, and a library re-export is followed into any distribution it holds. None
    # for a JVM module and wherever no environment was found.
    environment: Path | None = None
    # What the previous scan into `out_dir` recorded about each document it wrote or kept
    # (`ScanReport.records`). Empty reads every file, as a scan always did; a backend that
    # keeps nothing ignores it.
    previous: tuple[ReuseRecord, ...] = ()


class ScanError(RuntimeError):
    """A scan that could not be completed — an unreadable input, or a backend
    that failed partway through one.

    Typed rather than a bare `RuntimeError` because one caller branches on it:
    a LIBRARY scan that fails is a gap to record about that library, while the
    module's own scan failing is the analysis failing. A caller that cannot tell
    those apart has to choose between crashing on a corrupt jar and swallowing a
    broken module scan."""


@dataclass(frozen=True)
class ScanReport:
    documents: int
    facts: int
    scanner_id: str
    # `group:artifact:version` per THIRD-PARTY library the scanner ran, in the
    # order the producing build sorted them (NFR-1). Not a version of the
    # scanner: a facility Sextant ships moves with `sextant_version` and has
    # nothing of its own to record, while a library it depends on moves on
    # someone else's release cycle and is the only version here a consumer can
    # act on. Empty for a facility that uses none. Which libraries those are is
    # the backend's business and is named only inside its own adapter
    # (ARCHITECTURE §10).
    scanner_libraries: tuple[str, ...] = ()
    # What the jar says it can read, reported back on every scan. The same list
    # `--capabilities` answers, so a workspace's record and the set its catalogs
    # were gated on cannot disagree — and it is READ (`AsmScanner.scan`), not
    # merely emitted, because a field nothing consumes is the defect this
    # project keeps finding.
    capabilities: tuple[str, ...] = ()
    uncovered: tuple[str, ...] = ()
    # One record per document this scan wrote or kept, for the next scan into the same
    # folder (`ScanRequest.previous`). Empty for a backend that keeps nothing, and then the
    # next scan reads every file. `reused` is how many of `documents` were kept.
    records: tuple[ReuseRecord, ...] = ()
    reused: int = 0


@dataclass(frozen=True)
class ScannerProvenance:
    """One facility that produced documents in a workspace.

    A version exists only where the thing can move INDEPENDENTLY of Sextant.
    `sextant-config-reader` and `sextant-detector` ship inside the wheel, so
    their version is `sextant_version` and a separate copy of it carried no
    information — it was two more hand-maintained literals that had never once
    differed from the tool's own. A backend that runs THIRD-PARTY libraries in a
    subprocess is different: those can move without Sextant moving at all, so
    they are the versions worth recording, and each backend reports its own.
    """

    id: str
    libraries: tuple[str, ...] = ()


class Scanner(Protocol):
    """Implementations are keyed by backend, never by language (M03)."""

    def accepts(self, languages: set[str]) -> bool: ...
    def capabilities(self) -> set[str]: ...
    def rank(self) -> int: ...
    def scan(self, request: ScanRequest) -> ScanReport: ...


def select_scanner(scanners: Sequence[Scanner], languages: frozenset[str]) -> Scanner:
    """The highest-ranked scanner accepting these languages.

    The rule lives beside the Protocol that declares `accepts` and `rank`,
    rather than in each composition root, because it is what those two methods
    are *for* — a second root that combined them differently would make the
    port mean two things. Ties keep registry order, so the result depends only
    on the registry and not on iteration (NFR-1).
    """
    accepting = [scanner for scanner in scanners if scanner.accepts(set(languages))]
    if not accepting:
        raise NoAdapterError(
            f"no scanner accepts {', '.join(sorted(languages)) or 'a module with no language'}"
        )
    return max(accepting, key=lambda scanner: scanner.rank())
