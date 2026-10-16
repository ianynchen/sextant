"""CP-34 — `org.apache.kafka.clients.producer.ProducerRecord`'s constructors, and
which argument of each one is the VALUE.

Three shipped catalogs (`kafka-clients.yml`, `spring-kafka-template.yml`,
`spring-kafka-replying.yml`) declare `record_wrappers: [{type: ProducerRecord,
channel_ctor_arg: 0, payload_ctor_arg: last}]`, and `single_call._record_arguments`
resolves `last` to the linked constructor's own final argument. A test docstring in this
repository asserted that the rule "holds across every `ProducerRecord` overload (design
doc)" — a belief with nothing measured behind it. This probe measures it.

The question is mechanical: of every constructor `ProducerRecord` declares, which
parameter carries the value the record is built around, and is it the last one?

**Version scope (§5.4).** Read against **kafka-clients 3.6.2** — the version the jar
reports for itself out of its own `kafka/kafka-version.properties`, the entry its own
`AppInfoParser` reads at runtime, checked against the coordinate before any table is
printed and ABORTED on if the two disagree. kafka-clients writes nothing into its manifest
and ships no `pom.properties`, which is why that entry and not the usual two. That is the
version `kafka-clients.yml`'s own `measured:` block already cites, and the one
`fixtures/orders-service/pom.xml` resolves. A kafka-clients release before or after 3.6.2
is unverified here: a constructor added or removed changes the overload set this verdict is
about, which is the whole point of bounding it.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

ARTIFACT = "org.apache.kafka:kafka-clients:3.6.2"
INTERNAL = "org/apache/kafka/clients/producer/ProducerRecord"

# The field the value ends up in. Named here because the bytecode evidence below is a
# `putfield` of exactly this member, and the generic reading is checked against it.
VALUE_FIELD = "value:Ljava/lang/Object;"


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


# Where THIS artifact states its own version. kafka-clients writes nothing into its
# manifest — `META-INF/MANIFEST.MF` is the two-line default — and no `pom.properties`
# either; it ships `kafka/kafka-version.properties`, which is the file its own
# `AppInfoParser` reads to report the client version at runtime. `cp12_sweep_round1b`
# already reads this artifact through exactly that entry, and this probe follows it
# rather than inventing a second route to the same number.
VERSION_ENTRY = "kafka/kafka-version.properties"
VERSION_KEY = "version"


def self_reported_version(jar: Path) -> tuple[str, str]:
    """The version this ARCHIVE claims for itself (§5.4), read out of its own bytes."""
    with zipfile.ZipFile(jar) as archive:
        if VERSION_ENTRY not in archive.namelist():
            raise ProbeError(f"{jar.name} carries no `{VERSION_ENTRY}` — it reports no version")
        text = archive.read(VERSION_ENTRY).decode("utf-8", "replace")
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == VERSION_KEY:
            return value.strip(), VERSION_ENTRY
    raise ProbeError(f"{jar.name}'s `{VERSION_ENTRY}` declares no `{VERSION_KEY}`")


def checked(artifact: str) -> tuple[Path, str, str]:
    jar = resolve(artifact)
    reported, source = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own {source} while the coordinate asked "
            f"for {requested!r}."
        )
    return jar, reported, source


def _javap(jar: Path, internal: str, *flags: str) -> str:
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


def _split_parameters(declared: str) -> list[str]:
    """One declared parameter per slot, from javap's own human-readable list — split on
    the commas at depth zero, because a parameter may carry its own generic arguments
    (`java.lang.Iterable<org.apache.kafka.common.header.Header>` is ONE slot)."""
    parameters, depth, current = [], 0, ""
    for character in declared:
        if character == "<":
            depth += 1
        elif character == ">":
            depth -= 1
        if character == "," and depth == 0:
            parameters.append(current.strip())
            current = ""
        else:
            current += character
    if current.strip():
        parameters.append(current.strip())
    return parameters


def value_variable(text: str) -> str:
    """The name of the class's VALUE type variable, read off its own declaration line
    rather than assumed — `public class ...ProducerRecord<K, V> {` gives `V`.

    The last variable, because the accessor that names the record's payload is `V value()`
    and the class declares its variables key-then-value. Read mechanically so a class
    that renamed them is followed rather than mismatched in silence."""
    match = re.search(r"class\s+\S*ProducerRecord<([^>]*)>", text)
    if not match:
        raise ProbeError("ProducerRecord's declaration states no type variables")
    variables = [name.strip() for name in match.group(1).split(",")]
    if len(variables) != 2:
        raise ProbeError(f"expected two type variables, read {variables}")
    return variables[1]


def constructors(jar: Path, internal: str) -> list[tuple[str, str]]:
    """`(declared parameter list, erased descriptor)` for every constructor, from
    `javap -p -s`'s own output: a signature line, then its `descriptor:` line below."""
    text = _javap(jar, internal, "-p", "-s")
    simple = internal.rsplit("/", 1)[1]
    # javap prints the constructor's own name fully qualified, so the character before it
    # is the package dot rather than a space.
    pattern = re.compile(rf"[\s.]{re.escape(simple)}\((.*?)\);\n\s+descriptor: (\S+)")
    found = re.findall(pattern, text)
    if not found:
        raise ProbeError(f"javap printed no constructor for {internal}")
    return found


