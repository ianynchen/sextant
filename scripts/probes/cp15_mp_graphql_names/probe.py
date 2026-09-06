"""CP-15's measurement half: the operation name MicroProfile GraphQL serves for
a method whose `@Query` or `@Mutation` names none.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. Like CP-7, CP-13 and CP-14 it reads each jar's own identity out of its
own bytes before it measures anything and refuses to file a cell under a version
the artifact did not claim (GUIDELINES §5.4, and CP-5's failure it exists to
prevent).

Every question answers PER RESOLVED ARTIFACT rather than once, so a rule read
against two SmallRye minors prints two rows and §5.4's scope is the rows
themselves rather than a sentence about them.

Question 5 is not an instruction sequence at all: `MethodHelper.getPropertyName`
is a public static method over a `Direction` and a `String`, needing no jandex
index and no deployment, so the probe COMPILES a driver against the resolved jar
and prints what the implementation returned. That is the answer `OI-5` asks for
— a name, not a reading of the code that computes one.

Everything it prints is the table `cp15_mp_graphql_names.md` carries verbatim.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
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
# `javap`'s comment for a loaded string constant.
_STRING_CONSTANT = re.compile(r"^String (.*)$")

# Markdown tables are `|`-delimited, so an instruction sequence is joined with
# something else: a `|` inside a cell silently splits the row, and a table
# nobody can read back is a table nobody re-checks.
_STEP = " ; "

_OPERATION_CREATOR = "io.smallrye.graphql.schema.creator.OperationCreator"
_ANNOTATIONS = "io.smallrye.graphql.schema.Annotations"
_METHOD_HELPER = "io.smallrye.graphql.schema.helper.MethodHelper"

# The `Annotations` fields question 2 resolves to the annotation types they
# name. Listed rather than discovered because the LIST is the finding — these
# are the five sources `getOperationName` consults, and a field appearing in
# that method and not here must fail loudly rather than be dropped from the
# cell.
_NAME_SOURCES = (
    "QUERY",
    "MUTATION",
    "NAME",
    "JAKARTA_JSONB_PROPERTY",
    "JAVAX_JSONB_PROPERTY",
    "JACKSON_PROPERTY",
)

# The method names question 5 puts through the implementation. Fixed here so
# the cell is a table rather than a sample: an accessor prefix on each side of
# the direction split (`getOrders`, `isActive`, `setStatus`), a name with no
# prefix at all (`orders`), the two names the strip's own length and
# capitalisation tests reject (`get`, `gettotal`), the one-letter case that
# passes them (`getX`), and an acronym (`getURL`) — because "strip the prefix
# and lowercase" and "strip the prefix and lowercase the FIRST CHARACTER" are
# different rules and only that name tells them apart.
_NAMES = (
    "getOrders",
    "isActive",
    "setStatus",
    "orders",
    "createOrder",
    "getX",
    "get",
    "gettotal",
    "getURL",
)

_DRIVER = """
import io.smallrye.graphql.schema.helper.Direction;
import io.smallrye.graphql.schema.helper.MethodHelper;

public class Driver {
    public static void main(String[] args) {
        StringBuilder out = new StringBuilder();
        for (String name : args) {
            if (out.length() > 0) {
                out.append(" ; ");
            }
            out.append(name)
               .append(" -> OUT ").append(MethodHelper.getPropertyName(Direction.OUT, name))
               .append(", IN ").append(MethodHelper.getPropertyName(Direction.IN, name));
        }
        System.out.println(out);
    }
}
"""


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

    The comment is what makes a sequence both legible and checkable: `getstatic`
    alone says nothing, `getstatic Field Annotations.NAME` is the rule.
    """
    match = _INSTRUCTION.match(line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _body(output: str, method: str) -> list[str]:
    """One method's instruction sequence, by the text of its declaration."""
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if re.search(rf"\b{method}\(", line)), None)
    if start is None:
        raise ProbeError(f"javap printed no `{method}` at all")
    body: list[str] = []
    for line in lines[start + 2 :]:
        step = _step(line)
        if step is None:
            break
        body.append(step)
    return body


def _named(artifacts: list[Artifact], name: str) -> list[Artifact]:
    found = [artifact for artifact in artifacts if artifact.name == name]
    if not found:
        raise ProbeError(f"no resolved artifact named {name}")
    return found


