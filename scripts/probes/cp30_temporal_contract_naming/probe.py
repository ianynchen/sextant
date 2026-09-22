"""CP-30's measurement half: the eight `javap` reads task-2-brief.md asks for, on Temporal's
naming rules — which member each of `POJOWorkflowMethodMetadata`'s branches names a
workflow method from (Q1); `POJOActivityMethodMetadata`'s empty-name test and the
`namePrefix` composition it guards (Q2), and `getActivityNameFromMethod`'s title-casing
(Q3); `POJOActivityInterfaceMetadata.validateAndQualifiedForActivityMethod`'s qualification
rule (Q4) and the same question asked of
`POJOWorkflowInterfaceMetadata.validateAndQualifiedForWorkflowMethod` (Q5); the two
attributes `WorkflowImpl`/`ActivityImpl`/`NexusServiceImpl` each declare (Q6);
`WorkflowClient.newUntypedWorkflowStub` and `WorkflowStub.signal`/`query`/`update`'s
argument-0 naming (Q7); the task queue's declaration sites across `WorkerFactory` and
every `*Options$Builder` class the SDK ships (Q8); and, once Task 6 added the fixture, the
owners its own compiled `com.acme.tp.client.OrderClient` names at its call sites (Q9,
the CP-27 row-16 pattern applied here).

Called by `run.sh`, which resolves the two jars and compiles the fixture; this script
downloads nothing. Like CP-27 it reads each jar's own identity out of its own bytes before
it measures anything and refuses to file a cell under a version the archive did not claim
(GUIDELINES §5.4) — but unlike every jar CP-27 measured, neither of these two states an
`Implementation-Version` at all, so `Artifact` falls back to verifying the jar's own SHA-1
against Maven's `.jar.sha1` sidecar instead (see `Artifact`'s docstring, and the write-up's
Version scope section, for why). The fixture's own classes carry no manifest either: Q9's
cell is filed under the class-file version `javap -v` reports for them, the one identity a
compiled class states itself (CP-27's fixture row, same reasoning). Nothing is executed:
every cell is a `javap` read of a class file.

Q1-Q5 dump a method's FULL instruction body (offset, mnemonic, and `javap`'s own comment)
rather than a curated excerpt of it — a probe that pre-selects which instructions "answer"
the question could select the ones that confirm what was expected instead of what the
bytecode says (exactly the failure this task exists to avoid). Q8 does not assume the
count of `*Options$Builder` classes that declare `setTaskQueue`: it javaps every class in
the jar matching that name shape and reports which ones actually declare it.
"""

from __future__ import annotations

import hashlib
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
    """Unlike every jar CP-27 measured, NEITHER `temporal-sdk-1.27.0.jar` nor
    `temporal-spring-boot-autoconfigure-1.27.0.jar` states an `Implementation-Version`
    anywhere in its bytes — checked here, and independently: their manifests carry only
    `Manifest-Version`/`Multi-Release`, they ship no `META-INF/maven/*/pom.properties`,
    and no class's constant pool holds the literal string `1.27.0`. §5.4's mechanism
    ("read the run's own output, never the parameter") has nothing to read for these two
    archives, so this probe falls back to the next-best self-verifying fact: Maven wrote
    a `.jar.sha1` sidecar next to each jar when `mvn dependency:get` resolved this exact
    coordinate from Maven Central, and that sidecar is itself a checksum of the archive's
    own bytes. `_verify_checksum` recomputes the SHA-1 from the jar `probe.py` actually
    reads and aborts if it disagrees with the sidecar — so a corrupted or hand-substituted
    local jar still fails loud, even though the version COLUMN below is the requested
    coordinate rather than something the archive itself states. See task-2-report.md for
    why this is recorded as a finding, not smoothed over."""

    def __init__(self, key: str, group: str, name: str, requested: str, jar: Path):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        reported = _manifest_version(jar, "META-INF/MANIFEST.MF", "Implementation-Version")
        self.self_reported = reported is not None
        if reported is not None:
            self.observed = reported
            if self.observed != requested:
                raise ProbeError(
                    f"{jar.name} reports version {self.observed!r} but was expected to "
                    f"report {requested!r} — a mislabelled column, which is CP-5's "
                    "failure exactly"
                )
        else:
            self.observed = requested
            _verify_checksum(jar)


