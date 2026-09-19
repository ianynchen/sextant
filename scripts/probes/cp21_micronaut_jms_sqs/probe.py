"""CP-21's measurement half: `@JMSListener`/`@JMSProducer`'s declared
attributes (no `connectionFactory` of any name), the post-processor's
`Qualifiers.byName` resolution of `value()` as a bean name, the three broker
modules' own `CONNECTION_FACTORY_BEAN_NAME` literals, and Task 1's compiled
fixture carrying that literal verbatim in its class file.

Called by `run.sh`, which resolves the jars (and recompiles the fixture, since
`fixtures/orders-micronaut/target/` is gitignored and not itself committed);
this script never downloads anything. Like CP-16/CP-17/CP-18/CP-19/CP-20 it
reads each jar's own identity out of its own bytes before it measures anything
and refuses to file a cell under a version the artifact did not claim
(GUIDELINES §5.4, and CP-5's failure it exists to prevent).
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
_STEP = " ; "


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    def __init__(self, key: str, group: str, name: str, requested: str, jar: Path):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        self.observed = _identity(jar, "META-INF/MANIFEST.MF", "Implementation-Version")
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was resolved as "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )


def _identity(jar: Path, entry: str, key: str) -> str:
    with zipfile.ZipFile(jar) as archive:
        names = [n for n in archive.namelist() if n == entry or n.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}`")
        text = archive.read(names[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    raise ProbeError(f"{jar.name}'s `{entry}` declares no `{key}`")


def _javap(*arguments: str, classpath: str) -> str:
    result = subprocess.run(
        ["javap", "-cp", classpath, *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _step(line: str) -> str | None:
    match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def q1_annotation_shape(jar: Path, fqn: str) -> str:
    """Q1. Every declared attribute, `@Target`, `@Retention`."""
    output = _javap("-v", fqn, classpath=str(jar))
    attrs = re.findall(r"public abstract (\S+) ([\w$]+)\(\);", output)
    target = re.search(r"java\.lang\.annotation\.Target\(\s*\n\s*value=(\[[^\]]*\]|\S+)", output)
    retention = re.search(r"java\.lang\.annotation\.Retention\(\s*\n\s*value=(\S+)", output)
    attr_text = _STEP.join(f"{name}(): {typ}" for typ, name in attrs)
    return f"{attr_text} ; @Target({target.group(1) if target else '?'}) ; @Retention({retention.group(1) if retention else '?'})"


def q2_post_processor(core_jar: Path) -> str:
    """Q2. The post-processor's `getRequiredValue`/`Qualifiers.byName` read."""
    output = _javap(
        "-c",
        "-p",
        "io.micronaut.jms.configuration.AbstractJMSListenerMethodProcessor",
        classpath=str(core_jar),
    )
    lines = output.splitlines()
    kept = []
    for line in lines:
        step = _step(line)
        if step and ("JMSListener" in step or "getRequiredValue" in step or "byName" in step):
            kept.append(step)
    if not kept:
        raise ProbeError("no JMSListener/getRequiredValue/byName markers found")
    seen: dict[str, None] = {}
    for step in kept:
        seen.setdefault(step)
    return _STEP.join(seen)


def q3_broker_constant(jar: Path, fqn: str) -> str:
    """Q3a-c. Each broker module's `CONNECTION_FACTORY_BEAN_NAME` literal."""
    output = _javap("-constants", fqn, classpath=str(jar))
    match = re.search(r"CONNECTION_FACTORY_BEAN_NAME = (\"[^\"]*\")", output)
    if not match:
        raise ProbeError(f"{fqn}: no CONNECTION_FACTORY_BEAN_NAME constant")
    return f"CONNECTION_FACTORY_BEAN_NAME = {match.group(1)}"


def q3d_named_bean(sqs_jar: Path) -> str:
    """Q3d. The generated SQS connection-factory bean carries `@Named` with
    that exact literal."""
    output = _javap(
        "-v",
        "io.micronaut.jms.sqs.configuration.$SqsConfiguration$SqsJmsConnectionFactory0$Definition",
        classpath=str(sqs_jar),
    )
    has_literal = "sqsJmsConnectionFactory" in output
    has_named = "jakarta.inject.Named" in output
    return f'carries literal "sqsJmsConnectionFactory": {has_literal} ; carries @Named: {has_named}'


def q4_fixture(fixture_classes: Path) -> str:
    """Q4. Task 1's compiled fixture: the annotation's `value` inlines
    verbatim in the class file."""
    output = _javap("-v", "com.acme.mn.OrderMessaging$SqsConsumer", classpath=str(fixture_classes))
    match = re.search(
        r"io\.micronaut\.jms\.annotations\.JMSListener\(\s*\n\s*value=(\"[^\"]*\")", output
    )
    if not match:
        raise ProbeError("OrderMessaging$SqsConsumer carries no @JMSListener(value=...)")
    return f"@JMSListener(value={match.group(1)})"


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    fixture_classes: Path | None = None
    for spec in specs:
        if spec.startswith("FIXTURE="):
            fixture_classes = Path(spec.split("=", 1)[1])
            continue
        key, group, name, version, jar = spec.split("|")
        artifacts[key] = Artifact(key, group, name, version, Path(jar))
    if fixture_classes is None:
        raise ProbeError("no FIXTURE= argument given")

    core = artifacts["core"]
    sqs = artifacts["sqs"]
    amq = artifacts["amq"]
    artemis = artifacts["artemis"]

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
    print("| identity read from the archive itself | " + " | ".join(["yes"] * len(columns)) + " |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    rows = [
        (
            "1a",
            "JMSListener: attributes, @Target, @Retention",
            core,
            q1_annotation_shape(core.jar, "io.micronaut.jms.annotations.JMSListener"),
        ),
        (
            "1b",
            "JMSProducer: attributes, @Target, @Retention",
            core,
            q1_annotation_shape(core.jar, "io.micronaut.jms.annotations.JMSProducer"),
        ),
        (
            "2",
            "the post-processor's value()->Qualifiers.byName resolution",
            core,
            q2_post_processor(core.jar),
        ),
        (
            "3a",
            "SqsConfiguration.CONNECTION_FACTORY_BEAN_NAME",
            sqs,
            q3_broker_constant(sqs.jar, "io.micronaut.jms.sqs.configuration.SqsConfiguration"),
        ),
        (
            "3b",
            "ActiveMqClassicConfiguration.CONNECTION_FACTORY_BEAN_NAME",
            amq,
            q3_broker_constant(
                amq.jar,
                "io.micronaut.jms.activemq.classic.configuration.ActiveMqClassicConfiguration",
            ),
        ),
        (
            "3c",
            "ActiveMqArtemisConfiguration.CONNECTION_FACTORY_BEAN_NAME",
            artemis,
            q3_broker_constant(
                artemis.jar,
                "io.micronaut.jms.activemq.artemis.configuration.ActiveMqArtemisConfiguration",
            ),
        ),
        (
            "3d",
            "the generated SQS connection-factory bean's own @Named literal",
            sqs,
            q3d_named_bean(sqs.jar),
        ),
    ]
    for number, question, artifact, observed in rows:
        print(
            f"| {number} | {question} | `{artifact.group}:{artifact.name}` | {artifact.observed} | `{observed}` |"
        )

    print(
        f"| 4 | Task 1's compiled fixture: the value inlines | `com.acme.mn.OrderMessaging$SqsConsumer` | fixture (recompiled by run.sh) | `{q4_fixture(fixture_classes)}` |"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-21 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
