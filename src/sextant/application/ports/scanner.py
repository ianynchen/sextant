from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ScanRequest:
    module_id: str
    coordinates: str
    version: str
    classes_dir: Path
    out_dir: Path


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
