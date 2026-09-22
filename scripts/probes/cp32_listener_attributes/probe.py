"""CP-32's measurement half: the `javap` reads
`.superpowers/sdd/2026-09-22-temporal-and-eventbus/task-9-brief.md` asks for, on the five
SHIPPED listener catalogs' own annotations — for each candidate attribute, its declared
type, its `AnnotationDefault`, and **what the framework's own post-processor does with it**,
so that a `metadata_from` entry's `kind` names what the framework MEANS rather than what the
attribute is called (spec 2026-09-22 §2e).

Called by `run.sh`, which resolves the five jars and compiles the two fixtures; this script
downloads nothing. Like CP-27, CP-30 and CP-31 it reads each jar's own identity out of its
own bytes before it measures anything and refuses to file a cell under a version the archive
did not claim (GUIDELINES §5.4); all five of these jars state an `Implementation-Version`, so
the manifest check is the one that runs and CP-30's SHA-1 fallback is never reached. The
fixtures' own classes carry no manifest: their cells are filed under the class-file version
`javap -v` reports for them, the one identity a compiled class states about itself.

**Nothing here pre-selects which attribute answers a question.** The element rows list EVERY
element the named annotation declares with its descriptor and its own `AnnotationDefault`,
never the handful a catalog reads — an attribute that gains, loses or renames a default shows
up in the cell the next time this runs, and an attribute whose NAME differs from the one the
criterion assumed (Micronaut JMS's `messageSelector`) can only be found by listing them all.
Each element's own meta-annotations are kept with it, because Micronaut's `@AliasFor` is what
says two differently named elements are one attribute. The post-processor rows dump the FULL
instruction body of EVERY method that references the attribute, found by SEARCHING the class
for the reference rather than by naming a method here, because a probe that hard-codes a
method name stops measuring the day the framework moves the read.

The fixture rows print every use of one of these annotations that the committed fixtures'
own compiled classes carry, decoded by `javap` itself, with the member it sits on — the row
that says which shipped endpoints a `metadata_from` line moves, and the only row in this
probe that is about this repository rather than about a framework.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
_STEP = " ; "
# `javap`'s own two-line shape under `-v`: a declaration, then its erased descriptor.
_DECLARATION = re.compile(r"^\s{2}\S.*?([\w$]+)\(")
_DESCRIPTOR_LINE = re.compile(r"^\s*descriptor:\s*(\S+)\s*$")
# `javap -v`'s rendering of one ANNOTATION USE's raw encoding, which shares
# `_DECLARATION`'s shape (two-space indent, a `(`) and is not a declaration.
_ENCODED_USE = re.compile(r"^\s*\d+:\s*#")


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    """One resolved jar, labelled with the version IT reports about ITSELF.

    Every archive CP-32 reads writes an `Implementation-Version` into its own manifest
    (checked: spring-kafka, spring-jms, spring-rabbit, micronaut-kafka and micronaut-jms-core
    all carry the entry), so §5.4's ordinary mechanism applies unchanged and a jar reporting
    anything other than the coordinate `run.sh` asked for stops the run rather than filling a
    mislabelled column. CP-30's SHA-1 fallback exists for archives that state no version
    anywhere; none of these is one, and this class deliberately has no such branch — a jar
    that stopped reporting a version would abort here rather than quietly fall back to
    trusting the parameter.
    """

    def __init__(self, key: str, group: str, name: str, requested: str, jar: Path):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        reported = _manifest_version(jar, "META-INF/MANIFEST.MF", "Implementation-Version")
        if reported is None:
            raise ProbeError(
                f"{jar.name} states no `Implementation-Version` in its own manifest — every "
                "cell filed under its column would be the coordinate this run asked for "
                "rather than anything the archive says (CP-5's failure exactly)"
            )
        self.observed = reported
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was expected to report "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )


class Fixture:
    """One committed fixture's compiled classes, labelled with the one identity a class
    file states about itself: its own class-file major version. CP-27's row 16, CP-30's
    Q9 and CP-31's Q9, same reasoning."""

    def __init__(self, key: str, name: str, classes: Path, identity_class: str):
        self.key = key
        self.name = name
        self.classes = classes
        output = _javap("-v", identity_class, classpath=classes)
        match = re.search(r"major version: (\d+)", output)
        if match is None:
            raise ProbeError(f"{name}: {identity_class}'s class file states no major version")
        self.observed = f"class file {match.group(1)}"


