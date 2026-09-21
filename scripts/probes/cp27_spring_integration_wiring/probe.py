"""CP-27's measurement half: the Spring Integration wiring surface spec 2026-09-21 §3–§6
reads — `IntegrationFlow.from`'s overloads and the absence of `IntegrationFlows` (F1);
the members `BaseIntegrationFlowDefinition` declares (F3) with the descriptors the step
model keys by, and what each divert member CONSTRUCTS (the router, gateway or
scatter-gather handler its body `new`s — the bytecode behind the `divert` classification);
`MessageProducerSupport`'s two output-channel setters; the ten
`Kafka.messageDrivenChannelAdapter` and four `inboundChannelAdapter` descriptors (F2) with
the producer spec's `topic` setters; the `Amqp` factories, the outbound spec's and the
outbound endpoint's address setters (F4), the inbound adapter's constructors, the
container's queue setters (F5), the `ConsumerProperties`/`ContainerProperties`/`Queue`
constructors; `@Bean`'s and `@Qualifier`'s attributes (F8); the invoke order inside
`DefaultListableBeanFactory.determineAutowireCandidate` (§3a's container rung); and the
step OWNERS the fixture's own compiled flow classes name at their call sites.

Called by `run.sh`, which resolves the jars and compiles the fixture; this script
downloads nothing. Like CP-16 through CP-26 it reads each jar's own identity out of its
own bytes before it measures anything and refuses to file a cell under a version the
archive did not claim (GUIDELINES §5.4, and CP-5's failure it exists to prevent). The
fixture's classes carry no manifest: their cells are filed under the class-file version
`javap -v` reports for them, which is the one identity a compiled class states itself.
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
                f"{jar.name} reports version {self.observed!r} but was expected to report "
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


def _javap(*arguments: str, classpath: Path, check: bool = True) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0 and check:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _members(output: str) -> list[tuple[str, str]]:
    """`(name, descriptor)` for every declared member of a `javap -p -s` listing,
    in declaration order — the line naming the member, then its `descriptor:`."""
    found: list[tuple[str, str]] = []
    lines = output.splitlines()
    for index, line in enumerate(lines[:-1]):
        if not line.startswith("  ") or line.startswith("    ") or "descriptor:" in line:
            continue
        if "descriptor:" not in lines[index + 1]:
            continue
        declaration = line.strip().rstrip(";")
        match = re.search(r"([\w$<>]+)\(", declaration)
        if match is None:
            continue
        found.append((match.group(1), lines[index + 1].split("descriptor:", 1)[1].strip()))
    return found


def _public_descriptors(output: str, name: str) -> list[str]:
    """Every `descriptor:` following a `public` declaration of `name(`."""
    found: list[str] = []
    lines = output.splitlines()
    for index, line in enumerate(lines[:-1]):
        if (
            line.startswith("  public")
            and re.search(rf"[\s.]{re.escape(name)}\(", line)
            and "descriptor:" in lines[index + 1]
        ):
            found.append(lines[index + 1].split("descriptor:", 1)[1].strip())
    return found


def _constructor_descriptors(output: str) -> list[str]:
    """Every public constructor's descriptor: a declaration naming the class itself."""
    found: list[str] = []
    lines = output.splitlines()
    for index, line in enumerate(lines[:-1]):
        if not line.startswith("  public"):
            continue
        declaration = line.strip().rstrip(";")
        if re.match(r"public (\w+\.)+\w+\(", declaration) and "descriptor:" in lines[index + 1]:
            found.append(lines[index + 1].split("descriptor:", 1)[1].strip())
    return found


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


def _step(line: str) -> str | None:
    match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _constructed(output: str, name: str) -> list[str]:
    """The classes every overload of `name` constructs (`new`), in body order, deduped —
    what the member's handler IS, read off the bytecode rather than the reference."""
    classes: list[str] = []
    for declaration, body in _bodies(output):
        if not re.search(rf"[\s.]{re.escape(name)}\(", declaration):
            continue
        for line in body:
            step = _step(line)
            if step is not None and step.startswith("new class "):
                cls = step[len("new class ") :]
                if cls not in classes:
                    classes.append(cls)
    return classes


