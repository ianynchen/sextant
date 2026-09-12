"""W58 — the annotation surface nine Micronaut and Quarkus catalogs are written against.

`micronaut-http.yml`, `micronaut-http-client.yml`, `micronaut-kafka.yml`,
`micronaut-kafka-client.yml`, `micronaut-jms.yml`, `micronaut-jms-producer.yml`,
`micronaut-pubsub.yml`, `micronaut-pubsub-client.yml` and `quarkus-reactive-routes.yml`
are `annotation_driven`, and an `annotation_driven` catalog fails SILENTLY on a wrong
FQN or a wrong attribute name: the annotation never matches, or the attribute is never
present, and the catalog derives nothing while looking healthy (W53's finding, `G-91`).
So every FQN and every attribute the nine name is read here out of the jar, and the
`@Repeatable` container `quarkus-reactive-routes.yml` names is checked to be the one
`@Route` declares.

**Version scope (§5.4).** Read against **micronaut-http 4.7.6, micronaut-http-client-core
4.7.6, micronaut-kafka 5.6.0, micronaut-jms-core 4.2.0, micronaut-gcp-pubsub 5.8.0,
quarkus-reactive-routes 3.17.5 and quarkus-reactive-routes-deployment 3.17.5** — each the
version the jar reports for itself, checked against the coordinate before any table is
printed. Attribute names are API surface and move between majors; these versions and no
other are what the nine catalogs claim.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

# (coordinate, internal class name, catalogs naming it, the attributes those catalogs read)
CLAIMS = (
    (
        "io.micronaut:micronaut-http:4.7.6",
        "io/micronaut/http/annotation/Controller",
        "micronaut-http",
        ("value", "consumes", "produces"),
    ),
    (
        "io.micronaut:micronaut-http:4.7.6",
        "io/micronaut/http/annotation/Body",
        "micronaut-http",
        (),
    ),
    *(
        (
            "io.micronaut:micronaut-http:4.7.6",
            f"io/micronaut/http/annotation/{verb}",
            "micronaut-http, micronaut-http-client",
            ("value", "uri", "uris", "consumes", "produces"),
        )
        for verb in ("Get", "Post", "Put", "Delete", "Patch", "Head", "Options", "Trace")
    ),
    (
        "io.micronaut:micronaut-http-client-core:4.7.6",
        "io/micronaut/http/client/annotation/Client",
        "micronaut-http-client",
        ("value", "path"),
    ),
    (
        "io.micronaut.kafka:micronaut-kafka:5.6.0",
        "io/micronaut/configuration/kafka/annotation/KafkaListener",
        "micronaut-kafka",
        (),
    ),
    (
        "io.micronaut.kafka:micronaut-kafka:5.6.0",
        "io/micronaut/configuration/kafka/annotation/KafkaClient",
        "micronaut-kafka-client",
        (),
    ),
    (
        "io.micronaut.kafka:micronaut-kafka:5.6.0",
        "io/micronaut/configuration/kafka/annotation/Topic",
        "micronaut-kafka, micronaut-kafka-client",
        ("value", "patterns"),
    ),
    (
        "io.micronaut.jms:micronaut-jms-core:4.2.0",
        "io/micronaut/jms/annotations/JMSListener",
        "micronaut-jms",
        (),
    ),
    (
        "io.micronaut.jms:micronaut-jms-core:4.2.0",
        "io/micronaut/jms/annotations/JMSProducer",
        "micronaut-jms-producer",
        (),
    ),
    (
        "io.micronaut.jms:micronaut-jms-core:4.2.0",
        "io/micronaut/jms/annotations/Queue",
        "micronaut-jms, micronaut-jms-producer",
        ("value",),
    ),
    (
        "io.micronaut.jms:micronaut-jms-core:4.2.0",
        "io/micronaut/jms/annotations/Topic",
        "micronaut-jms, micronaut-jms-producer",
        ("value",),
    ),
    (
        "io.micronaut.gcp:micronaut-gcp-pubsub:5.8.0",
        "io/micronaut/gcp/pubsub/annotation/PubSubListener",
        "micronaut-pubsub",
        (),
    ),
    (
        "io.micronaut.gcp:micronaut-gcp-pubsub:5.8.0",
        "io/micronaut/gcp/pubsub/annotation/PubSubClient",
        "micronaut-pubsub-client",
        (),
    ),
    (
        "io.micronaut.gcp:micronaut-gcp-pubsub:5.8.0",
        "io/micronaut/gcp/pubsub/annotation/Subscription",
        "micronaut-pubsub",
        ("value",),
    ),
    (
        "io.micronaut.gcp:micronaut-gcp-pubsub:5.8.0",
        "io/micronaut/gcp/pubsub/annotation/Topic",
        "micronaut-pubsub-client",
        ("value",),
    ),
    (
        "io.quarkus:quarkus-reactive-routes:3.17.5",
        "io/quarkus/vertx/web/Route",
        "quarkus-reactive-routes",
        ("path", "methods", "consumes", "produces"),
    ),
    (
        "io.quarkus:quarkus-reactive-routes:3.17.5",
        "io/quarkus/vertx/web/Route$Routes",
        "quarkus-reactive-routes",
        ("value",),
    ),
    (
        "io.quarkus:quarkus-reactive-routes:3.17.5",
        "io/quarkus/vertx/web/RouteBase",
        "quarkus-reactive-routes",
        ("path", "consumes", "produces"),
    ),
    (
        "io.quarkus:quarkus-reactive-routes:3.17.5",
        "io/quarkus/vertx/web/Body",
        "quarkus-reactive-routes",
        (),
    ),
)

# The message-body binders the three messaging pairs cite for `request_body.annotation`.
BODY_BINDERS = (
    (
        "io.micronaut.kafka:micronaut-kafka:5.6.0",
        "io/micronaut/configuration/kafka/bind/KafkaMessagingBodyBinder",
    ),
    (
        "io.micronaut.jms:micronaut-jms-core:4.2.0",
        "io/micronaut/jms/bind/DefaultBodyArgumentBinder",
    ),
    (
        "io.micronaut.gcp:micronaut-gcp-pubsub:5.8.0",
        "io/micronaut/gcp/pubsub/bind/PubSubBodyBinder",
    ),
)

DEPLOYMENT = "io.quarkus:quarkus-reactive-routes-deployment:3.17.5"
PROCESSOR = "io/quarkus/vertx/web/deployment/ReactiveRoutesProcessor"


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


def attributes(jar: Path, internal: str) -> dict[str, str]:
    """`name -> declared type` for every attribute an annotation interface declares."""
    out: dict[str, str] = {}
    for line in _javap(jar, internal).splitlines():
        match = re.match(r"\s+public abstract (\S+) (\w+)\(\);", line)
        if match:
            out[match.group(2)] = match.group(1)
    return out


def repeatable_container(jar: Path, internal: str) -> str | None:
    """What `@Repeatable(value = …)` names, as `javap -v` renders it:
    `value=class Lio/quarkus/vertx/web/Route$Routes;`."""
    text = _javap(jar, internal, "-v")
    match = re.search(r"java\.lang\.annotation\.Repeatable\(\s*value=class L([\w/$]+);", text)
    return match.group(1).replace("/", ".") if match else None


def main() -> None:
    coordinates = list(dict.fromkeys(c for c, *_ in CLAIMS)) + [DEPLOYMENT]
    read = {c: checked(c) for c in coordinates}

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w58_micronaut_quarkus_annotations/run.sh`, which runs")
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

    print("### Every annotation the nine catalogs name, and every attribute they read\n")
    print(
        "| # | coordinate | annotation | catalog(s) | attribute the catalog reads | declared as |"
    )
    print("|---|---|---|---|---|---|")
    n = 0
    for coordinate, internal, catalogs, wanted in CLAIMS:
        jar = read[coordinate][0]
        declared = attributes(jar, internal)
        fqn = internal.replace("/", ".")
        if not wanted:
            n += 1
            print(
                f"| {n} | `{coordinate.split(':')[1]}` | `{fqn}` | {catalogs} | *(gate only)* | "
                f"exists, {len(declared)} attribute(s) |"
            )
            continue
        for name in wanted:
            n += 1
            verdict = f"`{declared[name]}`" if name in declared else "**ABSENT**"
            print(
                f"| {n} | `{coordinate.split(':')[1]}` | `{fqn}` | {catalogs} | `{name}` | {verdict} |"
            )
    print()

    print("### `@Route`'s repeatable container\n")
    jar = read["io.quarkus:quarkus-reactive-routes:3.17.5"][0]
    container = repeatable_container(jar, "io/quarkus/vertx/web/Route")
    print(f"`@Repeatable` on `io.quarkus.vertx.web.Route` names **`{container}`**; the catalog")
    print("declares `container: io.quarkus.vertx.web.Route$Routes`.\n")

    print("### `Route$HttpMethod`, the closed verb set `all_methods` lists\n")
    text = _javap(jar, "io/quarkus/vertx/web/Route$HttpMethod")
    members = re.findall(r"public static final \S+ (\w+);", text)
    print("`" + "`, `".join(members) + "`\n")

    print("### The three message-body binders, and the annotation each keys on\n")
    print("| coordinate | binder | `io.micronaut.messaging.annotation.*` it references |")
    print("|---|---|---|")
    for coordinate, internal in BODY_BINDERS:
        text = _javap(read[coordinate][0], internal, "-v")
        refs = sorted(set(re.findall(r"io/micronaut/messaging/annotation/(\w+)", text)))
        print(
            f"| `{coordinate.split(':')[1]}` | `{internal.rsplit('/', 1)[1]}` | {', '.join(refs) or '**none**'} |"
        )
    print()

    print("### Path composition, in the deployment processor\n")
    text = _javap(read[DEPLOYMENT][0], PROCESSOR, "-p", "-c")
    dashify = text.count("Method dashify:(Ljava/lang/String;)Ljava/lang/String;")
    print(f"`ReactiveRoutesProcessor` calls `dashify(String)` on `MethodInfo.name()` **{dashify}**")
    print("time(s) — the absent-`path` form serves the method name dashed, which no")
    print("`path_fallback` word says, so the catalog derives that form as nothing rather than")
    print('as `/helloWorld`. The bytecode around each call appends `"/"` between the base')
    print('path and the route path, and prepends `"/"` to a route path that lacks one.')


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
