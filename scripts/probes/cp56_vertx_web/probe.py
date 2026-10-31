"""CP-56: the shapes Vert.x Web's server and WebClient take — which Router, Route, WebClient,
HttpRequest, WebClientOptions and RequestOptions methods exist and with what descriptor, every
method that returns `this` per owner and version, what RouteState does with an empty method set and
a null path, what RouteImpl and RouterImpl refuse, where the WebClient takes its default host and
port from WebClientOptions and when a request's own host or port wins, the HttpMethod constants, the
same names on the RxJava 3 and Mutiny wrappers, and the bytecode javac 21 writes for the call forms
a route or a request is written in. Every cell is read off the jars and the probe module's class
file with `javap -v -p -c`; nothing runs. The version in each column is the jar's own manifest.
Prints the observation table `cp56_vertx_web.md` carries."""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _jvm_annotations import (
    ClassFile,
    Instruction,
    ProbeError,
    body,
    classes,
    identity,
    jar_at,
    lambda_targets,
)

VERSIONS = ["4.5.10", "5.0.0", "5.2.1"]
# The Mutiny wrappers wrap the Vert.x release their parent pom names: 3.23.1 wraps 4.5.34,
# 4.0.2 wraps 5.1.8 (`vertx.version` in `smallrye-mutiny-vertx-bindings-projects`).
MUTINY_VERSIONS = ["3.23.1", "4.0.2"]
MUTINY_COLUMNS = [f"mutiny {v}" for v in MUTINY_VERSIONS]
COLUMNS = [*VERSIONS, *MUTINY_COLUMNS]
# The core column each Mutiny column is compared with when a row asks what the wrapper adds:
# the nearest Vert.x release this record reads.
MUTINY_AGAINST = {"mutiny 3.23.1": "4.5.10", "mutiny 4.0.2": "5.2.1"}

WEB = ("io.vertx", "vertx-web")
CLIENT = ("io.vertx", "vertx-web-client")
COMMON = ("io.vertx", "vertx-web-common")
CORE = ("io.vertx", "vertx-core")
RX = ("io.vertx", "vertx-rx-java3")
M_WEB = ("io.smallrye.reactive", "smallrye-mutiny-vertx-web")
M_CLIENT = ("io.smallrye.reactive", "smallrye-mutiny-vertx-web-client")

# Which artifacts a column reads, in the order a class is looked up in them.
COLUMN_ARTIFACTS = {
    **{version: [WEB, CLIENT, COMMON, CORE, RX] for version in VERSIONS},
    **{column: [M_WEB, M_CLIENT] for column in MUTINY_COLUMNS},
}
REQUESTED = {
    **{v: v for v in VERSIONS},
    **{column: v for column, v in zip(MUTINY_COLUMNS, MUTINY_VERSIONS, strict=True)},
}

ROUTER = "io.vertx.ext.web.Router"
ROUTE = "io.vertx.ext.web.Route"
ROUTING_CONTEXT = "io.vertx.ext.web.RoutingContext"
ROUTER_IMPL = "io.vertx.ext.web.impl.RouterImpl"
ROUTE_IMPL = "io.vertx.ext.web.impl.RouteImpl"
MESSAGE_CONSUMER = "io.vertx.core.eventbus.MessageConsumer"
MESSAGE_CONSUMER_IMPL = "io.vertx.core.eventbus.impl.MessageConsumerImpl"
ROUTE_STATE = "io.vertx.ext.web.impl.RouteState"
WEB_CLIENT = "io.vertx.ext.web.client.WebClient"
WEB_CLIENT_BASE = "io.vertx.ext.web.client.impl.WebClientBase"
HTTP_REQUEST = "io.vertx.ext.web.client.HttpRequest"
HTTP_REQUEST_IMPL = "io.vertx.ext.web.client.impl.HttpRequestImpl"
CLIENT_URI = "io.vertx.ext.web.client.impl.ClientUri"
WEB_CLIENT_OPTIONS = "io.vertx.ext.web.client.WebClientOptions"
WEB_CLIENT_CONFIG = "io.vertx.ext.web.client.WebClientConfig"
REQUEST_OPTIONS = "io.vertx.core.http.RequestOptions"
HTTP_METHOD = "io.vertx.core.http.HttpMethod"
SHAPES = "probe.Shapes"

VERBS = ["get", "post", "put", "delete", "patch", "head", "options", "trace", "connect"]
CLIENT_VERBS = ["get", "post", "put", "delete", "patch", "head"]

ROUTER_NAMES = [
    "router",
    "route",
    "routeWithRegex",
    "mountSubRouter",
    *VERBS,
    *[f"{verb}WithRegex" for verb in VERBS],
]
ROUTE_NAMES = [
    "method",
    "path",
    "pathRegex",
    "produces",
    "consumes",
    "virtualHost",
    "order",
    "last",
    "setName",
    "useNormalizedPath",
    "putMetadata",
    "handler",
    "blockingHandler",
    "respond",
    "failureHandler",
    "subRouter",
    "disable",
    "enable",
    "remove",
]
WEB_CLIENT_NAMES = [
    "create",
    "wrap",
    *CLIENT_VERBS,
    *[f"{verb}Abs" for verb in CLIENT_VERBS],
    "request",
    "requestAbs",
]
HTTP_REQUEST_NAMES = [
    "method",
    "uri",
    "host",
    "port",
    "ssl",
    "putHeader",
    "addQueryParam",
    "setQueryParam",
    "setTemplateParam",
    "timeout",
    "basicAuthentication",
    "bearerTokenAuthentication",
    "followRedirects",
    "expect",
    "as",
    "send",
    "sendJson",
    "sendJsonObject",
    "sendBuffer",
    "sendForm",
    "sendMultipartForm",
    "sendStream",
]
WEB_CLIENT_OPTIONS_NAMES = [
    "setDefaultHost",
    "setDefaultPort",
    "setSsl",
    "getDefaultHost",
    "getDefaultPort",
]
REQUEST_OPTIONS_NAMES = [
    "setHost",
    "setPort",
    "setURI",
    "setAbsoluteURI",
    "setSsl",
    "setServer",
    "setMethod",
    "getHost",
    "getPort",
    "getURI",
    "isSsl",
]

# The same classes on the wrappers: the package prefix is all that changes.
WRAPPERS = {"rxjava3": "io.vertx.rxjava3", "mutiny": "io.vertx.mutiny"}


def wrapped(name: str, prefix: str) -> str:
    return name.replace("io.vertx.", f"{prefix}.", 1)


# --- jar access ---------------------------------------------------------------------------------


@dataclass(eq=False)
class Method:
    name: str
    descriptor: str
    flags: str
    code: list[Instruction]

    @property
    def is_static(self) -> bool:
        return "ACC_STATIC" in self.flags

    @property
    def is_abstract(self) -> bool:
        return "ACC_ABSTRACT" in self.flags

    @property
    def is_bridge(self) -> bool:
        return "ACC_BRIDGE" in self.flags or "ACC_SYNTHETIC" in self.flags


_STEP = re.compile(r"^\s+(\d+): ([a-z]\w*)\s*([^/]*?)\s*(?://\s*(.*))?$")
_HEADER = re.compile(r"^  \S.*;$")


