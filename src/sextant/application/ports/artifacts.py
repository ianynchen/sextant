"""The ArtifactReader port (M03's dormant second port). Mirrors Scanner's
shape (`accepts`, one entry point that returns facts) because it is the same
kind of seam: implementations are keyed by file format, never by framework —
a reader reads the neutral shape of a config file and never layers, resolves
a placeholder, or interprets a profile (D00 §5c). That is M04 pass 2's job,
reading catalog data a reader knows nothing about."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sextant.domain.facts import Document, Fact


@dataclass(frozen=True)
class ReadRequest:
    module_id: str
    version: str
    # Every file this reader owns, already partitioned by `accepts` and in
    # declaration order (NFR-1: files sorted by relative path) — a reader
    # never lists a directory itself.
    files: tuple[Path, ...]
    # The resource root `files` were found under. `relative_path` on each
    # returned Document is relative to this, the same convention a scanner's
    # own documents keep relative to their classes directory.
    root: Path


class ArtifactReader(Protocol):
    """Keyed by file kind (extension), never by framework. Readers never
    compete: `accepts` partitions file kinds so at most one registered
    reader claims any given file (M03)."""

    def accepts(self, file_kind: str) -> bool: ...
    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]: ...


def group_files_by_reader(
    files: Sequence[Path], readers: Sequence[ArtifactReader]
) -> list[tuple[ArtifactReader, tuple[Path, ...]]]:
    """Partitions `files` among `readers`, in registry order: the first
    reader whose `accepts` claims a file's extension owns it. A file no
    reader claims is silently dropped from every group — same
    all-formats-not-all-files spirit as `select_scanner`'s registry, except
    partial rather than total, because a resource root mixes config formats
    with everything else (`.txt`, static assets) a config reader has no
    stake in.

    Order is preserved twice over: readers keep registry order, and each
    reader's own files keep the order `files` arrived in — sorted by
    relative path by the caller (NFR-1)."""
    grouped: dict[int, list[Path]] = {}
    for file in files:
        kind = file.suffix.removeprefix(".").lower()
        for index, reader in enumerate(readers):
            if reader.accepts(kind):
                grouped.setdefault(index, []).append(file)
                break
    return [(readers[index], tuple(grouped[index])) for index in sorted(grouped)]
