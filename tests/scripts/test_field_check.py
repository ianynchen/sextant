"""2M final review wave, I1: `_checkout` reports whether it actually MOVED
HEAD, and `_ensure_compiled` must rebuild unconditionally when it did —
`target/` is untracked and survives a real `git checkout`, so skipping the
rebuild on "`target/classes` already exists" alone would validate a PIN
REFRESH's new sources against the OLD commit's leftover bytecode.

Driven at the unit level against a throwaway real git repo — `field_check.py`
itself is deliberately opt-in and network-using (its own module docstring),
never part of `scripts/check.sh` or this suite; these tests exercise its git
and subprocess plumbing directly, never `_check_one`'s live-network path.

`scripts/` carries no package `__init__.py` and sits outside `pythonpath`
(`pyproject.toml` only adds `src`), so the module is loaded straight from its
file path rather than imported by name.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "field_check.py"
_spec = importlib.util.spec_from_file_location("field_check", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
field_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(field_check)


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _two_commit_repo(root: Path) -> tuple[str, str]:
    """A tiny real git repo with two commits, so `_checkout` has a genuine
    HEAD to move between — returns `(first_commit, second_commit)`."""
    root.mkdir()
    _git(["init", "-q"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "test"], root)
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    _git(["add", "a.txt"], root)
    _git(["commit", "-q", "-m", "first"], root)
    first = _git(["rev-parse", "HEAD"], root)
    (root / "a.txt").write_text("two\n", encoding="utf-8")
    _git(["commit", "-q", "-am", "second"], root)
    second = _git(["rev-parse", "HEAD"], root)
    return first, second


def test_checkout_reports_false_when_head_is_already_at_the_pinned_commit(tmp_path: Path):
    repo = tmp_path / "repo"
    _first, second = _two_commit_repo(repo)

    assert field_check._checkout(repo, second) is False


def test_checkout_reports_true_when_it_actually_moves_head(tmp_path: Path):
    """The moved-head signal `_ensure_compiled` depends on to know that
    whatever is in `target/classes` was compiled from the PREVIOUS commit."""
    repo = tmp_path / "repo"
    first, _second = _two_commit_repo(repo)

    assert field_check._checkout(repo, first) is True
    assert _git(["rev-parse", "HEAD"], repo) == first


def _stub_run(calls: list[list[str]]) -> object:
    def fake_run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    return fake_run


def test_ensure_compiled_skips_the_rebuild_when_head_did_not_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The ordinary case between two runs of this script: an unmoved HEAD
    means whatever is already in `target/classes` was compiled from the
    commit that is still checked out, so `./mvnw` is never invoked."""
    repo = tmp_path / "repo"
    (repo / "target" / "classes").mkdir(parents=True)
    calls: list[list[str]] = []
    monkeypatch.setattr(field_check, "_run", _stub_run(calls))

    field_check._ensure_compiled(repo, force=False)

    assert calls == []


def test_ensure_compiled_rebuilds_unconditionally_when_head_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """I1's own regression: after a PIN REFRESH (`_checkout` moved HEAD),
    `target/classes` already existing is no longer evidence it matches the
    now-checked-out sources — `force=True` must invoke the build regardless
    of the directory's presence."""
    repo = tmp_path / "repo"
    (repo / "target" / "classes").mkdir(parents=True)
    calls: list[list[str]] = []
    monkeypatch.setattr(field_check, "_run", _stub_run(calls))

    field_check._ensure_compiled(repo, force=True)

    assert calls, "a moved HEAD must trigger a rebuild even though target/classes exists"
