"""W14 — do class-level and method-level listeners register independently?
(F2 §3.5.)

`spring-kafka.yml` treats a class-level `@KafkaListener` as a PREFIX for the
methods inside it. That is right for one shape and wrong for another, and the
design says to measure per framework before encoding the distinction rather than
fixing the instance that was noticed.

Three questions, each answered from the framework's own bytecode rather than from
its documentation:

1. **Where may each annotation be written?** `@Target` is the framework's own
   statement, and it settles whether the class-plus-method shape can arise at all.
2. **Does the class-level "handler" annotation carry a destination?** An
   annotation that names no destination cannot be an independent registration —
   it can only select which method serves one.
3. **Does the framework process the two independently?** The registrar's own
   method set says whether a class-level annotation and a method-level one take
   separate paths, and whether either excludes the other.

Then, separately: what Sextant derives today for each shape.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = REPO / "src" / "sextant" / "catalogs"
M2 = Path.home() / ".m2" / "repository"

# `group:artifact:version`, and the classes read out of each. The versions are
# the ones the fixture poms pin, so a verdict here and a verdict from the fixture
# describe the same libraries.
LIBRARIES = (
    (
        "org.springframework.kafka:spring-kafka:3.1.4",
        "kafka",
        "org/springframework/kafka/annotation",
        ("KafkaListener", "KafkaHandler"),
        "KafkaListenerAnnotationBeanPostProcessor",
    ),
    (
        "org.springframework.amqp:spring-rabbit:3.1.4",
        "rabbit",
        "org/springframework/amqp/rabbit/annotation",
        ("RabbitListener", "RabbitHandler"),
        "RabbitListenerAnnotationBeanPostProcessor",
    ),
    (
        "io.awspring.cloud:spring-cloud-aws-sqs:3.1.1",
        "sqs",
        "io/awspring/cloud/sqs/annotation",
        ("SqsListener",),
        "AbstractListenerAnnotationBeanPostProcessor",
    ),
)


class ProbeError(RuntimeError):
    """Something the run could not establish. ABORTS rather than warning."""


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
    """The version the ARCHIVE states for itself, and WHERE it states it.

    Two places, because the three artifacts here do not agree on one: Spring's
    own jars carry no `META-INF/maven/*/pom.properties` at all and write
    `Implementation-Version` in the manifest, while `spring-cloud-aws-sqs` writes
    both. Maven's `pom.properties` is preferred where present — it is the build's
    own record of what it produced — and the source is REPORTED beside the
    version rather than left implicit, so a reader can tell which of the two
    answered. (`jaxb-api-2.3.1.jar`, in W11, is why that matters: it writes
    `2.3.0` in the manifest and `2.3.1` in its `pom.properties`.)

    Raises rather than defaulting: a missing self-report is exactly where a
    hand-written column would go unchallenged (CP-5).
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
        except KeyError as missing:
            raise ProbeError(
                f"{jar.name} carries neither a pom.properties nor a manifest — "
                f"it reports no version of its own"
            ) from missing
    for line in manifest.splitlines():
        if line.lower().startswith("implementation-version:"):
            return line.split(":", 1)[1].strip(), "MANIFEST.MF"
    raise ProbeError(f"{jar.name} states no version in either its pom.properties or its manifest")


def checked(artifact: str) -> tuple[Path, str, str]:
    """The jar, the version IT reports and where it reported it — aborting when
    that disagrees with the coordinate that resolved it rather than printing a
    version never read."""
    jar = resolve(artifact)
    reported, source = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own {source} while the coordinate "
            f"asked for {requested!r}. Fix run.sh rather than labelling a column with a "
            f"version this run did not read."
        )
    return jar, reported, source


