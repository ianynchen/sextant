from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.selection import NoAdapterError


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
