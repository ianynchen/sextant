"""CP-25's measurement half. Row 1: Javalin 6.4.0's `ApiBuilder` guard — what
`staticInstance()` throws when no block is open (the exception class and the
message literal) and one verb's first instructions showing every static verb goes
through it — the measured fact `javalin-apibuilder.yml`'s `follow_calls: all` rests
on (spec 2026-09-19 §4a). Rows 2–12: the parameter-annotation binder rules of §5b —
Spring's `required`/`isOptional`/`handleMissingValue` sequence and what
`isOptional` reads (`Optional`, an annotation whose simple name is `Nullable`, the
Kotlin delegate), `HeadersRequestCondition` dropping `Accept`/`Content-Type` (A4),
the `defaultValue` element_value_pairs check (the one row that compiles a sample),
Micronaut's annotation attributes, its missing-value path (`isNullable` → null,
`isOptional` → empty, else `UnsatisfiedRouteException`) and the annotation
spellings its processor maps to that `Nullable` stereotype, RESTEasy Reactive's
extractors handing a null through and `ParameterHandler` substituting only a
`@DefaultValue`, JAX-RS's `value`-only attributes, and reactive-routes' generated
`HttpServerRequest.getParam`/`getHeader` read whose Vert.x return is `@Nullable`.
The §5d rows (Javalin `Validator.get()`, `jakarta.servlet` reads) join with that
mechanism's task.

Called by `run.sh`, which resolves the jars; this script downloads nothing. Like
CP-16 through CP-24 it reads each jar's own identity out of its own bytes before it
measures anything and refuses to file a cell under a version the archive did not
claim (GUIDELINES §5.4, and CP-5's failure it exists to prevent).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
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
    # The mnemonic is a word: a `tableswitch` case (`1: 104`) is not a step.
    match = re.match(r"^\s*\d+:\s+([a-z][a-z0-9_]*)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _steps(body: list[str]) -> list[str]:
    return [s for s in (_step(line) for line in body) if s is not None]


def _steps_between(body: list[str], first: int, last: int) -> list[str]:
    """The instructions whose bytecode offset lies in `[first, last]` — a window
    into a long method, quoted by offset so the cell can be re-found in `javap`."""
    out = []
    for line in body:
        match = re.match(r"^\s*(\d+):", line)
        if match and first <= int(match.group(1)) <= last:
            step = _step(line)
            if step is not None:
                out.append(step)
    return out


def _abstract_members(output: str) -> list[str]:
    """An annotation interface's attributes: its `public abstract` members, as
    `type name`."""
    return [
        re.sub(r"^\s*public abstract\s+", "", line.strip()).rstrip(";").replace("()", "")
        for line in output.splitlines()
        if line.strip().startswith("public abstract")
    ]


def _literals(body: list[str]) -> list[str]:
    """Every `ldc String …` literal in a method body, in order."""
    return [line.split("// String ", 1)[1].strip() for line in body if "// String " in line]


# --- Q1: the ApiBuilder guard (spec 2026-09-19 §4a, `follow_calls: all`) -------


def q1_api_builder_guard(javalin: Path) -> str:
    output = _javap("-c", "-p", "io.javalin.apibuilder.ApiBuilder", classpath=javalin)
    field = next(
        (
            line.strip()
            for line in output.splitlines()
            if "staticJavalin;" in line and "static" in line
        ),
        "?",
    )
    guard = _steps(_method_body(output, "staticInstance();"))
    verb = _steps(
        _method_body(output, "public static void get(java.lang.String, io.javalin.http.Handler);")
    )
    return _STEP.join(
        [
            f"field: {field}",
            "staticInstance(): " + _STEP.join(guard),
            "get(String, Handler) opens with: " + _STEP.join(verb[:1]),
        ]
    )


# --- Q2–Q5: Spring (spec 2026-09-19 §5b `requirement: binder`, F6; §5c A4) ---


def q2_spring_resolve_argument(spring_web: Path) -> str:
    """The null-value branch of `resolveArgument`: `defaultValue` when one is set,
    else `required && !isOptional()` → `handleMissingValue`; and what turns an
    unwritten `defaultValue` into the null that branch reads."""
    cls = "org.springframework.web.method.annotation.AbstractNamedValueMethodArgumentResolver"
    output = _javap("-c", "-p", cls, classpath=spring_web)
    body = _method_body(output, "public final java.lang.Object resolveArgument(")
    window = _steps_between(body, 92, 147)
    info = _method_body(output, "updateNamedValueInfo(")
    default_none = next((lit for lit in _literals(info) if lit.startswith("\\n")), "?")
    # As javap prints it: the escapes are javap's own spelling of the constant's
    # control and private-use characters, not a second layer added here.
    attrs = _abstract_members(
        _javap("-p", "org.springframework.web.bind.annotation.RequestParam", classpath=spring_web)
    )
    return _STEP.join(
        [
            "resolveArgument null-value branch (offsets 92-147): " + _STEP.join(window),
            f"updateNamedValueInfo: defaultValue equal to ValueConstants.DEFAULT_NONE (javap: {default_none}) becomes null",
            "RequestParam attributes: " + ", ".join(attrs),
        ]
    )


def q3_spring_is_optional(spring_core: Path) -> str:
    """`MethodParameter.isOptional()` and the two reads under it."""
    output = _javap("-c", "-p", "org.springframework.core.MethodParameter", classpath=spring_core)
    is_optional = _steps(_method_body(output, "public boolean isOptional();"))
    nullable = _method_body(output, "private boolean hasNullableAnnotation();")
    nullable_steps = [
        s
        for s in _steps(nullable)
        if "String Nullable" in s or "getSimpleName" in s or "getParameterAnnotations" in s
    ]
    delegate = _javap(
        "-c", "-p", "org.springframework.core.MethodParameter$KotlinDelegate", classpath=spring_core
    )
    kotlin = [
        s
        for s in _steps(_method_body(delegate, "public static boolean isOptional("))
        if "isMarkedNullable" in s or "KParameter.isOptional" in s
    ]
    return _STEP.join(
        [
            "isOptional(): " + _STEP.join(is_optional),
            "hasNullableAnnotation(): " + _STEP.join(nullable_steps),
            "KotlinDelegate.isOptional(): " + _STEP.join(kotlin),
        ]
    )


def q4_headers_condition_drops_two(spring_webmvc: Path) -> str:
    """`HeadersRequestCondition.parseExpressions` skips two header names (A4)."""
    output = _javap(
        "-c",
        "-p",
        "org.springframework.web.servlet.mvc.condition.HeadersRequestCondition",
        classpath=spring_webmvc,
    )
    body = _method_body(output, "parseExpressions(")
    kept = [
        s
        for s in _steps(body)
        if "String " in s or "equalsIgnoreCase" in s or "HeaderExpression" in s
    ]
    return _STEP.join(kept)


_SAMPLE = """
import org.springframework.web.bind.annotation.RequestParam;
public class Sample {
    public void written(@RequestParam(defaultValue = "0") String page) {}
    public void unwritten(@RequestParam String page) {}
}
"""


def q5_default_value_reaches_bytecode_only_when_written(spring_web: Path) -> str:
    """Compiles a two-method sample against spring-web and reads each method's
    `RuntimeVisibleParameterAnnotations`: the attribute's presence in the class
    file is the test `request_params.default_attr` makes."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "Sample.java"
        source.write_text(_SAMPLE, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-cp", str(spring_web), "-d", tmp, str(source)],
            capture_output=True,
            text=True,
            check=False,
        )
        if javac.returncode != 0:
            raise ProbeError(f"javac Sample.java failed: {javac.stderr.strip()}")
        output = _javap("-v", "Sample", classpath=Path(tmp))
    cells = []
    for method in ("written", "unwritten"):
        block = "\n".join(_method_body(output, f"public void {method}("))
        pairs = re.search(r"RuntimeVisibleParameterAnnotations:\s*parameter 0:\s*0: (\S+)", block)
        cells.append(f"{method}: {pairs.group(1) if pairs else '?'}")
    return _STEP.join(cells)


