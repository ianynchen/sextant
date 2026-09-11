"""Every DECLINING test names the guard it pins (GUIDELINES §10, §8.3).

`test_catalog_near_miss_coverage.py` is the other half of this rule and answers
a different question: which shipped catalogs have a near-miss at all. It says
plainly what it cannot do — "the marker is a DECLARATION by the test's author,
not a proof ... this file reads it statically and does not re-verify that the
marked body asserts emptiness". This file closes the half of that gap a static
read can close, and `scripts/guard_check.py` closes the other half by
measurement.

## The defect

A near-miss can pass because its synthetic input is broken in some UNRELATED
way, at which point the guard it claims to pin is deletable and the test stays
green — coverage that counts and measures nothing, which is worse than no test,
because the coverage file counts it. It has shipped twice: sweep 1 found three
by hand, and the fix pass correcting those wrote three more (`A-M2`'s servlet
`bypassed_by` near-misses). §13.8 makes the second occurrence of a cause an
existing principle already forbids a MECHANISM rather than another correction.

The mechanism is `scripts/guard_check.py`: it disables one named guard and
reruns only the tests naming it, and a test that still passes is a failure. It
is its own command, because it is slower than a test and its failures mean
something different. What it needs from every declining test is the NAME of the
guard, and that is what this file enforces:

    @pytest.mark.declines("jakarta-servlet")     # which catalog is covered
    @pytest.mark.pins("supertype_dispatch.bypassed-by")   # which guard is measured

Two markers rather than one argument, because they name different subjects: one
test carries nine `declines` markers and still measures exactly one guard.

## What is enforced here, and what is not

Enforced, statically and offline: that every `declines`-marked test names
exactly one guard; that the id is one `scripts/guard_check.py` defines, so a
typo cannot declare coverage of nothing (§5.3's failure in miniature); that
every registered guard is named by some test, so the registry cannot accumulate
entries measuring nothing either; and that each guard's anchor text still
occurs in the shipped file exactly as many times as the registry claims — a
stale anchor must fail HERE, as a registry that has rotted, rather than in the
harness as a suite that has suddenly stopped discriminating.

Not enforced here: whether any of it discriminates. That is a measurement, it
costs a pytest subprocess per guard, and it lives in the harness. The audit of
which existing tests do NOT discriminate is `_DOES_NOT_DISCRIMINATE_YET` in
`scripts/guard_check.py` — the shrinking allowlist §8.3 requires of a rule made
enforceable, checked there because only a run can check it.

There is no backlog of declining tests permitted to name no guard. Every one of
the twenty-eight that existed when this landed names one, so a list would have
been empty on the day it shipped — and an empty allowlist is a name where no
mechanism is.

OFFLINE and deterministic (NFR-1): it parses test files and reads shipped
source, and runs nothing.
"""

import ast
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).parents[2]
TESTS = REPO / "tests"