def _manifest_version(jar: Path, entry: str, key: str) -> str | None:
    with zipfile.ZipFile(jar) as archive:
        names = [n for n in archive.namelist() if n == entry or n.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}`")
        text = archive.read(names[0]).decode("utf-8", "replace")
    # A manifest wraps a long value onto a continuation line beginning with one space;
    # `Implementation-Version` is short in every archive here, but the unwrap is done
    # anyway rather than left as an assumption about a future release's formatting.
    unwrapped: list[str] = []
    for line in text.splitlines():
        if line.startswith(" ") and unwrapped:
            unwrapped[-1] += line[1:]
        else:
            unwrapped.append(line)
    for line in unwrapped:
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    return None


def _javap(*arguments: str, classpath: Path, check: bool = True) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0 and check:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _bodies(output: str) -> list[tuple[str, list[str]]]:
    """`(declaration, instruction lines)` per method of a `javap -p -c` listing."""
    methods: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in output.splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            current = (line.strip().rstrip(";"), [])
            methods.append(current)
        elif current is not None and line.startswith("    "):
            current[1].append(line)
    return methods


def _step_with_offset(line: str) -> str | None:
    """`"<offset>: <mnemonic> <comment-or-operand>"` for one instruction line — CP-30's own
    `_step_with_offset`, including its fix: a branch target is a BARE trailing operand with
    no `//`, so splitting on `//` unconditionally drops every branch destination."""
    match = re.match(r"^\s*(\d+):\s+(\S+)(.*)$", line)
    if match is None:
        return None
    offset, mnemonic, operands = match.groups()
    text = operands.split("//", 1)[1].strip() if "//" in operands else operands.strip()
    return f"{offset}: {mnemonic} {text}".strip()


# --- the element rows: every element an annotation declares, with its own default ---------


