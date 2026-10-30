"""A controller that exists in one environment only (spec 2026-10-21-conditional-controllers,
ruled 2026-10-22): `resolve/endpoint_conditions.py`.

The evaluation rules are the framework's own, read off the jars (CP-42, CP-43), and the
tests below pin them one by one on the pure functions; the workspace-level test drives the
whole pass through the SHIPPED `spring-web` catalog — its `conditions` block, its config
model — on hand-built facts, so a catalog edit that breaks the block fails here rather than
only in the fixture.
"""

from pathlib import Path

import pytest

from sextant.application.resolve.bean_conditions import (
    FAILS,
    HOLDS,
    OTHER,
    PROFILE,
    PROPERTY,
    UNRESOLVED,
    ConditionModel,
    _expression,
    _holds,
)
from sextant.application.resolve.bean_conditions import (
    record_bean_conditions as record_endpoint_conditions,
)
from sextant.application.resolve.config import resolve_config
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    ConfigEntryFact,
    Document,
    SymbolFact,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "


# --- the framework's rules, one by one (CP-42, CP-43) ------------------------------------


def test_a_profile_holds_where_the_environment_is_one_of_the_listed_names():
    """CP-42 row 2: ANY listed expression matching accepts."""
    expression = {"expressions": ["kubernetes", "nacos-discovery"]}
    assert _holds(PROFILE, expression, {}, "kubernetes") == (HOLDS, "resolved")
    assert _holds(PROFILE, expression, {}, "nacos-discovery") == (HOLDS, "resolved")
    assert _holds(PROFILE, expression, {}, "default") == (FAILS, "resolved")


@pytest.mark.pins("conditions.a-NEGATED-profile-holds-everywhere-but-that-environment")
def test_a_negated_profile_holds_everywhere_but_that_environment():
    """CP-42 row 3: `!` negates. `@Profile("!prod")` is the ordinary way to say "not in
    production", and it holds in every other environment the module resolves."""
    assert _holds(PROFILE, {"expressions": ["!prod"]}, {}, "default") == (HOLDS, "resolved")
    assert _holds(PROFILE, {"expressions": ["!prod"]}, {}, "prod") == (FAILS, "resolved")


@pytest.mark.pins("conditions.a-COMPOSED-profile-expression-is-stated-not-evaluated")
def test_a_composed_profile_expression_is_stated_not_evaluated():
    """CP-42 row 3: `&`, `|` and parentheses compose over SEVERAL active profiles, which
    this analysis does not evaluate: only a bare name and its negation are decided.
    Unresolved, in every environment, rather than a verdict about a deployment nobody
    measured."""
    for text in ("a & b", "a | b", "(a)", "!(a & b)"):
        assert _holds(PROFILE, {"expressions": [text]}, {}, "a") == (UNRESOLVED, "unresolved")


def test_a_property_compares_case_insensitively_against_having_value():
    """CP-43 row 2: `String.equalsIgnoreCase`."""
    expression = {"keys": ["orders.legacy"], "having_value": "true", "match_if_missing": False}
    assert _holds(PROPERTY, expression, {"orders.legacy": "TRUE"}, "prod") == (HOLDS, "resolved")
    assert _holds(PROPERTY, expression, {"orders.legacy": "false"}, "prod") == (FAILS, "resolved")


def test_an_empty_having_value_means_any_value_but_false():
    """CP-43 row 2: without a `havingValue`, the property must not `equalsIgnoreCase("false")`."""
    expression = {"keys": ["orders.legacy"], "having_value": "", "match_if_missing": False}
    assert _holds(PROPERTY, expression, {"orders.legacy": "anything"}, "e") == (HOLDS, "resolved")
    assert _holds(PROPERTY, expression, {"orders.legacy": "FALSE"}, "e") == (FAILS, "resolved")


