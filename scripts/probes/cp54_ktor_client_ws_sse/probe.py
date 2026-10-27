"""CP-54: the shapes Ktor 3.6.0's HTTP client, WebSocket and SSE calls take — the static verb fields
on `HttpMethod`, the call sequence the compiler inlines for each client form, every overload of the
server `webSocket`/`webSocketRaw`/`sse` routes and the client `webSocket`/`ws`/`wss`/`sse` calls
with what each argument is, the `DefaultRequest` URL setters, the verb and URL a fresh request
builder starts with, and how `DefaultRequest` joins a relative address onto its base. Every cell is
read off the Ktor jars and the probe module's class files with `javap -c`, except the join and the
fresh-builder defaults, which `Main.kt` takes from Ktor itself by running its `DefaultRequest`
plugin over a mock engine, and which verb each WebSocket and SSE route answers (h), which
`Main.kt` asks Ktor's own router by sending requests to small routing trees on Ktor's test host
and on a CIO server. The version in each column is the jar's own manifest, and the process
that ran Ktor's code has to report the same one. Prints the observation table
`cp54_ktor_client_ws_sse.md` carries."""

import re
import subprocess
import sys
from dataclasses import dataclass, field
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
)

VERSION = "3.6.0"
HTTP = ("io.ktor", "ktor-http-jvm")
CLIENT = ("io.ktor", "ktor-client-core-jvm")
MOCK = ("io.ktor", "ktor-client-mock-jvm")
SERVER_WS = ("io.ktor", "ktor-server-websockets-jvm")
SERVER_SSE = ("io.ktor", "ktor-server-sse-jvm")
TEST_HOST = ("io.ktor", "ktor-server-test-host-jvm")
SERVER_CIO = ("io.ktor", "ktor-server-cio-jvm")
ARTIFACTS = {
    "http": HTTP,
    "client": CLIENT,
    "mock": MOCK,
    "server_ws": SERVER_WS,
    "server_sse": SERVER_SSE,
    "test_host": TEST_HOST,
    "server_cio": SERVER_CIO,
}

METHOD = "io.ktor.http.HttpMethod"
COMPANION = "io.ktor.http.HttpMethod$Companion"
BUILDER = "io.ktor.client.request.HttpRequestBuilder"
REQUEST_KT = "io.ktor.client.request.HttpRequestKt"
DEFAULT_REQUEST_KT = "io.ktor.client.plugins.DefaultRequestKt"
DEFAULT_BUILDER = "io.ktor.client.plugins.DefaultRequest$DefaultRequestBuilder"
SERVER_WS_KT = "io.ktor.server.websocket.RoutingKt"
SERVER_WS_PART = "io.ktor.server.websocket.RoutingKt__RoutingKt"
SERVER_SSE_KT = "io.ktor.server.sse.RoutingKt"
CLIENT_WS_KT = "io.ktor.client.plugins.websocket.BuildersKt"
CLIENT_SSE_KT = "io.ktor.client.plugins.sse.BuildersKt"
PROBE = "probe.ProbeKt"
INSTALL = "probe.InstallKt"

# The probe module's functions, one per shape, in the order the table reports them.
HTTP_FORMS = [
    ("clientGetString", '`client.get("…")`'),
    ("clientPostWithBody", '`client.post("…") { setBody(…) }`'),
    ("clientPostNoBody", '`client.post("…")`'),
    ("clientPutString", '`client.put("…") { setBody(…) }`'),
    ("clientPatchString", '`client.patch("…") { setBody(…) }`'),
    ("clientDeleteString", '`client.delete("…")`'),
    ("clientHeadString", '`client.head("…")`'),
    ("clientOptionsString", '`client.options("…")`'),
    ("clientGetBlockUrl", '`client.get { url("…") }`'),
    ("clientRequestPut", '`client.request("…") { method = HttpMethod.Put }`'),
    ("clientPrepare", '`client.prepareGet("…").execute()`'),
    ("clientRelative", '`client.get("relative/path")`'),
    ("clientDerivedRelative", '`derivedClient.get("/derived/path")`, a client made by `config`'),
]
SERVER_SHAPES = [
    ("serverWsPath", '`webSocket("/ws/chat") { }`', "server_ws"),
    ("serverWsPathAndProtocol", '`webSocket("/ws/protocol", protocol = "chat") { }`', "server_ws"),
    ("serverWsPathless", "`webSocket { }`", "server_ws"),
    ("serverWsProtocolOnly", '`webSocket(protocol = "pathless") { }`', "server_ws"),
    ("serverWsRawPath", '`webSocketRaw("/ws/raw") { }`', "server_ws"),
    ("serverWsRawFull", '`webSocketRaw("/ws/raw-auto", "chat", true) { }`', "server_ws"),
    ("serverSsePath", '`sse("/sse/events") { }`', "server_sse"),
    ("serverSsePathless", "`sse { }`", "server_sse"),
    (
        "serverNested",
        '`route("/api") { webSocket("/nested") { }; sse("/nested-events") { } }`',
        "server_ws",
    ),
]
CLIENT_SHAPES = [
    ("clientWebSocket", '`client.webSocket("ws://…") { }`'),
    ("clientWebSocketParts", '`client.webSocket(host = …, port = 8080, path = "/parts") { }`'),
    ("clientWebSocketRequestLambda", '`client.webSocket({ url("ws://…") }) { }`'),
    ("clientWs", '`client.ws("/opentelemetry/websocket") { }`'),
    ("clientWss", '`client.wss("/secure/websocket") { }`'),
    ("clientWebSocketSession", '`client.webSocketSession("ws://…")`'),
    ("clientSse", '`client.sse("https://…") { }`'),
    ("clientSseParts", '`client.sse(host = …, port = 8080, path = "/sse-parts") { }`'),
    ("clientSseRequestLambda", '`client.sse({ url("https://…") }) { }`'),
    ("clientSseSession", '`client.sseSession("https://…")`'),
]


