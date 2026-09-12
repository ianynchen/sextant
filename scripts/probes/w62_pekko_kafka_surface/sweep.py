"""W62 — Pekko Connectors Kafka's consumer-source, subscription-factory and
producer-sink methods, and which argument position (if any) carries a topic or a
subscription built from one.

`pekko-connectors-kafka.yml` (`alpakka-pekko`) reads
`Consumer.plainSource`/`committableSource`/`atMostOnceSource`/
`plainPartitionedSource`/`committablePartitionedSource`, each of whose second argument
is a `Subscription` built by `Subscriptions.topics`/`topicPattern`/`assignment`. Before
any row was written the question is mechanical: of every method matching
`plainSource|committableSource|atMostOnceSource|plainPartitionedSource|
committablePartitionedSource|topics|topicPattern|assignment|plainSink|committableSink|
flexiFlow` on `Consumer`, `Subscriptions` and `Producer`, which parameter position (if
any) carries a value shaped like a topic — a plain `String`, a `String...`/
`TopicPartition...` varargs array, or a `Subscription`/`AutoSubscription`/
`ManualSubscription` built from one?

**Version scope (§5.4).** Read against **pekko-connectors-kafka 1.1.0** — the version
the jar reports for itself, checked against the coordinate before any table is printed.
`fixtures/orders-pekko/pom.xml` pins the same version.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

# (coordinate, internal class, the method-name regex this class's topic-shaped methods
# are read through — the same pattern across all three types, per w62's brief).
_NAME_PATTERN = (
    r"plainSource|committableSource|atMostOnceSource|plainPartitionedSource|"
    r"committablePartitionedSource|topics|topicPattern|assignment|plainSink|"
    r"committableSink|flexiFlow"
)
CLASSES = (
    (
        "org.apache.pekko:pekko-connectors-kafka_2.13:1.1.0",
        "org/apache/pekko/kafka/javadsl/Consumer",
    ),
    ("org.apache.pekko:pekko-connectors-kafka_2.13:1.1.0", "org/apache/pekko/kafka/Subscriptions"),
    (
        "org.apache.pekko:pekko-connectors-kafka_2.13:1.1.0",
        "org/apache/pekko/kafka/javadsl/Producer",
    ),
)

# The topic-or-subscription JVM parameter shapes checked, in descriptor order — a plain
# topic name, a `String...`/`TopicPartition...` varargs array (erased to a real array
# descriptor), or one of the three `Subscription` types `Subscriptions`' own factories
# return and `Consumer`'s own sources consume.
_TOPIC_SHAPES = (
    "Ljava/lang/String;",
    "[Ljava/lang/String;",
    "[Lorg/apache/kafka/common/TopicPartition;",
    "Lorg/apache/pekko/kafka/Subscription;",
    "Lorg/apache/pekko/kafka/AutoSubscription;",
    "Lorg/apache/pekko/kafka/ManualSubscription;",
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
    """The version the jar records about ITSELF (§5.4).

    Checked with `unzip -l` before this was written: pekko-connectors-kafka_2.13-1.1.0
    carries no Maven `pom.properties` (a Scala/sbt-built artifact, not `mvn`-built), but
    its manifest states `Implementation-Version` directly — the same rung `w61`
    (Javalin) reads first, checked in the same order.
    """
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
        except KeyError:
            manifest = ""
        for line in manifest.splitlines():
            if line.lower().startswith("implementation-version:"):
                return line.split(":", 1)[1].strip(), "MANIFEST.MF"
    raise ProbeError(f"{jar.name} states no version in its pom.properties nor its manifest")


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


def topic_methods(jar: Path, internal: str, name_pattern: str) -> list[tuple[str, str]]:
    """`(method name, descriptor)` for every public method on `internal` whose name
    matches `name_pattern` — `javap -p -s`'s own output, a signature line then its
    `descriptor:` line directly below (the `w60`/`w61` precedent's own parse)."""
    text = _javap(jar, internal, "-p", "-s")
    pattern = re.compile(rf"public .*? ({name_pattern})\(.*?\n\s+descriptor: (\S+)")
    return [(name, descriptor) for name, descriptor in re.findall(pattern, text)]


def _parameter_types(descriptor: str) -> list[str]:
    """The parameter portion of a JVM descriptor, split into one erased type per
    slot — `domain/symbols.parameter_types`'s own algorithm, restated here so this
    probe has no import dependency on the shipped engine it is measuring against."""
    params = descriptor[1 : descriptor.index(")")]
    types = []
    i = 0
    while i < len(params):
        start = i
        while params[i] == "[":
            i += 1
        if params[i] == "L":
            i = params.index(";", i) + 1
        else:
            i += 1
        types.append(params[start:i])
    return types


def topic_argument(descriptor: str) -> int | None:
    """The position of the first parameter shaped like a topic or a subscription built
    from one, or `None` when no parameter carries one of those shapes at all (`Producer`
    row's own answer — every method there takes settings and a producer/committer, never
    a topic)."""
    for index, parameter in enumerate(_parameter_types(descriptor)):
        if parameter in _TOPIC_SHAPES:
            return index
    return None


def main() -> None:
    coordinates = list(dict.fromkeys(coordinate for coordinate, _ in CLASSES))
    read = {c: checked(c) for c in coordinates}

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w62_pekko_kafka_surface/run.sh`, which runs")
    print("`sweep.py`. **Every version in the headers below is the one the JAR itself")
    print("reported** — out of its own `META-INF/maven/.../pom.properties` or its")
    print("manifest's `Implementation-Version` — and **not the version the coordinate")
    print("list asked for**; `checked` compares the two and ABORTS when they disagree.\n")
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

    print("### Every method matching `plainSource|committableSource|atMostOnceSource|")
    print("### plainPartitionedSource|committablePartitionedSource|topics|topicPattern|")
    print("### assignment|plainSink|committableSink|flexiFlow`, and which position (if")
    print("### any) carries a topic or a subscription built from one\n")
    for coordinate, internal in CLASSES:
        jar = read[coordinate][0]
        methods = topic_methods(jar, internal, _NAME_PATTERN)
        print(f"**`{internal.replace('/', '.')}`** ({coordinate})\n")
        print("| # | method | descriptor | topic argument |")
        print("|---|---|---|---|")
        if not methods:
            # `_NAME_PATTERN` itself contains `|`, and inside a table ROW every
            # unescaped `|` divides a cell — even inside backticks
            # (`tests/architecture/test_markdown_tables.py`'s own rule). `\|` is the
            # only thing that protects one.
            escaped_pattern = _NAME_PATTERN.replace("|", r"\|")
            print(f"| — | *(no `{escaped_pattern}` method found)* | — | — |")
            print()
            continue
        for n, (name, descriptor) in enumerate(methods, start=1):
            position = topic_argument(descriptor)
            cell = str(position) if position is not None else "*(none)*"
            print(f"| {n} | `{name}` | `{descriptor}` | {cell} |")
        print()


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