# --- Q6–Q8: Micronaut (F8; §5b `binder` with no `required_attr`) ----------------


def q6_micronaut_attributes(micronaut_http: Path) -> str:
    cells = []
    for name in ("QueryValue", "Header", "CookieValue"):
        attrs = _abstract_members(
            _javap("-p", f"io.micronaut.http.annotation.{name}", classpath=micronaut_http)
        )
        cells.append(f"@{name}: {', '.join(attrs)}")
    return _STEP.join(cells)


def q7_micronaut_missing_value(micronaut_router: Path, micronaut_core: Path) -> str:
    """What the route match does with an unsatisfied binding, and what the two
    predicates it asks read."""
    routes = _javap(
        "-c", "-p", "io.micronaut.web.router.AbstractRouteMatch", classpath=micronaut_router
    )
    fail = _steps(_method_body(routes, "private void setBindingResultOfFail("))
    fail = [
        s
        for s in fail
        if "isNullable" in s
        or "isOptional" in s
        or "aconst_null" in s
        or "Optional.empty" in s
        or "UnsatisfiedRouteException" in s
        or s == "athrow"
    ]
    element = _javap(
        "-c", "-p", "io.micronaut.core.annotation.AnnotatedElement", classpath=micronaut_core
    )
    nullable = [
        s
        for s in _steps(_method_body(element, "public default boolean isNullable();"))
        if "String " in s or "hasStereotype" in s
    ]
    info = _javap("-c", "-p", "io.micronaut.core.type.TypeInformation", classpath=micronaut_core)
    optional = [
        s
        for s in _steps(_method_body(info, "public default boolean isOptional();"))
        if "class " in s
    ]
    return _STEP.join(
        [
            "AbstractRouteMatch.setBindingResultOfFail: " + _STEP.join(fail),
            "AnnotatedElement.isNullable(): " + _STEP.join(nullable),
            "TypeInformation.isOptional(): " + _STEP.join(optional),
        ]
    )


