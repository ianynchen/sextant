"""Tests for the `scheduled_chain` engine (D02 §2's `scheduled_chain` style; Quartz spec
2026-10-28 §3a, §3b): one `scheduled_work` entry per `newTrigger()` root, with its kind,
its name and its schedule.

Most read `fixtures/orders-quartz`, analysed once through `module analyze`, because the
shapes that matter cross methods — a cron from a getter two calls away, a schedule builder
handed through a helper — and the value walk is what crosses them. The two shapes the
fixture does not hold (a name with no group, two identical unnamed triggers) are hand-built
facts in the `test_call_engines.py` style. The job a trigger runs is found from whatever
pairs them (§3c): `forJob(...)` on the chain, or a `scheduleJob(job, trigger)` the value walk
reaches, and the handler is the body the JVM's dispatch rule picks for the job class.
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
from sextant.application.resolve.values import producers_of, value_index
from sextant.cli.app import cli
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    MethodReturnFact,
    SymbolFact,
)
from sextant.domain.symbols import method_descriptor
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
    are no triggers. Every one names its job, so every one has a handler (re-pinned
    2026-10-29, Task 10: the handler was NULL before the job was looked for)."""
    rows = [
        row
        for method in ("sweepEvery30s", "sweepNightly", "auditTrigger", "officeHours")
        for row in _entries_in(analyzed, f"QuartzConfig#{method}")
    ]
    assert len(rows) == 4, rows
    assert {row["trigger"] for row in rows} == {"simple", "cron", "dailyTimeInterval"}
    assert all(row["handler"] is not None and row["catalog_id"] == "quartz" for row in rows)
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


@pytest.mark.pins("values.a-branch-of-calls-on-one-receiver-passes-through")
def test_a_builder_through_a_branching_helper_is_followed_to_its_root(analyzed: Path):
    """The RuoYi shape. `createJob` hands `withSchedule` the result of `misfire(row,
    builder)`, whose body branches between two calls on its parameter. Both branches are
    builder calls on ONE receiver, so the chain reader passes through to it, in the calling
    context it came through, and reaches `cronSchedule(row.getCron())`: `cron`, read at
    runtime from the getter (re-pinned 2026-10-29, fix round 1: it stopped at the branch and
    named no source)."""
    [row] = _entries_in(analyzed, "RowScheduler#createJob")
    assert (row["trigger"], row["name"], row["expression"], row["resolution"]) == (
        "cron",
        None,
        None,
        "partial",
    )
    assert "OrderJobRow#getCron(" in str(row["expression_source"]), row