def parse_methods(cls: ClassFile) -> list[Method]:
    """Every method of a `javap -v -p -c` listing: name, descriptor, flags, instructions."""
    lines = cls.text.splitlines()
    simple = cls.name.rsplit(".", 1)[-1].rsplit("$", 1)[-1]
    found: list[Method] = []
    in_body = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "{":
            in_body = True
        elif line == "}":
            in_body = False
        elif (
            in_body
            and _HEADER.match(line)
            and "(" in line
            and i + 1 < len(lines)
            and "descriptor:" in lines[i + 1]
        ):
            header = line.strip()
            descriptor = lines[i + 1].split("descriptor:", 1)[1].strip()
            flags = lines[i + 2].strip() if "flags:" in lines[i + 2] else ""
            if header == "static {};":
                name = "<clinit>"
            else:
                name = re.search(r"([\w$]+)\(", header).group(1)  # type: ignore[union-attr]
                if name == simple and descriptor.endswith(")V") and " void " not in header:
                    name = "<init>"
            code: list[Instruction] = []
            j = i + 2
            while j < len(lines) and not re.match(r"^  \S", lines[j]) and lines[j] != "}":
                step = _STEP.match(lines[j])
                if step:
                    code.append(
                        Instruction(
                            int(step.group(1)), step.group(2), step.group(3), step.group(4) or ""
                        )
                    )
                j += 1
            found.append(Method(name, descriptor, flags, code))
            i = j
            continue
        i += 1
    return found


class Repo:
    """The jars of each column, each version read from the jar's own manifest."""

    def __init__(self) -> None:
        self.jars: dict[str, list[tuple[tuple[str, str], Path, str]]] = {}
        self.cache: dict[tuple[str, str], ClassFile | None] = {}
        self.methods_cache: dict[tuple[str, str], list[Method]] = {}
        for column, artifacts in COLUMN_ARTIFACTS.items():
            found = []
            for artifact in artifacts:
                jar = jar_at(artifact[0], artifact[1], REQUESTED[column])
                if jar is None:
                    continue
                stated, _ = identity(jar, REQUESTED[column])
                found.append((artifact, jar, stated))
            self.jars[column] = found

    def cls(self, column: str, name: str) -> ClassFile | None:
        key = (column, name)
        if key not in self.cache:
            self.cache[key] = None
            for _, jar, _ in self.jars[column]:
                try:
                    if name.replace(".", "/") + ".class" not in _members(jar):
                        continue
                    self.cache[key] = classes(jar, [name])[name]
                    break
                except ProbeError:
                    continue
        return self.cache[key]

    def methods(self, column: str, name: str) -> list[Method] | None:
        cls = self.cls(column, name)
        if cls is None:
            return None
        key = (column, name)
        if key not in self.methods_cache:
            self.methods_cache[key] = parse_methods(cls)
        return self.methods_cache[key]


_MEMBERS: dict[Path, set[str]] = {}


def _members(jar: Path) -> set[str]:
    if jar not in _MEMBERS:
        import zipfile

        with zipfile.ZipFile(jar) as archive:
            _MEMBERS[jar] = set(archive.namelist())
    return _MEMBERS[jar]


# --- small readers -----------------------------------------------------------------------------

_PRIMITIVES = {
    "I": "int",
    "J": "long",
    "Z": "boolean",
    "D": "double",
    "F": "float",
    "B": "byte",
    "C": "char",
    "S": "short",
    "V": "void",
}


def descriptor_parts(descriptor: str) -> tuple[list[str], str]:
    """`(Ljava/lang/String;I)Lio/vertx/X;` -> (["java/lang/String", "I"], "io/vertx/X")."""
    arguments, _, result = descriptor[1:].partition(")")
    parts: list[str] = []
    i = 0
    while i < len(arguments):
        start = i
        while arguments[i] == "[":
            i += 1
        i = arguments.index(";", i) + 1 if arguments[i] == "L" else i + 1
        parts.append(arguments[start:i])
    return parts, result


def simple_type(descriptor_type: str) -> str:
    dimensions = len(descriptor_type) - len(descriptor_type.lstrip("["))
    core = descriptor_type.lstrip("[")
    name = core[1:-1].rsplit("/", 1)[-1] if core.startswith("L") else _PRIMITIVES[core]
    return name + "[]" * dimensions


def signature(method: Method) -> str:
    """`name(SimpleType,SimpleType)`, for naming an overload in a list."""
    parameters, _ = descriptor_parts(method.descriptor)
    return f"{method.name}({','.join(simple_type(p) for p in parameters)})"


def returns(method: Method) -> str:
    return descriptor_parts(method.descriptor)[1]


def returns_this(method: Method) -> str:
    """ "this" when every `areturn` of the body is preceded by `aload_0`, "some" when only some
    are, "" when none is (or the body returns no reference)."""
    code = method.code
    areturns = [i for i, step in enumerate(code) if step.opcode == "areturn"]
    if not areturns:
        return ""
    loaded = [i > 0 and code[i - 1].opcode == "aload_0" for i in areturns]
    return "this" if all(loaded) else "some" if any(loaded) else ""


_INVOKE = re.compile(r"(?:Interface)?Method (?:(\S+?)\.)?\"?([<\w$>]+)\"?:(\S+)")


def invocations(code: list[Instruction]) -> list[tuple[str, str, str]]:
    """(owner as dotted name, method name, descriptor) of each call, in order."""
    found = []
    for step in code:
        match = _INVOKE.match(step.comment)
        if step.opcode.startswith("invoke") and match and step.opcode != "invokedynamic":
            owner = (match.group(1) or "").replace("/", ".")
            found.append((owner, match.group(2), match.group(3)))
    return found


def reads(code: list[Instruction], member: str) -> bool:
    return any(owner_name == member for _, owner_name, _ in invocations(code))


def short(dotted: str) -> str:
    return dotted.rsplit(".", 1)[-1]


def named(column_methods: list[Method], name: str) -> list[Method]:
    return [m for m in column_methods if m.name == name and not m.is_bridge]


def superclass(cls: ClassFile) -> str:
    """The class named after `extends` in a class declaration ("" for an interface or Object)."""
    declaration = re.sub(r"<[^<>]*>", "", cls.declaration)
    if " interface " in declaration:
        return ""
    match = re.search(r"\bextends ([\w.$]+)", declaration)
    return match.group(1) if match else ""


def find_method(repo: "Repo", column: str, owner: str, name: str, descriptor: str):  # type: ignore[no-untyped-def]
    """(method, class that declares it), looking up the superclass chain; (None, "") when not found."""
    for _ in range(10):
        if not owner:
            break
        methods = repo.methods(column, owner)
        if methods is None:
            break
        for m in methods:
            if m.name == name and m.descriptor == descriptor:
                return m, owner
        cls = repo.cls(column, owner)
        owner = superclass(cls) if cls else ""
    return None, ""


def classify(repo: "Repo", column: str, owner: str, method: Method, depth: int = 0) -> str:
    """ "this" when every return is `aload_0; [checkcast;] areturn`; "via" when every return is
    the result (through an optional checkcast) of a call to a method of the same class chain
    that itself answers `this` (or to an abstract method returning the same type, which an
    implementation answers); "some" when only some returns are `this`; "" otherwise."""
    code = method.code
    areturns = [i for i, step in enumerate(code) if step.opcode == "areturn"]
    if not areturns or depth > 6:
        return ""
    kinds = []
    for i in areturns:
        j = i - 1
        while j >= 0 and code[j].opcode == "checkcast":
            j -= 1
        step = code[j]
        if step.opcode == "aload_0":
            kinds.append("this")
            continue
        match = _INVOKE.match(step.comment)
        if not (step.opcode.startswith("invoke") and match and step.opcode != "invokedynamic"):
            kinds.append("")
            continue
        target_owner = (match.group(1) or owner).replace("/", ".")
        callee, _ = find_method(repo, column, target_owner, match.group(2), match.group(3))
        own = target_owner == owner or target_owner in lineage(repo, column, owner)
        if callee is None or not own or callee.is_static:
            kinds.append("")
        elif callee.is_abstract:
            kinds.append("via")
        else:
            kinds.append("via" if classify(repo, column, target_owner, callee, depth + 1) else "")
    if all(k == "this" for k in kinds):
        return "this"
    if all(k in ("this", "via") for k in kinds):
        return "via"
    return "some" if any(kinds) else ""


