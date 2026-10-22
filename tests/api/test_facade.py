"""`sextant.api` (2N Task 5, §5b): the library facade, exercised end to end
against a PRIVATE COPY of the `orders-service` fixture — never the tracked
one, for the same reason `tests/cli/test_enrich_command.py` uses one: `enrich`
writes `.sextant-enrichment.json` at the module root, and a test running
against the tracked path would clobber the golden overlay a later `enrich`
regenerates.

`FakeEnrichmentAgent` and `_register_fake` are the same seam
`tests/cli/test_enrich_command.py` already uses — `AGENT_REGISTRY` is one
dict, shared by the CLI and this module alike, so monkeypatching it here
reaches `sextant.api`'s own composition exactly the way it reaches
`cli/app.py`'s. No test in this file calls out to a network — the two that
touch `agent="tradewind"` (the default-auth check and the running-loop
failure) both refuse before any client is built.
"""

import asyncio
import gc
import json
import shutil
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from click.testing import CliRunner

from fixture_build import compile_fixture
from sextant import api
from sextant.agents import AGENT_REGISTRY
from sextant.application.boundary.vocabulary import KINDS
from sextant.application.enrich.tools import ToolExecutor
from sextant.application.ports.enrichment import EnrichmentAnswers, EnrichmentBrief
from sextant.cli.app import cli
from sextant.domain.enrichment import ENRICHMENT_FILE
from sextant.domain.version import FACT_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION, SEXTANT_VERSION

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"

# A real, analysed symbol this fixture's own golden overlay already uses
# (`fixtures/orders-service/.sextant-enrichment.json`) — proven present in
# `declared_symbols`, so a component claim naming it is grounded rather than
# incidentally correct (same constant `tests/cli/test_enrich_command.py`
# pins).
REAL_MEMBER = "com/example/orders/soap/OrderSoapEndpoint#"
PHANTOM_MEMBER = "com/example/orders/soap/GhostClass#"


def _component(
    name: str = "Legacy billing edge", members: list[str] | None = None
) -> dict[str, object]:
    return {
        "kind": "component",
        "evidence": "llm",
        "anchor": "after-component-overview",
        "name": name,
        "purpose": "Everything this module exchanges with the billing system lives here.",
        "members": [REAL_MEMBER] if members is None else members,
    }


