"""The one fixture-build step that cannot live beside the test that needs it.

`fixtures/orders-service` declares a dependency on `com.example:orders-soap-client`
(2I Task 6's opt-in library extraction), and Maven resolves every declared
dependency before it compiles anything — so the ~30 `mvn -o compile` calls
scattered through this suite all fail unless that artifact is in the local
repository first. Installing it is therefore a precondition of the suite, not of
one test, which is what makes it a session fixture here rather than a call in
each file.

**`mvn install` cannot do it in this environment.** Neither `maven-jar-plugin`
nor the resolver `maven-install-plugin:install-file` needs is in `~/.m2`, and
offline mode cannot fetch them (Phase 2I Task 2's own finding). So the three
steps `mvn install` would run are done directly: compile with the plugin that IS
present, assemble the jar, and lay it into the local repository at the path
Maven's own layout convention puts it — which is exactly the path
`MavenDetector` resolves a library coordinate through.

The jar is assembled with `zipfile` rather than the JDK's `jar` tool for one
reason: entry order is then under this file's control, sorted, so the fixture
jar is byte-identical between machines.
"""

import subprocess
import zipfile
from pathlib import Path

import pytest

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


def _is_current(jar: Path) -> bool:
    if not jar.is_file():
        return False
    built = jar.stat().st_mtime
    sources = [*STUB.rglob("*.java"), STUB / "pom.xml", STUB.parent / "pom.xml"]
    return all(source.stat().st_mtime <= built for source in sources)


@pytest.fixture(scope="session", autouse=True)
def stub_library_in_the_local_repository() -> Path:
    """Built and installed once per session, and skipped entirely when it is
    already current — every test in this suite depends on it, including the ones
    that never touch Maven, so the up-to-date path must cost nothing."""
    jar = local_repository_jar()
    if _is_current(jar):
        return jar
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=STUB, check=True)
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