def lineage(repo: "Repo", column: str, owner: str) -> list[str]:
    """The superclass chain of a class, nearest first."""
    chain = []
    for _ in range(10):
        cls = repo.cls(column, owner)
        owner = superclass(cls) if cls else ""
        if not owner:
            break
        chain.append(owner)
    return chain


# --- the table -----------------------------------------------------------------------------------

ROWS: list[tuple[int, str, str, dict[str, str]]] = []
GAP = "–"


def emit(question: str, artifact: str, cells: dict[str, str]) -> None:
    """One row. A cell identical to an earlier column's says so instead of repeating itself."""
    seen: dict[str, str] = {}
    out: dict[str, str] = {}
    for column in COLUMNS:
        text = cells.get(column, GAP)
        if text != GAP and len(text) > 30 and text in seen:
            out[column] = f"same as {seen[text]}"
        else:
            out[column] = text
            if text != GAP:
                seen.setdefault(text, column)
    ROWS.append((len(ROWS) + 1, question, artifact, out))


def render() -> str:
    header = "| # | question | artifact | " + " | ".join(COLUMNS) + " |"
    divider = "|---|---|---|" + "---|" * len(COLUMNS)
    lines = [header, divider]
    for number, question, artifact, cells in ROWS:
        body_cells = " | ".join(cells[column].replace("|", "\\|") for column in COLUMNS)
        lines.append(f"| {number} | {question} | {artifact} | {body_cells} |")
    return "\n".join(lines)


def per_column(repo: Repo, owner: str, fn) -> dict[str, str]:  # type: ignore[no-untyped-def]
    cells: dict[str, str] = {}
    for column in COLUMNS:
        found = repo.methods(column, owner)
        if found is not None:
            cells[column] = fn(found)
    return cells


def descriptors_of(methods: list[Method], name: str) -> str:
    found = sorted(m.descriptor for m in named(methods, name))
    return "; ".join(f"`{d}`" for d in found) if found else "absent"


def descriptors_in(repo: Repo, column: str, owner: str, name: str) -> str:
    """The descriptors of `name` declared by `owner`; failing that, those of the nearest
    superclass that declares it, said to be inherited."""
    declared = descriptors_of(repo.methods(column, owner) or [], name)
    if declared != "absent":
        return declared
    for ancestor in lineage(repo, column, owner):
        inherited = descriptors_of(repo.methods(column, ancestor) or [], name)
        if inherited != "absent":
            return f"not declared; inherited from `{short(ancestor)}`: {inherited}"
    return "absent"


# --- the groups ---------------------------------------------------------------------------------


def group_identity(repo: Repo) -> None:
    for column in COLUMNS:
        for artifact, _, stated in repo.jars[column]:
            print(f"- {column}: {artifact[0]}:{artifact[1]} states {stated}", file=sys.stderr)


def group_a(repo: Repo) -> None:
    """(a) the methods the spec names, with descriptors."""
    owners = [
        (ROUTER, ROUTER_NAMES),
        (ROUTE, ROUTE_NAMES),
        (WEB_CLIENT, WEB_CLIENT_NAMES),
        (HTTP_REQUEST, HTTP_REQUEST_NAMES),
        (WEB_CLIENT_OPTIONS, WEB_CLIENT_OPTIONS_NAMES),
        (WEB_CLIENT_CONFIG, WEB_CLIENT_OPTIONS_NAMES),
        (REQUEST_OPTIONS, REQUEST_OPTIONS_NAMES),
    ]
    for owner, names in owners:
        for name in names:
            emit(
                f"descriptors of `{short(owner)}.{name}` (a)",
                f"`{owner}`",
                {
                    c: descriptors_in(repo, c, owner, name)
                    for c in COLUMNS
                    if repo.methods(c, owner) is not None
                },
            )


def group_b(repo: Repo) -> None:
    """(b) every method returning `this`, per owner and version."""
    owners = [
        ROUTE_IMPL,
        HTTP_REQUEST_IMPL,
        WEB_CLIENT_OPTIONS,
        WEB_CLIENT_CONFIG,
        REQUEST_OPTIONS,
        *[wrapped(o, p) for p in WRAPPERS.values() for o in (ROUTE, HTTP_REQUEST)],
    ]
    for owner in owners:

        def listing(column: str, owner: str = owner) -> str:
            methods = repo.methods(column, owner) or []
            # Private methods answer their receiver too (Mutiny's `handler` returns the result of a
            # private `__handler`) but no caller can name one, so they are not listed.
            mine = [
                m
                for m in methods
                if not m.is_static
                and not m.is_bridge
                and "ACC_PRIVATE" not in m.flags
                and m.name != "<init>"
            ]
            kinds = {m: classify(repo, column, owner, m) for m in mine}
            names = {
                kind: sorted({signature(m) for m, k in kinds.items() if k == kind})
                for kind in ("this", "via", "some")
            }
            text = (
                f"**{len(names['this'])} + {len(names['via'])}**: "
                f"{len(names['this'])} return `this` directly: "
                + ", ".join(f"`{n}`" for n in names["this"])
            )
            if names["via"]:
                text += (
                    f"; {len(names['via'])} return the result of a call to a method of the same "
                    "class that returns `this`: " + ", ".join(f"`{n}`" for n in names["via"])
                )
            if names["some"]:
                text += "; returns this on some paths only: " + ", ".join(
                    f"`{n}`" for n in names["some"]
                )
            return text

        cells = {c: listing(c) for c in COLUMNS if repo.methods(c, owner) is not None}
        emit(
            f"every method of `{short(owner)}`"
            + (
                " (rxjava3 wrapper)"
                if "rxjava3" in owner
                else " (mutiny wrapper)"
                if "mutiny" in owner
                else ""
            )
            + " that answers its own receiver, directly or through another such call, counted (b)",
            f"`{owner}`",
            cells,
        )

    # The interfaces the caller's static type usually is: what they declare to return their own
    # type, and whether the implementation answers `this` for each abstract one.
    for interface, implementation in ((ROUTE, ROUTE_IMPL), (HTTP_REQUEST, HTTP_REQUEST_IMPL)):
        emit_interface_listing(repo, interface, implementation)

    # WebClientOptions: setters it inherits and does not override. Called on a WebClientOptions
    # they answer the SUPERCLASS type, so a chain typed through them leaves WebClientOptions.
    def inherited(column: str) -> str:
        own = repo.methods(column, WEB_CLIENT_OPTIONS) or []
        overridden = {
            (m.name, tuple(descriptor_parts(m.descriptor)[0])) for m in own if not m.is_bridge
        }
        found = []
        for ancestor in lineage(repo, column, WEB_CLIENT_OPTIONS):
            for m in repo.methods(column, ancestor) or []:
                if m.is_static or m.is_bridge or m.name == "<init>" or m.is_abstract:
                    continue
                key = (m.name, tuple(descriptor_parts(m.descriptor)[0]))
                if key in overridden or not classify(repo, column, ancestor, m):
                    continue
                found.append(f"{short(ancestor)}.{signature(m)}")
        return f"**{len(found)}**: " + (", ".join(f"`{n}`" for n in sorted(found)) or "none")

    emit(
        "setters `WebClientOptions` inherits without overriding that answer their receiver (b)",
        f"`{WEB_CLIENT_OPTIONS}`",
        {c: inherited(c) for c in VERSIONS},
    )


