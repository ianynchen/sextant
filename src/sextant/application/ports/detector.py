"""The Detector port (M02). Works out what a repository contains, before
anything reads code. Implementations are keyed by build system, never by
language — a module records the languages present."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sextant.application.ports.selection import NoAdapterError


@dataclass(frozen=True)
class ModuleModel:
    module_id: str
    coordinates: str
    version: str
    root: Path
    kind: str
    languages: frozenset[str]
    source_roots: tuple[Path, ...]
    output_dirs: tuple[Path, ...]
    # Where the ArtifactReader port (M03's second port) looks for config
    # files — `src/main/resources` for Maven. Defaulted so every existing
    # construction site keeps working; a build system that names none
    # reports the empty tuple, never a guess.
    resource_roots: tuple[Path, ...] = ()


@dataclass(frozen=True)
class RepositoryModel:
    root: Path
    modules: tuple[ModuleModel, ...] = field(default_factory=tuple)


class Detector(Protocol):
    """Keyed by build system, never by language (M02)."""

    def accepts(self, path: Path) -> bool: ...
    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel: ...


def select_detector(detectors: Sequence[Detector], path: Path) -> Detector:
    """The first detector that recognises this repository.

    First rather than best: detectors are keyed by build system, and where a
    repository carries two build files the registry's order is the deliberate
    statement of which one is authoritative. There is no rank to appeal to.
    """
    for detector in detectors:
        if detector.accepts(path):
            return detector
    raise NoAdapterError(f"no detector recognises {path} as a repository it can read")
