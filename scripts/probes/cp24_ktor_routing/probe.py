"""CP-24's measurement half: the Ktor 3.0.3 routing surface spec 2026-09-19 §4b, §4c
and §5d read — the selector and terminal signatures on `RoutingBuilderKt` and
`Route`, `HttpMethod.DefaultMethods`' members, the `HttpMethod$Companion.get*` and
`ContentType$Application.get*` getters with the value each returns (read off the
string literal the static initialiser passes to the field the getter reads), the
`ParametersKt.getOrFail` overloads and the exception their bodies throw, the
`StringValues.get` owners behind `ApplicationRequest.getHeaders`/`getQueryParameters`
and `ApplicationCall.getParameters`, and `HttpMethodRouteSelector.evaluate`'s
bytecode — which returns the failure constant on a method mismatch, so a route
under disagreeing `method` selectors never dispatches (A11: bytecode, no server run).

Called by `run.sh`, which resolves the jars; this script downloads nothing. Like
CP-16 through CP-23 it reads each jar's own identity out of its own bytes before it
measures anything and refuses to file a cell under a version the archive did not
claim (GUIDELINES §5.4, and CP-5's failure it exists to prevent).
"""

from __future__ import annotations

import itertools
import re
import subprocess
import sys
import zipfile
from pathlib import Path

_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
_STEP = " ; "


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    def __init__(self, key: str, group: str, name: str, requested: str, jar: Path):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        self.observed = _identity(jar, "META-INF/MANIFEST.MF", "Implementation-Version")
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was expected to report "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )


def _identity(jar: Path, entry: str, key: str) -> str:
    with zipfile.ZipFile(jar) as archive:
        names = [n for n in archive.namelist() if n == entry or n.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}`")
        text = archive.read(names[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    raise ProbeError(f"{jar.name}'s `{entry}` declares no `{key}`")


def _javap(*arguments: str, classpath: Path) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _method_body(output: str, header: str) -> list[str]:
    """The instruction lines of the first method whose declaration line contains
    `header`, up to the blank line that ends it."""
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if header in line), None)
    if start is None:
        raise ProbeError(f"no method matching {header!r}")
    body: list[str] = []
    for line in lines[start + 1 :]:
        if not line.strip():
            break
        body.append(line)
    return body


def _step(line: str) -> str | None:
    match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _steps(body: list[str], keep: tuple[str, ...] = ()) -> list[str]:
    steps = [s for s in (_step(line) for line in body) if s is not None]
    if keep:
        steps = [s for s in steps if any(marker in s for marker in keep)]
    return steps


def _descriptors(output: str, name: str) -> list[str]:
    """Every `descriptor:` line that follows a `public ... <name>(` declaration."""
    found: list[str] = []
    lines = output.splitlines()
    for i, line in enumerate(lines[:-1]):
        declares = re.search(rf"\b{re.escape(name)}\(", line) and "descriptor:" not in line
        if declares and "descriptor:" in lines[i + 1]:
            found.append(lines[i + 1].split("descriptor:", 1)[1].strip())
    return found


# --- Q1: the selector and terminal signatures (§4b, §4c) ---------------------


def q1_selectors(server: Path) -> str:
    output = _javap("-p", "-s", "io.ktor.server.routing.RoutingBuilderKt", classpath=server)
    cells = []
    for name in ("route", "method", "param", "optionalParam", "header", "accept", "contentType"):
        for descriptor in _descriptors(output, name):
            cells.append(f"{name}{descriptor}")
    if not cells:
        raise ProbeError("no selector on RoutingBuilderKt found")
    return _STEP.join(cells)


def q1b_handle(server: Path) -> str:
    output = _javap("-p", "-s", "io.ktor.server.routing.Route", classpath=server)
    header = next((line for line in output.splitlines() if " handle(" in line), None)
    if header is None:
        raise ProbeError("no Route.handle found")
    descriptor = _descriptors(output, "handle")
    kind = "interface" if "public interface io.ktor.server.routing.Route" in output else "class"
    return f"Route is an {kind} ; {header.strip()} ; {descriptor[0] if descriptor else '?'}"


# --- Q2/Q3: HttpMethod — DefaultMethods and the companion getters (§4b, §4c) ---


def _clinit_string_fields(output: str) -> dict[str, list[str]]:
    """Field name → the string literals `ldc`ed since the previous `putstatic`, read off
    the static initialiser: the constructor arguments of the value that field holds."""
    body = _method_body(output, "static {}")
    pending: list[str] = []
    fields: dict[str, list[str]] = {}
    for step in _steps(body):
        if step.startswith("ldc String "):
            pending.append(step[len("ldc String ") :])
        elif step.startswith("putstatic"):
            match = re.search(r"Field (\w+):", step)
            if match:
                fields[match.group(1)] = pending
            pending = []
    return fields


def q2_default_methods(http: Path) -> str:
    output = _javap("-p", "-c", "io.ktor.http.HttpMethod", classpath=http)
    body = _method_body(output, "static {}")
    steps = _steps(body)
    # The `listOf` call's array: every `getstatic Field X` that precedes an `aastore`.
    members: list[str] = []
    for previous, step in itertools.pairwise(steps):
        if step == "aastore" and previous.startswith("getstatic"):
            match = re.search(r"Field (\w+):", previous)
            if match:
                members.append(match.group(1))
    fields = _clinit_string_fields(output)
    values = [fields.get(member, ["?"])[-1] for member in members]
    holder = next((s for s in steps if "DefaultMethods" in s and s.startswith("putstatic")), "?")
    return (
        f"members in order: {', '.join(members)} ; values: {', '.join(values)} ; "
        f"built by {next((s for s in steps if 'listOf' in s), '?')} ; {holder}"
    )


def q3_http_method_getters(http: Path) -> str:
    companion = _javap("-p", "-c", "io.ktor.http.HttpMethod$Companion", classpath=http)
    outer = _javap("-p", "-c", "io.ktor.http.HttpMethod", classpath=http)
    fields = _clinit_string_fields(outer)
    cells = []
    for name in re.findall(r"public final io\.ktor\.http\.HttpMethod (get\w+)\(\);", companion):
        body = _method_body(companion, f" {name}();")
        target = next((s for s in _steps(body) if "invokestatic" in s or "getstatic" in s), "?")
        # `access$getGet$cp` reads field `Get`; a `getstatic` names the field directly.
        match = re.search(r"access\$get(\w+)\$cp|Field (\w+):", target)
        field = (match.group(1) or match.group(2)) if match else "?"
        literal = fields.get(field, ["?"])[-1]
        cells.append(f'{name}() -> {field} = "{literal}"')
    if not cells:
        raise ProbeError("no HttpMethod$Companion getters found")
    return _STEP.join(cells)


def q4_content_type_getters(http: Path) -> str:
    output = _javap("-p", "-c", "io.ktor.http.ContentType$Application", classpath=http)
    fields = _clinit_string_fields(output)
    cells = []
    for name in re.findall(r"public final io\.ktor\.http\.ContentType (get\w+)\(\);", output):
        body = _method_body(output, f" {name}();")
        target = next((s for s in _steps(body) if s.startswith("getstatic")), "?")
        match = re.search(r"Field (\w+):", target)
        field = match.group(1) if match else "?"
        literals = fields.get(field, [])
        value = "/".join(literals[:2]) if len(literals) >= 2 else "?"
        cells.append(f'{name}() -> {field} = "{value}"')
    if not cells:
        raise ProbeError("no ContentType$Application getters found")
    return _STEP.join(cells)


# --- Q5: getOrFail and what it throws (§5d) ------------------------------------


def q5_get_or_fail(server: Path) -> str:
    plain = _javap("-p", "-s", "io.ktor.server.util.ParametersKt", classpath=server)
    descriptors = _descriptors(plain, "getOrFail")
    output = _javap("-p", "-c", "io.ktor.server.util.ParametersKt", classpath=server)
    cells = [f"overloads: {', '.join(descriptors)}"]
    for header in (
        "public static final java.lang.String getOrFail(",
        "getOrFailImpl(io.ktor.http.Parameters, java.lang.String, io.ktor.util.reflect.TypeInfo)",
    ):
        body = _method_body(output, header)
        kept = _steps(body, keep=("Parameters.get", "ifnonnull", "new ", "athrow", "fromValues"))
        cells.append(f"{header.split('(')[0].split()[-1]}: {_STEP.join(kept)}")
    return _STEP.join(cells)


# --- Q6: the StringValues owners (§5d) -----------------------------------------


def q6_string_values_owners(server: Path, http: Path, utils: Path) -> str:
    request = _javap("-p", "-s", "io.ktor.server.request.ApplicationRequest", classpath=server)
    call = _javap("-p", "-s", "io.ktor.server.application.ApplicationCall", classpath=server)
    cells = []
    for output, owner, name in (
        (request, "ApplicationRequest", "getHeaders"),
        (request, "ApplicationRequest", "getQueryParameters"),
        (call, "ApplicationCall", "getParameters"),
    ):
        descriptor = _descriptors(output, name)
        cells.append(f"{owner}.{name}{descriptor[0] if descriptor else '?'}")
    for type_name in ("io.ktor.http.Headers", "io.ktor.http.Parameters"):
        declared = next(
            line.strip().rstrip(" {")
            for line in _javap("-p", type_name, classpath=http).splitlines()
            if line.startswith("public ")
        )
        cells.append(declared)
    values = _javap("-p", "-s", "io.ktor.util.StringValues", classpath=utils)
    get = [d for d in _descriptors(values, "get") if d == "(Ljava/lang/String;)Ljava/lang/String;"]
    get_all = _descriptors(values, "getAll")
    cells.append(
        f"StringValues.get{get[0] if get else '?'} ; StringValues.getAll{get_all[0] if get_all else '?'}"
    )
    return _STEP.join(cells)


# --- Q7: HttpMethodRouteSelector.evaluate (A11) --------------------------------


def q7_evaluate(server: Path) -> str:
    output = _javap("-p", "-c", "io.ktor.server.routing.HttpMethodRouteSelector", classpath=server)
    body = _method_body(output, "evaluate(io.ktor.server.routing.RoutingResolveContext")
    return _STEP.join(_steps(body))


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        key, group, name, requested, jar = spec.split("|")
        artifacts[key] = Artifact(key, group, name, requested, Path(jar))
    server, http, utils = artifacts["server"], artifacts["http"], artifacts["utils"]

    columns = sorted({a.observed for a in artifacts.values()})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(sorted(f"{a.group}:{a.name}" for a in artifacts.values() if a.observed == v))
            for v in columns
        )
        + " |"
    )
    print(
        "| identity read from the archive itself (`Implementation-Version`) | "
        + " | ".join(["yes"] * len(columns))
        + " |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    def row(number: str, question: str, artifact: Artifact, observed: str) -> None:
        print(
            f"| {number} | {question} | `{artifact.group}:{artifact.name}` | {artifact.observed} | `{observed}` |"
        )

    row(
        "1a",
        "RoutingBuilderKt selector signatures: route ×2, method, param ×2, optionalParam, header, accept, contentType",
        server,
        q1_selectors(server.jar),
    )
    row(
        "1b",
        "Route.handle: a member of the Route interface, its descriptor",
        server,
        q1b_handle(server.jar),
    )
    row(
        "2",
        "HttpMethod.DefaultMethods: members and values, from the static initialiser",
        http,
        q2_default_methods(http.jar),
    )
    row(
        "3",
        "HttpMethod$Companion.get* getters and the literal each field was built from",
        http,
        q3_http_method_getters(http.jar),
    )
    row(
        "4",
        "ContentType$Application.get* getters and the type/subtype literals each field was built from",
        http,
        q4_content_type_getters(http.jar),
    )
    row(
        "5",
        "ParametersKt.getOrFail overloads and what their bodies throw on a missing name",
        server,
        q5_get_or_fail(server.jar),
    )
    row(
        "6",
        "StringValues.get owners: ApplicationRequest.getHeaders/getQueryParameters, ApplicationCall.getParameters",
        server,
        q6_string_values_owners(server.jar, http.jar, utils.jar),
    )
    row(
        "7",
        "HttpMethodRouteSelector.evaluate bytecode: the failure constant on a method mismatch",
        server,
        q7_evaluate(server.jar),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-24 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
