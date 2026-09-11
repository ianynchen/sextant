"""CP-7's measurement half: the four Spring rules the `@HttpExchange` direction
flip mirrors, read off the framework's own bytecode.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. Like CP-11 it reads each jar's own identity out of its own bytes
before it measures anything and refuses to file a cell under a version the
artifact did not claim (GUIDELINES §5.4, and CP-5's failure it exists to
prevent).

Every question answers PER RESOLVED ARTIFACT rather than once, so a rule read
against four Spring minors prints four rows and §5.4's scope is the rows
themselves rather than a sentence about them.

Everything it prints is the table `cp7_http_exchange.md` carries verbatim and
`tests/architecture/test_http_exchange_direction_rules.py` pins the shipped
catalog against.
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
# `javap -v`'s rendering of one annotation-attribute declaration and the
# `@AliasFor` that may sit on it.
_ATTRIBUTE = re.compile(r"^\s{2}public abstract (\S+) ([\w$]+)\(\);\s*$")
_ALIAS_FOR = re.compile(r'^\s*value="([^"]*)"\s*$')

# Markdown tables are `|`-delimited, so an instruction sequence is joined with
# something else: a `|` inside a cell silently splits the row, and a table
# nobody can read back is a table nobody re-checks.
_STEP = " ; "

_SEARCH_STRATEGY = "MergedAnnotations$SearchStrategy."
_TYPE_IN = "MergedAnnotationPredicates.typeIn"


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
    alone says nothing, `ldc class org/springframework/stereotype/Controller`
    is the rule.
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


def _annotation_search(output: str) -> tuple[str, list[str]]:
    """The method that builds the mapping's annotation search, and the search
    itself — from the `SearchStrategy` it names through the `typeIn` filter that
    says which annotations it accepts.

    Found by SEARCHING THE WHOLE DISASSEMBLY for the search strategy rather than
    by naming a method, because the method it lives in is not stable across the
    minors in scope: 6.1.6 and 6.2.15 declare a private static
    `getAnnotationDescriptors`, and 7.0.x inlines the same sequence into
    `createRequestMappingInfo`. Keying on a method name would have printed an
    empty cell for half the version scope and read as "the rule is gone".
    """
    lines = output.splitlines()
    index = next(
        (
            i
            for i, line in enumerate(lines)
            if _step(line) and _SEARCH_STRATEGY in (_step(line) or "")
        ),
        None,
    )
    if index is None:
        raise ProbeError("no method in this class names a MergedAnnotations SearchStrategy")
    declaration = next(
        (lines[i].strip() for i in range(index, -1, -1) if _METHOD_LINE.match(lines[i])), None
    )
    if declaration is None:
        raise ProbeError("the SearchStrategy instruction sits inside no method javap declared")
    body: list[str] = []
    for line in lines[index:]:
        step = _step(line)
        if step is None:
            break
        body.append(step)
        if _TYPE_IN in step:
            return declaration, body
    raise ProbeError("the annotation search names no `typeIn` filter")


def _named(artifacts: list[Artifact], name: str) -> list[Artifact]:
    found = [artifact for artifact in artifacts if artifact.name == name]
    if not found:
        raise ProbeError(f"no resolved artifact named {name}")
    return found


_RMHM = "org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping"


def q1_server_side_handler_predicate(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q1. Spring MVC's server-side handler test, per resolved minor.

    The rule the flip gates on. GUIDELINES §8.1 stated this for a month as
    "`@Controller` OR a type-level `@RequestMapping`", which is an OLDER
    Spring's rule; the disjunct is what a plain `@Service` implementation of an
    `@HttpExchange` interface would have to pass, and it is absent. The
    instruction sequence is the answer because the finding is that this is a
    PREDICATE call rather than a literal compare — a boolean would record the
    reader's conclusion instead of what the jar said.
    """
    return [
        (
            artifact.name,
            artifact.observed,
            _STEP.join(_body(_javap("-p", "-c", _RMHM, classpath=artifact.jar), "isHandler")),
        )
        for artifact in _named(artifacts, "spring-webmvc")
    ]


