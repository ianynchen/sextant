"""A schedule set in configuration, read per environment (spec
2026-10-23-configured-schedules §3b): `resolve/resolved_schedules.py`.

A job written `@Scheduled(cron = "${orders.sweep.cron}")` keeps its one `scheduled_work` row,
`unresolved` with the expression verbatim; its value in each environment the module's own
configuration resolves is a row of `resolved_schedules` beside it, read through the project's
one placeholder rule (`resolve/config.py::substitute`). Every test drives the shipped catalogs
over hand-built facts spelled the way the extractor spells them.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.config import resolve_config
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.resolved_schedules import record_resolved_schedules
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    ConfigEntryFact,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_CAPABILITIES = {"annotation_args", "type_annotations", "nested_annotation_args"}
_VOID = "()V"

SCHEDULED = "org/springframework/scheduling/annotation/Scheduled#"
SCHEDULES = "org/springframework/scheduling/annotation/Schedules#"
SWEEPER = "com/acme/orders/OrderSweeper#"
SWEEP = _MODULE + method_descriptor(SWEEPER, "sweep", _VOID)


def _document(document_id: str, relative_path: str, language: str, scanner: str) -> Document:
    return Document(
        document_id=document_id,
        relative_path=relative_path,
        module_id="com.acme:orders-service",
        language=language,
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id=scanner,
        content_hash="sha256:c",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


def _scheduled(args: dict[str, object]) -> AnnotationUse:
    return AnnotationUse(annotation=SCHEDULED, args=args)


def _repeated(*args: dict[str, object]) -> AnnotationUse:
    """Two or more `@Scheduled` on one method, as javac folds them: one `@Schedules`
    container whose `value` is the array of uses."""
    return AnnotationUse(annotation=SCHEDULES, args={"value": [_scheduled(a) for a in args]})


def _sweeper(use: AnnotationUse) -> list[object]:
    """`OrderSweeper#sweep()` carrying `use`."""
    return [
        SymbolFact(document_id="doc", symbol=_MODULE + SWEEPER, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id="doc",
            symbol=SWEEP,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + SWEEPER,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
        ),
        AnnotationFact(
            document_id="doc",
            target=SWEEP,
            retention="runtime",
            use=use,
        ),
    ]


def _config(root: Path, relative_path: str, entries: dict[str, str]) -> None:
    document = _document(relative_path, relative_path, "yaml", "sextant-config-reader")
    document = document.model_copy(update={"origin_entry": "src/main/resources"})
    write_fact_file(
        root / f"{relative_path}.jsonl",
        document,
        [
            ConfigEntryFact(document_id=relative_path, key_raw=k, key_path=k, value=v)
            for k, v in entries.items()
        ],
    )


def _catalogs() -> list[Catalog]:
    return [
        c for c in YamlCatalogSource(CATALOGS).load() if c.id in ("spring-web", "spring-scheduling")
    ]


def _exact(catalogs: list[Catalog]) -> list[Catalog]:
    """The shipped catalogs with the config model's `key_matching` set to `exact`."""
    return [
        replace(c, config_model={**c.config_model, "key_matching": "exact"})
        if c.config_model
        else c
        for c in catalogs
    ]


def _resolved(
    tmp_path: Path,
    args: dict[str, object] | AnnotationUse,
    files: dict[str, dict[str, str]] | None = None,
    catalogs: list[Catalog] | None = None,
) -> DuckDbWorkspace:
    """The job through the passes this one reads after — configuration and the scheduled-work
    engine — and then this pass. `args` is one `@Scheduled`'s arguments, or a whole use;
    `files` maps a configuration file to its entries, `None` reading none at all."""
    root = tmp_path / "facts"
    write_fact_file(
        root / "doc.jsonl",
        _document("doc", "com/acme/orders/OrderSweeper.java", "java", "asm"),
        _sweeper(args if isinstance(args, AnnotationUse) else _scheduled(args)),
    )
    for relative_path, entries in (files or {}).items():
        _config(root, relative_path, entries)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    catalogs = catalogs or _catalogs()
    resolve_config(workspace, catalogs)
    workspace.derive("scheduled_work_reset")
    derive_endpoints(workspace, catalogs, capabilities=_CAPABILITIES)
    record_resolved_schedules(workspace, catalogs)
    return workspace


