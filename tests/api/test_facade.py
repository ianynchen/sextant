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
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from click.testing import CliRunner

from sextant import api
from sextant.agents import AGENT_REGISTRY
from sextant.application.enrich.tools import ToolExecutor
from sextant.application.ports.enrichment import EnrichmentAnswers, EnrichmentBrief
from sextant.cli.app import cli
from sextant.domain.enrichment import ENRICHMENT_FILE

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
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=root, check=True)
    return root


@pytest.fixture
def module_root(compiled_fixture: Path, tmp_path: Path) -> Path:
    """One test's own module root: the compiled tree is shared, but
    `.sextant/` and `.sextant-enrichment.json` must not leak between tests."""
    root = tmp_path / "orders-service"
    shutil.copytree(compiled_fixture, root)
    return root


def _analyzed_and_rendered(root: Path) -> None:
    """Prepares `root` through the facade itself, not the CLI — these are
    facade tests, and `analyze`/`render` are exactly as much "the facade" as
    `enrich` is."""
    api.analyze(root)
    api.render(root)


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


def test_a_malformed_overlay_raises_configurationerror(module_root: Path):
    """`.sextant-enrichment.json` is Sextant's own program artifact — one
    that does not parse is the same class of "written wrong" mistake a bad
    `.sextant.yml` is, and `render` refuses it as a `ConfigurationError`."""
    _analyzed_and_rendered(module_root)
    (module_root / ENRICHMENT_FILE).write_text("not json", encoding="utf-8")

    with pytest.raises(api.ConfigurationError):
        api.render(module_root)


# --------------------------------------------------------------------------
# enrich
# --------------------------------------------------------------------------


def test_enrich_dry_run_returns_the_brief_path_and_validates_nothing(module_root: Path):
    """Step 1's own requirement. `dry_run=True` calls no agent — `overlay`
    stands in for the one artifact the call actually wrote (the composed
    brief), and `accepted`/`refused`/`partial_reason` are all the honest
    zero/`None` of a run that validated no answer."""
    _analyzed_and_rendered(module_root)

    result = api.enrich(module_root, dry_run=True)

    assert isinstance(result, api.EnrichResult)
    assert result.overlay == module_root / ".sextant" / "enrich-brief.json"
    assert result.overlay is not None and result.overlay.is_file()
    assert result.accepted == 0
    assert result.refused == 0
    assert result.partial_reason is None
    assert not (module_root / ENRICHMENT_FILE).exists()


def test_enrich_dry_run_and_ingest_together_raise_enrichmenterror(module_root: Path):
    _analyzed_and_rendered(module_root)
    answers = module_root / "answers.json"
    answers.write_text("[]", encoding="utf-8")

    with pytest.raises(api.EnrichmentError):
        api.enrich(module_root, dry_run=True, ingest=answers)


def test_enrich_default_auth_is_api_key_a_library_host_has_no_login(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Step 1's own requirement, and the v1 contract's own asymmetry
    (module docstring): the CLI's own default is `subscription`; embedding
    defaults the opposite way, deliberately, since a service host has no
    login to hand Tradewind. Proven by what actually reaches the agent's own
    constructor, not by reading the default off the signature."""
    _analyzed_and_rendered(module_root)
    _configure_a_model(module_root)
    fake = FakeEnrichmentAgent(answers_text=json.dumps([_component()]))
    _register_fake(monkeypatch, "fake-default-auth", fake)

    api.enrich(module_root, agent="fake-default-auth")

    assert fake.captured_kwargs is not None
    assert fake.captured_kwargs["auth"] == "api-key"


def test_enrich_accepts_claims_and_writes_the_overlay(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    _analyzed_and_rendered(module_root)
    _configure_a_model(module_root)
    fake = FakeEnrichmentAgent(answers_text=json.dumps([_component()]))
    _register_fake(monkeypatch, "fake-happy-path", fake)

    result = api.enrich(module_root, agent="fake-happy-path")

    assert result.overlay == module_root / ENRICHMENT_FILE
    assert result.overlay is not None and result.overlay.is_file()
    assert result.accepted == 1
    assert result.refused == 0
    assert result.partial_reason is None
    assert len(fake.seen_briefs) == 1


def test_enrich_reports_refused_claims_and_partial_reason(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    _analyzed_and_rendered(module_root)
    _configure_a_model(module_root)
    claims = [_component(), _component(name="Phantom", members=[PHANTOM_MEMBER])]
    fake = FakeEnrichmentAgent(answers_text=json.dumps(claims))
    _register_fake(monkeypatch, "fake-refusal", fake)

    result = api.enrich(module_root, agent="fake-refusal")

    assert result.accepted == 1
    assert result.refused == 1


def test_unknown_agent_raises_enrichmenterror_naming_the_known_list(module_root: Path):
    _analyzed_and_rendered(module_root)

    with pytest.raises(api.EnrichmentError) as excinfo:
        api.enrich(module_root, agent="not-a-real-agent")
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
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """`enrich_async` is the facade's own async entry (module docstring):
    the same composition as `enrich`, run on a worker thread so it can be
    safely awaited from a caller that already has a running loop — an async
    service's own request handler, above all."""
    _analyzed_and_rendered(module_root)
    _configure_a_model(module_root)
    fake = FakeEnrichmentAgent(answers_text=json.dumps([_component()]))
    _register_fake(monkeypatch, "fake-async", fake)

    async def _run() -> api.EnrichResult:
        return await api.enrich_async(module_root, agent="fake-async")

    result = asyncio.run(_run())

    assert result.accepted == 1
    assert result.overlay == module_root / ENRICHMENT_FILE


def test_sync_enrich_called_from_a_running_loop_raises_the_adapters_own_message(
    module_root: Path,
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
    _analyzed_and_rendered(module_root)
    _configure_a_model(module_root)

    async def _run() -> None:
        api.enrich(module_root, agent="tradewind", auth="api-key")

    with pytest.raises(api.EnrichmentError) as excinfo:
        asyncio.run(_run())
    assert str(excinfo.value) == (
        "tradewind run failed: asyncio.run() cannot be called from a running event loop"
    )


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def test_export_writes_a_bundle_with_the_manifest(module_root: Path):
    _analyzed_and_rendered(module_root)

    result = api.export(module_root)

    assert isinstance(result, api.ExportResult)
    assert result.bundle.is_dir()
    assert (result.bundle / "manifest.json").is_file()


def test_export_before_analyze_raises_notanalyzederror(tmp_path: Path):
    with pytest.raises(api.NotAnalyzedError):
        api.export(tmp_path)
