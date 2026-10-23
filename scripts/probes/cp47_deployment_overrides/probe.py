"""CP-47: does a deployment outrank the configuration files a module ships? Where do the
command line, the OS environment and the config-data files sit in Spring Boot's property
sources, how does an environment variable name a property, and does the first source that
has a key win? Every cell is read off the jars with `javap`; the version in each column is the
jar's own manifest. Prints the observation table `cp47_deployment_overrides.md` carries."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _spring_jar import javap, manifest_version, newest_jar

APPLICATION = "org.springframework.boot.SpringApplication"
CONFIG_DATA = "org.springframework.boot.context.config.ConfigDataEnvironment"
STANDARD = "org.springframework.core.env.StandardEnvironment"
SYSTEM_SOURCE = "org.springframework.core.env.SystemEnvironmentPropertySource"
RESOLVER = "org.springframework.core.env.PropertySourcesPropertyResolver"
MAPPER = "org.springframework.boot.context.properties.source.SystemEnvironmentPropertyMapper"
NAME = "org.springframework.boot.context.properties.source.ConfigurationPropertyName"
PROPERTY = "org.springframework.boot.autoconfigure.condition.OnPropertyCondition"

_HEADER = re.compile(r"^  \S.*(?:\)|\{\})(?: throws [\w.,\s$]+)?;$")


def body(listing: str, header: str) -> str:
    """The instruction listing of the first method whose header contains `header`."""
    lines: list[str] = []
    inside = False
    for line in listing.splitlines():
        if _HEADER.match(line):
            if inside:
                break
            inside = header in line
        elif inside:
            lines.append(line)
    return "\n".join(lines)


def calls(text: str) -> list[str]:
    """`Class.method` for every method a listing invokes, in order."""
    return [
        f"{owner.rsplit('/', 1)[-1]}.{name.strip(chr(34))}"
        for owner, name in re.findall(
            r"// (?:Interface)?Method ([\w/$]+)\.(\"?<?[\w$]+>?\"?):", text
        )
    ]


def strings(text: str) -> list[str]:
    return re.findall(r"// String (\S+)\s*$", text, re.MULTILINE)


def constructed(text: str) -> list[str]:
    found = re.findall(r"new\s+#\d+\s+// class (\S+)", text)
    return list(dict.fromkeys(name.rsplit("/", 1)[-1] for name in found))


def join(items: list[str]) -> str:
    return "`" + "`, `".join(items) + "`" if items else "NOTHING"


def main() -> int:
    core = newest_jar("org.springframework", "spring-core")
    boot = newest_jar("org.springframework.boot", "spring-boot")
    auto = newest_jar("org.springframework.boot", "spring-boot-autoconfigure")
    if core is None or boot is None or auto is None:
        print("spring-core / spring-boot / spring-boot-autoconfigure NOT IN THE LOCAL REPOSITORY")
        return 1
    v_core, v_boot, v_auto = manifest_version(core), manifest_version(boot), manifest_version(auto)
    print(f"| what the run read | {v_core} | {v_boot} | {v_auto} |")
    print("|---|---|---|---|")
    print(
        "| artifact reporting this version | spring-core | spring-boot | spring-boot-autoconfigure |"
    )
    print("| where the jar states that version | MANIFEST.MF | MANIFEST.MF | MANIFEST.MF |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    configure = body(
        javap(boot, APPLICATION, "-c", "-p"), "configurePropertySources(org.springframework"
    )
    on_sources = [c for c in calls(configure) if c.startswith("MutablePropertySources.")]
    command_line = [c for c in constructed(configure) if c == "SimpleCommandLinePropertySource"]
    first = "MutablePropertySources.addFirst" in on_sources and bool(command_line)
    print(
        f"| 1 | where the command line is put among the property sources | `spring-boot` | "
        f"{v_boot} | `SpringApplication.configurePropertySources` loads "
        f"{join(strings(configure))}, constructs {join(constructed(configure))} and runs "
        f"{join(on_sources)} on the property sources; the command-line source is added by "
        f"`{'addFirst' if first else 'NOT addFirst'}` |"
    )

    standard = body(javap(core, STANDARD, "-c", "-p"), "customizePropertySources(")
    standard_adds = [c for c in calls(standard) if c.startswith("MutablePropertySources.")]
    named = strings(standard)
    applied = body(javap(boot, CONFIG_DATA, "-c", "-p"), "applyContributor(")
    applied_adds = [c for c in calls(applied) if c.startswith("MutablePropertySources.")]
    wrapped = body(javap(boot, CONFIG_DATA, "-c", "-p"), "applyToEnvironment(")
    moved = [c for c in calls(wrapped) if c.endswith(".moveToEnd")]
    order = ["commandLineArgs"] if first else []
    order += named if standard_adds == ["MutablePropertySources.addLast"] * len(named) else []
    order += ["config data files"] if applied_adds == ["MutablePropertySources.addLast"] else []
    print(
        f"| 2 | where the OS environment and the configuration files sit | `spring-core`, "
        f"`spring-boot` | {v_core}, {v_boot} | `StandardEnvironment.customizePropertySources` "
        f"loads {join(named)} and runs {join(standard_adds)}; "
        f"`ConfigDataEnvironment.applyContributor` runs {join(applied_adds)} for each config-data "
        f"source and `applyToEnvironment` ends with {join(moved)}; so the order, highest "
        f"first, is {' > '.join(f'`{item}`' for item in order)} |"
    )

    resolve = body(javap(core, SYSTEM_SOURCE, "-c", "-p"), "checkPropertyName(")
    swaps = re.findall(
        r"bipush\s+(\d+)\s*\n\s*\d+: bipush\s+(\d+)\s*\n.*String\.replace:\(CC\)", resolve
    )
    swapped = [(chr(int(a)), chr(int(b))) for a, b in swaps]
    resolving = body(javap(core, SYSTEM_SOURCE, "-c", "-p"), "resolvePropertyName(")
    upper = "String.toUpperCase" in calls(resolving)

    def environment_variable(key: str) -> str:
        name = key
        for old, new in dict.fromkeys(swapped):
            name = name.replace(old, new)
        return name.upper() if upper else name

    mapper = javap(boot, MAPPER, "-c", "-p")
    candidates = re.findall(
        r"Field [\w/$]*\$ToStringFormat\.(\w+):.*\n\s*\d+: (iconst_[01])\n",
        body(
            mapper,
            "map(org.springframework.boot.context.properties.source.ConfigurationPropertyName)",
        ),
    )
    asked = [
        f"{kind} {'upper' if flag == 'iconst_1' else 'as-is'} case" for kind, flag in candidates
    ]
    convert = body(mapper, "convertName(")
    separator = re.search(
        r"bipush\s+(\d+)\s*\n(?:.*\n)*?.*ConfigurationPropertyName\.adapt:", convert
    )
    lowered = "String.toLowerCase" in calls(body(mapper, "processElementValue("))
    formats = body(javap(boot, NAME, "-c", "-p"), "buildToString(")
    joined = sorted(set(re.findall(r"bipush\s+(\d+)", formats)))
    split_on = chr(int(separator[1])) if separator else "NONE"
    print(
        f"| 3 | how an environment variable names a property | `spring-core`, `spring-boot` | "
        f"{v_core}, {v_boot} | `SystemEnvironmentPropertySource.checkPropertyName` replaces "
        f"{join([f'{a} with {b}' for a, b in dict.fromkeys(swapped)])} and "
        f"`resolvePropertyName` upper-cases: {'yes' if upper else 'NO'}, so "
        f"`spring.profiles.active` is looked up as `{environment_variable('spring.profiles.active')}` "
        f"and `billing.enabled` as `{environment_variable('billing.enabled')}`; the binder's "
        f"`SystemEnvironmentPropertyMapper.map` offers {join(asked)} and `convertName` adapts "
        f"with separator `{split_on}` and lower-cases "
        f"each element: {'yes' if lowered else 'NO'}; `buildToString` joins with "
        f"`{'`, `'.join(chr(int(code)) for code in joined)}`, so `BILLING_ENABLED` reads as "
        f"`{'.'.join(part.lower() for part in 'BILLING_ENABLED'.split(split_on))}` |"
    )

    resolver = javap(core, RESOLVER, "-c", "-p")
    getter = body(resolver, "getProperty(java.lang.String, java.lang.Class<T>, boolean)")
    steps = calls(getter)
    walk = [
        step
        for step in steps
        if step
        in (
            "PropertySources.iterator",
            "Iterator.hasNext",
            "Iterator.next",
            "PropertySource.getProperty",
        )
    ]
    merges = [step for step in steps if re.search(r"\.(put|putAll|addAll|merge|add)$", step)]
    skip = re.search(
        r"PropertySource\.getProperty:.*\n(?:.*\n){1,2}?\s*\d+: ifnull\s+(\d+)", getter
    )
    back = skip is not None and re.search(rf"\n\s*{skip[1]}: goto\s+\d+", getter) is not None
    returns = re.search(r"convertValueIfNecessary:.*\n\s*\d+: areturn", getter) is not None
    print(
        f"| 4 | whether the first source holding a key wins | `spring-core` | {v_core} | "
        f"`PropertySourcesPropertyResolver.getProperty` runs {join(list(dict.fromkeys(walk)))} "
        f"over the sources in order; a null value jumps back to the next source: "
        f"{'yes' if back else 'NO'}; a non-null one is converted and returned at once: "
        f"{'yes' if returns else 'NO'}; calls that merge values: {join(merges)} |"
    )

    spec = javap(auto, PROPERTY + "$Spec", "-c", "-p")
    collect = body(spec, "collectProperties(")
    read = [c for c in calls(collect) if c.startswith("PropertyResolver.")]
    condition = body(javap(auto, PROPERTY, "-c", "-p"), "getMatchOutcome(")
    environment = "ConditionContext.getEnvironment" in calls(condition)
    print(
        f"| 5 | what `@ConditionalOnProperty` reads a key through | `spring-boot-autoconfigure` | "
        f"{v_auto} | `OnPropertyCondition$Spec.collectProperties` runs {join(list(dict.fromkeys(read)))}; "
        f"`getMatchOutcome` takes the resolver from `ConditionContext.getEnvironment`: "
        f"{'yes' if environment else 'NO'} |"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
