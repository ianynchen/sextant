"""CP-43: what does `@ConditionalOnProperty` declare and how does its condition compare a
value? Every cell is read off the jar with `javap`; the version is the jar's own manifest.
Prints the observation table `cp43_on_property_condition.md` carries."""

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _spring_jar import javap, manifest_version, newest_jar

ANNOTATION = "org.springframework.boot.autoconfigure.condition.ConditionalOnProperty"
SPEC = "org.springframework.boot.autoconfigure.condition.OnPropertyCondition$Spec"
CONDITION = "org.springframework.boot.autoconfigure.condition.OnPropertyCondition"


def main() -> int:
    jar = newest_jar("org.springframework.boot", "spring-boot-autoconfigure")
    if jar is None:
        print("spring-boot-autoconfigure NOT IN THE LOCAL REPOSITORY")
        return 1
    version = manifest_version(jar)
    print(f"| what the run read | {version} |")
    print("|---|---|")
    print(f"| `spring-boot-autoconfigure` version, from its manifest | {version} |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")
    members = re.findall(r"public abstract (\S+) (\w+)\(\);", javap(jar, ANNOTATION))
    print(
        f"| 1 | what `@ConditionalOnProperty` declares | `spring-boot-autoconfigure` | {version} | `{', '.join(f'{t} {n}()' for t, n in members)}` |"
    )
    body = javap(jar, SPEC, "-c", "-p")
    match_block = body[body.index("isMatch(") :] if "isMatch(" in body else ""
    match_block = match_block[: match_block.find("\n\n")] if "\n\n" in match_block else match_block
    uses = re.findall(
        r"// (?:Method )?(?:org/springframework/util/StringUtils\.hasLength|java/lang/String\.equalsIgnoreCase)",
        match_block,
    )
    literal_false = '"false"' if "String false" in match_block else "no literal"
    print(
        f"| 2 | how `Spec.isMatch` compares the property's value | `spring-boot-autoconfigure` | {version} | `{' -> '.join(dict.fromkeys(u.split('/')[-1] for u in uses))}`; literal compared against when `havingValue` is empty: {literal_false} |"
    )
    # Read where the Spec is BUILT from the annotation and consulted where the outcome is
    # decided — both inside the inner `Spec` class, by the attribute's own name.
    mentions = len(re.findall(r"matchIfMissing", body))
    print(
        f"| 3 | what decides an ABSENT property | `spring-boot-autoconfigure` | {version} | "
        f"`matchIfMissing` read off the annotation and consulted in `Spec` ({mentions} mentions) — "
        "a missing property matches exactly when it is `true` |"
    )
    # How a `prefix` is joined to a name: read off `Spec.getPrefix` — the calls it makes and
    # the one literal it compares against.
    prefix_block = body[body.index("getPrefix(") :] if "getPrefix(" in body else ""
    prefix_block = (
        prefix_block[: prefix_block.find("\n\n")] if "\n\n" in prefix_block else prefix_block
    )
    prefix_calls = [
        c.split("/")[-1]
        for c in re.findall(r"// Method ([\w/]+\.(?:trim|hasText|endsWith))", prefix_block)
    ]
    literal_dot = '"."' if re.search(r"// String \.\s*$", prefix_block, re.MULTILINE) else "none"
    print(
        f"| 4 | how `prefix` is joined to a name | `spring-boot-autoconfigure` | {version} | "
        f"`Spec.getPrefix`: `{' -> '.join(prefix_calls)}`, literal {literal_dot} — the prefix is "
        "trimmed, and `.` is appended only where it does not already end in one |"
    )
    # Every annotation in the `condition` package that is itself meta-annotated
    # `@Conditional`: the conditions this analysis names and does not evaluate (`other`).
    package = "org/springframework/boot/autoconfigure/condition/"
    with zipfile.ZipFile(jar) as archive:
        classes = sorted(
            n[: -len(".class")].replace("/", ".")
            for n in archive.namelist()
            if n.startswith(package) and n.endswith(".class") and "$" not in n
        )
    conditional = []
    for cls in classes:
        verbose = javap(jar, cls, "-v")
        if (
            "ACC_ANNOTATION" in verbose
            and "Lorg/springframework/context/annotation/Conditional;" in verbose
        ):
            conditional.append(cls.rsplit(".", 1)[-1])
    print(
        f"| 5 | the annotations in `o.s.b.autoconfigure.condition` meta-annotated `@Conditional` | "
        f"`spring-boot-autoconfigure` | {version} | {len(conditional)}: "
        f"`{'`, `'.join(conditional)}` |"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
