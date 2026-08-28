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

    Two locations, unlike the catalogs, because the jar is built rather than
    committed: inside the package once a wheel is built, and in Gradle's output
    when running from a checkout.
    """
    packaged = _package_root() / "extractor-jvm" / "sextant-extractor.jar"
    if packaged.is_file():
        return packaged
    built = _repo_root() / "extractor-jvm" / "build" / "libs" / "sextant-extractor.jar"
    if built.is_file():
        return built
    raise MissingResourceError(
        f"the JVM extractor is at neither {packaged} nor {built} — build it with "
        "`cd extractor-jvm && ./gradlew build`, and build it before the wheel"
    )


def _package_root() -> Path:
    return Path(str(resources.files("sextant")))


def _repo_root() -> Path:
    return Path(__file__).parents[3]
