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
    """Every regular file under `root`, sorted by its path *relative to
    `root`* so a reader sees a deterministic order regardless of the
    filesystem's own directory-entry order (NFR-1: files sorted by relative
    path).

    Sorting the `Path` objects themselves is not equivalent, and silently
    gives the wrong order (2F review fix round 1): `PurePath.__lt__`
    compares each path's *parts tuple*, not its rendered string, so a
    shorter first segment sorts before a longer one regardless of what
    follows it — `a/b.yml` (`("a", "b.yml")`) sorts before `a.yml`
    (`("a.yml",)`) by Path ordering, the reverse of comparing the relative
    path *strings* `"a.yml"` and `"a/b.yml"`, which is the order NFR-1
    actually means."""
    return tuple(
        sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: str(path.relative_to(root)),
        )
    )
