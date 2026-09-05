"""CP-11's measurement half: the four framework rules the round-1 sweep fix
pass mirrors, read off the frameworks' own bytecode.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. Like CP-10 it does two things before it measures anything, and aborts
on the first that fails:

1. **Reads each jar's own identity out of its own bytes** and refuses to file a
   cell under a version the artifact did not claim (GUIDELINES §5.4, and CP-5's
   failure it exists to prevent). Where the self-report lives differs per
   artifact — the manifest's `Implementation-Version`, or, for OkHttp, the
   `ConstantValue` of `okhttp3.OkHttp.VERSION`, which is the only place that
   archive writes its version at all. An artifact that writes it NOWHERE is
   declared `-` in `run.sh` and prints as `assumed`, rather than being labelled
   with the coordinate as though it had been observed.
2. **Indexes class -> jar** off the archives, so a class is attributed to the
   jar the run opened. Q3 depends on it: the whole finding is which of two
   jakarta.websocket artifacts declares which annotation.

Every question answers PER RESOLVED ARTIFACT rather than once, so a rule read
against five Spring minors prints five rows and §5.4's scope is the rows
themselves rather than a sentence about them.

Everything it prints is the table `cp11_sweep_round1.md` carries verbatim and
`tests/architecture/test_sweep_round1_framework_rules.py` pins the shipped
catalogs and engines against.
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
# `javap -v`'s rendering of a compile-time constant field.
_CONSTANT_VALUE = re.compile(r"^\s*ConstantValue:\s*String\s+(\S+)\s*$")
# `javap -p -s`'s two lines: the declaration, then the erased descriptor.
_DECLARATION = re.compile(r"^\s{2}\S.*?([\w$]+)\s*\(")
_DESCRIPTOR_LINE = re.compile(r"^\s*descriptor:\s*(\S+)\s*$")
# One `javap -c` instruction line: ordinal, mnemonic, then whatever operands
# and trailing `// comment` follow. The operands are matched loosely on purpose
# — `invokedynamic #21,  0` and `invokeinterface #25,  2` carry two of them,
# and a pattern that assumed one silently ENDED the body at the first such
# instruction, which is how Q6a first printed an empty cell.
_INSTRUCTION = re.compile(r"^\s*\d+:\s+(\S+)(.*)$")

_ASSUMED = "-"
# Markdown tables are `|`-delimited, so an instruction sequence is joined with
# something else. Not cosmetic: a `|` inside a cell silently splits the row, and
# a table nobody can read back is a table nobody re-checks.
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

    @property
    def label(self) -> str:
        return f"{self.name} {self.observed}"


def _identity(jar: Path, entry: str, key: str) -> str:
    """The version this ARCHIVE claims for itself, read out of its own bytes.

    Two spellings, because the artifacts in scope use two. `class:<fqn>` reads
    the `ConstantValue` of a static final field through `javap -v` — OkHttp
    writes no manifest version and ships no `pom.properties`, and
    `okhttp3.OkHttp.VERSION` is where it does state one. Everything else names
    an archive entry and a key inside it.
    """
    if entry.startswith("class:"):
        output = _javap("-v", "-p", entry.removeprefix("class:"), classpath=jar)
        for line in _field_block(output, key):
            match = _CONSTANT_VALUE.match(line)
            if match:
                return match.group(1)
        raise ProbeError(f"{jar.name}'s `{entry}` declares no constant `{key}`")
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


def _field_block(output: str, field: str) -> list[str]:
    """The `javap -v` lines belonging to one field declaration."""
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if re.search(rf"\b{re.escape(field)};\s*$", line):
            return lines[index : index + 5]
    return []


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


def _methods(output: str) -> list[tuple[str, str]]:
    """`(name, erased descriptor)` for every method `javap -p -s` printed."""
    found: list[tuple[str, str]] = []
    pending: str | None = None
    for line in output.splitlines():
        descriptor = _DESCRIPTOR_LINE.match(line)
        if descriptor and pending is not None:
            found.append((pending, descriptor.group(1)))
            pending = None
            continue
        declaration = _DECLARATION.match(line)
        pending = declaration.group(1) if declaration else pending
    return found


def _body(output: str, method: str) -> list[str]:
    """One method's instruction sequence as `mnemonic <constant-pool comment>`.

    The comment is what makes the sequence both legible and checkable: `ldc`
    alone says nothing, `ldc class org/springframework/stereotype/Controller`
    is the rule.
    """
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if re.search(rf"\b{method}\(", line)), None)
    if start is None:
        raise ProbeError(f"javap printed no `{method}` at all")
    body: list[str] = []
    for line in lines[start + 2 :]:
        match = _INSTRUCTION.match(line)
        if not match:
            break
        operands = match.group(2)
        comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
        body.append(f"{match.group(1)} {comment}".strip())
    return body


# --- The four questions, in the order `cp11_sweep_round1.md` states them -----
#
# Each returns one `(label, version, observed)` row per artifact it applies to.
# The answers are whole strings rather than booleans on purpose: a boolean
# records the reader's conclusion, a string records what the jar said, and only
# the second can be re-checked by somebody who disagrees.

_HTTP_VERBS = frozenset({"get", "head", "post", "put", "patch", "delete", "options", "trace"})

_WEBSOCKET_ANNOTATIONS = (
    "jakarta.websocket.OnMessage",
    "jakarta.websocket.ClientEndpoint",
    "jakarta.websocket.server.ServerEndpoint",
)


def q1_okhttp_verb_setters(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q1 (`A-C2`). Every `Request.Builder` method that SETS the verb — a named
    verb, or the generic `method(String, RequestBody)`. Completeness is the
    whole question: an uncovered one falls through as an unmatched fluent step
    and leaves the root's `http_method: GET` default standing."""
    rows = []
    for artifact in _named(artifacts, "okhttp"):
        output = _javap("-p", "-s", "okhttp3.Request$Builder", classpath=artifact.jar)
        setters = sorted(
            f"{name}{descriptor.split(')')[0]})"
            for name, descriptor in _methods(output)
            if (name.lower() in _HTTP_VERBS or name == "method")
            and descriptor.endswith(")Lokhttp3/Request$Builder;")
        )
        rows.append((artifact.name, artifact.observed, ", ".join(setters)))
    return rows


