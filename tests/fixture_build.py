"""Compile a fixture module once per test session.

MEASURED 2026-09-11, before this existed: 42 of the suite's 43 `mvn -o compile`
invocations named `fixtures/orders-service`, each re-running Maven to produce a `target/`
identical to the last one — a fixture's source does not change during a test run.

**Its own module rather than `conftest.py`, and that is not a style choice.** Several
directories under `tests/` have their own `conftest.py`, so a bare `from conftest import …`
resolves to the NEAREST one and fails everywhere else. `fixture_stub` next door is imported
the same way for the same reason.
"""

import subprocess
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

_COMPILED: set[Path] = set()


def compile_fixture(root: Path) -> Path:
    """Compile one fixture root, at most once per session, and hand back its path.

    Idempotent by memo rather than by asking Maven: `mvn -o compile` on an up-to-date tree
    still pays JVM start-up, and not paying that 42 times is the whole point.
    """
    if root not in _COMPILED:
        subprocess.run(["mvn", "-q", "-o", "compile"], cwd=root, check=True)
        _COMPILED.add(root)
    return root
