"""Language confinement (ARCHITECTURE §10): only `ingress/extract/jvm` may
reference a language by name.

import-linter enforces the rules that are about imports. This one is about
text — a hardcoded `"java"` in a build-system detector is not an import — so
it needs a check of its own, and until now it had none. It is also the rule
the branch actually broke: the Maven detector shipped `languages={"java"}`
and a `src/main/java` source root, under a constraint both the plan and
ARCHITECTURE state. An untested rule is already being violated.
"""

import re
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "sextant"
JVM_ADAPTER = SOURCE_ROOT / "ingress" / "extract" / "jvm"

# The languages the JVM backend covers. A name here may appear only inside the
# adapter that owns it; anywhere else it is a language branch waiting to
# happen, and the next backend has to fork the code to get past it.
LANGUAGE_NAMES = ("java", "kotlin", "scala", "groovy", "clojure")

_LANGUAGE = re.compile(rf"\b({'|'.join(LANGUAGE_NAMES)})\b", re.IGNORECASE)


def _confined_sources() -> list[Path]:
    """Every source Sextant ships except the JVM adapter's own files."""
    return sorted(
        path
        for pattern in ("*.py", "*.sql")
        for path in SOURCE_ROOT.rglob(pattern)
        if JVM_ADAPTER not in path.parents
    )


# The recorded exceptions, keyed on the EXACT source line rather than on a file
# or a line number: a file-wide exemption would wave through every future
# language name in that file, and a line number drifts on the next edit. One
# entry has to be added deliberately, per line, which is the point.
#
# `ingress/detect/maven.py` reads the property key `java.version` because that
# is what MAVEN calls the setting, and Spring Boot's parent pom sets that one
# and nothing else (W3b). It is a wire key, not a language branch — the
# detector's behaviour does not vary by language, and the file says so itself.
# Dropping the key was measured and rejected: the commonest Boot module in the
# estate would then report no declared release, and multi-release selection
# would fall back to the class-file major, a worse answer than the pom states.
# `tests/architecture/test_source_rules.py` records the same exception against
# its own rule, for the same reason.
_RECORDED = {("ingress/detect/maven.py", '"java.version",')}


def _hits(path: Path) -> list[str]:
    relative = str(path.relative_to(SOURCE_ROOT))
    return [
        f"{path.relative_to(SOURCE_ROOT)}:{number}: {line.strip()}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _LANGUAGE.search(line) and (relative, line.strip()) not in _RECORDED
    ]


def test_every_recorded_exception_still_exists():
    """A recorded exception that no longer matches anything is a hole kept open
    for nothing, and the next language name on that exact line would ride
    through it unexamined. The list shrinks when the code does."""
    live = {
        (str(path.relative_to(SOURCE_ROOT)), line.strip())
        for path in _confined_sources()
        for line in path.read_text(encoding="utf-8").splitlines()
        if _LANGUAGE.search(line)
    }
    assert _RECORDED <= live, f"recorded but no longer present: {_RECORDED - live}"


def test_no_language_name_appears_outside_the_jvm_adapter():
    offences = [hit for path in _confined_sources() for hit in _hits(path)]
    assert offences == [], "a language name outside sextant.ingress.extract.jvm:\n" + "\n".join(
        offences
    )


def test_the_check_finds_a_language_name_where_one_is_allowed_to_be():
    """A confinement check that matches nothing anywhere passes for the wrong
    reason. The adapter that owns these languages names them, so the pattern
    must see them there."""
    named = [hit for path in sorted(JVM_ADAPTER.rglob("*.py")) for hit in _hits(path)]
    assert named, "the language pattern matches nothing even inside the JVM adapter"
