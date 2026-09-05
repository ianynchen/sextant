"""CP-13's measurement half: what three frameworks do with an INHERITED member.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. It keeps CP-11/CP-12's two pre-flight guarantees, aborting on the
first that fails:

1. **Reads each jar's own identity out of its own bytes** and refuses to file a
   cell under a version the artifact did not claim (GUIDELINES §5.4, and CP-5's
   failure it exists to prevent).
2. **Indexes class -> jar** off the archives, so a class is attributed to the
   jar the run opened.

**One question, asked of three sites.** Three Class A Majors encode the same
invented rule — *a type's members are the ones it DECLARES* — and all three
were graded `read` by the sweep, with the framework half explicitly unverified:

* `A-M13` — a repository's query methods are taken to be the ones it declares,
  so a repository extending a module-local base loses every inherited query
  route.
* `A-M14` — CRUD exclusion matches on the bare method NAME, so a derived query
  method named `findAll(String)` is dropped.
* `A-M15` — `members: public_methods` joins on `enclosing`, so a `@WebService`
  class's inherited public operations are absent from the SOAP surface.

The language half was never in doubt (JLS 8.2, 9.2, 9.4.1; JLS 8.4.2 for the
signature). What was unverified is whether each FRAMEWORK acts on it, and that
is answerable from bytecode without a live deployment: the question in every
case is which reflective enumeration the framework calls —
`Class.getMethods()`, which includes inherited public methods, or
`getDeclaredMethods()`, which does not — and what it then filters out. Both are
instructions, so both are measurable.

**What this probe does NOT settle**, stated so the verdict is not read wider
than it was measured: nothing here was deployed. It records which method the
framework enumerates and which filters it applies to the result; it does not
observe a served route or a published WSDL. A live run remains rank 2 and 11 of
the sweep's probe backlog.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

# `<key>=<value>` in a `.properties` entry, and the manifest's own `Name: value`.
_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
# One `javap -c` instruction line. The operands are matched loosely on purpose,
# for CP-11's reason: an `invokeinterface #25,  2` carries two of them and a
# stricter pattern silently ENDS a body at the first such instruction.
_INSTRUCTION = re.compile(r"^\s*\d+:\s+(\S+)(.*)$")
# A `javap -c` method declaration line, which is what ends the body above it.
_DECLARATION = re.compile(r"^\s{2}\S.*?[\w$]+\s*\(")

_ASSUMED = "-"
# Markdown tables are `|`-delimited, so an instruction sequence is joined with
# something else: a `|` inside a cell silently splits the row, and a table
# nobody can read back is a table nobody re-checks.
_STEP = " ; "


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    """One resolved jar, and the identity it reported for itself."""

    __slots__ = ("classes", "jar", "name", "observed", "requested", "self_reported")

    def __init__(self, name: str, requested: str, jar: Path, entry: str, key: str) -> None:
        self.name = name
        self.requested = requested
        self.jar = jar
        self.self_reported = entry != _ASSUMED
        self.observed = _identity(jar, entry, key) if self.self_reported else requested
        if self.self_reported and self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was resolved as "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )
        self.classes = _classes_of(jar)


def _identity(jar: Path, entry: str, key: str) -> str:
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


def _classes_of(jar: Path) -> set[str]:
    with zipfile.ZipFile(jar) as archive:
        return {
            name[: -len(".class")].replace("/", ".")
            for name in archive.namelist()
            if name.endswith(".class")
        }


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


def _body(output: str, method: str, limit: int | None = None) -> list[str]:
    """One method's instruction sequence as `mnemonic <constant-pool comment>`.

    The comment is what makes the sequence both legible and checkable: `invokevirtual`
    alone says nothing, `invokevirtual java/lang/Class.getMethods` is the answer.
    """
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if re.search(rf"\b{method}\(", line)), None)
    if start is None:
        raise ProbeError(f"javap printed no `{method}` at all")
    body: list[str] = []
    for line in lines[start + 2 :]:
        if _DECLARATION.match(line):
            break
        match = _INSTRUCTION.match(line)
        if not match:
            continue
        operands = match.group(2)
        comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
        body.append(f"{match.group(1)} {comment}".strip())
    return body[:limit] if limit is not None else body


def _enumeration(body: list[str]) -> str:
    """Only the steps that answer the question: which reflective enumeration the
    framework calls, and what it then tests each member against.

    Filtered rather than printed whole, and the filter is the reason this cell
    is readable at all — `processClass` is 300 instructions. Every retained
    step is a `java/lang/Class` or `java/lang/reflect` call or a named
    framework predicate, so nothing that decides membership is dropped.
    """
    keep = (
        "java/lang/Class.getMethods",
        "java/lang/Class.getDeclaredMethods",
        "java/lang/reflect/Method.getDeclaringClass",
        "java/lang/reflect/Method.getParameterTypes",
        "java/lang/reflect/Method.getParameterCount",
        "java/lang/reflect/Method.getName",
        "java/lang/reflect/Modifier.isStatic",
        "java/lang/reflect/Modifier.isFinal",
        "isWebMethodBySpec",
        "isQueryMethod",
        "isBaseClassMethod",
        "isCustomMethod",
        "getMostSpecificMethod",
    )
    seen: list[str] = []
    for step in body:
        for wanted in keep:
            if wanted in step and step not in seen:
                seen.append(step)
    return _STEP.join(seen)


def _class_wide(output: str) -> list[str]:
    """Every instruction in a whole class, rather than one method's body.

    Needed because a framework predicate is not always in the method that
    names it: `calculateQueryMethods` at spring-data-commons 3.2.5 puts its
    filter in `lambda$calculateQueryMethods$2`, and
    `RepositoryAwareMethodLookup`'s comparisons are spread across several
    one-line private methods. `_enumeration`'s keep-list is narrow enough
    that a whole-class scan is still an answer rather than a dump — it
    retains only `java/lang/Class` and `java/lang/reflect` calls and the named
    framework predicates, which is exactly the set that decides membership.
    """
    return [
        f"{match.group(1)} {match.group(2).split('//', 1)[1].strip()}".strip()
        if "//" in match.group(2)
        else match.group(1)
        for line in output.splitlines()
        if (match := _INSTRUCTION.match(line))
    ]


def _named(artifacts: list[Artifact], name: str) -> Artifact:
    found = [artifact for artifact in artifacts if artifact.name == name]
    if not found:
        raise ProbeError(f"no resolved artifact named {name}")
    return found[0]


# --- the questions ---------------------------------------------------------


def q1_spring_data_query_methods(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q1 (`A-M13`). Which methods Spring Data treats as a repository's own.

    `RepositoryInformationSupport.calculateQueryMethods` is the whole answer,
    and `getMethods()` versus `getDeclaredMethods()` is the one instruction
    that decides whether an INHERITED query method is a route."""
    rows = []
    for artifact in [a for a in artifacts if a.name == "spring-data-commons"]:
        output = _javap(
            "-p",
            "-c",
            "org.springframework.data.repository.core.RepositoryInformationSupport",
            classpath=artifact.jar,
        )
        rows.append((artifact.name, artifact.observed, _enumeration(_class_wide(output))))
    return rows


