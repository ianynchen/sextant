"""CP-36: what a Spring Cloud service-discovery lookup hands back, and what identifies it.

Spec `docs/superpowers/specs/2026-10-17-outgoing-endpoint-addresses-design.md` §4,
`OI-142`. The question is narrow: a module that resolves its own peer addresses through
`DiscoveryClient` writes

    discoveryClient.getInstances("customers-service").get(0).getUri()

and there is no URL anywhere in its class file. So which part of that chain carries the
identity of the service being called, and does the rest of the chain preserve it?

Three readings, each off the published jars rather than off documentation:

1. **`DiscoveryClient.getInstances`'s descriptor** — does it take the service id as one
   argument, and does it hand back a collection? If it returns one instance rather than a
   list, the chain this probe exists for does not exist.
2. **`ServiceInstance`'s members, and what `createUri` BUILDS** — the format string is the
   evidence for the claim that the runtime URI carries no path, which is what makes the
   literal tail of a concatenation the whole path rather than a suffix of one.
3. **`getUri`'s descriptor** — that it takes nothing, which is why no `arg` can name its
   identity and why `from_receiver` had to exist.

The identity read back for the column header is each jar's own
`Implementation-Version` from its manifest, not the version this harness was asked for;
`run.sh` aborts on a disagreement.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

_STEP = " ; "
_CLIENT = "org.springframework.cloud.client.discovery.DiscoveryClient"
_INSTANCE = "org.springframework.cloud.client.ServiceInstance"


@dataclass(frozen=True)
class Artifact:
    key: str
    group: str
    name: str
    requested: str
    jar: Path

    @property
    def observed(self) -> str:
        """The version the ARCHIVE reports about itself, read before anything is measured."""
        with zipfile.ZipFile(self.jar) as archive:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        match = re.search(r"^Implementation-Version:\s*(.+?)\s*$", manifest, re.MULTILINE)
        return match.group(1) if match else "unreported"


def _javap(*arguments: str, classpath: Path) -> str:
    """`javap` with the classpath FIRST, which is the order it accepts: options, then the
    classes. Written the other way round the first time and every cell came back empty —
    which is why the write-up's verdicts are read off this table rather than retyped."""
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _signature(output: str, member: str) -> str:
    """One declared member's line as javap prints it, whitespace squeezed."""
    for line in output.splitlines():
        if f" {member}(" in line or line.strip().startswith(member + "("):
            return " ".join(line.split()).rstrip(";")
    return "absent"


def q1_get_instances(jar: Path) -> str:
    output = _javap("-p", _CLIENT, classpath=jar)
    return _signature(output, "getInstances")


def q2_service_instance(jar: Path) -> str:
    output = _javap("-p", _INSTANCE, classpath=jar)
    members = [
        " ".join(line.split()).rstrip(";")
        for line in output.splitlines()
        if "(" in line and "class" not in line and "interface" not in line
    ]
    built = _javap("-p", "-c", "-constants", _INSTANCE, classpath=jar)
    formats = re.findall(r'// String (%s(?:://|:)?[^\s"]*)', built)
    return _STEP.join([f"members {sorted(members)}", f"createUri builds {formats or 'nothing'}"])


def q3_get_uri(jar: Path) -> str:
    output = _javap("-p", _INSTANCE, classpath=jar)
    return _signature(output, "getUri")


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        key, group, name, requested, path = spec.split("|")
        artifacts[key] = Artifact(key, group, name, requested, Path(path))
    commons = artifacts["commons"]

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
            f"| {number} | {question} | `{artifact.group}:{artifact.name}` "
            f"| {artifact.observed} | `{observed}` |"
        )

    row(
        "1",
        "`DiscoveryClient.getInstances` — what it takes and hands back",
        commons,
        q1_get_instances(commons.jar),
    )
    row(
        "2",
        "`ServiceInstance`'s members, and the format `createUri` builds",
        commons,
        q2_service_instance(commons.jar),
    )
    row(
        "3",
        "`ServiceInstance.getUri` — how many arguments name its identity",
        commons,
        q3_get_uri(commons.jar),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
