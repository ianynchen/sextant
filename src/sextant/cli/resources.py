"""Where the composition root finds the files Sextant ships with.

Resolved through the installed package rather than from this file's position on
disk. `Path(__file__).parents[3]` assumed a source checkout: from a wheel it
points above `site-packages`, where neither the catalogs nor the extractor
exist — and a catalog directory that is merely absent globs to nothing, so a
packaged Sextant would report no endpoints and no skipped catalogs. That is the
failure capability reporting exists to prevent, arriving through packaging."""

from importlib import resources
from pathlib import Path


class MissingResourceError(FileNotFoundError):
    """A file Sextant ships with is not where the install put it."""


def catalogs_dir() -> Path:
    """The built-in catalogs (D02 §6).

    One location, checkout and wheel alike, because they live inside the
    package — they travel with the code that interprets them or a version
    mismatch becomes possible.
    """
    directory = _package_root() / "catalogs"
    if not directory.is_dir():
        raise MissingResourceError(f"the built-in catalogs are not at {directory}")
    return directory


def extractor_jar() -> Path:
    """The JVM extractor. ARCHITECTURE §9 ships it inside the distribution
    because version drift between extractor and loader is a silent correctness
    fault — the two must travel as one artifact.

    One location, like the catalogs: Gradle builds the jar straight into the
    package. It is git-ignored rather than committed, so a fresh clone has none
    until the extractor is built — which is why this reports the remedy instead
    of failing at install time. Making the wheel force-include it did exactly
    that, breaking `pip install -e .` on any clone.
    """
    jar = _package_root() / "extractor-jvm" / "sextant-extractor.jar"
    if not jar.is_file():
        raise MissingResourceError(
            f"the JVM extractor is not at {jar} — build it with "
            "`cd extractor-jvm && ./gradlew build`"
        )
    return jar


def _package_root() -> Path:
    return Path(str(resources.files("sextant")))