# --- a small javap reader for what `_jvm_annotations` does not keep: descriptors, parameter
# --- names, nullability and the hidden-deprecation flag of every method ------------------------


def dotted(descriptor_type: str) -> str:
    """One JVM field descriptor as a Java type name (`Ljava/lang/String;` -> `java.lang.String`)."""
    dimensions = len(descriptor_type) - len(descriptor_type.lstrip("["))
    core = descriptor_type.lstrip("[")
    primitives = {
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
    name = core[1:-1].replace("/", ".") if core.startswith("L") else primitives[core]
    return name + "[]" * dimensions


def split_descriptor(descriptor: str) -> tuple[list[str], str]:
    """`(Lio/ktor/X;IJ)V` -> (["io.ktor.X", "int", "long"], "void")."""
    arguments, _, result = descriptor[1:].partition(")")
    found: list[str] = []
    i = 0
    while i < len(arguments):
        start = i
        while arguments[i] == "[":
            i += 1
        i = arguments.index(";", i) + 1 if arguments[i] == "L" else i + 1
        found.append(dotted(arguments[start:i]))
    return found, dotted(result)


def short(type_name: str) -> str:
    """`kotlin.jvm.functions.Function2` -> `Function2`; `…$Companion` keeps its nesting."""
    return type_name.rsplit(".", 1)[-1]


@dataclass
class Method:
    name: str
    parameters: list[str]
    result: str
    flags: str
    names: dict[int, str] = field(default_factory=dict)  # parameter index -> source name
    nullable: set[int] = field(default_factory=set)
    hidden: bool = False
    lines: list[str] = field(default_factory=list)

    @property
    def public(self) -> bool:
        return "ACC_PUBLIC" in self.flags

    @property
    def synthetic(self) -> bool:
        return "ACC_SYNTHETIC" in self.flags

    @property
    def static(self) -> bool:
        return "ACC_STATIC" in self.flags


_HEADER = re.compile(r"^  \S.*\(.*\)(?: throws [\w.,\s$]+)?;$")


def methods_of(cls: ClassFile) -> list[Method]:
    """Every method of a class: descriptor, flags, parameter names from the LocalVariableTable,
    the parameters marked `@Nullable`, and whether `@Deprecated(level = HIDDEN)` is on it."""
    lines = cls.text.splitlines()
    starts = [i for i, line in enumerate(lines) if _HEADER.match(line)]
    found: list[Method] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        chunk = lines[start:end]
        header = chunk[0]
        name = header[: header.index("(")].split()[-1].strip('"')
        if name.startswith("static"):  # `static {}` initialiser has no name before `(`
            name = "<clinit>"
        descriptor = next(
            (l.split("descriptor:", 1)[1].strip() for l in chunk if "descriptor:" in l), None
        )
        if descriptor is None:
            continue
        parameters, result = split_descriptor(descriptor)
        flags = next((l.split("flags:", 1)[1].strip() for l in chunk if "flags:" in l), "")
        method = Method(name, parameters, result, flags, lines=chunk)
        # parameter index -> JVM slot, to match the LocalVariableTable (long and double take two)
        slot = 0 if "ACC_STATIC" in flags else 1
        slots: dict[int, int] = {}
        for index, type_name in enumerate(parameters):
            slots[slot] = index
            slot += 2 if type_name in ("long", "double") else 1
        for line in chunk:
            row = re.match(r"^\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+\S+$", line)
            if row and int(row.group(1)) == 0 and int(row.group(3)) in slots:
                method.names[slots[int(row.group(3))]] = row.group(4)
        in_parameters = False
        current = -1
        for line in chunk:
            if line.strip() == "RuntimeInvisibleParameterAnnotations:":
                in_parameters = True
            elif in_parameters:
                index_row = re.match(r"^\s+parameter (\d+):", line)
                if index_row:
                    current = int(index_row.group(1))
                elif "org.jetbrains.annotations.Nullable" in line:
                    method.nullable.add(current)
                elif line.strip() and not line.startswith("      "):
                    in_parameters = False
        method.hidden = any("DeprecationLevel;.HIDDEN" in l for l in chunk)
        found.append(method)
    return found


def mask_bits(method: Method) -> list[int]:
    """The parameter positions a `$default` bridge tests (`<mask> iand`): the ones that have a
    default value. Position 0 is the receiver of an extension function."""
    bits: list[int] = []
    previous = None
    for line in method.lines:
        step = re.match(r"^\s+\d+: (\w+)\s*([^/]*?)\s*(?://\s*(.*))?$", line)
        if not step:
            continue
        opcode, operand, comment = step.group(1), step.group(2), step.group(3) or ""
        if opcode == "iand" and previous is not None:
            bits.append(previous)
        previous = None
        constant = re.fullmatch(r"iconst_(m?\d)", opcode)
        if constant:
            previous = int(constant.group(1).replace("m", "-"))
        elif opcode in ("bipush", "sipush"):
            previous = int(operand)
        elif opcode == "ldc" and comment.startswith("int "):
            previous = int(comment.split()[1])
    return [value.bit_length() - 1 for value in bits if value > 0 and value & (value - 1) == 0]


class Table:
    """The overloads of one class, indexed so a descriptor from a call site finds its method.
    `parts` are the classes a multifile facade delegates to: the facade's `$default` bridges only
    forward the call, and the mask they test is in the part."""

    def __init__(self, cls: ClassFile, parts: list[ClassFile] | None = None):
        self.cls = cls
        self.methods = methods_of(cls)
        self.parts = [Table(part) for part in parts or []]

    def named(self, base: str) -> list[Method]:
        """Public methods whose JVM name is `base` or `base-<mangling>`: the ones source code can
        call and the `@Deprecated(HIDDEN)` ones, which the compiler marks synthetic and which an
        older compiled caller still links to."""
        return [
            m
            for m in self.methods
            if m.public and "$" not in m.name and (m.name == base or m.name.startswith(base + "-"))
        ]

    def partner(self, method: Method) -> Method | None:
        """The `$default` bridge of a method, found by name, parameters and result. A bridge for
        an instance method takes the instance as its first parameter."""
        skip = 0 if method.static else 1
        return next(
            (
                m
                for m in self.methods
                if m.name == method.name + "$default"
                and m.result == method.result
                and m.parameters[skip:-2] == method.parameters
            ),
            None,
        )

    def find(self, name: str, parameters: list[str], result: str) -> Method | None:
        return next(
            (
                m
                for m in self.methods
                if m.name == name and m.parameters == parameters and m.result == result
            ),
            None,
        )

    def defaulted(self, method: Method) -> list[int]:
        """The parameter positions of `method` that have a default value, read from the bits its
        `$default` bridge tests. A bridge's mask counts the value parameters only: the receiver of
        an extension function (every static method in these classes) is not one of the bits."""
        bridge = self.partner(method)
        if bridge is None:
            return []
        bits = mask_bits(bridge)
        if not bits:  # a facade's bridge only forwards; the part holds the test
            for part in self.parts:
                inner = part.find(bridge.name, bridge.parameters, bridge.result)
                if inner is not None:
                    bits = mask_bits(inner)
        offset = 1 if method.static else 0
        return sorted(bit + offset for bit in bits)


def role(method: Method, index: int) -> str:
    name = method.names.get(index, f"arg{index}")
    if name.startswith("$this$"):
        name = "receiver"
    return f"{name}{'?' if index in method.nullable else ''}: {short(method.parameters[index])}"


def describe(table: Table, method: Method) -> str:
    """`name(arg0 role, arg1 role, …) -> result`, the numbering the catalog's `path_arg` and
    `arg_types` read, with the parameters that have a default and any hidden-deprecation noted."""
    parameters = method.parameters
    shown = [
        f"{i}={role(method, i)}"
        for i in range(len(parameters))
        if not parameters[i].endswith("Continuation")
    ]
    text = f"`{method.name}({', '.join(shown)}) -> {short(method.result)}`"
    if table.partner(method) is not None and not method.hidden:
        defaulted = [method.names.get(i, f"arg{i}") for i in table.defaulted(method)]
        text += f" (`{method.name}$default` defaults: {', '.join(defaulted) or 'none read'})"
    if method.hidden:
        text += " [`@Deprecated(HIDDEN)`: an older binary form]"
    return text


def overload_cell(table: Table, base: str) -> str:
    found = table.named(base)
    if not found:
        raise ProbeError(f"{table.cls.name} has no public method named {base}")
    return "<br>".join(f"({n}) {describe(table, m)}" for n, m in enumerate(found, 1))


# --- instructions ------------------------------------------------------------------------------

_CALL = re.compile(r'Method ([\w/$]+)\.("?)([^:"]+)\2:(\(.*)')


def invocations(steps: list[Instruction]) -> list[tuple[int, str, str, str]]:
    """(position, owner, name, descriptor) of every invocation, owner dotted."""
    found = []
    for i, step in enumerate(steps):
        match = _CALL.match(step.comment)
        if step.opcode.startswith("invoke") and match:
            found.append((i, match.group(1).replace("/", "."), match.group(3), match.group(4)))
    return found


def literals(steps: list[Instruction]) -> list[str]:
    found = []
    for step in steps:
        match = re.fullmatch(r"String(?: (.*))?", step.comment)
        if (
            step.opcode.startswith("ldc")
            and match
            and not (match.group(1) or "").startswith(("$", "<this>"))
        ):
            found.append(match.group(1) or "")
    return found


def int_before(steps: list[Instruction], position: int) -> int | None:
    """The int literal pushed two instructions before the call at `position` (the mask a
    `$default` call passes; the instruction between is the `aconst_null` marker)."""
    if position < 2 or steps[position - 1].opcode != "aconst_null":
        return None
    step = steps[position - 2]
    constant = re.fullmatch(r"iconst_(m?\d)", step.opcode)
    if constant:
        return int(constant.group(1).replace("m", "-"))
    if step.opcode in ("bipush", "sipush"):
        return int(step.operand)
    if step.opcode == "ldc" and step.comment.startswith("int "):
        return int(step.comment.split()[1])
    return None


def shape_steps(cls: ClassFile, function: str) -> list[Instruction]:
    """A shape's instructions: the function itself, then the lambdas the compiler made from its
    blocks (`<function>$lambda$N…`), in name order."""
    names = sorted(
        {
            m.name
            for m in methods_of(cls)
            if m.name == function or m.name.startswith(function + "$lambda")
        }
    )
    steps: list[Instruction] = []
    for name in names:
        steps += body(cls, name)
    if not steps:
        raise ProbeError(f"{cls.name} has no function {function}")
    return steps


def http_sequence(cls: ClassFile, function: str) -> str:
    """(b): the ordered calls that make up the request, as the compiler inlined them."""
    steps = body(cls, function)
    tokens: list[str] = []
    for i, owner, name, descriptor in invocations(steps):
        simple = owner.rsplit(".", 1)[-1]
        if name == "<init>" and simple == "HttpRequestBuilder":
            tokens.append("`new HttpRequestBuilder()`")
        elif simple == "HttpRequestKt" and name == "url":
            tokens.append(
                f"`HttpRequestKt.url(builder, {short(split_descriptor(descriptor)[0][1])})`"
            )
        elif simple == "HttpRequestBuilder" and name == "setMethod":
            verb = next(
                (
                    re.match(r"Field io/ktor/http/HttpMethod\.(\w+):", s.comment).group(1)
                    for s in reversed(steps[:i])
                    if s.comment.startswith("Field io/ktor/http/HttpMethod.")
                ),
                "?",
            )
            tokens.append(f"`builder.setMethod(HttpMethod.{verb})`")
        elif simple == "HttpRequestBuilder" and name in ("setBody", "setBodyType"):
            tokens.append(f"`builder.{name}`")
        elif simple == "HttpStatement" and name == "<init>":
            tokens.append("`new HttpStatement(builder, client)`")
        elif simple == "HttpStatement" and name == "execute":
            tokens.append("`HttpStatement.execute()`")
    constants = literals(steps)
    return " -> ".join(tokens) + "; string constants: " + ", ".join(f"`{c}`" for c in constants)


def call_sites(cls: ClassFile, function: str, tables: dict[str, Table]) -> str:
    """(c)/(d): each call a shape makes into the routing or builders classes, with the overload
    it lands on, what each argument is, and for a `$default` call which parameters the mask says
    were left to their defaults."""
    steps = shape_steps(cls, function)
    found = []
    for position, owner, name, descriptor in invocations(steps):
        table = tables.get(owner)
        if table is None:
            continue
        parameters, result = split_descriptor(descriptor)
        method = table.find(name, parameters, result)
        if method is None:
            raise ProbeError(f"{owner}.{name}{descriptor} is called but not declared")
        if name.endswith("$default"):
            base = table.find(name[: -len("$default")], parameters[:-2], result)
            if base is None:
                raise ProbeError(f"{owner}.{name} has no base method to read the mask against")
            mask = int_before(steps, position)
            if mask is None:
                raise ProbeError(f"{owner}.{name} is called without a mask literal")
            offset = 1 if base.static else 0
            left = [i + offset for i in range(len(parameters) - 2 - offset) if mask >> i & 1]
            supplied = [
                f"{i}={role(base, i)}"
                for i in range(len(base.parameters))
                if i not in left and not base.parameters[i].endswith("Continuation")
            ]
            found.append(
                f"`{name}` (mask {mask}) supplies {', '.join(supplied)}; "
                f"defaults {', '.join(f'{i}={role(base, i)}' for i in left) or 'none'}"
            )
        else:
            supplied = [
                f"{i}={role(method, i)}"
                for i in range(len(parameters))
                if not parameters[i].endswith("Continuation")
            ]
            found.append(f"`{name}` supplies {', '.join(supplied)}")
    strings = literals(steps)
    return "; ".join(found) + (
        "; string literals: " + ", ".join(f"`{s}`" for s in strings) if strings else ""
    )


# --- the process that ran Ktor's code ------------------------------------------------------------


def run_main(java_home: str, classes_dir: str, classpath_file: str) -> list[list[str]]:
    classpath = Path(classpath_file).read_text(encoding="utf-8").strip()
    result = subprocess.run(
        [f"{java_home}/bin/java", "-cp", f"{classes_dir}:{classpath}", "probe.MainKt"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"MainKt failed: {result.stderr.strip()}")
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    arguments = dict(arg.split("=", 1) for arg in argv)
    java_home = arguments["JAVA_HOME"]
    expected_metadata = arguments["EXPECTED_KOTLIN_MV"]

    jars = {}
    for key, (group, artifact) in ARTIFACTS.items():
        jar = jar_at(group, artifact, VERSION)
        if jar is None:
            raise ProbeError(f"NOT IN THE LOCAL REPOSITORY: {group}:{artifact}:{VERSION}")
        jars[key] = (jar, identity(jar, VERSION)[0])
    columns = sorted({stated for _, stated in jars.values()})
    if len(columns) != 1:
        raise ProbeError(
            f"the Ktor jars state different versions: { {k: v[1] for k, v in jars.items()} }"
        )

    ran = run_main(java_home, arguments["CLASSES"], arguments["CLASSPATH"])
    reported = {r[1]: r[2] for r in ran if r[0] == "IDENTITY"}
    for key, (group, artifact) in ARTIFACTS.items():
        name = artifact.removesuffix("-jvm")
        if reported.get(name) != jars[key][1]:
            raise ProbeError(
                f"the process reports {name} {reported.get(name)!r}, "
                f"the jar's manifest states {jars[key][1]!r}"
            )
    for entry in ran:
        if entry[0] in (
            "MERGE",
            "PROTOCOL",
            "DISPATCH",
            "DERIVED",
            "JOIN",
            "TWICE",
            "ENGINELESS",
            "QUERY",
            "INSTALLED",
        ) and (entry[-1] == "NOT REACHED" or entry[-1].startswith("FAILED")):
            raise ProbeError(f"Ktor's run did not complete: {' | '.join(entry)}")
    # (h) a request the server never received measures nothing about routing.
    for entry in ran:
        if entry[0] == "DISPATCH" and entry[3] == "NOT RECEIVED":
            raise ProbeError(f"the server received no request: {' | '.join(entry)}")

    module = classes(Path(arguments["CLASSES"]), [PROBE, "probe.MainKt", INSTALL])
    probe = module[PROBE]
    metadata = re.search(r"mv=\[(?:I\()?(\d+)\)?,(?:I\()?(\d+)\)?,(?:I\()?(\d+)\)?\]", probe.text)
    stated_metadata = ".".join(metadata.groups()) if metadata else "NOT FOUND"
    major = re.search(r"^\s+major version: (\d+)", probe.text, flags=re.MULTILINE)
    stated_major = major.group(1) if major else "NOT FOUND"
    if stated_major != "65":  # class file major version 65 is Java 21
        raise ProbeError(
            f"the probe module's class files are major version {stated_major}, not 65 (Java 21)"
        )
    if stated_metadata != expected_metadata:
        raise ProbeError(
            f"the probe module's class files state Kotlin metadata {stated_metadata}, "
            f"the run expected {expected_metadata}"
        )

    http = classes(jars["http"][0], [METHOD, COMPANION])
    client = classes(
        jars["client"][0],
        [
            BUILDER,
            REQUEST_KT,
            DEFAULT_REQUEST_KT,
            DEFAULT_BUILDER,
            CLIENT_WS_KT,
            CLIENT_SSE_KT,
            "io.ktor.client.HttpClient",
        ],
    )
    server_ws_classes = classes(jars["server_ws"][0], [SERVER_WS_KT, SERVER_WS_PART])
    server_ws = server_ws_classes[SERVER_WS_KT]
    server_sse = classes(jars["server_sse"][0], [SERVER_SSE_KT])[SERVER_SSE_KT]
    tables = {
        SERVER_WS_KT: Table(server_ws, [server_ws_classes[SERVER_WS_PART]]),
        SERVER_SSE_KT: Table(server_sse),
        CLIENT_WS_KT: Table(client[CLIENT_WS_KT]),
        CLIENT_SSE_KT: Table(client[CLIENT_SSE_KT]),
    }

    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + ", ".join(f"{g}:{a}" for g, a in ARTIFACTS.values())
        + " |"
    )
    print("| where the jar states that version | MANIFEST.MF `Implementation-Version` |")
    print(
        "| what the process that ran Ktor's code reported | `Package.getImplementationVersion` of a class from each jar: "
        + ", ".join(
            f"{a.removesuffix('-jvm')} {reported[a.removesuffix('-jvm')]}"
            for _, a in ARTIFACTS.values()
        )
        + f"; Kotlin runtime {reported['kotlin-stdlib']} |"
    )
    print(
        f"| the probe module's compiler | `kotlin.Metadata` `mv` on `{PROBE}`: {stated_metadata} "
        f"(the metadata version is the only version kotlinc writes into a class file); class file "
        f"major version {stated_major} (Java 21) |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    row = 0

    def emit(question: str, key: str, observed: str) -> None:
        nonlocal row
        row += 1
        group, artifact = ARTIFACTS[key]
        print(f"| {row} | {question} | `{group}:{artifact}` | {jars[key][1]} | {observed} |")

    # (a) the verb fields
    verb = next(c for c in http.values() if c.name == METHOD)
    wire = {}
    pending = None
    for step in body(verb, "<clinit>"):
        string = re.fullmatch(r"String (.*)", step.comment)
        if step.opcode.startswith("ldc") and string:
            pending = string.group(1)
        elif step.opcode == "putstatic" and pending is not None:
            field_name = re.match(r"Field (\w+):", step.comment)
            if field_name:
                wire[field_name.group(1)] = pending
            pending = None
    declared = [
        m.name
        for m in verb.members
        if m.header.startswith("public static final io.ktor.http.HttpMethod ")
    ]
    emit(
        "the static verb fields of `HttpMethod`, in declaration order (a)",
        "http",
        "; ".join(f'`{f}` = `"{wire.get(f, "NOT A STRING CONSTANT")}"`' for f in declared),
    )
    companion = next(c for c in http.values() if c.name == COMPANION)
    getters = [
        m.name
        for m in methods_of(companion)
        if m.public and m.name.startswith("get") and m.result.endswith("HttpMethod")
    ]
    # the verbs read since the previous `putstatic`, when the one that stores `DefaultMethods` comes
    listed: list[str] = []
    collected: list[str] = []
    for step in body(verb, "<clinit>"):
        if step.opcode == "getstatic":
            field_read = re.match(
                r"Field (?:io/ktor/http/HttpMethod\.)?(\w+):Lio/ktor/http/HttpMethod;", step.comment
            )
            if field_read:
                collected.append(field_read.group(1))
        elif step.opcode == "putstatic":
            if step.comment.startswith("Field DefaultMethods:"):
                listed = collected
                break
            collected = []
    if not listed:
        raise ProbeError(
            "HttpMethod's static initialiser never stores DefaultMethods from verb fields"
        )
    emit(
        "the verb getters on `HttpMethod.Companion`, and the verbs `DefaultMethods` lists (a)",
        "http",
        f"getters: {', '.join(f'`{g}`' for g in getters)}; no getter for: "
        f"{', '.join(f'`{f}`' for f in declared if 'get' + f not in getters) or 'none'}; "
        f"`DefaultMethods` holds: {', '.join(f'`{f}`' for f in listed)}",
    )

    # (b) the five client forms, a relative call, and a call on a derived client
    for function, written in HTTP_FORMS:
        emit(
            f"the call sequence compiled for {written} (b)",
            "client",
            http_sequence(probe, function),
        )

    # (c) the server routes
    for base, key, label, table_key in (
        ("webSocket", "server_ws", "server `webSocket`", SERVER_WS_KT),
        ("webSocketRaw", "server_ws", "server `webSocketRaw`", SERVER_WS_KT),
        ("sse", "server_sse", "server `sse`", SERVER_SSE_KT),
    ):
        emit(
            f"every overload of {label}, with what each argument is (c)",
            key,
            overload_cell(tables[table_key], base),
        )
    for function, written, key in SERVER_SHAPES:
        emit(f"the call {written} compiles to (c)", key, call_sites(probe, function, tables))

    # (d) the client WebSocket and SSE calls
    for base, table_key, label in (
        ("webSocket", CLIENT_WS_KT, "client `webSocket`"),
        ("ws", CLIENT_WS_KT, "client `ws`"),
        ("wss", CLIENT_WS_KT, "client `wss`"),
        ("webSocketSession", CLIENT_WS_KT, "client `webSocketSession`"),
        ("sse", CLIENT_SSE_KT, "client `sse`"),
        ("sseSession", CLIENT_SSE_KT, "client `sseSession`"),
        ("serverSentEvents", CLIENT_SSE_KT, "client `serverSentEvents`"),
        ("serverSentEventsSession", CLIENT_SSE_KT, "client `serverSentEventsSession`"),
    ):
        emit(
            f"every overload of {label}, with what each argument is (d)",
            "client",
            overload_cell(tables[table_key], base),
        )
    for function, written in CLIENT_SHAPES:
        emit(f"the call {written} compiles to (d)", "client", call_sites(probe, function, tables))

    # (e) DefaultRequest
    builder = Table(client[DEFAULT_BUILDER])
    emit(
        "the URL setters of `DefaultRequest.DefaultRequestBuilder` (e)",
        "client",
        overload_cell(builder, "url"),
    )
    emit(
        "the URL setters on a request builder, `HttpRequestKt.url` (e)",
        "client",
        overload_cell(Table(client[REQUEST_KT]), "url"),
    )
    emit(
        "the `defaultRequest` installer (e)",
        "client",
        overload_cell(Table(client[DEFAULT_REQUEST_KT]), "defaultRequest"),
    )
    wiring = []
    static_init = body(probe, "<clinit>")
    for position, owner, name, descriptor in invocations(static_init):
        if owner.endswith("HttpClientKt") or name == "config":
            wiring.append(
                f"`{short(owner)}.{name}` with {short(split_descriptor(descriptor)[0][-1])}"
            )
    emit(
        "how the two clients are constructed, from the static initialiser of the file (e)",
        "client",
        "; ".join(wiring)
        + "; the configuration lambdas call: "
        + "; ".join(
            f"`{name}` -> "
            + ", ".join(
                f"`{short(owner)}.{call}`"
                for _, owner, call, _ in invocations(body(probe, name))
                if call in ("install$default", "defaultRequest", "url")
            )
            for name in (
                "client$lambda$0",
                "client$lambda$0$0",
                "derivedClient$lambda$0",
                "derivedClient$lambda$0$0",
            )
        ),
    )

    # (f) the fresh builder's defaults
    constructor = body(client[BUILDER], "HttpRequestBuilder", "")
    defaults = [
        f"{s.opcode} {s.comment}"
        for s in constructor
        if s.opcode in ("getstatic", "putfield")
        and ("HttpMethod" in s.comment or "method" in s.comment)
    ]
    bits = {r[1]: r[2] for r in ran if r[0] == "DEFAULT"}
    emit(
        "the verb and URL of a request builder nothing has been set on (f)",
        "client",
        f"constructor bytecode: {', '.join(f'`{d}`' for d in defaults)}; run on a fresh "
        f"`HttpRequestBuilder()`: verb `{bits['verb']}`, URL `{bits['url']}`",
    )

    # (g) Ktor's own join of a relative address onto the base
    for entry in ran:
        if entry[0] == "MERGE":
            _, label, base, relative, result = entry
            emit(
                f"`DefaultRequest` join: {label} (g)",
                "client",
                f'base `{base}`, call `get("{relative}")` -> Ktor sent `{result}`',
            )
    for entry in ran:
        if entry[0] == "PROTOCOL":
            _, label, base, relative, result = entry
            emit(
                f"`DefaultRequest` join through a WebSocket call: {label} (g)",
                "client",
                f"base `{base}`, address `{relative}` -> the engine received `{result}`",
            )

    # (h) which verb each WebSocket and SSE route answers, asked of Ktor's own router
    for entry in ran:
        if entry[0] == "DISPATCH":
            _, label, request, received, selected, outcome = entry
            if label.startswith("test host"):
                key = "test_host"
            elif label.startswith("`sse") or "sse {" in label:
                key = "server_sse"
            else:
                key = "server_ws"
            route = (
                f"the router selected `{selected}`" if selected != "NONE" else "no route selected"
            )
            emit(
                f"{label} sent `{request}` (h)",
                key,
                f"the server received `{received}`; {route}; {outcome}",
            )

    # (i) the base a client derived by `config { … }` sends to
    for entry in ran:
        if entry[0] == "DERIVED":
            _, label, parent, child, relative, result = entry
            emit(
                f"`DefaultRequest` join on a client derived by `config`: {label} (i)",
                "client",
                f"parent base `{parent}`, derived client's own base `{child}`, call "
                f'`get("{relative}")` -> Ktor sent `{result}`',
            )

    # (j) joins (g) does not cover, and a block setting the base twice
    for entry in ran:
        if entry[0] == "JOIN":
            _, label, base, relative, result = entry
            sent = result if result.startswith("Ktor threw") else f"Ktor sent `{result}`"
            emit(
                f"`DefaultRequest` join: {label} (j)",
                "client",
                f'base `{base}`, call `get("{relative}")` -> {sent}',
            )
    for entry in ran:
        if entry[0] == "TWICE":
            _, label, first, second, relative, result = entry
            emit(
                f"`defaultRequest {{ url(…); url(…) }}`: {label} (j)",
                "client",
                f'`url("{first}")` then `url("{second}")`, call `get("{relative}")` -> '
                f"Ktor sent `{result}`",
            )

    # (k) the engine-less factory `HttpClient { … }`, and an address that is only a query
    engineless_wiring = [
        f"`{short(owner)}.{name}` `{descriptor}`"
        for _, owner, name, descriptor in invocations(static_init)
        if owner.endswith("HttpClientJvmKt")
    ]
    emit(
        "how the engine-less client `HttpClient { … }` is constructed, from the static "
        "initialiser of the file (k)",
        "client",
        "; ".join(engineless_wiring)
        + "; the configuration lambdas call: "
        + "; ".join(
            f"`{name}` -> "
            + ", ".join(
                f"`{short(owner)}.{call}`"
                for _, owner, call, _ in invocations(body(probe, name))
                if call in ("install$default", "defaultRequest", "url")
            )
            for name in ("enginelessClient$lambda$0", "enginelessClient$lambda$0$0")
        ),
    )
    for entry in ran:
        if entry[0] == "ENGINELESS":
            _, label, base, relative, engine, result = entry
            emit(
                f"`DefaultRequest` join on an engine-less `HttpClient {{ … }}`: {label} (k)",
                "client",
                f'the factory chose `{engine}`; base `{base}`, call `get("{relative}")` -> '
                f"Ktor sent `{result}`",
            )
    for entry in ran:
        if entry[0] == "QUERY":
            _, label, base, relative, result = entry
            emit(
                f"`DefaultRequest` join: a query and nothing else, {label} (k)",
                "client",
                f'base `{base}`, call `get("{relative}")` -> Ktor sent `{result}`',
            )

    # (l) the DefaultRequest plugin installed with `install(…)`
    installs = []
    plugin = "NONE"
    for step in body(module[INSTALL], "installedClient$lambda$0"):
        if step.opcode == "getstatic":
            plugin = step.comment.removeprefix("Field ")
        match = re.match(r"(?:Interface)?Method (\S+)\.(\S+?):(\S+)", step.comment)
        if step.opcode.startswith("invoke") and match and "install" in match.group(2):
            installs.append(
                f"`{short(match.group(1).replace('/', '.'))}.{match.group(2)}` "
                f"`{match.group(3)}` after `getstatic {plugin}`"
            )
    emit(
        "how `install(WebSockets)` and `install(DefaultRequest) { url(…) }` compile, from a "
        "client's configuration lambda (l)",
        "client",
        "; ".join(installs) or "NO install CALL FOUND",
    )
    for entry in ran:
        if entry[0] == "INSTALLED":
            _, label, base, relative, result = entry
            emit(
                f"`DefaultRequest` join: the plugin installed as {label} (l)",
                "client",
                f'base `{base}`, call `get("{relative}")` -> Ktor sent `{result}`',
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
