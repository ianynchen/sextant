"""CP-14's measurement half: the value a `@Scheduled` declaration uses to say
*never*, read off Spring's own bytecode.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. Like CP-7 and CP-13 it reads each jar's own identity out of its own
bytes before it measures anything and refuses to file a cell under a version the
artifact did not claim (GUIDELINES §5.4, and CP-5's failure it exists to
prevent).

Every question answers PER RESOLVED ARTIFACT rather than once, so a rule read
against three Spring minors prints three rows and §5.4's scope is the rows
themselves rather than a sentence about them.

Everything it prints is the table `cp14_schedule_sentinel.md` carries verbatim.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

# The manifest's own `Name: value`.
_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
# One `javap -c` instruction line: ordinal, mnemonic, then whatever operands and
# trailing `// comment` follow. Operands are matched loosely for CP-11's reason —
# `invokeinterface #25,  2` carries two, and a pattern assuming one silently ENDS
# the body at the first such instruction.
_INSTRUCTION = re.compile(r"^\s*\d+:\s+(\S+)(.*)$")
# A `javap` method declaration: two-space indented, ending in a parameter list.
_METHOD_LINE = re.compile(r"^\s{2}\S.*\(")
# `javap -constants`' rendering of one compile-time constant field.
_CONSTANT = re.compile(r"^\s{2}public static final (\S+) (\w+) = (.+);\s*$")
# One declared annotation attribute.
_ATTRIBUTE = re.compile(r"^\s{2}public abstract (\S+) ([\w$]+)\(\);\s*$")
# `javap`'s comment for a loaded string constant, which is where the SENTINEL
# VALUE itself lives. `javap` escapes a quote and a backslash inside the
# literal and prints the rest raw, so the value is whatever follows the marker.
_STRING_CONSTANT = re.compile(r"^String (.*)$")

# Markdown tables are `|`-delimited, so an instruction sequence is joined with
# something else: a `|` inside a cell silently splits the row, and a table
# nobody can read back is a table nobody re-checks.
_STEP = " ; "

_SCHEDULED = "org.springframework.scheduling.annotation.Scheduled"
_POST_PROCESSOR = "org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor"
_STRING_EQUALS = "Method java/lang/String.equals:(Ljava/lang/Object;)Z"

# What a cell of question 2 keeps out of a method body several hundred
# instructions long. The three are the whole rule: which attributes of the
# annotation are read, what the read value is compared against, and which
# registration call the comparison stands in front of. Anything else — the
# `Assert` messages, the placeholder resolution, the `Duration` arithmetic —
# is the framework doing something other than deciding whether this
# declaration schedules anything.
_RELEVANT = (
    "InterfaceMethod org/springframework/scheduling/annotation/Scheduled.",
    "Method org/springframework/scheduling/config/ScheduledTaskRegistrar.schedule",
    _STRING_EQUALS,
)


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    """One resolved jar, and the identity it reported for itself."""

    __slots__ = ("jar", "name", "observed", "requested")

    def __init__(self, name: str, requested: str, jar: Path, entry: str, key: str) -> None:
        self.name = name
        self.requested = requested
        self.jar = jar
        self.observed = _identity(jar, entry, key)
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was resolved as "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )


def _identity(jar: Path, entry: str, key: str) -> str:
    """The version this ARCHIVE claims for itself, read out of its own bytes."""
    with zipfile.ZipFile(jar) as archive:
        names = [name for name in archive.namelist() if name == entry or name.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}` — it reports no version of its own")
        text = archive.read(names[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    raise ProbeError(f"{jar.name}'s `{entry}` declares no `{key}`")


def _javap(*arguments: str, classpath: Path) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _step(line: str) -> str | None:
    """One instruction as `mnemonic <constant-pool comment>`, or None where the
    line is not an instruction at all.

    The comment is what makes a sequence both legible and checkable: `ldc`
    alone says nothing, `ldc String -` is the sentinel.
    """
    match = _INSTRUCTION.match(line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _equality_sites(output: str) -> list[int]:
    """Every line index at which this disassembly compares two strings.

    The whole class, not one method: which method holds the sentinel test is
    not a stable fact — CP-7 learned that when a rule moved between a private
    helper and its caller across two minors — and keying on a method name
    would have printed an empty cell and read as "the rule is gone".
    """
    lines = output.splitlines()
    return [index for index, line in enumerate(lines) if _STRING_EQUALS in (_step(line) or "")]


def _enclosing_method(output: str, index: int) -> str:
    """The declaration `javap` printed for the method the instruction at
    `index` sits in."""
    lines = output.splitlines()
    found = next(
        (lines[i].strip() for i in range(index, -1, -1) if _METHOD_LINE.match(lines[i])), None
    )
    if found is None:
        raise ProbeError("the comparison sits inside no method javap declared")
    return found


def _constant_compared(output: str, index: int) -> str:
    """The string constant loaded for the comparison at `index`.

    Searched BACKWARDS from the comparison rather than taken at a fixed offset:
    javac puts the receiver and the argument on the stack in whichever order
    the source wrote them, so the `ldc` is two instructions back here and could
    be one or three elsewhere. The search stops at the start of the method, so
    a comparison whose operands are both computed yields no constant rather
    than borrowing the previous method's.
    """
    lines = output.splitlines()
    for i in range(index - 1, -1, -1):
        if _METHOD_LINE.match(lines[i]):
            break
        step = _step(lines[i]) or ""
        if not step.startswith("ldc"):
            continue
        literal = _STRING_CONSTANT.match(step.split(" ", 1)[1] if " " in step else "")
        if literal:
            return literal.group(1)
    raise ProbeError("the string comparison loads no string constant of its own")


def _named(artifacts: list[Artifact], name: str) -> list[Artifact]:
    found = [artifact for artifact in artifacts if artifact.name == name]
    if not found:
        raise ProbeError(f"no resolved artifact named {name}")
    return found


def q1_the_annotation_declares_the_sentinel(
    artifacts: list[Artifact],
) -> list[tuple[str, str, str]]:
    """Q1. What `@Scheduled` declares: its compile-time constants, then its
    attributes.

    The constants are the half `OI-2` needs. A framework that names its own
    disable value in the annotation's public API is stating a fact about the
    declaration, not about a deployment — which is exactly what makes it
    encodable (§8.2's line: a deployment can overwrite a property, and cannot
    overwrite a constant compiled into the caller).

    The attribute list rides along because the same reading answers the OTHER
    half of `spring-scheduling.yml`'s `triggers` block — which attributes exist
    at all — and a `triggers` alias set is only as trustworthy as the
    enumeration it was chosen from.
    """
    rows = []
    for artifact in _named(artifacts, "spring-context"):
        output = _javap("-p", "-s", "-constants", _SCHEDULED, classpath=artifact.jar)
        constants = [
            f"{match.group(2)} = {match.group(3)}"
            for match in map(_CONSTANT.match, output.splitlines())
            if match
        ]
        attributes = [
            f"{match.group(2)}()" for match in map(_ATTRIBUTE.match, output.splitlines()) if match
        ]
        if not constants:
            raise ProbeError(f"{_SCHEDULED} declares no constant at {artifact.observed}")
        rows.append(
            (
                artifact.name,
                artifact.observed,
                _STEP.join([*constants, *attributes]),
            )
        )
    return rows


def q2_what_the_sentinel_withdraws(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q2. The attribute the sentinel is compared against, and what the
    comparison stands in front of.

    A constant named `CRON_DISABLED` is a name, not a behaviour. What decides
    whether `spring-scheduling.yml` may drop the row is what the post-processor
    DOES with the match — so the cell is the enclosing method's declaration
    followed by every `Scheduled` attribute read, the comparison itself, and
    every `ScheduledTaskRegistrar.schedule*` call, in bytecode order. A reader
    can then see which registration the comparison sits before, and which
    registrations it does not reach.
    """
    rows = []
    for artifact in _named(artifacts, "spring-context"):
        output = _javap("-p", "-c", _POST_PROCESSOR, classpath=artifact.jar)
        sites = _equality_sites(output)
        if len(sites) != 1:
            raise ProbeError(
                f"{_POST_PROCESSOR} compares strings at {len(sites)} sites at "
                f"{artifact.observed}; this question assumes the sentinel test is the only "
                "one and must be re-read rather than answered"
            )
        lines = output.splitlines()
        declaration = _enclosing_method(output, sites[0])
        start = next(i for i in range(sites[0], -1, -1) if lines[i].strip() == declaration.strip())
        body = [
            step
            for line in lines[start:]
            if (step := _step(line)) is not None and any(marker in step for marker in _RELEVANT)
        ]
        rows.append((artifact.name, artifact.observed, _STEP.join([declaration, *body])))
    return rows


