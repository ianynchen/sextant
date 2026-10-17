"""CP-35: where a Spring Cloud starter's version actually lives, and what spells it.

Walks `<dependencyManagement>` — `<parent>` links and `<scope>import</scope>` entries
alike — from one BOM in the local Maven repository, and reports for each requested
artifact the BOM that manages it, how many hops away that is, and the RAW version string
written there.

The raw string is the point. `scripts/probes/cp33_binding_writes.md` measures bytecode;
this measures other people's poms, and the finding it exists to record is that a Spring
Cloud component BOM versions its own artifacts as `${project.version}` — a Maven BUILT-IN
that is not an entry in any `<properties>` block, so a reader that interpolates only from
`<properties>` resolves nothing and (in our case) dropped the entry with no message.

Called by `run.sh`, which owns the identity check: the column header is the `<version>`
this script read out of the pom it opened, printed on the `BOM-VERSION` line below, and
`run.sh` aborts when that disagrees with the coordinate it was asked for.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.etree import ElementTree

M2 = Path.home() / ".m2" / "repository"
NS = "{http://maven.apache.org/POM/4.0.0}"
PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")
# A pom that names itself in a cycle is a build Maven would refuse; the visited set is
# what makes an exhaustive walk safe, so this is a backstop and not the termination rule.
MAX_HOPS = 40


def pom_of(group: str, artifact: str, version: str) -> Path:
    return M2 / Path(*group.split(".")) / artifact / version / f"{artifact}-{version}.pom"


def child(node: ElementTree.Element, tag: str) -> str | None:
    found = node.find(NS + tag)
    return found.text.strip() if found is not None and found.text else None


def properties_of(root: ElementTree.Element, inherited: dict[str, str]) -> dict[str, str]:
    merged = dict(inherited)
    block = root.find(NS + "properties")
    if block is not None:
        for entry in block:
            if entry.text:
                merged[entry.tag.replace(NS, "")] = entry.text.strip()
    return merged


def expanded(value: str, properties: dict[str, str]) -> str | None:
    """`value` with every `${…}` replaced, or None where one names nothing defined.

    Deliberately NOT given Maven's built-ins: this harness reproduces what a reader
    limited to `<properties>` sees, because that is the behaviour under measurement.
    """
    current = value.strip()
    for _ in range(10):
        if "${" not in current:
            return current
        replaced = PLACEHOLDER.sub(lambda hit: properties.get(hit.group(1), hit.group(0)), current)
        if replaced == current:
            return None
        current = replaced
    return None


def walk(
    group: str,
    artifact: str,
    version: str,
    target: str,
    hops: int = 0,
    visited: frozenset[tuple[str, str, str]] = frozenset(),
    properties: dict[str, str] | None = None,
) -> tuple[int, str, str, str] | None:
    """(hops, managing BOM, its version, the RAW version string) for `target`, or None."""
    here = (group, artifact, version)
    if here in visited or hops > MAX_HOPS:
        return None
    path = pom_of(group, artifact, version)
    if not path.is_file():
        return None
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError:
        return None
    visited = visited | {here}
    properties = properties_of(root, properties or {})

    imports: list[tuple[str, str, str]] = []
    block = root.find(NS + "dependencyManagement")
    if block is not None:
        for dependency in block.iter(NS + "dependency"):
            name = child(dependency, "artifactId")
            raw = child(dependency, "version")
            scope = child(dependency, "scope")
            if raw is None or name is None:
                continue
            if name == target and scope != "import":
                return hops, artifact, version, raw
            if scope == "import":
                settled = expanded(raw, properties)
                if settled is not None:
                    imports.append((child(dependency, "groupId") or group, name, settled))

    parent = root.find(NS + "parent")
    if parent is not None:
        found = walk(
            child(parent, "groupId") or group,
            child(parent, "artifactId") or "",
            child(parent, "version") or "",
            target,
            hops + 1,
            visited,
            properties,
        )
        if found is not None:
            return found

    for import_group, import_artifact, import_version in imports:
        found = walk(
            import_group, import_artifact, import_version, target, hops + 1, visited, properties
        )
        if found is not None:
            return found
    return None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: chain.py <group:artifact:version> <targetArtifactId>...", file=sys.stderr)
        return 2
    group, artifact, asked = argv[0].split(":")
    targets = argv[1:]

    path = pom_of(group, artifact, asked)
    if not path.is_file():
        print(f"not in the local repository: {path}", file=sys.stderr)
        return 1
    root = ElementTree.parse(path).getroot()
    # The identity, read out of the opened file rather than echoed back from the
    # argument. `run.sh` compares the two and aborts on a disagreement — the CP-5
    # failure this convention exists to prevent.
    reported = child(root, "version") or ""
    print(f"BOM-VERSION {reported}")

    for target in targets:
        found = walk(group, artifact, asked, target)
        if found is None:
            print(f"ROW {target}|not found|-|-")
            continue
        hops, managing, managing_version, raw = found
        print(f"ROW {target}|{managing}:{managing_version}|{hops}|{raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
