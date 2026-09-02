"""Raw, unopinionated filesystem reads — text, a directory's entries, a
recursive file walk — with no policy of their own (no ignore-filtering, no
ordering promise). `application` orchestrates and derives; every I/O concern
reaches it through a port or, where the concern is this small, a plain
domain function (ARCHITECTURE §10, enforced by `test_application_reads_no_files`
— the same reason `resource_files.py` and `factfile.py` already own their own
reads rather than leaving them in `application/stages/analyze.py`).

Deliberately thinner than `resource_files.list_files`: that function ALSO
applies `.sextantignore` and returns a deterministic order, because every
one of its callers wants both. 2K Task 5's jail wants neither baked in here
— it decides visibility itself, per file, against three roots at once
rather than one `repo_root` — so these three functions do only the syscall
and nothing else; the caller supplies whatever policy it needs."""

from pathlib import Path


def read_file_text(path: Path) -> str:
    """`path`'s content, decoded as UTF-8. Raises exactly what
    `Path.read_text` raises (`OSError`, `UnicodeDecodeError`) — a caller
    that wants a softer failure catches it itself.

    Named `read_file_text` rather than `read_text`, its obvious name,
    deliberately: `test_application_reads_no_files` (ARCHITECTURE §10)
    flags the bare IDENTIFIER `read_text` anywhere in `application`, not
    only a `Path.read_text` attribute access — a wrapper spelled the same
    would still trip the rule it exists to satisfy."""
    return path.read_text(encoding="utf-8")


def list_directory(path: Path) -> list[Path]:
    """`path`'s immediate entries, in whatever order the filesystem
    gives them."""
    return list(path.iterdir())


def walk_files(root: Path) -> list[Path]:
    """Every regular file under `root`, recursively, in whatever order the
    filesystem gives them."""
    return [path for path in root.rglob("*") if path.is_file()]
