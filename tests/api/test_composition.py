"""Whitebox seams inside `sextant.api`'s own composition — relocated here
(2N Task 6, carry (c)) from `tests/cli/test_app.py`, which unit-tested them
through two re-exports `cli/app.py` kept purely for these tests'
sake: `_skip_reason = api._skip_reason` (no translation, an unchanged
alias) and a `_tool_executor_for` wrapper that caught `api.EnrichmentError`
and re-raised `click.ClickException`. Neither re-export had a production
caller left after 2N Task 5's extraction — `module_enrich` calls
`api._enrich` directly, which calls `api._tool_executor_for` itself — so
both were dead code kept alive only by these tests. Ported faithfully
against the real functions they always exercised, `sextant.api._skip_reason`
and `sextant.api._tool_executor_for`, asserting what those functions
actually raise now that there is no CLI-layer translation to intercept it:
`api.EnrichmentError`, not `click.ClickException`."""

from pathlib import Path

import pytest

from sextant import api
from sextant.application.ports.detector import ModuleModel
from sextant.domain.redaction import Redactor


def test_a_missing_home_directory_is_reported_as_a_message_not_a_stack_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`ToolExecutor.__init__` (2K Task 7 fix round 3) calls `Path.home()`,
    which raises `RuntimeError` — not `ValueError` — when no home directory
    can be resolved (a container image with no `HOME` set, above all). Before
    2K Task 8's review, `_tool_executor_for` caught `ValueError` alone, so
    this would have escaped as an uncaught crash rather than reaching the
    caller as the same kind of message every other jail-construction refusal
    already gets.

    A direct unit test of `_tool_executor_for` rather than a full `module
    enrich` invocation: the jailed roots just need to exist and sit under
    the repository root `IgnoreRules.load` reads, which `tmp_path` alone
    already satisfies — no fixture compile required."""
    (tmp_path / "facts").mkdir()
    (tmp_path / "render").mkdir()

    def _no_home() -> Path:
        raise RuntimeError("could not determine the user's home directory")

    monkeypatch.setattr(Path, "home", staticmethod(_no_home))

    with pytest.raises(api.EnrichmentError) as excinfo:
        api._tool_executor_for(tmp_path, tmp_path, Redactor.from_rules())
    assert "could not determine the user's home directory" in str(excinfo.value)


def test_no_module_kind_causes_a_skip():
    """The near-miss for the removed `library` skip (2026-09-04 user ruling):
    module KIND no longer decides analysis at all. Even the value that used to
    skip outright is analyzed now — nothing produces `library` any more, and a
    module nothing references costs only facts nobody links to, while skipping
    a referenced one loses its outbound clients and shapes entirely. The one
    surviving skip rests on evidence, not inference: Maven's own declaration
    that a module produces no jar."""
    for kind in ("library", "service", "undetermined"):
        module = ModuleModel(
            module_id="g:a",
            coordinates="g/a",
            version="1.0.0",
            root=Path("."),
            kind=kind,
            languages=frozenset(),
            source_roots=(),
            output_dirs=(),
        )
        assert api._skip_reason(module) is None, kind


def test_skip_reason_names_packaging_pom():
    module = ModuleModel(
        module_id="g:a",
        coordinates="g/a",
        version="1.0.0",
        root=Path("."),
        kind="undetermined",
        languages=frozenset(),
        source_roots=(),
        output_dirs=(),
        packaging="pom",
    )
    assert api._skip_reason(module) == "packaging is pom"


def test_skip_reason_is_none_for_an_ordinary_undetermined_jar_module():
    """The ruled amendment's whole point: `undetermined` alone is no longer
    a skip reason."""
    module = ModuleModel(
        module_id="g:a",
        coordinates="g/a",
        version="1.0.0",
        root=Path("."),
        kind="undetermined",
        languages=frozenset(),
        source_roots=(),
        output_dirs=(),
    )
    assert api._skip_reason(module) is None
