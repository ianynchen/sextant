"""Build the stub libraries and lay them into the local Maven repository.

`fixtures/orders-service` declares a dependency on `com.example:orders-soap-client`
(2I Task 6's opt-in library extraction), and Maven resolves every declared
dependency before it compiles anything — so nothing that compiles that fixture
can run until this artifact is in `~/.m2`. Two callers need that, which is why
the logic lives in its own module rather than in `conftest.py`:

- the test suite's session fixture (`conftest.py`), which compiles offline —
  ARCHITECTURE §9a: no test reaches the network;
- CI's priming step, which runs this file as a script BEFORE the suite exists,
  because it primes `orders-service`'s dependencies with the same `mvn compile`
  Maven uses to resolve them — and that resolution fails on the stub unless the
  stub is installed first. Priming is the one step allowed to fetch, so the
  script path compiles online.

**`mvn install` cannot do the installation in the offline environment.** Neither
`maven-jar-plugin` nor the resolver `maven-install-plugin:install-file` needs is
guaranteed in `~/.m2`, and offline mode cannot fetch them (Phase 2I Task 2's own
finding). So the three steps `mvn install` would run are done directly: compile,
assemble the jar, and lay it into the local repository at the path Maven's own
layout convention puts it — which is exactly the path `MavenDetector` resolves a
library coordinate through.

**More than one library.** `LIBRARIES` lists every fixture that is a dependency jar of
another fixture: the stub above, and `orders-vertx-web-base`, the jar holding the shapes
Hono keeps in `service-base` (Vert.x Web spec 2026-10-30 §3f), which `orders-vertx-web`
declares and which must stay OUTSIDE that module's own classes, and `orders-dagger-network`, the
Dagger module `orders-dagger` includes from another build module. Each is built and laid down
by the steps above, one after another. The functions take the library as their last
argument and default to the first, so every caller written for the stub alone — the suite's
session fixture, `fixture_build`'s fingerprint, the tests that patch `local_repository_jar`
— is unchanged.

The jar is assembled with `zipfile` rather than the JDK's `jar` tool for one
reason: entry order is then under this file's control, sorted, so the fixture
jar's contents are identical between machines.
"""

import subprocess
import zipfile
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).parents[1]
STUB = REPO / "fixtures" / "orders-soap-client"
STUB_GROUP = "com.example"
STUB_ARTIFACT = "orders-soap-client"
STUB_VERSION = "1.0.0"


class Library(NamedTuple):
    """One fixture that is a dependency jar of another: its coordinate and its directory."""

    group: str
    artifact: str
    version: str
    directory: Path


LIBRARIES = (
    Library(STUB_GROUP, STUB_ARTIFACT, STUB_VERSION, STUB),
    Library(
        "com.example", "orders-vertx-web-base", "1.0.0", REPO / "fixtures" / "orders-vertx-web-base"
    ),
    # The Dagger module `orders-dagger` includes from another build module (spec 2026-11-05
    # di-recipe-hop §3): its recipe must stay outside that module's own classes.
    Library(
        "com.example", "orders-dagger-network", "1.0.0", REPO / "fixtures" / "orders-dagger-network"
    ),
)


def _pom(library: Library) -> str:
    return f"""<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>{library.group}</groupId>
  <artifactId>{library.artifact}</artifactId>
  <version>{library.version}</version>
</project>
"""


def local_repository_jar(library: Library = LIBRARIES[0]) -> Path:
    """Where Maven's layout convention puts this fixture's artifact — the same
    path `MavenDetector` composes from the coordinate and the version the POM
    declares for it."""
    return (
        Path.home()
        / ".m2"
        / "repository"
        / Path(*library.group.split("."))
        / library.artifact
        / library.version
        / f"{library.artifact}-{library.version}.jar"
    )


def is_current(jar: Path, library: Library = LIBRARIES[0]) -> bool:
    if not jar.is_file():
        return False
    built = jar.stat().st_mtime
    directory = library.directory
    sources = [*directory.rglob("*.java"), directory / "pom.xml", directory.parent / "pom.xml"]
    return all(source.stat().st_mtime <= built for source in sources)


def compile_and_install(*, offline: bool, library: Library = LIBRARIES[0]) -> Path:
    """Compile the stub, assemble its jar, and lay jar + POM into `~/.m2`.

    `offline` is the caller's promise about the network: the test suite passes
    True (no test reaches the network), CI's priming step passes False (a fresh
    runner has no compiler plugin in `~/.m2` to compile with)."""
    jar = local_repository_jar(library)
    mode = ["-o"] if offline else ["-B"]
    # The classpath goal beside `compile`, as `fixture_build` runs it: the detector reads
    # the file this writes, and a stub without one would start `mvn` on every `detect`.
    subprocess.run(
        [
            "mvn",
            "-q",
            *mode,
            "compile",
            "dependency:build-classpath",
            "-Dmdep.outputFile=target/sextant-classpath.txt",
            "-Dmdep.includeScope=compile",
            "-Dmdep.regenerateFile=true",
        ],
        cwd=library.directory,
        check=True,
    )
    classes = library.directory / "target" / "classes"
    staged = library.directory / "target" / jar.name
    with zipfile.ZipFile(staged, "w") as archive:
        for path in sorted(classes.rglob("*.class")):
            archive.write(path, str(path.relative_to(classes)))
    jar.parent.mkdir(parents=True, exist_ok=True)
    jar.write_bytes(staged.read_bytes())
    # The POM beside it is not decoration: offline resolution reads it, and a
    # jar laid down without one is an artifact Maven refuses to resolve.
    jar.with_suffix(".pom").write_text(_pom(library), encoding="utf-8")
    return jar


def install_all(*, offline: bool) -> None:
    """Every listed library, each only when its jar is not already current."""
    for library in LIBRARIES:
        if not is_current(local_repository_jar(library), library):
            compile_and_install(offline=offline, library=library)


if __name__ == "__main__":
    for each in LIBRARIES:
        compile_and_install(offline=False, library=each)
