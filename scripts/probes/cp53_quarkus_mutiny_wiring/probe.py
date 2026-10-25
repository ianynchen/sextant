"""CP-53: how Quarkus's gRPC build step wires its Mutiny clients and services — which class
`discoverInjectedClients` maps each service interface to, how it classifies an injected
`@GrpcClient` type, which generated beans `processGeneratedBeans` serves and what each delegates
to — and whether the four marker types are in `quarkus-grpc-api`. Every cell is read off the jars
with `javap -c`; the version in each column is the jar's own manifest. Prints the observation
table `cp53_quarkus_mutiny_wiring.md` carries."""

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
    called,
    classes,
    dotnames,
    fields,
    identity,
    jar_at,
    recipes,
)

VERSION = "3.17.5"
API = ("io.quarkus", "quarkus-grpc-api")
DEPLOYMENT = ("io.quarkus", "quarkus-grpc-deployment")
NAMES = "io.quarkus.grpc.deployment.GrpcDotNames"
CLIENTS = "io.quarkus.grpc.deployment.GrpcClientProcessor"
SERVER = "io.quarkus.grpc.deployment.GrpcServerProcessor"
MARKERS = ["MutinyService", "MutinyClient", "MutinyBean", "MutinyStub"]

# What a conditional jump's operand has to be for the jump to be TAKEN, and for it to fall
# through; the pair names the outcome that each side of the branch stands for.
OUTCOMES = {
    "ifeq": ("false", "true"),
    "ifne": ("true", "false"),
    "ifnull": ("null", "non-null"),
    "ifnonnull": ("non-null", "null"),
    "if_icmpeq": ("equal", "unequal"),
    "if_icmpne": ("unequal", "equal"),
}


def index_of(steps: list[Instruction], method: str, start: int = 0) -> int:
    """The position of the first call to `Owner.name` at or after `start`; a probe that cannot
    find a call it expects aborts rather than printing a cell about something else."""
    for i in range(start, len(steps)):
        if steps[i].opcode.startswith("invoke") and called([steps[i]]) == [method]:
            return i
    raise ProbeError(f"no call to {method} where the probe expected one")


def local(step: Instruction) -> int | None:
    """The local-variable slot an `aload`/`astore` (or its `_N` form) names."""
    short = re.fullmatch(r"a(?:load|store)_(\d)", step.opcode)
    if short:
        return int(short.group(1))
    if step.opcode in ("aload", "astore") and step.operand.isdigit():
        return int(step.operand)
    return None


def constants(steps: list[Instruction]) -> list[str]:
    """The string constants a body loads, in order, the empty string included (`javap` prints
    it as a bare `String`)."""
    found: list[str] = []
    for step in steps:
        match = re.fullmatch(r"String(?: (.*))?", step.comment)
        if step.opcode.startswith("ldc") and match:
            found.append(match.group(1) or "")
    return found


def static_before(steps: list[Instruction], at: int, prefix: str) -> str:
    """The nearest `getstatic` at or before position `at` whose field starts with `prefix`."""
    for i in range(at, -1, -1):
        read = fields([steps[i]])
        if read and read[0].startswith(prefix):
            return read[0]
    raise ProbeError(f"no {prefix}* constant before position {at}")


def named(constant: str, names: dict[str, str]) -> str:
    """`GrpcDotNames.MUTINY_CLIENT` -> the class name that constant is built from."""
    return names.get(constant.split(".", 1)[1], constant)


def loop_exit(steps: list[Instruction], after: int) -> int:
    """The offset an iterator loop leaves to: the operand of the `ifeq` that follows the first
    `Iterator.hasNext` at or after position `after`."""
    at = index_of(steps, "Iterator.hasNext", after)
    if steps[at + 1].opcode != "ifeq":
        raise ProbeError("an iterator loop without the expected `ifeq` exit")
    return int(steps[at + 1].operand)


def is_goto(steps: list[Instruction], offset: int, destination: int) -> bool:
    return any(
        s.offset == offset and s.opcode == "goto" and int(s.operand) == destination for s in steps
    )


def skip_outcome(steps: list[Instruction], start: int, top: int) -> str:
    """At or after position `start`, the first conditional jump with a `goto top` (back to the
    next item of the outer loop, leaving this one unserved) on one side: which outcome of the
    tested value sends the item there."""
    for i in range(start, len(steps)):
        jump = steps[i]
        if jump.opcode not in OUTCOMES:
            continue
        if is_goto(steps, steps[i + 1].offset, top):
            return OUTCOMES[jump.opcode][1]
        if is_goto(steps, int(jump.operand), top):
            return OUTCOMES[jump.opcode][0]
    raise ProbeError("no conditional jump leads back to the loop")


