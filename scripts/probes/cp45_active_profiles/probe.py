"""CP-45: which configuration keys name the active profiles, which profile is active when none
is named, and where a profile-specific file may not set them? Every cell is read off the jars
with `javap`; the version in each column is the jar's own manifest. Prints the observation
table `cp45_active_profiles.md` carries."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _spring_jar import javap, manifest_version, newest_jar

ENVIRONMENT = "org.springframework.core.env.AbstractEnvironment"
PROFILES = "org.springframework.boot.context.config.Profiles"
TYPE = PROFILES + "$Type"
CONFIG_DATA = "org.springframework.boot.context.config.ConfigDataEnvironment"
INVALID = "org.springframework.boot.context.config.InvalidConfigDataPropertyException"

_HEADER = re.compile(r"^  \S.*(?:\)|\{\})(?: throws [\w.,\s$]+)?;$")


def bodies(listing: str) -> dict[str, str]:
    """`javap -c -p` output as method header -> its instruction listing."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in listing.splitlines():
        if _HEADER.match(line):
            current = found.setdefault(line.strip(), [])
        elif current is not None:
            current.append(line)
    return {header: "\n".join(lines) for header, lines in found.items()}


def body(listing: str, name: str) -> str:
    """The first method whose header names `name` (`static {}` for the initialiser)."""
    pattern = re.compile(rf"(?:^|\s){re.escape(name)}(?:\(|$|;)")
    return next((text for header, text in bodies(listing).items() if pattern.search(header)), "")


def strings(text: str) -> list[str]:
    """The string constants a listing loads, in order."""
    return re.findall(r"// String (\S+)\s*$", text, re.MULTILINE)


def invoked(text: str) -> list[str]:
    """The simple names of the methods a listing invokes, in order, once each."""
    names = re.findall(r"// (?:Interface)?Method (?:[\w/$]+\.)?(\"?<?[\w$]+>?\"?):", text)
    return list(dict.fromkeys(names))


def constants(jar: Path, class_name: str) -> dict[str, str]:
    """The `static final String` constants a class declares, name -> value."""
    return dict(
        re.findall(
            r"static final java\.lang\.String (\w+) = \"([^\"]*)\";",
            javap(jar, class_name, "-constants", "-p"),
        )
    )


def main() -> int:
    core = newest_jar("org.springframework", "spring-core")
    boot = newest_jar("org.springframework.boot", "spring-boot")
    if core is None or boot is None:
        print("spring-core / spring-boot NOT IN THE LOCAL REPOSITORY")
        return 1
    v_core, v_boot = manifest_version(core), manifest_version(boot)
    print(f"| what the run read | {v_core} | {v_boot} |")
    print("|---|---|---|")
    print("| artifact reporting this version | spring-core | spring-boot |")
    print("| where the jar states that version | MANIFEST.MF | MANIFEST.MF |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    environment = constants(core, ENVIRONMENT)
    named = [
        f"`{name}` = `{environment.get(name, 'NOT DECLARED')}`"
        for name in (
            "ACTIVE_PROFILES_PROPERTY_NAME",
            "DEFAULT_PROFILES_PROPERTY_NAME",
            "RESERVED_DEFAULT_PROFILE_NAME",
        )
    ]
    print(
        f"| 1 | the keys naming the active and the default profiles, and the reserved default "
        f"profile | `spring-core` | {v_core} | `AbstractEnvironment` declares {', '.join(named)} |"
    )

    include = constants(boot, PROFILES).get("INCLUDE_PROFILES_PROPERTY_NAME", "NOT DECLARED")
    print(
        f"| 2 | the key naming profiles included beside the active ones | `spring-boot` | "
        f"{v_boot} | `Profiles` declares `INCLUDE_PROFILES_PROPERTY_NAME` = `{include}` |"
    )

    kinds = strings(body(javap(boot, TYPE, "-c", "-p", "-constants"), "static {}"))
    print(
        f"| 3 | what Boot's two profile kinds read | `spring-boot` | {v_boot} | `Profiles$Type`'s "
        f"initialiser loads `{'`, `'.join(kinds)}` — each kind with the key it reads, and "
        f"`DEFAULT` with the value it falls back to |"
    )

    profiles = javap(boot, PROFILES, "-c", "-p")
    read = invoked(body(profiles, "getProfiles"))
    wanted = [
        name
        for name in read
        if name in ("getProperty", "trimAllWhitespace", "commaDelimitedListToSet", "bind")
    ]
    bound = "STRING_SET" in body(profiles, "getProfiles")
    print(
        f"| 4 | how a kind's value becomes profiles | `spring-boot` | {v_boot} | `getProfiles` "
        f"runs `{' -> '.join(wanted)}`{', binding to `STRING_SET` (a `Set<String>`)' if bound else ''}"
        f" — a comma-separated value, whitespace removed, or a list |"
    )

    accepted = body(profiles, "getAccepted")
    fields = re.findall(r"// Field (\w+):", accepted)
    tests = invoked(accepted)
    constructor = body(profiles, PROFILES)
    activated = invoked(body(profiles, "getActivatedProfiles"))
    print(
        f"| 5 | which profiles are accepted | `spring-boot` | {v_boot} | `getAccepted` reads "
        f"`{'`, `'.join(dict.fromkeys(fields))}` and tests `{'`, `'.join(tests)}`: the active "
        f"list unless it is empty, else the default list; `getActivatedProfiles` runs "
        f"`{' -> '.join(activated)}` over the `ACTIVE` kind and the constructor's additional "
        f"profiles; the constructor also binds `{'`, `'.join(strings(constructor))}` and runs "
        f"`{'expandProfiles' if 'expandProfiles' in invoked(constructor) else 'NO expansion'}` |"
    )

    config_data = javap(boot, CONFIG_DATA, "-c", "-p")
    # In order: the included profiles read, added to the additional set, and handed to the
    # `Profiles` constructor (a `LinkedHashSet`'s own constructor is not one of them).
    steps = re.findall(
        r"// (?:Interface)?Method ([\w/$]*?(?:getIncludedProfiles|Set\.addAll|"
        r"config/Profiles\.\"<init>\"|ConfigDataActivationContext\.withProfiles)):",
        body(config_data, "withProfiles"),
    )
    steps = [step.rsplit("/", 1)[-1] for step in steps]
    included = "Profiles.INCLUDE_PROFILES" in body(config_data, "lambda$getIncludedProfiles$0")
    print(
        f"| 6 | where included profiles join the active ones | `spring-boot` | {v_boot} | "
        f"`ConfigDataEnvironment.withProfiles` runs `{' -> '.join(steps)}`: "
        f"`getIncludedProfiles` (reading `Profiles.INCLUDE_PROFILES`: "
        f"{'yes' if included else 'NO'}) is added to the additional profiles handed to "
        f"`new Profiles(…)` |"
    )

    invalid = strings(body(javap(boot, INVALID, "-c", "-p"), "static {}"))
    print(
        f"| 7 | which keys a profile-specific file may not set | `spring-boot` | {v_boot} | "
        f"`InvalidConfigDataPropertyException`'s initialiser builds `PROFILE_SPECIFIC_ERRORS` "
        f"from `Profiles.INCLUDE_PROFILES` (and its `[0]`) and `"
        f"{'`, `'.join(s for s in invalid if s.startswith(('spring.profiles.a', 'spring.profiles.d')))}"
        f"` |"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
