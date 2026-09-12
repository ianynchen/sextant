"""W59 — the RECEIVE-shaped methods on the four messaging templates, and which of them
take a destination name at argument 0.

`spring-rabbit-template.yml`, `spring-jms-template.yml`, `spring-kafka-template.yml` and
`spring-sqs-template.yml` all read their SEND half only (`G-44`). A `single_call` row can
only address a wire off an argument the call site itself carries, so before any receive
row is written the question is mechanical: of every `receive*` method each template
declares, which ones take the queue/destination/topic name as argument 0 — addressable —
and which read a template-configured default, or a `Consumer<...Options>` lambda whose
destination is buried inside it — not addressable by this style at all?

**Version scope (§5.4).** Read against **spring-rabbit 3.1.4, spring-jms 6.1.6,
spring-kafka 3.1.4 and spring-cloud-aws-sqs 3.1.1** — each the version the jar reports for
itself, checked against the coordinate before any table is printed.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

# (coordinate, internal class, the method-name regex this class's receive-shaped methods
# are read through)
METHODS = (
    (
        "org.springframework.amqp:spring-rabbit:3.1.4",
        "org/springframework/amqp/rabbit/core/RabbitTemplate",
        r"receive\w*",
    ),
    (
        "org.springframework:spring-jms:6.1.6",
        "org/springframework/jms/core/JmsTemplate",
        r"receive\w*",
    ),
    (
        "org.springframework.kafka:spring-kafka:3.1.4",
        "org/springframework/kafka/core/KafkaTemplate",
        r"receive\w*",
    ),
    (
        "io.awspring.cloud:spring-cloud-aws-sqs:3.1.1",
        "io/awspring/cloud/sqs/operations/SqsTemplate",
        r"receive\w*",
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
            f"for {requested!r}."
        )
    return jar, reported, source


def _javap(jar: Path, internal: str, *flags: str) -> str:
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


_PRIMITIVES = {
    "B": "byte",
    "C": "char",
    "D": "double",
    "F": "float",
    "I": "int",
    "J": "long",
    "S": "short",
    "Z": "boolean",
}


def _first_param_type(descriptor: str) -> str | None:
    """The JVM type of argument 0, read off the descriptor's own parameter list —
    `None` when the method takes no arguments at all."""
    params = descriptor[1 : descriptor.index(")")]
    if not params:
        return None
    i = 0
    arrays = 0
    while params[i] == "[":
        arrays += 1
        i += 1
    if params[i] == "L":
        end = params.index(";", i)
        name = params[i + 1 : end].replace("/", ".")
    else:
        name = _PRIMITIVES[params[i]]
    return name + "[]" * arrays


def receive_methods(jar: Path, internal: str, name_pattern: str) -> list[tuple[str, str]]:
    """`(method name, descriptor)` for every public method on `internal` whose name
    matches `name_pattern` — `javap -s`'s own output, parsed the way `_javap` renders
    it: a signature line, then its `descriptor:` line directly below."""
    text = _javap(jar, internal, "-p", "-s")
    pattern = re.compile(rf"public .*? ({name_pattern})\(.*?\n\s+descriptor: (\S+)")
    return [(name, descriptor) for name, descriptor in re.findall(pattern, text)]


def main() -> None:
    coordinates = list(dict.fromkeys(coordinate for coordinate, *_ in METHODS))
    read = {c: checked(c) for c in coordinates}

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w59_template_receive_halves/run.sh`, which runs")
    print("`sweep.py`. **Every version in the headers below is the one the JAR itself")
    print("reported** — out of its own `pom.properties` or its manifest's")
    print("`Implementation-Version`, and **not the version the coordinate list asked for**;")
    print("`checked` compares the two and ABORTS when they disagree.\n")
    versions: list[str] = []
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

    print("### Every `receive*` method each template declares, and whether it addresses")
    print("### a wire\n")
    for coordinate, internal, name_pattern in METHODS:
        jar = read[coordinate][0]
        methods = receive_methods(jar, internal, name_pattern)
        print(f"**`{internal.replace('/', '.')}`** ({coordinate})\n")
        print("| # | method | descriptor | argument 0 type | addressable |")
        print("|---|---|---|---|---|")
        if not methods:
            print(f"| — | *(no `{name_pattern}` method found)* | — | — | — |")
            print()
            continue
        for n, (name, descriptor) in enumerate(methods, start=1):
            arg0 = _first_param_type(descriptor) or "*(none)*"
            addressable = "**yes**" if descriptor.startswith("(Ljava/lang/String;") else "no"
            print(f"| {n} | `{name}` | `{descriptor}` | `{arg0}` | {addressable} |")
        print()


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