@pytest.mark.pins("conditions.an-ABSENT-key-is-decided-by-match-if-missing")
def test_an_absent_key_is_decided_by_match_if_missing_and_nothing_else():
    """CP-43 row 3."""
    present = {"keys": ["orders.legacy"], "having_value": "true", "match_if_missing": True}
    absent = {"keys": ["orders.legacy"], "having_value": "true", "match_if_missing": False}
    assert _holds(PROPERTY, present, {}, "e") == (HOLDS, "resolved")
    assert _holds(PROPERTY, absent, {}, "e") == (FAILS, "resolved")


def test_a_key_resolving_to_a_placeholder_nobody_filled_is_unresolved():
    """The framework would see SOME value and this analysis does not know which: a key
    present with no resolved value is `unresolved` in that environment, never a verdict."""
    expression = {"keys": ["orders.legacy"], "having_value": "true", "match_if_missing": True}
    assert _holds(PROPERTY, expression, {"orders.legacy": None}, "e") == (UNRESOLVED, "unresolved")


def test_a_matching_plain_name_decides_the_condition_whatever_else_is_listed():
    """CP-42 row 2 with row 3 (review fix, Minor 2): ANY matching expression accepts, so a
    composed term beside a plain name that matches does not take the verdict away; where
    no plain term holds, the composed one leaves the condition `unresolved`."""
    expression = {"expressions": ["prod", "a & b"]}
    assert _holds(PROFILE, expression, {}, "prod") == (HOLDS, "resolved")
    assert _holds(PROFILE, expression, {}, "default") == (UNRESOLVED, "unresolved")


def test_a_prefix_is_joined_with_one_dot_whether_or_not_it_ends_in_one():
    """CP-43 row 4 (`Spec.getPrefix`; review fix, Minor 1): trimmed, `.` appended only where
    the prefix does not already end in one."""
    model = ConditionModel(
        kind=PROPERTY,
        annotation="org/springframework/boot/autoconfigure/condition/ConditionalOnProperty#",
        members={"prefix": "prefix", "names": ["name", "value"], "having_value": "havingValue"},
    )
    for prefix in ("orders.", "orders", " orders "):
        kind, expression = _expression(model, {"prefix": prefix, "name": ["legacy"]})
        assert (kind, expression["keys"]) == (PROPERTY, ["orders.legacy"]), prefix


def test_an_unevaluated_condition_is_unresolved_in_every_environment():
    """Spec §4: `other` is named, never decided."""
    expression = {"annotation": "x/Conditional#", "args": {"value": ["x/Y#"]}}
    assert _holds(OTHER, expression, {"any": "thing"}, "prod") == (UNRESOLVED, "unresolved")


# --- the pass, through the shipped catalog ------------------------------------------------


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


def _controller(root: Path, owner: str, handler: str, conditions: list[AnnotationUse]) -> None:
    facts = [
        SymbolFact(document_id=owner, symbol=_MODULE + owner, construct_kind=ConstructKind.CLASS),
        SymbolFact(
            document_id=owner,
            symbol=_MODULE + handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + owner,
        ),
        AnnotationFact(
            document_id=owner,
            target=_MODULE + owner,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/RestController#", args={}
            ),
        ),
        AnnotationFact(
            document_id=owner,
            target=_MODULE + handler,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={"value": ["/" + owner.split("/")[-1].rstrip("#").lower()]},
            ),
        ),
        *[
            AnnotationFact(document_id=owner, target=_MODULE + owner, retention="runtime", use=use)
            for use in conditions
        ],
    ]
    write_fact_file(
        root / f"{owner.replace('/', '_')}.jsonl",
        _document(owner, owner.rstrip("#") + ".java", "java", "sextant-jvm-extractor"),
        facts,
    )


def _config(root: Path, relative_path: str, entries: dict[str, str]) -> None:
    """A config FILE's facts, spelled the way the config reader spells them: the document's
    `relative_path` is the file's basename (`application-prod.yml`, which the model's
    `application{-profile}.yml` pattern names) and `origin_entry` the resource root."""
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