def q2_spring_data_base_method_lookup(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q2 (`A-M14`). How Spring Data decides a method IS one of the base
    contract's — the test that separates a CRUD method from a query method.

    `MethodLookups$RepositoryAwareMethodLookup`'s own predicates are the
    answer, and the finding is that they compare a SIGNATURE while our
    `crud_methods` exclusion compares a bare NAME."""
    rows = []
    for artifact in [a for a in artifacts if a.name == "spring-data-commons"]:
        output = _javap(
            "-p",
            "-c",
            "org.springframework.data.repository.core.support."
            "MethodLookups$RepositoryAwareMethodLookup",
            classpath=artifact.jar,
        )
        rows.append((artifact.name, artifact.observed, _enumeration(_class_wide(output))))
    return rows


def q3_jaxws_exposed_members(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q3 (`A-M15`). Which members the JAX-WS reference implementation exposes
    as SOAP operations, read off `RuntimeModeler.processClass` — the method
    that walks an implementor class and builds its operation model."""
    artifact = _named(artifacts, "jaxws-rt")
    output = _javap("-p", "-c", "com.sun.xml.ws.model.RuntimeModeler", classpath=artifact.jar)
    return [(artifact.name, artifact.observed, _enumeration(_body(output, "processClass")))]


def q4_jaxws_web_method_test(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q4 (`A-M15`). What the JAX-WS RI then EXCLUDES from that enumeration —
    `isWebMethodBySpec`. The exclusions are the half a widened member join has
    to mirror, and one of them (`final`) our own SQL does not have."""
    artifact = _named(artifacts, "jaxws-rt")
    output = _javap("-p", "-c", "com.sun.xml.ws.model.RuntimeModeler", classpath=artifact.jar)
    return [(artifact.name, artifact.observed, _enumeration(_body(output, "isWebMethodBySpec")))]


_QUESTIONS: list[tuple[str, str, Callable[[list[Artifact]], list[tuple[str, str, str]]]]] = [
    ("1", "`RepositoryInformationSupport.calculateQueryMethods`", q1_spring_data_query_methods),
    ("2", "`MethodLookups$RepositoryAwareMethodLookup`", q2_spring_data_base_method_lookup),
    ("3", "`RuntimeModeler.processClass`", q3_jaxws_exposed_members),
    ("4", "`RuntimeModeler.isWebMethodBySpec`", q4_jaxws_web_method_test),
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
    print(
        "| identity read from the archive itself | "
        + " | ".join(
            "yes" if all(a.self_reported for a in artifacts if a.observed == version) else "assumed"
            for version in columns
        )
        + " |"
    )
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
        print(f"CP-13 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
