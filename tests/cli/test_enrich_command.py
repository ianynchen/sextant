"""`sextant module enrich` (2K design §5/§8), end to end through the real CLI
command — `FakeEnrichmentAgent` standing in for the network so the suite
never calls out (2K design §9). Every test here runs against a PRIVATE COPY
of the `orders-service` fixture, never the tracked one: `enrich` writes
`.sextant-enrichment.json` at the module root by design, and the tracked
copy of that file is the golden fixture Task 7's own ruling regenerates
through this same command — a test that ran against the tracked path would
clobber it on every run.

`ToolExecutor` (2K Task 5) requires its jailed roots to sit under the
`.sextantignore` repo root it was loaded for — true of the default
`--workspace` layout (`<module>/.sextant`) and nothing else — so every test
here uses that default rather than an external `tmp_path`, the convention
`test_vertical_slice.py`'s own tests use for `analyze`/`render`.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from click.testing import CliRunner

from sextant.agents import AGENT_REGISTRY
from sextant.application.enrich.tools import ToolExecutor
from sextant.application.ports.enrichment import EnrichmentAnswers, EnrichmentBrief
from sextant.cli.app import cli
from sextant.domain.enrichment import ENRICHMENT_FILE

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"

# Real, analysed symbols this fixture's own golden overlay already uses
# (`fixtures/orders-service/.sextant-enrichment.json`) — proven present in
# `declared_symbols`, so a component claim naming them is grounded rather
# than incidentally correct.
REAL_MEMBER = "com/example/orders/soap/OrderSoapEndpoint#"
PHANTOM_MEMBER = "com/example/orders/soap/GhostClass#"


def _component(name: str = "Legacy billing edge", members: list[str] | None = None) -> dict:
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
    model — makes one real tool call first (so the transcript is not empty
    and the jail actually runs), then returns the answer it was built with."""

    answers_text: str
    partial: bool = False
    partial_reason: str | None = None
    seen_briefs: list[EnrichmentBrief] = field(default_factory=list)

    def run(self, brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers:
        self.seen_briefs.append(brief)
        executor.execute("list_dir", {"path": "."})
        return EnrichmentAnswers(
            text=self.answers_text,
            transcript=list(executor.transcript),
            partial=self.partial,
            partial_reason=self.partial_reason,
        )


def _register_fake(monkeypatch: pytest.MonkeyPatch, name: str, agent: FakeEnrichmentAgent) -> None:
    """Registers `agent` under `name`, ignoring whatever `model`/`max_turns`
    the CLI passes — `AGENT_REGISTRY` maps a name to a *constructor*
    (`Callable[..., EnrichmentAgent]`), so the fake's own constructor just
    hands back the one pre-built instance every test already configured."""
    monkeypatch.setitem(AGENT_REGISTRY, name, lambda **kwargs: agent)


@pytest.fixture(scope="module")
def compiled_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A private, compiled copy of `orders-service` — shared read-only
    ground (the compile) across every test in this module, since `mvn`
    itself is the expensive part and analyze/render/enrich never touch the
    source or `target/` a second time."""
    root = tmp_path_factory.mktemp("orders-service")
    # Neither travels: `.sextant/` is the checked-out repo's own gitignored
    # scratch workspace, whose `workspace.duckdb` can predate the current
    # schema (`CREATE TABLE IF NOT EXISTS` never migrates an existing file);
    # `.sextant-enrichment.json` is the tracked GOLDEN overlay, and a test
    # that inherited it would see one before `enrich` ever ran; `.tradewind`
    # is the api-key session store (2N design §1) — a stale one inherited
    # from a prior local run would make a test asserting the store gets
    # WRITTEN pass vacuously against a file that was already there.
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
    `.sextant/` and `.sextant-enrichment.json` must not leak from one test
    into the next, so each test gets a fresh copy of those two — the only
    things `analyze`/`render`/`enrich` ever write."""
    root = tmp_path / "orders-service"
    shutil.copytree(compiled_fixture, root)
    return root


def _analyzed_and_rendered(root: Path) -> None:
    runner = CliRunner()
    for command in ("analyze", "render"):
        result = runner.invoke(cli, ["module", command, str(root)])
        assert result.exit_code == 0, result.output


def test_enrich_refuses_a_workspace_with_no_rendered_document(module_root: Path):
    """2K design §8: the brief is built from the machine-rendered document,
    so a workspace that was only ever analysed is refused, loudly, naming
    `render` — before composing anything or touching an agent."""
    result = CliRunner().invoke(cli, ["module", "analyze", str(module_root)])
    assert result.exit_code == 0, result.output

    result = CliRunner().invoke(
        cli, ["module", "enrich", str(module_root), "--agent", "claude-api", "--model", "x"]
    )
    assert result.exit_code != 0
    assert "sextant module render" in result.output


def test_an_unknown_agent_is_refused_naming_the_known_list(module_root: Path):
    _analyzed_and_rendered(module_root)
    result = CliRunner().invoke(
        cli, ["module", "enrich", str(module_root), "--agent", "not-a-real-agent", "--model", "x"]
    )
    assert result.exit_code != 0
    assert "not-a-real-agent" in result.output
    assert "tradewind" in result.output


def test_tradewind_api_key_with_no_key_refuses_loudly_naming_the_variable(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """2K Task 7 ruling 5, kept for Tradewind (2N design §1): the key is
    read from the environment alone by SEXTANT, and its absence is refused
    before any client is built — `TradewindAgent.run`'s own pre-client check
    — so this makes no network call even though it exercises the real
    adapter."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _analyzed_and_rendered(module_root)
    result = CliRunner().invoke(
        cli,
        [
            "module",
            "enrich",
            str(module_root),
            "--agent",
            "tradewind",
            "--auth",
            "api-key",
            "--model",
            "claude-x",
        ],
    )
    assert result.exit_code != 0
    assert "ANTHROPIC_API_KEY" in result.output


def test_max_turns_above_the_api_key_ceiling_refuses_via_the_agents_own_validation(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """2N design §1: the langchain (api-key) backend's own hard ceiling is
    24 `--max-turns` (25 model iterations) — `--max-turns 25` is refused
    through `TradewindAgent.__init__`'s own `ValueError`, not a silent late
    failure. The real `tradewind` constructor is used and never reaches the
    network: the `ValueError` fires in `__init__`, before `run` even checks
    for a key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _analyzed_and_rendered(module_root)
    result = CliRunner().invoke(
        cli,
        [
            "module",
            "enrich",
            str(module_root),
            "--agent",
            "tradewind",
            "--auth",
            "api-key",
            "--model",
            "claude-x",
            "--max-turns",
            "25",
        ],
    )
    assert result.exit_code != 0
    assert "--max-turns 25 exceeds the api-key backend's own ceiling of 24" in result.output


def test_max_turns_zero_reaches_the_agent_honestly_not_silently_defaulted(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """2K Task 7 fix round 1, minor, kept for Tradewind: `--max-turns 0` is
    a real, falsy-but-meaningful flag value — `is None`, never `or`, is what
    lets it reach the agent's own constructor as `0` rather than silently
    reading as "no flag given" and becoming the CLI's own default of 20."""
    _analyzed_and_rendered(module_root)
    captured: dict[str, object] = {}

    def _constructor(**kwargs: object) -> FakeEnrichmentAgent:
        captured.update(kwargs)
        return FakeEnrichmentAgent(answers_text=json.dumps([_component()]))

    monkeypatch.setitem(AGENT_REGISTRY, "fake-zero-turns", _constructor)

    result = CliRunner().invoke(
        cli,
        [
            "module",
            "enrich",
            str(module_root),
            "--agent",
            "fake-zero-turns",
            "--model",
            "x",
            "--max-turns",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["max_turns"] == 0


def test_dry_run_writes_only_the_brief_and_instructions_copy(module_root: Path):
    _analyzed_and_rendered(module_root)
    markdown_path = module_root / ".sextant" / "render" / "architecture.md"
    before = markdown_path.read_bytes()

    result = CliRunner().invoke(cli, ["module", "enrich", str(module_root), "--dry-run"])
    assert result.exit_code == 0, result.output

    brief_path = module_root / ".sextant" / "enrich-brief.json"
    instructions_path = module_root / ".sextant" / "enrich-instructions.md"
    assert brief_path.is_file()
    assert instructions_path.is_file()
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    assert "prompt" in brief and "tool_definitions" in brief and "jailed_roots" in brief
    assert {d["name"] for d in brief["tool_definitions"]} == {
        "list_dir",
        "find",
        "grep",
        "read_file",
    }

    # Calls nothing (2K design §3): no overlay, no changed rendered output.
    assert not (module_root / ENRICHMENT_FILE).is_file()
    assert markdown_path.read_bytes() == before


def test_a_second_runs_brief_carries_the_machine_document_not_the_enriched_one(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """2K final review, F1 — the reviewer's live scenario, pinned. Spec §5
    says the brief carries the MACHINE-rendered document, and after one
    `enrich` the file at `render/architecture.md` is the ENRICHED one:
    composing the brief from those bytes would feed a second run its own
    prior claims back as if they were machine findings, compounding run over
    run. That is the very loop the Task 3 overlay-jail exclusion exists to
    prevent, arriving by the other door.

    So the brief is an in-memory, overlay-free assembly — and the pin is
    exact rather than "no claim text visible": byte-for-byte the same
    document `render` writes with no overlay present, which is what makes
    "machine-only" a property of the assembly path rather than of this
    fixture's particular claims."""
    _analyzed_and_rendered(module_root)
    markdown_path = module_root / ".sextant" / "render" / "architecture.md"
    machine_only = markdown_path.read_text(encoding="utf-8")

    fake = FakeEnrichmentAgent(answers_text=json.dumps([_component()]))
    _register_fake(monkeypatch, "fake-second-run", fake)
    first = CliRunner().invoke(
        cli,
        ["module", "enrich", str(module_root), "--agent", "fake-second-run", "--model", "fake-x"],
    )
    assert first.exit_code == 0, first.output

    # The on-disk document really is enriched now — otherwise this test would
    # pass against the very bug it exists to catch.
    enriched = markdown_path.read_text(encoding="utf-8")
    assert "Legacy billing edge" in enriched
    assert enriched != machine_only

    second = CliRunner().invoke(cli, ["module", "enrich", str(module_root), "--dry-run"])
    assert second.exit_code == 0, second.output
    brief = json.loads((module_root / ".sextant" / "enrich-brief.json").read_text(encoding="utf-8"))

    assert "Legacy billing edge" not in brief["prompt"]
    assert "**Enrichment — evidence: llm**" not in brief["prompt"]
    assert machine_only.rstrip("\n") in brief["prompt"]


def test_a_relative_path_argument_resolves_before_the_jail_is_built(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """2K Task 7 fix round 1, Important I3: `path.resolve()` (cli/app.py) —
    without it, a relative `path` argument (the ordinary way to invoke this
    on a command line: `cd` somewhere and name the module relative to it)
    makes `IgnoreRules.load(path)`'s own unresolved `repo_root` disagree
    with `ToolExecutor`'s resolved roots — an absolute path is never
    "relative to" a merely-relative one — and every jailed root is refused
    as a wiring mismatch even though it is genuinely contained. A revert of
    that one line breaks this test."""
    _analyzed_and_rendered(module_root)
    monkeypatch.chdir(module_root.parent)

    result = CliRunner().invoke(cli, ["module", "enrich", module_root.name, "--dry-run"])

    assert result.exit_code == 0, result.output
    assert (module_root / ".sextant" / "enrich-brief.json").is_file()


def test_the_happy_path_writes_the_overlay_and_both_assembled_outputs(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    _analyzed_and_rendered(module_root)
    fake = FakeEnrichmentAgent(answers_text=json.dumps([_component()]))
    _register_fake(monkeypatch, "fake-happy-path", fake)

    result = CliRunner().invoke(
        cli,
        ["module", "enrich", str(module_root), "--agent", "fake-happy-path", "--model", "fake-x"],
    )
    assert result.exit_code == 0, result.output

    overlay = json.loads((module_root / ENRICHMENT_FILE).read_text(encoding="utf-8"))
    assert overlay["produced_by"]["agent"] == "fake-happy-path"
    assert overlay["produced_by"]["model"] == "fake-x"
    assert [claim["name"] for claim in overlay["claims"]] == ["Legacy billing edge"]

    # The agent actually made a tool call, and the transcript records it.
    assert fake.seen_briefs and fake.seen_briefs[0].prompt
    transcript_lines = (
        (module_root / ".sextant" / "enrich-transcript.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert any(json.loads(line).get("name") == "list_dir" for line in transcript_lines)
    summary = json.loads(transcript_lines[-1])
    assert summary == {
        "event": "run_summary",
        "partial": False,
        "partial_reason": None,
        "refusals": [],
    }

    markdown = (module_root / ".sextant" / "render" / "architecture.md").read_text(encoding="utf-8")
    html = (module_root / ".sextant" / "render" / "architecture.html").read_text(encoding="utf-8")
    assert "**Enrichment — evidence: llm**" in markdown
    assert "Legacy billing edge" in markdown
    assert 'class="llm-badge"' in html
    assert "Legacy billing edge" in html


def test_a_refused_claim_is_reported_and_excluded_from_the_written_overlay(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """spec §10's refused-at-ingest case, live through the CLI: the phantom
    member is reported on stdout and never reaches the file (2K design §6)."""
    _analyzed_and_rendered(module_root)
    claims = [_component(), _component(name="Phantom", members=[PHANTOM_MEMBER])]
    fake = FakeEnrichmentAgent(answers_text=json.dumps(claims))
    _register_fake(monkeypatch, "fake-refusal", fake)

    result = CliRunner().invoke(
        cli, ["module", "enrich", str(module_root), "--agent", "fake-refusal", "--model", "x"]
    )
    assert result.exit_code == 0, result.output
    assert "refused claim 1" in result.output
    assert PHANTOM_MEMBER in result.output

    overlay = json.loads((module_root / ENRICHMENT_FILE).read_text(encoding="utf-8"))
    assert [claim["name"] for claim in overlay["claims"]] == ["Legacy billing edge"]


def test_a_later_assembly_failure_still_prints_the_refusal_report_first(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """2N Task 5 fix round 1, MAJOR-1: the per-claim report — BASE's own
    "before either is buried in a file" guarantee — must survive even when
    the FINAL assembly (built from the accepted overlay) fails afterward.
    A `redact:` rule wide enough to eat a claim's own `evidence` marker
    (`value_patterns: [llm]`, matching every accepted claim's `evidence:
    "llm"` — the same pathological rule
    `tests/egress/test_render_assembly.py::
    test_a_redaction_rule_that_breaks_a_claims_schema_is_refused_by_name`
    pins at the renderer level) breaks assembly on the ACCEPTED claim
    (index 0), after a refused claim (the phantom, index 1) has already
    been validated — proving the refusal report for index 1 still reaches
    stdout even though the run then errors out, and reaches it BEFORE the
    error, never after."""
    _analyzed_and_rendered(module_root)
    (module_root / ".sextant.yml").write_text(
        "redact:\n  value_patterns:\n    - llm\n", encoding="utf-8"
    )
    claims = [_component(), _component(name="Phantom", members=[PHANTOM_MEMBER])]
    fake = FakeEnrichmentAgent(answers_text=json.dumps(claims))
    _register_fake(monkeypatch, "fake-assembly-failure", fake)

    result = CliRunner().invoke(
        cli,
        [
            "module",
            "enrich",
            str(module_root),
            "--agent",
            "fake-assembly-failure",
            "--model",
            "x",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "refused claim 1" in result.output
    assert PHANTOM_MEMBER in result.output
    assert "Error:" in result.output
    assert "claim 0" in result.output
    # The report reaches stdout BEFORE the error line — never buried after it.
    assert result.output.index("refused claim 1") < result.output.index("Error:")

    # The overlay IS still written (2K Task 7 fix round 1's own ordering
    # ruling, unaffected by this fix): the accepted claim's record survives
    # a rendering failure that happens after it was written.
    overlay = json.loads((module_root / ENRICHMENT_FILE).read_text(encoding="utf-8"))
    assert [claim["name"] for claim in overlay["claims"]] == ["Legacy billing edge"]


def test_the_checked_in_refused_at_ingest_fixture_pins_its_refusal_report(module_root: Path):
    """Spec §10's own fixture requirement: a checked-in answers file whose
    claims include at least one refusal (`fixtures/orders-service/
    enrich-answers-refused.json` — a real component beside a `Phantom edge`
    naming a class this module does not have), ingested for real and its
    refusal report pinned — the `--ingest` door's own proof of spec §10,
    independent of the dynamically-built refusal case above."""
    _analyzed_and_rendered(module_root)
    answers_path = FIXTURE / "enrich-answers-refused.json"

    result = CliRunner().invoke(
        cli,
        [
            "module",
            "enrich",
            str(module_root),
            "--ingest",
            str(answers_path),
            "--agent",
            "a-human",
            "--model",
            "n/a",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (
        "refused claim 1: component `Phantom edge` names member "
        "`com/example/orders/soap/GhostClass#`, which is not a symbol in this workspace"
    ) in result.output

    overlay = json.loads((module_root / ENRICHMENT_FILE).read_text(encoding="utf-8"))
    assert [claim["name"] for claim in overlay["claims"]] == [
        "Billing edge (refused-at-ingest fixture)"
    ]


def test_a_partial_run_is_reported_and_recorded(module_root: Path, monkeypatch: pytest.MonkeyPatch):
    """2K Task 7 ruling 4: an honest record of a truncated run reaches both
    the user-visible report and the workspace's own transcript file."""
    _analyzed_and_rendered(module_root)
    fake = FakeEnrichmentAgent(
        answers_text=json.dumps([_component()]), partial=True, partial_reason="max_turns"
    )
    _register_fake(monkeypatch, "fake-partial", fake)

    result = CliRunner().invoke(
        cli, ["module", "enrich", str(module_root), "--agent", "fake-partial", "--model", "x"]
    )
    assert result.exit_code == 0, result.output
    assert "partial" in result.output.lower()
    assert "max_turns" in result.output

    transcript_lines = (
        (module_root / ".sextant" / "enrich-transcript.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    summary = json.loads(transcript_lines[-1])
    assert (summary["partial"], summary["partial_reason"]) == (True, "max_turns")


def test_ingest_validates_an_externally_authored_answers_file(module_root: Path, tmp_path: Path):
    """The universal door (2K design §3): no adapter runs, so `--agent`/
    `--model` label the overlay's provenance rather than selecting one."""
    _analyzed_and_rendered(module_root)
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps([_component(name="Ingested claim")]), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "module",
            "enrich",
            str(module_root),
            "--ingest",
            str(answers_path),
            "--agent",
            "a-human",
            "--model",
            "n/a",
        ],
    )
    assert result.exit_code == 0, result.output

    overlay = json.loads((module_root / ENRICHMENT_FILE).read_text(encoding="utf-8"))
    assert overlay["produced_by"]["agent"] == "a-human"
    assert overlay["produced_by"]["model"] == "n/a"
    assert [claim["name"] for claim in overlay["claims"]] == ["Ingested claim"]

    transcript_lines = (
        (module_root / ".sextant" / "enrich-transcript.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    # No agent ran, so the only line is the run summary — a clean,
    # non-partial record (`--ingest` has no notion of a truncated run).
    assert len(transcript_lines) == 1
    assert json.loads(transcript_lines[0])["partial"] is False


def test_ingest_without_agent_or_model_is_refused(module_root: Path, tmp_path: Path):
    _analyzed_and_rendered(module_root)
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps([_component()]), encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["module", "enrich", str(module_root), "--ingest", str(answers_path)]
    )
    assert result.exit_code != 0
    assert "--agent" in result.output and "--model" in result.output


def test_dry_run_and_ingest_are_mutually_exclusive(module_root: Path, tmp_path: Path):
    answers_path = tmp_path / "answers.json"
    answers_path.write_text("[]", encoding="utf-8")
    result = CliRunner().invoke(
        cli,
        ["module", "enrich", str(module_root), "--dry-run", "--ingest", str(answers_path)],
    )
    assert result.exit_code != 0
    assert "--dry-run" in result.output and "--ingest" in result.output


def test_config_defaults_are_used_and_a_flag_overrides_them(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """`.sextant.yml`'s `enrich:` section (2K design §3) supplies `--agent`/
    `--model`/`--max-turns` when a flag does not — flags win, live through
    both a defaulted and an overridden field in the same run."""
    _analyzed_and_rendered(module_root)
    config_path = module_root / ".sextant.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "enrich:\n  agent: fake-config-default\n  model: default-model\n  max_turns: 7\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def _constructor(**kwargs: object) -> FakeEnrichmentAgent:
        captured.update(kwargs)
        return FakeEnrichmentAgent(answers_text=json.dumps([_component()]))

    monkeypatch.setitem(AGENT_REGISTRY, "fake-config-default", _constructor)

    # `--agent` is left to the config default; `--model` is overridden by a flag.
    result = CliRunner().invoke(
        cli, ["module", "enrich", str(module_root), "--model", "flag-model"]
    )
    assert result.exit_code == 0, result.output
    assert captured == {
        "auth": "subscription",
        "model": "flag-model",
        "max_turns": 7,
        "session_store": None,
    }

    overlay = json.loads((module_root / ENRICHMENT_FILE).read_text(encoding="utf-8"))
    assert overlay["produced_by"]["agent"] == "fake-config-default"
    assert overlay["produced_by"]["model"] == "flag-model"


def test_a_zero_max_turns_from_the_config_reaches_the_agent(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """M6 fix: `.sextant.yml enrich: max_turns: 0` used to be refused at the
    yml gate ("must be a positive integer") though the flag and the
    constructor both legalize `0` — an honest single-response run with no
    tool execution. `is None`, never falsy-`or`, is what lets the config's
    own `0` reach the agent here too, mirroring the flag's own
    `test_max_turns_zero_reaches_the_agent_honestly_not_silently_defaulted`."""
    _analyzed_and_rendered(module_root)
    config_path = module_root / ".sextant.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "enrich:\n  agent: fake-config-zero-turns\n  model: default-model\n  max_turns: 0\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def _constructor(**kwargs: object) -> FakeEnrichmentAgent:
        captured.update(kwargs)
        return FakeEnrichmentAgent(answers_text=json.dumps([_component()]))

    monkeypatch.setitem(AGENT_REGISTRY, "fake-config-zero-turns", _constructor)

    result = CliRunner().invoke(cli, ["module", "enrich", str(module_root)])
    assert result.exit_code == 0, result.output
    assert captured["max_turns"] == 0


def test_config_auth_and_session_store_reach_the_agent_and_the_auth_flag_wins(
    module_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Fix round 1, I3: `.sextant.yml enrich: auth:`/`session_store:`
    (2N design §1) reach the agent's own constructor kwargs the same way
    `agent:`/`model:`/`max_turns:` already do — `--auth` (a real flag)
    beats the config's `auth: api-key` the same way every other flag wins
    over its default here, and `session_store` (config-only, no flag
    counterpart) reaches the agent as a `Path` (cli/app.py's own
    conversion), not the raw string `.sextant.yml` carries."""
    _analyzed_and_rendered(module_root)
    config_path = module_root / ".sextant.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "enrich:\n"
        "  agent: fake-config-auth\n"
        "  model: default-model\n"
        "  auth: api-key\n"
        "  session_store: custom/sessions.sqlite\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def _constructor(**kwargs: object) -> FakeEnrichmentAgent:
        captured.update(kwargs)
        return FakeEnrichmentAgent(answers_text=json.dumps([_component()]))

    monkeypatch.setitem(AGENT_REGISTRY, "fake-config-auth", _constructor)

    result = CliRunner().invoke(
        cli,
        ["module", "enrich", str(module_root), "--auth", "subscription"],
    )

    assert result.exit_code == 0, result.output
    assert captured == {
        "auth": "subscription",  # the flag, never the config's "api-key"
        "model": "default-model",
        "max_turns": 20,
        "session_store": Path("custom/sessions.sqlite"),
    }


def test_no_agent_flag_defaults_to_tradewind_so_the_run_fails_at_model_not_agent(
    module_root: Path,
):
    """Fix round 1, M7: `--agent` defaults to `tradewind` (2N design §1)
    when neither the flag nor `.sextant.yml enrich: agent:` names one — a
    bare `enrich` with no flags at all fails on the NEXT missing
    requirement (`--model`), never on an unset `--agent`, which is the only
    way to prove the default actually applies rather than merely being
    documented."""
    _analyzed_and_rendered(module_root)

    result = CliRunner().invoke(cli, ["module", "enrich", str(module_root)])

    assert result.exit_code != 0
    assert "--model is required" in result.output
    assert "--agent is required" not in result.output
