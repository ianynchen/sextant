"""Compile a fixture module once — per session, and across sessions when nothing changed.

MEASURED 2026-09-11, before this existed: 42 of the suite's 43 `mvn -o compile`
invocations named `fixtures/orders-service`, each re-running Maven to produce a `target/`
identical to the last one — a fixture's source does not change during a test run.

MEASURED 2026-09-12, with the per-process memo below but before the stamp: a `mvn` shim on
PATH counted 25 Maven invocations in one full suite run, 50.7s of wall time between them
and ~130s of the suite's 510s CPU. Nineteen of them verified a fixture root whose sources
had not changed since the last run: `orders-service` four times (the memo is per process,
and xdist runs four), three other fixtures twice, and the two copies of `orders-service`
that `test_facade.py` and `test_enrich_command.py` make once each — `copytree` keeps
`target/` and Maven finds nothing to do, and still takes 5.5s to say so. Each of those is
Maven's JVM plus its own up-to-date check: 3.4–3.6s wall, 10–11s CPU, on a tree it will
not touch.

**The stamp.** After a compile, `target/sextant-fixture.stamp` records a fingerprint of
everything the compile read: every file under the root except its outputs and the suite's
own scratch (`target/`, `.sextant/`, `.sextant-enrichment.json`, `.tradewind/`, `.git/`),
the parent directory's `pom.xml` when the root's POM declares a `<parent>` (billing-lib's
`<relativePath>` reaches the reactor parent), and the stub library jar's path, size and
mtime (`orders-service` depends on it, and the session fixture in `conftest.py` rebuilds
it before anything compiles). A root whose `target/classes` exists and whose stamp equals
today's fingerprint is compiled already, in this process or any earlier one, and Maven is
not asked. The fingerprint is content-based, so a `copytree` of a stamped root is stamped
too, and a `touch` changes nothing. MEASURED: the fingerprint of `orders-service`, 112
files, costs 4ms; every other fixture is under 1ms.

CI primes the stamps: `python tests/fixture_build.py` compiles `PRIMED_FIXTURES` online
and writes their stamps before the suite starts, so the suite's offline compiles find
nothing to do. Without that the first `compile_fixture` on every worker would still run
Maven once per root.

**Its own module rather than `conftest.py`, and that is not a style choice.** Several
directories under `tests/` have their own `conftest.py`, so a bare `from conftest import …`
resolves to the NEAREST one and fails everywhere else. `fixture_stub` next door is imported
the same way for the same reason.
"""

import hashlib
import os
import subprocess
from pathlib import Path

import fixture_stub

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# The Maven fixtures the suite compiles offline. CI compiles these online first (the
# workflow's priming step runs this file as a script) so the suite's own compiles find a
# stamp; `orders-reactor/billing-lib` is not here because it resolves its parent by
# `<relativePath>` and needs nothing fetched beyond what the others already did.
PRIMED_FIXTURES = (
    "orders-service",
    "orders-soap-final",
    "orders-spring7",
    "spring-integration-probe",
    "orders-micronaut",
    "orders-quarkus",
    "orders-receivers",
    "orders-streams",
    "orders-javalin",
    "orders-pekko",
)

STAMP = Path("target") / "sextant-fixture.stamp"

# What a compile writes or the suite scribbles beside a fixture — never a compile input.
_NOT_AN_INPUT = frozenset({"target", ".sextant", ".sextant-enrichment.json", ".tradewind", ".git"})

_COMPILED: set[Path] = set()


def fingerprint(root: Path) -> str:
    """One digest over everything a compile of `root` reads.

    Content, not mtimes, for the files under the root: `copytree` copies of a stamped
    fixture (two module-scoped fixtures make them) must fingerprint the same as the
    original, and a `touch` must not force a recompile. The stub jar is the one input by
    size and mtime: it is a build output of another fixture, rewritten whole when it is
    rebuilt, and hashing a jar on every check is a cost with no discrimination to show for
    it.
    """
    digest = hashlib.sha256()
    for path in _inputs(root):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    if _declares_a_parent(root / "pom.xml"):
        parent = root.parent / "pom.xml"
        if parent.is_file():
            digest.update(b"parent:")
            digest.update(parent.read_bytes())
            digest.update(b"\0")
    jar = fixture_stub.local_repository_jar()
    stat = jar.stat() if jar.is_file() else None
    size, mtime = (stat.st_size, stat.st_mtime) if stat else ("", "")
    digest.update(f"stub:{jar}:{size}:{mtime}".encode())
    return digest.hexdigest()


def _inputs(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory, subdirectories, names in os.walk(root):
        subdirectories[:] = sorted(d for d in subdirectories if d not in _NOT_AN_INPUT)
        files.extend(Path(directory) / n for n in names if n not in _NOT_AN_INPUT)
    return sorted(files)


def _declares_a_parent(pom: Path) -> bool:
    return pom.is_file() and "<parent>" in pom.read_text(encoding="utf-8")


def is_current(root: Path) -> bool:
    """Compiled by some earlier call, in this process or another, from these same inputs."""
    stamp = root / STAMP
    if not (root / "target" / "classes").is_dir() or not stamp.is_file():
        return False
    return stamp.read_text(encoding="utf-8") == fingerprint(root)


def compile_and_stamp(root: Path, *, offline: bool) -> Path:
    """Run Maven on `root` and stamp the result.

    `offline` is the caller's promise about the network, exactly as in `fixture_stub`: the
    suite passes True (no test reaches the network), CI's priming step passes False.
    """
    inputs = fingerprint(root)
    mode = ["-o"] if offline else ["-B"]
    subprocess.run(["mvn", "-q", *mode, "compile"], cwd=root, check=True)
    (root / STAMP).parent.mkdir(exist_ok=True)
    (root / STAMP).write_text(inputs, encoding="utf-8")
    return root


def compile_fixture(root: Path) -> Path:
    """Compile one fixture root, at most once per session and only when its inputs changed
    since the last compile, and hand back its path.

    The memo is what stops a session asking twice; the stamp is what stops a session asking
    at all. Two xdist workers racing on the same unstamped root both compile, as before —
    Maven writes the same `target/` either way.
    """
    if root not in _COMPILED:
        if not is_current(root):
            compile_and_stamp(root, offline=True)
        _COMPILED.add(root)
    return root


if __name__ == "__main__":
    for name in PRIMED_FIXTURES:
        compile_and_stamp(FIXTURES / name, offline=False)
