"""Where the composition root finds the files Sextant ships with.

Delegates the real lookups to `sextant.resources` (2N Task 5 fix round 1,
MAJOR-2) — that module's own docstring carries the full rationale. This
module keeps only `_package_root`, UNCHANGED, so
`tests/cli/test_resources.py`'s own
`monkeypatch.setattr(resources, "_package_root", ...)` still reaches the
exact code path it always did: passed through as `sextant.resources`'s own
`root` parameter, rather than read off a shared default. Every message and
path-join now lives in exactly one place — `sextant.resources`'s own; this
module supplies only WHERE to look."""

from importlib import resources
from pathlib import Path

from sextant import resources as _resources
from sextant.resources import MissingResourceError

__all__ = ["MissingResourceError", "catalogs_dir", "extractor_jar", "instructions_path"]


def catalogs_dir() -> Path:
    return _resources.catalogs_dir(root=_package_root())


def extractor_jar() -> Path:
    return _resources.extractor_jar(root=_package_root())


def instructions_path() -> Path:
    return _resources.instructions_path(root=_package_root())


def _package_root() -> Path:
    return Path(str(resources.files("sextant")))
