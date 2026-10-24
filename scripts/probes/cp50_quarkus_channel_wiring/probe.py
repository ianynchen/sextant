"""CP-50: which channels does Quarkus attach a connector to without being told, and when? How
it finds an ORPHAN channel, what makes a channel connector-managed, when the one connector of a
direction is attached, the build-time flag that gates it, and what kind of configuration the
attachment writes. Every cell is read off the jars with `javap -v`; the version in each column
is the jar's own manifest. Prints the observation table `cp50_quarkus_channel_wiring.md`
carries."""

import re
import sys
import zipfile
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
    lambda_targets,
    recipes,
    strings,
    targets,
)

PACKAGE = "io.quarkus.smallrye.reactivemessaging"
DEPLOYMENT = f"{PACKAGE}.deployment"
ITEMS = f"{DEPLOYMENT}.items"
WIRING = f"{DEPLOYMENT}.WiringProcessor"
HELPER = f"{DEPLOYMENT}.WiringHelper"
CHANNEL_ITEM = f"{ITEMS}.ChannelBuildItem"
BUILD_CONFIG = f"{DEPLOYMENT}.ReactiveMessagingBuildTimeConfig"
NAMES = f"{DEPLOYMENT}.ReactiveMessagingDotNames"
CONFIG_ROOT = "io.quarkus.runtime.annotations.ConfigRoot"

VERSIONS = ["3.17.5", "3.40.1.1"]
CORE = ("io.quarkus", "quarkus-core", "3.17.5")


class Version:
    """One Quarkus generation's deployment jar (and its runtime jar, which 3.40 moves the
    configuration-key helpers into), parsed once."""

    def __init__(self, version: str) -> None:
        deployment = jar_at("io.quarkus", "quarkus-messaging-deployment", version)
        runtime = jar_at("io.quarkus", "quarkus-messaging", version)
        if deployment is None or runtime is None:
            raise FileNotFoundError(version)
        self.runtime = runtime
        self.stated = identity(deployment, version)[0]
        identity(runtime, version)
        self.classes: dict[str, ClassFile] = {
            **classes(deployment, [WIRING, HELPER, CHANNEL_ITEM, BUILD_CONFIG, NAMES]),
            **classes(runtime),
        }

    def find(self, owner: str, default: str) -> ClassFile:
        return self.classes[owner or default]


def key_built_by(version: Version, owner: ClassFile, steps: list[Instruction]) -> list[str]:
    """Each configuration key a body builds, in order: a string concatenation's recipe, or a
    static helper (in either jar) that formats an `ldc`'d `%s` pattern with the constant the
    caller loaded just before calling it. Channel names and directions the caller supplies
    show as `<>`."""
    found: list[str] = []
    concat = iter(recipes(owner, steps))
    last_constant: str | None = None
    for step, target in zip(steps, _per_step_targets(steps), strict=True):
        if step.opcode.startswith("ldc") and step.comment.startswith("String "):
            last_constant = step.comment.split("String ", 1)[1]
        elif step.opcode == "invokedynamic" and "makeConcatWithConstants" in step.comment:
            found.append(next(concat))
        elif step.opcode == "invokestatic" and target and target[0] in version.classes:
            pattern = next(
                (s for s in strings(body(version.classes[target[0]], target[1])) if "%s" in s),
                None,
            )
            if pattern is not None:
                rendered = pattern.replace("%s", "<>", 1).replace("%s", last_constant or "<>", 1)
                found.append(f"{rendered} (via `{target[0].rsplit('.', 1)[-1]}.{target[1]}`)")
    return found


def _per_step_targets(steps: list[Instruction]) -> list[tuple[str, str] | None]:
    resolved = iter(targets(steps))
    return [
        next(resolved)
        if step.opcode.startswith("invoke") and re.match(r"(?:Interface)?Method ", step.comment)
        else None
        for step in steps
    ]


def int_constant(step: Instruction) -> int | None:
    """The int an `iconst_N` / `bipush` / `sipush` pushes."""
    if step.opcode.startswith("iconst_") and step.opcode[-1].isdigit():
        return int(step.opcode.rsplit("_", 1)[1])
    if step.opcode in ("bipush", "sipush") and step.operand.isdigit():
        return int(step.operand)
    return None


