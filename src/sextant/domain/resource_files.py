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

from sextant.domain.ignorefile import IgnoreRules


def list_files(root: Path, repo_root: Path, ignore: IgnoreRules) -> tuple[Path, ...]:
    """Every regular file under `root` that `.sextantignore` (2K design §2)
    does not exclude, sorted by its path *relative to `root`* so a reader
    sees a deterministic order regardless of the filesystem's own
    directory-entry order (NFR-1: files sorted by relative path).

    `ignore` is checked here, at the one place both of `analyze`'s walk
    sites (resource roots and schema roots) funnel through — a file this
    excludes is never in the tuple a caller partitions or reads, so an
    ignored file cannot reach a reader by any path through this function.
    `repo_root` is what `ignore.matches` matches against: a `.sextantignore`
    pattern is written against the repo root, not against whatever
    resource or schema root a given call happens to be walking (2K Task 2
    binding: matching is repo-root-relative).

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
            (
                path
                for path in root.rglob("*")
                if path.is_file() and not ignore.matches(path.relative_to(repo_root))
            ),
            key=lambda path: str(path.relative_to(root)),
        )
    )


def named_file(root: Path, name: str) -> Path | None:
    """The regular file `name` (relative to `root`) names, or `None` where there is none or it
    lies outside `root`: code names a file as a string, and a `..` or an absolute path must not
    take a read out of the module. No ignore rule is consulted — the caller reads a file the
    code NAMED, deliberately, which the walk above never does for a built-in-ignored one."""
    anchor = root.resolve()
    path = (root / name).resolve()
    if not path.is_file() or not path.is_relative_to(anchor):
        return None
    return root / path.relative_to(anchor)