def _rows(workspace: DuckDbWorkspace) -> list[tuple[object, ...]]:
    return [
        (
            r["handler"],
            r["trigger"],
            r["expression"],
            r["environment"],
            r["value"],
            r["unresolved_reason"],
        )
        for r in workspace.query("resolved_schedules")
    ]


@pytest.mark.pins("schedules.a-PLACEHOLDER-expression-is-read-per-environment")
def test_a_placeholder_cron_is_read_in_each_environment(tmp_path: Path):
    workspace = _resolved(
        tmp_path,
        {"cron": "${orders.sweep.cron}"},
        {
            "application.yml": {"orders.sweep.cron": "0 0 * * * *"},
            "application-prod.yml": {"orders.sweep.cron": "0 */5 * * * *"},
        },
    )
    rows = _rows(workspace)
    [job] = workspace.query("scheduled_work")
    workspace.close()

    assert rows == [
        (SWEEP, "cron", "${orders.sweep.cron}", "default", "0 0 * * * *", None),
        (SWEEP, "cron", "${orders.sweep.cron}", "prod", "0 */5 * * * *", None),
    ]
    # `scheduled_work` keeps its one row per job: the schedule is still the deployment's.
    assert (job["handler"], job["expression"], job["resolution"]) == (
        SWEEP,
        "${orders.sweep.cron}",
        "unresolved",
    )


@pytest.mark.pins("schedules.an-ANNOTATION-default-applies-where-no-environment-sets-the-key")
def test_an_annotation_default_applies_where_no_environment_sets_the_key(tmp_path: Path):
    workspace = _resolved(
        tmp_path,
        {"cron": "${orders.sweep.cron:0 0 * * * *}"},
        {
            "application.yml": {"orders.name": "orders"},
            "application-prod.yml": {"orders.name": "orders-prod"},
        },
    )
    rows = _rows(workspace)
    [job] = workspace.query("scheduled_work")
    workspace.close()

    assert rows == [
        (SWEEP, "cron", "${orders.sweep.cron:0 0 * * * *}", "default", "0 0 * * * *", None),
        (SWEEP, "cron", "${orders.sweep.cron:0 0 * * * *}", "prod", "0 0 * * * *", None),
    ]
    assert job["resolution"] == "unresolved"


def test_a_key_set_nowhere_is_missing_in_every_environment(tmp_path: Path):
    workspace = _resolved(
        tmp_path,
        {"fixedRateString": "${orders.purge.rate}"},
        {
            "application.yml": {"orders.name": "orders"},
            "application-prod.yml": {"orders.name": "orders-prod"},
        },
    )
    rows = _rows(workspace)
    [job] = workspace.query("scheduled_work")
    workspace.close()

    assert rows == [
        (SWEEP, "fixedRate", "${orders.purge.rate}", "default", None, "missing_key"),
        (SWEEP, "fixedRate", "${orders.purge.rate}", "prod", None, "missing_key"),
    ]
    assert (job["expression"], job["resolution"]) == ("${orders.purge.rate}", "unresolved")


@pytest.mark.parametrize(
    "expression",
    [
        pytest.param("0 0 * * * *", id="a-literal-cron"),
        pytest.param("#{@sweepSchedule.cron()}", id="a-SpEL-expression"),
    ],
)
def test_an_expression_holding_no_placeholder_gets_no_rows(tmp_path: Path, expression: str):
    workspace = _resolved(
        tmp_path,
        {"cron": expression},
        {"application.yml": {"orders.sweep.cron": "0 */5 * * * *"}},
    )
    rows = _rows(workspace)
    [job] = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []
    assert job["expression"] == expression


def test_no_resolved_environment_gives_no_rows(tmp_path: Path):
    workspace = _resolved(tmp_path, {"cron": "${orders.sweep.cron:0 0 * * * *}"})
    rows = _rows(workspace)
    [job] = workspace.query("scheduled_work")
    workspace.close()

    assert rows == []
    assert job["resolution"] == "unresolved"


def test_a_reference_matches_a_configured_key_by_relaxed_binding(tmp_path: Path):
    """Spring's model declares `key_matching: relaxed`, so `${orders.sweep-cron}` and a
    configured `orders.sweepCron` are one key, as `resolve_config`'s own references are."""
    workspace = _resolved(
        tmp_path,
        {"cron": "${orders.sweep-cron}"},
        {"application.yml": {"orders.sweepCron": "0 0 * * * *"}},
    )
    rows = _rows(workspace)
    workspace.close()

    assert rows == [(SWEEP, "cron", "${orders.sweep-cron}", "default", "0 0 * * * *", None)]