def interface_listing(repo: Repo, column: str, interface: str, implementation: str) -> str:
    """What `interface` declares to return its own type, abstract or default, and whether
    `implementation` and the defaults answer the receiver (b)."""
    declared = repo.methods(column, interface) or []
    own = [
        m
        for m in declared
        if not m.is_static and not m.is_bridge and returns(m) == f"L{interface.replace('.', '/')};"
    ]
    impl = repo.methods(column, implementation) or []
    answers = {
        (m.name, m.descriptor)
        for m in impl
        if not m.is_bridge and classify(repo, column, implementation, m)
    }
    abstract = sorted({signature(m) for m in own if m.is_abstract})
    defaults = sorted({signature(m) for m in own if not m.is_abstract})
    unanswered = sorted(
        {signature(m) for m in own if m.is_abstract and (m.name, m.descriptor) not in answers}
    )
    default_this = sorted(
        {signature(m) for m in own if not m.is_abstract and classify(repo, column, interface, m)}
    )
    return (
        f"**{len(abstract)} + {len(defaults)}** declared to return `{short(interface)}`: "
        f"{len(abstract)} abstract: "
        + ", ".join(f"`{n}`" for n in abstract)
        + f"; the implementation does not answer `this` for: {', '.join(f'`{n}`' for n in unanswered) or 'none'}"
        + f"; {len(defaults)} default: "
        + (", ".join(f"`{n}`" for n in defaults) or "none")
        + f"; of those, answering the result of a self-returning call: {', '.join(f'`{n}`' for n in default_this) or 'none'}"
    )


def emit_interface_listing(repo: Repo, interface: str, implementation: str) -> None:
    emit(
        f"every method `{short(interface)}` declares to return `{short(interface)}`, abstract or default, "
        f"and whether `{short(implementation)}` and the defaults answer the receiver (b)",
        f"`{interface}`",
        {
            c: interface_listing(repo, c, interface, implementation)
            for c in COLUMNS
            if repo.methods(c, interface) is not None
        },
    )


def group_b_event_bus(repo: Repo) -> None:
    """(b) for the event bus's `MessageConsumer`, which `vertx-eventbus-chain.yml` walks: added
    after (h) so every earlier row keeps its number (Vert.x plan, Task 8)."""
    emit_interface_listing(repo, MESSAGE_CONSUMER, MESSAGE_CONSUMER_IMPL)


HTTP_CLIENT_IMPL = "io.vertx.core.http.impl.HttpClientImpl"


def _local(step: Instruction) -> str:
    """The local a load or store names: `astore_2` and `astore 2` both name local 2."""
    return step.opcode.rsplit("_", 1)[-1] if "_" in step.opcode else step.operand


def group_e_server(repo: Repo) -> None:
    """(e) where a request built with a `SocketAddress` goes: what the request hands
    `RequestOptions.setServer` at send time, and what the core client does with that server.
    Added after (h) and the event bus's (b) so every earlier row keeps its number (Vert.x
    plan, Task 12 review)."""

    def server_handed_on(methods: list[Method]) -> str:
        chosen = [m for m in methods if m.name == "buildRequestOptions"]
        if not chosen:
            return "absent"
        code = chosen[0].code
        found = []
        for i, step in enumerate(code):
            if "RequestOptions.setServer:" not in step.comment or i == 0:
                continue
            given = code[i - 1]
            source = (
                given.comment.removeprefix("Field ")
                if given.opcode == "getfield"
                else given.comment.split("Method ", 1)[-1].split(":")[0]
                if given.opcode.startswith("invoke")
                else f"{given.opcode} {given.operand}".strip()
            )
            found.append(
                f"@{step.offset} `setServer({descriptor_parts(step.comment.split(':', 1)[1])[0][0].strip('L;').rsplit('/', 1)[-1]})`"
                f" is handed `{source}`"
            )
        return "; ".join(found) or "NOT FOUND"

    emit(
        "`HttpRequestImpl.buildRequestOptions`: what it hands `RequestOptions.setServer` at send "
        "time (e)",
        f"`{HTTP_REQUEST_IMPL}`",
        {c: server_handed_on(repo.methods(c, HTTP_REQUEST_IMPL) or []) for c in VERSIONS},
    )

    def server_chosen(methods: list[Method]) -> str:
        found = []
        for m in methods:
            code = m.code
            for i, step in enumerate(code):
                if "RequestOptions.getServer:" not in step.comment or i + 1 >= len(code):
                    continue
                store = code[i + 1]
                if not store.opcode.startswith("astore"):
                    continue
                for j in range(i + 2, len(code) - 1):
                    load, test = code[j], code[j + 1]
                    if not (
                        load.opcode.startswith("aload")
                        and _local(load) == _local(store)
                        and test.opcode in ("ifnull", "ifnonnull")
                    ):
                        continue
                    target = int(test.operand)
                    when_null = (
                        [x for x in code[j + 2 :] if x.offset < target]
                        if test.opcode == "ifnonnull"
                        else [x for x in code if x.offset >= target]
                    )
                    built = [
                        x.comment.split("Method ", 1)[-1].split(":")[0]
                        for x in when_null
                        if x.opcode.startswith("invoke") and "inetSocketAddress" in x.comment
                    ]
                    loads = [
                        k
                        for k, x in enumerate(code)
                        if x.opcode.startswith("aload") and _local(x) == _local(store)
                    ]
                    handed = next(
                        (
                            x.comment.split("Method ", 1)[-1]
                            for x in code[loads[-1] + 1 :]
                            if x.opcode.startswith("invoke")
                            # the call taking it: the first one with an address parameter
                            and re.search(
                                r"\(.*Lio/vertx/core/net/(Socket)?Address;.*\)", x.comment
                            )
                        ),
                        "NOTHING",
                    )
                    found.append(
                        f"`{signature(m)}`: `getServer()` into local {_local(store)}, tested "
                        f"`{test.opcode}` @{test.offset}; only when it is null is an address "
                        f"built from the request's port and host"
                        f" ({', '.join(f'`{b}`' for b in built) or 'NOTHING BUILT'}); the local, "
                        f"set or built, is last loaded @{code[loads[-1]].offset} and handed to "
                        f"`{handed}`"
                    )
                    break
        return "; ".join(found) or "NOT FOUND"

    emit(
        "`HttpClientImpl`: in the method reading `RequestOptions.getServer`, whether a set server "
        "is the address the request goes to, and when the request's own host and port build "
        "one instead (e)",
        f"`{HTTP_CLIENT_IMPL}`",
        {c: server_chosen(repo.methods(c, HTTP_CLIENT_IMPL) or []) for c in VERSIONS},
    )


