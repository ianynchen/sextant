"""CP-16's measurement half: which attributes of a listener annotation name a
destination, and how the framework FINDS the annotation at all.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. Like CP-7, CP-13, CP-14 and CP-15 it reads each jar's own identity out
of its own bytes before it measures anything and refuses to file a cell under a
version the artifact did not claim (GUIDELINES §5.4, and CP-5's failure it
exists to prevent).

Every question answers PER RESOLVED ARTIFACT rather than once, so a rule read
against two minors of a framework prints two rows and §5.4's scope is the rows
themselves rather than a sentence about them.

Everything it prints is the table `cp16_listener_destinations.md` carries
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
# `javap -v`'s rendering of a meta-annotation's own name and value lines: the
# type on one line, `value=...` on the next, both indented deeper than the
# member declarations around them.
_META_TYPE = re.compile(r"^\s{4}([\w.$]+)\($")
_META_VALUE = re.compile(r"^\s{6}value=(.+)$")

# Markdown tables are `|`-delimited, so an instruction sequence is joined with
# something else: a `|` inside a cell silently splits the row, and a table
# nobody can read back is a table nobody re-checks.
_STEP = " ; "

# The meta-annotations question 2 keeps. `@Target` says where a declaration may
# legally sit — the conjunct `derive_endpoints.handler-is-a-method` rests on —
# and `@Repeatable` names the CONTAINER javac folds repeats into, which is the
# fact `spring-scheduling.yml` had to name explicitly and no listener catalog
# does. `@Retention` and `@Documented` say nothing about either.
_META_KEPT = ("java.lang.annotation.Target", "java.lang.annotation.Repeatable")

# What question 4 keeps out of a post-processor several thousand instructions
# long: the listener annotation's own attribute reads (which attributes are read
# AT ALL), Spring's two annotation-search entry points (which says whether a
# meta-annotated, inherited or repeated declaration is found), and the endpoint's
# own destination setters (which says what a read attribute BECOMES).
_SEARCHES = (
    "org/springframework/core/annotation/AnnotatedElementUtils.",
    "org/springframework/core/annotation/MergedAnnotations",
)


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


@dataclass(frozen=True)
class Family:
    """One listener framework, and the classes this probe reads for it."""

    key: str
    artifact: str
    annotation: str
    container: str
    handler: str | None
    post_processor: str
    setters: str

    @property
    def internal(self) -> str:
        return self.annotation.replace(".", "/")


# The container javac folds a repeated use into, spelled internally. Named here
# rather than parsed out of question 2's `@Repeatable` value so that the two
# readings are independent: if a framework renamed its container, question 2
# would print the new name and question 4 would print no container reference,
# and the disagreement is the finding rather than a silently agreeing pair.
_FAMILIES = (
    Family(
        key="kafka",
        artifact="spring-kafka",
        annotation="org.springframework.kafka.annotation.KafkaListener",
        container="org/springframework/kafka/annotation/KafkaListeners",
        handler="org.springframework.kafka.annotation.KafkaHandler",
        post_processor=(
            "org.springframework.kafka.annotation.KafkaListenerAnnotationBeanPostProcessor"
        ),
        setters="org/springframework/kafka/config/",
    ),
    Family(
        key="jms",
        artifact="spring-jms",
        annotation="org.springframework.jms.annotation.JmsListener",
        container="org/springframework/jms/annotation/JmsListeners",
        handler=None,
        post_processor="org.springframework.jms.annotation.JmsListenerAnnotationBeanPostProcessor",
        setters="org/springframework/jms/config/",
    ),
    Family(
        key="rabbit",
        artifact="spring-rabbit",
        annotation="org.springframework.amqp.rabbit.annotation.RabbitListener",
        container="org/springframework/amqp/rabbit/annotation/RabbitListeners",
        handler="org.springframework.amqp.rabbit.annotation.RabbitHandler",
        post_processor=(
            "org.springframework.amqp.rabbit.annotation.RabbitListenerAnnotationBeanPostProcessor"
        ),
        setters="org/springframework/amqp/rabbit/listener/",
    ),
)


class Artifact:
    """One resolved jar, and the identity it reported for itself."""

    __slots__ = ("jar", "name", "observed", "requested")

    def __init__(self, name: str, requested: str, jar: Path, entry: str, key: str) -> None:
        self.name = name
        self.requested = requested
        self.jar = jar
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


def _javap(*arguments: str, classpath: Path) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
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
    order. The TYPE is half the answer: `String[]` and `String` are different
    claims about one destination, and a nested annotation type is a destination
    no `path_from` alias can reach."""
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

    `javap -v` prints a type line and then its `value=` line; the value is
    taken from the following line rather than a fixed offset because a
    meta-annotation with no value prints none at all.
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
    found = [a for a in artifacts if a.name == family.artifact]
    if not found:
        raise ProbeError(f"no resolved artifact named {family.artifact}")
    return [(artifact.name, artifact.observed, answer(artifact, family)) for artifact in found]


