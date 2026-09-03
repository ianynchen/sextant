"""Where the composition root finds the files Sextant ships with.

Resolved through the installed package rather than from this file's position on
disk. `Path(__file__).parents[3]` assumed a source checkout: from a wheel it
points above `site-packages`, where neither the catalogs nor the extractor
exist — and a catalog directory that is merely absent globs to nothing, so a
packaged Sextant would report no endpoints and no skipped catalogs. That is the
failure capability reporting exists to prevent, arriving through packaging.

**The one implementation, full stop** (2N Task 5, §5b introduced it because
the library facade, `sextant.api`, needed these lookups and the import-linter
layering puts `api` BELOW `cli` — a lookup both sides needed could not live
inside the `cli` package alone; 2N Task 6 finished the move by retiring
`sextant.cli.resources`, the delegating copy that briefly existed for fix
round 1's `_package_root` whitebox reasons, once its one unique test —
`tests/cli/test_resources.py::test_a_missing_extractor_says_how_to_build_it`,
which whiteboxed `_package_root` with `monkeypatch.setattr` — was ported to
target THIS module's own `_package_root` instead, in
`tests/test_sextant_resources.py`). Every lookup below still takes an
optional `root`, defaulting to THIS module's `_package_root()` when omitted
(every real caller's own path, `sextant.api` included) — the parameter
remains as the seam that test uses to point at a directory with nothing in
it, without touching the installed package.
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
    to be (module docstring); omitted, it is this module's own
    `_package_root()`.
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
