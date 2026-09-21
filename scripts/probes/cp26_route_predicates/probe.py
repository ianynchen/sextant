"""CP-26's measurement half: the route-tree predicates spec 2026-09-19 §5c reads as
request requirements — `RequestPredicates.queryParam`'s two overloads and the
`headers(Predicate)` it leaves unread, on the reactive stack (spring-webflux) and on
its servlet twin (spring-webmvc), with the `QueryParamPredicate.test` bytecode that
makes the requirement `required`; Spring Cloud Gateway's `PredicateSpec` `header`/
`query`/`cookie` overloads, and `BooleanSpec$BooleanOpSpec`'s declared members and
superclass (the three are INHERITED there, so a call after `and()`/`or()` carries the
subclass as its owner and no override exists to declare separately); and the
`Header=`/`Query=`/`Cookie=` properties spellings read off each `*RoutePredicateFactory`'s
`shortcutFieldOrder` — recorded for `gateway-properties-routes`, which is out of §5c's scope;
and how each of those three factories MATCHES the regex it is given (the `value` column
carries the regex as written because the framework matches it whole-string — `Pattern.
asMatchPredicate` in the header factory, `String.matches` in the query and cookie ones).

Called by `run.sh`, which resolves the jars; this script downloads nothing. Like CP-16
through CP-24 it reads each jar's own identity out of its own bytes before it measures
anything and refuses to file a cell under a version the archive did not claim
(GUIDELINES §5.4, and CP-5's failure it exists to prevent).
"""

from __future__ import annotations

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


# --- Q1/Q2: RequestPredicates.queryParam / headers, both stacks (§5c) ------------------


def q_request_predicates(jar: Path, package: str) -> str:
    """The parameter predicate factories a stack's `RequestPredicates` declares — every
    overload of `queryParam` AND of `param` (the two stacks spell it differently, which
    is the whole reason both are read) — with `headers`, and the `test` body of the
    predicate class each factory builds."""
    predicates = f"org.springframework.web.{package}.RequestPredicates"
    output = _javap("-p", "-s", predicates, classpath=jar)
    cells = []
    for name in ("queryParam", "param", "headers"):
        cells += [f"{name}{d}" for d in _descriptors(output, name)]
    if not cells:
        raise ProbeError(f"no queryParam/param/headers on {predicates}")
    for inner_name in ("QueryParamPredicate", "ParamPredicate"):
        try:
            inner = _javap("-p", "-c", f"{predicates}${inner_name}", classpath=jar)
        except ProbeError:
            continue
        body = _method_body(inner, "public boolean test(")
        kept = _steps(body, keep=("ServerRequest.", "filter", "isPresent", "ireturn"))
        cells.append(f"{inner_name}.test: {_STEP.join(kept)}")
    return _STEP.join(cells)


def q2b_servlet_params(jar: Path) -> str:
    """What the servlet `ServerRequest.param(name)` reads: `params()`, which
    `DefaultServerRequest` backs with the servlet request's own parameter map — query
    string and form body alike, the one API that cannot tell the two apart."""
    request = _javap(
        "-p", "-c", "org.springframework.web.servlet.function.ServerRequest", classpath=jar
    )
    body = _method_body(request, "param(java.lang.String)")
    cells = [
        f"ServerRequest.param: {_STEP.join(_steps(body, keep=('params', 'MultiValueMap.get')))}"
    ]
    params = _javap(
        "-p",
        "-c",
        "org.springframework.web.servlet.function.DefaultServerRequest$ServletParametersMap",
        classpath=jar,
    )
    reads = sorted(
        {
            s.split("InterfaceMethod ")[-1]
            for s in _steps(params.splitlines())
            if "HttpServletRequest.getParameter" in s
        }
    )
    cells.append(f"ServletParametersMap reads: {', '.join(reads)}")
    return _STEP.join(cells)


# --- Q3/Q4: the gateway's PredicateSpec and BooleanOpSpec (§5c) -----------------------


def q3_predicate_spec(jar: Path) -> str:
    output = _javap(
        "-p", "-s", "org.springframework.cloud.gateway.route.builder.PredicateSpec", classpath=jar
    )
    cells = []
    for name in ("header", "query", "cookie"):
        for descriptor in _descriptors(output, name):
            cells.append(f"{name}{descriptor}")
    if not cells:
        raise ProbeError("no header/query/cookie on PredicateSpec")
    return _STEP.join(cells)


