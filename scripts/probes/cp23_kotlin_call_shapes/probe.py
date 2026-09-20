"""CP-23's measurement half: the shapes kotlinc 2.2.0 gives a call with defaulted
arguments (the `$default` bridge, its mask literals and marker, the bridge's own
`iand`/`ifeq` body), a `@JvmStatic` default call with no receiver, and a lambda
compiled as a class under `-Xlambdas=class` beside the compiler's default
`invokedynamic` — plus what the extractor itself reads back as `declares_default`.

Called by `run.sh`, which compiles `src/main/kotlin/cp23/Shapes.kt` twice (one Maven
profile per lambda mode, each into its own `target/<profile>`) and builds the
extractor jar. Like CP-22 it reads each build's own identity out of its own bytes
before it measures anything and refuses to file a cell under a version the class
files did not claim (GUIDELINES §5.4, and CP-5's failure it exists to prevent).

The identity here is the METADATA version kotlinc wrote: `@kotlin.Metadata`'s `mv`
on `Shapes.class` (as `javap -v` prints it) and the version header of the
`META-INF/*.kotlin_module` the same compilation wrote (JVM `DataOutput` ints: a
count, then that many ints). kotlinc writes no compiler version string anywhere in
its output, so the metadata version is the identity the class files REPORT; the
POM's `kotlin.version` is only the parameter that resolved the plugin.
"""

from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

_STEP = " ; "


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Build:
    """One profile's `target/<profile>/classes`, identified by its own bytes."""

    def __init__(self, profile: str, classes: Path, java_home: Path, requested_identity: str):
        self.profile = profile
        self.classes = classes
        self.javap = java_home / "bin" / "javap"
        self.observed = _metadata_version(self, "cp23.Shapes")
        module_version = _module_version(classes)
        if self.observed != module_version:
            raise ProbeError(
                f"{profile}: Shapes.class reports metadata {self.observed!r} but the "
                f".kotlin_module beside it reports {module_version!r} — two compilations in one directory"
            )
        if self.observed != requested_identity:
            raise ProbeError(
                f"{profile}: the class files report metadata version {self.observed!r} but were "
                f"expected to report {requested_identity!r} — a mislabelled column, which is CP-5's failure exactly"
            )

    def javap_out(self, *arguments: str) -> str:
        result = subprocess.run(
            [str(self.javap), "-cp", str(self.classes), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
        return result.stdout


def _metadata_version(build: Build, class_name: str) -> str:
    """`@kotlin.Metadata(mv=[a,b,c])` as `javap -v` decodes it off the class file."""
    output = build.javap_out("-v", "-p", class_name)
    match = re.search(r"kotlin\.Metadata\(\s*mv=\[(\d+),(\d+),(\d+)\]", output)
    if match is None:
        raise ProbeError(f"{class_name} carries no @kotlin.Metadata with an `mv`")
    return ".".join(match.groups())


def _module_version(classes: Path) -> str:
    modules = sorted((classes / "META-INF").glob("*.kotlin_module"))
    if len(modules) != 1:
        raise ProbeError(f"{classes} holds {len(modules)} .kotlin_module files, not one")
    data = modules[0].read_bytes()
    (count,) = struct.unpack(">i", data[:4])
    if count < 3:
        raise ProbeError(f"{modules[0].name} header counts {count} version ints")
    return ".".join(str(v) for v in struct.unpack(f">{count}i", data[4 : 4 + 4 * count])[:3])


# ---- bytecode --------------------------------------------------------------------


def _step(line: str) -> str | None:
    match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _method_body(output: str, declaration: str) -> list[str]:
    """The instructions of the first method whose declaration line contains
    `declaration`, as `opcode <javap comment>` steps, runs collapsed to `x ×N`."""
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if declaration in line), None)
    if start is None:
        raise ProbeError(f"no method matching {declaration!r}")
    steps: list[str] = []
    started = False
    for line in lines[start + 1 :]:
        step = _step(line)
        if step is None:
            if started:
                break
            continue
        started = True
        steps.append(step)
    collapsed: list[str] = []
    for step in steps:
        if collapsed and collapsed[-1].split(" ×")[0] == step:
            head, _, count = collapsed[-1].partition(" ×")
            collapsed[-1] = f"{head} ×{int(count or 1) + 1}"
        else:
            collapsed.append(step)
    return collapsed


