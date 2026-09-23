"""CP-31's measurement half: the `javap` reads
`.superpowers/sdd/2026-09-22-temporal-and-eventbus/task-8-brief.md` asks for, on the Vert.x
event bus's own surface — every descriptor `EventBus`, `MessageConsumer` and
`MessageProducer` declare, read separately on vertx-core 4.5.10 and 5.0.0 (Q1-Q3, M7); the
delegation inside `EventBusImpl.consumer(String, Handler)` (Q4, M6); `MessageConsumerOptions`
and its `setAddress` (Q5, M7); `@ConsumeEvent`'s own `AnnotationDefault` values (Q6, M8);
the default-address call inside Quarkus's `VertxProcessor` (Q7, M8); the Mutiny facade's own
descriptors (Q8, M9); the owners `fixtures/orders-eventbus`'s own compiled classes name
at their event-bus call sites (Q9, CP-27's row-16 / CP-30's Q9 pattern applied here); and
the bus's OWN ENVELOPE — both `Message` types' whole declared surface (Q10) and the two
places Quarkus states what it will accept in a consumer's parameter (Q11, Q12), added by
the 2026-09-22 wrapper fix.

Called by `run.sh`, which resolves the five jars and compiles the fixture; this script
downloads nothing. Like CP-27 and CP-30 it reads each jar's own identity out of its own
bytes before it measures anything and refuses to file a cell under a version the archive did
not claim (GUIDELINES §5.4) — and unlike CP-30's two Temporal archives, all five of these
jars DO state an `Implementation-Version`, so the manifest check is the one that runs and
the SHA-1 fallback is never reached. The fixture's own classes carry no manifest: Q9's cell
is filed under the class-file version `javap -v` reports for them, the one identity a
compiled class states about itself.

**Nothing here pre-selects which instructions answer a question.** Q4 and Q7 dump a method's
FULL instruction body (offset, mnemonic, and `javap`'s own comment) rather than a curated
excerpt, because a probe that picks the "relevant" instructions can pick the ones that
confirm what was expected instead of what the bytecode says. Q1-Q3 and Q8 list EVERY method
descriptor the named type declares, not the handful the catalogs read, so an overload that
appears or disappears between releases shows up in the cell the next time this runs. Q5 asks
each version for `MessageConsumerOptions` and records the ABSENCE where `javap` cannot find
it, because the absence is the measurement. Q6 reads the `AnnotationDefault` attribute of
every element `@ConsumeEvent` declares, not only the two the catalog reads.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
_STEP = " ; "
# `javap`'s own two-line shape under `-s`: a declaration, then its erased descriptor.
_DECLARATION = re.compile(r"^\s{2}\S.*?([\w$]+)\(")
_DESCRIPTOR_LINE = re.compile(r"^\s*descriptor:\s*(\S+)\s*$")


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    """One resolved jar, labelled with the version IT reports about ITSELF.

    Every archive CP-31 reads writes an `Implementation-Version` into its own manifest
    (checked: vertx-core at both versions, smallrye-mutiny-vertx-core, quarkus-vertx and
    quarkus-vertx-deployment all carry the entry), so §5.4's ordinary mechanism applies
    unchanged and a jar reporting anything other than the coordinate `run.sh` asked for
    stops the run rather than filling a mislabelled column. CP-30's SHA-1 fallback exists
    for archives that state no version anywhere; none of these is one, and this class
    deliberately has no such branch — a jar that stopped reporting a version would abort
    here rather than quietly fall back to trusting the parameter.
    """

    def __init__(self, key: str, group: str, name: str, requested: str, jar: Path):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        reported = _manifest_version(jar, "META-INF/MANIFEST.MF", "Implementation-Version")
        if reported is None:
            raise ProbeError(
                f"{jar.name} states no `Implementation-Version` in its own manifest — every "
                "cell filed under its column would be the coordinate this run asked for "
                "rather than anything the archive says (CP-5's failure exactly)"
            )
        self.observed = reported
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was expected to report "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )


def _manifest_version(jar: Path, entry: str, key: str) -> str | None:
    with zipfile.ZipFile(jar) as archive:
        names = [n for n in archive.namelist() if n == entry or n.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}`")
        text = archive.read(names[0]).decode("utf-8", "replace")
    # A manifest wraps a long value onto a continuation line beginning with one space;
    # `Implementation-Version` is short in every archive here, but the unwrap is done
    # anyway rather than left as an assumption about a future release's formatting.
    unwrapped: list[str] = []
    for line in text.splitlines():
        if line.startswith(" ") and unwrapped:
            unwrapped[-1] += line[1:]
        else:
            unwrapped.append(line)
    for line in unwrapped:
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    return None


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
    """`"<offset>: <mnemonic> <comment-or-operand>"` for one instruction line — CP-30's own
    `_step_with_offset`, including its fix: a branch target is a BARE trailing operand with
    no `//`, so splitting on `//` unconditionally drops every branch destination."""
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


def _every_descriptor(output: str) -> list[str]:
    """`name(descriptor)` for EVERY method the `javap -s -p` listing declares, in
    declaration order.

    Methods only: a field's `descriptor:` line follows a declaration with no `(` in it, and
    `_DECLARATION` requires one. The list is not filtered to the names any catalog reads —
    the question these rows answer is what the type DECLARES, which is what tells the two
    major versions apart.
    """
    found: list[str] = []
    lines = output.splitlines()
    pending: str | None = None
    for line in lines:
        descriptor = _DESCRIPTOR_LINE.match(line)
        if descriptor is not None:
            if pending is not None:
                found.append(f"{pending}{descriptor.group(1)}")
            pending = None
            continue
        declaration = _DECLARATION.match(line)
        pending = declaration.group(1) if declaration is not None else None
    return found


# --- Q1-Q3: the three event-bus types' whole declared surface, PER VERSION --------------


def q_type_surface(jar: Path, owner: str) -> str:
    descriptors = _every_descriptor(_javap("-s", "-p", owner, classpath=jar))
    if not descriptors:
        raise ProbeError(f"{owner} declares no method at all in {jar.name}")
    return f"×{len(descriptors)} ; " + _STEP.join(descriptors)


# --- Q4: `EventBusImpl.consumer(String, Handler)`, the whole body (M6) ------------------

_IMPL = "io.vertx.core.eventbus.impl.EventBusImpl"


def q_impl_consumer(jar: Path) -> str:
    output = _javap("-c", "-p", _IMPL, classpath=jar)
    body = _full_body(output, "consumer(java.lang.String, io.vertx.core.Handler")
    return _STEP.join(body)


def q_impl_options_consumer(jar: Path) -> str:
    """The SAME question asked of 5.0.0's options-taking pair, because the catalogs answer
    it for those overloads too.

    M6 is stated about `consumer(String, Handler)` alone, and spec §3a lists
    `consumer(MessageConsumerOptions[, Handler])` as an inbound row WITHOUT asking whether
    the handler-less form of it registers anything. If it delegates the same way, the
    one-argument options form registers nothing either and a row for it would publish an
    endpoint nobody serves — so the bodies are read rather than the shape assumed. BOTH
    overloads' whole bodies are dumped, the handler-less one first.
    """
    output = _javap("-c", "-p", _IMPL, classpath=jar)
    bare = _full_body(output, "consumer(io.vertx.core.eventbus.MessageConsumerOptions)")
    with_handler = _full_body(
        output, "consumer(io.vertx.core.eventbus.MessageConsumerOptions, io.vertx.core.Handler"
    )
    return _STEP.join(
        ["--- consumer(MessageConsumerOptions) ---", *bare]
        + ["--- consumer(MessageConsumerOptions, Handler) ---", *with_handler]
    )


# --- Q5: `MessageConsumerOptions`, and its absence where there is one --------------------

_OPTIONS = "io.vertx.core.eventbus.MessageConsumerOptions"


def q_consumer_options(jar: Path) -> str:
    output = _javap("-s", "-p", _OPTIONS, classpath=jar, check=False)
    descriptors = _every_descriptor(output)
    if not descriptors:
        # The ABSENCE is the measurement, not a failed read: M7 claims this type arrives at
        # 5.0.0, and a version that does not carry it must say so in its own cell rather
        # than leave a blank a reader would take for an oversight.
        return f"javap finds no {_OPTIONS} in this artifact at all (class not declared)"
    return f"×{len(descriptors)} ; " + _STEP.join(descriptors)


# --- Q6: `@ConsumeEvent`'s own `AnnotationDefault` values (M8) ---------------------------

_CONSUME_EVENT = "io.quarkus.vertx.ConsumeEvent"
# The two meta-annotations whose own rendering decides a catalog question:
# `@Target` says whether a class-level use can exist at all, `@Retention` whether the
# use reaches the class file for a scanner to read.
_META_ANNOTATIONS = (
    "java.lang.annotation.Target(",
    "java.lang.annotation.Retention(",
)


def q_consume_event_defaults(jar: Path) -> str:
    """Every element `@ConsumeEvent` declares and the `AnnotationDefault` beside it.

    Read off `javap -v`'s own rendering of the attribute, element by element, rather than
    off the two the catalog happens to care about — an element gaining or losing a default
    is exactly the change this row exists to notice. `@Target`/`@Retention` are recorded
    too: `@ConsumeEvent` being METHOD-only is what says a class-level use cannot exist, and
    a catalog's `class_level` question is decided by it.
    """
    output = _javap("-v", "-p", _CONSUME_EVENT, classpath=jar)
    cells: list[str] = []
    name: str | None = None
    lines = output.splitlines()
    for index, line in enumerate(lines):
        declaration = _DECLARATION.match(line)
        if declaration is not None:
            name = declaration.group(1)
            continue
        if line.strip() == "AnnotationDefault:" and name is not None:
            # `javap` prints `default_value: <encoded>` then the decoded value beneath it;
            # both are kept, because the encoded form names the constant-pool TYPE tag
            # (`Z#19` — a boolean) and the decoded form names the value.
            encoded = lines[index + 1].strip() if index + 1 < len(lines) else ""
            decoded = lines[index + 2].strip() if index + 2 < len(lines) else ""
            cells.append(f"{name}: {encoded} -> {decoded}")
            name = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(_META_ANNOTATIONS):
            cells.append(stripped.rstrip("("))
        if "ElementType;." in stripped or "RetentionPolicy;." in stripped:
            cells.append(stripped)
    if not cells:
        raise ProbeError(f"{_CONSUME_EVENT} declares no AnnotationDefault at all")
    return _STEP.join(cells)


# --- Q7: the default address `VertxProcessor` writes (M8) -------------------------------

_PROCESSOR = "io.quarkus.vertx.deployment.VertxProcessor"


def q_processor_default_address(jar: Path) -> str:
    """The FULL body of the `VertxProcessor` method that calls `withDefaultValue`.

    Which method that is is found by SEARCHING the class's bodies for the call rather than
    by naming `build` — the brief cites offsets in a method it does not name, and a probe
    that hard-coded the name would stop measuring the day the processor moved the call.
    """
    output = _javap("-c", "-p", _PROCESSOR, classpath=jar)
    for declaration, body in _bodies(output):
        steps = [s for s in (_step_with_offset(line) for line in body) if s is not None]
        if any("withDefaultValue" in step for step in steps):
            return f"in `{declaration}` ; " + _STEP.join(steps)
    raise ProbeError(f"no method of {_PROCESSOR} calls `withDefaultValue`")


# --- Q8: the Mutiny facade's own descriptors (M9) ---------------------------------------

_MUTINY_TYPES = (
    "io.vertx.mutiny.core.eventbus.EventBus",
    "io.vertx.mutiny.core.eventbus.MessageConsumer",
    "io.vertx.mutiny.core.eventbus.MessageProducer",
)


def q_mutiny_surface(jar: Path) -> str:
    cells: list[str] = []
    for owner in _MUTINY_TYPES:
        descriptors = _every_descriptor(_javap("-s", "-p", owner, classpath=jar))
        cells.append(f"{owner.rsplit('.', 1)[1]} ×{len(descriptors)}")
        cells.extend(f"{owner.rsplit('.', 1)[1]}.{d}" for d in descriptors)
    return _STEP.join(cells)


# --- Q10-Q12: the bus's OWN ENVELOPE, `Message<T>` --------------------------------------
#
# Added by the wrapper fix (2026-09-22). Q1-Q9 measured every type the catalogs name as an
# OWNER and none of the type a consumer's parameter is DECLARED as, which is how three of
# the four catalogs came to ship with no bus envelope in `wrappers` at all: nothing had been
# measured to declare one from, and the absence read as "no envelope exists" rather than
# "nobody looked". Q10 reads both `Message` types' whole declared surface — the core one and
# the facade's, which are DIFFERENT types and must not be conflated. Q11 and Q12 read the
# framework's own rule about them, because whether the spelling even compiles under Quarkus
# decides whether the wrapper is ordinary input or an exotic shape.

_MESSAGE = "io.vertx.core.eventbus.Message"
_MUTINY_MESSAGE = "io.vertx.mutiny.core.eventbus.Message"
_CONSTANTS = "io.quarkus.vertx.deployment.VertxConstants"


def q_message_gate(jar: Path) -> str:
    """`VertxConstants.isMessage`, `isMessageHeaders` and the static initializer that fills
    the `DotName`s both read — WHOLE bodies, the Q4/Q7 discipline.

    This is the pair of predicates Quarkus's own `VertxProcessor` asks about a consumer's
    parameters, so the class names loaded by `<clinit>` are the exact set of types the
    framework treats as an envelope and as headers. A probe that read only `isMessage`
    would record the branch without recording WHICH two names it compares against.
    """
    output = _javap("-c", "-p", _CONSTANTS, classpath=jar)
    cells: list[str] = []
    for fragment in ("isMessage(", "isMessageHeaders(", "static {}"):
        cells.append(f"--- {fragment.rstrip('(')} ---")
        cells.extend(_full_body(output, fragment))
    return _STEP.join(cells)


def q_processor_string_constants(jar: Path) -> str:
    """EVERY `String` constant `VertxProcessor`'s own constant pool holds, in pool order.

    Not the four that mention `Message`: a probe that grepped for the expected sentence
    could only ever confirm it. The validation rules Quarkus enforces on a consumer's
    signature are written into these constants verbatim, so the whole pool is dumped and a
    reader sees the rules beside everything else the class says.
    """
    output = _javap("-v", "-p", _PROCESSOR, classpath=jar)
    found = [
        line.split("//", 1)[1].strip()
        for line in output.splitlines()
        if re.match(r"^\s*#\d+ = String\b", line) and "//" in line
    ]
    if not found:
        raise ProbeError(f"{_PROCESSOR} holds no String constant at all")
    return f"×{len(found)} ; " + _STEP.join(found)


# --- Q9: the fixture's own compiled classes ---------------------------------------------

_FIXTURE_IDENTITY_CLASS = "com.acme.eb.OrderBus"


def fixture_identity(classes: Path) -> str:
    output = _javap("-v", _FIXTURE_IDENTITY_CLASS, classpath=classes)
    match = re.search(r"major version: (\d+)", output)
    if match is None:
        raise ProbeError("the fixture's class file states no major version")
    return f"class file {match.group(1)}"


def _fixture_classes(classes: Path) -> list[str]:
    return sorted(
        path.relative_to(classes).with_suffix("").as_posix().replace("/", ".")
        for path in classes.rglob("*.class")
    )


def q_fixture_owners(classes: Path) -> str:
    """Every `io.vertx.*`/`io.quarkus.*` owner and member the fixture's own compiled classes
    name at a call site, per class — enumerated off the compiled tree rather than off a list
    of class names typed here, so an arm added to the fixture appears in this cell without
    the probe being edited.

    Owners are bucketed by their FULL internal name, not by the simple name they used to
    be. `io/vertx/core/eventbus/Message` and `io/vertx/mutiny/core/eventbus/Message` are
    different types (Q10a/Q10c) and so are the two `MultiMap`s, and the fixture now names
    all four; a bucket keyed on `Message` collapsed each pair into one cell entry with the
    same descriptor beside it and hid the exact distinction this probe measures.
    """
    cells: list[str] = []
    for name in _fixture_classes(classes):
        output = _javap("-p", "-c", name, classpath=classes)
        owners: dict[str, set[str]] = {}
        for line in output.splitlines():
            match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
            if match is None:
                continue
            mnemonic, operands = match.groups()
            if not mnemonic.startswith("invoke") or "Method " not in operands:
                continue
            target = operands.split("Method ", 1)[1].strip()
            if "." not in target:
                continue
            owner, rest = target.split(".", 1)
            if not owner.startswith(("io/vertx/", "io/quarkus/")):
                continue
            owners.setdefault(owner, set()).add(rest)
        if owners:
            cells.append(
                f"{name}: "
                + ", ".join(
                    f"{owner}[{', '.join(sorted(members))}]"
                    for owner, members in sorted(owners.items())
                )
            )
        else:
            cells.append(f"{name}: (no event-bus call site)")
    return _STEP.join(cells)


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
    core45 = artifacts["core45"]
    core50 = artifacts["core50"]
    mutiny = artifacts["mutiny"]
    quarkus = artifacts["quarkus"]
    deployment = artifacts["deployment"]
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
            "yes"
            if all(a.observed == a.requested for a in artifacts.values() if a.observed == v)
            else "NO"
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
            else f"`fixtures/orders-eventbus` (target/classes) | {fixture}"
        )
        print(f"| {number} | {question} | {where} | `{observed}` |")

    for suffix, artifact in (("a", core45), ("b", core50)):
        row(
            f"1{suffix}",
            "every descriptor `io.vertx.core.eventbus.EventBus` declares",
            artifact,
            q_type_surface(artifact.jar, "io.vertx.core.eventbus.EventBus"),
        )
    for suffix, artifact in (("a", core45), ("b", core50)):
        row(
            f"2{suffix}",
            "every descriptor `io.vertx.core.eventbus.MessageConsumer` declares",
            artifact,
            q_type_surface(artifact.jar, "io.vertx.core.eventbus.MessageConsumer"),
        )
    for suffix, artifact in (("a", core45), ("b", core50)):
        row(
            f"3{suffix}",
            "every descriptor `io.vertx.core.eventbus.MessageProducer` declares",
            artifact,
            q_type_surface(artifact.jar, "io.vertx.core.eventbus.MessageProducer"),
        )
    for suffix, artifact in (("a", core45), ("b", core50)):
        row(
            f"4{suffix}",
            "`EventBusImpl.consumer(String, Handler)`'s whole body — what it delegates to",
            artifact,
            q_impl_consumer(artifact.jar),
        )
    row(
        "4c",
        "the same question asked of 5.0.0's `consumer(MessageConsumerOptions[, Handler])` "
        "pair — whole bodies, both overloads",
        core50,
        q_impl_options_consumer(core50.jar),
    )
    for suffix, artifact in (("a", core45), ("b", core50)):
        row(
            f"5{suffix}",
            "`io.vertx.core.eventbus.MessageConsumerOptions` and its `setAddress`",
            artifact,
            q_consumer_options(artifact.jar),
        )
    row(
        "6",
        "every element `@ConsumeEvent` declares, with its own `AnnotationDefault`",
        quarkus,
        q_consume_event_defaults(quarkus.jar),
    )
    row(
        "7",
        "the whole body of the `VertxProcessor` method that calls `withDefaultValue`",
        deployment,
        q_processor_default_address(deployment.jar),
    )
    row(
        "8",
        "every descriptor the Mutiny facade's `EventBus`, `MessageConsumer` and "
        "`MessageProducer` declare",
        mutiny,
        q_mutiny_surface(mutiny.jar),
    )
    row(
        "9",
        "the owners and members the fixture's own compiled classes name at their "
        "`io.vertx`/`io.quarkus` call sites",
        None,
        q_fixture_owners(classes),
    )
    for suffix, artifact, owner in (
        ("a", core45, _MESSAGE),
        ("b", core50, _MESSAGE),
        ("c", mutiny, _MUTINY_MESSAGE),
    ):
        row(
            f"10{suffix}",
            f"every descriptor `{owner}` declares — the bus's own envelope",
            artifact,
            q_type_surface(artifact.jar, owner),
        )
    row(
        "11",
        "`VertxConstants.isMessage`, `isMessageHeaders` and `<clinit>` — whole bodies, and "
        "the class names they compare against",
        deployment,
        q_message_gate(deployment.jar),
    )
    row(
        "12",
        "every `String` constant `VertxProcessor` holds — Quarkus's own rules about a "
        "consumer's signature, in its own words",
        deployment,
        q_processor_string_constants(deployment.jar),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-31 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
