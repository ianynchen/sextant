"""CP-29's measurement half: the Spring Cloud Gateway 5.0.0 property-route surface spec
2026-09-21 §7b reads — the prefix `GatewayProperties` binds under (F6) and whether the
pre-4.2 prefix still binds anywhere in the jar; `PredicateDefinition(String)`'s shortcut
grammar and `RouteDefinition`'s fields (F7); the five predicate factories' `shortcutFieldOrder`
and `shortcutType` with the `Config` each binds into; every predicate factory the jar
declares, by the name the framework derives for it; the three `ShortcutType` normalisers;
how a route's `uri` scheme is handled (`lb`); `HttpMethod.values()` and `valueOf` at
spring-web 6.1.6 with the identity comparison the `Method` predicate makes (F9); and — for
§7a — the `accept`/`contentType` overloads on the three router DSL classes at spring-webflux
and spring-webmvc 6.1.6.

Called by `run.sh`, which resolves the jars; this script downloads nothing. Like CP-16
through CP-28 it reads each jar's own identity out of its own bytes before it measures
anything and refuses to file a cell under a version the archive did not claim
(GUIDELINES §5.4, and CP-5's failure it exists to prevent).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
_STEP = " ; "
_PREDICATE = "org.springframework.cloud.gateway.handler.predicate"
_SUPPORT = "org.springframework.cloud.gateway.support"
_LEGACY_PREFIX = "spring.cloud.gateway.routes"


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


def _javap(*arguments: str, classpath: Path, check: bool = True) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0 and check:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _bodies(output: str) -> list[tuple[str, list[str]]]:
    """`(declaration, instruction lines)` per method of a `javap -p -c` listing."""
    methods: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in output.splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            current = (line.strip().rstrip(";"), [])
            methods.append(current)
        elif current is not None and line.startswith("    "):
            current[1].append(line)
    return methods


def _body(output: str, header: str) -> list[str]:
    for declaration, body in _bodies(output):
        if header in declaration:
            return body
    raise ProbeError(f"no method matching {header!r}")


def _step(line: str) -> str | None:
    match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    # The comment names the member an invoke reaches; an operand with no comment — a
    # `bipush 61`, the `=` the shortcut grammar splits on — is the operand itself.
    comment = operands.split("//", 1)[1].strip() if "//" in operands else operands.strip()
    return f"{match.group(1)} {comment}".strip()


def _steps(body: list[str], keep: tuple[str, ...] = ()) -> list[str]:
    steps = [s for s in (_step(line) for line in body) if s is not None]
    if keep:
        steps = [s for s in steps if any(marker in s for marker in keep)]
    return steps


def _fields(output: str) -> list[str]:
    """Every declared field of a `javap -p` listing, `type name`."""
    found: list[str] = []
    for line in output.splitlines():
        declaration = line.strip().rstrip(";")
        if (
            line.startswith("  ")
            and not line.startswith("    ")
            and "(" not in declaration
            and declaration
            and not declaration.startswith("static {}")
        ):
            tokens = declaration.split()
            while tokens and tokens[0] in (
                "public",
                "private",
                "protected",
                "final",
                "static",
                "volatile",
                "transient",
            ):
                tokens.pop(0)
            found.append(" ".join(tokens))
    return found


def _public_descriptors(output: str, name: str) -> list[str]:
    """Every `descriptor:` following a `public` declaration of `name(`."""
    found: list[str] = []
    lines = output.splitlines()
    for index, line in enumerate(lines[:-1]):
        if (
            line.startswith("  public")
            and re.search(rf"[\s.]{re.escape(name)}\(", line)
            and "descriptor:" in lines[index + 1]
        ):
            found.append(lines[index + 1].split("descriptor:", 1)[1].strip())
    return found


def _entries(jar: Path, suffix: str) -> list[str]:
    with zipfile.ZipFile(jar) as archive:
        return sorted(n for n in archive.namelist() if n.endswith(suffix))


def _entries_carrying(jar: Path, needle: bytes) -> list[str]:
    """Every archive entry whose BYTES carry `needle` — a constant-pool scan that reads
    no class file's structure and so cannot miss a string a `javap -constants` of one
    named class would."""
    with zipfile.ZipFile(jar) as archive:
        return sorted(n for n in archive.namelist() if needle in archive.read(n))


# --- Q1: F6 — the prefix -----------------------------------------------------------


def q1_prefix(gateway: Path) -> str:
    output = _javap(
        "-p",
        "-constants",
        "org.springframework.cloud.gateway.config.GatewayProperties",
        classpath=gateway,
    )
    prefix = next(line.strip().rstrip(";") for line in output.splitlines() if " PREFIX = " in line)
    verbose = _javap(
        "-p", "-v", "org.springframework.cloud.gateway.config.GatewayProperties", classpath=gateway
    ).splitlines()
    at = next(i for i, line in enumerate(verbose) if "ConfigurationProperties(" in line)
    annotation = " ".join(line.strip() for line in verbose[at : at + 3])
    routes = next(line.strip().rstrip(";") for line in output.splitlines() if " routes;" in line)
    return _STEP.join([prefix, annotation, routes])


# --- Q2: F6 — does the pre-4.2 prefix bind anywhere in this jar? ----------------------


def q2_legacy_prefix(gateway: Path) -> str:
    carrying = _entries_carrying(gateway, _LEGACY_PREFIX.encode())
    deprecated = _entries_carrying(gateway, b"DeprecatedConfigurationProperty")
    names = _entries(gateway, ".class")
    suspicious = [
        n for n in names if re.search(r"(Deprecated|Legacy|Compat|Migrat)", n.rsplit("/", 1)[-1])
    ]
    with zipfile.ZipFile(gateway) as archive:
        factories = archive.read("META-INF/spring.factories").decode("utf-8", "replace")
        metadata = json.loads(archive.read("META-INF/spring-configuration-metadata.json"))
    joined = factories.replace("\\\n", "")
    post_processors = next(
        (
            line.split("=", 1)[1].split(",")
            for line in joined.splitlines()
            if line.startswith("org.springframework.boot.EnvironmentPostProcessor=")
        ),
        [],
    )
    route_properties = sorted(
        p["name"] for p in metadata.get("properties", []) if p["name"].endswith(".routes")
    )
    deprecations = sorted(p["name"] for p in metadata.get("properties", []) if p.get("deprecation"))
    post = _javap(
        "-p",
        "-c",
        "-constants",
        "org.springframework.cloud.gateway.config.GatewayEnvironmentPostProcessor",
        classpath=gateway,
    )
    ldc = _steps(_body(post, "postProcessEnvironment("), keep=("ldc",))
    return _STEP.join(
        [
            f"entries carrying `{_LEGACY_PREFIX}`: {carrying or 'none'}",
            f"entries carrying `DeprecatedConfigurationProperty`: {deprecated or 'none'}",
            f"class names matching Deprecated|Legacy|Compat|Migrat: {[n.rsplit('/', 1)[-1] for n in suspicious] or 'none'}",
            f"metadata `*.routes` properties: {route_properties}",
            f"metadata deprecations: {deprecations or 'none'}",
            f"EnvironmentPostProcessor: {post_processors}",
            f"postProcessEnvironment ldc: {ldc}",
        ]
    )


# --- Q3: F7 — PredicateDefinition(String) ---------------------------------------------


def q3_predicate_definition(gateway: Path) -> str:
    output = _javap(
        "-p", "-c", "-constants", f"{_PREDICATE}.PredicateDefinition", classpath=gateway
    )
    body = _body(output, "PredicateDefinition(java.lang.String)")
    kept = _steps(
        body,
        keep=(
            "bipush",
            "indexOf",
            "substring",
            "setName",
            "tokenizeToStringArray",
            "ldc",
            "generateName",
            "Map.put",
            "athrow",
        ),
    )
    fields = _fields(_javap("-p", f"{_PREDICATE}.PredicateDefinition", classpath=gateway))
    names = _javap("-p", "-constants", f"{_SUPPORT}.NameUtils", classpath=gateway)
    prefix = next(
        line.strip().rstrip(";") for line in names.splitlines() if "GENERATED_NAME_PREFIX" in line
    )
    return _STEP.join([f"fields {fields}", prefix, *kept])


# --- Q4: F7 — RouteDefinition ---------------------------------------------------------


def q4_route_definition(gateway: Path) -> str:
    listing = _javap(
        "-p", "org.springframework.cloud.gateway.route.RouteDefinition", classpath=gateway
    )
    output = _javap(
        "-p",
        "-c",
        "-constants",
        "org.springframework.cloud.gateway.route.RouteDefinition",
        classpath=gateway,
    )
    body = _body(output, "RouteDefinition(java.lang.String)")
    kept = _steps(
        body,
        keep=(
            "bipush",
            "indexOf",
            "setId",
            "tokenizeToStringArray",
            "URI.create",
            "setUri",
            'PredicateDefinition."<init>"',
        ),
    )
    return _STEP.join([f"fields {_fields(listing)}", *kept])


# --- Q5: the five factories' shortcut shape and Config ----------------------------------

_FACTORIES = ("Path", "Method", "Header", "Query", "Cookie")


def q5_shortcuts(gateway: Path) -> str:
    cells = []
    for name in _FACTORIES:
        cls = f"{_PREDICATE}.{name}RoutePredicateFactory"
        output = _javap("-p", "-c", "-constants", cls, classpath=gateway)
        order = _steps(_body(output, "shortcutFieldOrder()"), keep=("ldc",))
        declared = any("shortcutType()" in d for d, _ in _bodies(output))
        kind = (
            _steps(_body(output, "shortcutType()"), keep=("getstatic",))
            if declared
            else ["inherited"]
        )
        config = _fields(_javap("-p", f"{cls}$Config", classpath=gateway))
        cells.append(
            f"{name}: shortcutFieldOrder {[s.split('String ', 1)[1] for s in order]} / "
            f"shortcutType {[k.rsplit('.', 1)[-1].split(':')[0] for k in kind]} / Config {config}"
        )
    interface = _javap(
        "-p", "-c", "-constants", f"{_SUPPORT}.ShortcutConfigurable", classpath=gateway
    )
    default = _steps(_body(interface, "shortcutType()"), keep=("getstatic",))
    cells.append(
        f"ShortcutConfigurable default shortcutType: {[k.rsplit('.', 1)[-1].split(':')[0] for k in default]}"
    )
    return _STEP.join(cells)


# --- Q6: every predicate factory, by the name the framework derives --------------------


def q6_factory_names(gateway: Path) -> str:
    names = [
        n.rsplit("/", 1)[-1][: -len(".class")]
        for n in _entries(gateway, "RoutePredicateFactory.class")
        if "/handler/predicate/" in n and "$" not in n
    ]
    concrete = [
        n for n in names if n not in ("RoutePredicateFactory", "AbstractRoutePredicateFactory")
    ]
    rule = _javap("-p", "-c", "-constants", f"{_SUPPORT}.NameUtils", classpath=gateway)
    steps = _steps(
        _body(rule, "normalizeRoutePredicateName(java.lang.Class"), keep=("invoke", "ldc")
    )
    derived = [n[: -len("RoutePredicateFactory")] for n in concrete]
    return _STEP.join([f"names {derived}", f"normalizeRoutePredicateName: {steps}"])


# --- Q7: the three ShortcutType normalisers ----------------------------------------------


def q7_shortcut_types(gateway: Path) -> str:
    listing = _javap("-p", f"{_SUPPORT}.ShortcutConfigurable$ShortcutType", classpath=gateway)
    members = [
        line.strip().split()[-1].rstrip(";")
        for line in listing.splitlines()
        if "public static final" in line and "ShortcutType " in line and "[]" not in line
    ]
    cells = [f"members {members}"]
    for index, member in enumerate(members, start=1):
        output = _javap(
            "-p",
            "-c",
            "-constants",
            f"{_SUPPORT}.ShortcutConfigurable$ShortcutType${index}",
            classpath=gateway,
        )
        kept = _steps(
            _body(output, "normalize("),
            keep=(
                "normalizeKey",
                "shortcutFieldOrder",
                "ldc",
                "equalsIgnoreCase",
                "subList",
                "Collectors.toList",
                "Map.put",
            ),
        )
        cells.append(f"{member}: {kept}")
    key = _javap("-p", "-c", "-constants", f"{_SUPPORT}.ShortcutConfigurable", classpath=gateway)
    cells.append(
        f"normalizeKey: {_steps(_body(key, 'normalizeKey('), keep=('ldc', 'startsWith', 'shortcutFieldOrder', 'List.get'))}"
    )
    return _STEP.join(cells)


# --- Q8: the uri scheme -------------------------------------------------------------


def q8_uri_scheme(gateway: Path) -> str:
    lb = _javap(
        "-p",
        "-c",
        "-constants",
        "org.springframework.cloud.gateway.filter.ReactiveLoadBalancerClientFilter",
        classpath=gateway,
    )
    filter_steps = _steps(
        _body(lb, "filter(org.springframework.web.server.ServerWebExchange"),
        keep=("ldc", "getScheme", "String.equals", "getHost"),
    )
    route = _javap(
        "-p",
        "-c",
        "-constants",
        "org.springframework.cloud.gateway.filter.RouteToRequestUrlFilter",
        classpath=gateway,
    )
    regex = next(
        line.strip().rstrip(";")
        for line in route.splitlines()
        if "SCHEME_REGEX" in line and "=" in line
    )
    route_steps = _steps(
        _body(route, "filter(org.springframework.web.server.ServerWebExchange"),
        keep=("ldc", "getScheme", "hasAnotherScheme", "getSchemeSpecificPart"),
    )
    return _STEP.join(
        [
            f"ReactiveLoadBalancerClientFilter.filter: {filter_steps}",
            regex,
            f"RouteToRequestUrlFilter.filter: {route_steps}",
        ]
    )


# --- Q9: F9 — HttpMethod at spring-web 6.1.6 -------------------------------------------


def q9_http_method(web: Path, gateway: Path) -> str:
    output = _javap("-p", "-c", "-constants", "org.springframework.http.HttpMethod", classpath=web)
    values = [
        s.split("String ", 1)[1]
        for s in _steps(_body(output, "static {}"), keep=("ldc",))
        if "String " in s
    ]
    value_of = _steps(
        _body(output, "valueOf(java.lang.String)"),
        keep=("String.equals", "getstatic", "new class", '"<init>"'),
    )
    compare = _javap("-p", "-c", f"{_PREDICATE}.MethodRoutePredicateFactory$1", classpath=gateway)
    test = _steps(_body(compare, "lambda$test$0("))
    return _STEP.join(
        [
            f"values() {values}",
            f"valueOf: {len([s for s in value_of if 'String.equals' in s])} equals arms then {[s for s in value_of if 'new class' in s]}",
            f"MethodRoutePredicateFactory$1.lambda$test$0: {test}",
        ]
    )


# --- Q10: §7a — the media overloads on the three DSL classes ----------------------------

_DSL_CLASSES = (
    ("webflux", "org.springframework.web.reactive.function.server.RouterFunctionDsl"),
    ("webflux", "org.springframework.web.reactive.function.server.CoRouterFunctionDsl"),
    ("webmvc", "org.springframework.web.servlet.function.RouterFunctionDsl"),
)


def q10_media_overloads(artifacts: dict[str, Artifact]) -> str:
    cells = []
    for key, cls in _DSL_CLASSES:
        output = _javap("-p", "-s", cls, classpath=artifacts[key].jar)
        for name in ("accept", "contentType"):
            cells.append(f"{cls.rsplit('.', 1)[-1]}.{name}: {_public_descriptors(output, name)}")
    return _STEP.join(cells)


# --- Q11: does a route with no `Method=` predicate constrain the method? ----------------


def q11_no_method_predicate(gateway: Path) -> str:
    """What builds a `Route` from a definition, and whether anything there is a method.

    The question behind the fan-out: a route declaring only `Path=` — which is every route
    `spring-petclinic-api-gateway` writes — serves WHICH methods? Fanning a route out over
    all eight is only honest if all eight really reach it, and the counter-example is in
    this repository already: `RouterFunctions.resources(...)` is verb-less too and serves
    GET, HEAD and OPTIONS only, so fanning THAT out publishes five routes nobody can call
    (spec 2026-09-21 §0b A1).

    Two readings, from `RouteDefinitionRouteLocator` — the class that turns a definition
    into a `Route`: what `combinePredicates` does with an EMPTY predicate list, and how
    many times `HttpMethod` is mentioned anywhere in the class. A zero there is the answer:
    nothing in route construction can constrain a method it never names.
    """
    locator = "org.springframework.cloud.gateway.route.RouteDefinitionRouteLocator"
    body = _body(_javap("-p", "-c", locator, classpath=gateway), "combinePredicates(")
    empty_arm = _steps(body, keep=("isEmpty", "invokedynamic", "AsyncPredicate.from"))
    mentions = _javap("-p", "-v", locator, classpath=gateway).count("HttpMethod")
    return _STEP.join(
        [
            f"combinePredicates empty-list arm: {empty_arm}",
            f"HttpMethod mentions in the whole class: {mentions}",
        ]
    )


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        key, group, name, requested, path = spec.split("|")
        artifacts[key] = Artifact(key, group, name, requested, Path(path))
    gateway, web = artifacts["gateway"], artifacts["web"]

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
        "11",
        "does a route declaring only `Path=` constrain the method at all",
        gateway,
        q11_no_method_predicate(gateway.jar),
    )
    row(
        "1",
        "F6: `GatewayProperties.PREFIX`, its `@ConfigurationProperties`, the `routes` field",
        gateway,
        q1_prefix(gateway.jar),
    )
    row(
        "2",
        "F6: does `spring.cloud.gateway.routes` bind anywhere in this jar — byte scan, metadata, post-processors",
        gateway,
        q2_legacy_prefix(gateway.jar),
    )
    row(
        "3",
        "F7: `PredicateDefinition` fields and `PredicateDefinition(String)`'s grammar",
        gateway,
        q3_predicate_definition(gateway.jar),
    )
    row(
        "4",
        "F7: `RouteDefinition` fields and `RouteDefinition(String)`'s grammar",
        gateway,
        q4_route_definition(gateway.jar),
    )
    row(
        "5",
        "the five factories: `shortcutFieldOrder`, `shortcutType`, `Config` fields",
        gateway,
        q5_shortcuts(gateway.jar),
    )
    row(
        "6",
        "every predicate factory the jar declares, by the name the framework derives",
        gateway,
        q6_factory_names(gateway.jar),
    )
    row(
        "7",
        "`ShortcutType`'s three normalisers and `normalizeKey`",
        gateway,
        q7_shortcut_types(gateway.jar),
    )
    row(
        "8",
        "the `uri` scheme: `lb` and the request-URL filter",
        gateway,
        q8_uri_scheme(gateway.jar),
    )
    row(
        "9",
        "F9: `HttpMethod.values()`, `valueOf(String)`, and how `Method` compares",
        web,
        q9_http_method(web.jar, gateway.jar),
    )
    row(
        "10",
        "§7a: `accept`/`contentType` overloads on the three router DSL classes",
        artifacts["webflux"],
        q10_media_overloads(artifacts),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-29 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