def client_map(names: dict[str, str], processor: ClassFile) -> str:
    """(a): which classes `discoverInjectedClients` maps, and by which of their interfaces."""
    steps = body(processor, "discoverInjectedClients")
    first = index_of(steps, "IndexView.getKnownDirectImplementors")
    root = named(static_before(steps, first, "GrpcDotNames."), names)
    interfaces = index_of(steps, "ClassInfo.interfaceNames")
    implementor = local(steps[interfaces - 1])
    leave = loop_exit(steps, interfaces)
    # An interface equal to the root is passed over (`DotName.equals`, then `ifne`); any other is
    # stored (`astore`) and the next instruction jumps out of the interface loop (`goto`).
    compare = index_of(steps, "DotName.equals", interfaces)
    passes_root = steps[compare + 1].opcode == "ifne"
    kept = local(steps[compare + 3])
    stops = steps[compare + 3].opcode.startswith("astore") and is_goto(
        steps, steps[compare + 4].offset, leave
    )
    refused = next(i for i, s in enumerate(steps) if "IllegalStateException" in s.comment)
    put = index_of(steps, "Map.put", refused)
    keyed = local(steps[put - 3]) == kept and called(steps[put - 1 : put + 1]) == [
        "ClassInfo.name",
        "Map.put",
    ]
    valued = local(steps[put - 2]) == implementor
    return (
        f"reads every direct implementor of `{root}` (`IndexView.getKnownDirectImplementors`) "
        f"and its `ClassInfo.interfaceNames`; the interface kept is the first one that is not "
        f"`{root}` (`DotName.equals` then `ifne`: {'yes' if passes_root else 'NO'}) and the scan "
        f"stops there (`astore` then `goto` out of the loop: {'yes' if stops else 'NO'}); "
        f"`Map.put` stores that interface as the key and the implementor's `ClassInfo.name` as "
        f"the value ({'yes' if keyed and valued else 'NO'}); an implementor with no such "
        f"interface raises `IllegalStateException`: `{recipes(processor, steps)[0]}`"
    )


@dataclass
class Test:
    """One test an injected type goes through: how it compares, against which name, which
    client kind a pass yields, and where in the method it sits."""

    how: str
    against: str
    at: int
    yields: str = ""


def classification(names: dict[str, str], processor: ClassFile) -> tuple[str, str, str]:
    """(b): the tests an injection point's type goes through, in order, what each yields, and what
    the last one does."""
    steps = body(processor, "discoverInjectedClients")
    begin = index_of(steps, "BeanDiscoveryFinishedBuildItem.getInjectionPoints")
    tests: list[Test] = []
    for i in range(begin, len(steps)):
        how = called([steps[i]])
        if how in (["DotName.equals"], ["Set.contains"]) and steps[i - 1].opcode == "getstatic":
            tests.append(Test(how[0], named(static_before(steps, i, "GrpcDotNames."), names), i))
            continue
        read = fields([steps[i]])
        if (
            tests
            and not tests[-1].yields
            and read
            and read[0].startswith("GrpcClientBuildItem$ClientType.")
        ):
            tests[-1].yields = read[0].split(".", 1)[1]
    chain = "; ".join(f"`{t.how}` `{t.against}` -> `{t.yields}`" for t in tests)

    # The set the `Set.contains` tests read is the one `getRawTypeClosure` returned: it is stored
    # in a local, and each test loads that local right before its constant.
    closure_at = index_of(steps, "getRawTypeClosure")
    closure_slot = local(steps[closure_at + 1])
    contains = [t for t in tests if t.how == "Set.contains"]
    reads_closure = bool(contains) and all(local(steps[t.at - 2]) == closure_slot for t in contains)

    last = tests[-1].at
    mapped = steps[last : index_of(steps, "GrpcClientBuildItem.addClient", last)]
    looked_up = index_of(mapped, "Map.get")
    # The `Map.get` result is stored in a local (after a `checkcast`), and that local is loaded
    # for the `ClientInfo` that is built next.
    result = next(local(s) for s in mapped[looked_up:] if s.opcode.startswith("astore"))
    built = index_of(mapped, 'GrpcClientBuildItem$ClientInfo."<init>"')
    stored = result in [local(s) for s in mapped[:built] if s.opcode.startswith("aload")]
    misses = "invalidInjectionPoint" in " ".join(s.comment for s in mapped)
    other_branch = int(next(s for s in steps[last:] if s.opcode == "ifeq").operand)
    otherwise = "invalidInjectionPoint" in " ".join(
        s.comment for s in steps if other_branch <= s.offset <= other_branch + 6
    )
    return (
        chain,
        (
            f"the {len(contains)} `Set.contains` tests read the set that `getRawTypeClosure` "
            f"returns for the injected type's class ({'yes' if reads_closure else 'NO'})"
        ),
        (
            f"`Map.get` of the injected type's name (`Type.name`) in the map of (a); the result is "
            f"the class given to `ClientInfo` as the client ({'yes' if stored else 'NO'}); no "
            f"entry -> `invalidInjectionPoint`: {'yes' if misses else 'NO'}; a type that passes "
            f"none of the tests -> `invalidInjectionPoint`: {'yes' if otherwise else 'NO'}"
        ),
    )


