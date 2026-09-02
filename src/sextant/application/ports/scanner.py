from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
    scanner_version: str
    uncovered: tuple[str, ...] = ()


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
