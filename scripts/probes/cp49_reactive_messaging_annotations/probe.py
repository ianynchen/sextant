"""CP-49: which annotations name a SmallRye Reactive Messaging channel, where may each sit, which
are repeatable, what does each member default to — and which direction does Quarkus give the
channel each one names? Every cell is read off the jars with `javap -v`; the version in each
column is the jar's own manifest. Prints the observation table
`cp49_reactive_messaging_annotations.md` carries."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _jvm_annotations import (
    ClassFile,
    ProbeError,
    body,
    called,
    classes,
    dotnames,
    fields,
    identity,
    jar_at,
    recipes,
    render,
)

MP = "org.eclipse.microprofile.reactive.messaging"
SR = "io.smallrye.reactive.messaging"
DEPLOYMENT = "io.quarkus.smallrye.reactivemessaging.deployment"

# (key, group, artifact, version) — the coordinates read; each jar's column is its own manifest.
JARS = [
    (
        "mp",
        "org.eclipse.microprofile.reactive.messaging",
        "microprofile-reactive-messaging-api",
        "3.0.1",
    ),
    ("api", "io.smallrye.reactive", "smallrye-reactive-messaging-api", "4.25.0"),
    ("provider", "io.smallrye.reactive", "smallrye-reactive-messaging-provider", "4.25.0"),
    ("kafka", "io.smallrye.reactive", "smallrye-reactive-messaging-kafka", "4.25.0"),
    ("runtime17", "io.quarkus", "quarkus-messaging", "3.17.5"),
    ("deployment17", "io.quarkus", "quarkus-messaging-deployment", "3.17.5"),
    ("runtime40", "io.quarkus", "quarkus-messaging", "3.40.1.1"),
    ("deployment40", "io.quarkus", "quarkus-messaging-deployment", "3.40.1.1"),
]

# The annotations and types a channel is named through, per the jar that declares them.
DECLARED = {
    "mp": [f"{MP}.Incoming", f"{MP}.Outgoing", f"{MP}.Channel", f"{MP}.Emitter"],
    "api": [
        f"{MP}.Incoming",
        f"{MP}.Outgoing",
        f"{MP}.Channel",
        f"{MP}.Emitter",
        f"{SR}.annotations.Incomings",
        f"{SR}.annotations.Outgoings",
        f"{SR}.annotations.Channel",
        f"{SR}.annotations.Emitter",
        f"{SR}.MutinyEmitter",
    ],
}
EMITTER_FACTORY_FOR = f"{SR}.annotations.EmitterFactoryFor"


def describe(cls: ClassFile) -> str:
    """Kind, deprecation, `@Target`, `@Retention`, `@Repeatable`, qualifier, and each member."""
    if "@interface" in cls.declaration or " extends java.lang.annotation.Annotation" in (
        cls.declaration
    ):
        kind = "annotation"
    elif " interface " in f" {cls.declaration} ":
        kind = "interface"
    else:
        kind = "class"
    parts = [f"{kind} `{cls.name}`"]
    if cls.annotation("java.lang.Deprecated"):
        parts.append("`@Deprecated`")
    target = cls.annotation("java.lang.annotation.Target")
    if kind == "annotation":
        parts.append(f"`@Target` {render(target.elements['value']) if target else 'NOT DECLARED'}")
        retention = cls.annotation("java.lang.annotation.Retention")
        parts.append(f"`@Retention` {retention.elements['value'] if retention else 'NOT DECLARED'}")
        repeatable = cls.annotation("java.lang.annotation.Repeatable")
        parts.append(
            f"`@Repeatable` {repeatable.elements['value'] if repeatable else 'not declared'}"
        )
        if cls.annotation("jakarta.inject.Qualifier"):
            parts.append("a CDI `@Qualifier`")
        members = [
            f"`{m.name}()`: `{m.returns}`, "
            + (f"default {render(m.default)}" if m.default is not None else "no default")
            + "".join(f", `@{a.type.rsplit('.', 1)[-1]}`" for a in m.annotations)
            for m in cls.members
            if m.header.endswith("();")
        ]
        parts.append("members " + ("; ".join(members) if members else "none"))
    else:
        abstract = [m.name for m in cls.members if " abstract " in f" {m.header} "]
        parts.append(f"abstract methods `{'`, `'.join(dict.fromkeys(abstract))}`")
    return "; ".join(parts)


def main() -> int:
    jars: dict[str, tuple[Path, str, str]] = {}
    stated_in: dict[str, set[str]] = {}
    missing = []
    for key, group, artifact, version in JARS:
        jar = jar_at(group, artifact, version)
        if jar is None:
            missing.append(f"{group}:{artifact}:{version}")
            continue
        stated, where = identity(jar, version)
        jars[key] = (jar, f"{group}:{artifact}", stated)
        stated_in.setdefault(stated, set()).add(f"`{where}`")
    for coordinate in missing:
        print(f"NOT IN THE LOCAL REPOSITORY: {coordinate}", file=sys.stderr)
    if "mp" not in jars or "api" not in jars:
        return 1

    columns = sorted({stated for _, _, stated in jars.values()})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(name for _, name, stated in jars.values() if stated == column)
            for column in columns
        )
        + " |"
    )
    print(
        "| where the jar states that version | "
        + " | ".join(f"MANIFEST.MF {', '.join(sorted(stated_in[c]))}" for c in columns)
        + " |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    row = 0

    def emit(question: str, key: str, observed: str) -> None:
        nonlocal row
        row += 1
        _, name, stated = jars[key]
        print(f"| {row} | {question} | `{name}` | {stated} | {observed} |")

    for key in ("mp", "api"):
        jar = jars[key][0]
        parsed = classes(jar, DECLARED[key])
        for name in DECLARED[key]:
            cls = parsed.get(name)
            emit(
                f"what `{name.rsplit('.', 1)[-1]}` is",
                key,
                describe(cls) if cls else f"`{name}` NOT IN THIS JAR",
            )

    for key in ("provider", "kafka", "runtime17", "runtime40"):
        if key not in jars:
            continue
        factories = []
        for cls in classes(jars[key][0]).values():
            annotation = cls.annotation(EMITTER_FACTORY_FOR)
            if annotation is not None:
                factories.append(
                    f"`{cls.name.rsplit('.', 1)[-1]}` -> `{annotation.elements['value']}`"
                )
        emit(
            "which injected types are emitters (`@EmitterFactoryFor` on a factory class)",
            key,
            "; ".join(factories) if factories else "no class carries `@EmitterFactoryFor`",
        )

    for key in ("deployment17", "deployment40"):
        if key not in jars:
            continue
        jar = jars[key][0]
        parsed = classes(
            jar,
            [
                f"{DEPLOYMENT}.ReactiveMessagingDotNames",
                f"{DEPLOYMENT}.WiringProcessor",
                f"{DEPLOYMENT}.WiringHelper",
            ],
        )
        names = dotnames(parsed[f"{DEPLOYMENT}.ReactiveMessagingDotNames"])
        wanted = [
            "INCOMING",
            "INCOMINGS",
            "OUTGOING",
            "OUTGOINGS",
            "CHANNEL",
            "LEGACY_CHANNEL",
            "EMITTER",
            "MUTINY_EMITTER",
            "LEGACY_EMITTER",
            "EMITTER_FACTORY_FOR",
        ]
        emit(
            "the names Quarkus's wiring reads (`ReactiveMessagingDotNames`)",
            key,
            ", ".join(f"`{n}` = `{names.get(n, 'NOT DECLARED')}`" for n in wanted),
        )
        wiring = parsed[f"{DEPLOYMENT}.WiringProcessor"]
        extract = body(wiring, "extractComponents")
        read = [f for f in fields(extract) if f.startswith("ReactiveMessagingDotNames.")]
        handlers = [c for c in called(extract) if c.split(".")[-1].startswith("handle")]
        emit(
            "what `extractComponents` reads, and the handlers it dispatches to, in order",
            key,
            f"reads `{'`, `'.join(r.split('.', 1)[1] for r in read)}`; calls "
            f"`{'`, `'.join(h.split('.')[-1] for h in handlers)}`",
        )
        directions = []
        for handler in dict.fromkeys(h.split(".")[-1] for h in handlers):
            steps = called(body(wiring, handler))
            produced = [s.split(".")[-1] for s in steps if "produce" in s and "Channel" in s]
            emitted = [s.split(".")[-1] for s in steps if s.endswith("createEmitter")]
            for helper in emitted:
                produced += [
                    s.split(".")[-1]
                    for s in called(body(wiring, helper))
                    if "produce" in s and "Channel" in s
                ]
            via = f" (via `{'`, `'.join(emitted)}`)" if emitted else ""
            directions.append(f"`{handler}` -> `{'`, `'.join(produced) or 'NONE'}`{via}")
        emit("which direction each handler gives the channel it names", key, "; ".join(directions))
        # The emitter branch is taken when the injection point's type is a key of the map
        # built from every bean's `@EmitterFactoryFor` value; otherwise a `@Channel` on it is
        # an injected stream.
        marks = ("getRequiredType", "Map.get:", "handleEmitter", "handleChannelInjection")
        first = [
            next((i for i, step in enumerate(extract) if mark in step.comment), -1)
            for mark in marks
        ]
        keyed = -1 not in first and first == sorted(first)
        emit(
            "what makes an injected `@Channel` an emitter rather than a stream",
            key,
            "the injection point's required type is looked up (`Map.get`) in the "
            "`@EmitterFactoryFor` map before `handleEmitter`; otherwise `handleChannelInjection`: "
            + ("yes" if keyed else "NOT FOUND"),
        )
        empty = [r for r in recipes(wiring, extract) if r.startswith("Empty")]
        for handler in ("handleMethodAnnotatedWithIncoming", "handleMethodAnnotationWithOutgoing"):
            empty += [r for r in recipes(wiring, body(wiring, handler)) if r.startswith("Empty")]
        emit(
            "what an empty `@Incoming` / `@Outgoing` value does",
            key,
            "a `DeploymentException` (validation error): "
            + ("; ".join(f"`{r}`" for r in dict.fromkeys(empty)) or "NOT FOUND"),
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ProbeError as error:
        print(f"CP-49 aborted: {error}", file=sys.stderr)
        sys.exit(1)