def closure(processor: ClassFile) -> str:
    steps = body(processor, "getRawTypeClosure")
    recursive = any(s.opcode == "invokestatic" and "getRawTypeClosure" in s.comment for s in steps)
    return (
        f"the class's own name (`ClassInfo.name`), plus the closure of each of its "
        f"`ClassInfo.interfaceNames` and of its `ClassInfo.superName` unless that is "
        f"`DotNames.OBJECT` ({'yes' if 'DotNames.OBJECT' in fields(steps) else 'NO'}), each "
        f"found with `IndexView.getClassByName` and followed recursively "
        f"({'yes' if recursive else 'NO'}); a class the index does not hold is added by name "
        f"alone, without its own supertypes"
    )


def server_rows(names: dict[str, str], server: ClassFile) -> list[tuple[str, str]]:
    """(c): what `processGeneratedBeans` does with each direct implementor of `MutinyBean`."""
    steps = body(server, "processGeneratedBeans")
    first = index_of(steps, "IndexView.getKnownDirectImplementors")
    bean = named(static_before(steps, first, "GrpcDotNames."), names)
    top_index = first + 3  # the `aload` before the outer loop's `Iterator.hasNext`
    top = steps[top_index].offset

    field_at = index_of(steps, "ClassInfo.field")
    delegate = constants(steps[field_at - 2 : field_at])[0]
    implementors = index_of(steps, "IndexView.getAllKnownImplementors")
    type_read = [
        c for c in called(steps[field_at:implementors]) if c in ("FieldInfo.type", "Type.name")
    ]
    none_known = skip_outcome(steps, implementors, top)

    marker_at = index_of(steps, "ClassInfo.declaredAnnotation")
    service = named(static_before(steps, marker_at, "GrpcDotNames."), names)
    inner = index_of(steps, "Collection.iterator", implementors + 1)
    inner_exit = loop_exit(steps, inner)
    first_only = any(
        s.opcode == "goto" and int(s.operand) == inner_exit
        for s in steps[marker_at : marker_at + 8]
    )
    after_loop = next(i for i, s in enumerate(steps) if s.offset == inner_exit)
    unmatched = skip_outcome(steps, after_loop, top)

    super_at = index_of(steps, "ClassInfo.superName", after_loop)
    size_at = index_of(steps, "Collection.size", super_at)
    expected = re.fullmatch(r"iconst_(\d)", steps[size_at + 1].opcode)
    sole = skip_outcome(steps, size_at, top)
    replace_at = index_of(steps, "String.replace", super_at)
    swapped = constants(steps[replace_at - 3 : replace_at])
    plain = skip_outcome(steps, index_of(steps, "Collection.isEmpty", replace_at), top)
    prefixes = constants(steps[:first])
    starts = index_of(steps, "String.startsWith", replace_at)
    # The string `startsWith` is called on is the superclass's name, as `DotName.toString`
    # stored it before the `replace` — not the replaced name.
    name_slot = local(steps[index_of(steps, "DotName.toString", super_at) + 1])
    on_superclass = local(steps[starts - 2]) == name_slot
    prefixed = skip_outcome(steps, starts, top)

    # The bean is the local stored right after the outer loop's `Iterator.next`; the match is the
    # local stored right after the `ifnull` that follows `declaredAnnotation`.
    bean_slot = local(next(x for x in steps[top_index:] if x.opcode.startswith("astore")))
    match_slot = local(next(x for x in steps[marker_at + 2 :] if x.opcode.startswith("astore")))
    registered = steps[starts:]
    wrapper = index_of(registered, 'DelegatingGrpcBeanBuildItem."<init>"')
    handed = [local(x) for x in registered[wrapper - 2 : wrapper]]
    gather = index_of(registered, "gatherBlockingOrVirtualMethodNames")
    reads_match = local(registered[gather - 4]) == match_slot
    recorded = index_of(registered, "Map.put", gather)
    under_bean = local(registered[recorded - 3]) == bean_slot and called(
        registered[recorded - 2 : recorded + 1]
    ) == ["ClassInfo.name", "Map.put"]
    exposed = index_of(steps, 'BindableServiceBuildItem."<init>"')
    return [
        (
            "which generated beans are visited, and what is read from each",
            (
                f"every direct implementor of `{bean}` (`IndexView.getKnownDirectImplementors`); the "
                f"field of each named `{delegate}` (`ClassInfo.field`; absent -> "
                f"`IllegalStateException`: `{recipes(server, steps)[0]}`); that field's type "
                f"(`{'`, `'.join(type_read)}`); and `IndexView.getAllKnownImplementors` of the type "
                f"(bean skipped when the result of `Collection.isEmpty` is {none_known})"
            ),
        ),
        (
            "which class the bean is said to delegate to",
            (
                f"the first implementor of the field's type carrying `{service}` on the class itself "
                f"(`ClassInfo.declaredAnnotation`, not inherited; the scan stops at the first match: "
                f"{'yes' if first_only else 'NO'}); the bean is skipped when that match is "
                f"{unmatched}"
            ),
        ),
        (
            "the further conditions on a bean",
            (
                f"the bean's `ClassInfo.superName` has `IndexView.getAllKnownSubclasses` of size "
                f"`{expected.group(1) if expected else 'NOT READ'}` (`Collection.size`; bean skipped "
                f"when the comparison is {sole}); the same superclass name with `{swapped[0]}` "
                f"replaced by `{swapped[1] or 'an empty string'}` (`String.replace`, `DotName.createSimple`) "
                f"has no known subclass (bean skipped when `Collection.isEmpty` is {plain}); and "
                f"the superclass's name (`DotName.toString`: {'yes' if on_superclass else 'NO'}) starts with none of `{'`, `'.join(prefixes)}` (`String.startsWith`; "
                f"bean skipped when the flag is {prefixed})"
            ),
        ),
        (
            "what a bean that passes is registered as",
            (
                f"`DelegatingGrpcBeanBuildItem(bean, match)` ({'yes' if handed == [bean_slot, match_slot] else 'NO'}); "
                f"the match's methods are read (`gatherBlockingOrVirtualMethodNames`: "
                f"{'yes' if reads_match else 'NO'}) and recorded under the bean's name "
                f"(`ClassInfo.name`, `Map.put`: {'yes' if under_bean else 'NO'}); each recorded bean "
                f"name becomes a `BindableServiceBuildItem` ({'yes' if exposed else 'NO'})"
            ),
        ),
    ]