def q3_the_sentinel_is_the_only_one(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q3. The converse, which CP-10's table is criticised for never asking:
    is `-` the only value this post-processor reads as an absence, or does a
    fixed rate or a fixed delay have a sentinel of its own?

    Answered by enumerating every string comparison in the class and printing
    the constant each one loads. One row, one constant, is the answer that
    bounds `spring-scheduling.yml`'s new key to `cron` — and a second constant
    appearing at a later minor turns this cell into the finding rather than
    leaving it to a reader's memory.
    """
    rows = []
    for artifact in _named(artifacts, "spring-context"):
        output = _javap("-p", "-c", _POST_PROCESSOR, classpath=artifact.jar)
        constants = [
            f"{_enclosing_method(output, site).split('(')[0].split()[-1]} compares "
            f'"{_constant_compared(output, site)}"'
            for site in _equality_sites(output)
        ]
        rows.append((artifact.name, artifact.observed, _STEP.join(constants)))
    return rows


def q4_what_the_sentinel_does_not_withdraw(
    artifacts: list[Artifact],
) -> list[tuple[str, str, str]]:
    """Q4. Whether reaching the sentinel still counts as having declared a
    schedule — the half that decides what a DISABLED cron beside a live
    `fixedDelay` does.

    Q2 shows the comparison stands in front of `scheduleCronTask` alone. It
    does not show whether the framework has already recorded that this
    declaration carried a schedule, and that flag is what the
    "Exactly one of ..." assertion later reads. So the cell is every
    instruction between the `cron()` read and the comparison, UNFILTERED: if
    the flag is written before the comparison, a declaration writing both a
    disabled cron and a live rate is one the container refuses to start, and
    dropping only the cron row would publish scheduled work for an application
    that never runs.
    """
    rows = []
    for artifact in _named(artifacts, "spring-context"):
        output = _javap("-p", "-c", _POST_PROCESSOR, classpath=artifact.jar)
        lines = output.splitlines()
        site = _equality_sites(output)[0]
        start = next(
            (
                index
                for index in range(site, -1, -1)
                if "Scheduled.cron:()Ljava/lang/String;" in (_step(lines[index]) or "")
            ),
            None,
        )
        if start is None:
            raise ProbeError("the sentinel comparison follows no `cron()` read")
        body = [step for line in lines[start : site + 1] if (step := _step(line)) is not None]
        rows.append((artifact.name, artifact.observed, _STEP.join(body)))
    return rows


def q5_what_reads_the_flag(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q5. What the flag Q4 found written is later read BY.

    Q4 shows the flag is set before the sentinel test; on its own that is an
    `istore` with no consequence. This prints every instruction from the
    comparison to the first `Assert.isTrue` after it, which is where the flag
    is read back — so the cell says, in the framework's own instructions,
    what happens to a declaration that writes a disabled cron beside a live
    rate. Without it the consequence would be the reader's inference, which is
    §5.4's own failure mode.
    """
    rows = []
    for artifact in _named(artifacts, "spring-context"):
        output = _javap("-p", "-c", _POST_PROCESSOR, classpath=artifact.jar)
        lines = output.splitlines()
        site = _equality_sites(output)[0]
        end = next(
            (
                index
                for index in range(site, len(lines))
                if "Method org/springframework/util/Assert.isTrue" in (_step(lines[index]) or "")
            ),
            None,
        )
        if end is None:
            raise ProbeError("no assertion follows the sentinel comparison")
        body = [step for line in lines[site : end + 1] if (step := _step(line)) is not None]
        rows.append((artifact.name, artifact.observed, _STEP.join(body)))
    return rows


_QUESTIONS: list[tuple[str, str, Callable[[list[Artifact]], list[tuple[str, str, str]]]]] = [
    (
        "1",
        "`@Scheduled`'s own constants, then its attributes",
        q1_the_annotation_declares_the_sentinel,
    ),
    (
        "2",
        "the sentinel comparison, the attributes read and the registrations around it",
        q2_what_the_sentinel_withdraws,
    ),
    ("3", "every string comparison in the post-processor", q3_the_sentinel_is_the_only_one),
    (
        "4",
        "every instruction between the `cron()` read and the comparison",
        q4_what_the_sentinel_does_not_withdraw,
    ),
    (
        "5",
        "from the comparison to the first assertion that follows it",
        q5_what_reads_the_flag,
    ),
]


def main(specs: list[str]) -> int:
    artifacts = []
    for spec in specs:
        _, name, version, entry, key, jar = spec.split("|")
        artifacts.append(Artifact(name, version, Path(jar), entry, key))

    columns = sorted({artifact.observed for artifact in artifacts})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(sorted(a.name for a in artifacts if a.observed == version))
            for version in columns
        )
        + " |"
    )
    print("| identity read from the archive itself | " + " | ".join(["yes"] * len(columns)) + " |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")
    for number, question, answer in _QUESTIONS:
        rows = answer(artifacts)
        for index, (where, version, observed) in enumerate(rows):
            suffix = "" if len(rows) == 1 else chr(ord("a") + index)
            print(f"| {number}{suffix} | {question} | `{where}` | {version} | `{observed}` |")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-14 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