def _javap(jar: Path, internal: str, *flags: str) -> str:
    """`javap` output for one class inside one jar.

    ABORTS when the jar does not carry the class, rather than returning "".
    An empty string reaches the tables as `—` for a `@Target` and `**NO**` for a
    destination attribute — which are this probe's own CONCLUSIONS, so a typo'd
    package or a class moved in a later release printed the verdict silently and
    exited 0. Every other unestablished thing here aborts; this one did not.
    """
    with tempfile.TemporaryDirectory() as into:
        try:
            with zipfile.ZipFile(jar) as archive:
                archive.extract(f"{internal}.class", into)
        except KeyError as missing:
            raise ProbeError(
                f"{jar.name} does not carry {internal}.class. Fix the class name or the "
                f"coordinate in run.sh rather than reading its absence as an answer."
            ) from missing
        return subprocess.run(
            ["javap", *flags, "-p", str(Path(into) / f"{internal}.class")],
            capture_output=True,
            text=True,
            check=False,
        ).stdout


def targets(jar: Path, internal: str) -> tuple[str, ...]:
    """The `ElementType`s an annotation's own `@Target` names — the framework's
    statement about where it may be written, not a reading of its javadoc."""
    listed = _javap(jar, internal, "-v")
    found = re.search(r"java\.lang\.annotation\.Target\(\s*value=\[([^\]]*)\]", listed)
    if not found:
        return ()
    return tuple(
        part.strip().rsplit(".", 1)[-1] for part in found.group(1).split(",") if part.strip()
    )


def attributes(jar: Path, internal: str) -> tuple[str, ...]:
    """An annotation's declared attributes, in declaration order."""
    return tuple(re.findall(r"\b(\w+)\(\);", _javap(jar, internal)))


def class_level_gate(jar: Path, internal: str) -> str:
    """The bytecode that GUARDS the class-level path, verbatim.

    Verbatim rather than interpreted, which is CP-17's own convention for exactly
    this question ("where the rule is an ALGORITHM, the discovery method VERBATIM
    out of the sources jar"). The first version of this probe read the registrar's
    method SIGNATURES and concluded that Kafka and Rabbit share a gate. They do
    not, and no signature could have said so. A summarising version then picked up
    a field loaded AFTER the branch as though it were the condition.

    So: the instructions from the last conditional branch before
    `processMultiMethodListeners`/`createAndConfigureMultiMethodEndpoint` up to
    that call. Short, and it says what is tested without this function deciding
    what the test means.
    """
    listed = _javap(jar, internal, "-c")
    call = next(
        (
            name
            for name in ("processMultiMethodListeners", "createAndConfigureMultiMethodEndpoint")
            if name in listed
        ),
        None,
    )
    if call is None:
        return "no class-level path in this jar"
    body = listed.split("public java.lang.Object postProcessAfterInitialization")
    region = body[1] if len(body) > 1 else listed
    before = region.split(call)[0]
    lines = [line.strip() for line in before.strip().splitlines() if line.strip()]
    branch = max(
        (i for i, line in enumerate(lines) if re.search(r"\b(if\w*|goto)\b\s+\d+", line)),
        default=None,
    )
    if branch is None:
        return "unguarded"
    window = lines[max(0, branch - 3) : branch + 1]
    return "<br>".join(_readable(line) for line in window)


def _readable(line: str) -> str:
    """One `javap -c` line with its constant-pool comment reduced to the NAME it
    refers to. `// Field …TypeMetadata.handlerMethods:[Ljava/lang/reflect/Method;`
    becomes `// handlerMethods` — the field being tested, which is the whole point
    of showing the line; a naive "last identifier" trim yielded `Method`, the type
    of the array rather than the thing loaded."""
    named = re.search(r"//\s*(?:Field|Method|class|InterfaceMethod)\s+\S*?([\w$]+):", line)
    if named is not None:
        line = line.split("//")[0].rstrip() + f"  // {named.group(1)}"
    return re.sub(r"\s+", " ", line.split("#")[0].rstrip() if "//" not in line else line)