@pytest.mark.pins("values.a-passed-through-branch-keeps-its-calling-context")
def test_a_passed_through_branch_stays_in_its_calling_context(analyzed: Path):
    """`misfire` is called from `createJob` AND from `updateJob`, each with its own
    `cronSchedule(row.getCron())`. Walked from `createJob`'s trigger, its parameter is the
    argument at `createJob`'s call alone: the chain is `createJob`'s `cronSchedule`, never
    `updateJob`'s rebuilt trigger's."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        index = value_index(workspace)
        [with_schedule] = [
            site
            for (caller, _), site in index.sites.items()
            if "/RowScheduler#createJob(" in caller and site["name"] == "withSchedule"
        ]
        builders = {
            (str(site["owner"]), str(site["name"]))
            for site in index.sites.values()
            if site["owner"] == CRON_BUILDER
        }
        producers = producers_of(index, with_schedule, 0, builders, along_receivers=True)
    finally:
        workspace.close()
    assert [
        [(caller.split("/")[-1].split("(")[0], ordinal) for caller, ordinal in p.chain]
        for p in producers
    ] == [[("RowScheduler#createJob", 7)]]
    assert producers[0].rooted and producers[0].inexact


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


_MODULE = "sextant-jvm maven com.acme/jobs 1.0.0 "
_TRIGGERS = "com/acme/jobs/Triggers#"
_SIMPLE = "org/quartz/SimpleScheduleBuilder#"
_SIMPLE_TYPE = "Lorg/quartz/SimpleScheduleBuilder;"
_TRIGGER_TYPE = "Lorg/quartz/TriggerBuilder;"


def _method_symbol(name: str, jvm: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + method_descriptor(_TRIGGERS, name, jvm),
        construct_kind="method",
        enclosing=_MODULE + _TRIGGERS,
    )


def _scheduled_with(caller: str, builder: list, schedule_source: int) -> list:
    """`newTrigger().withSchedule(<value schedule_source>).build()` in `caller`, after the
    `builder` sites that make the schedule (ordinals 1.., values 2..)."""
    return [
        _site(caller, 0, TRIGGER_BUILDER, "newTrigger", f"(){_TRIGGER_TYPE}", result=1),
        *builder,
        _site(
            caller,
            20,
            TRIGGER_BUILDER,
            "withSchedule",
            f"(Lorg/quartz/ScheduleBuilder;){_TRIGGER_TYPE}",
            receiver=1,
            result=21,
            arguments=(CallArgument(kind="unresolved", source=schedule_source),),
        ),
        _site(
            caller, 21, TRIGGER_BUILDER, "build", "()Lorg/quartz/Trigger;", receiver=21, result=22
        ),
    ]


def test_a_builder_chain_continued_on_a_helpers_parameter_is_written_whole(tmp_path: Path):
    """`withSchedule(forever(simpleSchedule().withIntervalInSeconds(30)))` with `forever(b)`
    returning `b.repeatForever()`: the chain's last call is on the helper's PARAMETER, so its
    root is in the caller. The reader continues through that receiver in the calling context
    and the chain is written whole, across the two methods. Nothing pairs the trigger with a
    job, so the row is `partial` (§3a: `resolved` needs the handler too; re-pinned 2026-10-29,
    Task 10)."""
    forever_jvm = f"({_SIMPLE_TYPE}){_SIMPLE_TYPE}"
    helper = _MODULE + method_descriptor(_TRIGGERS, "forever", forever_jvm)
    caller = _MODULE + method_descriptor(_TRIGGERS, "every30s", "()Lorg/quartz/Trigger;")
    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + _TRIGGERS, construct_kind="class"),
        _method_symbol("forever", forever_jvm),
        _method_symbol("every30s", "()Lorg/quartz/Trigger;"),
        CallSiteFact(
            document_id="doc_1",
            caller=helper,
            target=CallTarget(owner=_SIMPLE, name="repeatForever", descriptor=f"(){_SIMPLE_TYPE}"),
            invoke_kind="virtual",
            ordinal=0,
            receiver_parameter=0,
            result=2,
        ),
        MethodReturnFact(
            document_id="doc_1",
            method=helper,
            ordinal=0,
            value=CallArgument(kind="unresolved", source=2),
        ),
        *_scheduled_with(
            caller,
            [
                _site(caller, 1, _SIMPLE, "simpleSchedule", f"(){_SIMPLE_TYPE}", result=3),
                _site(
                    caller,
                    2,
                    _SIMPLE,
                    "withIntervalInSeconds",
                    f"(I){_SIMPLE_TYPE}",
                    receiver=3,
                    result=4,
                    arguments=(CallArgument(kind="int", value=30),),
                ),
                _site(
                    caller,
                    3,
                    _TRIGGERS,
                    "forever",
                    forever_jvm,
                    result=5,
                    arguments=(CallArgument(kind="unresolved", source=4),),
                ),
            ],
            schedule_source=5,
        ),
    ]
    [row] = _scheduled(tmp_path, facts)
    assert (row["trigger"], row["expression"], row["resolution"]) == (
        "simple",
        "simpleSchedule().withIntervalInSeconds(30).repeatForever()",
        "partial",
    )
    assert row["handler"] is None


@pytest.mark.pins("quartz.KIND-from-the-declared-return-type")
def test_the_kind_comes_from_a_helpers_declared_return_type(tmp_path: Path):
    """The dolphinscheduler shape: the schedule builder comes from a factory in a jar
    (`Schedules.nightly()`), whose body is not read, so the walk reaches no builder call. The
    factory is DECLARED to return `CronScheduleBuilder`, which the compiler wrote, so the kind
    is `cron` whatever it does inside; the expression is not in the code."""
    caller = "com/acme/jobs/Triggers#nightly()."
    facts = _scheduled_with(
        caller,
        [
            _site(
                caller,
                1,
                "com/vendor/Schedules#",
                "nightly",
                "()Lorg/quartz/CronScheduleBuilder;",
                result=3,
            )
        ],
        schedule_source=3,
    )
    [row] = _scheduled(tmp_path, facts)
    assert (row["trigger"], row["expression"], row["resolution"]) == ("cron", None, "partial")


# --- the job and its handler (§3c) ---------------------------------------------------------


def _handler_of(row: dict) -> str | None:
    """A handler as `Class#method`, or None for a NULL one."""
    handler = row["handler"]
    return None if handler is None else str(handler).split("/")[-1].split("(")[0]


def test_forJob_by_name_and_group_finds_the_job(analyzed: Path):
    """`forJob("sweep", "orders")` names the `JobBuilder` chain whose `withIdentity` is
    `orders.sweep`, in another method: both `sweep` triggers run `SweepJob`, a
    `QuartzJobBean`, whose handler is its `executeInternal`."""
    rows = [
        row
        for method in ("sweepEvery30s", "sweepNightly")
        for row in _entries_in(analyzed, f"QuartzConfig#{method}")
    ]
    assert [(_handler_of(row), row["resolution"]) for row in rows] == [
        ("SweepJob#executeInternal", "resolved"),
        ("SweepJob#executeInternal", "resolved"),
    ]


def test_forJob_by_detail_follows_the_bean_reference(analyzed: Path):
    """`auditTrigger(JobDetail auditDetail, …)` is a `@Bean` method, so Spring injects its
    parameter: of the two `@Bean JobDetail`s, the one named like the parameter
    (`auditDetail`), as the container picks it. Its chain is `newJob(AuditJob.class)`; the
    configured cron keeps the row `unresolved`."""
    [row] = _entries_in(analyzed, "QuartzConfig#auditTrigger")
    assert (_handler_of(row), row["resolution"]) == ("AuditJob#execute", "unresolved")


def test_scheduleJob_pairs_across_a_returned_trigger(analyzed: Path):
    """The ruoyi-vue-pro shape: `buildTrigger` returns the trigger, and `register` hands it
    to `scheduleJob(newJob(AuditJob.class).build(), …)`. The value walk pairs them across
    the return; the cron is read off a row, so the row is `partial`."""
    [row] = _entries_in(analyzed, "TriggerFactory#buildTrigger")
    assert (_handler_of(row), row["resolution"]) == ("AuditJob#execute", "partial")


@pytest.mark.pins("quartz.equal-HANDLERS-collapse")
def test_a_ternary_job_class_with_one_inherited_body_is_one_row(analyzed: Path):
    """The RuoYi shape: `newJob(jobClass(row))`, `jobClass` returning `concurrent ?
    ConcurrentRowJob.class : SerialRowJob.class`. The walk answers both, `narrowed`; both
    inherit `BaseRowJob.execute`, so the one body is one row, at its own resolution."""
    [row] = _entries_in(analyzed, "RowScheduler#createJob")
    assert (_handler_of(row), row["trigger"], row["resolution"]) == (
        "BaseRowJob#execute",
        "cron",
        "partial",
    )


def test_an_accessor_called_on_the_built_job_keeps_its_job(analyzed: Path):
    """The line RuoYi, NBlog and aurora all write between `build()` and `scheduleJob`:
    `detail.getJobDataMap().put("row", row)`. `getJobDataMap()` is a call ON the built
    `JobDetail`, but it hands back another object and takes nothing, so it does not change
    which call built the detail: the job, and its handler, are still found."""
    workspace = DuckDbWorkspace(analyzed)
    try:
        accessed = [
            site
            for site in workspace.query("call_sites")
            if "/RowScheduler#createJob(" in str(site["caller"]) and site["name"] == "getJobDataMap"
        ]
    finally:
        workspace.close()
    assert len(accessed) == 1, "the fixture must call the accessor on the built detail"
    [row] = _entries_in(analyzed, "RowScheduler#createJob")
    assert _handler_of(row) == "BaseRowJob#execute"


def test_a_set_built_in_a_jar_leaves_the_handler_null(analyzed: Path):
    """The dolphinscheduler shape: `scheduleJob(job, Set.of(trigger), true)`. The set is
    made in the JDK, so the walk from the consumer answers `external` and reaches no
    trigger: the job is not found, the row is `partial`, and it starts no trace."""
    [row] = _entries_in(analyzed, "TriggerMaker#make")
    assert (row["handler"], row["trigger"], row["resolution"]) == (None, "cron", "partial")
    workspace = DuckDbWorkspace(analyzed)
    try:
        scheduled = [row for row in workspace.query("scheduled_work")]
        roots = {
            str(root["handler"])
            for root in workspace.query("roots")
            if root["root_kind"] == "scheduled"
        }
    finally:
        workspace.close()
    assert roots == {str(row["handler"]) for row in scheduled if row["handler"] is not None}


# Hand-built job classes and chains, for the shapes the fixture does not hold.
_JOBS = "com/acme/jobs/"
JOB_BUILDER = "org/quartz/JobBuilder#"
_JOB_BUILDER_TYPE = "Lorg/quartz/JobBuilder;"
_EXECUTE = "(Lorg/quartz/JobExecutionContext;)V"
_QUARTZ_JOB_BEAN = "org/springframework/scheduling/quartz/QuartzJobBean#"


def _job_class(
    name: str,
    *,
    superclass: str | None = None,
    interfaces: tuple[str, ...] = (),
    declares: tuple[str, ...] = (),
) -> list:
    """A job class `com/acme/jobs/<name>`, with a body for each method in `declares`
    (each taking a `JobExecutionContext`)."""
    owner = f"{_JOBS}{name}#"
    facts: list = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + owner,
            construct_kind="class",
            superclass=superclass,
            interfaces=list(interfaces),
        )
    ]
    for method in declares:
        symbol = _MODULE + method_descriptor(owner, method, _EXECUTE)
        facts += [
            SymbolFact(
                document_id="doc_1",
                symbol=symbol,
                construct_kind="method",
                enclosing=_MODULE + owner,
            ),
            MethodReturnFact(document_id="doc_1", method=symbol, ordinal=0, value=None),
        ]
    return facts


def _job_chain(caller: str, job: str, *identity: str) -> list[CallSiteFact]:
    """`newJob(<job>.class)[.withIdentity(…identity)].build()` in `caller`, its result
    value 3."""
    sites = [
        _site(
            caller,
            0,
            JOB_BUILDER,
            "newJob",
            f"(Ljava/lang/Class;){_JOB_BUILDER_TYPE}",
            result=1,
            arguments=(CallArgument(kind="class", symbol=f"{_JOBS}{job}#"),),
        )
    ]
    current = 1
    if identity:
        sites.append(
            _site(
                caller,
                1,
                JOB_BUILDER,
                "withIdentity",
                f"({'Ljava/lang/String;' * len(identity)}){_JOB_BUILDER_TYPE}",
                receiver=1,
                result=2,
                arguments=tuple(CallArgument(kind="string", value=part) for part in identity),
            )
        )
        current = 2
    sites.append(
        _site(
            caller, 2, JOB_BUILDER, "build", "()Lorg/quartz/JobDetail;", receiver=current, result=3
        )
    )
    return sites


def _trigger_for_job(caller: str, *key: str) -> list[CallSiteFact]:
    """`newTrigger().forJob(…key).withSchedule(cronSchedule("0 0 * * * ?")).build()`."""
    builder = "Lorg/quartz/TriggerBuilder;"
    return [
        _site(caller, 0, TRIGGER_BUILDER, "newTrigger", f"(){builder}", result=1),
        _site(
            caller,
            1,
            TRIGGER_BUILDER,
            "forJob",
            f"({'Ljava/lang/String;' * len(key)}){builder}",
            receiver=1,
            result=2,
            arguments=tuple(CallArgument(kind="string", value=part) for part in key),
        ),
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
            receiver=2,
            result=4,
            arguments=(CallArgument(kind="unresolved", source=3),),
        ),
        _site(caller, 4, TRIGGER_BUILDER, "build", "()Lorg/quartz/Trigger;", receiver=4, result=5),
    ]


@pytest.mark.pins("quartz.forJob-DEFAULT-group-only")
def test_forJob_by_name_alone_uses_the_default_group_only(tmp_path: Path):
    """`forJob("x")` is `JobKey("x", DEFAULT)` (Quartz's `Key`): it names the job written
    `withIdentity("x")`, and not the one written `withIdentity("x", "other")`, whose key is
    another."""
    job = ("org/quartz/Job#",)
    facts = [
        *_job_class("OtherJob", interfaces=job, declares=("execute",)),
        *_job_class("DefaultJob", interfaces=job, declares=("execute",)),
        *_job_chain(f"{_JOBS}Jobs#other().", "OtherJob", "x", "other"),
        *_job_chain(f"{_JOBS}Jobs#plain().", "DefaultJob", "x"),
        *_trigger_for_job(f"{_JOBS}Triggers#hourly().", "x"),
    ]
    [row] = _scheduled(tmp_path, facts)
    assert (_handler_of(row), row["resolution"]) == ("DefaultJob#execute", "resolved")


@pytest.mark.pins("quartz.different-BODIES-are-narrowed")
def test_a_ternary_job_class_with_two_bodies_is_a_row_each_narrowed(tmp_path: Path):
    """`newJob(c ? FastJob.class : SlowJob.class)`, each class with its own `execute`: one
    of the two runs and which is not known, so each body is a row, `narrowed` (§3c)."""
    job = ("org/quartz/Job#",)
    caller = f"{_JOBS}Jobs#either()."
    chain = _job_chain(caller, "FastJob", "x", "g")
    chain[0] = _site(
        caller,
        0,
        JOB_BUILDER,
        "newJob",
        f"(Ljava/lang/Class;){_JOB_BUILDER_TYPE}",
        result=1,
        arguments=(
            CallArgument(
                kind="merge",
                candidates=[
                    CallArgument(kind="class", symbol=f"{_JOBS}FastJob#"),
                    CallArgument(kind="class", symbol=f"{_JOBS}SlowJob#"),
                ],
            ),
        ),
    )
    facts = [
        *_job_class("FastJob", interfaces=job, declares=("execute",)),
        *_job_class("SlowJob", interfaces=job, declares=("execute",)),
        *chain,
        *_trigger_for_job(f"{_JOBS}Triggers#hourly().", "x", "g"),
    ]
    rows = _scheduled(tmp_path, facts)
    assert [(_handler_of(row), row["resolution"]) for row in rows] == [
        ("FastJob#execute", "narrowed"),
        ("SlowJob#execute", "narrowed"),
    ]


def test_forJob_by_JobKey_reads_the_key_it_is_built_from(tmp_path: Path):
    """`forJob(JobKey.jobKey("x", "g"))`: the walk from the argument reaches the call that
    built the key (the catalog's `job_key`), whose name and group are the job's key."""
    job = ("org/quartz/Job#",)
    caller = f"{_JOBS}Triggers#hourly()."
    builder = "Lorg/quartz/TriggerBuilder;"
    sites = _trigger_for_job(caller, "x", "g")
    sites[1] = _site(
        caller,
        1,
        TRIGGER_BUILDER,
        "forJob",
        f"(Lorg/quartz/JobKey;){builder}",
        receiver=1,
        result=2,
        arguments=(CallArgument(kind="unresolved", source=9),),
    )
    key = _site(
        caller,
        0,
        "org/quartz/JobKey#",
        "jobKey",
        "(Ljava/lang/String;Ljava/lang/String;)Lorg/quartz/JobKey;",
        result=9,
        arguments=(CallArgument(kind="string", value="x"), CallArgument(kind="string", value="g")),
    )
    sites = [key, *(site.model_copy(update={"ordinal": site.ordinal + 1}) for site in sites)]
    facts = [
        *_job_class("KeyedJob", interfaces=job, declares=("execute",)),
        *_job_chain(f"{_JOBS}Jobs#keyed().", "KeyedJob", "x", "g"),
        *sites,
    ]
    [row] = _scheduled(tmp_path, facts)
    assert (_handler_of(row), row["resolution"]) == ("KeyedJob#execute", "resolved")


@pytest.mark.pins("quartz.several-PATHS-are-exact")
def test_classes_from_several_callers_are_a_row_each_resolved(tmp_path: Path):
    """`addJob(Class c)` holds `newJob(c)` and `scheduleJob(job, trigger)`, and `first()`
    and `second()` call it with `AJob.class` and `BJob.class`. Two callers are two paths,
    each exact (§3c's "several paths"): a row per class, each `resolved` — not `narrowed`,
    and not collapsed into one."""
    job = ("org/quartz/Job#",)
    add_jvm = "(Ljava/lang/Class;)V"
    add_job = _MODULE + method_descriptor(_TRIGGERS, "addJob", add_jvm)
    schedule_jvm = "(Lorg/quartz/JobDetail;Lorg/quartz/Trigger;)Ljava/util/Date;"

    def caller(name: str, job_class: str) -> list:
        symbol = _MODULE + method_descriptor(_TRIGGERS, name, "()V")
        return [
            _method_symbol(name, "()V"),
            _site(
                symbol,
                0,
                _TRIGGERS,
                "addJob",
                add_jvm,
                arguments=(CallArgument(kind="class", symbol=f"{_JOBS}{job_class}#"),),
            ),
        ]

    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + _TRIGGERS, construct_kind="class"),
        *_job_class("AJob", interfaces=job, declares=("execute",)),
        *_job_class("BJob", interfaces=job, declares=("execute",)),
        _method_symbol("addJob", add_jvm),
        *_cron_trigger(add_job),
        _site(
            add_job,
            10,
            JOB_BUILDER,
            "newJob",
            f"(Ljava/lang/Class;){_JOB_BUILDER_TYPE}",
            result=10,
            arguments=(CallArgument(kind="parameter", value=0),),
        ),
        _site(
            add_job, 11, JOB_BUILDER, "build", "()Lorg/quartz/JobDetail;", receiver=10, result=11
        ),
        _site(
            add_job,
            12,
            "org/quartz/Scheduler#",
            "scheduleJob",
            schedule_jvm,
            receiver=20,
            result=12,
            arguments=(
                CallArgument(kind="unresolved", source=11),
                CallArgument(kind="unresolved", source=5),
            ),
        ),
        MethodReturnFact(document_id="doc_1", method=add_job, ordinal=0, value=None),
        *caller("first", "AJob"),
        *caller("second", "BJob"),
    ]
    rows = _scheduled(tmp_path, facts)
    assert [(_handler_of(row), row["resolution"]) for row in rows] == [
        ("AJob#execute", "resolved"),
        ("BJob#execute", "resolved"),
    ]


def test_a_branched_job_class_with_a_placeholder_cron_is_partial(tmp_path: Path):
    """`newJob(c ? FastJob.class : SlowJob.class)`, two bodies, with a `${…}` cron: two
    gaps at once — which body runs, and the configured value — so neither `narrowed` nor
    `unresolved` says it alone: `partial` (§3a)."""
    job = ("org/quartz/Job#",)
    caller = f"{_JOBS}Jobs#either()."
    chain = _job_chain(caller, "FastJob", "x", "g")
    chain[0] = chain[0].model_copy(
        update={
            "arguments": [
                CallArgument(
                    kind="merge",
                    candidates=[
                        CallArgument(kind="class", symbol=f"{_JOBS}FastJob#"),
                        CallArgument(kind="class", symbol=f"{_JOBS}SlowJob#"),
                    ],
                )
            ]
        }
    )
    trigger = _trigger_for_job(f"{_JOBS}Triggers#hourly().", "x", "g")
    trigger[2] = trigger[2].model_copy(
        update={"arguments": [CallArgument(kind="string", value="${jobs.cron}")]}
    )
    facts = [
        *_job_class("FastJob", interfaces=job, declares=("execute",)),
        *_job_class("SlowJob", interfaces=job, declares=("execute",)),
        *chain,
        *trigger,
    ]
    rows = _scheduled(tmp_path, facts)
    assert [(_handler_of(row), row["expression"], row["resolution"]) for row in rows] == [
        ("FastJob#execute", "${jobs.cron}", "partial"),
        ("SlowJob#execute", "${jobs.cron}", "partial"),
    ]


@pytest.mark.pins("quartz.QUARTZJOBBEAN-runs-executeInternal")
def test_QuartzJobBean_runs_executeInternal(tmp_path: Path):
    """A job extending Spring's `QuartzJobBean` declares no `execute`: the JVM runs the
    one `QuartzJobBean` has, in a jar, which calls the subclass's `executeInternal` (the
    catalog's `supertype_dispatch`). That is the handler."""
    facts = [
        *_job_class("BeanJob", superclass=_QUARTZ_JOB_BEAN, declares=("executeInternal",)),
        *_job_chain(f"{_JOBS}Jobs#bean().", "BeanJob", "x", "g"),
        *_trigger_for_job(f"{_JOBS}Triggers#hourly().", "x", "g"),
    ]
    [row] = _scheduled(tmp_path, facts)
    assert (_handler_of(row), row["resolution"]) == ("BeanJob#executeInternal", "resolved")


@pytest.mark.pins("quartz.a-JAR-base-gives-NO-handler")
def test_another_jar_base_class_gives_no_handler(tmp_path: Path):
    """The same class on any OTHER jar base: what that base's `execute` does is not
    known, so the job's own `executeInternal` is not assumed to run. Handler NULL,
    `partial`."""
    facts = [
        *_job_class("VendorJob", superclass="com/vendor/BaseJob#", declares=("executeInternal",)),
        *_job_chain(f"{_JOBS}Jobs#vendor().", "VendorJob", "x", "g"),
        *_trigger_for_job(f"{_JOBS}Triggers#hourly().", "x", "g"),
    ]
    [row] = _scheduled(tmp_path, facts)
    assert (row["handler"], row["trigger"], row["resolution"]) == (None, "cron", "partial")


def test_a_trigger_reaching_two_consumers_is_one_entry(tmp_path: Path):
    """`trigger()` builds and returns one trigger, and `first()` and `second()` each hand
    it to `scheduleJob(newJob(AJob.class).build(), trigger())`: one `newTrigger()`, so one
    entry (ruling 3), its job found through both consumers alike."""
    trigger_jvm = "()Lorg/quartz/Trigger;"
    helper = _MODULE + method_descriptor(_TRIGGERS, "trigger", trigger_jvm)
    scheduler = "org/quartz/Scheduler#"
    schedule_jvm = "(Lorg/quartz/JobDetail;Lorg/quartz/Trigger;)Ljava/util/Date;"

    def consumer(name: str) -> list:
        caller = _MODULE + method_descriptor(_TRIGGERS, name, "()V")
        return [
            _method_symbol(name, "()V"),
            *_job_chain(caller, "AJob"),
            _site(caller, 3, _TRIGGERS, "trigger", trigger_jvm, result=4),
            _site(
                caller,
                4,
                scheduler,
                "scheduleJob",
                schedule_jvm,
                receiver=9,
                result=5,
                arguments=(
                    CallArgument(kind="unresolved", source=3),
                    CallArgument(kind="unresolved", source=4),
                ),
            ),
        ]

    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + _TRIGGERS, construct_kind="class"),
        *_job_class("AJob", interfaces=("org/quartz/Job#",), declares=("execute",)),
        _method_symbol("trigger", trigger_jvm),
        *_cron_trigger(helper),
        MethodReturnFact(
            document_id="doc_1",
            method=helper,
            ordinal=0,
            value=CallArgument(kind="unresolved", source=5),
        ),
        *consumer("first"),
        *consumer("second"),
    ]
    rows = _scheduled(tmp_path, facts)
    assert [(_handler_of(row), row["expression"], row["resolution"]) for row in rows] == [
        ("AJob#execute", "0 0 * * * ?", "resolved")
    ]


# --- the final review's fix wave (2026-10-29) ------------------------------------------------


def _add_job_facts(add_jvm: str, cron: CallArgument, calls: dict[str, tuple]) -> list:
    """`addJob(...)` holding `newTrigger().withSchedule(cronSchedule(<cron>)).build()`,
    `newJob(<parameter 0>).build()` and `scheduleJob(job, trigger)`, called from each
    method in `calls` with that call's arguments."""
    job = ("org/quartz/Job#",)
    add_job = _MODULE + method_descriptor(_TRIGGERS, "addJob", add_jvm)
    schedule_jvm = "(Lorg/quartz/JobDetail;Lorg/quartz/Trigger;)Ljava/util/Date;"
    trigger = _cron_trigger(add_job)
    trigger[1] = trigger[1].model_copy(update={"arguments": [cron]})
    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + _TRIGGERS, construct_kind="class"),
        *_job_class("AJob", interfaces=job, declares=("execute",)),
        *_job_class("BJob", interfaces=job, declares=("execute",)),
        _method_symbol("addJob", add_jvm),
        *trigger,
        _site(
            add_job,
            10,
            JOB_BUILDER,
            "newJob",
            f"(Ljava/lang/Class;){_JOB_BUILDER_TYPE}",
            result=10,
            arguments=(CallArgument(kind="parameter", value=0),),
        ),
        _site(
            add_job, 11, JOB_BUILDER, "build", "()Lorg/quartz/JobDetail;", receiver=10, result=11
        ),
        _site(
            add_job,
            12,
            "org/quartz/Scheduler#",
            "scheduleJob",
            schedule_jvm,
            receiver=20,
            result=12,
            arguments=(
                CallArgument(kind="unresolved", source=11),
                CallArgument(kind="unresolved", source=5),
            ),
        ),
        MethodReturnFact(document_id="doc_1", method=add_job, ordinal=0, value=None),
    ]
    for name, arguments in calls.items():
        symbol = _MODULE + method_descriptor(_TRIGGERS, name, "()V")
        facts += [
            _method_symbol(name, "()V"),
            _site(symbol, 0, _TRIGGERS, "addJob", add_jvm, arguments=arguments),
        ]
    return facts


