"""W16 — what tells a Spring RSocket controller from a STOMP one (F2 §3.6)?

`spring-stomp.yml` claims `@MessageMapping` and publishes what it finds as
`websocket`. That annotation is also THE routing annotation for Spring RSocket
controllers, so an RSocket handler is published on the wrong PROTOCOL — and
`docs/COVERAGE.md` has stated the boundary in place ever since, with the reason it
stayed open: "separating them needs a fact that tells an RSocket registration from a
STOMP one, and neither catalog reads one."

Three questions:

1. **Does the class itself distinguish them?** Both frameworks decide which beans to
   scan with a predicate. If the two predicates are the same, no fact on the class
   can separate them and the catalog gate must come from somewhere else.
2. **Does either annotation belong to one framework only?** `@ConnectMapping` is
   RSocket's connection-setup annotation and has no STOMP counterpart; whether it is
   a usable positive marker is a question about where it may be written.
3. **What DOES separate them?** Spring Boot decides which handler bean exists by
   auto-configuration, and each auto-configuration is `@ConditionalOnClass`. That
   condition names types, and a type belongs to an artifact — a dependency fact,
   which is what `detect.coordinates` already reads.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

# `coordinate`, and the classes read out of it.
MESSAGING = "org.springframework:spring-messaging:6.1.6"
AUTOCONFIGURE = "org.springframework.boot:spring-boot-autoconfigure:3.2.5"

STOMP_HANDLER = (
    "org/springframework/messaging/simp/annotation/support/SimpAnnotationMethodMessageHandler"
)
RSOCKET_BASE = (
    "org/springframework/messaging/handler/annotation/reactive/MessageMappingMessageHandler"
)
RSOCKET_HANDLER = "org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler"
CONNECT_MAPPING = "org/springframework/messaging/rsocket/annotation/ConnectMapping"
MESSAGE_MAPPING = "org/springframework/messaging/handler/annotation/MessageMapping"
RSOCKET_AUTOCONFIG = (
    "org/springframework/boot/autoconfigure/rsocket/RSocketMessagingAutoConfiguration"
)
STOMP_AUTOCONFIG = (
    "org/springframework/boot/autoconfigure/websocket/servlet/WebSocketMessagingAutoConfiguration"
)


class ProbeError(RuntimeError):
    """Something the run could not establish. ABORTS rather than warning."""


def resolve(artifact: str) -> Path:
    group, name, version = artifact.split(":")
    jar = M2 / Path(group.replace(".", "/")) / name / version / f"{name}-{version}.jar"
    if not jar.is_file():
        subprocess.run(
            ["mvn", "-q", "-B", "dependency:get", "-Dtransitive=false", f"-Dartifact={artifact}"],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
    if not jar.is_file():
        raise ProbeError(f"{artifact} did not resolve; fix the coordinate in run.sh")
    return jar


def self_reported_version(jar: Path) -> tuple[str, str]:
    """The version the ARCHIVE states for itself, and where. Raises rather than
    defaulting: a missing self-report is where a hand-written column would go
    unchallenged (CP-5)."""
    with zipfile.ZipFile(jar) as archive:
        entries = [
            name
            for name in archive.namelist()
            if name.startswith("META-INF/maven/") and name.endswith("/pom.properties")
        ]
        if entries:
            for line in archive.read(entries[0]).decode("utf-8", "replace").splitlines():
                if line.strip().startswith("version="):
                    return line.split("=", 1)[1].strip(), "pom.properties"
        try:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError as missing:
            raise ProbeError(f"{jar.name} reports no version of its own") from missing
    for line in manifest.splitlines():
        if line.lower().startswith("implementation-version:"):
            return line.split(":", 1)[1].strip(), "MANIFEST.MF"
    raise ProbeError(f"{jar.name} states no version in its pom.properties or its manifest")


def checked(artifact: str) -> tuple[Path, str, str]:
    jar = resolve(artifact)
    reported, source = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own {source} while the coordinate asked "
            f"for {requested!r}. Fix run.sh rather than labelling a column with a version this "
            f"run did not read."
        )
    return jar, reported, source


def _javap(jar: Path, internal: str, *flags: str) -> str:
    """`javap` output for one class. ABORTS when the jar does not carry it: an
    empty string reaches these tables as the probe's own conclusions."""
    with tempfile.TemporaryDirectory() as into:
        try:
            with zipfile.ZipFile(jar) as archive:
                archive.extract(f"{internal}.class", into)
        except KeyError as missing:
            raise ProbeError(
                f"{jar.name} does not carry {internal}.class. Fix the class name or the "
                f"coordinate rather than reading its absence as an answer."
            ) from missing
        return subprocess.run(
            ["javap", *flags, "-p", str(Path(into) / f"{internal}.class")],
            capture_output=True,
            text=True,
            check=False,
        ).stdout


