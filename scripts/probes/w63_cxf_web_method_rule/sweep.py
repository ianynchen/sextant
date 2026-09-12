"""W63 — does Apache CXF's JAX-WS frontend decide "which public method is an
operation" the way the reference implementation does (CP-13, jaxws-rt 4.0.2:
inherited public methods included, `static`/`final` excluded, `@WebMethod(exclude
= true)` honoured)?

`jakarta-jws.yml`'s `members: public_methods` rule and its `A-Mi7` comment both
name Apache CXF as the OTHER JAX-WS implementation in wide use, unmeasured. CXF
decides operation membership in
`org.apache.cxf.jaxws.support.JaxWsServiceConfiguration.isOperation(Method)`,
which the task brief says delegates to
`org.apache.cxf.service.factory.ReflectionServiceFactoryBean` /
`AbstractServiceConfiguration`. Both names are wrong at 4.0.5: `unzip -l` on
`cxf-core-4.0.5.jar` shows no such package at all, and `mvn dependency:tree`
off `cxf-rt-frontend-jaxws:4.0.5` finds them one hop further, repackaged as
`org.apache.cxf.wsdl.service.factory.{AbstractServiceConfiguration,
ReflectionServiceFactoryBean}` in `cxf-rt-wsdl` — a transitive dependency of
`cxf-rt-frontend-jaxws` through `cxf-rt-bindings-soap`, not of `cxf-core`. This
sweep fetches all four artifacts the two names actually resolve to and records
which one carries what, rather than silently substituting the brief's assumed
package.

**Version scope (§5.4).** Read against **cxf-rt-frontend-jaxws 4.0.5 and
cxf-core 4.0.5**, plus `cxf-rt-wsdl 4.0.5` (where the classes the brief named
actually live) and `jakarta.jws-api 3.0.0` (the annotations both `isOperation`
paths read). `fixtures/orders-service` has no CXF dependency of its own — this
task is the first to introduce one, kept to `scripts/probes/` rather than
mixed into the shipped fixture tree.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
M2 = Path.home() / ".m2" / "repository"


class ProbeError(RuntimeError):
    """Anything that would otherwise put an unmeasured cell in a table."""


# ---------------------------------------------------------------------------
# Resolving jars and checking what they say about themselves (§5.4).
# ---------------------------------------------------------------------------


def resolve(artifact: str) -> Path:
    group, name, version = artifact.split(":")
    jar = M2 / Path(group.replace(".", "/")) / name / version / f"{name}-{version}.jar"
    if not jar.is_file():
        subprocess.run(
            ["mvn", "-q", "-B", "dependency:get", "-Dtransitive=false", f"-Dartifact={artifact}"],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
    if not jar.is_file():
        raise ProbeError(f"{artifact} did not resolve; fix the coordinate in run.sh")
    return jar


def self_reported_version(jar: Path) -> tuple[str, str]:
    """The version the jar records about ITSELF, out of its own Maven
    `pom.properties` or, failing that, its manifest's `Implementation-Version` —
    the same two-rung read `w61`/`w62` use, in the same order."""
    with zipfile.ZipFile(jar) as archive:
        entries = [
            name
            for name in archive.namelist()
            if name.startswith("META-INF/maven/") and name.endswith("/pom.properties")
        ]
        if entries:
            for line in archive.read(entries[0]).decode("utf-8", "replace").splitlines():
                if line.strip().startswith("version="):
                    return line.split("=", 1)[1].strip(), "pom.properties"
        try:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError:
            manifest = ""
        for line in manifest.splitlines():
            if line.lower().startswith("implementation-version:"):
                return line.split(":", 1)[1].strip(), "MANIFEST.MF"
    raise ProbeError(f"{jar.name} states no version in its pom.properties nor its manifest")


def checked(artifact: str) -> tuple[Path, str, str]:
    jar = resolve(artifact)
    reported, source = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own {source} while the coordinate asked "
            f"for {requested!r}."
        )
    return jar, reported, source


ARTIFACTS = (
    "org.apache.cxf:cxf-rt-frontend-jaxws:4.0.5",
    "org.apache.cxf:cxf-core:4.0.5",
    "org.apache.cxf:cxf-rt-wsdl:4.0.5",
    "jakarta.jws:jakarta.jws-api:3.0.0",
)

# (artifact, internal class name) for every class this sweep reads, keyed by
# the SHORT name the tables below refer to it by.
CLASSES: dict[str, tuple[str, str]] = {
    "JaxWsServiceConfiguration": (
        "org.apache.cxf:cxf-rt-frontend-jaxws:4.0.5",
        "org/apache/cxf/jaxws/support/JaxWsServiceConfiguration",
    ),
    "JaxWsImplementorInfo": (
        "org.apache.cxf:cxf-rt-frontend-jaxws:4.0.5",
        "org/apache/cxf/jaxws/support/JaxWsImplementorInfo",
    ),
    "AbstractServiceConfiguration": (
        "org.apache.cxf:cxf-rt-wsdl:4.0.5",
        "org/apache/cxf/wsdl/service/factory/AbstractServiceConfiguration",
    ),
    "ReflectionServiceFactoryBean": (
        "org.apache.cxf:cxf-rt-wsdl:4.0.5",
        "org/apache/cxf/wsdl/service/factory/ReflectionServiceFactoryBean",
    ),
}

# Every method this sweep prints a row for: (class key, method name, a
# disambiguator for an overload, or "" when there is only one).
METHODS = (
    ("AbstractServiceConfiguration", "isOperation", ""),
    ("JaxWsServiceConfiguration", "isOperation", ""),
    ("JaxWsServiceConfiguration", "isWebMethod", "(Method)"),
    ("JaxWsServiceConfiguration", "hasWebServiceAnnotation", ""),
    ("JaxWsServiceConfiguration", "getDeclaredMethod", "(Class, Method)"),
    ("ReflectionServiceFactoryBean", "isValidMethod", ""),
    ("ReflectionServiceFactoryBean", "createInterface", ""),
)


def _javap(jar: Path, internal: str) -> str:
    with tempfile.TemporaryDirectory() as into:
        try:
            with zipfile.ZipFile(jar) as archive:
                archive.extract(f"{internal}.class", into)
        except KeyError as missing:
            raise ProbeError(f"{jar.name} does not carry {internal}") from missing
        completed = subprocess.run(
            ["javap", "-p", "-c", str(Path(into) / f"{internal}.class")],
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise ProbeError(f"javap failed on {internal}: {completed.stderr.strip()}")
    return completed.stdout


# A method header line, as `javap -p -c` prints it: some access modifiers, a
# return type, a name, a parenthesised parameter list, ending `;`. Deliberately
# excludes `static {};` (no return type before the name) and the `Code:` /
# instruction lines that follow.
_METHOD_HEADER = re.compile(
    r"^  (?:public |protected |private )?(?:static |final |abstract |synchronized )*"
    r"[\w.$<>\[\]?, ]+? (\w+)\(([^)]*)\);$"
)
_INVOKE_LINE = re.compile(
    r"^\s+\d+: (invoke\w+)\s+(?:#\d+(?:,\s*\d+)?)\s*//\s*((?:Interface)?Method\s+\S+)"
)


def _method_blocks(text: str) -> list[tuple[str, str, str]]:
    """`(method name, raw parameter list, body text)` for every method
    `javap -p -c` printed, split on the next header or `static {};`."""
    lines = text.splitlines()
    headers = [
        (i, match.group(1), match.group(2))
        for i, line in enumerate(lines)
        if (match := _METHOD_HEADER.match(line))
    ]
    blocks = []
    for index, (start, name, params) in enumerate(headers):
        end = headers[index + 1][0] if index + 1 < len(headers) else len(lines)
        blocks.append((name, params, "\n".join(lines[start:end])))
    return blocks


def invoke_sequence(jar: Path, internal: str, method: str, disambiguator: str) -> str:
    """The `invokestatic`/`invokevirtual`/`invokeinterface` targets `method`
    calls, in bytecode order, as `kind Method-or-InterfaceMethod fqn:descriptor`
    joined by ` ; ` — empty when the body calls nothing at all (the base
    class's own `isOperation`, which is `aconst_null; areturn`)."""
    text = _javap(jar, internal)
    candidates = [block for block in _method_blocks(text) if block[0] == method]
    if not candidates:
        raise ProbeError(f"{internal.replace('/', '.')} has no method named {method}")
    if len(candidates) > 1:
        if not disambiguator:
            raise ProbeError(
                f"{internal.replace('/', '.')}#{method} is overloaded; "
                "add a disambiguator to METHODS"
            )
        # `disambiguator` is a hand-written rendering of the parameter list
        # ("(Class, Method)") — matched by whichever candidate's own
        # parameter count agrees, since `javap -p -c`'s param list is fully
        # qualified and would have to be restated verbatim otherwise.
        param_count = disambiguator.count(",") + 1
        candidates = [c for c in candidates if len(c[1].split(",")) == param_count] or candidates
    _, _, body = candidates[0]
    calls = [
        f"{kind} {target}"
        for line in body.splitlines()
        if (m := _INVOKE_LINE.match(line))
        for kind, target in [m.groups()]
    ]
    return " ; ".join(calls)


# ---------------------------------------------------------------------------
# The live cross-check: build BillingWebService/AbstractBilling, boot a real
# `JaxWsServiceFactoryBean` over them, and read what CXF's own service model
# produced — the same role CP-13 Q5's compile-and-run played where a bytecode
# reading needed independent confirmation.
# ---------------------------------------------------------------------------


def live_operations() -> list[str]:
    """Everything this needs beyond `fixture/*.java` and `fixture/pom.xml` — the
    resolved classpath, the compiled classes — is built in a scratch directory
    and never written into the committed fixture, the same discipline CP-13's
    Q5 uses for its own compile-and-run (`tempfile.TemporaryDirectory`)."""
    fixture = HERE / "fixture"
    with tempfile.TemporaryDirectory() as scratch_name:
        scratch = Path(scratch_name)
        classpath_file = scratch / "cp.txt"
        subprocess.run(
            [
                "mvn",
                "-q",
                "-B",
                "-f",
                str(fixture / "pom.xml"),
                "dependency:build-classpath",
                f"-Dmdep.outputFile={classpath_file}",
            ],
            capture_output=True,
            check=False,
        )
        if not classpath_file.is_file() or not classpath_file.read_text().strip():
            raise ProbeError(
                "fixture/pom.xml's classpath did not resolve; the live cross-check needs "
                "network access to CXF's full transitive dependency set (jaxb, woodstox, "
                "xmlschema...), not just the two coordinates javap reads"
            )
        classpath = classpath_file.read_text().strip()
        out_dir = scratch / "out"
        out_dir.mkdir()
        sources = sorted(str(p) for p in fixture.glob("*.java"))
        compiled = subprocess.run(
            ["javac", "-cp", classpath, "-d", str(out_dir), *sources],
            capture_output=True,
            text=True,
            check=False,
        )
        if compiled.returncode != 0:
            raise ProbeError(f"javac failed on the fixture: {compiled.stderr.strip()}")
        ran = subprocess.run(
            ["java", "-cp", f"{out_dir}{os.pathsep}{classpath}", "LiveProbe"],
            capture_output=True,
            text=True,
            check=False,
        )
    if ran.returncode != 0:
        raise ProbeError(f"LiveProbe failed: {ran.stderr.strip()}")
    lines = ran.stdout.splitlines()
    if "W63_LIVE_OPERATIONS_BEGIN" not in lines or "W63_LIVE_OPERATIONS_END" not in lines:
        raise ProbeError(f"LiveProbe printed no markers; stdout was:\n{ran.stdout}")
    start = lines.index("W63_LIVE_OPERATIONS_BEGIN") + 1
    end = lines.index("W63_LIVE_OPERATIONS_END")
    return lines[start:end]


def main() -> None:
    read = {artifact: checked(artifact) for artifact in ARTIFACTS}

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w63_cxf_web_method_rule/run.sh`, which runs")
    print("`sweep.py`. **Every version in the table below is the one the JAR itself")
    print("reported** — out of its own `META-INF/maven/.../pom.properties` —")
    print("and **not the version the coordinate list asked for**; `checked` compares")
    print("the two and ABORTS the whole run when they disagree.\n")

    versions: list[str] = []
    for artifact in read:
        version = artifact.split(":")[2]
        if version not in versions:
            versions.append(version)
    print("| what the run read | " + " | ".join(versions) + " |")
    print("|---|" + "---|" * len(versions))
    for label, pick in (("artifacts reporting this version", 1), ("where the jar states it", 2)):
        cells = []
        for version in versions:
            names = [
                (a.split(":")[1] if pick == 1 else read[a][2])
                for a in read
                if a.split(":")[2] == version
            ]
            cells.append(", ".join(dict.fromkeys(names)))
        print(f"| {label} | " + " | ".join(cells) + " |")
    print()

    print("### Where the brief's two class names actually live at 4.0.5\n")
    print("The task brief names `org.apache.cxf.service.factory.ReflectionServiceFactoryBean`")
    print("/ `AbstractServiceConfiguration` inside `cxf-core`. `unzip -l` on")
    print("`cxf-core-4.0.5.jar` carries no such package. `mvn dependency:tree` off")
    print("`cxf-rt-frontend-jaxws:4.0.5` finds both classes one hop further, repackaged")
    print("as `org.apache.cxf.wsdl.service.factory.*` inside `cxf-rt-wsdl` — pulled in")
    print("transitively through `cxf-rt-bindings-soap`, not through `cxf-core` at all.\n")

    print("| class | brief's assumed location | actual 4.0.5 location |")
    print("|---|---|---|")
    print(
        "| `ReflectionServiceFactoryBean` | `cxf-core` / `org.apache.cxf.service.factory` | "
        "`cxf-rt-wsdl` / `org.apache.cxf.wsdl.service.factory` |"
    )
    print(
        "| `AbstractServiceConfiguration` | `cxf-core` / `org.apache.cxf.service.factory` | "
        "`cxf-rt-wsdl` / `org.apache.cxf.wsdl.service.factory` |"
    )
    print()

    print("### Every inspected method's `invokestatic`/`invokevirtual`/`invokeinterface`")
    print("### targets, in bytecode order\n")
    print("| class | method | calls, in order |")
    print("|---|---|---|")
    for class_key, method, disambiguator in METHODS:
        artifact, internal = CLASSES[class_key]
        jar = read[artifact][0]
        sequence = invoke_sequence(jar, internal, method, disambiguator)
        label = f"{method}{disambiguator}" if disambiguator else method
        cell = sequence if sequence else "*(calls nothing — `aconst_null; areturn`)*"
        print(f"| `{class_key}` | `{label}` | {cell} |")
    print()

    print("### Live cross-check: what CXF's own service model derives\n")
    print("`fixture/BillingWebService.java` reproduces `jakarta-jws.yml`'s own scenario:")
    print("`@WebService` on the implementor class (no separate SEI), one ordinary")
    print("operation (`charge`), one operation INHERITED from a plain, unannotated")
    print("superclass (`refund`, from `fixture/AbstractBilling.java`), one `final`")
    print("operation (`reconcile`), one `static` method (`staticHelper`) and one")
    print("`@WebMethod(exclude = true)` method (`internalOnly`). `fixture/LiveProbe.java`")
    print("boots a real `org.apache.cxf.jaxws.support.JaxWsServiceFactoryBean` over it and")
    print("prints every operation name CXF's own `ServiceInfo` carries — built and run by")
    print("`live_operations()` off a classpath `dependency:build-classpath` resolves from")
    print("`fixture/pom.xml` (the full CXF runtime, not just the two `javap` coordinates).\n")
    operations = live_operations()
    print("| method on `BillingWebService`/`AbstractBilling` | CXF derived it as an operation |")
    print("|---|---|")
    derived_names = {op.rsplit("}", 1)[-1] for op in operations}
    for name in ("charge", "refund", "reconcile", "staticHelper", "internalOnly"):
        print(f"| `{name}` | {'yes' if name in derived_names else 'no'} |")
    print()
    print(
        f"Raw operation QNames CXF produced: {', '.join(operations) if operations else '*(none)*'}"
    )
    print()


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