_MICRONAUT_NULLABLE_MAPPERS = (
    "CoreNullableTransformer",
    "JavaxNullableTransformer",
    "KotlinNullableMapper",
    "JspecifyNullableTransformer",
    "SpotbugsNullableTransformer",
    "AndroidxNullableTransformer",
    "JdtNullableTransformer",
    "ReactorNullableTransformer",
    "ReactivexNullableTransformer",
    "Rxjava3NullableTransformer",
)


def q8_micronaut_nullable_spellings(processor: Path) -> str:
    """The annotation names Micronaut's processor maps onto the `Nullable`
    stereotype `isNullable()` asks for — the set a `@Nullable` parameter must be
    spelled from to bind as optional."""
    cells = []
    for name in _MICRONAUT_NULLABLE_MAPPERS:
        output = _javap(
            "-c", "-p", f"io.micronaut.inject.annotation.internal.{name}", classpath=processor
        )
        literals = [lit for lit in _literals(output.splitlines()) if lit.endswith("Nullable")]
        cells.append(f"{name}: {' -> '.join(dict.fromkeys(literals))}")
    return _STEP.join(cells)


# --- Q9–Q10: JAX-RS and RESTEasy Reactive (F9, A9; §5b `requirement: optional`) --


def q9_jaxrs_attributes(jaxrs_api: Path, common: Path) -> str:
    cells = []
    for name in ("QueryParam", "HeaderParam", "CookieParam", "DefaultValue"):
        attrs = _abstract_members(_javap("-p", f"jakarta.ws.rs.{name}", classpath=jaxrs_api))
        cells.append(f"@{name}: {', '.join(attrs)}")
    for name in ("RestQuery", "RestHeader", "RestCookie"):
        attrs = _abstract_members(
            _javap("-p", f"org.jboss.resteasy.reactive.{name}", classpath=common)
        )
        cells.append(f"@{name}: {', '.join(attrs)}")
    return _STEP.join(cells)


