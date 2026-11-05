"""CP-59: javap readings of Spring's application-event API, the CDI event API and ArC, and the
two fixtures' bytecode. See run.sh."""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

ARGS = dict(a.split("=", 1) for a in sys.argv[1:])
FIX, JAVA_HOME = Path(ARGS["FIX"]), ARGS["JAVA_HOME"]
CLASSPATH = (FIX / "target/probe.cp").read_text().strip()
CLASSES = str(FIX / "target/classes")
CDI_FIX = Path(ARGS["CDI_FIX"])
[JAVAX_JAR] = [str(jar) for jar in (CDI_FIX / "target/probe-javax").glob("cdi-api-*.jar")]
[JAVAX2_JAR] = [str(jar) for jar in (CDI_FIX / "target/probe-javax2").glob("cdi-api-*.jar")]
CDI_CLASSPATH = f"{CDI_FIX / 'target/classes'}:{(CDI_FIX / 'target/probe.cp').read_text().strip()}"

# The artifacts whose types the catalog names, by jar file-name stem.
ARTIFACTS = ("spring-context", "spring-tx")


def javap(*flags_and_class: str, cp: str = "") -> str:
    out = subprocess.run(
        [
            f"{JAVA_HOME}/bin/javap",
            *flags_and_class[:-1],
            "-cp",
            cp or f"{CLASSES}:{CLASSPATH}",
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


def manifest_version(jar: str, keys: tuple[str, ...]) -> str:
    """The first of `keys` the jar's own MANIFEST.MF states (GUIDELINES §5.4); aborts if it
    states none. The Jakarta CDI API jar states only the OSGi `Bundle-Version`."""
    with zipfile.ZipFile(jar) as archive:
        manifest = archive.read("META-INF/MANIFEST.MF").decode()
    for key in keys:
        version = re.search(rf"^{key}: (\S+)", manifest, flags=re.MULTILINE)
        if version:
            return f"{key}: {version.group(1)}"
    sys.exit(f"{jar}: none of {keys} in its manifest")


def cdi_jar(artifact: str) -> str:
    """The one `<artifact>-<version>.jar` on the CDI fixture's class path."""
    jars = [
        c
        for c in CDI_CLASSPATH.split(":")
        if re.fullmatch(rf"{artifact}-[\d.]+\.jar", Path(c).name)
    ]
    if len(jars) != 1:
        sys.exit(f"expected one {artifact}-*.jar on the CDI class path, found {jars}")
    return jars[0]


def header(cls: str) -> str:
    """The class's declaration line as javap prints it (supertypes, type parameters)."""
    return next(
        line for line in javap("-s", cls).splitlines() if re.search(r"\b(class|interface) ", line)
    ).strip()


def methods(cls: str, name: str, cp: str = "") -> list[str]:
    """`descriptor  flags` of every method named `name` (`javap -v`, so flags show bridges)."""
    text = javap("-v", "-p", cls, cp=cp)
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


def class_annotations(cls: str, cp: str = "") -> list[str]:
    """The annotations on the type itself (`RuntimeVisibleAnnotations`), as javap decodes them."""
    text = javap("-v", cls, cp=cp)
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


def invokes(cls: str, name: str, cp: str = "") -> list[str]:
    """Each call to `name` in `cls`'s bytecode: the invoke instruction, owner and descriptor."""
    return [
        f"`{m.group(1)}` `{m.group(2)}.{name}:{m.group(3)}`"
        for m in re.finditer(
            rf"(invoke\w+)\s+#\d+(?:,\s+\d+)?\s+// (?:Interface)?Method ([\w/$]+)\.{name}:(\S+)",
            javap("-c", "-p", cls, cp=cp),
        )
    ]


def parameter_annotations(cls: str, cp: str) -> list[str]:
    """Each method of `cls` with `RuntimeVisibleParameterAnnotations`: its descriptor and the
    annotation on each parameter, as javap decodes them."""
    rows, method = [], None
    for line in javap("-v", "-p", cls, cp=cp).splitlines():
        if line.startswith("    descriptor:"):
            method = line.split(":", 1)[1].strip()
        elif re.match(r"^      parameter \d+:", line):
            rows.append([method, line.strip().rstrip(":"), "-"])
        elif re.match(r"^          [a-z][\w.]*\.[A-Z]\w*$", line) and rows:
            rows[-1][2] = line.strip()
    return [f"`{m}` {p}: `{a}`" for m, p, a in rows]


def lines_matching(cls: str, declared: str, pattern: str, cp: str) -> list[str]:
    """The instructions matching `pattern`, in order, as javap prints them, of the one method of
    `cls` whose declaration line contains `declared` (`notify(T, ` tells two overloads apart)."""
    text = javap("-c", "-p", cls, cp=cp)
    body = re.search(
        rf"\n  [^\n]*{re.escape(declared)}[^\n]*\n(.*?)\n(?:\n|}})", text, flags=re.DOTALL
    )
    if not body:
        return ["NOT FOUND"]
    return [
        re.sub(r"\s+", " ", line.strip())
        for line in body.group(1).splitlines()
        if re.search(pattern, line)
    ]


def bootstrap_handles(cls: str, cp: str) -> list[str]:
    """The method handle each lambda bootstrap of `cls` names (`javap -v`)."""
    text = javap("-v", "-p", cls, cp=cp)
    block = text.split("BootstrapMethods:")[-1]
    return [
        f"{m.group(1)}: `{m.group(2)}`"
        for m in re.finditer(
            r"^  (\d+): #\d+ REF_invokeStatic java/lang/invoke/LambdaMetafactory"
            r"[^\n]*\n    Method arguments:\n[^\n]*\n\s+#\d+ (REF_\w+ \S+)",
            block,
            flags=re.MULTILINE,
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
    print(
        "- fixture `com.acme.events.OrderShipped` super_class: "
        f"`{super_class('com.acme.events.OrderShipped')}`"
    )
    print()
    print("### 7. What javac writes at the fixture's publish sites\n")
    for row in invokes("com.acme.events.OrderService", "publishEvent"):
        print(f"- `OrderService`: {row}")
    print()
    cdi(versions)


def cdi(spring_versions: dict[str, str]) -> None:
    """Tables 8-11: CDI events (`cdi-events`, `cdi-async-events`)."""
    del spring_versions
    cp, javax = CDI_CLASSPATH, JAVAX_JAR
    jakarta_api, arc = cdi_jar("jakarta.enterprise.cdi-api"), cdi_jar("arc")
    print("### Identity, CDI (from each jar's own MANIFEST.MF)\n")
    print(
        f"- `jakarta.enterprise.cdi-api`: `{manifest_version(jakarta_api, ('Implementation-Version', 'Bundle-Version'))}`"
    )
    print(f"- `javax.enterprise:cdi-api`: `{manifest_version(javax, ('Implementation-Version',))}`")
    # cdi-api 2.0's `Implementation-Version` is an unexpanded `${parsedVersion.osgiVersion}`;
    # its `Bundle-Version` is the version it states.
    print(
        f"- `javax.enterprise:cdi-api` (2.x): `{manifest_version(JAVAX2_JAR, ('Bundle-Version',))}`"
    )
    print(f"- `arc`: `{manifest_version(arc, ('Implementation-Version',))}`")
    print()
    print("### 8. Sends: `Event`\n")
    for name in ("fire", "fireAsync"):
        for row in methods("jakarta.enterprise.event.Event", name, cp=cp):
            print(f"- `jakarta.enterprise.event.Event.{name}` {row}")
    for label, path in (("1.0.0", javax), ("2.0.0", JAVAX2_JAR)):
        for name in ("fire", "fireAsync"):
            rows = methods("javax.enterprise.event.Event", name, cp=path)
            for row in rows or ["none"]:
                print(f"- `javax.enterprise.event.Event.{name}` ({label}) {row}")
    print()
    print("### 9. The observer annotations, and where javac writes them\n")
    for cls, path in (
        ("jakarta.enterprise.event.Observes", cp),
        ("jakarta.enterprise.event.ObservesAsync", cp),
        ("javax.enterprise.event.Observes", javax),
        ("javax.enterprise.event.ObservesAsync", JAVAX2_JAR),
    ):
        print(f"#### `{cls}`\n")
        for line in class_annotations(cls, cp=path):
            print(f"- on the type: `{line}`")
        print()
    for cls in ("StartupObserver", "AsyncObserver"):
        for row in parameter_annotations(f"com.acme.shipping.{cls}", cp):
            print(f"- fixture `{cls}`: {row}")
    print()
    print("### 10. Which observers ArC notifies\n")
    impl = "io.quarkus.arc.impl.EventImpl"
    print("`EventImpl.fire(Object)`:\n")
    for item in lines_matching(impl, " fire(", r"iconst|Notifier\.notify", cp):
        print(f"- `{item}`")
    print("\n`EventImpl$1.get()` (the supplier `fireAsync` runs):\n")
    for item in lines_matching(f"{impl}$1", " get(", r"iconst|Notifier\.notify", cp):
        print(f"- `{item}`")
    print(
        "\n`EventImpl$Notifier.notify(Object, ObserverExceptionHandler, boolean)`, up to the filter:\n"
    )
    for item in lines_matching(
        f"{impl}$Notifier", " notify(T, ", r"^\s+(7|8|11|16|19|24|27): ", cp
    ):
        print(f"- `{item}`")
    print("\n`EventImpl$Notifier` lambda bootstraps:\n")
    for item in bootstrap_handles(f"{impl}$Notifier", cp):
        print(f"- {item}")
    print()
    print("### 11. What javac writes at the fixture's fire sites\n")
    for name in ("fire", "fireAsync"):
        for row in invokes("com.acme.shipping.ShippingService", name, cp=cp):
            print(f"- `ShippingService`: {row}")


main()
