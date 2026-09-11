"""CP-17's measurement half: which listener shapes a framework registers that a
catalog reaches only by naming a CONTAINER or a CLASS-LEVEL prefix, and whether
the sibling annotations a catalog declines to name are repeatable at all.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. Like CP-7, CP-13, CP-14, CP-15 and CP-16 it reads each jar's own
identity out of its own bytes before it measures anything and refuses to file a
cell under a version the artifact did not claim (GUIDELINES §5.4, and CP-5's
failure it exists to prevent).

Every question answers PER RESOLVED ARTIFACT rather than once, so a rule read
against two minors of a framework prints two rows and §5.4's scope is the rows
themselves rather than a sentence about them.

**An absent class is an ANSWER here, not an error.** CP-16 could assume every
class it named existed in every jar; this probe cannot, because half its
question is *"does this framework ship a container / a handler annotation at
all?"* — and `io.awspring.cloud.sqs.annotation.SqsHandler` exists at 4.1.1 and
not at 3.1.1, which is the finding rather than a broken run. So a class `javap`
cannot find prints `ABSENT FROM THIS JAR` and the run continues; every OTHER
`javap` failure still aborts.

**Question 6 reads SOURCE, and that is deliberate.** Where the framework's rule
is an ALGORITHM rather than a predicate — a union of two annotation reads, a
branch on whether a class-level annotation is present — chasing it through
`invokevirtual` in a disassembly is how a rule goes unopened for a round. A
sources jar is the literal source of the bytecode beside it, resolved at the
same coordinate, so the method body printed here is the rule at that exact
version rather than a paraphrase of it.

Everything it prints is the table `cp17_containers_and_class_level.md` carries
verbatim.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# The manifest's own `Name: value`.
_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
# One `javap -c` instruction line: ordinal, mnemonic, then whatever operands and
# trailing `// comment` follow. Operands are matched loosely for CP-11's reason —
# `invokeinterface #25,  2` carries two, and a pattern assuming one silently ENDS
# the body at the first such instruction.
_INSTRUCTION = re.compile(r"^\s*\d+:\s+(\S+)(.*)$")
# One declared annotation attribute, as `javap -s` prints it.
_ATTRIBUTE = re.compile(r"^\s{2}public abstract (\S+) ([\w$]+)\(\);\s*$")
# `javap -v`'s rendering of a meta-annotation's own name and value lines.
_META_TYPE = re.compile(r"^\s{4}([\w.$]+)\($")
_META_VALUE = re.compile(r"^\s{6}value=(.+)$")

# Markdown tables are `|`-delimited, so an instruction sequence is joined with
# something else: a `|` inside a cell silently splits the row, and a table
# nobody can read back is a table nobody re-checks.
_STEP = " ; "

# What `javap` says when the class is not in the archive at all. Matched rather
# than inferred from the exit status, because every OTHER javap failure — a
# malformed archive, a JDK too old for the class-file version — must still abort
# the run rather than print a cell claiming the class is missing.
_NOT_FOUND = re.compile(r"^Error: class not found: ", re.MULTILINE)

# The sentence an absent class prints. One string, so a reader of the table can
# tell "this framework ships no such annotation" from "this probe did not ask".
_ABSENT = "ABSENT FROM THIS JAR"

# The meta-annotations question 2 keeps. `@Target` says where a declaration may
# legally sit — the conjunct `derive_endpoints.handler-is-a-method` rests on —
# and `@Repeatable` names the container javac folds repeats into. `@Retention`
# and `@Documented` say nothing about either.
_META_KEPT = ("java.lang.annotation.Target", "java.lang.annotation.Repeatable")

# Spring's annotation-search entry points, kept by question 5 for CP-16's
# reason: which one is called says whether a meta-annotated, inherited or
# repeated declaration is found at all.
_SEARCHES = (
    "org/springframework/core/annotation/AnnotatedElementUtils.",
    "org/springframework/core/annotation/AnnotationUtils.",
    "org/springframework/core/annotation/MergedAnnotations",
)


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


@dataclass(frozen=True)
class Family:
    """One annotation under test, and the classes this probe reads for it.

    `container` and `handler` are the siblings whose EXISTENCE is half the
    question, so both are names to look for rather than names known to be
    there — an absent one is an observation.
    """

    key: str
    group: str
    artifact: str
    annotation: str
    container: str | None
    handler: str | None
    post_processor: str
    setters: str
    source: tuple[str, str] | None

    @property
    def internal(self) -> str:
        return self.annotation.replace(".", "/")

    @property
    def container_internal(self) -> str | None:
        return None if self.container is None else self.container.replace(".", "/")

    @property
    def handler_internal(self) -> str | None:
        return None if self.handler is None else self.handler.replace(".", "/")


# The container-shaped sibling is named here rather than parsed out of question
# 2's `@Repeatable` value, CP-16's reason unchanged: the two readings stay
# independent, so a framework whose container is named something else prints a
# `@Repeatable` naming one class and an `ABSENT` for the other, and the
# disagreement is the finding rather than a silently agreeing pair.
#
# `PulsarReaders`, `SqsListeners`, `KafkaHandlers` and `RabbitHandlers` are
# named on exactly the same footing as the containers that DO exist: the
# question is whether the framework ships one, and a name nobody looked for
# cannot answer it.
_FAMILIES = (
    Family(
        key="pulsar-listener",
        group="org.springframework.pulsar",
        artifact="spring-pulsar",
        annotation="org.springframework.pulsar.annotation.PulsarListener",
        container="org.springframework.pulsar.annotation.PulsarListeners",
        handler="org.springframework.pulsar.annotation.PulsarHandler",
        post_processor=(
            "org.springframework.pulsar.annotation.PulsarListenerAnnotationBeanPostProcessor"
        ),
        setters="org/springframework/pulsar/config/",
        source=(
            "org/springframework/pulsar/annotation/PulsarListenerAnnotationBeanPostProcessor.java",
            "findListenerAnnotations",
        ),
    ),
    Family(
        key="pulsar-reader",
        group="org.springframework.pulsar",
        artifact="spring-pulsar",
        annotation="org.springframework.pulsar.annotation.PulsarReader",
        container="org.springframework.pulsar.annotation.PulsarReaders",
        handler=None,
        post_processor=(
            "org.springframework.pulsar.annotation.PulsarReaderAnnotationBeanPostProcessor"
        ),
        setters="org/springframework/pulsar/config/",
        source=(
            "org/springframework/pulsar/annotation/PulsarReaderAnnotationBeanPostProcessor.java",
            "findReaderAnnotations",
        ),
    ),
    Family(
        key="sqs",
        group="io.awspring.cloud",
        artifact="spring-cloud-aws-sqs",
        annotation="io.awspring.cloud.sqs.annotation.SqsListener",
        container="io.awspring.cloud.sqs.annotation.SqsListeners",
        handler="io.awspring.cloud.sqs.annotation.SqsHandler",
        post_processor="io.awspring.cloud.sqs.annotation.SqsListenerAnnotationBeanPostProcessor",
        setters="io/awspring/cloud/sqs/config/",
        source=(
            "io/awspring/cloud/sqs/annotation/AbstractListenerAnnotationBeanPostProcessor.java",
            "detectAnnotationsAndRegisterEndpoints",
        ),
    ),
    Family(
        key="sqs-legacy-springframework",
        group="org.springframework.cloud",
        artifact="spring-cloud-aws-messaging",
        annotation="org.springframework.cloud.aws.messaging.listener.annotation.SqsListener",
        container="org.springframework.cloud.aws.messaging.listener.annotation.SqsListeners",
        handler=None,
        post_processor="org.springframework.cloud.aws.messaging.listener.QueueMessageHandler",
        setters="org/springframework/cloud/aws/messaging/listener/",
        source=None,
    ),
    Family(
        key="sqs-legacy-awspring",
        group="io.awspring.cloud",
        artifact="spring-cloud-aws-messaging",
        annotation="io.awspring.cloud.messaging.listener.annotation.SqsListener",
        container="io.awspring.cloud.messaging.listener.annotation.SqsListeners",
        handler=None,
        post_processor="io.awspring.cloud.messaging.listener.QueueMessageHandler",
        setters="io/awspring/cloud/messaging/listener/",
        source=None,
    ),
    Family(
        key="kafka-handler",
        group="org.springframework.kafka",
        artifact="spring-kafka",
        annotation="org.springframework.kafka.annotation.KafkaHandler",
        container="org.springframework.kafka.annotation.KafkaHandlers",
        handler=None,
        post_processor=(
            "org.springframework.kafka.annotation.KafkaListenerAnnotationBeanPostProcessor"
        ),
        setters="org/springframework/kafka/config/",
        source=None,
    ),
    Family(
        key="rabbit-handler",
        group="org.springframework.amqp",
        artifact="spring-rabbit",
        annotation="org.springframework.amqp.rabbit.annotation.RabbitHandler",
        container="org.springframework.amqp.rabbit.annotation.RabbitHandlers",
        handler=None,
        post_processor=(
            "org.springframework.amqp.rabbit.annotation.RabbitListenerAnnotationBeanPostProcessor"
        ),
        setters="org/springframework/amqp/rabbit/listener/",
        source=None,
    ),
    # Added after the first run, when closing `OI-40` needed a question the
    # `sqs` family does not carry: that family asks `@Repeatable` of
    # `@SqsListener` and reads `@SqsHandler`'s ATTRIBUTES only, so
    # `spring-sqs.yml`'s new handler entry would have declined a container on
    # no evidence — which is the omission §8.1 rule 4 forbids and the one the
    # two families below already answer for the other two frameworks. The
    # `sqs` family is left exactly as it was rather than widened, so the row
    # letters every verdict cites still name the same cells.
    Family(
        key="sqs-handler",
        group="io.awspring.cloud",
        artifact="spring-cloud-aws-sqs",
        annotation="io.awspring.cloud.sqs.annotation.SqsHandler",
        container="io.awspring.cloud.sqs.annotation.SqsHandlers",
        handler=None,
        post_processor="io.awspring.cloud.sqs.annotation.SqsListenerAnnotationBeanPostProcessor",
        setters="io/awspring/cloud/sqs/config/",
        source=None,
    ),
)


class Artifact:
    """One resolved jar, and the identity it reported for itself."""

    __slots__ = ("group", "jar", "name", "observed", "requested", "sources")

    def __init__(
        self,
        group: str,
        name: str,
        requested: str,
        jar: Path,
        sources: Path | None,
        entry: str,
        key: str,
    ) -> None:
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        self.sources = sources
        self.observed = _identity(jar, entry, key)
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was resolved as "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )


def _identity(jar: Path, entry: str, key: str) -> str:
    """The version this ARCHIVE claims for itself, read out of its own bytes."""
    with zipfile.ZipFile(jar) as archive:
        names = [name for name in archive.namelist() if name == entry or name.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}` — it reports no version of its own")
        text = archive.read(names[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    raise ProbeError(f"{jar.name}'s `{entry}` declares no `{key}`")


def _javap(*arguments: str, classpath: Path) -> str | None:
    """`javap`'s output, or None where the class is simply not in the archive.

    The None is the whole reason this differs from CP-16's helper: whether a
    framework ships a container or a handler annotation AT ALL is half of what
    this probe asks, so "not there" has to reach a cell. Every other failure
    still aborts.
    """
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if _NOT_FOUND.search(result.stderr):
            return None
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _step(line: str) -> str | None:
    """One instruction as `mnemonic <constant-pool comment>`, or None where the
    line is not an instruction at all."""
    match = _INSTRUCTION.match(line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _attributes(output: str) -> list[str]:
    """`name(): Type` for every attribute `javap -s` printed, in declaration
    order. The TYPE is half the answer: an annotation whose only attribute is a
    `boolean` names no address, which is the claim two shipped catalogs make
    about their handler annotation."""
    found = [
        f"{match.group(2)}(): {match.group(1)}"
        for match in map(_ATTRIBUTE.match, output.splitlines())
        if match
    ]
    if not found:
        raise ProbeError("javap printed no attributes for the annotation at all")
    return found


def _meta(output: str) -> list[str]:
    """The kept meta-annotations, as `Type(value)`.

    `javap -v` prints a type line and then its `value=` line; the value is taken
    from the following line rather than a fixed offset because a meta-annotation
    with no value prints none at all.
    """
    lines = output.splitlines()
    found = []
    for index, line in enumerate(lines):
        match = _META_TYPE.match(line)
        if match is None or match.group(1) not in _META_KEPT:
            continue
        following = _META_VALUE.match(lines[index + 1]) if index + 1 < len(lines) else None
        found.append(f"{match.group(1)}({following.group(1) if following else ''})")
    return found


def _for_each(
    artifacts: list[Artifact], family: Family, answer: Callable[[Artifact, Family], str]
) -> list[tuple[str, str, str]]:
    found = [a for a in artifacts if a.name == family.artifact and a.group == family.group]
    if not found:
        raise ProbeError(f"no resolved artifact named {family.group}:{family.artifact}")
    return [(artifact.name, artifact.observed, answer(artifact, family)) for artifact in found]


def q1_the_declared_attributes(artifact: Artifact, family: Family) -> str:
    """Q1. Every attribute the annotation under test declares, with its type.

    For a listener that is the enumeration a `path_from` alias set was chosen
    out of; for a handler it is the claim that no address lives on it.
    """
    output = _javap("-p", "-s", family.annotation, classpath=artifact.jar)
    return _ABSENT if output is None else _STEP.join(_attributes(output))


def q2_the_meta_annotations(artifact: Artifact, family: Family) -> str:
    """Q2. `@Target` and `@Repeatable` on the annotation under test.

    `@Repeatable` is the fact the vocabulary pass's audit table left open for
    four annotations at once: a catalog does not name a container it has not
    measured (§8.1 rule 4), and an EMPTY `@Repeatable` here is as much of an
    answer as a present one — it says the absence in the catalog is a claim.

    `@Target` says where a declaration may legally sit, which is what turns a
    class-level use from a composition into a real registration.
    """
    output = _javap("-v", "-p", family.annotation, classpath=artifact.jar)
    return _ABSENT if output is None else _STEP.join(_meta(output))


def q3_the_container_sibling(artifact: Artifact, family: Family) -> str:
    """Q3. Whether a container-shaped sibling exists, and what its `value()`
    returns.

    A container is not always javac's. JLS 9.6.3 governs the container of a
    `@Repeatable` annotation, but nothing stops a framework shipping a plain
    annotation of exactly that shape for an author to write by hand — and a
    class file cannot tell the two apart, which is why this asks the SHAPE
    question separately from question 2's `@Repeatable` question. The two
    answers together are what say which mechanism a framework uses.
    """
    if family.container is None:
        return "this probe names no container-shaped sibling for this annotation"
    output = _javap("-p", "-s", family.container, classpath=artifact.jar)
    return _ABSENT if output is None else _STEP.join(_attributes(output))


def q4_the_handler_sibling(artifact: Artifact, family: Family) -> str:
    """Q4. Whether a polymorphic handler sibling exists, and what it declares.

    `spring-kafka.yml` and `spring-rabbit.yml` model a class-level listener
    dispatching to handler methods; `spring-pulsar.yml` and `spring-sqs.yml`
    each state in a comment that their framework ships no such annotation. That
    comment is this cell, and one of the two is version-scoped in a way the
    comment does not say.
    """
    if family.handler is None:
        return "this probe names no handler sibling for this annotation"
    output = _javap("-p", "-s", family.handler, classpath=artifact.jar)
    return _ABSENT if output is None else _STEP.join(_attributes(output))


def _is_marker(step: str, family: Family) -> bool:
    """Whether one instruction is one of the markers this question keeps.

    Written as exact prefixes rather than a substring scan, CP-16's reason
    unchanged: the post-processor's OWN name begins with the annotation's, and
    a loose match fills the cell with the class's private plumbing.
    """
    siblings = tuple(
        f"invokeinterface InterfaceMethod {name}."
        for name in (family.internal, family.container_internal, family.handler_internal)
        if name is not None
    )
    classes = tuple(
        f"{mnemonic} class {name}"
        for name in (family.container_internal, family.handler_internal)
        if name is not None
        for mnemonic in ("ldc", "ldc_w", "checkcast")
    )
    return (
        any(search in step for search in _SEARCHES)
        or step.startswith(siblings)
        or step in classes
        or (step.startswith(f"invokevirtual Method {family.setters}") and ".set" in step)
    )


def q5_what_the_post_processor_reads(artifact: Artifact, family: Family) -> str:
    """Q5. How the post-processor FINDS the annotation, and which of its
    attributes, containers and handlers it reads.

    Deduplicated because a post-processor calls one attribute several times and
    the finding is the SET; ordered by first occurrence, so the search comes
    before the reads it enables. CP-16's shape exactly, widened by one marker:
    a reference to the HANDLER sibling, because a post-processor that never
    mentions it does not serve the class-level shape.
    """
    output = _javap("-p", "-c", family.post_processor, classpath=artifact.jar)
    if output is None:
        return _ABSENT
    if _javap("-p", family.annotation, classpath=artifact.jar) is None:
        # The annotation itself is not in this jar, so a post-processor that
        # never mentions it is the ONLY possible answer and an abort here would
        # be the harness refusing its own finding. Checked against the archive
        # rather than against an empty marker set, so a post-processor that
        # really does read nothing still aborts.
        return f"{_ABSENT} — the annotation this question reads for is not in this jar"
    seen: dict[str, None] = {}
    for line in output.splitlines():
        step = _step(line)
        if step is not None and _is_marker(step, family):
            seen.setdefault(step.split(" ", 1)[1] if " " in step else step)
    if not seen:
        raise ProbeError(f"{family.post_processor} names none of the markers this question reads")
    if not any(search in step for step in seen for search in _SEARCHES):
        # The search is not in this class at this version. That is the CP-7
        # failure one class UP — a rule that moved, printing an empty cell that
        # reads as "the rule is gone" — so the cell says where it went instead
        # of saying nothing. The superclass is read off `javap`'s own
        # declaration line, never written here.
        seen = {
            f"NO ANNOTATION SEARCH IN THIS CLASS — it extends {_superclass(output)}, "
            "which this question does not open": None,
            **seen,
        }
    return _STEP.join(seen)


def _superclass(output: str) -> str:
    """The type `javap` says this class extends, or `java.lang.Object` where it
    printed no `extends` clause."""
    declaration = next((line for line in output.splitlines() if " class " in line), "")
    match = re.search(r"\bextends ([\w.$]+)", declaration)
    return match.group(1) if match else "java.lang.Object"


def q6_the_discovery_method(artifact: Artifact, family: Family) -> str:
    """Q6. The framework's own discovery method, verbatim from the sources jar
    resolved at the SAME coordinate as the bytecode.

    Asked only where the rule is an ALGORITHM rather than a predicate — a union
    of two annotation reads, or a branch on whether a class-level annotation is
    present. Question 5 can say WHICH classes a post-processor touches and can
    never say in what combination, and guessing the combination off the
    disassembly is how `isCustomMethod` went unopened for a round.
    """
    if family.source is None:
        return "the rule for this annotation is a predicate questions 1-5 answer; no source read"
    if artifact.sources is None:
        raise ProbeError(f"{family.key} names a source read and no sources jar was resolved")
    path, method = family.source
    return _method_body(artifact.sources, path, method)


def _method_body(sources: Path, path: str, method: str) -> str:
    """One named method's whole body, whitespace collapsed onto one line.

    Brace-matched from the declaration rather than cut at a fixed line count, so
    a method that grows between versions is printed whole rather than truncated
    into a different rule. A name that matches no declaration, or more than one,
    ABORTS: a cell holding the wrong method is worse than no probe.
    """
    with zipfile.ZipFile(sources) as archive:
        try:
            text = archive.read(path).decode("utf-8", "replace")
        except KeyError:
            raise ProbeError(f"{sources.name} carries no `{path}`") from None
    starts = [
        index
        for index, line in enumerate(text.splitlines())
        if re.search(rf"\b{re.escape(method)}\s*\(", line) and line.rstrip().endswith("{")
    ]
    if len(starts) != 1:
        raise ProbeError(f"{path} declares {len(starts)} methods named `{method}`, expected 1")
    lines = text.splitlines()
    depth = 0
    body: list[str] = []
    for line in lines[starts[0] :]:
        body.append(line)
        depth += line.count("{") - line.count("}")
        if depth == 0:
            break
    else:
        raise ProbeError(f"{path}'s `{method}` never closes its brace")
    return re.sub(r"\s+", " ", " ".join(body)).strip()


_QUESTIONS: list[tuple[str, str, Callable[[Artifact, Family], str]]] = [
    ("1", "the annotation's declared attributes", q1_the_declared_attributes),
    ("2", "`@Target` and `@Repeatable` on it", q2_the_meta_annotations),
    ("3", "the container-shaped sibling", q3_the_container_sibling),
    ("4", "the polymorphic handler sibling", q4_the_handler_sibling),
    (
        "5",
        "the post-processor's annotation search, sibling references and attribute reads",
        q5_what_the_post_processor_reads,
    ),
    ("6", "the discovery method, verbatim from the sources jar", q6_the_discovery_method),
]


def main(specs: list[str]) -> int:
    artifacts = []
    for spec in specs:
        group, name, version, entry, key, jar, sources = spec.split("|")
        artifacts.append(
            Artifact(
                group,
                name,
                version,
                Path(jar),
                Path(sources) if sources else None,
                entry,
                key,
            )
        )

    columns = sorted({artifact.observed for artifact in artifacts})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(sorted(f"{a.group}:{a.name}" for a in artifacts if a.observed == version))
            for version in columns
        )
        + " |"
    )
    print("| identity read from the archive itself | " + " | ".join(["yes"] * len(columns)) + " |")
    print()
    print("| # | question | annotation family | artifact | version | observed |")
    print("|---|---|---|---|---|---|")
    for number, question, answer in _QUESTIONS:
        rows = [
            (family.key, *row)
            for family in _FAMILIES
            for row in _for_each(artifacts, family, answer)
        ]
        for index, (key, where, version, observed) in enumerate(rows):
            print(
                f"| {number}{chr(ord('a') + index)} | {question} | `{key}` | `{where}` | "
                f"{version} | `{observed}` |"
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-17 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