@pytest.mark.pins("conditions.the-PASS-writes-a-row-per-condition-and-environment")
def test_the_pass_writes_one_row_per_condition_and_environment_through_the_shipped_catalog(
    tmp_path: Path,
):
    """End to end on the real `spring-web` catalog: two controllers, one under
    `@Profile("prod")` and one under `@ConditionalOnProperty(name = "orders.legacy",
    havingValue = "true")`, against two environments (`application.yml`,
    `application-prod.yml` with `orders.legacy: true`). Each condition is one row per
    environment, structured; an unconditional controller writes nothing.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): a profile and a
    property are set by the deployment (CP-47), so only `@Profile("prod")` in `prod` stays
    decided — by the environment's own name. `orders.legacy` is not evaluated anywhere,
    whatever `application-prod.yml` sets."""
    facts = tmp_path / "facts"
    ops = "com/acme/orders/OpsController#"
    legacy = "com/acme/orders/LegacyOrdersController#"
    plain = "com/acme/orders/PlainController#"
    _controller(
        facts,
        ops,
        ops + "status(sig_00000001).",
        [
            AnnotationUse(
                annotation="org/springframework/context/annotation/Profile#",
                args={"value": ["prod"]},
            )
        ],
    )
    _controller(
        facts,
        legacy,
        legacy + "legacy(sig_00000002).",
        [
            AnnotationUse(
                annotation="org/springframework/boot/autoconfigure/condition/ConditionalOnProperty#",
                args={"name": ["orders.legacy"], "havingValue": "true"},
            )
        ],
    )
    _controller(facts, plain, plain + "plain(sig_00000003).", [])
    _config(facts, "application.yml", {"orders.legacy": "false"})
    _config(facts, "application-prod.yml", {"orders.legacy": "true"})

    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    assert (
        derive_endpoints(workspace, [spring], capabilities={"annotation_args", "type_annotations"})
        == []
    )
    resolve_config(workspace, [spring])
    workspace.derive("bean_conditions_reset")
    record_endpoint_conditions(workspace, [spring])
    rows = workspace.query("endpoint_conditions")
    workspace.close()

    by = {
        (r["handler"].split("/")[-1].split("(")[0], r["environment"]): (
            r["kind"],
            r["holds"],
            r["resolution"],
        )
        for r in rows
    }
    assert by == {
        ("OpsController#status", "default"): ("profile", "unresolved", "unresolved"),
        ("OpsController#status", "prod"): ("profile", "true", "resolved"),
        ("LegacyOrdersController#legacy", "default"): ("property", "unresolved", "unresolved"),
        ("LegacyOrdersController#legacy", "prod"): ("property", "unresolved", "unresolved"),
    }
    # The structured expression is what a machine reads: typed per kind, never prose.
    expressions = {r["kind"]: r["expression"] for r in rows}
    assert expressions["profile"] == '{"expressions": ["prod"]}'
    assert expressions["property"] == (
        '{"having_value": "true", "keys": ["orders.legacy"], "match_if_missing": false}'
    )