# --- Q1: F1 — IntegrationFlows absent; IntegrationFlow.from overloads ------------


def q1_from(core: Path) -> str:
    absent = _javap(
        "-p", "org.springframework.integration.dsl.IntegrationFlows", classpath=core, check=False
    )
    output = _javap(
        "-p", "-s", "org.springframework.integration.dsl.IntegrationFlow", classpath=core
    )
    descriptors = _public_descriptors(output, "from")
    return _STEP.join(
        [
            f"IntegrationFlows: {'absent' if not absent.strip() else 'PRESENT'}",
            f"from ×{len(descriptors)}",
        ]
        + [f"from{d}" for d in descriptors]
    )


# --- Q2/Q3: F3 — the 35 members, and the descriptors the step model keys by -------

_FLOW_DEFINITION = "org.springframework.integration.dsl.BaseIntegrationFlowDefinition"
_KEYED = ("handle", "handleReactive", "channel", "fixedSubscriberChannel", "nullChannel")
_DIVERTS = (
    "route",
    "routeByException",
    "routeToRecipients",
    "gateway",
    "scatterGather",
    "publishSubscribeChannel",
    "controlBus",
    "trigger",
    "to",
    "nullChannel",
)


def q2_members(core: Path) -> str:
    output = _javap("-p", "-s", _FLOW_DEFINITION, classpath=core)
    counts: dict[str, int] = {}
    for line in output.splitlines():
        if line.startswith("  public") and "static" not in line:
            match = re.search(r"([\w$]+)\(", line)
            if match and match.group(1) != "BaseIntegrationFlowDefinition":
                counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    names = sorted(counts)
    return _STEP.join(
        [f"{len(names)} public instance members"] + [f"{n} ×{counts[n]}" for n in names]
    )


def q3_keyed_descriptors(core: Path) -> str:
    output = _javap("-p", "-s", _FLOW_DEFINITION, classpath=core)
    cells = []
    for name in _KEYED:
        for descriptor in _public_descriptors(output, name):
            cells.append(f"{name}{descriptor}")
    return _STEP.join(cells)


def q3b_subclass_members(core: Path) -> str:
    """The members `IntegrationFlowDefinition` — the type every flow call site is
    compiled against — declares ON ITS OWN, beside the base's: the lambda `handle`
    is one of them, so a step model keyed on the base alone would miss it."""
    output = _javap(
        "-p", "-s", "org.springframework.integration.dsl.IntegrationFlowDefinition", classpath=core
    )
    header = next(
        line.strip().rstrip(" {") for line in output.splitlines() if line.startswith("public ")
    )
    cells = [header]
    for name, descriptor in _members(output):
        if name != "IntegrationFlowDefinition":
            cells.append(f"{name}{descriptor}")
    return _STEP.join(cells)


def q4_diverts(core: Path) -> str:
    output = _javap("-p", "-c", _FLOW_DEFINITION, classpath=core)
    cells = []
    for name in _DIVERTS:
        constructed = _constructed(output, name)
        cells.append(f"{name} -> {', '.join(constructed) or '(delegates; constructs nothing)'}")
    return _STEP.join(cells)


# --- Q5: MessageProducerSupport setters -------------------------------------------


def q5_producer_support(core: Path) -> str:
    output = _javap(
        "-p",
        "-s",
        "org.springframework.integration.endpoint.MessageProducerSupport",
        classpath=core,
    )
    cells = []
    for name in ("setOutputChannel", "setOutputChannelName"):
        for descriptor in _public_descriptors(output, name):
            cells.append(f"{name}{descriptor}")
    return _STEP.join(cells)


# --- Q6/Q7: F2 — the Kafka factories and the producer spec's topic setters --------


def q6_kafka_factories(kafka_dsl: Path) -> str:
    output = _javap(
        "-p", "-s", "org.springframework.integration.kafka.dsl.Kafka", classpath=kafka_dsl
    )
    cells = []
    for name in ("messageDrivenChannelAdapter", "inboundChannelAdapter", "outboundChannelAdapter"):
        descriptors = _public_descriptors(output, name)
        cells.append(f"{name} ×{len(descriptors)}")
        cells.extend(f"{name}{d}" for d in descriptors)
    others = sorted(
        {
            m.group(1)
            for line in output.splitlines()
            if line.startswith("  public static")
            for m in [re.search(r"([\w$]+)\(", line)]
            if m
            and m.group(1)
            not in (
                "messageDrivenChannelAdapter",
                "inboundChannelAdapter",
                "outboundChannelAdapter",
            )
        }
    )
    cells.append(f"other factories: {', '.join(others)}")
    return _STEP.join(cells)


