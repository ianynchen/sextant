"""CP-52: Quarkus gRPC's `@GrpcService` and `@GrpcClient` — which artifact declares them, where
each may sit, what `GrpcClient.value()` defaults to, and how the extension names a client
whose value is left out or empty; and whether a service bean must carry `@GrpcService`. Every
cell is read off the jars with `javap -v`; the version in each column is the jar's own
manifest. Prints the observation table `cp52_quarkus_grpc_annotations.md` carries."""

import re
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _jvm_annotations import (
    ClassFile,
    Instruction,
    ProbeError,
    body,
    called,
    classes,
    dotnames,
    fields,
    identity,
    jar_at,
    pom_at,
    pom_dependencies,
    recipes,
    render,
    strings,
)

VERSION = "3.17.5"
API = ("io.quarkus", "quarkus-grpc-api")
RUNTIME = ("io.quarkus", "quarkus-grpc")
DEPLOYMENT = ("io.quarkus", "quarkus-grpc-deployment")
SERVICE = "io.quarkus.grpc.GrpcService"
CLIENT = "io.quarkus.grpc.GrpcClient"
NAMES = "io.quarkus.grpc.deployment.GrpcDotNames"
CLIENTS = "io.quarkus.grpc.deployment.GrpcClientProcessor"
SERVER = "io.quarkus.grpc.deployment.GrpcServerProcessor"


def local(step: Instruction) -> int | None:
    """The local-variable slot an `aload`/`astore` (or its `_N` form) names."""
    short = re.fullmatch(r"a(?:load|store)_(\d)", step.opcode)
    if short:
        return int(short.group(1))
    if step.opcode in ("aload", "astore") and step.operand.isdigit():
        return int(step.operand)
    return None


def types_held(steps: list[Instruction], names: dict[str, str]) -> dict[int, str]:
    """Slot -> the `GrpcDotNames` class each `Type.create(<name>, …)` result is stored in."""
    held: dict[int, str] = {}
    pending: str | None = None
    last: str | None = None
    for step in steps:
        read = fields([step])
        if read and read[0].startswith("GrpcDotNames."):
            last = names.get(read[0].split(".", 1)[1], read[0])
        elif "Type.create:" in step.comment:
            pending = last
        elif step.opcode.startswith("astore") and pending is not None:
            slot = local(step)
            if slot is not None:
                held[slot] = pending
            pending = None
    return held


def arguments_to(
    steps: list[Instruction], held: dict[int, str], wanted: Callable[[str], bool]
) -> list[str]:
    """The held types loaded (`aload`) since the previous invocation, at the first call
    `wanted` accepts."""
    loaded: list[str] = []
    for step in steps:
        if step.opcode.startswith("aload"):
            slot = local(step)
            if slot is not None and slot in held:
                loaded.append(held[slot])
        elif step.opcode.startswith("invoke"):
            call = called([step])
            if call and wanted(call[0]):
                return loaded
            loaded = []
    return []


def describe(cls: ClassFile) -> str:
    target = cls.annotation("java.lang.annotation.Target")
    retention = cls.annotation("java.lang.annotation.Retention")
    parts = [
        f"annotation `{cls.name}`",
        f"`@Target` {render(target.elements['value']) if target else 'NOT DECLARED'}",
        f"`@Retention` {retention.elements['value'] if retention else 'NOT DECLARED'}",
    ]
    if cls.annotation("jakarta.inject.Qualifier"):
        parts.append("a CDI `@Qualifier`")
    methods = [m for m in cls.members if m.header.endswith("();")]
    parts.append(
        "members "
        + (
            "; ".join(
                f"`{m.name}()`: `{m.returns}`, "
                + (f"default {render(m.default)}" if m.default is not None else "no default")
                for m in methods
            )
            or "none"
        )
    )
    constants = [m for m in cls.members if " static final " in f" {m.header} "]
    for constant in constants:
        value = next(
            (
                line.split("ConstantValue: String ", 1)[1]
                for line in cls.text.splitlines()
                if "ConstantValue: String " in line
            ),
            "NOT READ",
        )
        parts.append(f"constant `{constant.name}` = `{value}`")
    return "; ".join(parts)