@pytest.mark.pins("quartz.one-PATH-ties-the-cron-to-its-job")
def test_a_shared_helpers_cron_and_class_stay_on_their_own_path(tmp_path: Path):
    """The `QuartzManager.addJob(jobClass, cron)` helper: `first()` passes `(AJob.class,
    "0 0 1 * * ?")` and `second()` passes `(BJob.class, "0 0 2 * * ?")`. The cron and the
    class are read TOGETHER on each path, so each caller's cron stays with its own job:
    two rows, each `resolved` — never AJob at 2am or BJob at 1am (final review, Critical
    1: four `resolved` rows, two of them false)."""

    def call(job_class: str, cron: str) -> tuple:
        return (
            CallArgument(kind="class", symbol=f"{_JOBS}{job_class}#"),
            CallArgument(kind="string", value=cron),
        )

    facts = _add_job_facts(
        "(Ljava/lang/Class;Ljava/lang/String;)V",
        CallArgument(kind="parameter", value=1),
        {"first": call("AJob", "0 0 1 * * ?"), "second": call("BJob", "0 0 2 * * ?")},
    )
    rows = _scheduled(tmp_path, facts)
    assert [(_handler_of(row), row["expression"], row["resolution"]) for row in rows] == [
        ("AJob#execute", "0 0 1 * * ?", "resolved"),
        ("BJob#execute", "0 0 2 * * ?", "resolved"),
    ]