def test_an_exact_matching_model_does_not_fold_spellings(tmp_path: Path):
    """A model declaring `key_matching: exact` looks a reference up by its spelling alone,
    so `${orders.sweep-cron}` does not find a configured `orders.sweepCron`."""
    workspace = _resolved(
        tmp_path,
        {"cron": "${orders.sweep-cron}"},
        {"application.yml": {"orders.sweepCron": "0 0 * * * *"}},
        catalogs=_exact(_catalogs()),
    )
    rows = _rows(workspace)
    workspace.close()

    assert rows == [(SWEEP, "cron", "${orders.sweep-cron}", "default", None, "missing_key")]


def test_an_expression_with_two_placeholders_resolves_only_when_both_do(tmp_path: Path):
    """Every placeholder is substituted; one the environment cannot answer fails the whole
    value, never a half-substituted schedule (`substitute`'s rule)."""
    expression = "${orders.sweep.seconds} ${orders.sweep.rest}"
    workspace = _resolved(
        tmp_path,
        {"cron": expression},
        {
            "application.yml": {"orders.sweep.seconds": "0", "orders.sweep.rest": "0 * * * *"},
            "application-prod.yml": {"orders.sweep.seconds": "30"},
            "application-qa.yml": {"orders.sweep.seconds": "15"},
        },
    )
    rows = _rows(workspace)
    workspace.close()

    assert rows == [
        (SWEEP, "cron", expression, "default", "0 0 * * * *", None),
        (SWEEP, "cron", expression, "prod", "30 0 * * * *", None),
        (SWEEP, "cron", expression, "qa", "15 0 * * * *", None),
    ]


def test_an_expression_with_one_missing_placeholder_is_unresolved_whole(tmp_path: Path):
    expression = "${orders.sweep.seconds} ${orders.sweep.rest}"
    workspace = _resolved(
        tmp_path,
        {"cron": expression},
        {"application.yml": {"orders.sweep.seconds": "0"}},
    )
    rows = _rows(workspace)
    workspace.close()

    assert rows == [(SWEEP, "cron", expression, "default", None, "missing_key")]


def test_two_placeholder_crons_on_one_method_are_attributed_to_their_own_expression(
    tmp_path: Path,
):
    """`@Schedules` folds two `@Scheduled(cron = ...)` on one method into two
    `scheduled_work` rows sharing handler and trigger; each environment's value is
    attributed to the job whose expression named it, by that expression."""
    workspace = _resolved(
        tmp_path,
        _repeated({"cron": "${orders.sweep.cron}"}, {"cron": "${orders.audit.cron}"}),
        {
            "application.yml": {
                "orders.sweep.cron": "0 0 * * * *",
                "orders.audit.cron": "0 0 3 * * *",
            },
            "application-prod.yml": {"orders.sweep.cron": "0 */5 * * * *"},
        },
    )
    rows = _rows(workspace)
    jobs = workspace.query("scheduled_work")
    workspace.close()

    assert [(j["trigger"], j["expression"]) for j in jobs] == [
        ("cron", "${orders.audit.cron}"),
        ("cron", "${orders.sweep.cron}"),
    ]
    assert rows == [
        (SWEEP, "cron", "${orders.audit.cron}", "default", "0 0 3 * * *", None),
        (SWEEP, "cron", "${orders.audit.cron}", "prod", "0 0 3 * * *", None),
        (SWEEP, "cron", "${orders.sweep.cron}", "default", "0 0 * * * *", None),
        (SWEEP, "cron", "${orders.sweep.cron}", "prod", "0 */5 * * * *", None),
    ]


def test_a_second_resolve_replaces_the_rows(tmp_path: Path):
    workspace = _resolved(
        tmp_path,
        {"cron": "${orders.sweep.cron}"},
        {"application.yml": {"orders.sweep.cron": "0 0 * * * *"}},
    )
    record_resolved_schedules(workspace, _catalogs())
    rows = _rows(workspace)
    workspace.close()

    assert rows == [(SWEEP, "cron", "${orders.sweep.cron}", "default", "0 0 * * * *", None)]