def q_call(build: Build, class_name: str, method: str) -> str:
    """Q1–Q4: the whole body of a caller — the mask literal(s) and the `aconst_null`
    marker sit immediately before the `invokestatic` of the `$default` bridge."""
    return _STEP.join(_method_body(build.javap_out("-c", "-p", class_name), f" {method}("))


def q5_bridge_body(build: Build) -> str:
    """Q5: `greet$default`'s own body — per parameter `iload mask ; iconst bit ; iand ;
    ifeq` and the default substituted on the fall-through."""
    return _STEP.join(_method_body(build.javap_out("-c", "-p", "cp23.Shapes"), " greet$default("))


# ---- class shapes ----------------------------------------------------------------

_MEMBER = re.compile(
    r"^  (?P<decl>[^\n]+);\n    descriptor: (?P<desc>\S+)\n    flags: \(0x[0-9a-f]+\)(?P<flags>[^\n]*)$",
    re.MULTILINE,
)


def q6_class_shape(build: Build, class_name: str) -> str:
    """Q6: superclass, then every field and method with its descriptor and flags, as
    the class file states them."""
    output = build.javap_out("-v", "-p", class_name)
    superclass = re.search(r"super_class: #\d+\s+// (\S+)", output)
    if superclass is None:
        raise ProbeError(f"{class_name}: no super_class")
    members = []
    for match in _MEMBER.finditer(output):
        decl, desc, flags = match.group("decl"), match.group("desc"), match.group("flags").strip()
        name = decl.rsplit("(", 1)[0].rsplit(" ", 1)[-1] if "(" in decl else decl.rsplit(" ", 1)[-1]
        if name.startswith("cp23."):  # a constructor is printed under the class name
            name = "<init>"
        if name == "{}":  # and the static initializer as `static {}`
            name = "<clinit>"
        kind = "method" if desc.startswith("(") else "field"
        members.append(f"{kind} {name}{desc if kind == 'method' else ':' + desc} [{flags}]")
    return _STEP.join([f"extends {superclass.group(1)}", *members])


def q7_lambda_mode(build: Build) -> str:
    """Q7: which lambda-returning function bodies carry `invokedynamic` and which
    reach a class — `new` for one that captures or suspends, `getstatic INSTANCE` for
    the singleton a non-capturing one becomes — and which `Shapes$…$1` class files
    the build wrote."""
    output = build.javap_out("-c", "-p", "cp23.Shapes")
    cells = []
    for method in ("plain", "suspended", "capturing"):
        body = _method_body(output, f" {method}(")
        indy = [s for s in body if s.startswith("invokedynamic")]
        klass = [s for s in body if s.startswith(("new ", "getstatic ")) and "Shapes$" in s]
        cells.append(f"{method}: {indy[0] if indy else klass[0] if klass else '?'}")
    written = sorted(p.name for p in build.classes.glob("cp23/Shapes$*.class"))
    return _STEP.join([*cells, "class files: " + ", ".join(written)])


# ---- the extractor's own reading -------------------------------------------------


