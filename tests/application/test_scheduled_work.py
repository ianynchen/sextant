"""Tests for the `scheduled_work` engine (D02 §2's `scheduled_work` style,
2O design §4a, Task 8).

Facts are hand-built in the exact shapes the extractor emits — an annotation
fact whose `args` follow D00 §5a's literal model, and capability 9.16's nested
`{"annotation": …, "args": {…}}` for the container javac folds a repeated
annotation into (`ClassScanner.useCollectingVisitor`). Every identity string is
invented, the `test_injected_client.py` discipline.

What these tests are ABOUT, rather than what they touch: this engine is the
first thing in the repository that publishes a claim about work nobody
requests, and the two ways to get that wrong are publishing a schedule the
framework never runs, and reading an attribute that is not a schedule at all.
The near-misses negate exactly those.
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {"annotation_args", "nested_annotation_args"}
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

SCHEDULED = "org.springframework.scheduling.annotation.Scheduled"
SCHEDULED_SYMBOL = "org/springframework/scheduling/annotation/Scheduled#"
SCHEDULES = "org.springframework.scheduling.annotation.Schedules"
SCHEDULES_SYMBOL = "org/springframework/scheduling/annotation/Schedules#"
SWEEP = "com/acme/orders/Sweeper#sweep()."


def _document(document_id: str = "doc_1") -> Document:
    return Document(
        document_id=document_id,
        relative_path="com/acme/orders/Sweeper.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _method(symbol: str = SWEEP) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + symbol,
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + "com/acme/orders/Sweeper#",
        signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
    )


def _annotated(
    args: dict[str, object],
    *,
    annotation: str = SCHEDULED_SYMBOL,
    target: str = SWEEP,
) -> AnnotationFact:
    return AnnotationFact(
        document_id="doc_1",
        target=_MODULE + target,
        use=AnnotationUse(annotation=annotation, args=args),
        retention="RUNTIME",
    )


def _folded(*uses: dict[str, object], target: str = SWEEP) -> AnnotationFact:
    """The shape javac produces for two or more repeats of one annotation on
    one method: a single container whose `value` is an ARRAY OF ANNOTATIONS.
    Capability 9.16 is what makes the array's entries readable at all."""
    return _annotated(
        {"value": [AnnotationUse(annotation=SCHEDULED_SYMBOL, args=use) for use in uses]},
        annotation=SCHEDULES_SYMBOL,
        target=target,
    )


def _shipped() -> Catalog:
    return next(
        catalog
        for catalog in YamlCatalogSource(catalogs_dir()).load()
        if catalog.id == "spring-scheduling"
    )


def _invented(matches: dict[str, object] | None = None) -> Catalog:
    """A catalog of this STYLE that names no framework, for the tests that pin
    an engine mechanism rather than Spring's own vocabulary — the
    `test_endpoints.py` discipline: a mechanism test must not be able to pass
    or fail because a shipped file changed."""
    return Catalog(
        id="test-scheduling",
        style="scheduled_work",
        protocol="",
        direction="",
        requires=(),
        matches=matches
        or {
            "annotation": SCHEDULED,
            "container": SCHEDULES,
            "triggers": {"cron": "cron", "fixedRate": "fixedRate"},
        },
        source=Path("test-scheduling.yml"),
    )


def _resolve(
    tmp_path: Path, facts: list[object], catalog: Catalog | None = None
) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "Sweeper.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.derive("scheduled_work_reset")
    skipped = derive_endpoints(workspace, [catalog or _shipped()], capabilities=CAPABILITIES)
    assert skipped == []
    return workspace


# --- (a) the happy paths ---------------------------------------------------


def test_a_cron_schedule_derives_one_row_carrying_the_expression_verbatim(tmp_path: Path):
    """The expression is the whole answer: a cron string normalised, trimmed
    or re-spaced would name a different schedule from the one that runs."""
    workspace = _resolve(tmp_path, [_method(), _annotated({"cron": "0 0 3 * * *"})])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert rows == [
        {
            "handler": _MODULE + SWEEP,
            "trigger": "cron",
            "name": None,
            "expression": "0 0 3 * * *",
            "expression_source": None,
            "resolution": "resolved",
            "evidence": "compiler",
            "catalog_id": "spring-scheduling",
        }
    ]


