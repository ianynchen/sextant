"""Spec §11 step 1: the two new keys are the ONLY difference.

Scans every compiled fixture directory with two extractor jars — the one built before
the change and the one built after — into two trees and compares them line by line.
A line the after jar wrote without either key must be byte-identical to the before
jar's. A line that carries one — `receiver_parameter` on a call site, `captures` on a
`lambda` entry of the argument grammar, wherever that grammar recurs: a call site's
arguments, an array's elements, a method return's value — must read as the before
line once the key is removed. Nothing else may differ, and no line may go missing
or appear.

    .venv/bin/python scripts/probes/fact_additivity/run.py /tmp/a1-proof/before.jar

§11 step 2 — analysing each corpus copy with both builds and diffing every workspace
table — is run by hand with `.superpowers/perf/table_diff.py`, because the scanner
reads its jar from one place and swapping it is not something a shipped script should
do; the task report records the commands and the output.

Read-only on the repository; writes only under /tmp/a1-proof. Exit 1 on any difference.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION

REPO = Path(__file__).resolve().parents[3]
AFTER_JAR = REPO / "src" / "sextant" / "extractor-jvm" / "sextant-extractor.jar"
# Every compiled class directory under `fixtures/`, whichever build tool laid it out:
# the two layouts the fixtures use, and a multi-module root's modules beside its own.
FIXTURES = sorted(
    p
    for pattern in ("**/target/classes", "**/build/classes/*/main")
    for p in (REPO / "fixtures").glob(pattern)
    if p.is_dir()
)
OUT = Path("/tmp/a1-proof")
NEW_KEYS = frozenset({"receiver_parameter", "captures"})


def scan(jar: Path, classes: Path, out: Path) -> None:
    subprocess.run(
        [
            "java",
            "-jar",
            str(jar),
            "--module-id",
            "proof",
            "--coordinates",
            "proof/" + classes.relative_to(REPO / "fixtures").parts[0],
            "--version",
            "0",
            "--classes",
            str(classes),
            "--out",
            str(out),
            "--fact-schema-version",
            str(FACT_SCHEMA_VERSION),
            "--sextant-version",
            SEXTANT_VERSION,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def without_the_new_keys(value: object) -> object:
    """The fact with both keys removed at every depth: `receiver_parameter` sits on
    the call site itself, `captures` on a `lambda` entry of the argument grammar, and
    the grammar nests (an array's `elements`) and recurs on other kinds (a method
    return's `value`), so the walk is over the whole object rather than one path."""
    if isinstance(value, dict):
        return {k: without_the_new_keys(v) for k, v in value.items() if k not in NEW_KEYS}
    if isinstance(value, list):
        return [without_the_new_keys(v) for v in value]
    return value


def carries_a_new_key(value: object) -> bool:
    if isinstance(value, dict):
        return bool(NEW_KEYS & value.keys()) or any(carries_a_new_key(v) for v in value.values())
    if isinstance(value, list):
        return any(carries_a_new_key(v) for v in value)
    return False


def compare_trees(before: Path, after: Path) -> tuple[list[str], int, int]:
    """Problems, the count of byte-identical lines, and the count of lines that
    carry a new key and read as the before line without it."""
    problems: list[str] = []
    identical = keyed = 0
    before_files = sorted(p.relative_to(before) for p in before.rglob("*.jsonl"))
    after_files = sorted(p.relative_to(after) for p in after.rglob("*.jsonl"))
    if before_files != after_files:
        problems.append(f"file sets differ: {set(before_files) ^ set(after_files)}")
    for relative in before_files:
        old = (before / relative).read_text(encoding="utf-8").splitlines()
        new = (after / relative).read_text(encoding="utf-8").splitlines()
        if len(old) != len(new):
            problems.append(f"{relative}: {len(old)} lines before, {len(new)} after")
            continue
        for number, (old_line, new_line) in enumerate(zip(old, new, strict=True), 1):
            if old_line == new_line:
                identical += 1
                continue
            new_fact = json.loads(new_line)
            if not carries_a_new_key(new_fact):
                problems.append(f"{relative}:{number}: differs and carries neither new key")
            elif without_the_new_keys(new_fact) != json.loads(old_line):
                problems.append(f"{relative}:{number}: differs beyond the two keys")
            else:
                keyed += 1
    return problems, identical, keyed


def label(classes: Path) -> str:
    return "_".join(classes.relative_to(REPO / "fixtures").parts)


def main(before_jar: Path) -> int:
    problems: list[str] = []
    for classes in FIXTURES:
        name = label(classes)
        before = OUT / "before" / name
        after = OUT / "after" / name
        for tree in (before, after):
            shutil.rmtree(tree, ignore_errors=True)
            tree.mkdir(parents=True)
        scan(before_jar, classes, before)
        scan(AFTER_JAR, classes, after)
        found, identical, keyed = compare_trees(before, after)
        verdict = "identical after stripping" if not found else "DIFFERS"
        print(f"{name}: {verdict} ({identical} lines byte-identical, {keyed} carry a new key)")
        problems.extend(f"{name}: {p}" for p in found)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