@pytest.mark.pins("quartz.a-row-is-RESOLVED-only-from-one-binding")
def test_a_trigger_returned_to_each_caller_keeps_that_callers_cron(tmp_path: Path):
    """`trigger(cron)` builds and returns a trigger; `first()` hands
    `scheduleJob(newJob(AJob.class).build(), trigger("0 0 1 * * ?"))` and `second()` the
    same with `BJob` and `"0 0 2 * * ?"`. The cron is read on the path the trigger took to
    each `scheduleJob` — back out of `trigger()` into the caller that paired it — so each
    caller's cron stays with its own job: two rows, each `resolved` (second fix wave,
    R19: read apart, every cron reached every job)."""
    trigger_jvm = "(Ljava/lang/String;)Lorg/quartz/Trigger;"
    helper = _MODULE + method_descriptor(_TRIGGERS, "trigger", trigger_jvm)
    schedule_jvm = "(Lorg/quartz/JobDetail;Lorg/quartz/Trigger;)Ljava/util/Date;"
    trigger = _cron_trigger(helper)
    trigger[1] = trigger[1].model_copy(
        update={"arguments": [CallArgument(kind="parameter", value=0)]}
    )

    def consumer(name: str, job_class: str, cron: str) -> list:
        caller = _MODULE + method_descriptor(_TRIGGERS, name, "()V")
        return [
            _method_symbol(name, "()V"),
            *_job_chain(caller, job_class),
            _site(
                caller,
                3,
                _TRIGGERS,
                "trigger",
                trigger_jvm,
                result=4,
                arguments=(CallArgument(kind="string", value=cron),),
            ),
            _site(
                caller,
                4,
                "org/quartz/Scheduler#",
                "scheduleJob",
                schedule_jvm,
                receiver=9,
                result=5,
                arguments=(
                    CallArgument(kind="unresolved", source=3),
                    CallArgument(kind="unresolved", source=4),
                ),
            ),
        ]

    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + _TRIGGERS, construct_kind="class"),
        *_job_class("AJob", interfaces=("org/quartz/Job#",), declares=("execute",)),
        *_job_class("BJob", interfaces=("org/quartz/Job#",), declares=("execute",)),
        _method_symbol("trigger", trigger_jvm),
        *trigger,
        MethodReturnFact(
            document_id="doc_1",
            method=helper,
            ordinal=0,
            value=CallArgument(kind="unresolved", source=5),
        ),
        *consumer("first", "AJob", "0 0 1 * * ?"),
        *consumer("second", "BJob", "0 0 2 * * ?"),
    ]
    rows = _scheduled(tmp_path, facts)
    assert sorted((_handler_of(row), row["expression"], row["resolution"]) for row in rows) == [
        ("AJob#execute", "0 0 1 * * ?", "resolved"),
        ("BJob#execute", "0 0 2 * * ?", "resolved"),
    ]


