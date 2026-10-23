"""CP-46: which interfaces does Spring Data's repository scanning register as beans, which does
it refuse, and does it evaluate an interface's own conditions? Every cell is read off the jars
with `javap`; the version in each column is the jar's own manifest. Prints the observation
table `cp46_repository_interface_beans.md` carries."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _spring_jar import javap, manifest_version, newest_jar

PROVIDER = "org.springframework.data.repository.config.RepositoryComponentProvider"
INTERFACE_FILTER = PROVIDER + "$InterfaceTypeFilter"
SCANNER = "org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider"
ANNOTATION_FILTER = "org.springframework.core.type.filter.AnnotationTypeFilter"

_HEADER = re.compile(r"^  \S.*\)(?: throws [\w.,\s$]+)?;$")


def bodies(listing: str) -> dict[str, list[str]]:
    """`javap -c -p` output as method header -> its instruction lines."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in listing.splitlines():
        if _HEADER.match(line):
            current = found.setdefault(line.strip(), [])
        elif current is not None:
            current.append(line)
    return found


def body(listing: str, pattern: str) -> list[str]:
    """The first method whose header matches `pattern`."""
    return next(
        (lines for header, lines in bodies(listing).items() if re.search(pattern, header)), []
    )


def invoked(lines: list[str]) -> list[str]:
    """The simple names of the methods the lines invoke, in order, once each."""
    names = [
        m.group(1)
        for line in lines
        if (m := re.search(r"// (?:Interface)?Method (?:[\w/$]+\.)?(\"?<?[\w$]+>?\"?):", line))
    ]
    return list(dict.fromkeys(names))


def short(name: str) -> str:
    return name.rsplit("/", 1)[-1].rsplit(".", 1)[-1]


def filters(lines: list[str]) -> list[str]:
    """Each filter the constructor builds, in order, as `Filter(Class, flags…)` and the method
    it is handed to (`addIncludeFilter` / `addExcludeFilter`)."""
    found: list[str] = []
    handed: list[str] = []
    flags: list[str] = []
    filter_class = ""
    for line in lines:
        if "// class " in line and " new " in line:
            filter_class, handed, flags = short(line.rsplit(" ", 1)[-1]), [], []
        elif "// class " in line and "ldc" in line:
            handed = [short(line.rsplit(" ", 1)[-1])]
        elif re.search(r"iconst_[01]", line) and handed:
            flags.append("true" if "iconst_1" in line else "false")
        elif (m := re.search(r"(add(?:Include|Exclude)Filter)", line)) and handed:
            found.append(f"`{filter_class}({', '.join(handed + flags)})` -> `{m.group(1)}`")
            handed, flags = [], []
    return found


def main() -> int:
    data = newest_jar("org.springframework.data", "spring-data-commons")
    context = newest_jar("org.springframework", "spring-context")
    core = newest_jar("org.springframework", "spring-core")
    if data is None or context is None or core is None:
        print("spring-data-commons / spring-context / spring-core NOT IN THE LOCAL REPOSITORY")
        return 1
    v_data, v_context, v_core = (manifest_version(j) for j in (data, context, core))
    print(f"| what the run read | {v_data} | {v_context} |")
    print("|---|---|---|")
    print("| artifact reporting this version | spring-data-commons | spring-context, spring-core |")
    print("| where the jar states that version | MANIFEST.MF | MANIFEST.MF |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    header = next(
        (line for line in javap(data, PROVIDER).splitlines() if "class " in line), ""
    ).strip()
    parent = re.search(r"extends ([\w.$]+)", header)
    print(
        f"| 1 | what the repository scanner is | `spring-data-commons` | {v_data} | "
        f"`RepositoryComponentProvider` extends "
        f"`{short(parent.group(1)) if parent else 'NOTHING'}` |"
    )

    provider = javap(data, PROVIDER, "-c", "-p")
    built = filters(body(provider, r"RepositoryComponentProvider\(java\.lang\.Iterable"))
    spelled = "; ".join(built)
    print(
        f"| 2 | the filters it is built with, when no include filter is handed in | "
        f"`spring-data-commons` | {v_data} | {spelled} |"
    )

    single = body(
        javap(core, ANNOTATION_FILTER, "-c", "-p"),
        r"AnnotationTypeFilter\(java\.lang\.Class<[^,]*>\);",
    )
    defaults = [
        "true" if "iconst_1" in line else "false"
        for line in single
        if re.search(r"iconst_[01]", line)
    ]
    print(
        f"| 3 | what a one-argument `AnnotationTypeFilter` considers | `spring-core` | {v_core} | "
        f"delegates with `considerMetaAnnotations` = {defaults[0] if defaults else '?'}, "
        f"`considerInterfaces` = {defaults[1] if len(defaults) > 1 else '?'} |"
    )

    match = body(javap(data, INTERFACE_FILTER, "-c", "-p"), r"boolean match\(")
    print(
        f"| 4 | what `InterfaceTypeFilter` matches | `spring-data-commons` | {v_data} | "
        f"`match` runs `{' -> '.join(invoked(match))}`: an interface assignable to the type |"
    )

    candidate = body(provider, r"isCandidateComponent\(org\.springframework\.beans")
    print(
        f"| 5 | which matched interfaces it keeps | `spring-data-commons` | {v_data} | "
        f"`isCandidateComponent(AnnotatedBeanDefinition)` runs "
        f"`{' -> '.join(invoked(candidate))}` |"
    )
    own = [
        h
        for h in bodies(provider)
        if "isCandidateComponent(org.springframework.core.type.classreading.MetadataReader)" in h
    ]
    scanner = body(
        javap(context, SCANNER, "-c", "-p"),
        r"boolean isCandidateComponent\(org\.springframework\.core\.type\.classreading\.MetadataReader\)",
    )
    steps = [
        n
        for n in invoked(scanner)
        if n in ("match", "registerCandidateTypeForIncludeFilter", "isConditionMatch")
    ]
    print(
        f"| 6 | whether a matched interface's own conditions are evaluated | `spring-data-commons`, "
        f"`spring-context` | {v_data}, {v_context} | `RepositoryComponentProvider` overrides "
        f"`isCandidateComponent(MetadataReader)`: {'yes' if own else 'no'}; the inherited one "
        f"runs `{' -> '.join(steps)}` |"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