def registrar_paths(jar: Path, internal: str) -> tuple[str, ...]:
    """The registrar's own methods whose PARAMETERS include a `java.lang.Class`
    or a `java.lang.reflect.Method` — which is what says whether a class-level
    annotation and a method-level one take separate paths.

    The parameter list, not the whole signature line: matching the bare word
    `Method` anywhere on the line pulled in every method taking a
    `MessageHandlerMethodFactory`, and a table where nearly every row matches
    says nothing. Lambdas (`lambda$…`) are dropped for the same reason — they are
    the compiler's methods, not the registrar's.
    """
    found = []
    for line in _javap(jar, internal).splitlines():
        signature = re.search(r"\b(\w+)\((.*)\);", line)
        if signature is None or signature.group(1).startswith("lambda$"):
            continue
        # javac's own synthetic accessors get numeric names in `javap` output;
        # they are not paths the registrar declares.
        if signature.group(1)[0].isdigit():
            continue
        parameters = signature.group(2)
        takes = []
        if re.search(r"\bjava\.lang\.Class\b", parameters):
            takes.append("Class")
        if re.search(r"\bjava\.lang\.reflect\.Method\b", parameters):
            takes.append("Method")
        if takes:
            found.append(f"{signature.group(1)}({'+'.join(takes)})")
    return tuple(found)


# --- what Sextant derives today ------------------------------------------

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_DOC = Document(
    document_id="doc_1",
    relative_path="com/acme/Orders.java",
    module_id="com.acme:orders-service",
    language="java",
    sextant_version="0.1.0",
    fact_schema_version=2,
    scanner_id="asm",
    content_hash="sha256:a",
    origin_entry="target/classes",
    origin_tier=OriginTier.MODULE_OUTPUT,
    redaction_set_hash="sha256:b",
)
_LISTENER = "org/springframework/kafka/annotation/KafkaListener#"
_HANDLER = "org/springframework/kafka/annotation/KafkaHandler#"
CAPABILITIES = {"annotation_args", "typed_signatures", "type_annotations", "nested_annotation_args"}


def listener_facts(*, class_topic: str | None, members: tuple[tuple[str, str | None], ...]):
    """A class carrying an optional class-level `@KafkaListener`, and one method
    per `(annotation, topic)` in `members`.

    Several members, because the shape that decides whether the §3.5 conjunct
    LOSES anything is the three-part one: a class-level listener, a
    `@KafkaHandler` serving it, and a method-level listener of its own beside
    them. A two-part fixture cannot tell "the class topic is not composed" from
    "the class topic is gone"."""
    owner = _MODULE + "com/acme/Orders#"
    facts: list = [
        SymbolFact(document_id="doc_1", symbol=owner, construct_kind=ConstructKind.CLASS),
    ]
    if class_topic is not None:
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=owner,
                retention="runtime",
                use=AnnotationUse(annotation=_LISTENER, args={"topics": [class_topic]}),
            )
        )
    for index, (annotation, topic) in enumerate(members):
        method = owner + f"onEvent{index}(sig_{index})."
        facts.append(
            SymbolFact(
                document_id="doc_1",
                symbol=method,
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
                signature=Signature(parameters=[], returns=TypeRef(symbol="V")),
            )
        )
        facts.append(
            AnnotationFact(
                document_id="doc_1",
                target=method,
                retention="runtime",
                use=AnnotationUse(
                    annotation=annotation,
                    args={} if topic is None else {"topics": [topic]},
                ),
            )
        )
    return facts


def catalog(catalog_id: str) -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id)


def derived(facts: list) -> list[dict]:
    with tempfile.TemporaryDirectory() as into:
        root = Path(into)
        write_fact_file(root / "facts" / "Orders.jsonl", _DOC, facts)
        workspace = DuckDbWorkspace(root / "ws.duckdb")
        workspace.load_facts(root / "facts")
        derive_endpoints(workspace, [catalog("spring-kafka")], capabilities=CAPABILITIES)
        rows = workspace.query("endpoints")
        workspace.close()
    return rows


