from pathlib import Path

import pytest

from sextant.application.ports.detector import Detector, RepositoryModel, select_detector
from sextant.application.ports.scanner import ScanReport, ScanRequest, select_scanner
from sextant.application.ports.selection import NoAdapterError


class _Detector:
    def __init__(self, recognises: bool) -> None:
        self._recognises = recognises

    def accepts(self, path: Path) -> bool:
        return self._recognises

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(root=path)


class _Scanner:
    def __init__(self, languages: set[str], rank: int) -> None:
        self._languages = languages
        self._rank = rank

    def accepts(self, languages: set[str]) -> bool:
        return bool(languages & self._languages)

    def capabilities(self) -> set[str]:
        return set()

    def rank(self) -> int:
        return self._rank

    def scan(self, request: ScanRequest) -> ScanReport:
        raise AssertionError("not scanned in a selection test")


def test_select_detector_takes_the_first_that_recognises_the_repository():
    """First rather than best: a repository carrying two build files is a real
    case, and registry order is the deliberate statement of which one wins."""
    wanted = _Detector(recognises=True)
    detectors: list[Detector] = [_Detector(recognises=False), wanted, _Detector(True)]

    assert select_detector(detectors, Path("/repo")) is wanted


def test_select_detector_names_the_path_when_nothing_recognises_it():
    with pytest.raises(NoAdapterError) as raised:
        select_detector([_Detector(recognises=False)], Path("/repo"))

    assert "/repo" in str(raised.value)


def test_select_scanner_takes_the_highest_ranked_of_those_accepting():
    best = _Scanner({"java"}, rank=10)
    scanners = [_Scanner({"java"}, rank=1), best, _Scanner({"python"}, rank=99)]

    assert select_scanner(scanners, frozenset({"java"})) is best


def test_select_scanner_keeps_registry_order_when_ranks_tie():
    """A tie must not resolve by iteration accident: the same registry has to
    give the same scanner on every run (NFR-1)."""
    first = _Scanner({"java"}, rank=5)
    scanners = [first, _Scanner({"java"}, rank=5)]

    assert select_scanner(scanners, frozenset({"java"})) is first


def test_select_scanner_names_the_languages_when_none_accepts():
    with pytest.raises(NoAdapterError) as raised:
        select_scanner([_Scanner({"java"}, rank=1)], frozenset({"rust"}))

    assert "rust" in str(raised.value)
