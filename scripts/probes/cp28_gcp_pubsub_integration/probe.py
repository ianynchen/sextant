"""CP-28's measurement half: the spring-cloud-gcp-pubsub 5.1.2 surface spec 2026-09-21
§4 and §6 read (F10) — `PubSubInboundChannelAdapter`'s constructor and the type it
extends (`MessageProducerSupport`, whose two output-channel setters the adapter inherits
and `IntegrationFlow.from(MessageProducerSupport)` accepts); `PubSubMessageHandler`'s
constructor, the type it extends, `setTopic` and the two expression setters; and
`PubSubMessageSource`'s constructor — the polled sibling whose shape is the near-miss
the catalog's declining test uses (a `(operations, String)` constructor on another type).

Called by `run.sh`, which resolves the jars; this script downloads nothing. Like CP-16
through CP-27 it reads each jar's own identity out of its own bytes before it measures
anything and refuses to file a cell under a version the archive did not claim
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


def _javap(*arguments: str, classpath: str) -> str:
    result = subprocess.run(
        ["javap", "-cp", classpath, *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _header(output: str) -> str:
    return next(
        line.strip().rstrip(" {") for line in output.splitlines() if line.startswith("public ")
    )


def _public_descriptors(output: str, name: str) -> list[str]:
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
    found: list[str] = []
    lines = output.splitlines()
    for index, line in enumerate(lines[:-1]):
        if not line.startswith("  public"):
            continue
        declaration = line.strip().rstrip(";")
        if re.match(r"public (\w+\.)+\w+\(", declaration) and "descriptor:" in lines[index + 1]:
            found.append(lines[index + 1].split("descriptor:", 1)[1].strip())
    return found


_INBOUND = "com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter"
_OUTBOUND = "com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler"
_SOURCE = "com.google.cloud.spring.pubsub.integration.inbound.PubSubMessageSource"


def q1_inbound_adapter(classpath: str) -> str:
    output = _javap("-p", "-s", _INBOUND, classpath=classpath)
    cells = [_header(output), f"<init>: {', '.join(_constructor_descriptors(output))}"]
    own = [
        name
        for name in ("setOutputChannel", "setOutputChannelName")
        if _public_descriptors(output, name)
    ]
    cells.append(f"redeclares output-channel setters: {', '.join(own) or 'none (inherited)'}")
    return _STEP.join(cells)


def q2_producer_support(classpath: str) -> str:
    output = _javap(
        "-p",
        "-s",
        "org.springframework.integration.endpoint.MessageProducerSupport",
        classpath=classpath,
    )
    cells = [_header(output)]
    for name in ("setOutputChannel", "setOutputChannelName"):
        for descriptor in _public_descriptors(output, name):
            cells.append(f"{name}{descriptor}")
    flow = _javap(
        "-p", "-s", "org.springframework.integration.dsl.IntegrationFlow", classpath=classpath
    )
    accepting = [d for d in _public_descriptors(flow, "from") if "MessageProducerSupport" in d]
    cells.append(f"IntegrationFlow.from accepting it: {', '.join(accepting)}")
    return _STEP.join(cells)


def q3_message_handler(classpath: str) -> str:
    output = _javap("-p", "-s", _OUTBOUND, classpath=classpath)
    cells = [_header(output), f"<init>: {', '.join(_constructor_descriptors(output))}"]
    for name in ("setTopic", "setTopicExpression", "setTopicExpressionString"):
        for descriptor in _public_descriptors(output, name):
            cells.append(f"{name}{descriptor}")
    return _STEP.join(cells)


def q4_message_source(classpath: str) -> str:
    output = _javap("-p", "-s", _SOURCE, classpath=classpath)
    return _STEP.join([_header(output), f"<init>: {', '.join(_constructor_descriptors(output))}"])


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        key, group, name, requested, jar = spec.split("|")
        artifacts[key] = Artifact(key, group, name, requested, Path(jar))
    pubsub, core = artifacts["pubsub"], artifacts["core"]
    classpath = f"{pubsub.jar}:{core.jar}"

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

    def row(number: str, question: str, artifact: Artifact, observed: str) -> None:
        print(
            f"| {number} | {question} | `{artifact.group}:{artifact.name}` | {artifact.observed} | `{observed}` |"
        )

    row(
        "1",
        "F10: `PubSubInboundChannelAdapter` — supertype, constructor, whether it redeclares the output-channel setters",
        pubsub,
        q1_inbound_adapter(classpath),
    )
    row(
        "2",
        "F10/§5: `MessageProducerSupport`'s setters, and the `IntegrationFlow.from` overload accepting it",
        core,
        q2_producer_support(classpath),
    )
    row(
        "3",
        "F10: `PubSubMessageHandler` — supertype, constructor, `setTopic` and the two expression setters",
        pubsub,
        q3_message_handler(classpath),
    )
    row(
        "4",
        "the near-miss shape: `PubSubMessageSource` — supertype and constructor",
        pubsub,
        q4_message_source(classpath),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-28 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