@dataclass
class FakeEnrichmentAgent:
    """The `EnrichmentAgent` port, driven by a canned answer instead of a
    model — makes one real tool call first (so the transcript is not empty),
    then returns the answer it was built with. Identical in shape to
    `tests/cli/test_enrich_command.py`'s own fake."""

    answers_text: str
    captured_kwargs: dict[str, object] | None = None
    seen_briefs: list[EnrichmentBrief] = field(default_factory=list)

    def run(self, brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers:
        self.seen_briefs.append(brief)
        executor.execute("list_dir", {"path": "."})
        return EnrichmentAnswers(text=self.answers_text, transcript=list(executor.transcript))


def _register_fake(monkeypatch: pytest.MonkeyPatch, name: str, agent: FakeEnrichmentAgent) -> None:
    """Registers `agent` under `name` and records whatever kwargs the
    facade's own `enrich()` passed through to the constructor — `AGENT_REGISTRY`
    maps a name to a *constructor* (`Callable[..., EnrichmentAgent]`), so this
    also proves what the caller actually resolved (defaults included)."""

    def _constructor(**kwargs: object) -> FakeEnrichmentAgent:
        agent.captured_kwargs = kwargs
        return agent

    monkeypatch.setitem(AGENT_REGISTRY, name, _constructor)


@pytest.fixture(scope="module")
def compiled_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A private, compiled copy of `orders-service`, shared read-only across
    every test in this module — `mvn` is the expensive part, and
    analyze/render/enrich never touch the source or `target/` a second
    time."""
    root = tmp_path_factory.mktemp("orders-service")
    shutil.copytree(
        FIXTURE,
        root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".sextant", ENRICHMENT_FILE, ".tradewind"),
    )
    compile_fixture(root)
    return root


@pytest.fixture
def module_root(compiled_fixture: Path, tmp_path: Path) -> Path:
    """One test's own module root: the compiled tree is shared, but
    `.sextant/` and `.sextant-enrichment.json` must not leak between tests."""
    root = tmp_path / "orders-service"
    shutil.copytree(compiled_fixture, root)
    return root


@pytest.fixture(scope="module")
def rendered_fixture(compiled_fixture: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The compiled copy, analysed and rendered ONCE through the facade itself, not the
    CLI — these are facade tests, and `analyze`/`render` are exactly as much "the facade"
    as `enrich` is. MEASURED 2026-09-12 (`--durations`): eight `enrich` tests here each
    re-ran both, 15s apiece, to reach a workspace that is the same every time."""
    root = tmp_path_factory.mktemp("rendered") / "orders-service"
    shutil.copytree(compiled_fixture, root)
    api.analyze(root)
    api.render(root)
    return root


@pytest.fixture
def rendered_root(rendered_fixture: Path, tmp_path: Path) -> Path:
    """One `enrich` test's own analysed-and-rendered module root, so what it writes never
    leaks into the next. The tests OF `analyze` and `render` keep `module_root`, which has
    no workspace yet — that is what they are testing."""
    root = tmp_path / "orders-service"
    shutil.copytree(rendered_fixture, root)
    return root


def _configure_a_model(root: Path) -> None:
    """`sextant.api.enrich` carries no `model` parameter (brief §5b: it
    reads `.sextant.yml enrich: model:`, the same source the CLI falls back
    to when `--model` is absent) — a live run, fake agent or real, needs one
    named somewhere. `root`'s own copy of `.sextant.yml` is private per test
    (the `module_root` fixture), so widening it here cannot leak into
    another test."""
    config = root / ".sextant.yml"
    config.write_text(
        config.read_text(encoding="utf-8") + "\nenrich:\n  model: dummy-model\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------


def test_analyze_returns_a_frozen_result_naming_the_modules_endpoint_count(module_root: Path):
    """The library equivalent of `sextant module analyze <path>` — a plain
    Python call against a fixture copy, asserted on the returned object
    rather than on stdout the way the CLI's own test does."""
    result = api.analyze(module_root)

    assert isinstance(result, api.AnalyzeResult)
    assert len(result.modules) == 1
    outcome = result.modules[0]
    assert isinstance(outcome, api.ModuleOutcome)
    assert outcome.analyzed is True
    assert outcome.skip_reason is None
    assert outcome.endpoints is not None and outcome.endpoints > 0
    assert (module_root / ".sextant" / "metadata.json").is_file()


def test_a_refused_detection_raises_a_sextanterror_not_systemexit_with_the_cli_message(
    tmp_path: Path,
):
    """Step 1's own requirement: a malformed `pom.xml` is refused by
    `MavenDetector.detect` as a `ParseError`, and `analyze` turns it into a
    typed `DetectionError` — never `SystemExit`, the shape a `click` command
    that let this propagate unhandled would raise. The message is asserted
    to be the EXACT text the CLI prints for the identical input (`Error: `
    is `click.ClickException`'s own prefix, added nowhere else), proving the
    extraction changed nothing about what a caller reads."""
    (tmp_path / "pom.xml").write_text("<project><groupId>oops</project>", encoding="utf-8")

    with pytest.raises(api.SextantError) as excinfo:
        api.analyze(tmp_path)
    assert not isinstance(excinfo.value, SystemExit)
    assert isinstance(excinfo.value, api.DetectionError)

    cli_result = CliRunner().invoke(cli, ["module", "analyze", str(tmp_path)])
    assert cli_result.exit_code != 0
    assert cli_result.output == f"Error: {excinfo.value}\n"


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def test_render_writes_both_documents_after_analyze(module_root: Path):
    api.analyze(module_root)

    result = api.render(module_root)

    assert isinstance(result, api.RenderResult)
    assert result.markdown == module_root / ".sextant" / "render" / "architecture.md"
    assert result.html == module_root / ".sextant" / "render" / "architecture.html"
    assert result.markdown.is_file()
    assert result.html.is_file()


def test_render_before_analyze_raises_notanalyzederror(tmp_path: Path):
    with pytest.raises(api.NotAnalyzedError):
        api.render(tmp_path)


def _stamped_workspace(root: Path, **overrides: object) -> Path:
    """A workspace directory carrying nothing but the two files the read gate
    checks for and the three stamps it compares — `overrides` replaces or (with
    a `None` value) DELETES one of them.

    Deliberately synthetic rather than a real `analyze` run: the stamp
    comparison happens before anything opens `workspace.duckdb`, so a workspace
    with the shape of a real one is all these tests need, and building it this
    way keeps them independent of a compiled fixture — which is what lets
    `scripts/guard_check.py` run them against a mutated copy of `src/` alone."""
    stamps: dict[str, object] = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "sextant_version": SEXTANT_VERSION,
        "fact_schema_version": FACT_SCHEMA_VERSION,
        **overrides,
    }
    workspace_dir = root / ".sextant"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "workspace.duckdb").write_bytes(b"")
    document: dict[str, object] = {"provenance": {}}
    for name, value in stamps.items():
        if value is None:
            continue
        if name == "schema_version":
            document["schema_version"] = value
        else:
            cast(dict[str, object], document["provenance"])[name] = value
    (workspace_dir / "metadata.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    return workspace_dir


@pytest.mark.pins("api.workspace-stamp-matches-the-running-build")
def test_a_workspace_derived_by_another_graph_schema_version_is_refused(tmp_path: Path):
    """OI-24, and the reason it had to close in the change that gave the walk
    a reader. `graph_schema_version` is D01 §7's stamp for the DERIVED tables,
    and a workspace one version behind answers `roots` and `call_edges` with
    empty tables rather than with an error — so `## Traces` would render
    `None found.` for a module with 160 endpoints and say nothing at all about
    why. An empty table and an absent table are the same bytes; only the stamp
    tells them apart, and until here nothing compared it."""
    _stamped_workspace(tmp_path, schema_version="0.9.0")

    with pytest.raises(api.NotAnalyzedError) as refused:
        api.render(tmp_path)

    assert "graph_schema_version" in str(refused.value)
    assert "0.9.0" in str(refused.value)


@pytest.mark.pins("api.workspace-stamp-matches-the-running-build")
def test_a_workspace_derived_by_another_sextant_version_is_refused(tmp_path: Path):
    """D01 §7's blunt last row: *"any Sextant version change re-derives,
    because derivation logic may have changed and there is no cheap way to
    know"*. A fixed dispatch bug produces a different graph from identical
    facts, and nothing about the graph schema moves when it does — so the
    version stamp is the only thing that can notice."""
    _stamped_workspace(tmp_path, sextant_version="0.0.1")

    with pytest.raises(api.NotAnalyzedError) as refused:
        api.render(tmp_path)

    assert "sextant_version" in str(refused.value)


@pytest.mark.pins("api.workspace-stamp-matches-the-running-build")
def test_a_workspace_missing_a_stamp_entirely_is_refused(tmp_path: Path):
    """An absent stamp is a mismatch, not an exemption. `write_metadata` has
    always written all three, so a document missing one was written by
    something that is not this program — and reading it as "close enough"
    is the silent acceptance the comparison exists to stop."""
    _stamped_workspace(tmp_path, fact_schema_version=None)

    with pytest.raises(api.NotAnalyzedError) as refused:
        api.render(tmp_path)

    assert "fact_schema_version" in str(refused.value)


@pytest.mark.pins("api.workspace-stamp-matches-the-running-build")
def test_export_refuses_a_stale_workspace_the_same_way_render_does(tmp_path: Path):
    """One gate, three verbs. `export` publishes a bundle other systems read
    (D06), so a stale workspace reaching it does not stop at one wrong
    document — it ships. The refusal lives in `_refuse_if_unanalyzed`, which
    all three call, precisely so this cannot be true of one verb and not
    another."""
    _stamped_workspace(tmp_path, schema_version="0.9.0")

    with pytest.raises(api.NotAnalyzedError):
        api.export(tmp_path)


def test_a_workspace_this_build_wrote_is_not_refused_as_stale(module_root: Path):
    """The near-miss §10 requires beside the four positives above, and the one
    that matters most: a gate that refused everything would pass every "is it
    refused?" test in this file while making `render` useless. The stamps
    `analyze` just wrote are the ones this build compares against, so the
    ordinary path must be untouched.

    Against a REAL analysed module, not a synthetic stamp file: the point of
    the pair is that the workspace this program actually writes is the one it
    accepts, which a hand-built `metadata.json` could agree with while
    `write_metadata` had drifted."""
    api.analyze(module_root)

    result = api.render(module_root)

    assert result.markdown.is_file()
    assert result.html.is_file()


def test_a_malformed_overlay_raises_configurationerror(rendered_root: Path):
    """`.sextant-enrichment.json` is Sextant's own program artifact — one
    that does not parse is the same class of "written wrong" mistake a bad
    `.sextant.yml` is, and `render` refuses it as a `ConfigurationError`."""
    (rendered_root / ENRICHMENT_FILE).write_text("not json", encoding="utf-8")

    with pytest.raises(api.ConfigurationError):
        api.render(rendered_root)


# --------------------------------------------------------------------------
# enrich
# --------------------------------------------------------------------------


def test_enrich_dry_run_returns_the_brief_path_and_validates_nothing(rendered_root: Path):
    """Step 1's own requirement. `dry_run=True` calls no agent — `overlay`
    stands in for the one artifact the call actually wrote (the composed
    brief), and `accepted`/`refused`/`partial_reason` are all the honest
    zero/`None` of a run that validated no answer."""

    result = api.enrich(rendered_root, dry_run=True)

    assert isinstance(result, api.EnrichResult)
    assert result.overlay == rendered_root / ".sextant" / "enrich-brief.json"
    assert result.overlay is not None and result.overlay.is_file()
    assert result.accepted == 0
    assert result.refused == 0
    assert result.partial_reason is None
    assert not (rendered_root / ENRICHMENT_FILE).exists()


def test_enrich_dry_run_and_ingest_together_raise_enrichmenterror(rendered_root: Path):
    answers = rendered_root / "answers.json"
    answers.write_text("[]", encoding="utf-8")

    with pytest.raises(api.EnrichmentError):
        api.enrich(rendered_root, dry_run=True, ingest=answers)


def test_enrich_default_auth_is_api_key_a_library_host_has_no_login(
    rendered_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Step 1's own requirement, and the v1 contract's own asymmetry
    (module docstring): the CLI's own default is `subscription`; embedding
    defaults the opposite way, deliberately, since a service host has no
    login to hand Tradewind. Proven by what actually reaches the agent's own
    constructor, not by reading the default off the signature."""
    _configure_a_model(rendered_root)
    fake = FakeEnrichmentAgent(answers_text=json.dumps([_component()]))
    _register_fake(monkeypatch, "fake-default-auth", fake)

    api.enrich(rendered_root, agent="fake-default-auth")

    assert fake.captured_kwargs is not None
    assert fake.captured_kwargs["auth"] == "api-key"


def test_enrich_accepts_claims_and_writes_the_overlay(
    rendered_root: Path, monkeypatch: pytest.MonkeyPatch
):
    _configure_a_model(rendered_root)
    fake = FakeEnrichmentAgent(answers_text=json.dumps([_component()]))
    _register_fake(monkeypatch, "fake-happy-path", fake)

    result = api.enrich(rendered_root, agent="fake-happy-path")

    assert result.overlay == rendered_root / ENRICHMENT_FILE
    assert result.overlay is not None and result.overlay.is_file()
    assert result.accepted == 1
    assert result.refused == 0
    assert result.partial_reason is None
    assert len(fake.seen_briefs) == 1


def test_enrich_reports_refused_claims_and_partial_reason(
    rendered_root: Path, monkeypatch: pytest.MonkeyPatch
):
    _configure_a_model(rendered_root)
    claims = [_component(), _component(name="Phantom", members=[PHANTOM_MEMBER])]
    fake = FakeEnrichmentAgent(answers_text=json.dumps(claims))
    _register_fake(monkeypatch, "fake-refusal", fake)

    result = api.enrich(rendered_root, agent="fake-refusal")

    assert result.accepted == 1
    assert result.refused == 1


def test_unknown_agent_raises_enrichmenterror_naming_the_known_list(rendered_root: Path):

    with pytest.raises(api.EnrichmentError) as excinfo:
        api.enrich(rendered_root, agent="not-a-real-agent")
    assert "not-a-real-agent" in str(excinfo.value)
    assert "tradewind" in str(excinfo.value)


def test_enrich_before_render_raises_enrichmenterror_naming_render(module_root: Path):
    api.analyze(module_root)

    with pytest.raises(api.EnrichmentError) as excinfo:
        api.enrich(module_root, dry_run=True)
    assert "sextant module render" in str(excinfo.value)


def test_enrich_before_analyze_raises_notanalyzederror(tmp_path: Path):
    with pytest.raises(api.NotAnalyzedError):
        api.enrich(tmp_path, dry_run=True)


# --------------------------------------------------------------------------
# enrich_async / the running-loop pair (Task 4 review's ruled carry)
# --------------------------------------------------------------------------


def test_enrich_async_awaited_in_a_running_loop_works_with_the_fake_agent(
    rendered_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """`enrich_async` is the facade's own async entry (module docstring):
    the same composition as `enrich`, run on a worker thread so it can be
    safely awaited from a caller that already has a running loop — an async
    service's own request handler, above all."""
    _configure_a_model(rendered_root)
    fake = FakeEnrichmentAgent(answers_text=json.dumps([_component()]))
    _register_fake(monkeypatch, "fake-async", fake)

    async def _run() -> api.EnrichResult:
        return await api.enrich_async(rendered_root, agent="fake-async")

    result = asyncio.run(_run())

    assert result.accepted == 1
    assert result.overlay == rendered_root / ENRICHMENT_FILE


def test_sync_enrich_called_from_a_running_loop_raises_the_adapters_own_message(
    rendered_root: Path,
):
    """The failure `enrich_async` exists to avoid: calling the plain,
    synchronous `enrich` from a coroutine already running under
    `asyncio.run` reaches `TradewindAgent.run`'s own nested `asyncio.run`,
    which raises immediately — before the coroutine it was given ever starts,
    so no client is built and no network call is attempted. Real
    `TradewindAgent`, deliberately: the point is that ITS OWN wrapping
    (`except Exception as failure: raise EnrichmentAgentError(f"tradewind
    run failed: {failure}")`) is what surfaces here, pinned by message,
    unchanged by this task."""
    _configure_a_model(rendered_root)

    async def _run() -> None:
        api.enrich(rendered_root, agent="tradewind", auth="api-key")

    with pytest.raises(api.EnrichmentError) as excinfo:
        asyncio.run(_run())
    assert str(excinfo.value) == (
        "tradewind run failed: asyncio.run() cannot be called from a running event loop"
    )

    # `TradewindAgent.run`'s own `self._run_async(brief, executor)` builds a
    # coroutine object before `asyncio.run` ever gets to run it — the nested
    # RuntimeError above fires immediately, so that coroutine is dropped
    # unawaited (fix round 1, MINOR-6). Left to Python's own GC, the "was
    # never awaited" warning surfaces whenever collection eventually runs —
    # observed attributed to a LATER, unrelated test in this same file,
    # since `excinfo`'s own traceback keeps the coroutine's frame alive
    # until something drops it. Dropped and force-collected here instead,
    # inside a `catch_warnings` this test owns, so the warning — inherent to
    # the scenario, not a bug — lands on the test that actually caused it.
    del excinfo
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        gc.collect()
    assert any("was never awaited" in str(warning.message) for warning in caught)


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def test_export_writes_a_bundle_with_the_manifest(rendered_root: Path):

    result = api.export(rendered_root)

    assert isinstance(result, api.ExportResult)
    assert result.bundle.is_dir()
    assert (result.bundle / "manifest.json").is_file()


def test_export_before_analyze_raises_notanalyzederror(tmp_path: Path):
    with pytest.raises(api.NotAnalyzedError):
        api.export(tmp_path)


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------


def test_diff_of_a_workspace_with_itself_is_empty_and_lists_every_kind(rendered_root: Path):
    result = api.diff(rendered_root, rendered_root)

    assert isinstance(result, api.DiffResult)
    assert result.diff.entries == () and set(result.diff.summary) == set(KINDS)
    assert result.written is None


def test_diff_writes_the_file_when_out_is_given(rendered_root: Path, tmp_path: Path):
    target = tmp_path / "nested" / "diff.json"

    result = api.diff(rendered_root, rendered_root, out=target)

    assert result.written == target
    written = target.read_text(encoding="utf-8")
    assert json.loads(written)["summary"] == result.diff.to_json()["summary"]
    assert written == json.dumps(result.diff.to_json(), sort_keys=True, indent=2) + "\n"


def test_diff_before_analyze_raises_notanalyzederror(tmp_path: Path):
    with pytest.raises(api.NotAnalyzedError):
        api.diff(tmp_path, tmp_path)


def test_diff_of_two_stamps_that_cannot_be_compared_raises_diffrefusederror(
    rendered_root: Path, tmp_path: Path
):
    """The refusal's own text names the stamp that differs; the facade carries it unchanged."""
    stale = tmp_path / "stale"
    shutil.copytree(rendered_root / ".sextant", stale)
    metadata = json.loads((stale / "metadata.json").read_text(encoding="utf-8"))
    metadata["schema_version"] = "0.9.0"
    (stale / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(api.DiffRefusedError) as refused:
        api.diff(rendered_root, stale)

    assert "graph_schema_version" in str(refused.value)


# --------------------------------------------------------------------------
# observability
# --------------------------------------------------------------------------


def test_observability_of_a_workspace_is_the_map_analyze_wrote(rendered_root: Path):
    stored = json.loads((rendered_root / ".sextant" / "metadata.json").read_text("utf-8"))

    result = api.observability(rendered_root)

    assert isinstance(result, api.ObservabilityMap)
    assert result.to_json() == stored["observability"]
    assert api.observability(rendered_root / ".sextant").to_json() == stored["observability"]
    assert set(result.kinds) == set(KINDS)


def test_observability_reads_a_bundle_as_well_as_a_workspace(rendered_root: Path):
    stored = json.loads((rendered_root / ".sextant" / "metadata.json").read_text("utf-8"))
    bundle = api.export(rendered_root).bundle

    result = api.observability(bundle)

    assert result.to_json() == stored["observability"]


def test_observability_of_a_workspace_without_the_map_is_the_labelled_degraded_one(
    rendered_root: Path,
):
    path = rendered_root / ".sextant" / "metadata.json"
    metadata = json.loads(path.read_text("utf-8"))
    del metadata["catalogs_run"], metadata["observability"]
    path.write_text(json.dumps(metadata), encoding="utf-8")

    result = api.observability(rendered_root)

    assert "predates boundary vocabulary 1" in result.kinds["endpoint"].reasons[0]
    assert result.kinds["endpoint"].verdict == "partial"


def test_observability_before_analyze_raises_notanalyzederror(tmp_path: Path):
    with pytest.raises(api.NotAnalyzedError):
        api.observability(tmp_path)


def test_observability_of_a_document_that_is_not_an_object_raises_notanalyzederror(
    tmp_path: Path,
):
    (tmp_path / "metadata.json").write_text("[1, 2]", encoding="utf-8")

    with pytest.raises(api.NotAnalyzedError, match="metadata.json"):
        api.observability(tmp_path)
