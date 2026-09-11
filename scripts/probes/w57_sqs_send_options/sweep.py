"""W57 — what does `SqsSendOptions` declare, and at which versions? (`OI-74`)

`spring-sqs-template.yml`'s builder row reads a destination and a payload from
INSIDE `sqsTemplate.send(to -> to.queue(…).payload(…))`, by naming the builder
methods called in the lambda body. Those names are the whole rule: a name the
interface does not declare reads nothing, and a name it declares on a DIFFERENT
member than the catalog assumes reads the wrong argument.

The catalog also states how many of the interface's methods take a `String`,
because that is the size of the fabrication the owner and name conjuncts prevent:
a reader taking the first literal in the body would publish whichever of those
happened to come first.

**Version scope (§5.4).** Read against **spring-cloud-aws-sqs 3.1.1 and 4.1.1**.
An interface's member list is API surface and moves between major versions; these
are the two this catalog's `measured:` block records.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

ARTIFACTS = (
    "io.awspring.cloud:spring-cloud-aws-sqs:3.1.1",
    "io.awspring.cloud:spring-cloud-aws-sqs:4.1.1",
)
OPTIONS = "io/awspring/cloud/sqs/operations/SqsSendOptions"

# The two the catalog reads, and the positions it reads them at.
CLAIMED = {"queue": 0, "payload": 0}


class ProbeError(RuntimeError):
    """Anything that would otherwise put an unmeasured cell in a table."""


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
            raise ProbeError(f"{jar.name} does not carry {internal}") from missing
        completed = subprocess.run(
            ["javap", *flags, str(Path(into) / f"{internal}.class")],
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise ProbeError(f"javap failed on {internal}: {completed.stderr.strip()}")
    return completed.stdout


def members(jar: Path) -> list[str]:
    """Every method the interface declares, as `name(args)`."""
    body = _javap(jar, OPTIONS, "-p")
    found = []
    # `name(args)` off the END of the declaration, by regex. Splitting on spaces —
    # which the first version of this did — mangles every multi-argument member:
    # `header(java.lang.String, java.lang.Object)` came out as `java.lang.Object)`
    # and the table printed two rows that are not methods. A signature contains
    # spaces by construction.
    signature = re.compile(r"\b(\w+)\((.*)\);\s*$")
    for line in body.splitlines():
        match = signature.search(line)
        if match is None:
            continue
        found.append(f"{match.group(1)}({match.group(2)})")
    if not found:
        raise ProbeError(
            f"{OPTIONS} declares no methods in {jar.name} — the class or the javap output "
            f"shape moved, and an empty table here would read as 'the builder declares "
            f"nothing'"
        )
    return sorted(found)


def main() -> None:
    read = {artifact.split(":")[2]: checked(artifact) for artifact in ARTIFACTS}
    versions = sorted(read)

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w57_sqs_send_options/run.sh`, which runs")
    print("`sweep.py`. **Every version in the headers below is the one the JAR itself")
    print("reported** — out of its own `pom.properties` or its manifest's")
    print("`Implementation-Version`, and")
    print("**not the version the coordinate list asked for**; `checked` compares the two")
    print("and ABORTS when they disagree, rather than printing a version it did not read.\n")
    print("| what the run read | " + " | ".join(versions) + " |")
    print("|---|" + "---|" * len(versions))
    print(
        "| artifact reporting this version | "
        + " | ".join(["spring-cloud-aws-sqs"] * len(versions))
        + " |"
    )
    print(
        "| where the jar states that version | " + " | ".join(read[v][2] for v in versions) + " |\n"
    )

    declared = {version: members(read[version][0]) for version in versions}
    print("### Every method `SqsSendOptions` declares\n")
    print("| method | " + " | ".join(versions) + " | read by the catalog |")
    print("|---|" + "---|" * (len(versions) + 1))
    every = sorted({name for names in declared.values() for name in names})
    for name in every:
        cells = ["yes" if name in declared[v] else "**no**" for v in versions]
        bare = name.split("(")[0]
        role = f"**yes, at arg{CLAIMED[bare]}**" if bare in CLAIMED else "no"
        print(f"| `{name}` | " + " | ".join(cells) + f" | {role} |")
    print()
    missing = sorted(set(CLAIMED) - {name.split("(")[0] for name in every})
    print(f"**Read by the catalog and NOT declared at both versions:** {missing or 'none'}.")

    # A `String` at a TOP-LEVEL parameter position, which is the number the prose
    # elsewhere quotes and the one that matters: it is how many members a reader
    # taking "the first string literal in the body" could mistake for the queue.
    # Generic arguments are stripped first — `headers(Map<String, Object>)` names
    # `String` and takes a Map, and counting it would inflate the figure the guard
    # cites. Measured rather than asserted, because the first prose to quote this
    # said four without a definition and three different definitions give 3, 4
    # and 5.
    def direct_strings(signature: str) -> bool:
        arguments = signature.split("(", 1)[1].rstrip(")")
        depth = 0
        flat = []
        for character in arguments:
            depth += (character == "<") - (character == ">")
            if depth == 0 and character != ">":
                flat.append(character)
        return "java.lang.String" in "".join(flat)

    takes = sorted(name for name in every if direct_strings(name))
    print(
        f"**Members taking a `String` at a top-level parameter position:** "
        f"{len(takes)} — {', '.join(takes)}."
    )


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