def main() -> int:
    jars: dict[str, tuple[Path, str]] = {}
    for key, (group, artifact) in (("api", API), ("runtime", RUNTIME), ("deployment", DEPLOYMENT)):
        jar = jar_at(group, artifact, VERSION)
        if jar is None:
            print(f"NOT IN THE LOCAL REPOSITORY: {group}:{artifact}:{VERSION}", file=sys.stderr)
            return 1
        jars[key] = (jar, identity(jar, VERSION)[0])

    columns = sorted({stated for _, stated in jars.values()})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + ", ".join(f"{g}:{a}" for g, a in (API, RUNTIME, DEPLOYMENT))
        + " |"
    )
    print("| where the jar states that version | MANIFEST.MF `Implementation-Version` |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    row = 0

    def emit(question: str, key: str, observed: str) -> None:
        nonlocal row
        row += 1
        group, artifact = {"api": API, "runtime": RUNTIME, "deployment": DEPLOYMENT}[key]
        print(f"| {row} | {question} | `{group}:{artifact}` | {jars[key][1]} | {observed} |")

    annotations = classes(jars["api"][0], [SERVICE, CLIENT])
    emit("what `GrpcService` is", "api", describe(annotations[SERVICE]))
    emit("what `GrpcClient` is", "api", describe(annotations[CLIENT]))

    with zipfile.ZipFile(jars["runtime"][0]) as archive:
        carried = [
            name
            for name in (SERVICE, CLIENT)
            if name.replace(".", "/") + ".class" in archive.namelist()
        ]
    pom = pom_at(*RUNTIME, VERSION)
    declared = pom_dependencies(pom) if pom else []
    emit(
        "which artifact a module declaring `quarkus-grpc` gets the annotations from",
        "runtime",
        f"the `quarkus-grpc` jar carries "
        f"{'`' + '`, `'.join(carried) + '`' if carried else 'neither annotation'}; its pom "
        f"declares `{':'.join(API)}`: {'yes' if ':'.join(API) in declared else 'NO'}",
    )

    parsed = classes(jars["deployment"][0], [NAMES, CLIENTS, SERVER])
    names = dotnames(parsed[NAMES])
    emit(
        "the names the extension reads (`GrpcDotNames`)",
        "deployment",
        ", ".join(
            f"`{n}` = `{names.get(n, 'NOT DECLARED')}`"
            for n in (
                "GRPC_SERVICE",
                "GRPC_CLIENT",
                "BINDABLE_SERVICE",
                "MUTINY_SERVICE",
                "MUTINY_BEAN",
            )
        ),
    )

    processor = parsed[CLIENTS]
    discover = body(processor, "discoverInjectedClients")
    # The sentinel is the string loaded right before `String.equals`; the element-name branch
    # is the instruction after the `ifeq` that follows it, and an absent value (`ifnull`) is
    # sent to the same place.
    at = next((i for i, step in enumerate(discover) if "String.equals:" in step.comment), None)
    if at is None or discover[at + 1].opcode != "ifeq":
        emit(
            "how a `@GrpcClient` injection point's client name is chosen", "deployment", "NOT FOUND"
        )
        return 1
    sentinel = strings(discover[at - 1 : at])
    element_branch = discover[at + 2].offset
    explicit_branch = int(discover[at + 1].operand)
    absent = any(
        step.opcode == "ifnull" and int(step.operand) == element_branch for step in discover[:at]
    )
    element = [s for s in discover if element_branch <= s.offset < explicit_branch]
    kinds = [f.split(".", 1)[1] for f in fields(element) if f.startswith("AnnotationTarget$Kind.")]
    named_by = [c for c in called(element) if c in ("FieldInfo.name", "MethodInfo.parameterName")]
    explicit = [c for c in called([s for s in discover if s.offset >= explicit_branch])]
    checks = [c for c in explicit if c in ("String.trim", "String.isEmpty")][:2]
    errors = recipes(processor, discover)
    emit(
        "how a `@GrpcClient` injection point's client name is chosen (`discoverInjectedClients`)",
        "deployment",
        f"compares `value()` with `{'`, `'.join(sentinel)}` (`String.equals`); a value equal to "
        f"it, or absent (`ifnull` to the same branch: {'yes' if absent else 'NO'}), names the "
        f"client by its target — target kinds `{'`, `'.join(dict.fromkeys(kinds))}` read with "
        f"`{'`, `'.join(named_by)}` (the field's name, the parameter's name); any other value "
        f"is the name, after `{'` -> `'.join(checks)}`",
    )
    emit(
        "what an unnamed parameter, and an empty or blank value, do",
        "deployment",
        "a `DeploymentException`: "
        + "; ".join(f"`{e}`" for e in errors if "client name" in e or "Unable to determine" in e),
    )

    server = parsed[SERVER]
    validate = body(server, "validateBindableServices")
    held = types_held(validate, names)
    predicate_args = arguments_to(validate, held, lambda c: c.endswith('"<init>"') and "$" in c)
    checked_args = arguments_to(validate, held, lambda c: c.endswith("validateBindableService"))
    predicate = next(
        (c.split('."')[0] for c in called(validate) if c.endswith('"<init>"') and "$" in c), ""
    )
    predicate_class = f"io.quarkus.grpc.deployment.{predicate}"
    test = body(classes(jars["deployment"][0], [predicate_class])[predicate_class], "test")
    single = body(server, "validateBindableService")
    skip = next((i for i, step in enumerate(single[:-1]) if "Set.contains" in step.comment), None)
    skips = skip is not None and single[skip + 1].opcode == "ifne"
    required = [
        names.get(f.split(".", 1)[1], f) for f in fields(single) if f.startswith("GrpcDotNames.")
    ]
    emit(
        "whether a gRPC service bean must carry `@GrpcService` (`validateBindableServices`)",
        "deployment",
        f"every class bean whose types `Set.contains` (x{called(test).count('Set.contains')}, "
        f"either) `{'`, `'.join(predicate_args)}` (the `{predicate}` predicate) is checked by "
        f"`validateBindableService`, which skips a bean whose types contain "
        f"`{'`, `'.join(checked_args)}` (`ifne` past the checks: {'yes' if skips else 'NO'}), "
        f"looks for `{'`, `'.join(required)}` among the bean's qualifiers (`Stream.noneMatch`) "
        f"and raises: " + "; ".join(f"`{r}`" for r in recipes(server, single)),
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ProbeError as error:
        print(f"CP-52 aborted: {error}", file=sys.stderr)
        sys.exit(1)