def main() -> None:
    print("## Observations\n")
    print(
        "Verbatim from `scripts/probes/w14_listener_registration/run.sh`, which runs "
        "`sweep.py`. **Every version below is the one the JAR itself reported** — and "
        "**not the version the coordinate list asked for**. WHERE each jar states it "
        "differs, so the run says which file answered rather than naming one source for "
        "all three: Maven's `META-INF/maven/*/pom.properties` where present, the "
        "manifest's `Implementation-Version` otherwise. Spring's own jars carry no "
        "`pom.properties` at all. `sweep.py` compares what it read against the coordinate "
        "and ABORTS when they disagree, rather than printing a version it did not read.\n"
    )

    read = {}
    for artifact, _, package, annotations, registrar in LIBRARIES:
        jar, version, source = checked(artifact)
        read[artifact] = (jar, version, package, annotations, registrar, source)

    order = sorted({entry[1] for entry in read.values()})
    print("| what the run read | " + " | ".join(order) + " |")
    print("|---" * (len(order) + 1) + "|")
    for label, pick in (
        ("artifacts reporting this version", lambda entry: entry[0].name.rsplit("-", 1)[0]),
        ("annotations read out of it", lambda entry: str(len(entry[3]))),
        ("where the jar states that version", lambda entry: entry[5]),
    ):
        cells = []
        for version in order:
            matching = [entry for entry in read.values() if entry[1] == version]
            cells.append(", ".join(sorted({pick(entry) for entry in matching})))
        print(f"| {label} | " + " | ".join(cells) + " |")
    print()

    print("### 1. Where each annotation may be written, and what it declares\n")
    print("| annotation | `@Target` | declares a destination? | attributes |")
    print("|---|---|---|---|")
    destination_words = (
        "topics",
        "topicPattern",
        "topicPartitions",
        "queues",
        "queueNames",
        "value",
        "bindings",
        "queuesToDeclare",
    )
    for artifact, _, package, annotations, _ in LIBRARIES:
        jar = read[artifact][0]
        for name in annotations:
            declared = attributes(jar, f"{package}/{name}")
            names_destination = [a for a in declared if a in destination_words]
            print(
                f"| `{name}` | {', '.join(targets(jar, f'{package}/{name}')) or '—'} "
                f"| {'**' + ', '.join(names_destination) + '**' if names_destination else '**NO**'} "
                f"| {len(declared)} |"
            )

    print("\n### 2. The framework's own registrar: are the two levels separate paths?\n")
    print(
        "The second column is read from `postProcessAfterInitialization`'s own BYTECODE — "
        "what it loads immediately before branching to the class-level path. The first is "
        "the registrar's method signatures, which can show that two paths EXIST and can "
        "never show whether one excludes the other.\n"
    )
    print(
        "| registrar | methods taking a `Class` or a `Method` | what gates the class-level path |"
    )
    print("|---|---|---|")
    for artifact, _, package, _, registrar in LIBRARIES:
        jar = read[artifact][0]
        paths = registrar_paths(jar, f"{package}/{registrar}")
        try:
            gate = class_level_gate(jar, f"{package}/{registrar}")
        except ProbeError:
            gate = "no `postProcessAfterInitialization` (see section 1)"
        print(f"| `{registrar}` | {', '.join(f'`{p}`' for p in paths) or '—'} | {gate} |")

    print("\n### 3. What Sextant derives, per shape (`spring-kafka.yml`)\n")
    print("| class-level `@KafkaListener` | members | rows | paths derived |")
    print("|---|---|---|---|")
    for label, class_topic, members, carries in (
        ("—", None, ((_LISTENER, "payments"),), "one `@KafkaListener(topics=payments)`"),
        ("`topics=orders`", "orders", ((_HANDLER, None),), "one `@KafkaHandler`"),
        (
            "`topics=orders`",
            "orders",
            ((_LISTENER, "payments"),),
            "one `@KafkaListener(topics=payments)`",
        ),
        (
            "`topics=orders`",
            "orders",
            ((_HANDLER, None), (_LISTENER, "payments")),
            "a `@KafkaHandler` AND a `@KafkaListener(topics=payments)`",
        ),
    ):
        rows = derived(listener_facts(class_topic=class_topic, members=members))
        paths = ", ".join(sorted(f"`{row['path']}`" for row in rows)) or "—"
        print(f"| {label} | {carries} | {len(rows)} | {paths} |")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"W14 ABORTED: {error}", file=sys.stderr)
        raise SystemExit(1) from error