def bodies(jar: Path, internal: str) -> str:
    return _javap(jar, internal, "-c", "-p")


def value_assignment(code: str) -> str:
    """The one line that stores into the value field, with the load that feeds it —
    the bytecode half of the reading, printed so the generic half is checkable."""
    lines = code.splitlines()
    for index, line in enumerate(lines):
        if "putfield" in line and VALUE_FIELD in line:
            return " ; ".join(part.strip() for part in lines[max(0, index - 1) : index + 1])
    raise ProbeError(f"no `putfield {VALUE_FIELD}` anywhere in the class")


def delegations(code: str) -> list[str]:
    """Each constructor's own body, one line, for the five that delegate rather than
    assign: the argument ORDER they pass on is what says which of their own parameters
    becomes the value."""
    blocks = re.split(r"\n(?=  public |  protected |  private )", code)
    found = []
    for block in blocks:
        head = block.splitlines()[0].strip()
        if "ProducerRecord(" not in head or "Code:" not in block:
            continue
        instructions = [
            line.strip()
            for line in block.splitlines()
            if re.match(r"\s+\d+: (aload(_\d)?|aconst_null|putfield|invokespecial)\b", line)
        ]
        found.append(f"{head} --- " + " ; ".join(instructions))
    return found


def main() -> None:
    jar, reported, source = checked(ARTIFACT)
    declaration = _javap(jar, INTERNAL, "-p")
    variable = value_variable(declaration)
    code = bodies(jar, INTERNAL)

    print("## Observations\n")
    print("Verbatim from `scripts/probes/cp34_producer_record_ctors/run.sh`, which runs")
    # Kept on one line each where §5.4's two required sentences are: the architecture
    # rule reads them as literal spellings, and a line break inside "not the version"
    # would fail a probe for stating exactly what the rule asks it to state.
    print("`sweep.py`. **The version in the header below is the one the JAR itself")
    print("reported** — out of its own `kafka/kafka-version.properties` —")
    print("and **not the version the coordinate asked for**;")
    print("`checked` compares the two and ABORTS when they disagree.\n")
    print(f"| what the run read | {reported} |")
    print("|---|---|")
    print(f"| artifacts reporting this version | {ARTIFACT.rsplit(':', 1)[0]} |")
    print(f"| where the jar states it | {source} |")
    print(f"| value type variable, read off the class declaration | `{variable}` |")
    print()
    print("### Every constructor, and where the value sits\n")
    print(
        "| # | declared parameters | erased descriptor | value slot | last slot | "
        "`last` is the value? |"
    )
    print("|---|---|---|---|---|---|")
    rows = []
    for index, (declared, descriptor) in enumerate(constructors(jar, INTERNAL), 1):
        parameters = _split_parameters(declared)
        slots = [position for position, name in enumerate(parameters) if name == variable]
        if len(slots) != 1:
            raise ProbeError(f"{declared}: {len(slots)} parameters declared `{variable}`")
        value_slot, last_slot = slots[0], len(parameters) - 1
        agrees = "yes" if value_slot == last_slot else "**NO**"
        rows.append((descriptor, value_slot, last_slot, value_slot == last_slot))
        print(
            f"| {index} | `{', '.join(parameters)}` | `{descriptor}` | {value_slot} | "
            f"{last_slot} | {agrees} |"
        )
    print()
    wrong = [row for row in rows if not row[3]]
    print(
        f"**{len(rows)} constructors; `last` is the value on {len(rows) - len(wrong)} and is "
        f"NOT on {len(wrong)}.**\n"
    )
    for descriptor, value_slot, last_slot, _ in wrong:
        print(f"* `{descriptor}` — value at {value_slot}, `last` reads {last_slot}")
    print()
    print("### The bytecode the generic reading is checked against\n")
    print(
        "One constructor assigns the field; the other five delegate to it, and the order "
        "they pass their own locals in is what carries their value into its slot.\n"
    )
    print("```")
    print(value_assignment(code))
    print("```\n")
    print("```")
    for line in delegations(code):
        print(line)
    print("```")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as failure:
        print(f"probe aborted: {failure}", file=sys.stderr)
        raise SystemExit(1) from failure
