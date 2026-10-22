"""Build the stub library and lay it into the local Maven repository.

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

The jar is assembled with `zipfile` rather than the JDK's `jar` tool for one
reason: entry order is then under this file's control, sorted, so the fixture
jar's contents are identical between machines.
"""

import subprocess
import zipfile
from pathlib import Path

REPO = Path(__file__).parents[1]
STUB = REPO / "fixtures" / "orders-soap-client"
STUB_GROUP = "com.example"
STUB_ARTIFACT = "orders-soap-client"
STUB_VERSION = "1.0.0"

_POM = f"""<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>{STUB_GROUP}</groupId>
  <artifactId>{STUB_ARTIFACT}</artifactId>
  <version>{STUB_VERSION}</version>
</project>
"""


def local_repository_jar() -> Path:
    """Where Maven's layout convention puts this fixture's artifact — the same
    path `MavenDetector` composes from the coordinate and the version the POM
    declares for it."""
    return (
        Path.home()
        / ".m2"
        / "repository"
        / Path(*STUB_GROUP.split("."))
        / STUB_ARTIFACT
        / STUB_VERSION
        / f"{STUB_ARTIFACT}-{STUB_VERSION}.jar"
    )


def is_current(jar: Path) -> bool:
    if not jar.is_file():
        return False
    built = jar.stat().st_mtime
    sources = [*STUB.rglob("*.java"), STUB / "pom.xml", STUB.parent / "pom.xml"]
    return all(source.stat().st_mtime <= built for source in sources)


def compile_and_install(*, offline: bool) -> Path:
    """Compile the stub, assemble its jar, and lay jar + POM into `~/.m2`.

    `offline` is the caller's promise about the network: the test suite passes
    True (no test reaches the network), CI's priming step passes False (a fresh
    runner has no compiler plugin in `~/.m2` to compile with)."""
    jar = local_repository_jar()
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
        cwd=STUB,
        check=True,
    )
    classes = STUB / "target" / "classes"
    staged = STUB / "target" / jar.name
    with zipfile.ZipFile(staged, "w") as archive:
        for path in sorted(classes.rglob("*.class")):
            archive.write(path, str(path.relative_to(classes)))
    jar.parent.mkdir(parents=True, exist_ok=True)
    jar.write_bytes(staged.read_bytes())
    # The POM beside it is not decoration: offline resolution reads it, and a
    # jar laid down without one is an artifact Maven refuses to resolve.
    jar.with_suffix(".pom").write_text(_POM, encoding="utf-8")
    return jar


if __name__ == "__main__":
    compile_and_install(offline=False)
