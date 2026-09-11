"""The guard harness's own tests — including one proving it FAILS a test that
does not discriminate.

`scripts/guard_check.py` exists because a near-miss can pass for a reason
unrelated to the guard it claims to pin, and nothing noticed. A harness with
that same defect would be worse than none at all: it would report the whole
declining suite as sound and be believed. So the load-bearing test here is
`test_the_harness_reports_a_test_that_does_not_notice_its_guard_as_surviving`,
run against a SYNTHETIC guard whose edit rewrites a comment.

It used to be run against one of `A-M2`'s three servlet `bypassed_by`
near-misses — a case independently known to survive its guard. Those were
fixed, which is what the harness is for, and a self-test anchored to a live
defect goes out with the defect. The synthetic case is also the sharper one:
"the edit changes no behaviour" is a property this file can guarantee, where
"this test happens not to notice" is a fact about someone else's test that a
later commit may quietly change.

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
_SUPERTYPE_DISPATCH = "sextant/application/resolve/engines/supertype_dispatch.py"
_DISCRIMINATING = (
    "tests/application/test_supertype_dispatch.py"
    "::test_an_address_annotation_writing_BOTH_SPELLINGS_derives_nothing"
)
# A guard the named test provably cannot notice: its edit rewrites a COMMENT.
# Synthetic on purpose — see the test below for why that is the stronger form.
_UNREACHABLE = "test-only.a-guard-nothing-can-notice"
_UNREACHABLE_GUARD = guard_check.Guard(
    what="a comment, which decides nothing",
    why="nothing — this exists only so the harness has a case whose outcome is known",
    edits=(
        guard_check.Edit(
            path=_SUPERTYPE_DISPATCH,
            find="# A member as this style selects one: its name and its parameter types, in",
            replace="# rewritten by the guard-check self-test; this decides nothing",
        ),
    ),
)


def test_the_harness_reports_a_test_that_does_not_notice_its_guard_as_surviving(
    monkeypatch: pytest.MonkeyPatch,
):
    """The one that matters. A harness that reported every marked test as
    discriminating would pass every other test in this file and be exactly as
    useless as no harness at all — it would declare the whole declining suite
    sound and be believed.

    **It is driven off a SYNTHETIC guard, and that is the correction rather
    than a compromise.** This used to run `supertype_dispatch.bypassed-by`
    against `A-M2`'s three servlet near-misses, which were independently known
    to survive it. They were fixed — which is the point of the harness — and a
    self-test anchored to a live defect fails the moment its subject is
    repaired, or, worse, quietly stops proving anything if a later defect
    happens to keep it green. The property under test is "a test that passes
    with its guard's edit applied is reported SURVIVED", and the sharpest way
    to produce one is an edit that provably changes no behaviour: a comment.

    A no-op edit is forbidden in the REGISTRY (`guard_check.py` §2.2 — it would
    manufacture a finding about a real test) and is exactly right here, because
    here the expected outcome is what is being checked rather than measured.

    It runs the real thing end to end — a copied tree, a real edit, a real
    pytest subprocess — because every cheaper version tests the harness's
    bookkeeping rather than its measurement, and the measurement is the whole
    mechanism.
    """
    monkeypatch.setitem(guard_check.GUARDS, _UNREACHABLE, _UNREACHABLE_GUARD)
    monkeypatch.setattr(guard_check, "pinned_tests", lambda: {_UNREACHABLE: [_DISCRIMINATING]})

    [outcome], complaints = guard_check.check([_UNREACHABLE])

    assert complaints == []
    assert outcome.uncontrolled == [], "this fails before any mutation — nothing was measured"
    assert outcome.killed == []
    assert outcome.survived == [_DISCRIMINATING]


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
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    """The other direction, and what keeps the allowlist from rotting into a
    record of nothing: an entry whose test now bites must be removed in the same
    commit that made it bite — the near-miss coverage file's
    `test_the_backlog_only_ever_shrinks`, applied to a measured list.

    The allowlist it reads is monkeypatched rather than the shipped one, and
    the reason is this test's own history: the shipped list is now EMPTY, so a
    version reading it would have nothing to assert and would pass whatever
    `report` did. A rule's own test must not go quiet the moment the rule has
    nothing left to catch."""
    monkeypatch.setattr(
        guard_check, "_DOES_NOT_DISCRIMINATE_YET", frozenset({(_DISCRIMINATING, _BYPASS)})
    )
    outcome = guard_check.Outcome(guard_id=_BYPASS, killed=[_DISCRIMINATING])

    assert guard_check.report([outcome], []) == 1
    assert "STALE ALLOWLIST ENTRY" in capsys.readouterr().out


def test_a_partial_run_does_not_report_untouched_allowlist_entries_as_fixed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    """`guard_check.py <one guard>` measures one guard, and the entries for
    every other one were not measured at all. Reporting them as fixed would
    make the shortest possible run look like the most productive.

    Monkeypatched for the reason the test above is: with the shipped allowlist
    empty there is no entry left for a partial run to mis-report, so reading it
    would assert nothing at all."""
    monkeypatch.setattr(
        guard_check,
        "_DOES_NOT_DISCRIMINATE_YET",
        frozenset(
            {("tests/application/test_endpoints.py::test_elsewhere", "single_call.claimed-arity")}
        ),
    )
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
