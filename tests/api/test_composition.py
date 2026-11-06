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


def test_no_module_kind_causes_a_skip(tmp_path: Path):
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
            languages=frozenset({"java"}),  # a language a scanner reads: only KIND is in question
            source_roots=(),
            # Compiled classes on disk, so the module has something to scan and only its
            # KIND is in question here.
            output_dirs=(tmp_path,),
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


@pytest.mark.pins("api.a-module-with-NOTHING-TO-SCAN-is-skipped")
def test_a_project_with_no_source_and_no_classes_is_skipped_with_its_reason(tmp_path: Path):
    """`subprojects { apply plugin: 'java' }` is how a great many Gradle builds are written,
    and it gives a folder-only project — `:services`, holding `:services:orders` — the java
    plugin too: Gradle reports a classes directory for it that is never created and no source
    root that exists. Analysed, it has no language, "no scanner accepts a module with no
    language" was raised, and the WHOLE reactor stopped (pre-existing; OI-273 fix round 1).
    It holds nothing to scan, exactly like a Maven `pom` module, so it is skipped and says why."""
    module = ModuleModel(
        module_id="shop:services",
        coordinates="shop/services",
        version="unspecified",
        root=tmp_path,
        kind="undetermined",
        languages=frozenset(),
        source_roots=(),
        output_dirs=(tmp_path / "build" / "classes" / "java" / "main",),
    )
    assert api._skip_reason(module) == "no source and no compiled classes: nothing to scan"


def test_skip_reason_puts_a_build_failure_first():
    """A part Gradle could not build is skipped with Gradle's own words (Android design M5),
    before any other rule: its packaging and its empty folders say only that it was not
    built, not why."""
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
        build_failure="not built: a part it needs failed to build (:lib)",
    )
    assert api._skip_reason(module) == "not built: a part it needs failed to build (:lib)"


@pytest.mark.pins("detect.a-part-with-NO-JVM-TARGET-is-skipped-with-that-reason")
def test_skip_reason_gives_the_detectors_own_reason_before_packaging():
    """A Kotlin Multiplatform part with only JS or Kotlin/Native versions has no classes, so
    its packaging is `pom`; the detector's reason says why, and is given instead (Android
    outbound Task 7)."""
    reason = "no JVM or Android target: Sextant reads JVM bytecode only (targets: js)"
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
        skip_reason=reason,
    )
    assert api._skip_reason(module) == reason


def test_skip_reason_is_none_for_an_ordinary_undetermined_jar_module(tmp_path: Path):
    """The ruled amendment's whole point: `undetermined` alone is no longer
    a skip reason."""
    module = ModuleModel(
        module_id="g:a",
        coordinates="g/a",
        version="1.0.0",
        root=Path("."),
        kind="undetermined",
        languages=frozenset({"java"}),  # a language a scanner reads: only KIND is in question
        source_roots=(),
        output_dirs=(tmp_path,),
    )
    assert api._skip_reason(module) is None


def test_the_catalog_hash_changes_when_any_model_beside_the_catalogs_changes(tmp_path: Path):
    """`_catalog_hash` is the identity of the framework knowledge a run was produced
    with, and the shape, bean, step, value and client models are that knowledge as much as
    the catalogs are (D02 §1b, §1c, §1f, §1g; spec 2026-09-21 §5; spec 2026-09-22 §2): an
    edit to any of the five directories must move it, or two runs would claim one knowledge while
    reading different tables."""
    (tmp_path / "invented.yml").write_text("id: invented\n", encoding="utf-8")
    baseline = api._catalog_hash(tmp_path)
    hashes = [baseline]
    for subdirectory in (
        "shape-models",
        "bean-models",
        "step-models",
        "value-models",
        "client-models",
    ):
        (tmp_path / subdirectory).mkdir()
        (tmp_path / subdirectory / "model.yml").write_text(
            f"id: {subdirectory}\n", encoding="utf-8"
        )
        hashes.append(api._catalog_hash(tmp_path))

    assert len(set(hashes)) == len(hashes), "an edit to one of the model directories went unseen"


def test_a_python_project_is_scanned_from_its_import_roots(tmp_path: Path):
    """A Python module writes no build output: the scan reads its import roots, and its
    module fact names Python's lookup rule (spec 2026-11-06 §3b, §3e)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "shop"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    package = tmp_path / "src" / "shop"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "orders.py").write_text("def create(): pass\n", encoding="utf-8")

    api.analyze(tmp_path)

    facts = tmp_path / ".sextant" / "facts"
    assert '"lookup":"c3"' in (facts / "module.jsonl").read_text(encoding="utf-8")
    orders = (facts / "shop" / "orders.py.jsonl").read_text(encoding="utf-8")
    assert "sextant-python pypi shop 1.0.0 shop/orders#create(" in orders