def main() -> int:
    jars = {}
    for key, (group, artifact) in (("api", API), ("deployment", DEPLOYMENT)):
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
        + ", ".join(f"{g}:{a}" for g, a in (API, DEPLOYMENT))
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
        group, artifact = {"api": API, "deployment": DEPLOYMENT}[key]
        print(f"| {row} | {question} | `{group}:{artifact}` | {jars[key][1]} | {observed} |")

    qualified = [f"io.quarkus.grpc.{m}" for m in MARKERS]
    present = classes(jars["api"][0], qualified)
    emit(
        "the four marker types (d)",
        "api",
        "; ".join(
            f"`{name}`: "
            + (f"`{present[name].declaration}`" if name in present else "NOT IN THE JAR")
            for name in qualified
        ),
    )

    parsed = classes(jars["deployment"][0], [NAMES, CLIENTS, SERVER])
    names = dotnames(parsed[NAMES])
    emit(
        "the names the extension reads (`GrpcDotNames`)",
        "deployment",
        ", ".join(
            f"`{n}` = `{names.get(n, 'NOT DECLARED')}`"
            for n in (
                "MUTINY_CLIENT",
                "MUTINY_STUB",
                "MUTINY_SERVICE",
                "MUTINY_BEAN",
                "ABSTRACT_BLOCKING_STUB",
                "CHANNEL",
                "GRPC_SERVICE",
            )
        ),
    )

    processor = parsed[CLIENTS]
    emit(
        "which class a service interface maps to (a, `discoverInjectedClients`)",
        "deployment",
        client_map(names, processor),
    )
    chain, tested, mapped = classification(names, processor)
    emit("how an injected `@GrpcClient` type is classified, in order (b)", "deployment", chain)
    emit(
        "what the `Set.contains` tests read (b)",
        "deployment",
        f"{tested}; the set holds {closure(processor)}",
    )
    emit("what a `MutinyService` type becomes (b)", "deployment", mapped)
    emit(
        "the error for a type that cannot be injected (b, `invalidInjectionPoint`)",
        "deployment",
        "; ".join(f"`{r}`" for r in recipes(processor, body(processor, "invalidInjectionPoint"))),
    )

    for question, observed in server_rows(names, parsed[SERVER]):
        emit(f"{question} (c, `processGeneratedBeans`)", "deployment", observed)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ProbeError as error:
        print(f"CP-53 aborted: {error}", file=sys.stderr)
        sys.exit(1)