def group_c(repo: Repo) -> None:
    """(c) RouteState's method set and null path; how RouterImpl builds a route."""

    def path_guard(methods: list[Method]) -> str:
        matches = [m for m in methods if m.name == "matches"]
        if not matches:
            return "no `matches` method"
        code = matches[0].code
        for i, step in enumerate(code):
            if step.opcode != "getfield" or "Field path:" not in step.comment:
                continue
            tail = code[i + 1 : i + 6]
            if len(tail) < 4 or tail[0].opcode != "ifnull":
                continue
            target = int(tail[0].operand)
            if tail[2].opcode == "getfield" and "Field pattern:" in tail[2].comment:
                tested = [c for c in code if c.offset < target and c.offset > step.offset]
                called = [name for _, name, _ in invocations(tested)]
                return (
                    f"`path == null` jumps to @{target}; the path test ({'/'.join(sorted({n for n in called if 'athMatch' in n}))}) "
                    f"is skipped when `path == null` or `pattern != null`; "
                    f"@{target} goes on to read "
                    + ", ".join(
                        f"`{c.comment.removeprefix('Field ')}`"
                        for c in [c for c in code if c.offset >= target][:3]
                        if c.comment
                    )
                )
        return "PATTERN NOT FOUND"

    def methods_guard(methods: list[Method]) -> str:
        matches = [m for m in methods if m.name == "matches"]
        if not matches:
            return "no `matches` method"
        code = matches[0].code
        found = []
        for i, step in enumerate(code):
            if step.opcode == "getfield" and "Field methods:" in step.comment:
                window = code[i + 1 : i + 8]
                if (
                    len(window) >= 7
                    and window[0].opcode == "invokestatic"
                    and "isEmpty" in window[0].comment
                    and window[1].opcode == "ifne"
                    and "containsMethod" in window[4].comment
                    and window[5].opcode == "ifne"
                ):
                    found.append(i)
        status = [
            code[i + 7].operand if i + 7 < len(code) and code[i + 7].opcode == "sipush" else "?"
            for i in found
        ]
        return (
            f"{len(found)} place(s) where `methods` empty skips `containsMethod`; "
            f"a miss answers {', '.join(status)}"
            if found
            else "PATTERN NOT FOUND"
        )

    def is_empty_helper(methods: list[Method]) -> str:
        helper = [m for m in methods if m.name == "isEmpty" and m.is_static]
        if not helper:
            return "no helper"
        return " ".join(
            f"{s.opcode}{(' ' + s.operand) if s.operand else ''}" for s in helper[0].code
        )

    emit(
        "`RouteState.matches`: what a null path does (c)",
        f"`{ROUTE_STATE}`",
        per_column(repo, ROUTE_STATE, path_guard),
    )
    emit(
        "`RouteState.matches`: what an empty method set does (c)",
        f"`{ROUTE_STATE}`",
        per_column(repo, ROUTE_STATE, methods_guard),
    )
    emit(
        "`RouteState.isEmpty(Collection)`, instruction by instruction (c)",
        f"`{ROUTE_STATE}`",
        per_column(repo, ROUTE_STATE, is_empty_helper),
    )

    def route_creation(methods: list[Method]) -> str:
        found = []
        for m in methods:
            if m.name in {"route", "get", "getWithRegex", "routeWithRegex"} and not m.is_bridge:
                calls = [f"{short(o)}.{n}" for o, n, _ in invocations(m.code)]
                news = [
                    s.comment.removeprefix("class ").rsplit("/", 1)[-1]
                    for s in m.code
                    if s.opcode == "new"
                ]
                found.append(
                    f"`{signature(m)}`: new {'+'.join(news) or '-'}; calls {', '.join(calls) or '-'}"
                )
        return "; ".join(sorted(found))

    emit(
        "how `RouterImpl` builds the route behind `route()`, `route(String)`, `route(HttpMethod, String)`, `get()`, `get(String)`, `getWithRegex(String)` (c)",
        f"`{ROUTER_IMPL}`",
        per_column(repo, ROUTER_IMPL, route_creation),
    )

    def route_constructors(methods: list[Method]) -> str:
        found = []
        for m in methods:
            if m.name == "<init>":
                calls = [n for _, n, _ in invocations(m.code) if n != "<init>"]
                found.append(f"`{m.descriptor}`: calls {', '.join(calls) or 'nothing but super'}")
        return "; ".join(sorted(found))

    emit(
        "the constructors of `RouteImpl`, and what each calls (c)",
        f"`{ROUTE_IMPL}`",
        per_column(repo, ROUTE_IMPL, route_constructors),
    )


def throws_of(code: list[Instruction]) -> list[str]:
    """Each `athrow`: the exception class, its message, and what the code since the previous throw
    (or the method start) read — calls, fields and constants — which is the guard."""
    found = []
    guard: list[str] = []
    pending = ""
    message = ""
    for step in code:
        if step.opcode == "new":
            pending = step.comment.removeprefix("class ").replace("/", ".")
            message = ""
        elif step.opcode.startswith("ldc") and step.comment.startswith("String "):
            text = step.comment.removeprefix("String ")
            if pending and not message:
                message = text
            else:
                guard.append(f'"{text}"')
        elif step.opcode in {"bipush", "sipush"}:
            guard.append(step.operand)
        elif step.opcode == "getfield":
            guard.append(step.comment.removeprefix("Field ").split(":")[0])
        elif step.opcode.startswith("invoke") and step.opcode != "invokedynamic":
            match = _INVOKE.match(step.comment)
            if match and not (match.group(2) == "<init>" and pending):
                guard.append(
                    f"{short((match.group(1) or 'this').replace('/', '.'))}.{match.group(2)}"
                )
        elif step.opcode == "athrow":
            found.append(
                f'throws `{short(pending)}`("{message}") after reading {", ".join(guard) or "nothing"}'
            )
            guard = []
            pending = ""
    return found


def group_d(repo: Repo) -> None:
    """(d) what RouteImpl and RouterImpl refuse."""

    def refusals(name: str):  # type: ignore[no-untyped-def]
        def read(methods: list[Method]) -> str:
            chosen = [m for m in methods if m.name == name]
            if not chosen:
                return "absent"
            return "; ".join(t for m in chosen for t in throws_of(m.code)) or "throws nothing"

        return read

    emit(
        "`RouteImpl.checkPath`: what it throws, and on what (d)",
        f"`{ROUTE_IMPL}`",
        per_column(repo, ROUTE_IMPL, refusals("checkPath")),
    )
    emit(
        "`RouteImpl.subRouter`: what it throws, and on what (d)",
        f"`{ROUTE_IMPL}`",
        per_column(repo, ROUTE_IMPL, refusals("subRouter")),
    )
    emit(
        "`RouterImpl.mountSubRouter`: what it throws, and on what (d)",
        f"`{ROUTER_IMPL}`",
        per_column(repo, ROUTER_IMPL, refusals("mountSubRouter")),
    )

    def callers(methods: list[Method]) -> str:
        names = sorted(
            {
                signature(m)
                for m in methods
                if any(n == "checkPath" for _, n, _ in invocations(m.code))
            }
        )
        return ", ".join(f"`{n}`" for n in names) or "none"

    emit(
        "the `RouteImpl` methods and constructors that call `checkPath` (d)",
        f"`{ROUTE_IMPL}`",
        per_column(repo, ROUTE_IMPL, callers),
    )

    def mount_calls(methods: list[Method]) -> str:
        chosen = [m for m in methods if m.name == "mountSubRouter"]
        if not chosen:
            return "absent"
        return "; ".join(
            f"`{m.descriptor}` calls "
            + ", ".join(f"{short(o)}.{n}" for o, n, _ in invocations(m.code))
            for m in chosen
        )

    emit(
        "what `RouterImpl.mountSubRouter` calls (d)",
        f"`{ROUTER_IMPL}`",
        per_column(repo, ROUTER_IMPL, mount_calls),
    )