@pytest.mark.pins("quartz.no-withSchedule-is-the-DEFAULT-schedule")
def test_a_trigger_with_no_schedule_fires_once(tmp_path: Path):
    """`newTrigger().withIdentity("x", "g").forJob("x", "g").startNow().build()`, Quartz's
    own first example: no `withSchedule`, so `TriggerBuilder.build()` uses
    `SimpleScheduleBuilder.simpleSchedule()` (fire once; CP-55's Quartz 2.5.1 bytecode).
    The trigger is an entry like any other (§3a): `simple`, `simpleSchedule()`."""
    caller = f"{_JOBS}Triggers#once()."
    builder = "Lorg/quartz/TriggerBuilder;"
    trigger = [
        _site(caller, 0, TRIGGER_BUILDER, "newTrigger", f"(){builder}", result=1),
        _site(
            caller,
            1,
            TRIGGER_BUILDER,
            "withIdentity",
            f"(Ljava/lang/String;Ljava/lang/String;){builder}",
            receiver=1,
            result=2,
            arguments=(
                CallArgument(kind="string", value="x"),
                CallArgument(kind="string", value="g"),
            ),
        ),
        _site(
            caller,
            2,
            TRIGGER_BUILDER,
            "forJob",
            f"(Ljava/lang/String;Ljava/lang/String;){builder}",
            receiver=2,
            result=3,
            arguments=(
                CallArgument(kind="string", value="x"),
                CallArgument(kind="string", value="g"),
            ),
        ),
        _site(caller, 3, TRIGGER_BUILDER, "startNow", f"(){builder}", receiver=3, result=4),
        _site(caller, 4, TRIGGER_BUILDER, "build", "()Lorg/quartz/Trigger;", receiver=4, result=5),
    ]
    facts = [
        *_job_class("OnceJob", interfaces=("org/quartz/Job#",), declares=("execute",)),
        *_job_chain(f"{_JOBS}Jobs#once().", "OnceJob", "x", "g"),
        *trigger,
    ]
    [row] = _scheduled(tmp_path, facts)
    assert (
        _handler_of(row),
        row["name"],
        row["trigger"],
        row["expression"],
        row["resolution"],
    ) == ("OnceJob#execute", "g.x", "simple", "simpleSchedule()", "resolved")