def _manifest_version(jar: Path, entry: str, key: str) -> str | None:
    """The manifest's own `key`, or `None` when the manifest declares no such property —
    unlike CP-27's `_identity`, absence is not fatal here: it is itself the finding."""
    with zipfile.ZipFile(jar) as archive:
        names = [n for n in archive.namelist() if n == entry or n.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}`")
        text = archive.read(names[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    return None


def _verify_checksum(jar: Path) -> None:
    """Recompute the jar's own SHA-1 from its bytes and abort if it disagrees with the
    `.jar.sha1` sidecar Maven wrote when it resolved this coordinate — the one
    self-verifying check left once the manifest states no version."""
    sidecar = jar.with_name(jar.name + ".sha1")
    if not sidecar.exists():
        raise ProbeError(
            f"no `{sidecar.name}` beside {jar.name} to verify the resolved jar against"
        )
    expected = sidecar.read_text().strip().split()[0]
    observed = hashlib.sha1(jar.read_bytes()).hexdigest()
    if observed != expected:
        raise ProbeError(
            f"{jar.name}'s SHA-1 {observed!r} disagrees with {sidecar.name}'s {expected!r} "
            "— the resolved jar is not the one Maven checksummed for this coordinate"
        )


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


def _step_with_offset(line: str) -> str | None:
    """`"<offset>: <mnemonic> <comment-or-operand>"` for one instruction line — the offset
    kept visible, unlike CP-27's `_step`, because the brief's expected answers cite offsets.
    A branch or `goto`'s destination is a BARE trailing operand with no `//` in `javap`'s
    own output (`95: if_acmpne   116`, not `95: if_acmpne   116  // ...`); splitting on `//`
    unconditionally silently dropped every branch target this method sees (fix-round-1
    finding 1). When there is no `//` comment, the raw operand is kept instead of being
    discarded."""
    match = re.match(r"^\s*(\d+):\s+(\S+)(.*)$", line)
    if match is None:
        return None
    offset, mnemonic, operands = match.groups()
    text = operands.split("//", 1)[1].strip() if "//" in operands else operands.strip()
    return f"{offset}: {mnemonic} {text}".strip()


def _full_body(output: str, method_name_fragment: str) -> list[str]:
    """Every instruction of the first method whose declaration contains
    `method_name_fragment`, in body order — the WHOLE method, not a curated subset."""
    for declaration, body in _bodies(output):
        if method_name_fragment in declaration:
            return [s for s in (_step_with_offset(line) for line in body) if s is not None]
    raise ProbeError(f"no method matching {method_name_fragment!r} found")


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


# --- Q1: POJOWorkflowMethodMetadata — which name each branch takes --------------------


def q1_workflow_method_naming(sdk: Path) -> str:
    output = _javap(
        "-c", "-p", "io.temporal.common.metadata.POJOWorkflowMethodMetadata", classpath=sdk
    )
    body = _full_body(
        output, "POJOWorkflowMethodMetadata(io.temporal.common.metadata.POJOWorkflowMethod"
    )
    return _STEP.join(body)


# --- Q2/Q3: POJOActivityMethodMetadata — the empty-name test and the title-case rule ---


def q2_activity_method_naming(sdk: Path) -> str:
    output = _javap(
        "-c", "-p", "io.temporal.common.metadata.POJOActivityMethodMetadata", classpath=sdk
    )
    body = _full_body(
        output,
        "POJOActivityMethodMetadata(java.lang.reflect.Method, java.lang.Class<?>, "
        "io.temporal.activity.ActivityInterface)",
    )
    return _STEP.join(body)


def q3_activity_name_from_method(sdk: Path) -> str:
    output = _javap(
        "-c", "-p", "io.temporal.common.metadata.POJOActivityMethodMetadata", classpath=sdk
    )
    body = _full_body(output, "getActivityNameFromMethod(java.lang.reflect.Method)")
    return _STEP.join(body)


# --- Q4/Q5: the two qualification rules -------------------------------------------------


def q4_activity_qualification(sdk: Path) -> str:
    output = _javap(
        "-c", "-p", "io.temporal.common.metadata.POJOActivityInterfaceMetadata", classpath=sdk
    )
    body = _full_body(output, "validateAndQualifiedForActivityMethod(java.lang.reflect.Method)")
    return _STEP.join(body)


_CALLER_GATE_NEEDLES = (
    "validateAndQualifiedForWorkflowMethod",
    "WorkflowMethodType.NONE",
    'POJOWorkflowMethodMetadata."<init>"',
)


def q5_workflow_qualification(sdk: Path) -> str:
    output = _javap(
        "-c", "-p", "io.temporal.common.metadata.POJOWorkflowInterfaceMetadata", classpath=sdk
    )
    predicate = _full_body(
        output,
        "validateAndQualifiedForWorkflowMethod(io.temporal.common.metadata.POJOWorkflowMethod)",
    )
    # Q5's write-up claims a SEPARATE check gates construction after this predicate already
    # returned true for an unannotated method — fix-round-1 finding 2 was that this claim
    # named the wrong caller (`newInstanceInternal`) and cited it from a one-off read, not
    # from the harness. `getWorkflowInterfaceMethods` is the actual caller (confirmed:
    # `javap`'s own declaration lines place offsets 140-145/204-212 inside it, not inside
    # `newInstanceInternal`); this pulls the same evidence mechanically, the same way every
    # other row does, rather than restating a claim nothing here generates.
    caller = _full_body(
        output, "getWorkflowInterfaceMethods(java.lang.Class<?>, boolean, java.util.Map<"
    )
    gate: list[str] = []
    for index, step in enumerate(caller):
        if any(needle in step for needle in _CALLER_GATE_NEEDLES):
            gate.append(step)
            if index + 1 < len(caller):
                gate.append(caller[index + 1])
    marker = (
        "--- getWorkflowInterfaceMethods's construction gate, reached AFTER the "
        "predicate above already returned true ---"
    )
    return _STEP.join(predicate + [marker] + gate)


# --- Q6: the three Spring Boot starter annotations' attributes -------------------------

_STARTER_ANNOTATIONS = (
    "io.temporal.spring.boot.WorkflowImpl",
    "io.temporal.spring.boot.ActivityImpl",
    "io.temporal.spring.boot.NexusServiceImpl",
)


def q6_starter_annotations(boot: Path) -> str:
    cells = []
    for name in _STARTER_ANNOTATIONS:
        output = _javap("-p", name, classpath=boot)
        members = [
            line.strip().rstrip(";")
            for line in output.splitlines()
            if line.strip().startswith("public abstract")
        ]
        cells.append(f"{name.rsplit('.', 1)[1]}: " + ", ".join(members))
    return _STEP.join(cells)


# --- Q7: WorkflowClient.newUntypedWorkflowStub and WorkflowStub's signal/query/update ---


def q7_client_and_stub_naming(sdk: Path) -> str:
    client = _javap("-s", "-p", "io.temporal.client.WorkflowClient", classpath=sdk)
    stub = _javap("-s", "-p", "io.temporal.client.WorkflowStub", classpath=sdk)
    cells = []
    descriptors = _public_descriptors(client, "newUntypedWorkflowStub")
    cells.append(f"WorkflowClient.newUntypedWorkflowStub ×{len(descriptors)}")
    cells.extend(f"newUntypedWorkflowStub{d}" for d in descriptors)
    for name in ("signal", "query", "update"):
        for d in _public_descriptors(stub, name):
            cells.append(f"WorkflowStub.{name}{d}")
    # The brief's claim is about these three names only; the rest of WorkflowStub's
    # update/signal family (asked about nowhere in task-2-brief.md's eight rows) is
    # recorded here too rather than silently dropped — §8 rule 3, raise what we see.
    other_names = ("signalWithStart", "startUpdate", "startUpdateWithStart", "getUpdateHandle")
    for name in other_names:
        for d in _public_descriptors(stub, name):
            cells.append(f"WorkflowStub.{name}{d} (not asked; recorded for completeness)")
    return _STEP.join(cells)


# --- Q8: the task queue's declaration sites, measured rather than assumed ---------------


def q8_task_queue_sites(sdk: Path) -> str:
    with zipfile.ZipFile(sdk) as archive:
        builder_classes = sorted(
            name[: -len(".class")].replace("/", ".")
            for name in archive.namelist()
            if name.endswith("Options$Builder.class")
        )
    declares: list[str] = []
    for cls in builder_classes:
        output = _javap("-s", "-p", cls, classpath=sdk, check=False)
        descriptors = _public_descriptors(output, "setTaskQueue")
        if descriptors:
            declares.append(f"{cls.rsplit('.', 1)[1]}: " + ", ".join(descriptors))
    factory = _javap("-s", "-p", "io.temporal.worker.WorkerFactory", classpath=sdk)
    factory_descriptors = _public_descriptors(factory, "newWorker")
    summary = f"scanned {len(builder_classes)} `*Options$Builder` classes; {len(declares)} declare public setTaskQueue"
    cells = [summary]
    cells.extend(declares)
    cells.append(f"WorkerFactory.newWorker ×{len(factory_descriptors)}")
    cells.extend(f"newWorker{d}" for d in factory_descriptors)
    return _STEP.join(cells)


# --- Q9: the fixture's own compiled classes — CP-27's row-16 pattern -------------------

# `OrderClient` is the one class task-6's fixture gives real CALL SITES into the SDK: the
# workflow/activity interfaces and impls carry Temporal's annotations, which are class-file
# ATTRIBUTES, not `invoke*` instructions, so they contribute nothing here — this scans the
# class that actually calls `WorkflowClient`/`WorkflowStub`.
_FIXTURE_CLASS = "com.acme.tp.client.OrderClient"


def fixture_identity(classes: Path) -> str:
    output = _javap("-v", _FIXTURE_CLASS, classpath=classes)
    match = re.search(r"major version: (\d+)", output)
    if match is None:
        raise ProbeError("the fixture's class file states no major version")
    return f"class file {match.group(1)}"


def q9_fixture_owners(classes: Path) -> str:
    output = _javap("-p", "-c", _FIXTURE_CLASS, classpath=classes)
    owners: dict[str, list[str]] = {}
    for line in output.splitlines():
        match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
        if match is None:
            continue
        mnemonic, operands = match.groups()
        if not mnemonic.startswith("invoke") or "Method " not in operands:
            continue
        target = operands.split("Method ", 1)[1].strip()
        owner, rest = target.split(".", 1)
        if not owner.startswith("io/temporal/"):
            continue
        member = rest.split(":", 1)[0]
        owners.setdefault(owner.rsplit("/", 1)[1], []).append(member)
    return _STEP.join(
        f"{owner}: {', '.join(sorted(set(members)))}" for owner, members in sorted(owners.items())
    )


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    classes: Path | None = None
    for spec in specs:
        key, group, name, requested, path = spec.split("|")
        if key == "fixture":
            classes = Path(path)
            continue
        artifacts[key] = Artifact(key, group, name, requested, Path(path))
    if classes is None:
        raise ProbeError("no fixture classes directory handed in")
    sdk, boot = artifacts["sdk"], artifacts["boot"]
    fixture = fixture_identity(classes)

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
        + " | ".join(
            "yes" if all(a.self_reported for a in artifacts.values() if a.observed == v) else "NO"
            for v in columns
        )
        + " |"
    )
    print(
        "| SHA-1 verified against `mvn`'s own `.jar.sha1` sidecar (used only where the "
        "manifest reports no version) | "
        + " | ".join(
            ", ".join(
                "verified" if not a.self_reported else "n/a (manifest reported)"
                for a in artifacts.values()
                if a.observed == v
            )
            for v in columns
        )
        + " |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    def row(number: str, question: str, artifact: Artifact | None, observed: str) -> None:
        where = (
            f"`{artifact.group}:{artifact.name}` | {artifact.observed}"
            if artifact is not None
            else f"`fixtures/temporal-probe` (target/classes) | {fixture}"
        )
        print(f"| {number} | {question} | {where} | `{observed}` |")

    row(
        "1",
        "`POJOWorkflowMethodMetadata`'s constructor: which name each branch takes",
        sdk,
        q1_workflow_method_naming(sdk.jar),
    )
    row(
        "2",
        "`POJOActivityMethodMetadata`'s constructor: the empty-name test and the "
        "prefix composition it guards",
        sdk,
        q2_activity_method_naming(sdk.jar),
    )
    row(
        "3",
        "`POJOActivityMethodMetadata.getActivityNameFromMethod`",
        sdk,
        q3_activity_name_from_method(sdk.jar),
    )
    row(
        "4",
        "`POJOActivityInterfaceMetadata.validateAndQualifiedForActivityMethod`",
        sdk,
        q4_activity_qualification(sdk.jar),
    )
    row(
        "5",
        "`POJOWorkflowInterfaceMetadata.validateAndQualifiedForWorkflowMethod`",
        sdk,
        q5_workflow_qualification(sdk.jar),
    )
    row(
        "6",
        "`WorkflowImpl`/`ActivityImpl`/`NexusServiceImpl`'s declared attributes",
        boot,
        q6_starter_annotations(boot.jar),
    )
    row(
        "7",
        "`WorkflowClient.newUntypedWorkflowStub`; `WorkflowStub.signal`/`query`/`update`",
        sdk,
        q7_client_and_stub_naming(sdk.jar),
    )
    row(
        "8",
        "the task queue's declaration sites: `WorkerFactory.newWorker` and every "
        "`*Options$Builder` class",
        sdk,
        q8_task_queue_sites(sdk.jar),
    )
    row(
        "9",
        "the owners the fixture's compiled `OrderClient` names at its `io.temporal.client` "
        "call sites",
        None,
        q9_fixture_owners(classes),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-30 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