def runtime_customizers(version: Version) -> str:
    """The `SmallRyeConfigBuilderCustomizer`s the runtime jar registers, the interceptors each
    installs, and what each interceptor's key function rewrites (its `ldc`'d prefixes and its
    concatenation recipe)."""
    service = "META-INF/services/io.smallrye.config.SmallRyeConfigBuilderCustomizer"
    with zipfile.ZipFile(version.runtime) as archive:
        if service not in archive.namelist():
            return f"no `{service}` in the jar: only the `mp.messaging.` spelling is read"
        registered = archive.read(service).decode().split()
    found = []
    for name in registered:
        customizer = version.classes.get(name)
        if customizer is None:
            found.append(f"`{name}` NOT IN THIS JAR")
            continue
        built = body(customizer, "configBuilder")
        created = [
            s.comment.split("class ", 1)[1].replace("/", ".")
            for s in built
            if s.opcode == "new" and s.comment.startswith("class ")
        ]
        for interceptor, function in zip(created[0::2], created[1::2], strict=False):
            target = version.classes[function]
            apply = body(target, "apply")
            prefix, *segments = strings(apply)
            cut = next(
                (
                    int_constant(apply[i - 1])
                    for i, step in enumerate(apply)
                    if "String.substring:(I)" in step.comment
                ),
                None,
            )
            recipe = next(iter(recipes(target, apply)), None)
            if cut is None or recipe is None:
                found.append(f"`{function}`: rewrite NOT FOUND")
                continue
            examples = [
                f"`{key}` -> `{recipe.replace('<>', key[cut:])}`"
                for key in (f"{prefix}{segment}<channel>.<attribute>" for segment in segments)
            ]
            found.append(
                f"`{interceptor.rsplit('.', 1)[-1]}` (`{function.rsplit('$', 1)[-1]}`): "
                + ", ".join(examples)
            )
    return f"`{'`, `'.join(r.rsplit('.', 1)[-1] for r in registered)}` registered; " + "; ".join(
        found
    )


def named(names: dict[str, str], steps: list[Instruction]) -> str:
    """The FQN behind each `ReactiveMessagingDotNames` constant a body reads."""
    return ", ".join(
        f"`{names.get(f.split('.', 1)[1], f)}`"
        for f in fields(steps)
        if f.startswith("ReactiveMessagingDotNames.")
    )


def jumps_to_return(steps: list[Instruction], after: str) -> bool:
    """Whether the conditional branch right after the call to `after` lands on `return`."""
    offsets = {step.offset: step for step in steps}
    for i, step in enumerate(steps):
        if after in step.comment and i + 1 < len(steps) and steps[i + 1].opcode.startswith("if"):
            target = offsets.get(int(steps[i + 1].operand.split()[0]))
            return target is not None and target.opcode == "return"
    return False