def scanned_predicate(jar: Path, internal: str) -> str:
    """The annotation a handler's bean predicate tests, read from the bytecode of
    whichever method carries it.

    Verbatim-ish rather than paraphrased: what is reported is the `ldc` operand,
    which IS the class the predicate asks about. STOMP overrides `isHandler`;
    RSocket's chain sets a `Predicate` field whose default is a lambda in the
    reactive base — different mechanisms, so the method name is reported too."""
    listed = _javap(jar, internal, "-c")
    for method in ("isHandler", "lambda$new$0"):
        body = re.search(
            rf"\b{re.escape(method)}\(.*?\n(.*?)(?=\n\s*(?:public|protected|private|\}}))",
            listed,
            re.DOTALL,
        )
        if body is None:
            continue
        named = re.search(r"ldc\w*\s+#\d+\s+// class ([\w/$]+)", body.group(1))
        if named is not None:
            return f"`{method}` tests `{named.group(1).rsplit('/', 1)[-1]}`"
    return "no bean predicate found in this class"


def targets(jar: Path, internal: str) -> str:
    listed = _javap(jar, internal, "-v")
    found = re.search(r"java\.lang\.annotation\.Target\(\s*value=\[([^\]]*)\]", listed)
    if found is None:
        return "—"
    return ", ".join(
        part.strip().rsplit(".", 1)[-1] for part in found.group(1).split(",") if part.strip()
    )


def conditional_classes(jar: Path, internal: str) -> list[str]:
    """The types an auto-configuration's `@ConditionalOnClass` names — the
    condition that decides whether its handler bean exists at all."""
    listed = _javap(jar, internal, "-v")
    block = re.search(r"ConditionalOnClass[^\n]*\n(.*?)(?=\n\s{0,2}\w|\Z)", listed, re.DOTALL)
    region = block.group(1) if block else listed
    return sorted(
        {
            name.replace("/", ".")
            for name in re.findall(r"L([\w/$]+);", region)
            if "/" in name and "annotation/condition" not in name and "java/lang" not in name
        }
    )


def main() -> None:
    print("## Observations\n")
    print(
        "Verbatim from `scripts/probes/w16_rsocket_versus_stomp/run.sh`, which runs "
        "`sweep.py`. **Every version below is the one the JAR itself reported** — and "
        "**not the version the coordinate list asked for**; `sweep.py` compares the two "
        "and ABORTS when they disagree, rather than printing a version it did not read.\n"
    )
    messaging, messaging_version, messaging_source = checked(MESSAGING)
    boot, boot_version, boot_source = checked(AUTOCONFIGURE)

    print(f"| what the run read | {messaging_version} | {boot_version} |")
    print("|---|---|---|")
    print("| artifact reporting this version | spring-messaging | spring-boot-autoconfigure |")
    print(f"| where the jar states that version | {messaging_source} | {boot_source} |")
    print()

    print("### 1. Does the CLASS distinguish an RSocket controller from a STOMP one?\n")
    print("| handler | the bean predicate it scans with |")
    print("|---|---|")
    for label, internal in (
        ("STOMP — `SimpAnnotationMethodMessageHandler`", STOMP_HANDLER),
        ("RSocket — `MessageMappingMessageHandler` (its base)", RSOCKET_BASE),
    ):
        print(f"| {label} | {scanned_predicate(messaging, internal)} |")
    print()

    print("### 2. Where each annotation may be written\n")
    print("| annotation | `@Target` | framework |")
    print("|---|---|---|")
    for label, internal, framework in (
        ("`@MessageMapping`", MESSAGE_MAPPING, "both"),
        ("`@ConnectMapping`", CONNECT_MAPPING, "RSocket only"),
    ):
        print(f"| {label} | {targets(messaging, internal)} | {framework} |")
    print()

    print("### 3. What decides which handler bean EXISTS\n")
    print("| auto-configuration | `@ConditionalOnClass` names |")
    print("|---|---|")
    for label, internal in (
        ("RSocket — `RSocketMessagingAutoConfiguration`", RSOCKET_AUTOCONFIG),
        ("STOMP — `WebSocketMessagingAutoConfiguration`", STOMP_AUTOCONFIG),
    ):
        named = conditional_classes(boot, internal)
        print(f"| {label} | {', '.join(f'`{n}`' for n in named) or '—'} |")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"W16 ABORTED: {error}", file=sys.stderr)
        raise SystemExit(1) from error