# `scripts/` carries no package `__init__.py` and sits outside `pythonpath`
# (`pyproject.toml` only adds `src`), so the module is loaded straight from its
# file path — `tests/scripts/test_field_check.py`'s own precedent. It is
# registered in `sys.modules` first because its registry is built from
# dataclasses, and `dataclasses` resolves a class's annotations through the
# module it believes it belongs to.
_MODULE_PATH = REPO / "scripts" / "guard_check.py"
_spec = importlib.util.spec_from_file_location("guard_check", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
guard_check = importlib.util.module_from_spec(_spec)
sys.modules["guard_check"] = guard_check
_spec.loader.exec_module(guard_check)


def marked_tests() -> dict[str, list[str]]:
    """`file:line:name` -> the guard ids it names, for every `declines` test.

    Read statically off the AST for the same reason the near-miss coverage file
    reads its own marker that way: a decorator is a fact about the source, and
    this is an architecture rule rather than a run of the suite it inspects.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not _ids(node, "declines"):
                continue
            where = f"{path.relative_to(REPO)}:{node.lineno}:{node.name}"
            found[where] = _ids(node, "pins")
    return found


def pinning_tests() -> dict[str, list[str]]:
    """`file:line:name` -> the guard ids it names, for every test carrying a
    `pins` marker — with or without a `declines` marker beside it.

    `marked_tests()`' superset, and the two answer different questions.
    `declines` names a shipped CATALOG, so a near-miss written against an
    INVENTED catalog — which is how every engine-vocabulary mechanism in
    `test_endpoints.py` is tested, deliberately, so that a test pins a
    mechanism rather than a framework — carries no `declines` marker and is
    invisible to `marked_tests()`. It still names a guard, and
    `scripts/guard_check.py::pinned_tests` still runs it.

    Reading the narrower set here is what let a registered guard read as
    "named by no test" while the harness was measuring it: the two halves of
    one mechanism disagreed about what naming means. They agree now.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            pins = _ids(node, "pins")
            if not pins:
                continue
            found[f"{path.relative_to(REPO)}:{node.lineno}:{node.name}"] = pins
    return found


def _ids(node: ast.FunctionDef | ast.AsyncFunctionDef, marker: str) -> list[str]:
    """The string arguments of every `@pytest.mark.<marker>(...)` decorator."""
    ids = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        target = decorator.func
        if not (isinstance(target, ast.Attribute) and target.attr == marker):
            continue
        for argument in decorator.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                ids.append(argument.value)
    return ids


def test_every_declining_test_names_exactly_one_guard():
    """The rule itself. EXACTLY one, not at least one: the harness answers "did
    this test notice" per guard, and a test naming two would be reported as
    discriminating on the strength of whichever one it happened to bite."""
    wrong = {where: ids for where, ids in marked_tests().items() if len(ids) != 1}
    assert wrong == {}, (
        "these `declines` tests do not name exactly one guard "
        '(`@pytest.mark.pins("<guard id>")`, from scripts/guard_check.py):\n'
        + "\n".join(
            f"  - {where}: {ids or 'no pins marker'}" for where, ids in sorted(wrong.items())
        )
        + "\n\nName the guard whose loss the near-miss would notice — the check "
        "whose absence makes its input derive a row — and then run "
        "`scripts/check.sh --guards` to find out whether it actually does."
    )


def test_every_pins_marker_names_a_guard_that_exists():
    """A marker is only as good as its argument. An id the registry does not
    define declares a measurement nobody can run — a name existing where a
    mechanism does not, which is §5.3 exactly."""
    phantom = {
        where: ids for where, ids in pinning_tests().items() if set(ids) - set(guard_check.GUARDS)
    }
    assert phantom == {}, (
        "`pins` markers naming guards scripts/guard_check.py does not define:\n"
        + "\n".join(
            f"  - {where}: {sorted(set(ids) - set(guard_check.GUARDS))}"
            for where, ids in sorted(phantom.items())
        )
    )


def test_every_registered_guard_is_named_by_some_test():
    """The registry cannot accumulate entries either. A guard nothing names is
    never disabled and never measured, so its `what` and `why` are prose that
    nothing keeps true — the same failure the markers have, from the other end.

    A guard worth registering and pinned by no test is a REAL finding, and it
    belongs where the other coverage gaps are recorded (the near-miss file's
    backlog, `docs/principles-sweep-2026-09-05.md`'s S1-MAJ-1), not as an entry
    here that looks measured.
    """
    named = {guard_id for ids in pinning_tests().values() for guard_id in ids}
    unused = sorted(set(guard_check.GUARDS) - named)
    assert unused == [], (
        "these guards are registered in scripts/guard_check.py and named by no test:\n"
        + "\n".join(f"  - {guard_id}" for guard_id in unused)
    )


def test_every_guard_anchor_still_occurs_where_the_registry_says():
    """A guard is an exact string in a shipped file, and the shipped file is
    edited by people who have never read the registry. When an anchor stops
    matching, the harness would apply nothing and report every test naming that
    guard as measuring nothing — a suite-wide false alarm from one refactor.

    So the anchor is checked HERE, in the fast suite, where the failure reads as
    what it is: a stale registry entry to re-anchor, not a test to rewrite.
    """
    stale = []
    for guard_id, guard in sorted(guard_check.GUARDS.items()):
        for edit in guard.edits:
            path = REPO / "src" / edit.path
            actual = path.read_text(encoding="utf-8").count(edit.find)
            if actual != edit.occurrences:
                stale.append(f"{guard_id} -> {edit.path}: want {edit.occurrences}, found {actual}")
    assert stale == [], "guard anchors that no longer match the shipped source:\n" + "\n".join(
        f"  - {entry}" for entry in stale
    )


def test_the_non_discriminating_allowlist_names_tests_that_still_exist():
    """`_DOES_NOT_DISCRIMINATE_YET` is the §8.3 audit list, and an entry naming
    a test that has been renamed or deleted records nothing while still looking
    like a backlog of one. The harness's own run refuses an entry that has
    started to discriminate; this refuses one that has stopped existing.

    Only the node id is checkable statically — whether the pairing is still the
    guard that test names is checked here too, since both halves are read off
    the same markers.
    """
    pinned = {
        f"{Path(where.split(':')[0]).as_posix()}::{where.split(':')[2]}": ids
        for where, ids in marked_tests().items()
    }
    unknown = sorted(
        f"{node_id} / {guard_id}"
        for node_id, guard_id in guard_check._DOES_NOT_DISCRIMINATE_YET
        if guard_id not in pinned.get(node_id, [])
    )
    assert unknown == [], (
        "_DOES_NOT_DISCRIMINATE_YET entries naming a test that no longer exists, "
        "or that no longer names that guard:\n" + "\n".join(f"  - {entry}" for entry in unknown)
    )


def test_the_marker_scan_finds_the_pins_markers_that_exist():
    """A scan that discovers nothing passes for the wrong reason — every rule
    above holds vacuously over an empty dict, and this file would assert only
    that the registry is self-consistent. `A-M2`'s servlet near-miss is the pin,
    because it is the finding that produced the mechanism: if the scan cannot
    see that one, it can see none of them."""
    marked = marked_tests()
    assert marked, "the `declines` marker scan found no marked test anywhere"
    named = {guard_id for ids in marked.values() for guard_id in ids}
    assert "supertype_dispatch.bypassed-by" in named, (
        "the scan no longer sees a test naming `supertype_dispatch.bypassed-by` — "
        "the marker mechanism is broken, not the coverage"
    )