def q4_boolean_op_spec(jar: Path) -> str:
    output = _javap(
        "-p",
        "-s",
        "org.springframework.cloud.gateway.route.builder.BooleanSpec$BooleanOpSpec",
        classpath=jar,
    )
    declared = next(
        (line.strip().rstrip(" {") for line in output.splitlines() if line.startswith("public ")),
        None,
    )
    if declared is None:
        raise ProbeError("no BooleanOpSpec class declaration")
    members = sorted(
        {match.group(1) for match in re.finditer(r"^\s+public [^(]* (\w+)\(", output, re.MULTILINE)}
    )
    overrides = [name for name in ("header", "query", "cookie") if name in members]
    return (
        f"{declared} ; declares: {', '.join(members)} ; "
        f"header/query/cookie overridden here: {overrides or 'none (inherited)'}"
    )


# --- Q5: the properties spellings (recorded, out of scope) ------------------------------


def q5_shortcut_field_orders(jar: Path) -> str:
    cells = []
    for factory in ("Header", "Query", "Cookie"):
        output = _javap(
            "-p",
            "-c",
            f"org.springframework.cloud.gateway.handler.predicate.{factory}RoutePredicateFactory",
            classpath=jar,
        )
        body = _method_body(output, "shortcutFieldOrder()")
        literals = [s[len("ldc String ") :] for s in _steps(body) if s.startswith("ldc String ")]
        cells.append(f"{factory}RoutePredicateFactory.shortcutFieldOrder: {', '.join(literals)}")
    return _STEP.join(cells)


# --- Q6: how the three factories match the regex (§5a/§5c, the `value` column) -----------


def q6_regex_matchers(jar: Path) -> str:
    """What each `*RoutePredicateFactory.apply` builds and how its predicate tests a
    value against `regexp`: the header factory compiles the regex in `apply` and its
    anonymous predicate's `test` calls `Pattern.asMatchPredicate`; the query and cookie
    factories' predicates match in a `lambda$test$0` that calls `String.matches` — all
    three whole-string matches, which is why the `value` column carries the regex as
    written and a consumer compares it for equality only where the spelling is a literal."""
    package = "org.springframework.cloud.gateway.handler.predicate"
    cells = []
    for factory in ("Header", "Query", "Cookie"):
        outer = _javap("-p", "-c", f"{package}.{factory}RoutePredicateFactory", classpath=jar)
        apply = _steps(
            _method_body(outer, f"apply({package}.{factory}RoutePredicateFactory$Config)"),
            keep=("Pattern.compile", '$1."<init>"'),
        )
        inner = _javap("-p", "-c", f"{package}.{factory}RoutePredicateFactory$1", classpath=jar)
        test = _steps(
            _method_body(
                inner, "public boolean test(org.springframework.web.server.ServerWebExchange)"
            ),
            keep=(
                "getHeaders",
                "getQueryParams",
                "getCookies",
                "asMatchPredicate",
                "String.matches",
                "InvokeDynamic",
            ),
        )
        cell = f"{factory}RoutePredicateFactory.apply: {_STEP.join(apply)}"
        cell += f" ; $1.test: {_STEP.join(test)}"
        if "lambda$test$0(" in inner:
            matcher = _steps(_method_body(inner, "lambda$test$0("), keep=("matches", "getValue"))
            cell += f" ; $1.lambda$test$0: {_STEP.join(matcher)}"
        cells.append(cell)
    return _STEP.join(cells)


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        key, group, name, requested, jar = spec.split("|")
        artifacts[key] = Artifact(key, group, name, requested, Path(jar))
    webflux, webmvc, gateway = artifacts["webflux"], artifacts["webmvc"], artifacts["gateway"]

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
        "1",
        "reactive RequestPredicates.queryParam/param/headers overloads, and QueryParamPredicate.test",
        webflux,
        q_request_predicates(webflux.jar, "reactive.function.server"),
    )
    row(
        "2",
        "servlet RequestPredicates.queryParam/param/headers overloads, and ParamPredicate.test",
        webmvc,
        q_request_predicates(webmvc.jar, "servlet.function"),
    )
    row(
        "2b",
        "servlet ServerRequest.param → params() → what DefaultServerRequest reads off HttpServletRequest",
        webmvc,
        q2b_servlet_params(webmvc.jar),
    )
    row(
        "3",
        "PredicateSpec header/query/cookie overloads",
        gateway,
        q3_predicate_spec(gateway.jar),
    )
    row(
        "4",
        "BooleanSpec$BooleanOpSpec: superclass, declared members, whether header/query/cookie are overridden",
        gateway,
        q4_boolean_op_spec(gateway.jar),
    )
    row(
        "5",
        "Header/Query/Cookie RoutePredicateFactory.shortcutFieldOrder — the properties spellings",
        gateway,
        q5_shortcut_field_orders(gateway.jar),
    )
    row(
        "6",
        "Header/Query/Cookie RoutePredicateFactory: what apply builds and how its predicate matches regexp — Pattern.asMatchPredicate or String.matches",
        gateway,
        q6_regex_matchers(gateway.jar),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-26 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