def q_annotation_elements(jar: Path, fqn: str) -> str:
    """Every element the annotation TYPE `fqn` declares — name, erased descriptor, its own
    `AnnotationDefault` (encoded and decoded), and any meta-annotation javap renders beneath
    it — followed by the annotation type's own `@Target` and `@Retention`.

    Listed in declaration order and NOT filtered to the elements any catalog reads. That is
    the whole point of the row: the criterion §2e states is about what a peer cares about,
    and deciding whether an element qualifies needs the element's own type and default, while
    deciding what it is CALLED needs every name the annotation declares. Micronaut JMS's
    selector is `messageSelector`, and no probe that looked only for `selector` would have
    found it.

    An element's own meta-annotations are kept with the element (`AliasFor`, which is how
    Micronaut says two differently named elements are one attribute) by capturing the lines
    between one element's default and the next declaration.
    """
    output = _javap("-v", "-p", fqn, classpath=jar)
    lines = output.splitlines()
    cells: list[str] = []
    name: str | None = None
    descriptor: str | None = None
    default: str | None = None
    extra: list[str] = []

    def flush() -> None:
        if name is None:
            return
        parts = [f"{name}{descriptor or '?'}"]
        parts.append(default if default is not None else "NO AnnotationDefault")
        parts.extend(extra)
        cells.append(" -> ".join(parts))

    for index, line in enumerate(lines):
        # `javap -v` renders an annotation USE as `  0: #38(#39=[e#40.#41])` — two-space
        # indent, and a `(` — so `_DECLARATION` matches it and captures the constant-pool
        # index as though it were an element name. An element declaration never begins with
        # a digit, and that is the whole of the difference.
        declaration = None if _ENCODED_USE.match(line) else _DECLARATION.match(line)
        if declaration is not None:
            flush()
            name, descriptor, default, extra = declaration.group(1), None, None, []
            continue
        if name is None:
            continue
        stripped = line.strip()
        descriptor_line = _DESCRIPTOR_LINE.match(line)
        if descriptor_line is not None:
            descriptor = descriptor_line.group(1)
            continue
        if stripped == "AnnotationDefault:":
            # `javap` prints `default_value: <encoded>` then the decoded value beneath it;
            # both are kept, because the encoded form names the constant-pool TYPE tag
            # (`Z#22` — a boolean, `s#10` — a string) and the decoded form names the value.
            encoded = lines[index + 1].strip() if index + 1 < len(lines) else ""
            decoded = lines[index + 2].strip() if index + 2 < len(lines) else ""
            default = f"{encoded} = {decoded}"
            continue
        if (
            "AliasFor" in stripped
            or stripped.startswith("member=")
            or "annotation=class" in stripped
        ):
            extra.append(stripped)
    flush()
    if not cells:
        raise ProbeError(f"{fqn} declares no element at all in {jar.name}")
    # The annotation TYPE's own meta-annotations, after its elements: `@Target` decides
    # whether a class-level use can exist at all, `@Retention` whether a use reaches the
    # class file for a scanner to read, and `@Repeatable` whether javac folds two uses into
    # a container the reader must unfold.
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(
            (
                "java.lang.annotation.Target(",
                "java.lang.annotation.Retention(",
                "java.lang.annotation.Repeatable(",
            )
        ):
            following = lines[index + 1].strip() if index + 1 < len(lines) else ""
            cells.append(f"TYPE {stripped.rstrip('(')}: {following}")
    return f"×{len(cells)} ; " + _STEP.join(cells)


# --- the post-processor rows: the FULL body of every method that reads the attribute -------


def q_bodies_referencing(jar: Path, owner: str, needle: str) -> str:
    """The FULL instruction body of every method of `owner` whose body references `needle`
    (an `<annotation>.<attribute>:` member reference, or an `ldc` of the attribute's name
    where the framework reads it by string).

    Which method that is is found by SEARCHING the class's bodies rather than by naming one
    here: CP-31's Q7 reason exactly — a probe that hard-coded `processListener` would stop
    measuring the day the framework moved the read, and would also hide a SECOND method that
    reads the same attribute differently. Every matching method is dumped whole, because a
    curated excerpt can be the instructions that confirm what was expected rather than what
    the bytecode says.
    """
    output = _javap("-c", "-p", owner, classpath=jar)
    cells: list[str] = []
    for declaration, body in _bodies(output):
        steps = [s for s in (_step_with_offset(line) for line in body) if s is not None]
        if any(needle in step for step in steps):
            cells.append(f"--- in `{declaration}` ---")
            cells.extend(steps)
    if not cells:
        raise ProbeError(f"no method of {owner} references {needle!r} in {jar.name}")
    return _STEP.join(cells)


# --- the fixture rows: the uses the committed repositories' own classes carry --------------

# The annotation types whose uses decide which shipped endpoints a `metadata_from` line
# would move. Every listener annotation the five amended catalogs name, and nothing else.
_FIXTURE_ANNOTATIONS = (
    "org.springframework.kafka.annotation.KafkaListener",
    "org.springframework.kafka.annotation.KafkaListeners",
    "org.springframework.kafka.annotation.KafkaHandler",
    "org.springframework.jms.annotation.JmsListener",
    "org.springframework.jms.annotation.JmsListeners",
    "org.springframework.amqp.rabbit.annotation.RabbitListener",
    "org.springframework.amqp.rabbit.annotation.RabbitListeners",
    "org.springframework.amqp.rabbit.annotation.RabbitHandler",
    "io.micronaut.configuration.kafka.annotation.KafkaListener",
    "io.micronaut.configuration.kafka.annotation.Topic",
    "io.micronaut.jms.annotations.JMSListener",
    "io.micronaut.jms.annotations.Queue",
    "io.micronaut.jms.annotations.Topic",
)