DEFAULTS = ("getDefaultHost", "getDefaultPort")


def group_e(repo: Repo) -> None:
    """(e) where the default host and port apply, and when the request's own wins."""

    def default_readers(column: str) -> str:
        found = []
        for artifact, jar, _ in repo.jars[column]:
            if artifact not in (CLIENT, M_CLIENT):
                continue
            for cls in classes(jar).values():
                if any(
                    n in DEFAULTS for m in parse_methods(cls) for _, n, _ in invocations(m.code)
                ):
                    found.append(short(cls.name))
        return ", ".join(f"`{n}`" for n in found) or "none"

    emit(
        "every class of `vertx-web-client` that calls `getDefaultHost` or `getDefaultPort` (e)",
        f"`{CLIENT[0]}:{CLIENT[1]}`",
        {c: default_readers(c) for c in VERSIONS},
    )

    def base_requests(methods: list[Method]) -> str:
        found = []
        for m in methods:
            if m.name not in {"request", "requestAbs"} or m.is_bridge:
                continue
            calls = invocations(m.code)
            host = any(n == "getDefaultHost" for _, n, _ in calls)
            port = any(n == "getDefaultPort" for _, n, _ in calls)
            targets = sorted({n for _, n, _ in calls if n in {"request", "requestAbs"}})
            builds = any(s.opcode == "new" and "HttpRequestImpl" in s.comment for s in m.code)
            parts, _ = descriptor_parts(m.descriptor)
            sig = ",".join(simple_type(p) for p in parts)
            found.append(
                f"`{m.name}({sig})`: default host {'yes' if host else 'no'}, default port "
                f"{'yes' if port else 'no'}, {'builds the request' if builds else 'delegates to ' + '/'.join(targets)}"
            )
        return "; ".join(sorted(found))

    emit(
        "each `WebClientBase.request`/`requestAbs`: does it fill the default host and the default port, and does it build the request or delegate (e)",
        f"`{WEB_CLIENT_BASE}`",
        {c: base_requests(repo.methods(c, WEB_CLIENT_BASE) or []) for c in VERSIONS},
    )

    def options_field(column: str) -> str:
        cls = repo.cls(column, WEB_CLIENT_BASE)
        if cls is None:
            return GAP
        found = re.findall(r"^  final (\S+) options;$", cls.text, re.MULTILINE)
        return ", ".join(f"`{f}`" for f in found) or "NOT FOUND"

    emit(
        "the type of the `options` field that `WebClientBase` reads the default host and port from (e)",
        f"`{WEB_CLIENT_BASE}`",
        {c: options_field(c) for c in VERSIONS},
    )

    def request_options_form(methods: list[Method]) -> str:
        for m in methods:
            if m.name != "request" or m.is_bridge:
                continue
            parts, _ = descriptor_parts(m.descriptor)
            if not parts or not parts[-1].endswith("RequestOptions;"):
                continue
            if not any(
                re.search(r"RequestOptions\.get(Port|Host):", step.comment) for step in m.code
            ):
                continue
            code = m.code
            tests = []
            for i, step in enumerate(code):
                if step.opcode == "invokevirtual" and re.search(
                    r"RequestOptions\.get(Port|Host):", step.comment
                ):
                    which = "port" if "getPort" in step.comment else "host"
                    window = code[i + 1 : i + 4]
                    ifnonnull = any(w.opcode == "ifnonnull" for w in window)
                    default = any(
                        w.opcode == "invokevirtual"
                        and re.search(r"WebClient(Options|Config)\.getDefault", w.comment)
                        for w in code[i + 1 : i + 12]
                    )
                    tests.append(
                        f"{which}: own value kept when non-null ({ifnonnull}), default read after the test ({default})"
                    )
            return f"`{signature(m)}`: " + ("; ".join(tests) or "NO TEST FOUND")
        return "no `RequestOptions` form reads the options' host or port"

    emit(
        "`WebClientBase.request(HttpMethod, SocketAddress, RequestOptions)`: the host and the port, a null test then the default (e)",
        f"`{WEB_CLIENT_BASE}`",
        {c: request_options_form(repo.methods(c, WEB_CLIENT_BASE) or []) for c in VERSIONS},
    )

    # The interface forms down to the WebClientBase call, once per verb: normalised by the verb.
    def interface_forms(methods: list[Method]) -> str:
        groups: dict[str, list[str]] = {}
        for m in methods:
            if m.is_static or m.is_abstract or m.is_bridge or not m.code:
                continue
            verb_match = re.fullmatch(r"(get|post|put|delete|patch|head)(Abs)?", m.name)
            if not verb_match and m.name not in {"request", "requestAbs"}:
                continue
            parts, _ = descriptor_parts(m.descriptor)
            sig = f"({','.join(simple_type(p) for p in parts)})"
            trace = []
            for step in m.code:
                if step.opcode == "getstatic" and "HttpMethod" in step.comment:
                    trace.append(
                        "HttpMethod.<verb>"
                        if verb_match
                        else step.comment.removeprefix("Field ").split(":")[0].rsplit("/", 1)[-1]
                    )
                elif step.opcode == "aconst_null":
                    trace.append("null")
                elif step.opcode.startswith("invoke") and step.opcode != "invokedynamic":
                    match = _INVOKE.match(step.comment)
                    if match:
                        o_parts, _ = descriptor_parts(match.group(3))
                        trace.append(
                            f"{short((match.group(1) or '').replace('/', '.'))}.{match.group(2)}({','.join(simple_type(p) for p in o_parts)})"
                        )
            key = (
                f"`{'<verb>' + (verb_match.group(2) or '') if verb_match else m.name}{sig}` -> "
                + " ".join(trace)
            )
            groups.setdefault(key, []).append(m.name)
        return "; ".join(
            f"{key} [{len(names)} method(s)]" if len(names) > 1 else key
            for key, names in sorted(groups.items())
        )

    emit(
        "the `WebClient` default methods per verb, normalised by the verb, and what each calls (e)",
        f"`{WEB_CLIENT}`",
        {c: interface_forms(repo.methods(c, WEB_CLIENT) or []) for c in VERSIONS},
    )

    def request_constructors(methods: list[Method]) -> str:
        found = []
        for m in methods:
            if m.name != "<init>" or descriptor_parts(m.descriptor)[0][0].endswith(
                "HttpRequestImpl;"
            ):
                continue
            consts = []
            for i, s in enumerate(m.code):
                if s.opcode == "putfield" and re.search(
                    r"Field (port|host|absoluteUri):", s.comment
                ):
                    prev = m.code[i - 1]
                    consts.append(
                        f"{s.comment.removeprefix('Field ').split(':')[0]} <- "
                        f"{'the argument' if prev.opcode.startswith(('aload', 'iload')) else prev.opcode}"
                    )
            found.append(f"`{signature(m)}`: {', '.join(consts)}")
        return "; ".join(sorted(found))

    emit(
        "what each `HttpRequestImpl` constructor stores in `port`, `host` and `absoluteUri` (e)",
        f"`{HTTP_REQUEST_IMPL}`",
        {c: request_constructors(repo.methods(c, HTTP_REQUEST_IMPL) or []) for c in VERSIONS},
    )

    def setters(methods: list[Method]) -> str:
        found = []
        for m in methods:
            if m.name in {"host", "port", "uri", "ssl"} and returns_this(m) == "this":
                stores = [
                    s.comment.removeprefix("Field ").split(":")[0]
                    for s in m.code
                    if s.opcode == "putfield"
                ]
                found.append(f"`{signature(m)}` stores {', '.join(stores)}")
        return "; ".join(sorted(found))

    emit(
        "the `HttpRequestImpl` setters `host`, `port`, `uri`, `ssl`: what each stores (e)",
        f"`{HTTP_REQUEST_IMPL}`",
        {c: setters(repo.methods(c, HTTP_REQUEST_IMPL) or []) for c in VERSIONS},
    )

    def build_options(methods: list[Method]) -> str:
        chosen = [m for m in methods if m.name == "buildRequestOptions"]
        if not chosen:
            return "absent"
        code = chosen[0].code
        found = []
        for i, step in enumerate(code):
            if step.opcode != "getfield" or not re.search(
                r"Field (ssl|port|host|uri|absoluteUri):", step.comment
            ):
                continue
            if i == 0 or code[i - 1].opcode != "aload_0":
                continue
            field = step.comment.removeprefix("Field ").split(":")[0]
            nxt = code[i + 1] if i + 1 < len(code) else None
            if nxt is None or nxt.opcode not in {"ifnull", "iflt", "ifnonnull"}:
                continue
            body_ops = code[i + 2 : i + 6]
            # An assignment guarded by the test: `aload_0; getfield f; store local`.
            assign = [
                s
                for j, s in enumerate(body_ops)
                if s.opcode.startswith(("astore", "istore"))
                and any(b.opcode == "getfield" and field in b.comment for b in body_ops[:j])
            ]
            if assign:
                found.append(
                    f"@{step.offset} own `{field}` ({'kept when >= 0' if nxt.opcode == 'iflt' else 'kept when non-null'}) overwrites local `{assign[0].opcode}{assign[0].operand}`"
                )
        parse_sources = []
        for s in code:
            if s.opcode == "getfield" and "ClientUri." in s.comment:
                parse_sources.append(
                    s.comment.removeprefix("Field ").split(":")[0].rsplit("/", 1)[-1]
                )
        return (
            "in order: "
            + "; ".join(found)
            + f"; the absolute URL is parsed first into {', '.join(parse_sources)}"
        )

    emit(
        "`HttpRequestImpl.buildRequestOptions`: the order in which the absolute URL's own parts and the request's own `ssl`/`port`/`host`/`uri` are applied at send time (e)",
        f"`{HTTP_REQUEST_IMPL}`",
        {c: build_options(repo.methods(c, HTTP_REQUEST_IMPL) or []) for c in VERSIONS},
    )

    def uri_constants(methods: list[Method]) -> str:
        chosen = [m for m in methods if m.name == "parse"]
        if not chosen:
            return "absent"
        consts = [
            f"{s.opcode} {s.operand}" for s in chosen[0].code if s.opcode in {"bipush", "sipush"}
        ]
        strings = [
            s.comment.removeprefix("String ")
            for s in chosen[0].code
            if s.opcode.startswith("ldc") and s.comment.startswith("String ")
        ]
        return f"integer constants: {', '.join(consts) or 'none'}; string constants: {', '.join(strings) or 'none'}"

    emit(
        "`ClientUri.parse`: the integer and string constants (the port an absolute URL without one falls back to) (e)",
        f"`{CLIENT_URI}`",
        {c: uri_constants(repo.methods(c, CLIENT_URI) or []) for c in VERSIONS},
    )

    def option_defaults(column: str) -> str:
        cls = repo.cls(column, "io.vertx.core.http.HttpClientOptions")
        if cls is None:
            return GAP
        found = re.findall(
            r"^  public static final \S+ (DEFAULT_DEFAULT_(?:HOST|PORT)|DEFAULT_SSL) = ([^;]+);$",
            cls.text,
            re.MULTILINE,
        )
        text = ", ".join(f"`{name}` = {value}" for name, value in found) or "NOT FOUND"
        config = repo.methods(column, "io.vertx.core.http.HttpClientConfig")
        if config is not None:
            stores = []
            for m in config:
                if m.name != "<init>" or descriptor_parts(m.descriptor)[0]:
                    continue
                for i, step in enumerate(m.code):
                    if step.opcode == "putfield" and re.search(
                        r"Field default(Host|Port):", step.comment
                    ):
                        prev = m.code[i - 1]
                        value = (
                            prev.comment.removeprefix("String ") or f"{prev.opcode} {prev.operand}"
                        )
                        stores.append(
                            f"`{step.comment.removeprefix('Field ').split(':')[0]}` <- {value}"
                        )
            text += "; `HttpClientConfig()` stores " + (", ".join(stores) or "NOTHING FOUND")
        return text

    emit(
        "the constants behind a `WebClientOptions` whose default host, default port and `ssl` were never set (e)",
        "`io.vertx.core.http.HttpClientOptions`",
        {c: option_defaults(c) for c in VERSIONS},
    )