def q10_resteasy_reactive_absent(server: Path) -> str:
    """The three extractors return the request's read verbatim; `handleResult`
    substitutes `defaultValue` for a null and stores the value — no throw."""
    cells = []
    for name, read in (
        ("QueryParamExtractor", "getQueryParameter"),
        ("HeaderParamExtractor", "getHeader"),
        ("CookieParamExtractor", "getCookieParameter"),
    ):
        output = _javap(
            "-c",
            "-p",
            f"org.jboss.resteasy.reactive.server.core.parameters.{name}",
            classpath=server,
        )
        steps = _steps(_method_body(output, "public java.lang.Object extractParameter("))
        cells.append(
            f"{name}.extractParameter: "
            + _STEP.join(s for s in steps if read in s or s == "areturn")
        )
    context = _javap(
        "-c",
        "-p",
        "org.jboss.resteasy.reactive.server.core.ResteasyReactiveRequestContext",
        classpath=server,
    )
    single = _steps_between(
        _method_body(
            context,
            "public java.lang.Object getQueryParameter(java.lang.String, boolean, boolean, java.lang.String);",
        ),
        0,
        34,
    )
    cells.append(
        "getQueryParameter single-valued path: "
        + _STEP.join(s for s in single if "getQueryParam" in s or s == "areturn" or "ifnull" in s)
    )
    handler = _javap(
        "-c", "-p", "org.jboss.resteasy.reactive.server.handlers.ParameterHandler", classpath=server
    )
    result = _steps_between(_method_body(handler, "private void handleResult("), 0, 35)
    cells.append("ParameterHandler.handleResult (offsets 0-35): " + _STEP.join(result))
    return _STEP.join(cells)


# --- Q11–Q12: quarkus-reactive-routes (§5b `requirement: optional`) ---------------


def q11_reactive_routes_attributes(routes: Path) -> str:
    cells = []
    for name in ("Param", "Header"):
        attrs = _abstract_members(_javap("-p", f"io.quarkus.vertx.web.{name}", classpath=routes))
        cells.append(f"@{name}: {', '.join(attrs)}")
    return _STEP.join(cells)


