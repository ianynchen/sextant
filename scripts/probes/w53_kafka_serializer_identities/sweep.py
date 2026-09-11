"""W53 — does every serializer class `spring-kafka-media.yml` names exist? (`G-88`)

The file maps configured serializer/deserializer CLASSES to two different
answers: `values` gives a media type, `format_from` gives the wire format. Between
them they name fourteen classes, **eight of them Confluent's**, and when A2
audited the file no `io.confluent` artifact resolved in `~/.m2` or the Gradle
cache — so those eight were unverified spellings.

A wrong class name here is silent in the same way a wrong annotation FQN is: the
configured class simply is not in the map, and D02's rule is that a class absent
from it stamps nothing rather than guessing. The row loses its format and nobody
is told a name was wrong.

`packages.confluent.io` serves the artifacts. This probe opens all four of them,
plus the two that carry the six non-Confluent classes.

**Version scope (§5.4).** Read against **Confluent 7.6.0** (four serializer
artifacts), **spring-kafka 3.1.4** and **kafka-clients 3.6.2**. A class's package
is API surface and can move between major versions; these are the versions read.
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

CONFLUENT = "https://packages.confluent.io/maven/"

# Every class the catalog names, and the artifact expected to carry it. The
# catalog is the source of the class list; this file is the source of where to
# look, which is the half the catalog does not state.
CLAIMS = (
    (
        "org.springframework.kafka:spring-kafka:3.1.4",
        None,
        "org/springframework/kafka/support/serializer/JsonSerializer",
    ),
    (
        "org.springframework.kafka:spring-kafka:3.1.4",
        None,
        "org/springframework/kafka/support/serializer/JsonDeserializer",
    ),
    (
        "org.apache.kafka:kafka-clients:3.6.2",
        None,
        "org/apache/kafka/common/serialization/StringSerializer",
    ),
    (
        "org.apache.kafka:kafka-clients:3.6.2",
        None,
        "org/apache/kafka/common/serialization/StringDeserializer",
    ),
    (
        "org.apache.kafka:kafka-clients:3.6.2",
        None,
        "org/apache/kafka/common/serialization/ByteArraySerializer",
    ),
    (
        "org.apache.kafka:kafka-clients:3.6.2",
        None,
        "org/apache/kafka/common/serialization/ByteArrayDeserializer",
    ),
    (
        "io.confluent:kafka-avro-serializer:7.6.0",
        CONFLUENT,
        "io/confluent/kafka/serializers/KafkaAvroSerializer",
    ),
    (
        "io.confluent:kafka-avro-serializer:7.6.0",
        CONFLUENT,
        "io/confluent/kafka/serializers/KafkaAvroDeserializer",
    ),
    (
        "io.confluent:kafka-protobuf-serializer:7.6.0",
        CONFLUENT,
        "io/confluent/kafka/serializers/protobuf/KafkaProtobufSerializer",
    ),
    (
        "io.confluent:kafka-protobuf-serializer:7.6.0",
        CONFLUENT,
        "io/confluent/kafka/serializers/protobuf/KafkaProtobufDeserializer",
    ),
    (
        "io.confluent:kafka-json-schema-serializer:7.6.0",
        CONFLUENT,
        "io/confluent/kafka/serializers/json/KafkaJsonSchemaSerializer",
    ),
    (
        "io.confluent:kafka-json-schema-serializer:7.6.0",
        CONFLUENT,
        "io/confluent/kafka/serializers/json/KafkaJsonSchemaDeserializer",
    ),
    (
        "io.confluent:kafka-json-serializer:7.6.0",
        CONFLUENT,
        "io/confluent/kafka/serializers/KafkaJsonSerializer",
    ),
    (
        "io.confluent:kafka-json-serializer:7.6.0",
        CONFLUENT,
        "io/confluent/kafka/serializers/KafkaJsonDeserializer",
    ),
)

CATALOG = REPO / "src" / "sextant" / "catalogs" / "spring-kafka-media.yml"


class ProbeError(RuntimeError):
    """Anything that would otherwise put an unmeasured cell in a table."""


def resolve(artifact: str, repository: str | None = None) -> Path:
    group, name, version = artifact.split(":")
    jar = M2 / Path(group.replace(".", "/")) / name / version / f"{name}-{version}.jar"
    if not jar.is_file():
        subprocess.run(
            [
                "mvn",
                "-q",
                "-B",
                "dependency:get",
                "-Dtransitive=false",
                *([f"-DremoteRepositories=confluent::::{repository}"] if repository else []),
                f"-Dartifact={artifact}",
            ],
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
    # Kafka's own route. `kafka-clients` ships a 25-byte manifest with no
    # `Implementation-Version` and no maven metadata at all, and states its
    # version in `kafka/kafka-version.properties` instead — measured, not
    # assumed, so the honest identity here is `reported` rather than the
    # `assumed` a reader of the first two routes alone would have written.
    with zipfile.ZipFile(jar) as archive:
        try:
            properties = archive.read("kafka/kafka-version.properties")
        except KeyError:
            properties = b""
    for line in properties.decode("utf-8", "replace").splitlines():
        if line.strip().startswith("version="):
            return line.split("=", 1)[1].strip(), "kafka/kafka-version.properties"
    raise ProbeError(
        f"{jar.name} states no version in its pom.properties, its manifest, or "
        f"kafka/kafka-version.properties"
    )


def checked(artifact: str, repository: str | None = None) -> tuple[Path, str, str]:
    jar = resolve(artifact, repository)
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


def catalog_classes() -> tuple[set[str], set[str]]:
    """The class names the shipped catalog actually maps, read out of it rather
    than restated here — so a class added to the catalog and not to this probe
    shows up as a row this probe never looked for."""
    import yaml

    # `values` and `format_from` live under `media_from_config`, not at the top of
    # `matches` — read by path rather than guessed, so a restructure fails loudly
    # here instead of silently reporting two empty sets.
    block = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["matches"]["media_from_config"]
    return set(block["values"]), set(block["format_from"])


def main() -> None:
    read = {}
    for coordinate, repository, _ in CLAIMS:
        if coordinate not in read:
            read[coordinate] = checked(coordinate, repository)

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w53_kafka_serializer_identities/run.sh`, which runs")
    print("`sweep.py`. **Every version in the headers below is the one the JAR itself")
    print("reported** — out of its own `pom.properties` or its manifest's")
    print("`Implementation-Version`, and **not the version the coordinate list asked for**;")
    print("`checked` compares the two and ABORTS when they disagree.\n")
    versions = list(dict.fromkeys(c.split(":")[2] for c in read))
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

    values, formats = catalog_classes()
    print("### Does every class the catalog names exist?\n")
    print("| class | artifact that carries it | present | in `values` | in `format_from` |")
    print("|---|---|---|---|---|")
    looked_for = set()
    for coordinate, _, internal in CLAIMS:
        fqn = internal.replace("/", ".")
        looked_for.add(fqn)
        found = carries(read[coordinate][0], internal)
        print(
            f"| `{fqn}` | `{coordinate.split(':')[1]}` | {'**yes**' if found else '**NO**'} "
            f"| {'yes' if fqn in values else '—'} | {'yes' if fqn in formats else '—'} |"
        )
    print()
    unchecked = sorted((values | formats) - looked_for)
    print(f"**Named in the catalog and not opened by this probe:** {unchecked or 'none'}.")
    print(f"**`values` holds {len(values)}; `format_from` holds {len(formats)}.**")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