def group_f(repo: Repo) -> None:
    """(f) the HttpMethod constants."""

    def constants(column: str) -> str:
        cls = repo.cls(column, HTTP_METHOD)
        if cls is None:
            return GAP
        names = re.findall(
            r"^  public static final io\.vertx\.core\.http\.HttpMethod (\w+);$",
            cls.text,
            re.MULTILINE,
        )
        methods = [m for m in parse_methods(cls) if m.is_static]
        statics = sorted(f"`{m.name}{m.descriptor}`" for m in methods if m.name != "<clinit>")
        return (
            f"**{len(names)}**: {', '.join(f'`{n}`' for n in names)}; "
            f"declaration `{cls.declaration.strip()}`; static methods {', '.join(statics)}"
        )

    emit(
        "the `public static final HttpMethod` fields, counted, and how the class is declared (f)",
        f"`{HTTP_METHOD}`",
        {c: constants(c) for c in VERSIONS},
    )


def group_g(repo: Repo) -> None:
    """(g) the same names on the wrappers; RoutingContext.next on all three."""
    for prefix_name, prefix in WRAPPERS.items():
        columns = VERSIONS if prefix_name == "rxjava3" else MUTINY_COLUMNS
        for owner, names in [
            (ROUTER, ROUTER_NAMES),
            (ROUTE, ROUTE_NAMES),
            (WEB_CLIENT, WEB_CLIENT_NAMES),
            (HTTP_REQUEST, HTTP_REQUEST_NAMES),
        ]:
            target = wrapped(owner, prefix)
            for name in names:
                cells = {}
                for column in columns:
                    methods = repo.methods(column, target)
                    if methods is not None:
                        cells[column] = descriptors_of(methods, name)
                emit(
                    f"descriptors of `{short(owner)}.{name}` on the {prefix_name} wrapper (g)",
                    f"`{target}`",
                    cells,
                )

    for owner in (
        ROUTING_CONTEXT,
        wrapped(ROUTING_CONTEXT, "io.vertx.rxjava3"),
        wrapped(ROUTING_CONTEXT, "io.vertx.mutiny"),
    ):
        cells = {}
        for column in COLUMNS:
            methods = repo.methods(column, owner)
            if methods is not None:
                cells[column] = descriptors_of(methods, "next")
        emit("descriptors of `RoutingContext.next` (g)", f"`{owner}`", cells)

    # Names the core owner declares that the wrapper does not, and the reverse.
    for prefix_name, prefix in WRAPPERS.items():
        columns = VERSIONS if prefix_name == "rxjava3" else MUTINY_COLUMNS
        for owner in (ROUTER, ROUTE, WEB_CLIENT, HTTP_REQUEST):
            target = wrapped(owner, prefix)
            cells = {}
            for column in columns:
                wrapper_methods = repo.methods(column, target)
                core_column = column if prefix_name == "rxjava3" else MUTINY_AGAINST[column]
                core_methods = repo.methods(core_column, owner)
                if wrapper_methods is None or core_methods is None:
                    continue

                def names_of(methods: list[Method]) -> set[str]:
                    return {
                        m.name
                        for m in methods
                        if not m.is_bridge
                        and m.name not in {"<init>", "<clinit>"}
                        and not m.name.startswith(("lambda$", "access$"))
                    }

                core_names = names_of(core_methods)
                wrapper_names = names_of(wrapper_methods)
                only_core = sorted(core_names - wrapper_names)
                only_wrapper = sorted(wrapper_names - core_names)
                cells[column] = (
                    f"core only: {', '.join(only_core) or 'none'}; wrapper only: {', '.join(only_wrapper) or 'none'}"
                    + (
                        ""
                        if prefix_name == "rxjava3"
                        else f" (against the {MUTINY_AGAINST[column]} core)"
                    )
                )
            emit(
                f"method names `{short(owner)}` declares that the {prefix_name} wrapper does not, and the reverse (g)",
                f"`{target}`",
                cells,
            )