@pytest.mark.parametrize(
    ("attribute", "value", "trigger", "expression"),
    [
        ("fixedRate", 5000, "fixedRate", "5000"),
        ("fixedRateString", "5s", "fixedRate", "5s"),
        ("fixedDelay", 250, "fixedDelay", "250"),
        ("fixedDelayString", "PT2S", "fixedDelay", "PT2S"),
    ],
)
def test_each_declared_trigger_attribute_carries_the_frameworks_own_kind(
    tmp_path: Path, attribute: str, value: object, trigger: str, expression: str
):
    """The `String` spellings are the SAME schedule kind as their numeric
    twins — the difference is the notation, not the schedule — so a consumer
    grouping by `trigger` must see one kind, not two."""
    workspace = _resolve(tmp_path, [_method(), _annotated({attribute: value})])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert [(row["trigger"], row["expression"]) for row in rows] == [(trigger, expression)]


def test_a_placeholder_expression_is_unresolved_and_still_carried_verbatim(tmp_path: Path):
    """Unresolved is an answer, invention is not. The value comes from
    configuration a deployment overwrites (§8.2), so the row says what the
    code declares and refuses to say what will run."""
    workspace = _resolve(tmp_path, [_method(), _annotated({"cron": "${orders.sweep.cron}"})])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert [(row["expression"], row["resolution"]) for row in rows] == [
        ("${orders.sweep.cron}", "unresolved")
    ]


def test_two_schedules_on_one_method_derive_two_rows_through_the_container(tmp_path: Path):
    """The multi-trigger case is the one capability 9.16 exists for: javac
    folds the repeats into a container, so before nested arguments could be
    read a method with TWO schedules reported none while its single-schedule
    neighbour reported its own."""
    workspace = _resolve(
        tmp_path, [_method(), _folded({"cron": "0 0 3 * * *"}, {"fixedRate": 5000})]
    )
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert [(row["trigger"], row["expression"]) for row in rows] == [
        ("cron", "0 0 3 * * *"),
        ("fixedRate", "5000"),
    ]


def test_a_declaration_writing_two_trigger_attributes_derives_a_row_for_each(tmp_path: Path):
    """Each attribute written IS a declared schedule, and reporting only the
    first would drop a fact the code states. What the container does with a
    declaration that names two is a startup question this analysis cannot
    answer — COVERAGE says so — and answering it by silence would be the
    silent under-report FR-17 forbids."""
    workspace = _resolve(
        tmp_path, [_method(), _annotated({"cron": "0 0 3 * * *", "fixedRate": 5000})]
    )
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert [row["trigger"] for row in rows] == ["cron", "fixedRate"]


# --- (b) the near-misses (§10) ---------------------------------------------


def test_a_method_named_sweep_with_no_schedule_annotation_derives_nothing(tmp_path: Path):
    """The rule's first conjunct: the annotation. A method whose NAME says it
    sweeps is not scheduled work — nothing but the declaration is."""
    workspace = _resolve(tmp_path, [_method()])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []


@pytest.mark.declines("spring-scheduling")
@pytest.mark.pins("spring-scheduling.triggers-are-the-schedule-attributes")
def test_an_initial_delay_alone_is_not_a_schedule_and_derives_nothing(tmp_path: Path):
    """`initialDelay` is a real attribute of the shipped catalog's own
    annotation, it is a duration, and it sits beside the rate it delays. It is
    not a schedule: reading it would publish the wait before the FIRST run as
    the interval between EVERY run. Every conjunct but one is satisfied here —
    the annotation is present, on a method, with an argument — which is what
    makes this a near-miss rather than an empty input."""
    workspace = _resolve(tmp_path, [_method(), _annotated({"initialDelay": 1000})])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []


@pytest.mark.declines("spring-scheduling")
@pytest.mark.pins("spring-scheduling.the-disable-sentinel-is-the-frameworks-own")
def test_a_cron_written_as_the_frameworks_disable_sentinel_derives_nothing(tmp_path: Path):
    """`-` is `@Scheduled.CRON_DISABLED`, and Spring's post-processor compares
    `cron()` against it immediately before `scheduleCronTask` and before
    nothing else — CP-14 rows 1-3, byte-identical at spring-context 6.1.6,
    6.2.19 and 7.0.9. So this declaration registers NO task, and a row for it
    would be work the framework will never do, published at
    `resolved`/`compiler` beside schedules that really run.

    Every conjunct but one is satisfied: the shipped annotation, on a method,
    with a trigger attribute the shipped catalog names and a value this pass
    can spell. The one that fails is the value itself, which is `OI-2`."""
    workspace = _resolve(tmp_path, [_method(), _annotated({"cron": "-"})])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []


