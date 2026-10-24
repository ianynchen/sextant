"""W53 — do the gRPC annotation FQNs two catalogs name actually exist? (`G-91`)

`grpc-spring.yml` and `grpc-net-devh.yml` name three annotation types between
them. Neither `net.devh:*` nor `org.springframework.grpc:*` resolved in either
local repository when A2 audited them, so A2's belief that all three spellings are
right was a PREDICTION (GUIDELINES §8.1) — and a wrong FQN in an
`annotation_driven` catalog is silent: the annotation simply never matches, and
the catalog derives nothing while looking healthy.

Both artifacts resolve from Maven Central. This probe opens them.

**Version scope (§5.4).** Read against **net.devh 3.1.0.RELEASE** (client and
server starters) and **Spring gRPC 0.10.0** (`spring-grpc-core` and its
Boot starter). Which package an annotation lives in is API surface and moves
between major versions; these are the versions read, and no other.
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _jvm_annotations import classes, render

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

# (coordinate, the class the catalog names, which catalog names it, and what the
# catalog uses the coordinate FOR). The last column matters: a `detect.coordinates`
# entry is a gate or a provenance record, and neither requires the jar to CARRY the
# class — only that declaring the coordinate means the class is on the classpath.
CLAIMS = (
    (
        "net.devh:grpc-client-spring-boot-starter:3.1.0.RELEASE",
        "net/devh/boot/grpc/client/inject/GrpcClient",
        "grpc-net-devh.yml",
        "field_annotation, and detect.coordinates",
    ),
    (
        "net.devh:grpc-server-spring-boot-starter:3.1.0.RELEASE",
        "net/devh/boot/grpc/server/service/GrpcService",
        "grpc-spring.yml",
        "corroborates.class_annotations",
    ),
    (
        "org.springframework.grpc:spring-grpc-core:0.10.0",
        "org/springframework/grpc/server/service/GrpcService",
        "grpc-spring.yml",
        "corroborates.class_annotations",
    ),
    (
        "org.springframework.grpc:spring-grpc-spring-boot-starter:0.10.0",
        "org/springframework/grpc/server/service/GrpcService",
        "grpc-spring.yml",
        "detect.coordinates",
    ),
)


class ProbeError(RuntimeError):
    """Anything that would otherwise put an unmeasured cell in a table."""


def resolve(artifact: str) -> Path:
    group, name, version = artifact.split(":")
    jar = M2 / Path(group.replace(".", "/")) / name / version / f"{name}-{version}.jar"
    if not jar.is_file():
        subprocess.run(
            ["mvn", "-q", "-B", "dependency:get", "-Dtransitive=false", f"-Dartifact={artifact}"],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
    if not jar.is_file():
        raise ProbeError(f"{artifact} did not resolve; fix the coordinate in run.sh")
    return jar


def self_reported_version(jar: Path) -> tuple[str, str]:
    """The version the ARCHIVE states for itself, and where. Raises rather than
    defaulting: a missing self-report is where a hand-written column would go
    unchallenged (CP-5)."""
    with zipfile.ZipFile(jar) as archive:
        entries = [
            name
            for name in archive.namelist()
            if name.startswith("META-INF/maven/") and name.endswith("/pom.properties")
        ]
        if entries:
            for line in archive.read(entries[0]).decode("utf-8", "replace").splitlines():
                if line.strip().startswith("version="):
                    return line.split("=", 1)[1].strip(), "pom.properties"
        try:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError as missing:
            raise ProbeError(f"{jar.name} reports no version of its own") from missing
    for line in manifest.splitlines():
        if line.lower().startswith("implementation-version:"):
            return line.split(":", 1)[1].strip(), "MANIFEST.MF"
    raise ProbeError(f"{jar.name} states no version in its pom.properties or its manifest")


def checked(artifact: str) -> tuple[Path, str, str]:
    jar = resolve(artifact)
    reported, source = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own {source} while the coordinate asked "
            f"for {requested!r}. Fix run.sh rather than labelling a column with a version this "
            f"run did not read."
        )
    return jar, reported, source


def _javap(jar: Path, internal: str, *flags: str) -> str:
    """`javap` output for one class. ABORTS when the jar does not carry it: an
    empty string reaches these tables as the probe's own conclusions."""
    with tempfile.TemporaryDirectory() as into:
        try:
            with zipfile.ZipFile(jar) as archive:
                archive.extract(f"{internal}.class", into)
        except KeyError as missing:
            raise ProbeError(f"{jar.name} does not carry {internal}") from missing
        completed = subprocess.run(
            ["javap", *flags, str(Path(into) / f"{internal}.class")],
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise ProbeError(f"javap failed on {internal}: {completed.stderr.strip()}")
    return completed.stdout


def carries(jar: Path, internal: str) -> bool:
    with zipfile.ZipFile(jar) as archive:
        return f"{internal}.class" in archive.namelist()


def class_count(jar: Path) -> int:
    with zipfile.ZipFile(jar) as archive:
        return sum(1 for name in archive.namelist() if name.endswith(".class"))


def main() -> None:
    read = {coordinate: checked(coordinate) for coordinate, *_ in CLAIMS}

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w53_grpc_annotation_identities/run.sh`, which runs")
    print("`sweep.py`. **Every version in the headers below is the one the JAR itself")
    print("reported** — out of its own `pom.properties` or its manifest's")
    print("`Implementation-Version`, and **not the version the coordinate list asked for**;")
    print("`checked` compares the two and ABORTS when they disagree.\n")
    versions = []
    for coordinate in read:
        version = coordinate.split(":")[2]
        if version not in versions:
            versions.append(version)
    print("| what the run read | " + " | ".join(versions) + " |")
    print("|---|" + "---|" * len(versions))
    for label, pick in (("artifacts reporting this version", 1), ("where the jar states it", 2)):
        cells = []
        for version in versions:
            names = [
                (c.split(":")[1] if pick == 1 else read[c][2])
                for c in read
                if c.split(":")[2] == version
            ]
            cells.append(", ".join(dict.fromkeys(names)))
        print(f"| {label} | " + " | ".join(cells) + " |")
    print()

    print("### Does each named type exist where the catalog says?\n")
    print("| coordinate | class the catalog names | carries it | classes in the jar | used as |")
    print("|---|---|---|---|---|")
    for coordinate, internal, catalog, role in CLAIMS:
        jar = read[coordinate][0]
        found = carries(jar, internal)
        fqn = internal.replace("/", ".")
        print(
            f"| `{coordinate}` | `{fqn}` ({catalog}) | "
            f"{'**yes**' if found else 'no'} | {class_count(jar)} | {role} |"
        )

    # Added 2026-10-24 (final review of spec 2026-10-24-quarkus-messaging-and-grpc): where
    # each annotation may SIT is what decides which injection points `injected_client` must
    # read, so it is read off the class file here rather than cited as a hand-run `javap`.
    print("\n### Where may each annotation sit?\n")
    print("| # | annotation | read from | `@Target` | `@Retention` |")
    print("|---|---|---|---|---|")
    row = 0
    done: set[str] = set()
    for coordinate, internal, _catalog, _role in CLAIMS:
        jar = read[coordinate][0]
        fqn = internal.replace("/", ".")
        if fqn in done or not carries(jar, internal):
            continue
        done.add(fqn)
        annotation = classes(jar, [fqn])[fqn]
        target = annotation.annotation("java.lang.annotation.Target")
        retention = annotation.annotation("java.lang.annotation.Retention")
        if target is None or retention is None:
            raise ProbeError(f"{fqn} declares no @Target or no @Retention in {jar.name}")
        row += 1
        print(
            f"| {row} | `{fqn}` | `{coordinate}` | {render(target.elements['value'])} | "
            f"{retention.elements['value']} |"
        )


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
