"""Where the composition root finds the files Sextant ships with.

Resolved through the installed package rather than from this file's position on
disk. `Path(__file__).parents[3]` assumed a source checkout: from a wheel it
points above `site-packages`, where neither the catalogs nor the extractor
exist — and a catalog directory that is merely absent globs to nothing, so a
packaged Sextant would report no endpoints and no skipped catalogs. That is the
failure capability reporting exists to prevent, arriving through packaging.

**The one real implementation; `sextant.cli.resources` delegates to it**
(2N Task 5, §5b, fix round 1 MAJOR-2): the library facade (`sextant.api`)
needs these same lookups, and the import-linter layering puts `api` BELOW
`cli` (`cli` is the one thing allowed to import `api`, never the reverse) —
so a lookup both sides need cannot live inside the `cli` package itself. A
straight re-export was the first attempt; it broke
`tests/cli/test_resources.py::test_a_missing_extractor_says_how_to_build_it`,
which whiteboxes `cli.resources._package_root` directly with
`monkeypatch.setattr` — a re-exported `extractor_jar` still closes over
`_package_root` in the module it was actually DEFINED in, so patching the
name in `cli.resources` had no effect on it. The fix is this module's own
`root` parameter: every lookup below takes an optional `root`, defaulting to
THIS module's `_package_root()` when omitted (every call `sextant.api`
itself makes). `cli/resources.py` keeps its own `_package_root` — the one
`monkeypatch` still reaches — and delegates by passing ITS OWN result in as
`root`, so each message and path-join lives in exactly one place, and the
existing whitebox test needed no edit.
"""

from importlib import resources
from pathlib import Path


class MissingResourceError(FileNotFoundError):
    """A file Sextant ships with is not where the install put it."""


def catalogs_dir(root: Path | None = None) -> Path:
    """The built-in catalogs (D02 §6).

    One location, checkout and wheel alike, because they live inside the
    package — they travel with the code that interprets them or a version
    mismatch becomes possible. `root` overrides where "the package" is taken
    to be — `cli.resources.catalogs_dir()` passes its own `_package_root()`
    here (module docstring); omitted, it is this module's own.
    """
    package_root = root if root is not None else _package_root()
    directory = package_root / "catalogs"
    if not directory.is_dir():
        raise MissingResourceError(f"the built-in catalogs are not at {directory}")
    return directory


def extractor_jar(root: Path | None = None) -> Path:
    """The JVM extractor. ARCHITECTURE §9 ships it inside the distribution
    because version drift between extractor and loader is a silent correctness
    fault — the two must travel as one artifact.

    One location, like the catalogs: Gradle builds the jar straight into the
    package. It is git-ignored rather than committed, so a fresh clone has none
    until the extractor is built — which is why this reports the remedy instead
    of failing at install time. Making the wheel force-include it did exactly
    that, breaking `pip install -e .` on any clone. `root` — see `catalogs_dir`.
    """
    package_root = root if root is not None else _package_root()
    jar = package_root / "extractor-jvm" / "sextant-extractor.jar"
    if not jar.is_file():
        raise MissingResourceError(
            f"the JVM extractor is not at {jar} — build it with "
            "`cd extractor-jvm && ./gradlew build`"
        )
    return jar


def instructions_path(root: Path | None = None) -> Path:
    """The enrichment instructions document (2K design §5) — the text every
    `sextant module enrich` run reads as its system prompt, and whose sha256
    is the overlay's `instructions_hash`. Shipped inside the package, one
    location like the catalogs and the extractor: it travels with the code
    that reads it, so a version mismatch cannot happen. `root` — see
    `catalogs_dir`."""
    package_root = root if root is not None else _package_root()
    path = package_root / "enrich" / "INSTRUCTIONS.md"
    if not path.is_file():
        raise MissingResourceError(f"the enrichment instructions are not at {path}")
    return path


def _package_root() -> Path:
    return Path(str(resources.files("sextant")))
