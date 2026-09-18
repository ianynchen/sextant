"""CP-20's measurement half: `@KafkaListener.batch()`'s type and default, the
post-processor's `StringUtils.hasText` -> `Boolean.parseBoolean` ->
`setBatchListener` parse, the batch listener adapter's accepted shapes, and
the container factory's own independent, config-driven `setBatchListener`.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. Like CP-16/CP-17/CP-18/CP-19 it reads each jar's own identity out of
its own bytes before it measures anything and refuses to file a cell under a
version the artifact did not claim (GUIDELINES §5.4, and CP-5's failure it
exists to prevent).

Row 5 is not a jar read at all — it is a grep over this repository's own
catalog files, so its identity is the git commit `run.sh` resolves HEAD to
rather than an `Implementation-Version`.
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


def _javap(*arguments: str, classpath: Path) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments], capture_output=True, text=True, check=False
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


def q1_batch_attribute(artifact: Artifact) -> str:
    """Q1. `batch()`'s declared type and default value."""
    output = _javap(
        "-v", "org.springframework.kafka.annotation.KafkaListener", classpath=artifact.jar
    )
    match = re.search(
        r"public abstract (\S+) batch\(\);.*?default_value: (\S+)\n(\s*\"[^\"]*\")?",
        output,
        re.DOTALL,
    )
    if not match:
        raise ProbeError("no batch() attribute found")
    literal = match.group(3)
    default = literal.strip() if literal else "(empty string)"
    return f"batch(): {match.group(1)} ; AnnotationDefault: {default}"


def q2_post_processor_parse(artifact: Artifact) -> str:
    """Q2. The post-processor's `batch()` -> `hasText` -> `parseBoolean` ->
    `setBatchListener` sequence."""
    output = _javap(
        "-c",
        "-p",
        "org.springframework.kafka.annotation.KafkaListenerAnnotationBeanPostProcessor",
        classpath=artifact.jar,
    )
    lines = output.splitlines()
    steps = []
    for i, line in enumerate(lines):
        step = _step(line)
        if step and "KafkaListener.batch:()" in step:
            # Capture this and the surrounding ~6 instructions: hasText gate,
            # then (on the branch taken) the second read and parseBoolean/
            # setBatchListener pair.
            for j in range(i, min(i + 12, len(lines))):
                s = _step(lines[j])
                if s:
                    steps.append(s)
                if s and "setBatchListener" in s:
                    return _STEP.join(steps)
    raise ProbeError("no batch()->hasText->parseBoolean->setBatchListener sequence found")


def q3_batch_adapter_shapes(artifact: Artifact) -> str:
    """Q3. `BatchMessagingMessageListenerAdapter.onMessage`'s accepted shapes."""
    output = _javap(
        "-p",
        "org.springframework.kafka.listener.adapter.BatchMessagingMessageListenerAdapter",
        classpath=artifact.jar,
    )
    shapes = [
        line.strip().rstrip(";")
        for line in output.splitlines()
        if re.search(r"\bonMessage\(", line) and "lambda" not in line
    ]
    if not shapes:
        raise ProbeError("no onMessage overloads found")
    return _STEP.join(shapes)


def q4_factory_batch_listener(artifact: Artifact) -> str:
    """Q4. The factory's own, independent, config-driven `setBatchListener` —
    absent from the concrete factory, present (and annotation-free) on its
    abstract base."""
    concrete = _javap(
        "-p",
        "org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory",
        classpath=artifact.jar,
    )
    concrete_has_batch = "batch" in concrete.lower()
    base = _javap(
        "-p",
        "org.springframework.kafka.config.AbstractKafkaListenerContainerFactory",
        classpath=artifact.jar,
    )
    base_members = [
        line.strip().rstrip(";")
        for line in base.splitlines()
        if "batch" in line.lower() and "Interceptor" not in line
    ]
    return (
        f"ConcurrentKafkaListenerContainerFactory declares batch member: {concrete_has_batch} ; "
        f"AbstractKafkaListenerContainerFactory: {_STEP.join(base_members)}"
    )


def q5_message_wrapper(repo: Path) -> str:
    """Q5. Whether `List<Message<T>>` is declared as a wrapper type in the
    shipped catalogs — a repository grep, not a jar read."""
    hits = []
    for name in ("spring-kafka.yml", "spring-kafka-message.yml"):
        path = repo / "src" / "sextant" / "catalogs" / name
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        found = bool(re.search(r"Message<|springframework\.messaging\.Message", text))
        hits.append(f"{name}: {'FOUND' if found else 'no match'}")
    return _STEP.join(hits)


def main(specs: list[str]) -> int:
    artifacts: list[Artifact] = []
    repo = None
    for spec in specs:
        if spec.startswith("REPO="):
            repo = Path(spec.split("=", 1)[1])
            continue
        key, group, name, version, jar = spec.split("|")
        artifacts.append(Artifact(key, group, name, version, Path(jar)))
    if repo is None:
        raise ProbeError("no REPO= argument given")

    columns = sorted({a.observed for a in artifacts})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(sorted(f"{a.group}:{a.name}" for a in artifacts if a.observed == v))
            for v in columns
        )
        + " |"
    )
    print("| identity read from the archive itself | " + " | ".join(["yes"] * len(columns)) + " |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    for artifact in artifacts:
        print(
            f"| 1 | batch()'s declared type and default | `{artifact.group}:{artifact.name}` | {artifact.observed} | `{q1_batch_attribute(artifact)}` |"
        )
        print(
            f"| 2 | the post-processor's batch()->hasText->parseBoolean->setBatchListener parse | `{artifact.group}:{artifact.name}` | {artifact.observed} | `{q2_post_processor_parse(artifact)}` |"
        )
        print(
            f"| 3 | BatchMessagingMessageListenerAdapter.onMessage's accepted shapes | `{artifact.group}:{artifact.name}` | {artifact.observed} | `{q3_batch_adapter_shapes(artifact)}` |"
        )
        print(
            f"| 4 | the factory's own, config-driven setBatchListener | `{artifact.group}:{artifact.name}` | {artifact.observed} | `{q4_factory_batch_listener(artifact)}` |"
        )

    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(
        f"| 5 | List<Message<T>> as a wrapper type in the shipped catalogs | `spring-kafka.yml, spring-kafka-message.yml` | repo@{commit} | `{q5_message_wrapper(repo)}` |"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-20 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
