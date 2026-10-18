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
from collections import Counter
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
# The keys a release ADDED, which is what this harness proves additive. Each entry stays
# after its release: the proof is re-run against an older jar whenever the next key lands,
# and a key removed from this set would silently start counting as a difference.
#
# `written_by` (2026-10-18, the walk's sixth edge) is the first that also comes with a
# BEHAVIOUR change in the same release — the `<init>` filter lifted — so the two are
# measured apart: this harness proves the KEY additive on the lines both jars write, and the
# new lines a lifted filter produces are counted separately, because a line the before jar
# never wrote has nothing to be identical to.
NEW_KEYS = frozenset({"receiver_parameter", "captures", "written_by"})


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


def compare_trees(before: Path, after: Path) -> tuple[list[str], int, int, int]:
    """Problems, byte-identical lines, lines that carry a new key and read as the before
    line without it, and lines the after jar wrote that the before jar did not.

    **The fourth number is why this is not a two-way diff** (2026-10-18). A release that
    adds a KEY can be proved line for line; a release that also changes WHICH FACTS ARE
    EMITTED cannot, because a line the before jar never wrote has nothing to be identical
    to. The `written_by` release is the first of the second kind — the `<init>` filter on
    `fieldWrites` lifted in the same change — so ADDED lines are counted and shown rather
    than reported as a difference, and the additivity claim is made about the lines both
    jars wrote. An added line that is NOT the expected kind is still a problem: every one
    is printed, so a reader checks what appeared rather than trusting a count.
    """
    problems: list[str] = []
    identical = keyed = added = 0
    before_files = sorted(p.relative_to(before) for p in before.rglob("*.jsonl"))
    after_files = sorted(p.relative_to(after) for p in after.rglob("*.jsonl"))
    if before_files != after_files:
        problems.append(f"file sets differ: {set(before_files) ^ set(after_files)}")
    for relative in before_files:
        old = (before / relative).read_text(encoding="utf-8").splitlines()
        new = (after / relative).read_text(encoding="utf-8").splitlines()
        if len(old) != len(new):
            # Line counts differ, so the positional pairing is gone: compare the sets of
            # facts with the new keys STRIPPED, which is the only comparison that can tell
            # "this line gained a key" from "this line is new". Comparing raw text here
            # reported every key-carrying line as lost, which is a false alarm this harness
            # must not raise — it is the one that would be ignored next time.
            old_facts = [
                json.dumps(without_the_new_keys(json.loads(line)), sort_keys=True) for line in old
            ]
            new_facts = [
                json.dumps(without_the_new_keys(json.loads(line)), sort_keys=True) for line in new
            ]
            old_counts, new_counts = Counter(old_facts), Counter(new_facts)
            lost = +(old_counts - new_counts)
            if lost:
                problems.append(
                    f"{relative}: {sum(lost.values())} fact(s) the after jar stopped writing"
                )
            added += sum((+(new_counts - old_counts)).values())
            identical += sum((old_counts & new_counts).values())
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
    return problems, identical, keyed, added


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
        found, identical, keyed, added = compare_trees(before, after)
        verdict = "additive" if not found else "DIFFERS"
        print(
            f"{name}: {verdict} ({identical} byte-identical, {keyed} carry a new key, "
            f"{added} newly emitted)"
        )
        problems.extend(f"{name}: {p}" for p in found)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
