"""Tests for the `scheduled_chain` engine (D02 §2's `scheduled_chain` style; Quartz spec
2026-10-28 §3a, §3b): one `scheduled_work` entry per `newTrigger()` root, with its kind,
its name and its schedule.

Most read `fixtures/orders-quartz`, analysed once through `module analyze`, because the
shapes that matter cross methods — a cron from a getter two calls away, a schedule builder
handed through a helper — and the value walk is what crosses them. The two shapes the
fixture does not hold (a name with no group, two identical unnamed triggers) are hand-built
facts in the `test_call_engines.py` style. Every row is `handler` NULL here: which job a
trigger runs is the next task's.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.engines import scheduled_chain
from sextant.application.resolve.return_flow import record_return_flows
from sextant.cli.app import cli
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

QUARTZ = FIXTURES / "orders-quartz"
CAPABILITIES = {"call_site", "string_constants", "chain_reconstruction"}

TRIGGER_BUILDER = "org/quartz/TriggerBuilder#"
CRON_BUILDER = "org/quartz/CronScheduleBuilder#"


def _catalogs() -> list[Catalog]:
    return YamlCatalogSource(catalogs_dir()).load()


def _quartz(catalogs: list[Catalog]) -> Catalog:
    return next(catalog for catalog in catalogs if catalog.id == "quartz")


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`orders-quartz`, analysed once the way a user analyses it."""
    workspace_dir = tmp_path_factory.mktemp("quartz-chains")
    compile_fixture(QUARTZ)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(QUARTZ), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    return workspace_dir / "workspace.duckdb"


def _entries_in(analyzed: Path, method: str) -> list[dict]:
    """The rows the engine derives from the `newTrigger()` chains in `method`
    (`Class#method`), in the walk's order."""
    catalogs = _catalogs()
    workspace = DuckDbWorkspace(analyzed)
    try:
        entries = scheduled_chain.entries(workspace, _quartz(catalogs), catalogs)
    finally:
        workspace.close()
    return [entry.row for entry in entries if f"/{method}(" in entry.caller]


def test_each_new_trigger_is_one_entry(analyzed: Path):
    """`QuartzConfig` builds four triggers, one per `newTrigger()`; its two `newJob()` chains
    are no triggers."""
    rows = [
        row
        for method in ("sweepEvery30s", "sweepNightly", "auditTrigger", "officeHours")
        for row in _entries_in(analyzed, f"QuartzConfig#{method}")
    ]
    assert len(rows) == 4, rows
    assert {row["trigger"] for row in rows} == {"simple", "cron", "dailyTimeInterval"}
    assert all(row["handler"] is None and row["catalog_id"] == "quartz" for row in rows)
    assert _entries_in(analyzed, "QuartzConfig#sweepDetail") == []


@pytest.mark.declines("quartz")
@pytest.mark.pins("quartz.a-REBUILT-trigger-is-not-an-entry")
def test_a_rebuilt_trigger_is_not_an_entry(analyzed: Path):
    """`updateJob` reschedules an existing trigger through `trigger.getTriggerBuilder()`: the
    same trigger with a new schedule, not a new one (ruling 3), so no entry."""
    assert _entries_in(analyzed, "RowScheduler#updateJob") == []


def test_a_cron_literal_is_resolved_verbatim(analyzed: Path):
    [row] = _entries_in(analyzed, "QuartzConfig#sweepNightly")
    assert (row["trigger"], row["name"], row["expression"], row["resolution"]) == (
        "cron",
        "orders.nightly",
        "0 0 2 * * ?",
        "resolved",
    )
    assert row["expression_source"] is None


def test_a_configured_cron_is_unresolved_and_gets_resolved_schedules(analyzed: Path):
    """`cronSchedule(sweepCron)` with `@Value("${orders.sweep.cron}") String sweepCron`: the
    placeholder verbatim, `unresolved`, and the repository's own value beside it."""
    [row] = _entries_in(analyzed, "QuartzConfig#auditTrigger")
    assert (row["trigger"], row["name"], row["expression"], row["resolution"]) == (
        "cron",
        None,
        "${orders.sweep.cron}",
        "unresolved",
    )
    workspace = DuckDbWorkspace(analyzed)
    try:
        values = [
            value["value"]
            for value in workspace.query("resolved_schedules")
            if value["expression"] == "${orders.sweep.cron}"
        ]
    finally:
        workspace.close()
    assert values == ["0 */5 * * * ?"], values


def test_a_simple_chain_is_its_text(analyzed: Path):
    """A schedule that is not `cronSchedule(String)` is its builder chain as written
    (ruling 4), a nested builder argument and javac's boxed weekday constants included."""
    [simple] = _entries_in(analyzed, "QuartzConfig#sweepEvery30s")
    assert (simple["trigger"], simple["name"], simple["expression"], simple["resolution"]) == (
        "simple",
        "orders.every30s",
        "simpleSchedule().withIntervalInSeconds(30).repeatForever()",
        "resolved",
    )
    [daily] = _entries_in(analyzed, "QuartzConfig#officeHours")
    assert (daily["trigger"], daily["expression"], daily["resolution"]) == (
        "dailyTimeInterval",
        (
            "dailyTimeIntervalSchedule().onDaysOfTheWeek(3, 5)"
            ".startingDailyAt(TimeOfDay.hourAndMinuteOfDay(9, 0)).withIntervalInHours(1)"
        ),
        "resolved",
    )