def q8_declares_default(build: Build, extractor: Path, java_home: Path) -> str:
    """Q8: run the built extractor jar on this build's classes and read
    `declares_default` off `greet`'s parameter facts — the fact is the observation,
    the way `tests/fixture_build.py`'s scans read the same jar."""
    with tempfile.TemporaryDirectory() as out:
        result = subprocess.run(
            [
                str(java_home / "bin" / "java"),
                "-jar",
                str(extractor),
                "--module-id",
                "cp23",
                "--coordinates",
                "dev.sextant.probes/cp23",
                "--version",
                "0",
                "--classes",
                str(build.classes),
                "--out",
                out,
                "--fact-schema-version",
                "1",
                "--sextant-version",
                "0",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ProbeError(f"extractor failed: {result.stderr.strip()}")
        report = json.loads(result.stdout)
        facts = (Path(out) / "cp23" / "Shapes.jsonl").read_text(encoding="utf-8").splitlines()
    metadata_library = next(
        (
            lib
            for lib in report["scanner_libraries"]
            if lib.startswith("org.jetbrains.kotlin:kotlin-metadata-jvm:")
        ),
        "?",
    )
    greet = next(
        (
            json.loads(line)
            for line in facts
            if '"kind":"symbol"' in line and "cp23/Shapes#greet(" in line
        ),
        None,
    )
    if greet is None:
        raise ProbeError("no symbol fact for cp23/Shapes#greet")
    parameters = _STEP.join(
        f"{p['name']}: declares_default={p.get('declares_default', 'absent')}"
        for p in greet["signature"]["parameters"]
    )
    return f"{report['scanner_id']} with {metadata_library} read {parameters}"


def main(arguments: list[str]) -> int:
    options = dict(argument.split("=", 1) for argument in arguments)
    java_home = Path(options["JAVA_HOME"])
    requested = options["EXPECTED"]
    indy = Build("indy", Path(options["INDY"]), java_home, requested)
    klass = Build("class", Path(options["CLASS"]), java_home, requested)
    extractor = Path(options["EXTRACTOR"])
    builds = [indy, klass]

    columns = sorted({b.observed for b in builds})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| builds whose class files report this metadata version | "
        + " | ".join(
            ", ".join(f"`target/{b.profile}/classes`" for b in builds if b.observed == v)
            for v in columns
        )
        + " |"
    )
    print(
        "| identity read from the class bytes themselves (`@kotlin.Metadata` `mv`, `.kotlin_module` header) | "
        + " | ".join(["yes"] * len(columns))
        + " |"
    )
    print()
    print("| # | question | profile | kotlinc metadata | observed |")
    print("|---|---|---|---|---|")
    rows = [
        (
            "1",
            "callsGreetWithDefaults: mask literal and marker before greet$default",
            indy,
            lambda: q_call(indy, "cp23.Shapes", "callsGreetWithDefaults"),
        ),
        (
            "2",
            "callsGreetPartially: mask 2",
            indy,
            lambda: q_call(indy, "cp23.Shapes", "callsGreetPartially"),
        ),
        (
            "3",
            "callsWide: two mask literals for 33 parameters",
            indy,
            lambda: q_call(indy, "cp23.Shapes", "callsWide"),
        ),
        (
            "4",
            "Statics.callsJs: @JvmStatic js$default with no receiver",
            indy,
            lambda: q_call(indy, "cp23.Statics", "callsJs"),
        ),
        (
            "5",
            "greet$default body: bit set -> default substituted",
            indy,
            lambda: q5_bridge_body(indy),
        ),
        (
            "6a",
            "-Xlambdas=class: Shapes$plain$1",
            klass,
            lambda: q6_class_shape(klass, "cp23.Shapes$plain$1"),
        ),
        (
            "6b",
            "-Xlambdas=class: Shapes$suspended$1",
            klass,
            lambda: q6_class_shape(klass, "cp23.Shapes$suspended$1"),
        ),
        (
            "6c",
            "-Xlambdas=class: Shapes$capturing$1",
            klass,
            lambda: q6_class_shape(klass, "cp23.Shapes$capturing$1"),
        ),
        (
            "7a",
            "default profile: which lambdas are invokedynamic, which are classes",
            indy,
            lambda: q7_lambda_mode(indy),
        ),
        ("7b", "-Xlambdas=class: the same three", klass, lambda: q7_lambda_mode(klass)),
        (
            "8a",
            "extractor jar reads declares_default off greet's parameters",
            indy,
            lambda: q8_declares_default(indy, extractor, java_home),
        ),
        (
            "8b",
            "extractor jar reads declares_default off greet's parameters",
            klass,
            lambda: q8_declares_default(klass, extractor, java_home),
        ),
    ]
    for number, question, build, observe in rows:
        print(f"| {number} | {question} | `{build.profile}` | {build.observed} | `{observe()}` |")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-23 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
