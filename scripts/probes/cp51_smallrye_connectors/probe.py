"""CP-51: what each SmallRye Reactive Messaging connector is called, what it speaks, every
attribute it declares (direction, name, default), and which attribute names the destination
with the channel name as its fallback. Every cell is read off the jars — `javap -v` for the
annotation data and the bytecode, `jdeps` for the packages a jar uses; the version in each
column is the jar's own manifest. Prints the observation tables
`cp51_smallrye_connectors.md` carries."""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _jvm_annotations import (
    Annotation,
    ClassFile,
    ProbeError,
    body,
    classes,
    identity,
    jar_at,
    lambda_targets,
    pom_at,
    pom_dependencies,
)
from _spring_jar import HOME

GROUP = "io.smallrye.reactive"
VERSION = "4.25.0"
CONNECTORS = ["kafka", "amqp", "rabbitmq", "pulsar", "jms", "aws-sqs"]
CONNECTOR = "org.eclipse.microprofile.reactive.messaging.spi.Connector"
ATTRIBUTES = "io.smallrye.reactive.messaging.annotations.ConnectorAttributes"
ATTRIBUTE = "io.smallrye.reactive.messaging.annotations.ConnectorAttribute"
# The Quarkus extensions whose poms are read for the coordinate that brings a connector in.
QUARKUS = ("io.quarkus", "3.17.5", ["kafka", "amqp", "rabbitmq", "pulsar", "jms", "aws-sqs"])
# Packages every connector uses whatever it speaks — the JDK, CDI and its annotations, the
# SmallRye/MicroProfile/Mutiny/Vert.x-core framework itself, logging, tracing, Netty, JSON and
# Guava — left out so what remains is the messaging client the connector drives.
INFRASTRUCTURE = re.compile(
    r"^(?:java|javax|jdk|sun|jakarta\.(?:annotation|enterprise|inject)|io\.smallrye|"
    r"org\.eclipse\.microprofile|io\.vertx\.(?:core|mutiny\.core)|io\.vertx\.mutiny\.core|"
    r"org\.jboss\.logging|io\.opentelemetry|io\.netty|com\.fasterxml|com\.google)(?:\.|$)"
)
_GETTER = re.compile(r"Method ([\w/$]*Connector\w*Configuration)\.(get\w+):\(\)(\S+)")


def getter(attribute: str) -> str:
    """The accessor SmallRye's generated `*Connector*Configuration` declares for an attribute:
    each `.`- or `-`-separated part capitalised."""
    return "get" + "".join(part[:1].upper() + part[1:] for part in re.split(r"[.\-]", attribute))


def declared(cls: ClassFile) -> list[Annotation]:
    container = cls.annotation(ATTRIBUTES)
    if container is not None:
        value = container.elements.get("value", [])
        return [a for a in value if isinstance(a, Annotation)] if isinstance(value, list) else []
    single = cls.annotation(ATTRIBUTE)
    return [single] if single is not None else []


