"""CP-59: javap readings of Spring's application-event API and the fixture's bytecode. See run.sh."""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

ARGS = dict(a.split("=", 1) for a in sys.argv[1:])
FIX, JAVA_HOME = Path(ARGS["FIX"]), ARGS["JAVA_HOME"]
CLASSPATH = (FIX / "target/probe.cp").read_text().strip()
CLASSES = str(FIX / "target/classes")

# The artifacts whose types the catalog names, by jar file-name stem.
ARTIFACTS = ("spring-context", "spring-tx")


def javap(*flags_and_class: str) -> str:
    out = subprocess.run(
        [
            f"{JAVA_HOME}/bin/javap",
            *flags_and_class[:-1],
            "-cp",
            f"{CLASSES}:{CLASSPATH}",
            flags_and_class[-1],
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if out.returncode != 0:
        sys.exit(f"javap failed on {flags_and_class[-1]}: {out.stderr}")
    return out.stdout


def reported_versions() -> dict[str, str]:
    """Each artifact's `Implementation-Version`, read from its own MANIFEST.MF (GUIDELINES
    §5.4), never from the pom or the jar's file name. Aborts if a jar or the key is missing."""
    found = {}
    for artifact in ARTIFACTS:
        jars = [
            c
            for c in CLASSPATH.split(":")
            if re.fullmatch(rf"{artifact}-[\d.]+\.jar", Path(c).name)
        ]
        if len(jars) != 1:
            sys.exit(f"expected one {artifact}-*.jar on the classpath, found {jars}")
        with zipfile.ZipFile(jars[0]) as jar:
            manifest = jar.read("META-INF/MANIFEST.MF").decode()
        version = re.search(r"^Implementation-Version: (\S+)", manifest, flags=re.MULTILINE)
        if not version:
            sys.exit(f"{jars[0]}: no Implementation-Version in its manifest")
        found[artifact] = version.group(1)
    return found


def header(cls: str) -> str:
    """The class's declaration line as javap prints it (supertypes, type parameters)."""
    return next(
        line for line in javap("-s", cls).splitlines() if re.search(r"\b(class|interface) ", line)
    ).strip()


def methods(cls: str, name: str) -> list[str]:
    """`descriptor  flags` of every method named `name` (`javap -v`, so flags show bridges)."""
    text = javap("-v", "-p", cls)
    rows, current = [], None
    for line in text.splitlines():
        m = re.match(r"^  (?:[\w$<>\[\]., ]+ )?([\w$<>]+)\(.*\);$", line)
        if m:
            current = {"name": m.group(1), "desc": "", "flags": ""}
            continue
        if current is None:
            continue
        if line.startswith("    descriptor:"):
            current["desc"] = line.split(":", 1)[1].strip()
        elif line.startswith("    flags:"):
            current["flags"] = line.split(":", 1)[1].strip()
            if current["name"] == name:
                rows.append(f"`{current['desc']}` {current['flags']}")
            current = None
    return rows


def annotation_elements(cls: str) -> list[str]:
    """Each element `name() descriptor` of an annotation type."""
    return [
        f"`{m.group(1)}()` `{m.group(2)}`"
        for m in re.finditer(
            r"^  public abstract \S+ (\w+)\(\);\n    descriptor: (\S+)",
            javap("-s", cls),
            flags=re.MULTILINE,
        )
    ]


def class_annotations(cls: str) -> list[str]:
    """The annotations on the type itself (`RuntimeVisibleAnnotations`), as javap decodes them."""
    text = javap("-v", cls)
    block = (
        text.split("RuntimeVisibleAnnotations:")[-1] if "RuntimeVisibleAnnotations:" in text else ""
    )
    return [
        line.strip()
        for line in block.splitlines()
        if re.match(r"^[a-z][\w.]*\.[A-Z]\w*", line.strip()) or line.strip().startswith("value=")
    ]


def super_class(cls: str) -> str:
    m = re.search(r"super_class: #\d+\s+// (\S+)", javap("-v", cls))
    return m.group(1) if m else "-"


def invokes(cls: str, name: str) -> list[str]:
    """Each call to `name` in `cls`'s bytecode: the invoke instruction, owner and descriptor."""
    return [
        f"`{m.group(1)}` `{m.group(2)}.{name}:{m.group(3)}`"
        for m in re.finditer(
            rf"(invoke\w+)\s+#\d+(?:,\s+\d+)?\s+// (?:Interface)?Method ([\w/$]+)\.{name}:(\S+)",
            javap("-c", "-p", cls),
        )
    ]


def decision(cls: str, method: str) -> list[str]:
    """The instructions of one method of `cls` that decide what it returns: every branch,
    call, `new` and `athrow`, in order, as javap prints them (the method that decides which
    event type a listener method registers)."""
    text = javap("-c", "-p", cls)
    body = re.search(rf"\n  [^\n]*\b{method}\([^\n]*\n(.*?)\n\n", text, flags=re.DOTALL)
    if not body:
        return ["NOT FOUND"]
    keep = re.compile(r"^\s+\d+: (invoke\w+|if\w*|new|athrow|areturn)\b")
    return [
        re.sub(r"\s+", " ", line.strip()) for line in body.group(1).splitlines() if keep.match(line)
    ]


def main() -> None:
    versions = reported_versions()
    print("### Identity (from each jar's own MANIFEST.MF)\n")
    for artifact, version in versions.items():
        print(f"- `{artifact}`: `Implementation-Version: {version}`")
    print()
    print("### 1. Sends\n")
    print(f"| owner `publishEvent` | {versions['spring-context']} |")
    print("|---|---|")
    for cls in ("org.springframework.context.ApplicationEventPublisher",):
        for row in methods(cls, "publishEvent"):
            print(f"| `{cls}` | {row} |")
    print()
    print("### 2. Who inherits `publishEvent`\n")
    for cls in (
        "org.springframework.context.ApplicationContext",
        "org.springframework.context.ConfigurableApplicationContext",
        "org.springframework.context.support.AbstractApplicationContext",
    ):
        print(f"- {header(cls)}")
    print()
    print("### 3. How the listener's event type is read\n")
    adapter = "org.springframework.context.event.ApplicationListenerMethodAdapter"
    print(f"`{adapter.rsplit('.', 1)[-1]}.resolveDeclaredEventTypes(Method, EventListener)`:\n")
    for item in decision(adapter, "resolveDeclaredEventTypes"):
        print(f"- `{item}`")
    print()
    print("### 4. The listener annotations\n")
    for cls in (
        "org.springframework.context.event.EventListener",
        "org.springframework.transaction.event.TransactionalEventListener",
    ):
        print(f"#### `{cls}`\n")
        print("- elements: " + ", ".join(annotation_elements(cls)))
        for line in class_annotations(cls):
            print(f"- on the type: `{line}`")
        print()
    print("### 5. The interface form\n")
    print(f"- {header('org.springframework.context.ApplicationListener')}")
    for row in methods("org.springframework.context.ApplicationListener", "onApplicationEvent"):
        print(f"- `ApplicationListener.onApplicationEvent` {row}")
    for row in methods("com.acme.events.MailListener", "onApplicationEvent"):
        print(f"- fixture `MailListener.onApplicationEvent` {row}")
    print()
    print("### 6. The root of an event's ancestry\n")
    print(
        f"- `org.springframework.context.ApplicationEvent` super_class: `{super_class('org.springframework.context.ApplicationEvent')}`"
    )
    print(f"- `java.util.EventObject` super_class: `{super_class('java.util.EventObject')}`")
    print()
    print("### 7. What javac writes at the fixture's publish sites\n")
    for row in invokes("com.acme.events.OrderService", "publishEvent"):
        print(f"- `OrderService`: {row}")


main()