@pytest.mark.pins("quartz.KIND-from-the-declared-return-type")
def test_the_kind_comes_from_a_helpers_declared_return_type(analyzed: Path):
    """`createJob` hands `withSchedule` the result of `misfire(row, builder)`, whose body
    branches between two calls on its parameter: the walk ends there, before any root. The
    helper is DECLARED to return `CronScheduleBuilder`, which the compiler wrote, so the kind
    is `cron` whatever the body does; the expression is not in the code."""
    [row] = _entries_in(analyzed, "RowScheduler#createJob")
    assert (row["trigger"], row["name"], row["expression"], row["resolution"]) == (
        "cron",
        None,
        None,
        "partial",
    )


@pytest.mark.pins("quartz.a-runtime-cron-is-PARTIAL-not-dropped")
def test_a_cron_from_a_row_getter_is_partial_with_its_source(analyzed: Path):
    """`register` reads `row.getCron()` and hands it to `buildTrigger(cron)`, which calls
    `cronSchedule(cron)`: the walk crosses the parameter and stops at the getter, whose value
    is a runtime row's (ruling 2). The entry stays, `partial`, naming the getter."""
    [row] = _entries_in(analyzed, "TriggerFactory#buildTrigger")
    assert (row["trigger"], row["expression"], row["resolution"]) == ("cron", None, "partial")
    assert "OrderJobRow#getCron(" in str(row["expression_source"]), row


# --- hand-built facts: the two shapes the fixture does not hold ---------------------------


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/jobs/Triggers.java",
        module_id="com.acme:jobs",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _site(
    caller: str,
    ordinal: int,
    owner: str,
    name: str,
    descriptor: str,
    *,
    receiver: int | None = None,
    result: int | None = None,
    arguments: tuple[CallArgument, ...] = (),
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind="static" if receiver is None else "virtual",
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=list(arguments),
    )


def _cron_trigger(caller: str, *identity: str) -> list[CallSiteFact]:
    """`newTrigger()[.withIdentity(…identity)].withSchedule(cronSchedule("0 0 * * * ?"))
    .build()` in `caller`, as javac emits it."""
    builder = "Lorg/quartz/TriggerBuilder;"
    sites = [_site(caller, 0, TRIGGER_BUILDER, "newTrigger", f"(){builder}", result=1)]
    current = 1
    if identity:
        strings = "Ljava/lang/String;" * len(identity)
        sites.append(
            _site(
                caller,
                1,
                TRIGGER_BUILDER,
                "withIdentity",
                f"({strings}){builder}",
                receiver=current,
                result=2,
                arguments=tuple(CallArgument(kind="string", value=part) for part in identity),
            )
        )
        current = 2
    sites += [
        _site(
            caller,
            2,
            CRON_BUILDER,
            "cronSchedule",
            "(Ljava/lang/String;)Lorg/quartz/CronScheduleBuilder;",
            result=3,
            arguments=(CallArgument(kind="string", value="0 0 * * * ?"),),
        ),
        _site(
            caller,
            3,
            TRIGGER_BUILDER,
            "withSchedule",
            f"(Lorg/quartz/ScheduleBuilder;){builder}",
            receiver=current,
            result=4,
            arguments=(CallArgument(kind="unresolved", source=3),),
        ),
        _site(caller, 4, TRIGGER_BUILDER, "build", "()Lorg/quartz/Trigger;", receiver=4, result=5),
    ]
    return sites


def _scheduled(tmp_path: Path, facts: list[CallSiteFact]) -> list[dict]:
    write_fact_file(tmp_path / "facts" / "Triggers.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace.load_facts(tmp_path / "facts")
        record_return_flows(workspace)
        record_call_edges(workspace)
        skipped = derive_endpoints(workspace, [_quartz(_catalogs())], capabilities=CAPABILITIES)
        assert skipped == []
        return workspace.query("scheduled_work")
    finally:
        workspace.close()


def test_a_name_without_a_group_takes_the_default_group(tmp_path: Path):
    """`withIdentity("x")`: Quartz's `Key` puts a key with no group in `DEFAULT` (CP-55 rows
    10-18), and the name is written `group.name`."""
    [row] = _scheduled(tmp_path, _cron_trigger("com/acme/jobs/Triggers#hourly().", "x"))
    assert (row["name"], row["trigger"], row["expression"]) == ("DEFAULT.x", "cron", "0 0 * * * ?")


def test_two_unnamed_triggers_are_two_rows(tmp_path: Path):
    """Two `newTrigger()` chains with the same schedule and no name are two triggers (ruling
    3), even with every column equal: nothing collapses them."""
    rows = _scheduled(
        tmp_path,
        _cron_trigger("com/acme/jobs/Triggers#first().")
        + _cron_trigger("com/acme/jobs/Triggers#second()."),
    )
    assert [(row["name"], row["trigger"], row["expression"]) for row in rows] == [
        (None, "cron", "0 0 * * * ?"),
        (None, "cron", "0 0 * * * ?"),
    ]