@pytest.mark.pins("quartz.a-call-ON-the-value-names-where-it-came-from")
def test_a_call_on_the_runtime_value_names_the_call_that_read_it(tmp_path: Path):
    """`cronSchedule(row.getCron().trim())`: `trim()` takes nothing and hands back its own
    receiver's type, so it is a call on the value, not where the value came from. The
    source named is `Row#getCron()`, the call that read it — never `String#trim()`."""
    caller = "com/acme/jobs/Triggers#hourly(Lcom/acme/jobs/Row;)."
    string = "()Ljava/lang/String;"
    sites = _cron_trigger(caller)
    sites[1] = sites[1].model_copy(
        update={"arguments": [CallArgument(kind="unresolved", source=8)]}
    )
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(owner="com/acme/jobs/Row#", name="getCron", descriptor=string),
            invoke_kind="virtual",
            ordinal=10,
            receiver_parameter=0,
            result=7,
        ),
        _site(caller, 11, "java/lang/String#", "trim", string, receiver=7, result=8),
        *sites,
    ]
    [row] = _scheduled(tmp_path, facts)
    assert (row["expression"], row["resolution"]) == (None, "partial")
    assert "Row#getCron(" in str(row["expression_source"]), row


@pytest.mark.pins("quartz.one-HANDLER-is-one-row-at-the-weaker-word")
def test_one_handler_found_exactly_and_through_a_branch_is_one_row(tmp_path: Path):
    """Two job chains share the key `g.x`: one is `newJob(AJob.class)`, the other
    `newJob(c ? AJob.class : BJob.class)`. `AJob#execute` is reached exactly on one path
    and as one of two on the other: one row for it, at the weaker word (`narrowed`), never
    a `resolved` row and a `narrowed` row for one body."""
    job = ("org/quartz/Job#",)
    branched = _job_chain(f"{_JOBS}Jobs#either().", "AJob", "x", "g")
    branched[0] = branched[0].model_copy(
        update={
            "arguments": [
                CallArgument(
                    kind="merge",
                    candidates=[
                        CallArgument(kind="class", symbol=f"{_JOBS}AJob#"),
                        CallArgument(kind="class", symbol=f"{_JOBS}BJob#"),
                    ],
                )
            ]
        }
    )
    facts = [
        *_job_class("AJob", interfaces=job, declares=("execute",)),
        *_job_class("BJob", interfaces=job, declares=("execute",)),
        *_job_chain(f"{_JOBS}Jobs#plain().", "AJob", "x", "g"),
        *branched,
        *_trigger_for_job(f"{_JOBS}Triggers#hourly().", "x", "g"),
    ]
    rows = _scheduled(tmp_path, facts)
    assert [(_handler_of(row), row["resolution"]) for row in rows] == [
        ("AJob#execute", "narrowed"),
        ("BJob#execute", "narrowed"),
    ]