def q7_kafka_topic(kafka_dsl: Path) -> str:
    output = _javap(
        "-p",
        "-s",
        "org.springframework.integration.kafka.dsl.KafkaProducerMessageHandlerSpec",
        classpath=kafka_dsl,
    )
    cells = []
    for name in ("topic", "topicExpression"):
        for descriptor in _public_descriptors(output, name):
            cells.append(f"{name}{descriptor}")
    return _STEP.join(cells)


# --- Q8–Q11: F4/F5 — the AMQP side -------------------------------------------------


def q8_amqp_factories(amqp_dsl: Path) -> str:
    output = _javap("-p", "-s", "org.springframework.integration.amqp.dsl.Amqp", classpath=amqp_dsl)
    cells = []
    for name in ("inboundAdapter", "outboundAdapter"):
        descriptors = _public_descriptors(output, name)
        cells.append(f"{name} ×{len(descriptors)}")
        cells.extend(f"{name}{d}" for d in descriptors)
    others = sorted(
        {
            m.group(1)
            for line in output.splitlines()
            if line.startswith("  public static")
            for m in [re.search(r"([\w$]+)\(", line)]
            if m and m.group(1) not in ("inboundAdapter", "outboundAdapter")
        }
    )
    cells.append(f"other factories: {', '.join(others)}")
    return _STEP.join(cells)


def q9_amqp_outbound_spec(amqp_dsl: Path) -> str:
    cells = []
    for owner in (
        "org.springframework.integration.amqp.dsl.AmqpOutboundChannelAdapterSpec",
        "org.springframework.integration.amqp.dsl.AmqpBaseOutboundEndpointSpec",
    ):
        output = _javap("-p", "-s", owner, classpath=amqp_dsl)
        header = next(
            line.strip().rstrip(" {") for line in output.splitlines() if line.startswith("public ")
        )
        cells.append(header)
        for name in (
            "exchangeName",
            "exchangeNameExpression",
            "exchangeNameFunction",
            "routingKey",
            "routingKeyExpression",
            "routingKeyFunction",
        ):
            for descriptor in _public_descriptors(output, name):
                cells.append(f"{owner.rsplit('.', 1)[1]}.{name}{descriptor}")
    return _STEP.join(cells)


def q10_amqp_outbound_endpoint(amqp_dsl: Path) -> str:
    output = _javap(
        "-p",
        "-s",
        "org.springframework.integration.amqp.outbound.AmqpOutboundEndpoint",
        classpath=amqp_dsl,
    )
    base = _javap(
        "-p",
        "-s",
        "org.springframework.integration.amqp.outbound.AbstractAmqpOutboundEndpoint",
        classpath=amqp_dsl,
    )
    cells = [f"constructors: {', '.join(_constructor_descriptors(output))}"]
    for name in (
        "setExchangeName",
        "setExchangeNameExpression",
        "setExchangeNameExpressionString",
        "setRoutingKey",
        "setRoutingKeyExpression",
        "setRoutingKeyExpressionString",
    ):
        for where, listing in (
            ("AmqpOutboundEndpoint", output),
            ("AbstractAmqpOutboundEndpoint", base),
        ):
            for descriptor in _public_descriptors(listing, name):
                cells.append(f"{where}.{name}{descriptor}")
    return _STEP.join(cells)


def q11_amqp_inbound_adapter(amqp_dsl: Path) -> str:
    output = _javap(
        "-p",
        "-s",
        "org.springframework.integration.amqp.inbound.AmqpInboundChannelAdapter",
        classpath=amqp_dsl,
    )
    return _STEP.join(f"<init>{d}" for d in _constructor_descriptors(output))