def stamp(step_comment: str) -> str:
    match = _INVOKE.match(step_comment)
    if not match:
        return step_comment
    parts, result = descriptor_parts(match.group(3))
    return (
        f"{short((match.group(1) or '').replace('/', '.'))}.{match.group(2)}"
        f"({','.join(simple_type(p) for p in parts)}){short(result.replace('/', '.')) if result != 'V' else ''}"
    )


def group_h(classes_dir: Path) -> None:
    """(h) what javac 21 writes for the call forms the catalogs read."""
    listing = classes(classes_dir, [SHAPES])[SHAPES]
    major = re.search(r"major version: (\d+)", listing.text)
    if not major or major.group(1) != "65":
        raise ProbeError(f"the probe module is not Java 21 bytecode: {major and major.group(1)}")
    emit(
        "the probe module's class file",
        f"`{SHAPES}`",
        {"5.0.0": f"major version {major.group(1)} (Java 21), compiled against Vert.x 5.0.0"},
    )
    shapes = [
        ("routeMethodReference", '`router.get("/x").handler(this::handle)`'),
        ("routeLambda", '`router.get("/x").handler(ctx -> …)`'),
        ("routeRespond", '`router.get("/x").respond(ctx -> Future.succeededFuture(…))`'),
        (
            "routeStatementStyle",
            '`Route route = router.route("/orders/:id"); route.method(GET); route.handler(this::handle);`',
        ),
        ("routeVerbArgument", '`router.route(HttpMethod.POST, "/orders").handler(this::handle)`'),
        ("routeNoVerbNoPath", "`router.route().handler(ctx -> ctx.next())`"),
        ("routeRegex", '`router.getWithRegex("/r/.+").handler(this::handle)`'),
        ("directRouter", "`new RouterImpl(vertx)`"),
        ("factoryRouter", "`Router.router(vertx)`"),
        ("subRouterMount", '`router.route("/api/*").subRouter(sub)`'),
        ("clientExplicitAddress", '`client.get(8080, "h", "/p").send()`'),
        ("clientHostAndUri", '`client.get("h", "/p").send()`'),
        ("clientUriOnly", '`client.get("/p").send()`'),
        ("clientAbsolute", '`client.getAbs("http://h:8080/p").send()`'),
        (
            "clientChain",
            '`client.post("/q").addQueryParam(…).timeout(…).basicAuthentication(…).as(…).send()`',
        ),
        (
            "clientStatementStyle",
            '`HttpRequest<Buffer> request = client.post("/q"); request.addQueryParam(…); request.timeout(…); request.send();`',
        ),
        (
            "clientWithDefaults",
            '`WebClient.create(vertx, new WebClientOptions().setDefaultHost("h").setDefaultPort(9))`',
        ),
    ]
    for method, label in shapes:
        steps = body(listing, method)
        if not steps:
            raise ProbeError(f"{method} has no body in {SHAPES}")
        trace = []
        for step in steps:
            if step.opcode.startswith("invoke") and step.opcode != "invokedynamic":
                trace.append(f"{step.opcode} `{stamp(step.comment)}`")
            elif step.opcode == "invokedynamic":
                targets = lambda_targets(listing, [step])
                trace.append(f"invokedynamic -> `{', '.join(targets) or step.comment}`")
            elif step.opcode == "new":
                trace.append(
                    f"new `{short(step.comment.removeprefix('class ').replace('/', '.'))}`"
                )
            elif step.opcode == "getstatic":
                trace.append(
                    f"getstatic `{step.comment.removeprefix('Field ').split(':')[0].rsplit('/', 1)[-1]}`"
                )
            elif step.opcode.startswith("ldc"):
                trace.append(f"ldc {step.comment.removeprefix('String ')}")
            elif step.opcode in {"pop", "areturn", "return"}:
                trace.append(step.opcode)
            elif step.opcode in {"sipush", "bipush", "aload_1", "aload_2"} and step.opcode.endswith(
                ("ipush",)
            ):
                trace.append(f"{step.opcode} {step.operand}")
        emit(f"javac 21 for {label} (h)", f"`{SHAPES}.{method}`", {"5.0.0": " -> ".join(trace)})
        # The lambda's own body, for the shapes that write one.
        lambdas = [t for t in lambda_targets(listing, steps) if "lambda$" in t]
        for target in lambdas:
            name = target.split(".", 1)[1]
            inner = body(listing, name)
            calls = [
                stamp(s.comment)
                for s in inner
                if s.opcode.startswith("invoke") and s.opcode != "invokedynamic"
            ]
            emit(
                f"the lambda body `{name}` of {label} (h)",
                f"`{SHAPES}.{name}`",
                {"5.0.0": " -> ".join(f"`{c}`" for c in calls)},
            )


def main(argv: list[str]) -> int:
    arguments = dict(a.split("=", 1) for a in argv)
    classes_dir = Path(arguments["CLASSES"])
    repo = Repo()
    missing = [c for c in COLUMNS if not repo.jars[c]]
    if missing:
        raise ProbeError(f"no jars found for column(s) {missing}: run run.sh, which fetches them")
    group_identity(repo)

    print("| what the run read | " + " | ".join(COLUMNS) + " |")
    print("|---|" + "---|" * len(COLUMNS))
    print(
        "| artifacts reporting this version | "
        + " | ".join(", ".join(f"{a[0]}:{a[1]}" for a, _, _ in repo.jars[c]) for c in COLUMNS)
        + " |"
    )
    print(
        "| where the jars state that version | "
        + " | ".join("MANIFEST.MF `Implementation-Version`" for _ in COLUMNS)
        + " |"
    )
    print()

    group_a(repo)
    group_b(repo)
    group_c(repo)
    group_d(repo)
    group_e(repo)
    group_f(repo)
    group_g(repo)
    group_h(classes_dir)
    group_b_event_bus(repo)
    group_e_server(repo)
    print(render())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
