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


def _hits(path: Path) -> list[str]:
    return [
        f"{path.relative_to(SOURCE_ROOT)}:{number}: {line.strip()}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _LANGUAGE.search(line)
    ]


def test_no_language_name_appears_outside_the_jvm_adapter():
    offences = [hit for path in _confined_sources() for hit in _hits(path)]
    assert offences == [], (
        "a language name outside sextant.ingress.extract.jvm:\n" + "\n".join(offences)
    )


def test_the_check_finds_a_language_name_where_one_is_allowed_to_be():
    """A confinement check that matches nothing anywhere passes for the wrong
    reason. The adapter that owns these languages names them, so the pattern
    must see them there."""
    named = [hit for path in sorted(JVM_ADAPTER.rglob("*.py")) for hit in _hits(path)]
    assert named, "the language pattern matches nothing even inside the JVM adapter"