@pytest.mark.pins("scheduled_work.a-disabled-trigger-declares-no-task")
def test_a_trigger_written_with_its_catalogs_own_sentinel_derives_nothing(tmp_path: Path):
    """The engine half, on an invented catalog naming no framework — the
    `test_endpoints.py` discipline, so this cannot pass or fail because a
    shipped file changed. A catalog that states the right sentinel and an
    engine that ignores it look identical from the shipped side; this is what
    tells them apart.

    Two attributes, one sentinel: `fixedRate` is written with the same text and
    keeps its row, which is what makes this a measurement of the pairing rather
    than of the value."""
    catalog = _invented(
        {
            "annotation": SCHEDULED,
            "container": SCHEDULES,
            "triggers": {"cron": "cron", "fixedRate": "fixedRate"},
            "disabled": {"cron": "off"},
        }
    )
    facts = [_method(), _annotated({"cron": "off", "fixedRate": "off"})]
    workspace = _resolve(tmp_path, facts, catalog)
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert [row["trigger"] for row in rows] == ["fixedRate"]


def test_a_disabled_sentinel_naming_no_trigger_attribute_is_refused(tmp_path: Path):
    """A sentinel written against an attribute no schedule is read from
    withdraws nothing at all, silently — the `A-Mi8` shape one key over. It is
    refused at load rather than ignored, because the mistake it reads as is a
    misspelled attribute name, which is exactly what the key exists to
    prevent."""
    catalog = _invented(
        {
            "annotation": SCHEDULED,
            "container": SCHEDULES,
            "triggers": {"cron": "cron"},
            "disabled": {"crons": "-"},
        }
    )
    with pytest.raises(CatalogError, match="crons"):
        _resolve(tmp_path, [_method(), _annotated({"cron": "0 0 3 * * *"})], catalog)


def test_an_unreadable_trigger_value_is_not_read_as_a_disable(tmp_path: Path):
    """`disabled.get()` answers None for an attribute the catalog gives no
    sentinel, and `_verbatim` answers None for a value this pass cannot spell.
    Comparing the two before the readability test would attribute an unread
    value to a disable nobody wrote — the same row either way, but attributed
    to the wrong rule, which is what makes a guard measure the wrong thing.

    `fixedRate` carries an annotation-valued argument and has no sentinel;
    `cron` beside it is ordinary and must still derive."""
    facts = [
        _method(),
        _annotated(
            {
                "cron": "0 0 3 * * *",
                "fixedRate": AnnotationUse(annotation="com/acme/orders/Tag#", args={}),
            }
        ),
    ]
    workspace = _resolve(tmp_path, facts, _invented())
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert [row["trigger"] for row in rows] == ["cron"]


@pytest.mark.pins("scheduled_work.declaration-is-a-method")
def test_the_annotation_on_an_annotation_type_derives_nothing(tmp_path: Path):
    """The framework's annotation is `@Target`-legal on an ANNOTATION TYPE,
    which is how a module composes its own `@Nightly`. That declaration is a
    composition, not scheduled work: no method runs, so publishing it would
    report a clock nobody set. Invented catalog on purpose — this pins an
    engine conjunct, not Spring's vocabulary."""
    composed = "com/acme/orders/Nightly#"
    facts = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + composed,
            construct_kind=ConstructKind.INTERFACE,
        ),
        _annotated({"cron": "0 0 3 * * *"}, target=composed),
    ]
    workspace = _resolve(tmp_path, facts, _invented())
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []


def test_an_annotation_with_no_arguments_derives_nothing(tmp_path: Path):
    """A boundary value rather than a near-miss (§10 distinguishes them): the
    declaration is claimed, and there is simply no expression to carry. A row
    with an empty schedule would claim work on a clock nobody set."""
    workspace = _resolve(tmp_path, [_method(), _annotated({})])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []


def test_a_container_holding_some_other_annotation_derives_nothing(tmp_path: Path):
    """A container is an ordinary annotation whose `value` happens to be an
    array. Reading whatever it holds would let any array-valued annotation
    contribute schedules, so each entry is checked against the annotation the
    catalog names."""
    other = _annotated(
        {"value": [AnnotationUse(annotation="com/acme/orders/Tag#", args={"cron": "0 0 3 * * *"})]},
        annotation=SCHEDULES_SYMBOL,
    )
    workspace = _resolve(tmp_path, [_method(), other])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []


def test_a_trigger_whose_value_is_not_a_literal_derives_nothing(tmp_path: Path):
    """An attribute that was written and could not be read must never become a
    schedule with an invented expression. `True` is the sharp case: Python's
    `bool` is an `int`, so a numeric-looking test alone would spell it `1` and
    publish a one-millisecond schedule."""
    workspace = _resolve(tmp_path, [_method(), _annotated({"fixedRate": True})])
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []


# --- (c) the table is rebuilt, not appended to -----------------------------


def test_a_second_resolve_replaces_the_rows_rather_than_doubling_them(tmp_path: Path):
    """The reset lives in the pipeline and runs once per resolve. `_resolve`
    calls it the way `resolve()` does, so running twice over one workspace
    must leave one set of rows — the defect a per-catalog reset would
    reintroduce is the opposite one, and `test_endpoints.py` pins that half."""
    facts = [_method(), _annotated({"cron": "0 0 3 * * *"})]
    write_fact_file(tmp_path / "facts" / "Sweeper.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    for _ in range(2):
        workspace.derive("scheduled_work_reset")
        derive_endpoints(workspace, [_shipped()], capabilities=CAPABILITIES)
    rows = workspace.query("scheduled_work")
    workspace.close()

    assert len(rows) == 1


# --- (d) a broken catalog is refused, never half-read ----------------------


@pytest.mark.parametrize(
    "matches",
    [
        {"container": SCHEDULES, "triggers": {"cron": "cron"}},
        {"annotation": SCHEDULED, "triggers": {"cron": "cron"}},
        {"annotation": SCHEDULED, "container": SCHEDULES},
        {"annotation": SCHEDULED, "container": SCHEDULES, "triggers": {}},
        {"annotation": SCHEDULED, "container": SCHEDULES, "triggers": ["cron"]},
    ],
)
def test_a_catalog_missing_or_malforming_its_matches_is_refused(
    tmp_path: Path, matches: dict[str, object]
):
    """The values reach a published column, where a typo is indistinguishable
    from an observation — so the file is refused rather than half-read."""
    with pytest.raises(CatalogError):
        _resolve(tmp_path, [_method()], _invented(matches))


def test_the_shipped_catalog_declares_no_wire_identity(tmp_path: Path):
    """The absence of `protocol`/`direction` is a CLAIM — this catalog derives
    nothing addressable — and `resolve/endpoints.py` refuses a non-wire style
    that declares either. Pinned here because a later editor adding
    `protocol: http` to make the file look like its neighbours would be adding
    a wire claim nothing reads and every reader believes."""
    catalog = _shipped()
    assert (catalog.protocol, catalog.direction) == ("", "")


def test_the_shipped_catalog_derives_no_endpoint_rows(tmp_path: Path):
    """The whole point of the second table: `endpoints` stays wire-true. A
    scheduled method has no protocol, no address and no direction, and a row
    claiming one would be a boundary nothing serves."""
    workspace = _resolve(tmp_path, [_method(), _annotated({"cron": "0 0 3 * * *"})])
    endpoints = workspace.query("endpoints")
    scheduled = workspace.query("scheduled_work")
    workspace.close()

    assert endpoints == []
    assert len(scheduled) == 1


def test_the_shipped_catalogs_trigger_map_names_no_delay_attribute():
    """The alias set, asserted against the shipped file itself. `initialDelay`
    and `initialDelayString` delay the FIRST run of a schedule declared
    elsewhere; `zone`, `timeUnit` and `scheduler` are not durations at all.
    None of them is a schedule, and the near-miss above proves the engine
    agrees."""
    triggers = _shipped().matches["triggers"]
    assert set(triggers) == {
        "cron",
        "fixedDelay",
        "fixedDelayString",
        "fixedRate",
        "fixedRateString",
    }
    assert set(triggers.values()) == {"cron", "fixedDelay", "fixedRate"}


def test_the_fact_shape_these_tests_build_is_the_one_the_extractor_writes():
    """A test suite built on an invented fact shape measures itself. The
    container's nested entry must serialize to capability 9.16's own
    `{"annotation": …, "args": {…}}` — `ClassScanner.useCollectingVisitor`'s
    `visitEnd` writes exactly those two keys — or every container test above
    passes against a shape no scanner produces."""
    payload = json.loads(_folded({"cron": "0 0 3 * * *"}).model_dump_json())
    entry = payload["use"]["args"]["value"][0]
    assert sorted(entry) == ["annotation", "args", "unresolved"]
    assert entry["annotation"] == SCHEDULED_SYMBOL
    assert entry["args"] == {"cron": "0 0 3 * * *"}