# --- the second fix wave (R19, 2026-10-29): a row is `resolved` from ONE binding ------------

_SCHEDULE_JVM = "(Lorg/quartz/JobDetail;Lorg/quartz/Trigger;)Ljava/util/Date;"


@pytest.mark.pins("quartz.a-row-is-RESOLVED-only-from-one-binding")
def test_one_helper_paired_in_two_shapes_publishes_no_false_pairing(tmp_path: Path):
    """`trigger(cron)` returns a trigger. `pair(Class k, String cron)` calls
    `scheduleJob(newJob(k).build(), trigger(cron))` and `p1`/`p2` call `pair(AJob, "c1")`,
    `pair(BJob, "c2")`; separately `third()` calls `scheduleJob(newJob(CJob).build(),
    trigger("c3"))`. Each pairing's cron is read on the path its trigger took: A@c1, B@c2,
    C@c3, and none of the six other cells (the reviewer's probe: seven `resolved` rows,
    four false)."""
    trigger_jvm = "(Ljava/lang/String;)Lorg/quartz/Trigger;"
    helper = _MODULE + method_descriptor(_TRIGGERS, "trigger", trigger_jvm)
    trigger = _cron_trigger(helper)
    trigger[1] = trigger[1].model_copy(
        update={"arguments": [CallArgument(kind="parameter", value=0)]}
    )
    pair_jvm = "(Ljava/lang/Class;Ljava/lang/String;)V"
    pair = _MODULE + method_descriptor(_TRIGGERS, "pair", pair_jvm)

    def scheduled(caller: str, job: CallArgument, cron: CallArgument) -> list:
        return [
            _site(
                caller,
                0,
                JOB_BUILDER,
                "newJob",
                f"(Ljava/lang/Class;){_JOB_BUILDER_TYPE}",
                result=1,
                arguments=(job,),
            ),
            _site(
                caller, 2, JOB_BUILDER, "build", "()Lorg/quartz/JobDetail;", receiver=1, result=3
            ),
            _site(caller, 3, _TRIGGERS, "trigger", trigger_jvm, result=4, arguments=(cron,)),
            _site(
                caller,
                4,
                "org/quartz/Scheduler#",
                "scheduleJob",
                _SCHEDULE_JVM,
                receiver=9,
                result=5,
                arguments=(
                    CallArgument(kind="unresolved", source=3),
                    CallArgument(kind="unresolved", source=4),
                ),
            ),
        ]

    def calls_pair(name: str, job: str, cron: str) -> list:
        symbol = _MODULE + method_descriptor(_TRIGGERS, name, "()V")
        return [
            _method_symbol(name, "()V"),
            _site(
                symbol,
                0,
                _TRIGGERS,
                "pair",
                pair_jvm,
                arguments=(
                    CallArgument(kind="class", symbol=f"{_JOBS}{job}#"),
                    CallArgument(kind="string", value=cron),
                ),
            ),
        ]

    third = _MODULE + method_descriptor(_TRIGGERS, "third", "()V")
    job = ("org/quartz/Job#",)
    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + _TRIGGERS, construct_kind="class"),
        *_job_class("AJob", interfaces=job, declares=("execute",)),
        *_job_class("BJob", interfaces=job, declares=("execute",)),
        *_job_class("CJob", interfaces=job, declares=("execute",)),
        _method_symbol("trigger", trigger_jvm),
        *trigger,
        MethodReturnFact(
            document_id="doc_1",
            method=helper,
            ordinal=0,
            value=CallArgument(kind="unresolved", source=5),
        ),
        _method_symbol("pair", pair_jvm),
        *scheduled(
            pair, CallArgument(kind="parameter", value=0), CallArgument(kind="parameter", value=1)
        ),
        MethodReturnFact(document_id="doc_1", method=pair, ordinal=0, value=None),
        *calls_pair("p1", "AJob", "c1"),
        *calls_pair("p2", "BJob", "c2"),
        _method_symbol("third", "()V"),
        *scheduled(
            third,
            CallArgument(kind="class", symbol=f"{_JOBS}CJob#"),
            CallArgument(kind="string", value="c3"),
        ),
    ]
    rows = _scheduled(tmp_path, facts)
    assert sorted((_handler_of(row), row["expression"], row["resolution"]) for row in rows) == [
        ("AJob#execute", "c1", "resolved"),
        ("BJob#execute", "c2", "resolved"),
        ("CJob#execute", "c3", "resolved"),
    ]