def client_packages(jar: Path) -> list[str]:
    result = subprocess.run(
        [str(HOME / "bin" / "jdeps"), "-verbose:package", "--multi-release", "21", str(jar)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"jdeps {jar.name} failed: {result.stderr.strip()}")
    used = {
        parts[2]
        for parts in (line.split() for line in result.stdout.splitlines())
        if len(parts) >= 3 and parts[1] == "->" and not parts[0].endswith(".jar")
    }
    return sorted(p for p in used if not INFRASTRUCTURE.match(p) and not p.startswith("not"))


def channel_fallbacks(parsed: dict[str, ClassFile], names: dict[str, str]) -> list[str]:
    """`config.get<X>().orElse(<the channel>)` / `.orElseGet(<the channel>)`: an Optional
    attribute accessor whose fallback, within the next eight instructions and before any other
    attribute accessor, is `getChannel()`, a `String channel` field, or a method reference /
    lambda whose target is `getChannel`."""
    found: dict[str, set[str]] = {}
    for cls in parsed.values():
        for member in cls.members:
            if "(" not in member.header:
                continue
            steps = body(cls, member.name)
            for i, step in enumerate(steps):
                accessor = _GETTER.search(step.comment)
                if not accessor or not accessor.group(3).startswith("Ljava/util/Optional"):
                    continue
                window = steps[i + 1 : i + 9]
                end = next(
                    (
                        j
                        for j, s in enumerate(window)
                        if re.search(r"Optional\.orElse(?:Get)?:", s.comment)
                    ),
                    None,
                )
                if end is None:
                    continue
                between = window[:end]
                if any(
                    _GETTER.search(s.comment) and "getChannel:" not in s.comment for s in between
                ):
                    continue
                how = None
                if any("getChannel:()" in s.comment for s in between):
                    how = "`getChannel()`"
                elif any(
                    s.opcode == "getfield"
                    and re.search(r"Field channel:Ljava/lang/String;", s.comment)
                    for s in between
                ):
                    how = "field `channel`"
                elif any(t.endswith(".getChannel") for t in lambda_targets(cls, between)):
                    how = "`::getChannel`"
                if how is None:
                    continue
                attribute = names.get(accessor.group(2), f"? ({accessor.group(2)})")
                simple = cls.name.rsplit(".", 1)[-1]
                where = f"{simple}.{'<init>' if member.name == simple else member.name}"
                found.setdefault(f"`{attribute}`", set()).add(f"{where} via {how}")
    return [f"{attr} ({'; '.join(sorted(where))})" for attr, where in sorted(found.items())]


def extension_poms(artifact: str) -> list[str]:
    group, version, extensions = QUARKUS
    declaring = []
    for extension in extensions:
        pom = pom_at(group, f"quarkus-messaging-{extension}", version)
        if pom is not None and f"{GROUP}:{artifact}" in pom_dependencies(pom):
            declaring.append(f"`{group}:quarkus-messaging-{extension}:{version}`")
    return declaring


def cell(value: object) -> str:
    return str(value).replace("|", "\\|") if value is not None else ""


def literal(value: object) -> str:
    """A declared value as code, an empty string shown as `""` rather than as nothing."""
    return f"`{cell(value)}`" if value != "" else '`""`'


def main() -> int:
    measured: list[tuple[str, Path, str]] = []
    for name in CONNECTORS:
        artifact = f"smallrye-reactive-messaging-{name}"
        jar = jar_at(GROUP, artifact, VERSION)
        if jar is None:
            print(
                f"NOT MEASURED: {GROUP}:{artifact}:{VERSION} not in the local repository",
                file=sys.stderr,
            )
            continue
        measured.append((artifact, jar, identity(jar, VERSION)[0]))
    if not measured:
        return 1

    api = jar_at(GROUP, "smallrye-reactive-messaging-api", VERSION)
    if api is None:
        print(
            f"NOT IN THE LOCAL REPOSITORY: {GROUP}:smallrye-reactive-messaging-api:{VERSION}",
            file=sys.stderr,
        )
        return 1
    measured.append(("smallrye-reactive-messaging-api", api, identity(api, VERSION)[0]))
    annotation = classes(api, [ATTRIBUTE])[ATTRIBUTE]
    defaults = {m.name: m.default for m in annotation.members if m.default is not None}

    columns = sorted({stated for _, _, stated in measured})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(f"{GROUP}:{a}" for a, _, s in measured if s == column) for column in columns
        )
        + " |"
    )
    print(
        "| where the jar states that version | "
        + " | ".join("MANIFEST.MF `Implementation-Version`" for _ in columns)
        + " |"
    )
    present = {a for a, _, _ in measured}
    missing = [n for n in CONNECTORS if f"smallrye-reactive-messaging-{n}" not in present]
    for name in missing:
        print(
            f"| `{GROUP}:smallrye-reactive-messaging-{name}` | NOT MEASURED — not in the "
            "local repository |"
        )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    attribute_rows: list[str] = []
    row = 1
    print(
        f"| {row} | what a member a `@ConnectorAttribute` leaves out reads as | "
        f"`{GROUP}:smallrye-reactive-messaging-api` | {measured[-1][2]} | "
        + "; ".join(f"`{name}()` defaults to `{value}`" for name, value in defaults.items())
        + " |"
    )
    for artifact, jar, stated in measured[:-1]:
        parsed = classes(jar)
        connectors = [cls for cls in parsed.values() if cls.annotation(CONNECTOR) is not None]
        for cls in connectors:
            connector = cls.annotation(CONNECTOR)
            assert connector is not None
            name = str(connector.elements.get("value"))
            interfaces = re.search(r" implements ([\w.$, ]+)", cls.declaration)
            implemented = [
                i.strip().rsplit(".", 1)[-1]
                for i in (interfaces.group(1).split(",") if interfaces else [])
            ]
            attributes = declared(cls)
            directions: dict[str, int] = {}
            for attribute in attributes:
                direction = str(attribute.elements.get("direction"))
                directions[direction] = directions.get(direction, 0) + 1
            row += 1
            print(
                f"| {row} | what the connector is | `{GROUP}:{artifact}` | {stated} | "
                f'`{cls.name}`: `@Connector("{name}")`; implements '
                f"`{'`, `'.join(implemented)}`; declares {len(attributes)} `@ConnectorAttribute`s "
                f"({', '.join(f'{d} {n}' for d, n in sorted(directions.items()))}) |"
            )
            row += 1
            print(
                f"| {row} | what it speaks (packages it uses beyond the framework's own) | "
                f"`{GROUP}:{artifact}` | {stated} | `{'`, `'.join(client_packages(jar))}` |"
            )
            stated_fallback = [
                f"`{a.elements['name']}` ({a.elements.get('direction')}): "
                f'"{cell(a.elements.get("description"))}"'
                for a in attributes
                if "channel name" in str(a.elements.get("description", "")).lower()
            ]
            row += 1
            print(
                f"| {row} | which attributes say the channel name is their fallback (their own "
                f"`description`) | `{GROUP}:{artifact}` | {stated} | "
                f"{'; '.join(stated_fallback) or 'none'} |"
            )
            names = {getter(str(a.elements["name"])): str(a.elements["name"]) for a in attributes}
            names["getChannel"] = "channel"
            fallbacks = channel_fallbacks(parsed, names)
            row += 1
            print(
                f"| {row} | which attributes fall back to the channel name in the bytecode "
                f"(`get<X>().orElse/orElseGet(<the channel>)`) | `{GROUP}:{artifact}` | {stated} | "
                f"{'; '.join(fallbacks) or 'none found'} |"
            )
            poms = extension_poms(artifact)
            row += 1
            print(
                f"| {row} | which Quarkus extension declares this artifact | "
                f"`{GROUP}:{artifact}` | {stated} | "
                + (
                    ", ".join(poms)
                    if poms
                    else f"no `{QUARKUS[0]}:quarkus-messaging-*:{QUARKUS[1]}` pom in the local "
                    "repository declares it"
                )
                + " |"
            )
            for attribute in attributes:
                e = attribute.elements
                attribute_rows.append(
                    f"| `{name}` | {e.get('direction')} | `{cell(e.get('name'))}` | "
                    f"{cell(e.get('type'))} | "
                    + (literal(e["defaultValue"]) if "defaultValue" in e else "—")
                    + f" | {cell(e.get('mandatory', defaults.get('mandatory')))} | "
                    + (f"`{cell(e['alias'])}`" if "alias" in e else "—")
                    + f" | {cell(e.get('deprecated', defaults.get('deprecated')))} |"
                )
        if not connectors:
            row += 1
            print(
                f"| {row} | what the connector is | `{GROUP}:{artifact}` | {stated} | "
                f"no class carries `@{CONNECTOR}` |"
            )

    print()
    print(
        "| connector | direction | attribute | type | `defaultValue` (— = not declared) | "
        "mandatory | alias (— = not declared) | deprecated |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for line in attribute_rows:
        print(line)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ProbeError as error:
        print(f"CP-51 aborted: {error}", file=sys.stderr)
        sys.exit(1)