def q1_the_name_sources_in_order(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q1. Every source `getOperationName` consults for an operation's name, in
    the order it consults them.

    `microprofile-graphql.yml` reads ONE — the operation annotation's own
    `value` — through `path_from: [value]`. Whether that is the whole rule is
    this cell, and the answer decides whether an un-annotated operation is the
    only wrong address the catalog can publish.

    The array construction is kept whole rather than filtered to the
    `getstatic`s, because its `iconst_N` indices ARE the order, and
    `getOneOfTheseMethodAnnotationsValue` takes the first entry with a value.
    """
    rows = []
    for artifact in _named(artifacts, "smallrye-graphql-schema-builder"):
        output = _javap("-p", "-c", _OPERATION_CREATOR, classpath=artifact.jar)
        rows.append(
            (artifact.name, artifact.observed, _STEP.join(_body(output, "getOperationName")))
        )
    return rows


def q2_which_annotation_each_source_is(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q2. The annotation TYPE behind each field name question 1 printed.

    A cell naming `Annotations.NAME` is a field, and a catalog cannot be
    written against a field. These are the FQNs, read out of the class's own
    static initialiser — the `ldc` that precedes each `putstatic`.
    """
    rows = []
    for artifact in _named(artifacts, "smallrye-graphql-schema-builder"):
        output = _javap("-p", "-c", _ANNOTATIONS, classpath=artifact.jar)
        lines = output.splitlines()
        found = []
        for field in _NAME_SOURCES:
            marker = f"putstatic Field {field}:"
            index = next((i for i, line in enumerate(lines) if marker in (_step(line) or "")), None)
            if index is None:
                raise ProbeError(f"{_ANNOTATIONS} assigns no `{field}` at {artifact.observed}")
            found.append(f"{field} = {_string_before(lines, index)}")
        rows.append((artifact.name, artifact.observed, _STEP.join(found)))
    return rows


def _string_before(lines: list[str], index: int) -> str:
    """The string constant loaded immediately before `index`.

    Searched backwards rather than taken at a fixed offset: a `DotName` is built
    by `createSimple(String)`, and how many instructions sit between the `ldc`
    and the `putstatic` is a compiler detail. The search runs to the top of the
    disassembly, so a field assigned from something other than a literal yields
    the previous literal — which is why every value this returns is printed into
    the cell rather than compared to an expectation here.
    """
    for i in range(index - 1, -1, -1):
        step = _step(lines[i]) or ""
        if not step.startswith("ldc"):
            continue
        literal = _STRING_CONSTANT.match(step.split(" ", 1)[1] if " " in step else "")
        if literal:
            return literal.group(1)
    raise ProbeError("the field is assigned from no string constant")


def q3_the_fallback_and_its_direction(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q3. What the name is when no source in question 1 supplied one.

    This is the method `microprofile-graphql.yml`'s `path_fallback:
    construct_name` claims to mirror. The cell shows whether the method name is
    used as written, and — the half `OI-5` did not predict — whether the
    transformation applied depends on WHICH operation annotation matched.
    """
    rows = []
    for artifact in _named(artifacts, "smallrye-graphql-schema-builder"):
        output = _javap("-p", "-c", _OPERATION_CREATOR, classpath=artifact.jar)
        rows.append(
            (
                artifact.name,
                artifact.observed,
                _STEP.join(_body(output, "getDefaultExecutionTypeName")),
            )
        )
    return rows


def q4_the_transformation(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q4. The two transformations question 3 selects between.

    Read as instructions rather than trusted from question 5's output, because
    question 5 measures a sample of names and this measures the rule: a `length`
    test, a `startsWith` and a capitalisation test are what say WHICH names are
    stripped, and a table of nine could agree with several different rules.
    """
    rows = []
    for artifact in _named(artifacts, "smallrye-graphql-schema-builder"):
        output = _javap("-p", "-c", _METHOD_HELPER, classpath=artifact.jar)
        body = [
            *_body(output, "getPropertyName"),
            *_body(output, "toNameFromGetter"),
            *_body(output, "toNameFromSetter"),
            *_body(output, "removeAndLowerCase"),
        ]
        rows.append((artifact.name, artifact.observed, _STEP.join(body)))
    return rows


def q5_what_the_implementation_returns(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q5. The names the implementation actually returns, per direction.

    Not a reading. `MethodHelper.getPropertyName` is public, static, and takes
    a `Direction` and a `String` — no jandex index, no deployment — so the
    driver below is compiled against the resolved jar and RUN, and the cell is
    what it printed. `OI-5`'s close condition is a served name, and this is the
    nearest thing to one that needs no container: the exact function whose
    result question 3 shows becoming the operation name.

    **What it does not settle**: nothing was deployed, so this is the schema
    builder's answer rather than an observed GraphQL request. A server that
    post-processed the name would not be visible here, and question 3 is what
    says nothing does between this call and the `Operation`'s own name.
    """
    rows = []
    for artifact in _named(artifacts, "smallrye-graphql-schema-builder"):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "Driver.java").write_text(_DRIVER, encoding="utf-8")
            for tool, arguments in (
                ("javac", ["-cp", str(artifact.jar), "-d", str(work), str(work / "Driver.java")]),
                ("java", ["-cp", f"{work}:{artifact.jar}", "Driver", *_NAMES]),
            ):
                result = subprocess.run(
                    [tool, *arguments], capture_output=True, text=True, check=False
                )
                if result.returncode != 0:
                    raise ProbeError(f"{tool} failed: {result.stderr.strip()}")
            rows.append((artifact.name, artifact.observed, result.stdout.strip()))
    return rows


_QUESTIONS: list[tuple[str, str, Callable[[list[Artifact]], list[tuple[str, str, str]]]]] = [
    (
        "1",
        "`OperationCreator.getOperationName` — the name sources, in order",
        q1_the_name_sources_in_order,
    ),
    ("2", "the annotation type each `Annotations` field names", q2_which_annotation_each_source_is),
    (
        "3",
        "`OperationCreator.getDefaultExecutionTypeName` — the fallback",
        q3_the_fallback_and_its_direction,
    ),
    ("4", "`MethodHelper`'s two transformations", q4_the_transformation),
    ("5", "what `getPropertyName` returned, compiled and run", q5_what_the_implementation_returns),
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
        print(f"CP-15 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
