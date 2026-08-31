"""Listing what is on disk under a resource root, for the ArtifactReader
port (D00 §5c) to read.

Lives in `domain` rather than `application`: `application` orchestrates
through ports only and never touches a filesystem directly (ARCHITECTURE
§10, enforced by `test_application_reads_no_files`) — the same reason
`domain/factfile.py` already owns the fact tree's own read/write, not
`application/stages/analyze.py`. A directory listing carries no policy, so
pushing it down here costs nothing and keeps the orchestration stage free of
raw I/O calls."""

from pathlib import Path


def list_files(root: Path) -> tuple[Path, ...]:
    """Every regular file under `root`, sorted by path so a reader sees a
    deterministic order regardless of the filesystem's own directory-entry
    order (NFR-1: files sorted by relative path — sorting the absolute path
    is equivalent here, since every result shares `root` as a prefix)."""
    return tuple(sorted(path for path in root.rglob("*") if path.is_file()))
