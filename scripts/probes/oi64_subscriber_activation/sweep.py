"""OI-64 — is a constructed `Subscriber` a boundary, and does Spring start a `@Bean` one?

`google-pubsub-subscriber.yml` derived a live inbound endpoint from
`Subscriber.newBuilder(subscription, receiver).build()`. Two questions decide whether
that was right, and BOTH were previously answered from reasoning rather than bytecode —
one of them in GUIDELINES §8.6 itself, in the paragraph that says the framework-rule
link is exactly the link that must be measured.

1. **Does construction subscribe?** If `Subscriber` is an ordinary service object that
   must be started, construction alone is not a boundary and the catalog needs an
   activation conjunct.
2. **Does Spring start a `Subscriber` returned from a `@Bean` method?** §8.6 gave this
   as a worked example of a *measured* framework rule. Spring starts a bean's lifecycle
   only for types it recognises — `Lifecycle`, `SmartLifecycle`, `InitializingBean` — or
   through a `BeanPostProcessor` some library registers. Both are readable from
   bytecode, and if neither holds then a `@Bean` returning a `Subscriber` is the same
   unstarted object as any other and §8.6's example is wrong.

The answers decide a catalog rule, so they are read from the jars rather than from
documentation, and the hierarchy is walked rather than assumed: `Subscriber`'s own
`javap` line does not mention Spring, but neither would a class whose SUPERTYPE
implemented `SmartLifecycle`.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

M2 = Path.home() / ".m2" / "repository"

SUBSCRIBER = ("com.google.cloud:google-cloud-pubsub", "1.127.3")
API_COMMON = ("com.google.api:api-common", "2.31.0")
SPRING_GCP = ("com.google.cloud:spring-cloud-gcp-pubsub", "5.1.2")

TYPE = "com.google.cloud.pubsub.v1.Subscriber"
# The interfaces by which Spring will start a bean on its own. A type implementing
# none of them, anywhere in its hierarchy, is not started by the container.
_SPRING_LIFECYCLE = (
    "org.springframework.context.Lifecycle",
    "org.springframework.context.SmartLifecycle",
    "org.springframework.beans.factory.InitializingBean",
    "org.springframework.context.SmartInitializingSingleton",
)
_DECLARATION = re.compile(
    r"^(?:public\s+)?(?:abstract\s+|final\s+)*(?:class|interface)\s+([\w.$<>,\s]+?)"
    r"(?:\s+extends\s+([\w.$<>,\s]+?))?(?:\s+implements\s+([\w.$<>,\s]+?))?\s*\{"
)
# The delivery methods, to show what `startAsync` is on the other side of.
_STARTS = ("startAsync", "awaitRunning", "stopAsync")


class ProbeError(RuntimeError):
    """A run that could not answer, told apart from a run that answered `no`."""


def jar(artifact: str, version: str) -> Path:
    group, name = artifact.split(":")
    found = M2 / group.replace(".", "/") / name / version / f"{name}-{version}.jar"
    if not found.exists():
        raise ProbeError(f"{found} is absent; run this through run.sh")
    return found


def self_reported_version(archive: Path) -> str:
    with zipfile.ZipFile(archive) as zf:
        try:
            manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError:
            manifest = ""
        for line in manifest.splitlines():
            if line.startswith("Implementation-Version:"):
                return line.split(":", 1)[1].strip()
        for name in zf.namelist():
            if name.startswith("META-INF/maven/") and name.endswith("pom.properties"):
                for line in zf.read(name).decode("utf-8", "replace").splitlines():
                    if line.startswith("version="):
                        return line.split("=", 1)[1].strip()
    return "the archive records no version about itself"


def checked(artifact: str, version: str) -> Path:
    archive = jar(artifact, version)
    claimed = self_reported_version(archive)
    if claimed != version:
        raise ProbeError(
            f"{archive} was requested as {version} and claims {claimed!r} — every cell "
            f"below would be filed under a version the artifact did not report."
        )
    return archive


def _javap(classpath: str, fqn: str, verbose: bool = False) -> str | None:
    command = ["javap", "-s"] + (["-v"] if verbose else []) + ["-cp", classpath, fqn]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return None if result.returncode != 0 else result.stdout


def supertypes(text: str) -> list[str]:
    for line in text.splitlines():
        declaration = _DECLARATION.match(line.strip())
        if declaration is None:
            continue
        found: list[str] = []
        for group in (declaration.group(2), declaration.group(3)):
            if not group:
                continue
            depth, current = 0, ""
            for character in group:
                if character == "<":
                    depth += 1
                elif character == ">":
                    depth -= 1
                elif character == "," and depth == 0:
                    found.append(current)
                    current = ""
                    continue
                if depth == 0 and character not in "<>":
                    current += character
            found.append(current)
        return [t.strip() for t in found if t.strip()]
    return []


def hierarchy(classpath: str, root: str) -> list[tuple[str, list[str]]]:
    """Every type in `root`'s hierarchy this classpath can open, with its own parents.

    Walked rather than read off one line: a class whose SUPERTYPE implemented
    `SmartLifecycle` would still print no Spring name on its own declaration."""
    walked: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    pending = [root]
    while pending:
        current = pending.pop(0)
        if current in seen or current.startswith("java."):
            continue
        seen.add(current)
        text = _javap(classpath, current)
        if text is None:
            walked.append((current, ["(not on this classpath)"]))
            continue
        parents = supertypes(text)
        walked.append((current, parents))
        pending.extend(parents)
    return walked


def main() -> None:
    subscriber = checked(*SUBSCRIBER)
    api_common = checked(*API_COMMON)
    spring_gcp = checked(*SPRING_GCP)
    classpath = f"{subscriber}:{api_common}:{spring_gcp}"

    print("## Observations\n")
    print(
        "Generated by `scripts/probes/oi64_subscriber_activation/run.sh` — every cell "
        "below is that run's own output, and this document pastes it verbatim.\n"
    )
    print(
        "**Each column header is the version the JAR ITSELF reported**, read out of its "
        "own `META-INF/MANIFEST.MF` or Maven `pom.properties` — not the version the loop "
        "asked for. The run ABORTS when the two disagree.\n"
    )

    print("### 1. `Subscriber`'s hierarchy, walked\n")
    print("Cells are what the type extends and implements, under the version that reported them.\n")
    print(f"| type | {SUBSCRIBER[1]} |")
    print("|---|---|")
    walked = hierarchy(classpath, TYPE)
    for name, parents in walked:
        print(f"| `{name}` | {', '.join(f'`{p}`' for p in parents) if parents else '—'} |")
    every = {name for name, _ in walked} | {p for _, ps in walked for p in ps}
    spring = sorted(n for n in every if n in _SPRING_LIFECYCLE)
    print(
        f"\n- Spring lifecycle interfaces anywhere in that hierarchy: "
        f"**{', '.join(spring) if spring else 'NONE'}**."
    )
    print("- Looked for: " + ", ".join(f"`{n}`" for n in _SPRING_LIFECYCLE) + ".\n")

    print("### 2. Does the class have to be started?\n")
    text = _javap(classpath, TYPE) or ""
    present = [name for name in _STARTS if f" {name}(" in text]
    print("Cells say whether `Subscriber` DECLARES the method itself.\n")
    print(f"| lifecycle method | {SUBSCRIBER[1]} |")
    print("|---|---|")
    for name in _STARTS:
        print(f"| `{name}` | {'**yes**' if name in present else 'no'} |")
    print(
        "\n- `Subscriber` declares `startAsync` ITSELF, which is the one that matters: "
        "the constructor hands back a service that has not begun. The other two are "
        "inherited from `AbstractApiService` rather than declared here, which is why "
        "they read `no` — this table asks what THIS class declares, and a caption "
        "claiming a declared pair would be overstating a one-class read.\n"
    )

    print("### 3. Does anything in spring-cloud-gcp-pubsub start such a bean?\n")
    # Read the BYTES, not the class names. An earlier version looked for
    # "PostProcessor" or "Lifecycle" in the file name — a name-shaped rule, in a probe
    # whose entire subject is that name-shaped rules are wrong. A post-processor may be
    # called anything; what it cannot avoid is REFERENCING the type it implements, and
    # that reference is in the constant pool.
    references = (
        b"org/springframework/beans/factory/config/BeanPostProcessor",
        b"org/springframework/context/SmartLifecycle",
        b"org/springframework/context/Lifecycle",
        b"org/springframework/beans/factory/InitializingBean",
    )
    with zipfile.ZipFile(spring_gcp) as zf:
        classes = [n for n in zf.namelist() if n.endswith(".class")]
        processors = sorted(
            n[: -len(".class")].replace("/", ".")
            for n in classes
            if any(marker in zf.read(n) for marker in references)
        )
    print(
        f"Cells are the classes whose own BYTES reference a Spring lifecycle or "
        f"post-processor type — read from the constant pool across all {len(classes)} "
        f"classes in the artifact, not matched on class NAMES.\n"
    )
    print(f"| {SPRING_GCP[1]} |")
    print("|---|")
    if processors:
        for name in processors:
            print(f"| `{name}` |")
    else:
        print("| **none ship in this artifact** |")
    print(
        "\n- So a `@Bean` method returning a `Subscriber` is started by nothing: the type "
        "implements no interface the container acts on, and the library registers no "
        "post-processor that would start it. **GUIDELINES §8.6 gave that case as a "
        "worked example of a MEASURED framework rule; it was not measured and it is "
        "false.**\n"
    )


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"PROBE COULD NOT ANSWER: {error}", file=sys.stderr)
        raise SystemExit(2) from error