@pytest.mark.pins("conditions.a-DECLARED-placeholder-nobody-filled-is-unresolved")
def test_a_declared_key_nobody_filled_is_unresolved_not_absent(tmp_path: Path):
    """Review fix (Major 1). `orders.legacy: ${ORDERS_LEGACY}` with nothing filling the
    reference resolves `missing_key` in the config layer — the same reason as a key the
    environment never declares — but WITH its file as `source`. The framework would see some
    value there and this analysis does not know which: `unresolved`, never the absent case
    `match_if_missing` decides.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): no environment
    decides a property the deployment sets, so the declared placeholder shows in the
    evidence — the module's own `default` configuration sets a placeholder, not nothing."""
    facts = tmp_path / "facts"
    legacy = "com/acme/orders/LegacyOrdersController#"
    _controller(
        facts,
        legacy,
        legacy + "legacy(sig_00000002).",
        [
            AnnotationUse(
                annotation="org/springframework/boot/autoconfigure/condition/ConditionalOnProperty#",
                args={"name": ["orders.legacy"], "havingValue": "true"},
            )
        ],
    )
    _config(facts, "application.yml", {"orders.legacy": "${ORDERS_LEGACY}"})
    _config(facts, "application-prod.yml", {"orders.legacy": "true"})
    rows = _rows_through_spring_web(tmp_path, facts)
    assert {(r["environment"], r["holds"], r["resolution"], r["evidence"]) for r in rows} == {
        (
            "default",
            "unresolved",
            "unresolved",
            (
                "`orders.legacy` is set by the deployment; this module's `default` configuration "
                "sets a placeholder this module does not fill"
            ),
        ),
        (
            "prod",
            "unresolved",
            "unresolved",
            (
                "`orders.legacy` is set by the deployment; this module's `prod` configuration "
                "sets `true`"
            ),
        ),
    }


@pytest.mark.pins("conditions.an-UNEVALUATED-condition-still-writes-its-row")
def test_a_condition_this_analysis_does_not_evaluate_still_writes_its_rows(tmp_path: Path):
    """Review fix (Major 3). `@ConditionalOnExpression` is code, not configuration (spec §4):
    the catalog's `other` entry names it, and the row is written verbatim — annotation and
    arguments — `unresolved` in every environment, rather than the endpoint reading as
    unconditional in both documents."""
    facts = tmp_path / "facts"
    gated = "com/acme/orders/GatedController#"
    _controller(
        facts,
        gated,
        gated + "gated(sig_00000004).",
        [
            AnnotationUse(
                annotation="org/springframework/boot/autoconfigure/condition/ConditionalOnExpression#",
                args={"value": "${orders.legacy}"},
            )
        ],
    )
    _config(facts, "application.yml", {"orders.legacy": "false"})
    _config(facts, "application-prod.yml", {"orders.legacy": "true"})
    rows = _rows_through_spring_web(tmp_path, facts)
    assert {(r["kind"], r["environment"], r["holds"], r["resolution"]) for r in rows} == {
        ("other", "default", "unresolved", "unresolved"),
        ("other", "prod", "unresolved", "unresolved"),
    }
    verbatim = (
        '{"annotation": "org/springframework/boot/autoconfigure/condition/'
        'ConditionalOnExpression#", "args": {"value": "${orders.legacy}"}}'
    )
    assert {r["expression"] for r in rows} == {verbatim}


def _rows_through_spring_web(tmp_path: Path, facts: Path) -> list[dict[str, object]]:
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    derive_endpoints(workspace, [spring], capabilities={"annotation_args", "type_annotations"})
    resolve_config(workspace, [spring])
    workspace.derive("bean_conditions_reset")
    record_endpoint_conditions(workspace, [spring])
    rows = workspace.query("endpoint_conditions")
    workspace.close()
    return rows


# --- a row's bean is the class that SERVES it (ruling 8, fix round 1) --------------------
#
# Spring reads a bean's conditions off the class it registers, and `@Conditional` is not
# `@Inherited`. A mapping a controller inherits runs code declared in its base, so the
# handler's enclosing class is the wrong place to look: the row exists exactly where the
# controller serving it does.


def _class_fact(
    owner: str,
    *,
    superclass: str | None = None,
    abstract: bool = False,
    annotations: list[AnnotationUse] = (),  # type: ignore[assignment]
) -> list[object]:
    return [
        SymbolFact(
            document_id=owner,
            symbol=_MODULE + owner,
            construct_kind=ConstructKind.CLASS,
            modifiers={"abstract": abstract, "final": False},
            **({"superclass": _MODULE + superclass} if superclass else {}),
        ),
        *[
            AnnotationFact(document_id=owner, target=_MODULE + owner, retention="runtime", use=u)
            for u in annotations
        ],
    ]