def q2_server_side_reads_http_exchange(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q2. Whether the SERVER side reads `@HttpExchange` at all, and with which
    annotation search.

    Two answers in one sequence, and the flip needs both. The `typeIn` filter
    names the annotation types a mapping may be built from — if `@HttpExchange`
    is not among them, an implemented interface serves nothing and the flip is
    a fabrication. The `SearchStrategy` says whether the search crosses the type
    hierarchy — if it does not, the interface's own annotations never reach the
    implementing class and the flip is a fabrication for a second reason.
    """
    rows = []
    for artifact in _named(artifacts, "spring-webmvc"):
        declaration, body = _annotation_search(_javap("-p", "-c", _RMHM, classpath=artifact.jar))
        rows.append((artifact.name, artifact.observed, _STEP.join([declaration, *body])))
    return rows


def q3_inherited_default_methods_are_candidates(
    artifacts: list[Artifact],
) -> list[tuple[str, str, str]]:
    """Q3. Whether a `default` method a controller inherits and never overrides
    is a handler candidate at all.

    `AbstractHandlerMethodMapping` selects a bean's handler methods through this
    one call, so what it walks IS the candidate set. It decides what our own
    handler symbol may be: a method the implementing class does not declare has
    no symbol on that class, and a join that insisted on one would drop a route
    the container really does serve.
    """
    rows = []
    for artifact in _named(artifacts, "spring-core"):
        output = _javap(
            "-p", "-c", "org.springframework.core.MethodIntrospector", classpath=artifact.jar
        )
        body = [
            step
            for step in _body(output, "selectMethods")
            if "ClassUtils." in step or "ReflectionUtils." in step
        ]
        rows.append((artifact.name, artifact.observed, _STEP.join(body)))
    return rows


def q4_which_attribute_carries_the_address(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q4. `@HttpExchange`'s own attributes, and which of them alias which.

    `spring-http-interface.yml` reads the address from `[value, url]`, and the
    two sides of the wire call it by different names: the client invoker reads
    `url()` and the server's mapping builder reads `value()`. That is a
    contradiction only if the two are separate attributes — so the `@AliasFor`
    pairing is the fact that decides whether one alias list serves both
    directions, or whether the flipped row reads an address the server ignores.
    """
    rows = []
    for artifact in _named(artifacts, "spring-web"):
        output = _javap(
            "-v",
            "-p",
            "org.springframework.web.service.annotation.HttpExchange",
            classpath=artifact.jar,
        )
        rows.append((artifact.name, artifact.observed, ", ".join(_aliases(output))))
    return rows


def _aliases(output: str) -> list[str]:
    """`name -> aliased name` for every attribute `javap -v` printed, in
    declaration order."""
    found: list[str] = []
    lines = output.splitlines()
    for index, line in enumerate(lines):
        attribute = _ATTRIBUTE.match(line)
        if attribute is None:
            continue
        alias = None
        # Scan to the NEXT declaration rather than a fixed window: `javap -v`
        # prints a variable number of lines per attribute (a descriptor, flags,
        # an `AnnotationDefault` and only sometimes a `RuntimeVisibleAnnotations`
        # block), and a window short enough to be safe against the next
        # attribute stopped one line before the `@AliasFor` value on this one.
        for following in lines[index + 1 :]:
            if _METHOD_LINE.match(following):
                break
            match = _ALIAS_FOR.match(following)
            if match:
                alias = match.group(1)
                break
        found.append(f"{attribute.group(2)}()" + (f" @AliasFor {alias}" if alias else ""))
    if not found:
        raise ProbeError("javap printed no attributes for the annotation at all")
    return found


_QUESTIONS: list[tuple[str, str, Callable[[list[Artifact]], list[tuple[str, str, str]]]]] = [
    ("1", "`RequestMappingHandlerMapping.isHandler`", q1_server_side_handler_predicate),
    (
        "2",
        "the mapping's annotation search and its accepted types",
        q2_server_side_reads_http_exchange,
    ),
    (
        "3",
        "`MethodIntrospector.selectMethods` — the handler-candidate walk",
        q3_inherited_default_methods_are_candidates,
    ),
    (
        "4",
        "`@HttpExchange`'s attributes and their `@AliasFor` pairing",
        q4_which_attribute_carries_the_address,
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
        print(f"CP-7 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