def _fixture_classes(classes: Path) -> list[str]:
    return sorted(
        path.relative_to(classes).with_suffix("").as_posix().replace("/", ".")
        for path in classes.rglob("*.class")
    )


def q_fixture_uses(classes: Path) -> str:
    """Every use of one of `_FIXTURE_ANNOTATIONS` the fixture's own compiled classes carry,
    as `javap -v` itself decodes it, with the class or member it sits on.

    Enumerated off the compiled tree rather than off a list of class names typed here, so an
    arm added to a fixture appears in this cell without the probe being edited — CP-31's Q9
    rule. A class carrying none of them prints nothing rather than a line saying so: these
    fixtures hold hundreds of classes and the question is which ones DO carry a use.
    """
    cells: list[str] = []
    for name in _fixture_classes(classes):
        output = _javap("-v", "-p", name, classpath=classes)
        lines = output.splitlines()
        # Which declaration a use sits on is decided by the INDENT of the
        # `RuntimeVisibleAnnotations:` header that opens the section, not by the last
        # declaration seen: javap prints the CLASS's own annotations at column 0 and after
        # the closing brace, so a class-level use read off "the last declaration" would be
        # filed against the last method in the file — which is exactly the site a
        # class-level `@KafkaListener` must NOT be attributed to (§2e's whole nearest-wins
        # question). A member's annotations are indented under the member.
        site = "(the class itself)"
        member = site
        found: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if stripped.startswith(("RuntimeVisibleAnnotations:", "RuntimeInvisibleAnnotations:")):
                site = "(the class itself)" if not line.startswith(" ") else member
                index += 1
                continue
            if (
                line.startswith("  ")
                and not line.startswith("   ")
                and stripped.endswith(";")
                and _ENCODED_USE.match(line) is None
            ):
                member = stripped.rstrip(";")
            match = next((a for a in _FIXTURE_ANNOTATIONS if stripped.startswith(a)), None)
            if match is not None and (stripped == match or stripped.startswith(match + "(")):
                block = [stripped]
                if stripped.endswith("("):
                    depth = 1
                    while depth > 0 and index + 1 < len(lines):
                        index += 1
                        inner = lines[index].strip()
                        block.append(inner)
                        depth += inner.count("(") - inner.count(")")
                found.append(f"on `{site}`: " + " ".join(block))
            index += 1
        if found:
            cells.append(f"{name} :: " + " ".join(f"[{f}]" for f in found))
    if not cells:
        raise ProbeError(f"no listener annotation use found under {classes}")
    return _STEP.join(cells)


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    fixture_paths: dict[str, tuple[str, Path]] = {}
    for spec in specs:
        key, group, name, requested, path = spec.split("|")
        if key.startswith("fixture:"):
            fixture_paths[key.split(":", 1)[1]] = (name, Path(path))
            continue
        artifacts[key] = Artifact(key, group, name, requested, Path(path))
    missing = {"kafka", "jms", "rabbit", "mnkafka", "mnjms"} - set(artifacts)
    if missing or {"spring", "micronaut"} - set(fixture_paths):
        raise ProbeError(f"run.sh handed in no spec for {sorted(missing)}")
    kafka = artifacts["kafka"]
    jms = artifacts["jms"]
    rabbit = artifacts["rabbit"]
    mnkafka = artifacts["mnkafka"]
    mnjms = artifacts["mnjms"]
    spring_fixture = Fixture(
        "spring", *fixture_paths["spring"], "com.acme.orders.messaging.OrderEventsListener"
    )
    micronaut_fixture = Fixture(
        "micronaut", *fixture_paths["micronaut"], "com.acme.mn.OrderMessaging"
    )
    fixtures = {"spring": spring_fixture, "micronaut": micronaut_fixture}

    columns = sorted({a.observed for a in artifacts.values()})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(sorted(f"{a.group}:{a.name}" for a in artifacts.values() if a.observed == v))
            for v in columns
        )
        + " |"
    )
    print(
        "| identity read from the archive itself (`Implementation-Version`) | "
        + " | ".join(
            "yes"
            if all(a.observed == a.requested for a in artifacts.values() if a.observed == v)
            else "NO"
            for v in columns
        )
        + " |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    def row(number: str, question: str, artifact: Artifact | Fixture, observed: str) -> None:
        where = (
            f"`{artifact.group}:{artifact.name}` | {artifact.observed}"
            if isinstance(artifact, Artifact)
            else f"`fixtures/{artifact.name}` (target/classes) | {artifact.observed}"
        )
        print(f"| {number} | {question} | {where} | `{observed}` |")

    elements = (
        ("1a", kafka, "org.springframework.kafka.annotation.KafkaListener"),
        ("1b", kafka, "org.springframework.kafka.annotation.KafkaHandler"),
        ("2a", jms, "org.springframework.jms.annotation.JmsListener"),
        ("3a", rabbit, "org.springframework.amqp.rabbit.annotation.RabbitListener"),
        ("3b", rabbit, "org.springframework.amqp.rabbit.annotation.RabbitHandler"),
        # The NESTED `@Queue`, because it declares an `exclusive()` of its OWN with a
        # different type — the collision a `metadata_from` naming the bare attribute name
        # would have to be read against.
        ("3c", rabbit, "org.springframework.amqp.rabbit.annotation.Queue"),
        ("4a", mnkafka, "io.micronaut.configuration.kafka.annotation.KafkaListener"),
        ("4b", mnkafka, "io.micronaut.configuration.kafka.annotation.Topic"),
        ("5a", mnjms, "io.micronaut.jms.annotations.JMSListener"),
        ("5b", mnjms, "io.micronaut.jms.annotations.Queue"),
        ("5c", mnjms, "io.micronaut.jms.annotations.Topic"),
    )
    for number, artifact, fqn in elements:
        row(
            number,
            f"every element `{fqn}` declares, with its own `AnnotationDefault`",
            artifact,
            q_annotation_elements(artifact.jar, fqn),
        )

    processors = (
        (
            "6",
            kafka,
            "org.springframework.kafka.annotation.KafkaListenerAnnotationBeanPostProcessor",
            "KafkaListener.groupId:",
            "`groupId`",
        ),
        (
            "7a",
            jms,
            "org.springframework.jms.annotation.JmsListenerAnnotationBeanPostProcessor",
            "JmsListener.selector:",
            "`selector`",
        ),
        (
            "7b",
            jms,
            "org.springframework.jms.annotation.JmsListenerAnnotationBeanPostProcessor",
            "JmsListener.subscription:",
            "`subscription`",
        ),
        (
            "8",
            rabbit,
            "org.springframework.amqp.rabbit.annotation.RabbitListenerAnnotationBeanPostProcessor",
            "RabbitListener.exclusive:",
            "`exclusive`",
        ),
        (
            "9",
            mnkafka,
            "io.micronaut.configuration.kafka.processor.KafkaConsumerProcessor",
            "String groupId",
            "`groupId`",
        ),
        (
            "10",
            mnjms,
            "io.micronaut.jms.configuration.AbstractJMSListenerMethodProcessor",
            "String messageSelector",
            "`messageSelector`",
        ),
    )
    for number, artifact, owner, needle, label in processors:
        row(
            number,
            f"the WHOLE body of every method of `{owner.rsplit('.', 1)[1]}` that references "
            f"{label}",
            artifact,
            q_bodies_referencing(artifact.jar, owner, needle),
        )

    for number, key in (("11a", "spring"), ("11b", "micronaut")):
        row(
            number,
            "every listener-annotation use the fixture's own compiled classes carry, with "
            "the member it sits on and the elements it WRITES",
            fixtures[key],
            q_fixture_uses(fixtures[key].classes),
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-32 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