def _mapped_method(owner: str, name: str, path: str) -> list[object]:
    symbol = _MODULE + owner + f"{name}(sig_00000010)."
    return [
        SymbolFact(
            document_id=owner,
            symbol=symbol,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + owner,
            modifiers={"static": False, "synthetic": False, "abstract": False},
        ),
        AnnotationFact(
            document_id=owner,
            target=symbol,
            retention="runtime",
            use=AnnotationUse(
                annotation="org/springframework/web/bind/annotation/GetMapping#",
                args={"value": [path]},
            ),
        ),
    ]


_REST = AnnotationUse(annotation="org/springframework/web/bind/annotation/RestController#", args={})
_PROD = AnnotationUse(
    annotation="org/springframework/context/annotation/Profile#", args={"value": ["prod"]}
)


def _prefix(path: str) -> AnnotationUse:
    return AnnotationUse(
        annotation="org/springframework/web/bind/annotation/RequestMapping#",
        args={"value": [path]},
    )


def _conditions_by_path(tmp_path: Path, classes: list[list[object]]) -> dict[str, set[str]]:
    """Each derived inbound path, with the condition kinds `endpoint_conditions` gives it."""
    facts = tmp_path / "facts"
    for index, class_facts in enumerate(classes):
        owner = str(class_facts[0].document_id)  # type: ignore[attr-defined]
        write_fact_file(
            facts / f"c{index}.jsonl",
            _document(owner, owner.rstrip("#") + ".java", "java", "sextant-jvm-extractor"),
            class_facts,
        )
    _config(facts, "application.yml", {})
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
    derive_endpoints(workspace, [spring], capabilities={"annotation_args", "type_annotations"})
    resolve_config(workspace, [spring])
    workspace.derive("bean_conditions_reset")
    record_endpoint_conditions(workspace, [spring])
    paths: dict[str, set[str]] = {str(r["path"]): set() for r in workspace.query("endpoints")}
    for row in workspace.query("endpoint_conditions"):
        paths.setdefault(str(row["path"]), set()).add(str(row["kind"]))
    workspace.close()
    return paths


@pytest.mark.pins("conditions.a-row-is-conditioned-by-the-class-that-SERVES-it")
def test_a_subclass_of_a_conditional_controller_does_not_take_its_condition(tmp_path: Path):
    """`BaseController` (`/base`, `@Profile("prod")`) maps `list`; `SubController`
    (`/sub`, no condition) extends it and overrides nothing. CP-58 measured both served;
    `/sub/list` exists wherever `SubController` does, which is everywhere — reading the
    handler's own class gave it the base's profile."""
    base = "com/acme/orders/BaseController#"
    sub = "com/acme/orders/SubController#"
    paths = _conditions_by_path(
        tmp_path,
        [
            [
                *_class_fact(base, annotations=[_REST, _prefix("/base"), _PROD]),
                *_mapped_method(base, "list", "/list"),
            ],
            _class_fact(sub, superclass=base, annotations=[_REST, _prefix("/sub")]),
        ],
    )

    assert paths == {"/base/list": {"profile"}, "/sub/list": set()}


def test_an_inherited_row_takes_the_condition_of_the_controller_serving_it(tmp_path: Path):
    """The other direction: an unconditional abstract base, and `OrderController` under
    `@Profile("prod")` inheriting its mapping. `/orders/list` exists only where
    `OrderController` does; read through the base it read as present everywhere."""
    crud = "com/acme/orders/CrudController#"
    orders = "com/acme/orders/OrderController#"
    paths = _conditions_by_path(
        tmp_path,
        [
            [*_class_fact(crud, abstract=True), *_mapped_method(crud, "list", "/list")],
            _class_fact(orders, superclass=crud, annotations=[_REST, _prefix("/orders"), _PROD]),
        ],
    )

    assert paths == {"/orders/list": {"profile"}}