@pytest.mark.pins("quartz.a-NAME-is-read-on-its-schedules-path")
def test_a_helpers_name_stays_with_the_schedule_its_caller_handed_it(tmp_path: Path):
    """`trigger(String name, ScheduleBuilder sb)` builds `newTrigger().withIdentity(name)
    .withSchedule(sb).build()` and pairs it with `AJob`; `first()` passes `("n1",
    cronSchedule("c1"))` and `second()` `("n2", cronSchedule("c2"))`. The name is read on
    the path the schedule came by: `n1`@c1 and `n2`@c2, never `n1`@c2 (the reviewer's
    probe: four `resolved` rows, two false)."""
    builder = "Lorg/quartz/TriggerBuilder;"
    jvm = "(Ljava/lang/String;Lorg/quartz/ScheduleBuilder;)V"
    helper = _MODULE + method_descriptor(_TRIGGERS, "trigger", jvm)
    sites = [
        _site(helper, 0, TRIGGER_BUILDER, "newTrigger", f"(){builder}", result=1),
        _site(
            helper,
            1,
            TRIGGER_BUILDER,
            "withIdentity",
            f"(Ljava/lang/String;){builder}",
            receiver=1,
            result=2,
            arguments=(CallArgument(kind="parameter", value=0),),
        ),
        _site(
            helper,
            3,
            TRIGGER_BUILDER,
            "withSchedule",
            f"(Lorg/quartz/ScheduleBuilder;){builder}",
            receiver=2,
            result=4,
            arguments=(CallArgument(kind="parameter", value=1),),
        ),
        _site(helper, 4, TRIGGER_BUILDER, "build", "()Lorg/quartz/Trigger;", receiver=4, result=5),
        _site(
            helper,
            10,
            JOB_BUILDER,
            "newJob",
            f"(Ljava/lang/Class;){_JOB_BUILDER_TYPE}",
            result=10,
            arguments=(CallArgument(kind="class", symbol=f"{_JOBS}AJob#"),),
        ),
        _site(helper, 11, JOB_BUILDER, "build", "()Lorg/quartz/JobDetail;", receiver=10, result=11),
        _site(
            helper,
            12,
            "org/quartz/Scheduler#",
            "scheduleJob",
            _SCHEDULE_JVM,
            receiver=20,
            result=12,
            arguments=(
                CallArgument(kind="unresolved", source=11),
                CallArgument(kind="unresolved", source=5),
            ),
        ),
        MethodReturnFact(document_id="doc_1", method=helper, ordinal=0, value=None),
    ]

    def caller(name: str, key: str, cron: str) -> list:
        symbol = _MODULE + method_descriptor(_TRIGGERS, name, "()V")
        return [
            _method_symbol(name, "()V"),
            _site(
                symbol,
                0,
                CRON_BUILDER,
                "cronSchedule",
                "(Ljava/lang/String;)Lorg/quartz/CronScheduleBuilder;",
                result=1,
                arguments=(CallArgument(kind="string", value=cron),),
            ),
            _site(
                symbol,
                1,
                _TRIGGERS,
                "trigger",
                jvm,
                arguments=(
                    CallArgument(kind="string", value=key),
                    CallArgument(kind="unresolved", source=1),
                ),
            ),
        ]

    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + _TRIGGERS, construct_kind="class"),
        *_job_class("AJob", interfaces=("org/quartz/Job#",), declares=("execute",)),
        _method_symbol("trigger", jvm),
        *sites,
        *caller("first", "n1", "c1"),
        *caller("second", "n2", "c2"),
    ]
    rows = _scheduled(tmp_path, facts)
    assert sorted((row["name"], row["expression"], row["resolution"]) for row in rows) == [
        ("DEFAULT.n1", "c1", "resolved"),
        ("DEFAULT.n2", "c2", "resolved"),
    ]


@pytest.mark.pins("quartz.an-UNTIED-name-is-NULL")
def test_a_pairing_no_path_ties_reads_each_part_alone_at_partial(tmp_path: Path):
    """`first()` and `second()` each call `scheduleJob(id(newJob(AJob.class).build()),
    id(trigger("n1" / "n2")))`, `id` handing back its argument. The job and the trigger
    each pass through `id` on a call of its own, which one path cannot hold, so nothing
    ties the pairing: each part is read alone and the row is `partial`. The name differs
    between the two callers and nothing ties it to the row, so it is NULL; the cron, the
    same on every path, is kept (never dropped for being untied)."""
    builder = "Lorg/quartz/TriggerBuilder;"
    trigger_jvm = "(Ljava/lang/String;)Lorg/quartz/Trigger;"
    helper = _MODULE + method_descriptor(_TRIGGERS, "trigger", trigger_jvm)
    id_jvm = "(Ljava/lang/Object;)Ljava/lang/Object;"
    identity = _MODULE + method_descriptor(_TRIGGERS, "id", id_jvm)
    trigger = _cron_trigger(helper, "n")
    trigger[1] = trigger[1].model_copy(
        update={
            "target": CallTarget(
                owner=TRIGGER_BUILDER,
                name="withIdentity",
                descriptor=f"(Ljava/lang/String;){builder}",
            ),
            "arguments": [CallArgument(kind="parameter", value=0)],
        }
    )

    def consumer(name: str, key: str) -> list:
        caller = _MODULE + method_descriptor(_TRIGGERS, name, "()V")
        return [
            _method_symbol(name, "()V"),
            *_job_chain(caller, "AJob"),
            _site(
                caller,
                3,
                _TRIGGERS,
                "id",
                id_jvm,
                result=6,
                arguments=(CallArgument(kind="unresolved", source=3),),
            ),
            _site(
                caller,
                4,
                _TRIGGERS,
                "trigger",
                trigger_jvm,
                result=4,
                arguments=(CallArgument(kind="string", value=key),),
            ),
            _site(
                caller,
                5,
                _TRIGGERS,
                "id",
                id_jvm,
                result=7,
                arguments=(CallArgument(kind="unresolved", source=4),),
            ),
            _site(
                caller,
                6,
                "org/quartz/Scheduler#",
                "scheduleJob",
                _SCHEDULE_JVM,
                receiver=9,
                result=8,
                arguments=(
                    CallArgument(kind="unresolved", source=6),
                    CallArgument(kind="unresolved", source=7),
                ),
            ),
        ]

    facts = [
        SymbolFact(document_id="doc_1", symbol=_MODULE + _TRIGGERS, construct_kind="class"),
        *_job_class("AJob", interfaces=("org/quartz/Job#",), declares=("execute",)),
        _method_symbol("trigger", trigger_jvm),
        *trigger,
        MethodReturnFact(
            document_id="doc_1",
            method=helper,
            ordinal=0,
            value=CallArgument(kind="unresolved", source=5),
        ),
        _method_symbol("id", id_jvm),
        MethodReturnFact(
            document_id="doc_1",
            method=identity,
            ordinal=0,
            value=CallArgument(kind="parameter", value=0),
        ),
        *consumer("first", "n1"),
        *consumer("second", "n2"),
    ]
    rows = _scheduled(tmp_path, facts)
    assert [
        (_handler_of(row), row["name"], row["expression"], row["resolution"]) for row in rows
    ] == [("AJob#execute", None, "0 0 * * * ?", "partial")]