def q12_container_setters(rabbit: Path) -> str:
    output = _javap(
        "-p",
        "-s",
        "org.springframework.amqp.rabbit.listener.AbstractMessageListenerContainer",
        classpath=rabbit,
    )
    cells = []
    for name in (
        "setQueueNames",
        "addQueueNames",
        "removeQueueNames",
        "setQueues",
        "addQueues",
        "removeQueues",
    ):
        for descriptor in _public_descriptors(output, name):
            cells.append(f"{name}{descriptor}")
    for owner in (
        "org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer",
        "org.springframework.amqp.rabbit.listener.DirectMessageListenerContainer",
    ):
        listing = _javap("-p", "-s", owner, classpath=rabbit)
        cells.append(
            f"{owner.rsplit('.', 1)[1]}.<init>: {', '.join(_constructor_descriptors(listing))}"
        )
    return _STEP.join(cells)


def q13_constructors(kafka: Path, amqp: Path) -> str:
    cells = []
    for owner, jar in (
        ("org.springframework.kafka.listener.ConsumerProperties", kafka),
        ("org.springframework.kafka.listener.ContainerProperties", kafka),
        ("org.springframework.amqp.core.Queue", amqp),
    ):
        listing = _javap("-p", "-s", owner, classpath=jar)
        cells.append(
            f"{owner.rsplit('.', 1)[1]}.<init>: {', '.join(_constructor_descriptors(listing))}"
        )
    return _STEP.join(cells)


# --- Q14/Q15: F8 and the autowire candidate order ---------------------------------


def q14_bean_attributes(context: Path, beans: Path) -> str:
    cells = []
    for owner, jar in (
        ("org.springframework.context.annotation.Bean", context),
        ("org.springframework.beans.factory.annotation.Qualifier", beans),
    ):
        listing = _javap("-p", "-s", owner, classpath=jar)
        attrs = [
            f"{name}{descriptor}"
            for name, descriptor in _members(listing)
            if descriptor.startswith("()")
        ]
        cells.append(f"@{owner.rsplit('.', 1)[1]}: {', '.join(attrs)}")
    return _STEP.join(cells)


def q15_autowire_candidate(beans: Path) -> str:
    output = _javap(
        "-p",
        "-c",
        "org.springframework.beans.factory.support.DefaultListableBeanFactory",
        classpath=beans,
    )
    for declaration, body in _bodies(output):
        if "determineAutowireCandidate(" in declaration:
            calls = [
                s.split("Method ", 1)[1].split(":", 1)[0].rsplit("/", 1)[-1]
                for s in (_step(line) for line in body)
                if s is not None
                and s.startswith(
                    ("invokevirtual", "invokespecial", "invokestatic", "invokeinterface")
                )
                and "Method " in s
            ]
            return _STEP.join(calls)
    raise ProbeError("no determineAutowireCandidate body found")


# --- Q16: the fixture's own compiled flow classes ---------------------------------

_FIXTURE_CLASSES = (
    "com.example.siprobe.Shape1DslFlows",
    "com.example.siprobe.Shape3PolledAndOtherBrokers",
    "com.example.siprobe.Shape5Flows",
)


def fixture_identity(classes: Path) -> str:
    output = _javap("-v", _FIXTURE_CLASSES[0], classpath=classes)
    match = re.search(r"major version: (\d+)", output)
    if match is None:
        raise ProbeError("the fixture's class file states no major version")
    return f"class file {match.group(1)}"