def q1_the_listener_attributes(artifact: Artifact, family: Family) -> str:
    """Q1. Every attribute the listener annotation declares, with its type.

    Each shipped catalog's `path_from` is an alias set chosen out of this list,
    and an alias set is only as trustworthy as the enumeration it was chosen
    from — `spring-scheduling.yml`'s `initialDelay` is the shape that goes
    wrong when the list was remembered rather than read.
    """
    return _STEP.join(_attributes(_javap("-p", "-s", family.annotation, classpath=artifact.jar)))


def q2_the_meta_annotations(artifact: Artifact, family: Family) -> str:
    """Q2. `@Target` and `@Repeatable` on the listener annotation.

    `@Target` bounds where a declaration may sit, which is what says whether a
    TYPE-level use is a real registration or a composition. `@Repeatable` names
    the CONTAINER javac folds two uses on one method into — and a catalog that
    does not name that container sees NO annotation at all on such a method,
    which is the failure `spring-scheduling.yml` names its `container` key to
    avoid.
    """
    return _STEP.join(_meta(_javap("-v", "-p", family.annotation, classpath=artifact.jar)))


def q3_the_handler_attributes(artifact: Artifact, family: Family) -> str:
    """Q3. What the sibling polymorphic-handler annotation declares.

    `spring-kafka.yml` and `spring-rabbit.yml` both claim their handler
    annotation carries no address of its own and reaches one only through the
    class-level listener. That claim is this cell. JMS has no such annotation,
    and the cell says so rather than being absent.
    """
    if family.handler is None:
        return "no sibling handler annotation in this framework"
    return _STEP.join(_attributes(_javap("-p", "-s", family.handler, classpath=artifact.jar)))


def _is_marker(step: str, family: Family) -> bool:
    """Whether one instruction is one of the three this question keeps.

    Written as exact prefixes rather than a substring scan, because the
    post-processor's OWN name begins with the annotation's — `KafkaListener`
    and `KafkaListenerAnnotationBeanPostProcessor$ListenerScope` share every
    character of the first — and a loose match filled the cell with the class's
    private plumbing.
    """
    return (
        any(search in step for search in _SEARCHES)
        or step.startswith(
            (
                f"invokeinterface InterfaceMethod {family.internal}.",
                f"invokeinterface InterfaceMethod {family.container}.",
            )
        )
        or step in (f"ldc class {family.container}", f"ldc_w class {family.container}")
        or step == f"checkcast class {family.container}"
        or (step.startswith(f"invokevirtual Method {family.setters}") and ".set" in step)
    )


def q4_what_the_post_processor_reads(artifact: Artifact, family: Family) -> str:
    """Q4. How the post-processor FINDS the annotation, and which of its
    attributes it reads.

    Three markers, deduplicated in bytecode order. Spring's annotation-search
    entry points (`AnnotatedElementUtils` / `MergedAnnotations`) say whether a
    META-ANNOTATED or INHERITED declaration is found at all. Every call on the
    listener annotation and on its repeatable CONTAINER says which attributes
    are read and whether a folded repeat is read — the fact that decides
    whether a catalog naming only the annotation sees such a method. Every
    `set*` call into the framework's own endpoint-config package says what a
    read attribute becomes.

    Deduplicated because a post-processor calls one attribute several times and
    the finding is the SET; ordered by first occurrence, so the search comes
    before the reads it enables.
    """
    output = _javap("-p", "-c", family.post_processor, classpath=artifact.jar)
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
            "which this probe does not open": None,
            **seen,
        }
    return _STEP.join(seen)


def _superclass(output: str) -> str:
    """The type `javap` says this class extends, or `java.lang.Object` where it
    printed no `extends` clause."""
    declaration = next((line for line in output.splitlines() if " class " in line), "")
    match = re.search(r"\bextends ([\w.$]+)", declaration)
    return match.group(1) if match else "java.lang.Object"


_QUESTIONS: list[tuple[str, str, Callable[[Artifact, Family], str]]] = [
    ("1", "the listener annotation's declared attributes", q1_the_listener_attributes),
    ("2", "`@Target` and `@Repeatable` on it", q2_the_meta_annotations),
    ("3", "the sibling handler annotation's attributes", q3_the_handler_attributes),
    (
        "4",
        "the post-processor's annotation search, attribute reads and endpoint calls",
        q4_what_the_post_processor_reads,
    ),
]


def main(specs: list[str]) -> int:
    artifacts = []
    for spec in specs:
        _, name, version, entry, key, jar = spec.split("|")
        artifacts.append(Artifact(name, version, Path(jar), entry, key))

    columns = sorted({artifact.observed for artifact in artifacts})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(sorted(a.name for a in artifacts if a.observed == version))
            for version in columns
        )
        + " |"
    )
    print("| identity read from the archive itself | " + " | ".join(["yes"] * len(columns)) + " |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")
    for number, question, answer in _QUESTIONS:
        rows = [row for family in _FAMILIES for row in _for_each(artifacts, family, answer)]
        for index, (where, version, observed) in enumerate(rows):
            print(
                f"| {number}{chr(ord('a') + index)} | {question} | `{where}` | {version} | "
                f"`{observed}` |"
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-16 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