def q2_spring_is_handler(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q2 (`A-C7`). The body of Spring MVC's server-side handler test, per
    resolved Spring minor. The finding is that it is a PREDICATE call, not a
    literal annotation compare, so the instruction sequence is the answer and a
    boolean would not be."""
    rows = []
    for artifact in _named(artifacts, "spring-webmvc"):
        output = _javap(
            "-p",
            "-c",
            "org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping",
            classpath=artifact.jar,
        )
        rows.append((artifact.name, artifact.observed, _STEP.join(_body(output, "isHandler"))))
    return rows


def q3_websocket_annotation_homes(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q3 (`A-C1`). Which jakarta.websocket artifact declares each of the three
    annotations, and what each targets. `@OnMessage` shipping in the CLIENT api
    jar and targeting METHOD is the direction-inversion finding: it is the
    message callback for a dialling-out `@ClientEndpoint` class exactly as much
    as for a served `@ServerEndpoint` one, so it cannot mint an inbound row on
    its own."""
    websocket = [a for a in artifacts if a.name.startswith("jakarta.websocket")]
    parts = []
    for fqn in _WEBSOCKET_ANNOTATIONS:
        homes = sorted((a for a in websocket if fqn in a.classes), key=lambda a: a.name)
        if not homes:
            raise ProbeError(f"no resolved artifact declares {fqn}")
        parts.append(
            f"{fqn.rpartition('.')[2]} in {'+'.join(a.name for a in homes)} "
            f"@Target({_target_of(homes[0], fqn)})"
        )
    versions = sorted({a.observed for a in websocket})
    return [("+".join(sorted(a.name for a in websocket)), ", ".join(versions), "; ".join(parts))]


def _target_of(artifact: Artifact, fqn: str) -> str:
    output = _javap("-v", "-p", fqn, classpath=artifact.jar)
    return ",".join(sorted(set(re.findall(r"ElementType;\.(\w+)", output))))


def q4_retrofit_interface_only(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q4 (`A-C6`). What `Retrofit.create` does with a non-interface. The
    catalog claim under test is "Retrofit only ever proxies interfaces", and the
    evidence is the guard's own instruction sequence — an `isInterface` test
    followed by an unconditional throw."""
    rows = []
    for artifact in _named(artifacts, "retrofit"):
        output = _javap("-p", "-c", "retrofit2.Retrofit", classpath=artifact.jar)
        guard = _body(output, "validateServiceInterface")[:6]
        rows.append((artifact.name, artifact.observed, _STEP.join(guard)))
    return rows


def _named(artifacts: list[Artifact], name: str) -> list[Artifact]:
    found = [artifact for artifact in artifacts if artifact.name == name]
    if not found:
        raise ProbeError(f"no resolved artifact named {name}")
    return found


def q5_spring_stomp_is_handler(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q5 (`A-C1`, `spring-stomp`). The catalog declared NO type-level gate at
    all, so one method annotation minted an endpoint. The framework does have a
    gate, and it is the same predicate Q2 measures for MVC — which is the fact
    that makes adding one to the catalog a mirror rather than an invention."""
    rows = []
    for artifact in _named(artifacts, "spring-messaging"):
        output = _javap(
            "-p",
            "-c",
            "org.springframework.messaging.simp.annotation.support."
            "SimpAnnotationMethodMessageHandler",
            classpath=artifact.jar,
        )
        rows.append((artifact.name, artifact.observed, _STEP.join(_body(output, "isHandler"))))
    return rows


def q6_http_interface_requires_an_interface(
    artifacts: list[Artifact],
) -> list[tuple[str, str, str]]:
    """Q6 (`A-C1`, `spring-http-interface`). Whether an `@HttpExchange` client
    must be an interface, which decides whether `declared_on: interface` is a
    mirror or a guess.

    TWO rows, because the answer is not in one place and saying so is the
    point: `HttpServiceProxyFactory.createClient` hands the type to Spring
    AOP's `ProxyFactory.getProxy(Class, Interceptor)`, and the requirement is
    asserted two hops down in `AdvisedSupport.addInterface`. Recording both
    bodies is what keeps the verdict a measurement instead of a chain somebody
    reasoned through once.
    """
    rows = []
    for artifact in _named(artifacts, "spring-web"):
        output = _javap(
            "-p",
            "-c",
            "org.springframework.web.service.invoker.HttpServiceProxyFactory",
            classpath=artifact.jar,
        )
        body = [
            step for step in _body(output, "createClient") if "aop/framework/ProxyFactory" in step
        ]
        rows.append((artifact.name, artifact.observed, _STEP.join(body)))
    for artifact in _named(artifacts, "spring-aop"):
        output = _javap(
            "-p", "-c", "org.springframework.aop.framework.AdvisedSupport", classpath=artifact.jar
        )
        body = _body(output, "public void addInterface")[:7]
        rows.append((artifact.name, artifact.observed, _STEP.join(body)))
    return rows


_QUESTIONS: list[tuple[str, str, Callable[[list[Artifact]], list[tuple[str, str, str]]]]] = [
    ("1", "okhttp `Request$Builder` verb setters", q1_okhttp_verb_setters),
    ("2", "Spring MVC `RequestMappingHandlerMapping.isHandler`", q2_spring_is_handler),
    ("3", "jakarta.websocket annotation homes and targets", q3_websocket_annotation_homes),
    ("4", "`Retrofit.create`'s interface guard", q4_retrofit_interface_only),
    (
        "5",
        "Spring STOMP `SimpAnnotationMethodMessageHandler.isHandler`",
        q5_spring_stomp_is_handler,
    ),
    (
        "6",
        "`@HttpExchange` client proxying, and its interface assertion",
        q6_http_interface_requires_an_interface,
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
        print(f"CP-11 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