def main() -> int:
    loaded: dict[str, Version] = {}
    for version in VERSIONS:
        try:
            loaded[version] = Version(version)
        except FileNotFoundError:
            print(
                f"NOT IN THE LOCAL REPOSITORY: quarkus-messaging(-deployment) {version}",
                file=sys.stderr,
            )
    if not loaded:
        return 1
    core = jar_at(*CORE)
    core_stated = identity(core, CORE[2])[0] if core else None

    columns = sorted(
        {v.stated for v in loaded.values()} | ({core_stated} if core_stated else set())
    )
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(
                (
                    ["io.quarkus:quarkus-messaging-deployment", "io.quarkus:quarkus-messaging"]
                    if column in loaded
                    else []
                )
                + (["io.quarkus:quarkus-core"] if column == core_stated else [])
            )
            for column in columns
        )
        + " |"
    )
    print(
        "| where the jar states that version | "
        + " | ".join("MANIFEST.MF `Implementation-Version`" for _ in columns)
        + " |"
    )
    for version in VERSIONS:
        if version not in loaded:
            print(f"| {version} | NOT MEASURED — not in the local repository |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    row = 0

    def emit(question: str, artifact: str, version: str, observed: str) -> None:
        nonlocal row
        row += 1
        print(f"| {row} | {question} | `{artifact}` | {version} | {observed} |")

    deployment = "io.quarkus:quarkus-messaging-deployment"
    for version, v in loaded.items():
        wiring = v.classes[WIRING]
        helper = v.classes[HELPER]
        names = dotnames(v.classes[NAMES])

        detect = body(wiring, "detectOrphanChannels")
        calls = called(detect)
        managed_skips = any(
            "isManagedByAConnector" in step.comment and detect[i + 1].opcode == "ifne"
            for i, step in enumerate(detect[:-1])
        )
        # The direction each `OrphanChannelBuildItem.of` is handed: the last
        # `ChannelDirection` constant loaded before the call.
        orphan_directions = []
        direction = "NONE"
        for step in detect:
            if step.opcode == "getstatic" and "ChannelDirection." in step.comment:
                direction = fields([step])[0].split(".", 1)[1]
            elif "OrphanChannelBuildItem.of" in step.comment:
                orphan_directions.append(direction)
        emit(
            "how an orphan channel is found (`detectOrphanChannels`)",
            deployment,
            version,
            f"keys each direction's channels by `getName` (`Map.put` x{calls.count('Map.put')}); "
            f"copies each direction's key set and `removeAll`s the other's "
            f"(`Set.removeAll` x{calls.count('Set.removeAll')}); skips a remaining name whose "
            f"channel `isManagedByAConnector` (`ifne`): {'yes' if managed_skips else 'NO'}; "
            f"produces `OrphanChannelBuildItem.of` for directions "
            f"`{'`, `'.join(orphan_directions)}`",
        )

        managed = body(v.classes[CHANNEL_ITEM], "isManagedByAConnector")
        emit(
            "what makes a channel connector-managed (`ChannelBuildItem.isManagedByAConnector`)",
            deployment,
            version,
            f"reads field `{'`, `'.join(fields(managed, 'getfield'))}` and tests "
            f"`{'`, `'.join(s.opcode for s in managed if s.opcode.startswith('if'))}` "
            "(managed when it is not null)",
        )

        connector = body(helper, "getManagingConnector")
        enabled = body(helper, "isChannelEnabled")
        enabled_default = (
            "true"
            if any(s.opcode == "iconst_1" for s in enabled)
            and "Boolean.valueOf" in called(enabled)
            and "Optional.orElse" in called(enabled)
            else "NOT FOUND"
        )
        emit(
            "where a channel's connector comes from, and when it counts",
            deployment,
            version,
            f"`getManagingConnector` reads `Config.getOptionalValue` of "
            f"`{'`, `'.join(key_built_by(v, helper, connector))}`; `isChannelEnabled` reads "
            f"`{'`, `'.join(key_built_by(v, helper, enabled))}`, default `{enabled_default}`",
        )

        produced = []
        for producer, factory in (
            ("produceIncomingChannel", "ChannelBuildItem.incoming"),
            ("produceOutgoingChannel", "ChannelBuildItem.outgoing"),
        ):
            steps = body(helper, producer)
            silent = jumps_to_return(steps, "isChannelEnabled")
            unmanaged = any(
                step.opcode == "aconst_null" and factory in steps[i + 1].comment
                for i, step in enumerate(steps[:-1])
            )
            sequence = "` -> `".join(dict.fromkeys(c.split(".")[-1] for c in called(steps)))
            produced.append(
                f"`{producer}` calls `{sequence}`; a connector-configured channel that is not "
                f"enabled produces nothing (the branch after `isChannelEnabled` lands on "
                f"`return`): {'yes' if silent else 'NO'}; one with no configured connector is "
                f"`{factory.split('.')[-1]}(name, null)`: {'yes' if unmanaged else 'NO'}"
            )
        emit(
            "what a named channel becomes (`produceIncomingChannel`, `produceOutgoingChannel`)",
            deployment,
            version,
            "; ".join(produced),
        )

        normalize_owner, _ = next(
            (t for t in targets(connector) if t[1] == "normalizeChannelName"), ("", "")
        )
        normalize_cls = v.find(normalize_owner, HELPER)
        normalize = body(normalize_cls, "normalizeChannelName")
        emit(
            "how a channel name is written into a key (`normalizeChannelName`)",
            deployment if normalize_cls is helper else "io.quarkus:quarkus-messaging",
            version,
            f"`{normalize_cls.name.rsplit('.', 1)[-1]}.normalizeChannelName` tests "
            f"`{'`, `'.join(c.split('.')[-1] for c in called(normalize) if 'concat' not in c)}` "
            f"against `{'`, `'.join(strings(normalize))}` and rewrites to "
            f"`{'`, `'.join(recipes(normalize_cls, normalize))}` (quoted when the name "
            "contains `.` and is not already quoted)",
        )

        lambda_filter = body(wiring, "lambda$discoverConnectors$0")
        lambda_produce = body(wiring, "lambda$discoverConnectors$1")
        inbound = body(helper, "isInboundConnector")
        outbound = body(helper, "isOutboundConnector")
        connector_name = body(helper, "getConnectorName")

        created = [c.split(".")[-1] for c in called(lambda_produce) if "create" in c]
        emit(
            "what counts as a connector on the classpath, and its direction (`discoverConnectors`)",
            deployment,
            version,
            f"every bean carrying the qualifier {named(names, lambda_filter)}; incoming when its "
            f"class implements {named(names, inbound)}; outgoing when it implements "
            f"{named(names, outbound)}; its name is the qualifier's `value()` (`getConnectorName` "
            f"reads {named(names, connector_name)}); produces `{'`, `'.join(created)}`",
        )

        attach = body(wiring, "autoConfigureConnectorForOrphansAndProduceManagedChannels")
        single = sum(
            1
            for i, step in enumerate(attach[:-2])
            if "Set.size" in step.comment
            and attach[i + 1].opcode == "iconst_1"
            and attach[i + 2].opcode == "if_icmpne"
        )
        flag = [c.split(".")[-1] for c in called(attach) if "autoConnectorAttachment" in c] + [
            f for f in fields(attach, "getfield") if "autoConnectorAttachment" in f
        ]
        defaults = [
            k for k in key_built_by(v, wiring, attach) if "connector" in k and "unknown" not in k
        ]
        written = [
            c.split(".")[0] for c in called(attach) if c.endswith('"<init>"') and "Default" in c
        ]
        managed_items = called(attach).count('ConnectorManagedChannelBuildItem."<init>"')
        emit(
            "when an orphan gets a connector "
            "(`autoConfigureConnectorForOrphansAndProduceManagedChannels`)",
            deployment,
            version,
            f"collects each direction's connector names into a set; `Set.size() == 1` tested "
            f"x{single} (once per direction), each behind `{'`, `'.join(dict.fromkeys(flag))}`; "
            f"for every orphan of that direction it writes `{'`, `'.join(dict.fromkeys(written))}` "
            f"of `{'`, `'.join(defaults)}` = the one connector's name, and a "
            f"`ConnectorManagedChannelBuildItem` (x{managed_items})",
        )

        unknown = [r for r in key_built_by(v, wiring, attach) if "unknown" in r]
        tail = called(attach)
        checked = [i for i, c in enumerate(tail) if c.endswith("isManagedByAConnector")]
        noise = ("getName", "getDirection", "getConnector", "produce")
        after = [
            c if "<init>" in c else c.split(".")[-1]
            for c in (tail[checked[-1] :] if checked else [])
            if not any(n in c for n in noise)
        ]
        has = body(helper, "hasConnector")
        matcher = [
            c.split(".")[-1]
            for t in lambda_targets(helper, has)
            for c in called(body(helper, t.split(".")[-1]))
        ]
        emit(
            "what happens to a channel whose connector is configured",
            deployment,
            version,
            f"for every channel that `isManagedByAConnector`, calls "
            f"`{'` -> `'.join(after)}`: "
            f"a `ConnectorManagedChannelBuildItem` when `WiringHelper.hasConnector` "
            f"(`{'`, `'.join(c.split('.')[-1] for c in called(has))}` over the connectors, testing "
            f"`{'`, `'.join(matcher)}`) finds the configured name, otherwise a `WiringException` "
            f"`{'`, `'.join(unknown) or 'NOT FOUND'}`; it is never an orphan (row on "
            "`detectOrphanChannels`)",
        )

        services = runtime_customizers(v)
        emit(
            "which spellings of a channel's configuration key Quarkus accepts",
            "io.quarkus:quarkus-messaging",
            version,
            services,
        )

        config = v.classes[BUILD_CONFIG]
        member = config.member("autoConnectorAttachment")
        root = config.annotation(CONFIG_ROOT)
        mapping = config.annotation("io.smallrye.config.ConfigMapping")
        if member is None:
            emit("the build-time flag's key and default", deployment, version, "NOT DECLARED")
            continue
        item = next((a for a in member.annotations if a.type.endswith("ConfigItem")), None)
        with_name = next((a for a in member.annotations if a.type.endswith("WithName")), None)
        with_default = next((a for a in member.annotations if a.type.endswith("WithDefault")), None)
        phase = root.elements.get("phase") if root else None
        if mapping is not None and with_name is not None:
            prefix = str(mapping.elements["prefix"])
            name = str(with_name.elements["value"])
            default = with_default.elements["value"] if with_default else "NONE"
            how = (
                f'`@ConfigMapping(prefix="{prefix}")` + `@WithName("{name}")`, '
                f'`@WithDefault("{default}")`'
            )
        elif root is not None and item is not None:
            prefix_default = "NOT MEASURED (quarkus-core not in the local repository)"
            if core is not None:
                root_cls = classes(core, [CONFIG_ROOT])[CONFIG_ROOT]
                prefix_member = root_cls.member("prefix")
                prefix_default = str(prefix_member.default) if prefix_member else "NOT DECLARED"
            prefix = f"{prefix_default}.{root.elements['name']}"
            name = str(item.elements["name"])
            default = item.elements.get("defaultValue", "NONE")
            how = (
                f'`@ConfigRoot(name="{root.elements["name"]}")` (prefix default '
                f'`"{prefix_default}"`, quarkus-core {core_stated}) + '
                f'`@ConfigItem(name="{name}", defaultValue="{default}")`'
            )
        else:
            emit("the build-time flag's key and default", deployment, version, "NOT FOUND")
            continue
        emit(
            "the build-time flag's key and default",
            deployment,
            version,
            f"`{prefix}.{name}` = `{default}`, phase `{phase}`; {how}",
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ProbeError as error:
        print(f"CP-50 aborted: {error}", file=sys.stderr)
        sys.exit(1)