def q16_fixture_owners(classes: Path) -> str:
    owners: dict[str, list[str]] = {}
    for name in _FIXTURE_CLASSES:
        output = _javap("-p", "-c", name, classpath=classes)
        for line in output.splitlines():
            step = _step(line)
            if step is None or not step.startswith("invoke") or "Method " not in step:
                continue
            target = step.split("Method ", 1)[1]
            owner, rest = target.split(".", 1)
            if not owner.startswith("org/springframework/integration/dsl/"):
                continue
            member = rest.split(":", 1)[0]
            owners.setdefault(owner.rsplit("/", 1)[1], []).append(member)
    return _STEP.join(
        f"{owner}: {', '.join(sorted(set(members)))}" for owner, members in sorted(owners.items())
    )


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    classes: Path | None = None
    for spec in specs:
        key, group, name, requested, path = spec.split("|")
        if key == "fixture":
            classes = Path(path)
            continue
        artifacts[key] = Artifact(key, group, name, requested, Path(path))
    if classes is None:
        raise ProbeError("no fixture classes directory handed in")
    core, kafka_dsl, amqp_dsl = artifacts["core"], artifacts["kafka-dsl"], artifacts["amqp-dsl"]
    rabbit, amqp, kafka = artifacts["rabbit"], artifacts["amqp"], artifacts["kafka"]
    context, beans = artifacts["context"], artifacts["beans"]
    fixture = fixture_identity(classes)

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
        + " | ".join(["yes"] * len(columns))
        + " |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    def row(number: str, question: str, artifact: Artifact | None, observed: str) -> None:
        where = (
            f"`{artifact.group}:{artifact.name}` | {artifact.observed}"
            if artifact is not None
            else f"`fixtures/spring-integration-probe` (target/classes) | {fixture}"
        )
        print(f"| {number} | {question} | {where} | `{observed}` |")

    row(
        "1",
        "F1: `IntegrationFlows` present?; `IntegrationFlow.from` public overloads",
        core,
        q1_from(core.jar),
    )
    row(
        "2",
        "F3: `BaseIntegrationFlowDefinition` public instance members, with overload counts",
        core,
        q2_members(core.jar),
    )
    row(
        "3",
        "F3: the descriptors the step model keys by — `handle`, `handleReactive`, `channel`, `fixedSubscriberChannel`, `nullChannel`",
        core,
        q3_keyed_descriptors(core.jar),
    )
    row(
        "3b",
        "F3: `IntegrationFlowDefinition`'s OWN public members (the subclass every flow is compiled against)",
        core,
        q3b_subclass_members(core.jar),
    )
    row(
        "4",
        "F3: what each divert member (and `nullChannel`) constructs — `new` in its bodies",
        core,
        q4_diverts(core.jar),
    )
    row(
        "5",
        "F10/§4: `MessageProducerSupport` output-channel setters",
        core,
        q5_producer_support(core.jar),
    )
    row(
        "6",
        "F2: `Kafka` source and sink factories by descriptor; the other factories",
        kafka_dsl,
        q6_kafka_factories(kafka_dsl.jar),
    )
    row(
        "7",
        "§5: `KafkaProducerMessageHandlerSpec.topic`/`topicExpression` overloads",
        kafka_dsl,
        q7_kafka_topic(kafka_dsl.jar),
    )
    row(
        "8",
        "§5: `Amqp` adapter factories by descriptor; the other factories",
        amqp_dsl,
        q8_amqp_factories(amqp_dsl.jar),
    )
    row(
        "9",
        "F4: the outbound spec's address setters and the type each is declared on",
        amqp_dsl,
        q9_amqp_outbound_spec(amqp_dsl.jar),
    )
    row(
        "10",
        "F4: `AmqpOutboundEndpoint` constructors and address setters (declared on the abstract base)",
        amqp_dsl,
        q10_amqp_outbound_endpoint(amqp_dsl.jar),
    )
    row(
        "11",
        "§4: `AmqpInboundChannelAdapter` constructors",
        amqp_dsl,
        q11_amqp_inbound_adapter(amqp_dsl.jar),
    )
    row(
        "12",
        "F5: `AbstractMessageListenerContainer` queue setters; the two containers' constructors",
        rabbit,
        q12_container_setters(rabbit.jar),
    )
    row(
        "13",
        "F5: `ConsumerProperties`, `ContainerProperties` and `Queue` constructors",
        kafka,
        q13_constructors(kafka.jar, amqp.jar),
    )
    row(
        "14",
        "F8: `@Bean` and `@Qualifier` attributes",
        context,
        q14_bean_attributes(context.jar, beans.jar),
    )
    row(
        "15",
        "§3a: `DefaultListableBeanFactory.determineAutowireCandidate` — the calls its body makes, in order",
        beans,
        q15_autowire_candidate(beans.jar),
    )
    row(
        "16",
        "§5: the owners the fixture's compiled flows name at their `integration.dsl` call sites",
        None,
        q16_fixture_owners(classes),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-27 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
