"""The guard harness's own tests — including one proving it FAILS a test that
does not discriminate.

`scripts/guard_check.py` exists because a near-miss can pass for a reason
unrelated to the guard it claims to pin, and nothing noticed. A harness with
that same defect would be worse than none at all: it would report the whole
declining suite as sound and be believed. So the load-bearing test here is
`test_the_harness_reports_a_known_non_discriminating_test_as_surviving`, run
against one of `A-M2`'s three servlet `bypassed_by` near-misses — a case
independently known to survive its guard, established before this file existed
(delete the branch, or write `bypassed_by: []` in both shipped servlet
catalogs, and all thirty-nine tests in `test_supertype_dispatch.py` still pass).

The rest is plumbing, driven at the unit level: the copy the mutation lands in,
the anchor that must still match, the report's own arithmetic. The harness is
deliberately opt-in and never part of `scripts/check.sh`'s default run (its own
module docstring); these tests are, because a broken harness is silent.

`scripts/` carries no package `__init__.py` and sits outside `pythonpath`
(`pyproject.toml` only adds `src`), so the module is loaded straight from its
file path — `test_field_check.py`'s precedent, with one addition: it is
registered in `sys.modules` before execution, because its registry is built
from dataclasses and `dataclasses` resolves a class's annotations through the
module it believes it belongs to.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "guard_check.py"
_spec = importlib.util.spec_from_file_location("guard_check", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
guard_check = importlib.util.module_from_spec(_spec)
sys.modules["guard_check"] = guard_check
_spec.loader.exec_module(guard_check)


_BYPASS = "supertype_dispatch.bypassed-by"
_NON_DISCRIMINATING = (
    "tests/application/test_supertype_dispatch.py"
    "::test_a_class_overriding_service_and_declaring_no_verb_derives_nothing"
)
_DISCRIMINATING = (
    "tests/application/test_supertype_dispatch.py"
    "::test_an_address_annotation_writing_BOTH_SPELLINGS_derives_nothing"
)


def test_the_harness_reports_a_known_non_discriminating_test_as_surviving():
    """The one that matters. `A-M2`'s servlet near-miss declares no `doXxx` at
    all, which is the shape the `not handlers` branch declines on its own — so
    disabling the bypass branch changes no outcome and the test stays green.

    Its two siblings survive the same mutation and are asserted with it, since
    the finding is about all three and a harness seeing one of them would be a
    harness with a filter nobody wrote.

    This runs the real thing end to end — a copied tree, a real mutation, a real
    pytest subprocess — because every cheaper version of it would be testing the
    harness's bookkeeping rather than its measurement, and the measurement is
    the whole mechanism.
    """
    [outcome], complaints = guard_check.check([_BYPASS])

    assert complaints == []
    assert outcome.uncontrolled == [], "these fail before any mutation — nothing was measured"
    assert outcome.killed == []
    assert _NON_DISCRIMINATING in outcome.survived
    assert len(outcome.survived) == 3


def test_a_discriminating_test_is_killed_by_the_guard_it_names():
    """The paired positive (§10), and the half that cannot be skipped: a harness
    that reported EVERY test as surviving would pass the test above and be
    exactly as useless as no harness at all. The both-spellings near-miss is the
    pin — its guard is one line in one engine, and disabling it publishes the
    address the alias set exists to refuse."""
    [outcome], _complaints = guard_check.check(["supertype_dispatch.address-args-are-an-alias-set"])

    assert outcome.uncontrolled == []
    assert outcome.survived == []
    assert outcome.killed == [_DISCRIMINATING]


def test_a_guard_whose_anchor_no_longer_matches_stops_the_run(tmp_path: Path):
    """A stale anchor must RAISE, never apply nothing. Applying nothing would
    report every test naming that guard as measuring nothing — a suite-wide
    false alarm produced by one refactor of the guarded file."""
    tree = guard_check.copy_tree(tmp_path / "tree")
    guard = guard_check.Guard(
        what="an anchor nobody wrote",
        why="the registry has rotted",
        edits=(
            guard_check.Edit(
                path="sextant/application/resolve/engines/supertype_dispatch.py",
                find="a string that is not in that file",
                replace="",
            ),
        ),
    )

    with pytest.raises(LookupError) as raised:
        guard_check.apply_edits(tree, guard)

    assert "registry" in str(raised.value)
    assert "found 0" in str(raised.value)


def test_the_mutation_lands_in_the_copy_and_never_in_the_repository(tmp_path: Path):
    """The property that makes a killed run harmless (NFR-1): nothing mutated
    ever exists outside the temporary tree, so there is no restore step to fail
    and no state a SIGKILL could leave behind."""
    guard = guard_check.GUARDS[_BYPASS]
    edit = guard.edits[0]
    shipped = guard_check.REPO / "src" / edit.path
    before = shipped.read_text(encoding="utf-8")
    tree = guard_check.copy_tree(tmp_path / "tree")

    guard_check.apply_edits(tree, guard)

    assert edit.replace in (tree / "src" / edit.path).read_text(encoding="utf-8")
    assert shipped.read_text(encoding="utf-8") == before
    assert edit.find in before


def test_the_copied_tree_carries_the_stub_the_session_fixture_reads(tmp_path: Path):
    """`tests/conftest.py`'s session-scoped autouse fixture stats the stub
    library's sources before every test in the suite, so a copy without them
    errors at SETUP — which the control run would report as "unmeasurable" for
    all twenty-eight tests at once, and did, before this was copied."""
    tree = guard_check.copy_tree(tmp_path / "tree")

    assert (tree / "fixtures" / "orders-soap-client" / "pom.xml").is_file()
    assert (tree / "fixtures" / "pom.xml").is_file()
    assert (tree / "pyproject.toml").is_file()


def test_a_survivor_outside_the_allowlist_fails_the_run(capsys: pytest.CaptureFixture[str]):
    """The gate itself, driven off a constructed outcome rather than a run: a
    newly-added non-discriminating test must fail immediately, and be named
    together with the guard it fails to pin (both, because the pair is what a
    reader needs and either alone is unactionable)."""
    outcome = guard_check.Outcome(guard_id=_BYPASS, survived=["tests/x.py::test_invented"])

    assert guard_check.report([outcome], []) == 1
    printed = capsys.readouterr().out
    assert "NOT DISCRIMINATING" in printed
    assert "tests/x.py::test_invented" in printed
    assert _BYPASS in printed


def test_an_allowlisted_entry_that_has_started_discriminating_fails_the_run(
    capsys: pytest.CaptureFixture[str],
):
    """The other direction, and what keeps the allowlist from rotting into a
    record of nothing: an entry whose test now bites must be removed in the same
    commit that made it bite — the near-miss coverage file's
    `test_the_backlog_only_ever_shrinks`, applied to a measured list."""
    outcome = guard_check.Outcome(guard_id=_BYPASS, killed=[_NON_DISCRIMINATING])

    assert guard_check.report([outcome], []) == 1
    assert "STALE ALLOWLIST ENTRY" in capsys.readouterr().out


def test_a_partial_run_does_not_report_untouched_allowlist_entries_as_fixed(
    capsys: pytest.CaptureFixture[str],
):
    """`guard_check.py <one guard>` measures one guard, and the entries for
    every other one were not measured at all. Reporting them as fixed would
    make the shortest possible run look like the most productive."""
    outcome = guard_check.Outcome(
        guard_id="supertype_dispatch.address-args-are-an-alias-set", killed=[_DISCRIMINATING]
    )

    assert guard_check.report([outcome], []) == 0
    assert "STALE ALLOWLIST ENTRY" not in capsys.readouterr().out


def test_a_test_failing_before_any_mutation_is_reported_unmeasurable_not_killed(
    capsys: pytest.CaptureFixture[str],
):
    """The positive control's whole point. A test broken for an unrelated reason
    fails under the mutation too, and counting that as "killed" would score the
    most broken test in the suite as the strongest — this file's own failure
    mode, and the one it is least able to notice about itself."""
    outcome = guard_check.Outcome(guard_id=_BYPASS, uncontrolled=["tests/x.py::test_broken"])

    assert guard_check.report([outcome], []) == 1
    printed = capsys.readouterr().out
    assert "UNMEASURABLE" in printed
    assert "NOT DISCRIMINATING" not in printed


def test_a_junit_case_maps_back_to_its_node_id():
    """Outcomes are read from pytest's own report because one run answers for
    several tests and the exit code answers for none of them individually. A
    parametrized case must fold back onto its function, or every parametrized
    near-miss would be silently unmatched and default to "passed"."""
    from xml.etree import ElementTree

    case = ElementTree.Element(
        "testcase",
        {"classname": "tests.application.test_endpoints", "name": "test_a_thing[GET-200]"},
    )

    assert guard_check._node_id_of(case) == ("tests/application/test_endpoints.py::test_a_thing")
