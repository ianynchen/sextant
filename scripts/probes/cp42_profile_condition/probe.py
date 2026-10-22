"""CP-42: what does `@Profile` declare, how does its condition decide, and what grammar does a
profile expression admit? Every cell is read off the jars with `javap`; the version is each
jar's own manifest. Prints the observation table `cp42_profile_condition.md` carries."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _spring_jar import javap, manifest_version, newest_jar

PROFILE = "org.springframework.context.annotation.Profile"
GENERIC = "org.springframework.context.annotation.Conditional"
CONDITION = "org.springframework.context.annotation.ProfileCondition"
PARSER = "org.springframework.core.env.ProfilesParser"


def main() -> int:
    context = newest_jar("org.springframework", "spring-context")
    core = newest_jar("org.springframework", "spring-core")
    if context is None or core is None:
        print("spring-context / spring-core NOT IN THE LOCAL REPOSITORY")
        return 1
    v_context, v_core = manifest_version(context), manifest_version(core)
    print(f"| what the run read | {v_context} |")
    print("|---|---|")
    print(f"| `spring-context` version, from its manifest | {v_context} |")
    print(f"| `spring-core` version, from its manifest | {v_core} |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")
    members = re.findall(r"public abstract (\S+) (\w+)\(\);", javap(context, PROFILE))
    print(
        f"| 1 | what `@Profile` declares | `spring-context` | {v_context} | `{', '.join(f'{t} {n}()' for t, n in members)}` |"
    )
    calls = sorted(
        set(
            re.findall(
                r"// (?:Interface)?Method (org/springframework[^\s]+)",
                javap(context, CONDITION, "-c", "-p"),
            )
        )
    )
    decides = [c for c in calls if "Environment" in c]
    print(
        f"| 2 | how `ProfileCondition.matches` decides | `spring-context` | {v_context} | calls `{'`, `'.join(decides)}` with the annotation's `value` array — ANY expression matching accepts |"
    )
    # Single-character literals only: the parser also carries the combined `()&|!` string it
    # tokenises on, which is not an operator but the set of them.
    operators = sorted(
        token
        for token in set(
            re.findall(r"// String ([()&|!]+)\s*$", javap(core, PARSER, "-c", "-p"), re.MULTILINE)
        )
        if len(token) == 1
    )
    print(
        # The or-bar is spelled out: a literal `|` inside a markdown table cell is a cell
        # boundary to the table checker, backticks or not.
        f"| 3 | operators the profile-expression parser handles | `spring-core` | {v_core} | `{' '.join('or-bar' if o == '|' else o for o in operators)}` — `!` negation, `&`, the or-bar (U+007C), parentheses |"
    )
    # The generic condition every `@ConditionalOn*` is built on: a CLASS, so code, not
    # configuration — named by this analysis and never evaluated.
    generic = [line.strip() for line in javap(context, GENERIC).splitlines() if "abstract" in line]
    print(
        f"| 4 | what `@Conditional` declares | `spring-context` | {v_context} | `{'; '.join(generic)}` — a `Condition` CLASS, code rather than configuration |"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