def q12_reactive_routes_generated_read(deployment: Path, vertx: Path) -> str:
    """The accessor the deployment generates for a `@Param`/`@Header` parameter
    and what Vert.x declares about its return."""
    methods = _javap("-c", "-p", "io.quarkus.vertx.web.deployment.Methods", classpath=deployment)
    static_init = _method_body(methods, "static {};")
    cells = []
    for field in ("REQUEST_GET_PARAM", "REQUEST_GET_HEADER", "OPTIONAL_OF_NULLABLE"):
        # The `ldc`s between the previous `putstatic` and this field's own are
        # the `MethodDescriptor.ofMethod(owner, name, returnType, params...)`
        # arguments, in that order.
        end = next(
            i
            for i, line in enumerate(static_init)
            if "putstatic" in line and f"Field {field}:" in line
        )
        start = max((i for i in range(end) if "putstatic" in static_init[i]), default=-1) + 1
        window = static_init[start:end]
        # `anewarray class java/lang/Class` is the varargs array, not an argument.
        owner, *rest = [
            line.split("// class ", 1)[1].strip()
            for line in window
            if "// class " in line and "anewarray" not in line
        ]
        name = _literals(window)[0]
        cells.append(
            f"Methods.{field} = ofMethod(owner {owner}, name {name}, returns {rest[0]}, params {', '.join(rest[1:])})"
        )
    provider = _javap(
        "-c",
        "-p",
        "io.quarkus.vertx.web.deployment.ReactiveRoutesProcessor$ParamAndHeaderProvider",
        classpath=deployment,
    )
    optional = [
        s
        for s in _steps(provider.splitlines())
        if "OPTIONAL_OF_NULLABLE" in s or "DotNames.OPTIONAL" in s
    ]
    cells.append(
        "ParamAndHeaderProvider wraps an Optional parameter: " + _STEP.join(dict.fromkeys(optional))
    )
    for name in ("getParam", "getHeader"):
        output = _javap("-v", "-p", "io.vertx.core.http.HttpServerRequest", classpath=vertx)
        block = "\n".join(
            _method_body(output, f"public default java.lang.String {name}(java.lang.String);")
        )
        annotation = re.search(r"METHOD_RETURN\s*\n\s*(\S+)", block)
        cells.append(
            f"HttpServerRequest.{name}(String) return: @{annotation.group(1) if annotation else '?'}"
        )
    return _STEP.join(cells)


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        key, group, name, requested, jar = spec.split("|")
        artifacts[key] = Artifact(key, group, name, requested, Path(jar))
    javalin = artifacts["javalin"]

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
    rows: list[tuple[str, tuple[Artifact, ...], str]] = [
        (
            "ApiBuilder.staticInstance(): the thread-local field, what it throws with no block open, and a verb's first instruction",
            (javalin,),
            q1_api_builder_guard(javalin.jar),
        ),
        (
            "AbstractNamedValueMethodArgumentResolver.resolveArgument: the null-value branch, DEFAULT_NONE, RequestParam's attributes",
            (artifacts["spring-web"],),
            q2_spring_resolve_argument(artifacts["spring-web"].jar),
        ),
        (
            "MethodParameter.isOptional(): Optional type, an annotation whose simple name is Nullable, the Kotlin delegate",
            (artifacts["spring-core"],),
            q3_spring_is_optional(artifacts["spring-core"].jar),
        ),
        (
            "HeadersRequestCondition.parseExpressions: the two header names it drops (A4)",
            (artifacts["spring-webmvc"],),
            q4_headers_condition_drops_two(artifacts["spring-webmvc"].jar),
        ),
        (
            "javac against spring-web, javap -v: RequestParam's element_value_pairs with and without a written defaultValue",
            (artifacts["spring-web"],),
            q5_default_value_reaches_bytecode_only_when_written(artifacts["spring-web"].jar),
        ),
        (
            "@QueryValue/@Header/@CookieValue attributes (F8)",
            (artifacts["micronaut-http"],),
            q6_micronaut_attributes(artifacts["micronaut-http"].jar),
        ),
        (
            "AbstractRouteMatch.setBindingResultOfFail: nullable → null, Optional → empty, else UnsatisfiedRouteException; what isNullable/isOptional read",
            (artifacts["micronaut-router"], artifacts["micronaut-core"]),
            q7_micronaut_missing_value(
                artifacts["micronaut-router"].jar, artifacts["micronaut-core"].jar
            ),
        ),
        (
            "The annotation spellings Micronaut's processor maps onto the jakarta.annotation.Nullable stereotype",
            (artifacts["micronaut-core-processor"],),
            q8_micronaut_nullable_spellings(artifacts["micronaut-core-processor"].jar),
        ),
        (
            "@QueryParam/@HeaderParam/@CookieParam/@DefaultValue and @RestQuery/@RestHeader/@RestCookie attributes (F9, A9)",
            (artifacts["jaxrs-api"], artifacts["resteasy-reactive-common"]),
            q9_jaxrs_attributes(
                artifacts["jaxrs-api"].jar, artifacts["resteasy-reactive-common"].jar
            ),
        ),
        (
            "RESTEasy Reactive extractors hand the request's read through; ParameterHandler.handleResult substitutes only a defaultValue",
            (artifacts["resteasy-reactive"],),
            q10_resteasy_reactive_absent(artifacts["resteasy-reactive"].jar),
        ),
        (
            "@Param/@Header attributes",
            (artifacts["reactive-routes"],),
            q11_reactive_routes_attributes(artifacts["reactive-routes"].jar),
        ),
        (
            "The read the deployment generates for @Param/@Header, and Vert.x's declared return nullability",
            (artifacts["reactive-routes-deployment"], artifacts["vertx-core"]),
            q12_reactive_routes_generated_read(
                artifacts["reactive-routes-deployment"].jar, artifacts["vertx-core"].jar
            ),
        ),
    ]
    for number, (question, measured, observed) in enumerate(rows, start=1):
        names = ", ".join(f"`{a.group}:{a.name}`" for a in measured)
        versions = ", ".join(dict.fromkeys(a.observed for a in measured))
        print(f"| {number} | {question} | {names} | {versions} | `{observed}` |")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-25 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
