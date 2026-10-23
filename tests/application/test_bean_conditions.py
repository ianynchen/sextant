"""A bean that exists in some environments only (spec 2026-10-22-conditional-beans §2, §2a):
`resolve/bean_conditions.py`, and the `endpoint_conditions` view every derived row reads it
through.

The registration rule is Spring's own, read off the jar (CP-44,
`scripts/probes/cp44_bean_registration_conditions.md`): a scanned class is conditioned by
its own annotations; a `@Bean` method by its own AND its configuration class's; a class
merely constructed inside a `@Bean` body by the factory method's — and only the class the
method RETURNS is the bean. Every test drives the whole pass through the SHIPPED catalogs
and their bean model, on hand-built facts spelled the way the extractor spells them (module
coordinates on every declared symbol, bare descriptors on every call target).
"""

import json
from pathlib import Path

import duckdb
import pytest

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.bean_conditions import (
    FAILS,
    HOLDS,
    PROFILE,
    PROPERTY,
    UNRESOLVED,
    ActiveProfiles,
    ConditionModel,
    _holds,
    _judged,
    _models,
    _profile_holds,
    active_profiles,
    deployment_reading,
    record_bean_conditions,
    redact_condition_evidence,
)
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.conditions import enclosing_type_of
from sextant.application.resolve.config import resolve_config
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    ConfigEntryFact,
    Document,
    MethodReturnFact,
    Signature,
    SymbolFact,
    TypeHeaderFact,
    TypeRef,
)
from sextant.domain.redaction import REDACTED, RedactionRules, Redactor
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_CAPABILITIES = {
    "annotation_args",
    "type_annotations",
    "call_site",
    "string_constants",
    "nested_annotation_args",
}
_VOID = "()V"

SERVICE = "org/springframework/stereotype/Service#"
COMPONENT = "org/springframework/stereotype/Component#"
CONFIGURATION = "org/springframework/context/annotation/Configuration#"
BEAN = "org/springframework/context/annotation/Bean#"
SCHEDULED = "org/springframework/scheduling/annotation/Scheduled#"
RESTTEMPLATE = "org/springframework/web/client/RestTemplate#"

ORDERS = "com/acme/orders/"
PUBLISHER = ORDERS + "OrderPublisher#"
KAFKA = ORDERS + "KafkaOrderPublisher#"
LEGACY = ORDERS + "LegacyOrderPublisher#"
FORMATTER = ORDERS + "RecordFormatter#"
MESSAGING = ORDERS + "MessagingConfig#"


def _profile(*names: str) -> AnnotationUse:
    return AnnotationUse(
        annotation="org/springframework/context/annotation/Profile#", args={"value": list(names)}
    )


def _on_property(name: str, having: str) -> AnnotationUse:
    return AnnotationUse(
        annotation="org/springframework/boot/autoconfigure/condition/ConditionalOnProperty#",
        args={"name": [name], "havingValue": having},
    )


def _marker(annotation: str) -> AnnotationUse:
    return AnnotationUse(annotation=annotation, args={})


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


def _annotated(target: str, uses: list[AnnotationUse]) -> list[object]:
    return [
        AnnotationFact(document_id="doc", target=_MODULE + target, retention="runtime", use=use)
        for use in uses
    ]


def _type(
    symbol: str,
    uses: list[AnnotationUse] | None = None,
    *,
    kind: ConstructKind = ConstructKind.CLASS,
    interfaces: tuple[str, ...] = (),
    superclass: str | None = None,
) -> list[object]:
    """A type, its annotations, and — for a class — a constructor whose body was read, so
    a `new` of it is an edge into the module rather than the third-party boundary."""
    facts: list[object] = [
        SymbolFact(
            document_id="doc",
            symbol=_MODULE + symbol,
            construct_kind=kind,
            interfaces=list(interfaces),
            superclass=None if superclass is None else _MODULE + superclass,
        ),
        *_annotated(symbol, uses or []),
    ]
    if kind == ConstructKind.CLASS:
        constructor = _MODULE + method_descriptor(symbol, "<init>", _VOID)
        facts += [
            SymbolFact(
                document_id="doc",
                symbol=constructor,
                construct_kind=ConstructKind.CONSTRUCTOR,
                enclosing=_MODULE + symbol,
                signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
            ),
            MethodReturnFact(document_id="doc", method=constructor, ordinal=0, value=None),
        ]
    return facts


def _method(
    owner: str, name: str, returns: str, uses: list[AnnotationUse], constructs: list[str]
) -> list[object]:
    """A method returning `returns` (bare) whose body runs `new` on each of `constructs`."""
    symbol = method_descriptor(owner, name, "()L" + returns.removesuffix("#") + ";")
    facts: list[object] = [
        SymbolFact(
            document_id="doc",
            symbol=_MODULE + symbol,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + owner,
            signature=Signature(parameters=[], returns=TypeRef(symbol=returns)),
        ),
        MethodReturnFact(document_id="doc", method=_MODULE + symbol, ordinal=0, value=None),
        *_annotated(symbol, uses),
    ]
    for ordinal, constructed in enumerate(constructs):
        facts.append(
            CallSiteFact(
                document_id="doc",
                caller=_MODULE + symbol,
                target=CallTarget(owner=constructed, name="<init>", descriptor=_VOID),
                invoke_kind="special",
                ordinal=ordinal,
                result=None,
            )
        )
    return facts


def _factory_symbol(owner: str, name: str, returns: str) -> str:
    return _MODULE + method_descriptor(owner, name, "()L" + returns.removesuffix("#") + ";")


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


def _catalogs(*ids: str) -> list[Catalog]:
    return [c for c in YamlCatalogSource(CATALOGS).load() if c.id in ids]


def _resolved(
    tmp_path: Path,
    facts: list[object],
    *ids: str,
    environments: tuple[str, ...] = ("prod",),
    default_legacy: str = "false",
    base: dict[str, str] | None = None,
) -> DuckDbWorkspace:
    """The facts through the passes the conditions pass reads after: configuration (the
    environments), the call graph and the hierarchy (what a factory constructs, and what it
    is assignable to), and the rows themselves."""
    root = tmp_path / "facts"
    write_fact_file(
        root / "doc.jsonl", _document("doc", "com/acme/orders/All.java", "java", "asm"), facts
    )
    _config(root, "application.yml", {"orders.legacy": default_legacy, **(base or {})})
    for profile in environments:
        _config(root, f"application-{profile}.yml", {"orders.legacy": "true"})
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    catalogs = _catalogs("spring-web", *ids)
    resolve_config(workspace, catalogs)
    record_call_edges(workspace)
    workspace.derive("scheduled_work_reset")
    derive_endpoints(workspace, catalogs, capabilities=_CAPABILITIES)
    workspace.derive("bean_conditions_reset")
    record_bean_conditions(workspace, catalogs)
    return workspace


def _verdicts(rows: list[dict[str, object]], bean: str) -> dict[str, tuple[object, ...]]:
    return {
        str(r["environment"]): (r["bean_kind"], r["via"], r["kind"], r["holds"], r["resolution"])
        for r in rows
        if r["bean"] == _MODULE + bean
    }


# --- a scanned class: every row whose code is in it -------------------------------------


def test_a_conditional_scanned_class_conditions_its_outbound_row_and_its_scheduled_job(
    tmp_path: Path,
):
    """`@Service @Profile("prod") ProdSync` makes an outbound call and runs on a clock. Both
    rows are derived from a bean Spring registers only under `prod`, so both carry the
    condition — the outbound one through the `endpoint_conditions` view, the scheduled job
    through its handler's owner class, which is the one join every row kind shares.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("prod")`
    holds in `prod`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `prod`."""
    sync = ORDERS + "ProdSync#"
    run = method_descriptor(sync, "run", _VOID)
    facts = [
        *_type(sync, [_marker(SERVICE), _profile("prod")]),
        SymbolFact(
            document_id="doc",
            symbol=_MODULE + run,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + sync,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
        ),
        *_annotated(run, [AnnotationUse(annotation=SCHEDULED, args={"fixedRate": 5000})]),
        CallSiteFact(
            document_id="doc",
            caller=_MODULE + run,
            target=CallTarget(
                owner=RESTTEMPLATE,
                name="getForObject",
                descriptor="(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=12,
            arguments=[
                CallArgument(kind="string", value="/billing/balances/{id}"),
                CallArgument(kind="class", symbol="java/lang/String#"),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]
    workspace = _resolved(tmp_path, facts, "spring-resttemplate", "spring-scheduling")
    beans = workspace.query("bean_conditions")
    viewed = workspace.query("endpoint_conditions")
    [job] = workspace.query("scheduled_work")
    workspace.close()

    assert _verdicts(beans, sync) == {
        "default": ("class", None, "profile", "unresolved", "unresolved"),
        "prod": ("class", None, "profile", "true", "resolved"),
    }
    assert {(r["direction"], r["caller"], r["environment"], r["holds"]) for r in viewed} == {
        ("outbound", _MODULE + run, "default", "unresolved"),
        ("outbound", _MODULE + run, "prod", "true"),
    }
    # The scheduled job finds the same rows through its handler's owner class.
    assert enclosing_type_of(str(job["handler"])) == _MODULE + sync
    assert {r["bean"] for r in beans} == {_MODULE + sync}


# --- a `@Bean` factory: the class it constructs and returns -----------------------------


def test_a_profile_factory_conditions_the_class_it_constructs(tmp_path: Path):
    """`@Bean @Profile("prod") OrderPublisher publisher() { return new KafkaOrderPublisher(); }`
    in an unconditional configuration class. Spring registers the bean only under `prod`, and
    the class whose code runs is `KafkaOrderPublisher` — its own annotations are never
    consulted on this route (CP-44 row 4), the factory's are.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("prod")`
    holds in `prod`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `prod`."""
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(KAFKA, interfaces=(PUBLISHER,)),
        *_type(MESSAGING, [_marker(CONFIGURATION)]),
        *_method(MESSAGING, "publisher", PUBLISHER, [_marker(BEAN), _profile("prod")], [KAFKA]),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    via = _factory_symbol(MESSAGING, "publisher", PUBLISHER)
    assert _verdicts(beans, KAFKA) == {
        "default": ("factory", via, "profile", "unresolved", "unresolved"),
        "prod": ("factory", via, "profile", "true", "resolved"),
    }
    # The configuration class itself carries no condition, so it is no conditional bean. The
    # factory method is one: its own body is the factory's code, `via` itself.
    assert {r["bean"] for r in beans} == {_MODULE + KAFKA, via}


@pytest.mark.pins("beans.a-FACTORY-conditions-only-the-class-it-returns")
def test_a_factory_conditions_only_the_class_it_returns(tmp_path: Path):
    """Review focus 1. The same factory also builds a helper it hands to the bean
    (`new KafkaOrderPublisher(new RecordFormatter())` in the source). The helper is not
    assignable to the declared return type, so it is no bean the container registers — a
    structural rule on `type_hierarchy`, never a model of what the body does with it."""
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(KAFKA, interfaces=(PUBLISHER,)),
        *_type(FORMATTER),
        *_type(MESSAGING, [_marker(CONFIGURATION)]),
        *_method(
            MESSAGING,
            "publisher",
            PUBLISHER,
            [_marker(BEAN), _profile("prod")],
            [FORMATTER, KAFKA],
        ),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    # The class it returns and the factory method itself (its own body is the factory's code).
    via = _factory_symbol(MESSAGING, "publisher", PUBLISHER)
    assert {r["bean"] for r in beans} == {_MODULE + KAFKA, via}
    assert _verdicts(beans, FORMATTER) == {}


def test_a_factory_in_a_conditional_configuration_inherits_the_class_condition(tmp_path: Path):
    """`@Configuration @ConditionalOnProperty(name = "orders.legacy", havingValue = "true")`
    with an unconditional `@Bean`: Spring skips every `@Bean` of a configuration class whose
    own condition fails (CP-44 row 4), so the constructed class carries the class's
    condition, as `configuration`.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `orders.legacy` is
    set by the deployment (CP-47), so the condition is not evaluated in either environment,
    whatever the module's files set; the route it is on is what this test pins."""
    legacy_config = ORDERS + "LegacyConfig#"
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(LEGACY, interfaces=(PUBLISHER,)),
        *_type(legacy_config, [_marker(CONFIGURATION), _on_property("orders.legacy", "true")]),
        *_method(legacy_config, "legacyPublisher", PUBLISHER, [_marker(BEAN)], [LEGACY]),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    via = _factory_symbol(legacy_config, "legacyPublisher", PUBLISHER)
    assert _verdicts(beans, LEGACY) == {
        "default": ("configuration", via, "property", "unresolved", "unresolved"),
        "prod": ("configuration", via, "property", "unresolved", "unresolved"),
    }
    # The configuration class is itself a conditional scanned bean.
    assert _verdicts(beans, legacy_config) == {
        "default": ("class", None, "property", "unresolved", "unresolved"),
        "prod": ("class", None, "property", "unresolved", "unresolved"),
    }


# --- a class registered more than one way: it exists wherever ANY route registers it -----


def _presence(workspace: DuckDbWorkspace, bean: str) -> dict[str, tuple[object, ...]]:
    return {
        str(r["environment"]): (r["holds"], r["resolution"])
        for r in workspace.query("bean_presence")
        if r["bean"] == _MODULE + bean
    }


@pytest.mark.pins("beans.registration-ROUTES-combine-by-OR")
def test_two_exclusive_profile_factories_make_the_class_exist_in_each_profile(tmp_path: Path):
    """Ruled 2026-10-22: OR across routes. `@Bean @Profile("prod")` and `@Bean
    @Profile("staging")` each register their own definition of `KafkaOrderPublisher`, so it
    exists in `prod` and in `staging` and nowhere else — decided, not `unresolved`. Each
    factory's own condition rows stay, evaluated, under its own `via`.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): each profile is
    decided only in its own environment, so the class exists in `prod` and in `staging`,
    decided there by the OR; elsewhere — `default`, and each profile's route in the other's
    environment — the deployment may activate the profile, so it is not evaluated."""
    staging = ORDERS + "StagingConfig#"
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(KAFKA, interfaces=(PUBLISHER,)),
        *_type(MESSAGING, [_marker(CONFIGURATION)]),
        *_method(MESSAGING, "publisher", PUBLISHER, [_marker(BEAN), _profile("prod")], [KAFKA]),
        *_type(staging, [_marker(CONFIGURATION)]),
        *_method(staging, "publisher", PUBLISHER, [_marker(BEAN), _profile("staging")], [KAFKA]),
    ]
    workspace = _resolved(tmp_path, facts, environments=("prod", "staging"))
    presence = _presence(workspace, KAFKA)
    rows = [r for r in workspace.query("bean_conditions") if r["bean"] == _MODULE + KAFKA]
    workspace.close()

    assert presence == {
        "default": ("unresolved", "unresolved"),
        "prod": ("true", "resolved"),
        "staging": ("true", "resolved"),
    }
    assert {(r["via"], r["environment"], r["holds"]) for r in rows} == {
        (_factory_symbol(MESSAGING, "publisher", PUBLISHER), "default", "unresolved"),
        (_factory_symbol(MESSAGING, "publisher", PUBLISHER), "prod", "true"),
        (_factory_symbol(MESSAGING, "publisher", PUBLISHER), "staging", "unresolved"),
        (_factory_symbol(staging, "publisher", PUBLISHER), "default", "unresolved"),
        (_factory_symbol(staging, "publisher", PUBLISHER), "prod", "unresolved"),
        (_factory_symbol(staging, "publisher", PUBLISHER), "staging", "true"),
    }


@pytest.mark.parametrize("unconditional", ["factory", "scanned"])
def test_an_unconditional_route_beside_a_conditional_factory_makes_the_class_exist_everywhere(
    tmp_path: Path, unconditional: str
):
    """Review focus 2, as ruled: a conditional factory of `KafkaOrderPublisher` beside an
    unconditional `@Bean` of it — or beside its own unconditional `@Component` — means the
    class exists in every environment, resolved. The conditional route's rows are still
    written and still evaluated; the bean's presence is what changes.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("prod")`
    holds in `prod`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `prod`. The unconditional route still
    decides the class's presence everywhere."""
    plain = ORDERS + "DefaultConfig#"
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(
            KAFKA,
            [_marker(COMPONENT)] if unconditional == "scanned" else [],
            interfaces=(PUBLISHER,),
        ),
        *_type(MESSAGING, [_marker(CONFIGURATION)]),
        *_method(MESSAGING, "publisher", PUBLISHER, [_marker(BEAN), _profile("prod")], [KAFKA]),
    ]
    if unconditional == "factory":
        facts += [
            *_type(plain, [_marker(CONFIGURATION)]),
            *_method(plain, "fallback", PUBLISHER, [_marker(BEAN)], [KAFKA]),
        ]
    workspace = _resolved(tmp_path, facts)
    presence = _presence(workspace, KAFKA)
    conditional = [
        r
        for r in workspace.query("bean_conditions")
        if r["bean"] == _MODULE + KAFKA and r["kind"] is not None
    ]
    workspace.close()

    assert presence == {"default": ("true", "resolved"), "prod": ("true", "resolved")}
    assert {(r["environment"], r["holds"], r["resolution"]) for r in conditional} == {
        ("default", "unresolved", "unresolved"),
        ("prod", "true", "resolved"),
    }


def test_a_plain_new_outside_any_factory_leaves_the_class_open_where_the_factory_fails(
    tmp_path: Path,
):
    """A plain `new KafkaOrderPublisher()` in an ordinary method runs that class's code on a
    path no bean decides. Where the conditional factory holds (`prod`) the class exists
    regardless; where it fails (`default`) whether its code runs is not known — `unresolved`,
    the evidence naming the method that constructs it."""
    plain = ORDERS + "Fallback#"
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(KAFKA, interfaces=(PUBLISHER,)),
        *_type(MESSAGING, [_marker(CONFIGURATION)]),
        *_method(MESSAGING, "publisher", PUBLISHER, [_marker(BEAN), _profile("prod")], [KAFKA]),
        *_type(plain),
        *_method(plain, "make", PUBLISHER, [], [KAFKA]),
    ]
    workspace = _resolved(tmp_path, facts)
    rows = [r for r in workspace.query("bean_presence") if r["bean"] == _MODULE + KAFKA]
    workspace.close()

    by = {str(r["environment"]): r for r in rows}
    assert (by["prod"]["holds"], by["prod"]["resolution"]) == ("true", "resolved")
    assert (by["default"]["holds"], by["default"]["resolution"]) == ("unresolved", "unresolved")
    assert _factory_symbol(plain, "make", PUBLISHER) in str(by["default"]["evidence"])


def test_a_subclass_constructor_calling_super_is_not_a_second_registration(tmp_path: Path):
    """A subclass's `<init>` calls its superclass's — `invokespecial` to a constructor, the
    same instruction a `new` compiles to — and constructs nothing. Read as a second route it
    would turn every conditional base class with a subclass `unresolved`.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("prod")`
    holds in `prod`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `prod`."""
    base = ORDERS + "BaseSync#"
    child = ORDERS + "ChildSync#"
    facts = [
        *_type(base, [_marker(SERVICE), _profile("prod")]),
        *_type(child, superclass=base),
        CallSiteFact(
            document_id="doc",
            caller=_MODULE + method_descriptor(child, "<init>", _VOID),
            target=CallTarget(owner=base, name="<init>", descriptor=_VOID),
            invoke_kind="special",
            ordinal=0,
            result=None,
        ),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    assert _verdicts(beans, base) == {
        "default": ("class", None, "profile", "unresolved", "unresolved"),
        "prod": ("class", None, "profile", "true", "resolved"),
    }


# --- a stereotype or a condition through a COMPOSED annotation (CP-44 row 5) --------------


@pytest.mark.pins("beans.a-COMPOSED-stereotype-or-condition-is-followed")
def test_a_module_local_composed_stereotype_makes_a_conditional_class_a_bean(tmp_path: Path):
    """`@MyService` is the module's own annotation, meta-annotated `@Service`. The scanner
    matches meta-annotations, so `@MyService @Profile("prod") Orders` is a scanned bean — and
    the annotation type itself, which carries `@Service`, is no bean.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("prod")`
    holds in `prod`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `prod`."""
    my_service = ORDERS + "MyService#"
    orders = ORDERS + "Orders#"
    facts = [
        *_type(my_service, [_marker(SERVICE)], kind=ConstructKind.ANNOTATION),
        *_type(orders, [AnnotationUse(annotation=my_service, args={}), _profile("prod")]),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    assert _verdicts(beans, orders) == {
        "default": ("class", None, "profile", "unresolved", "unresolved"),
        "prod": ("class", None, "profile", "true", "resolved"),
    }
    assert {r["bean"] for r in beans} == {_MODULE + orders}


def test_a_stereotype_through_a_dependency_annotations_recorded_header_makes_a_bean(
    tmp_path: Path,
):
    """Review finding 1's real input, reduced: an auto-configuration annotation from a jar,
    whose header the classpath read recorded as meta-annotated `@Configuration`. Nothing
    names that annotation in code; its header makes the class a configuration bean, and the
    class's own `@ConditionalOnProperty` conditions it.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `orders.legacy` is
    set by the deployment (CP-47), so the condition is not evaluated in any environment,
    whatever the module's files set; what this test pins is which bean carries it."""
    auto = "org/acme/boot/AutoConfig#"
    wiring = ORDERS + "OrdersAutoConfiguration#"
    facts = [
        TypeHeaderFact(
            document_id="doc",
            symbol="sextant-jvm maven org.acme/boot 1.0.0 " + auto,
            construct_kind=ConstructKind.ANNOTATION,
            annotations=[_marker(CONFIGURATION)],
            origin="org.acme:boot",
            version="1.0.0",
        ),
        *_type(
            wiring,
            [AnnotationUse(annotation=auto, args={}), _on_property("orders.legacy", "true")],
        ),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    assert _verdicts(beans, wiring) == {
        "default": ("class", None, "property", "unresolved", "unresolved"),
        "prod": ("class", None, "property", "unresolved", "unresolved"),
    }


@pytest.mark.pins("beans.a-COMPOSED-stereotype-or-condition-is-followed")
def test_a_condition_carried_on_a_composed_annotation_conditions_its_users(tmp_path: Path):
    """`@LegacyOnly` is the module's own annotation carrying `@ConditionalOnProperty(name =
    "orders.legacy", havingValue = "true")`; a `@Service @LegacyOnly` class carries that
    condition, its arguments folded from the composition.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `orders.legacy` is
    set by the deployment (CP-47), so the condition is not evaluated in any environment,
    whatever the module's files set; what this test pins is which bean carries it."""
    legacy_only = ORDERS + "LegacyOnly#"
    orders = ORDERS + "LegacyOrders#"
    facts = [
        *_type(
            legacy_only,
            [_on_property("orders.legacy", "true")],
            kind=ConstructKind.ANNOTATION,
        ),
        *_type(orders, [_marker(SERVICE), AnnotationUse(annotation=legacy_only, args={})]),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    assert _verdicts(beans, orders) == {
        "default": ("class", None, "property", "unresolved", "unresolved"),
        "prod": ("class", None, "property", "unresolved", "unresolved"),
    }


# --- a lambda a conditional factory creates is that factory's code -----------------------

_METAFACTORY = "java/lang/invoke/LambdaMetafactory#"
_GET_FOR_OBJECT = "(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;"


def _outbound_call(caller: str, ordinal: int = 0) -> CallSiteFact:
    """`restTemplate.getForObject("/billing/balances/{id}", String.class)` in `caller`."""
    return CallSiteFact(
        document_id="doc",
        caller=_MODULE + caller,
        target=CallTarget(owner=RESTTEMPLATE, name="getForObject", descriptor=_GET_FOR_OBJECT),
        invoke_kind="virtual",
        ordinal=ordinal,
        receiver=3,
        result=12,
        arguments=[
            CallArgument(kind="string", value="/billing/balances/{id}"),
            CallArgument(kind="class", symbol="java/lang/String#"),
            CallArgument(kind="unresolved"),
        ],
    )


@pytest.mark.pins("beans.a-LAMBDA-a-factory-creates-is-the-factorys-code")
def test_a_lambda_a_conditional_factory_creates_carries_the_factorys_condition(
    tmp_path: Path,
):
    """Review finding 2. `@Bean @Profile("prod") Runnable sync() { return () ->
    rest.getForObject(…); }` in an unconditional configuration class: the lambda body is
    the factory's code, read off the `dynamic` call edge from `sync` to it (never off its
    name). Its outbound row carries the factory's condition, `via` the factory — not the
    configuration class's (none).

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("prod")`
    holds in `prod`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `prod`."""
    wiring = ORDERS + "SyncConfig#"
    runnable = "java/lang/Runnable#"
    factory = method_descriptor(wiring, "sync", "()Ljava/lang/Runnable;")
    body = method_descriptor(wiring, "lambda$sync$0", _VOID)
    facts = [
        *_type(wiring, [_marker(CONFIGURATION)]),
        *_method(wiring, "sync", runnable, [_marker(BEAN), _profile("prod")], []),
        CallSiteFact(
            document_id="doc",
            caller=_MODULE + factory,
            target=CallTarget(owner=_METAFACTORY, name="metafactory", descriptor=_VOID),
            invoke_kind="dynamic",
            ordinal=0,
            result=4,
            implementation=body,
            arguments=[CallArgument(kind="lambda", symbol=body)],
        ),
        SymbolFact(
            document_id="doc",
            symbol=_MODULE + body,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + wiring,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
            modifiers={"synthetic": True},
        ),
        MethodReturnFact(document_id="doc", method=_MODULE + body, ordinal=0, value=None),
        _outbound_call(body),
    ]
    workspace = _resolved(tmp_path, facts, "spring-resttemplate")
    beans = workspace.query("bean_conditions")
    viewed = workspace.query("endpoint_conditions")
    workspace.close()

    assert _verdicts(beans, body) == {
        "default": ("factory", _MODULE + factory, "profile", "unresolved", "unresolved"),
        "prod": ("factory", _MODULE + factory, "profile", "true", "resolved"),
    }
    assert {(r["caller"], r["via"], r["environment"], r["holds"]) for r in viewed} == {
        (_MODULE + body, _MODULE + factory, "default", "unresolved"),
        (_MODULE + body, _MODULE + factory, "prod", "true"),
    }


@pytest.mark.pins("beans.a-FACTORY-methods-own-body-is-the-factorys-code")
def test_a_row_made_in_a_conditional_factorys_own_body_states_the_factorys_condition(
    tmp_path: Path,
):
    """OI-108's case. `@Bean @Profile("local") Runnable flow() { rest.getForObject(…); … }` in
    an unconditional configuration class: the row's code symbol IS the factory method, so
    the owner class (no rows) is the wrong bean. The method is a bean of its own, `via`
    itself, and the row exists only in `local` — the same mechanism a lambda it creates
    uses.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("local")`
    holds in `local`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `local`."""
    wiring = ORDERS + "AdapterConfig#"
    runnable = "java/lang/Runnable#"
    factory = method_descriptor(wiring, "flow", "()Ljava/lang/Runnable;")
    facts = [
        *_type(wiring, [_marker(CONFIGURATION)]),
        *_method(wiring, "flow", runnable, [_marker(BEAN), _profile("local")], []),
        _outbound_call(factory),
    ]
    workspace = _resolved(tmp_path, facts, "spring-resttemplate", environments=("local",))
    beans = workspace.query("bean_conditions")
    viewed = workspace.query("endpoint_conditions")
    workspace.close()

    assert _verdicts(beans, factory) == {
        "default": ("factory", _MODULE + factory, "profile", "unresolved", "unresolved"),
        "local": ("factory", _MODULE + factory, "profile", "true", "resolved"),
    }
    assert {(r["caller"], r["via"], r["environment"], r["holds"]) for r in viewed} == {
        (_MODULE + factory, _MODULE + factory, "default", "unresolved"),
        (_MODULE + factory, _MODULE + factory, "local", "true"),
    }


def test_a_call_to_a_conditional_factory_method_is_answered_by_the_methods_own_bean(
    tmp_path: Path,
):
    """Whole-branch review, minor: a call naming a `@Bean @Profile("local")` method maps the
    method to its OWN bean — the method, on the factory's route — never to its configuration
    class, which carries no condition. A direct call is `resolved`, so `candidate_presence`
    lists no row for it (a site is listed only when narrowed, or answered by an interface
    bean) and the trace reads as it always did; where a subclass configuration overrides the
    method, the call narrows to both bodies and `candidate_presence` states the base method's
    own presence: `local` only, while the override exists everywhere.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("local")`
    holds in `local`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `local`."""
    wiring = ORDERS + "AdapterConfig#"
    override = ORDERS + "LocalAdapterConfig#"
    runnable = "java/lang/Runnable#"
    returns = "()Ljava/lang/Runnable;"
    factory = _MODULE + method_descriptor(wiring, "flow", returns)
    overriding = _MODULE + method_descriptor(override, "flow", returns)
    service = ORDERS + "OrderService#"
    send = method_descriptor(service, "send", _VOID)

    def call(kind: str) -> CallSiteFact:
        return CallSiteFact(
            document_id="doc",
            caller=_MODULE + send,
            target=CallTarget(owner=wiring, name="flow", descriptor=returns),
            invoke_kind=kind,
            ordinal=0,
            result=None,
        )

    facts = [
        *_type(wiring, [_marker(CONFIGURATION)]),
        *_method(wiring, "flow", runnable, [_marker(BEAN), _profile("local")], []),
        *_type(service, [_marker(SERVICE)]),
        *_body(service, "send"),
    ]
    direct = _resolved(tmp_path / "direct", [*facts, call("static")], environments=("local",))
    [edge] = [r for r in direct.query("call_edges") if r["caller"] == _MODULE + send]
    mapped = {r["symbol"]: r["bean"] for r in direct.query("symbol_beans")}
    listed = direct.query("candidate_presence")
    direct.close()

    assert (edge["callee"], edge["resolution"]) == (factory, "resolved")
    assert mapped[factory] == factory
    assert listed == []

    subclassed = [
        *facts,
        *_type(override, [_marker(CONFIGURATION)], superclass=wiring),
        *_method(override, "flow", runnable, [_marker(BEAN)], []),
        call("virtual"),
    ]
    narrowed = _resolved(tmp_path / "narrowed", subclassed, environments=("local",))
    candidates = {
        (r["callee"], r["environment"]): (r["bean"], r["holds"])
        for r in narrowed.query("candidate_presence")
    }
    narrowed.close()

    assert candidates == {
        (factory, "default"): (factory, "unresolved"),
        (factory, "local"): (factory, "true"),
        (overriding, "default"): (None, "true"),
        (overriding, "local"): (None, "true"),
    }


# --- the view tells two routes of one bean apart -----------------------------------------


def test_two_exclusive_factories_rows_on_one_endpoint_carry_distinct_via(tmp_path: Path):
    """Review finding 3. `KafkaOrderPublisher#send` makes an outbound call and the class is
    registered by a `prod` factory and a `staging` one. Read as "every row must hold", the
    row would exist nowhere; `via` tells the two routes apart, and `bean_presence` — not the
    rows — says where the row exists.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): each profile is
    decided only in its own environment, so the `staging` route holds in `staging` and is
    not evaluated elsewhere, and the class exists, decided, in `prod` and `staging` only."""
    staging = ORDERS + "StagingConfig#"
    send = method_descriptor(KAFKA, "send", _VOID)
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(KAFKA, interfaces=(PUBLISHER,)),
        SymbolFact(
            document_id="doc",
            symbol=_MODULE + send,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + KAFKA,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
        ),
        _outbound_call(send),
        *_type(MESSAGING, [_marker(CONFIGURATION)]),
        *_method(MESSAGING, "publisher", PUBLISHER, [_marker(BEAN), _profile("prod")], [KAFKA]),
        *_type(staging, [_marker(CONFIGURATION)]),
        *_method(staging, "publisher", PUBLISHER, [_marker(BEAN), _profile("staging")], [KAFKA]),
    ]
    workspace = _resolved(tmp_path, facts, "spring-resttemplate", environments=("prod", "staging"))
    viewed = workspace.query("endpoint_conditions")
    presence = _presence(workspace, KAFKA)
    workspace.close()

    assert {(r["via"], r["bean_kind"]) for r in viewed} == {
        (_factory_symbol(MESSAGING, "publisher", PUBLISHER), "factory"),
        (_factory_symbol(staging, "publisher", PUBLISHER), "factory"),
    }
    assert {
        (r["environment"], r["holds"])
        for r in viewed
        if r["via"].startswith(_factory_symbol(staging, "publisher", PUBLISHER))
    } == {("default", "unresolved"), ("prod", "unresolved"), ("staging", "true")}
    assert presence == {
        "default": ("unresolved", "unresolved"),
        "prod": ("true", "resolved"),
        "staging": ("true", "resolved"),
    }


def test_a_bean_left_open_by_an_unfilled_placeholder_says_the_value_is_unknown(
    tmp_path: Path,
):
    """Minor: `orders.legacy: ${ORDERS_LEGACY}` with nothing filling it. Where the bean's only
    route is open for that reason, `bean_presence` says the configured value is unknown — not
    that the condition is one this analysis does not evaluate.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `orders.legacy` is
    set by the deployment, so it is not evaluated in either environment; the evidence is the
    module's own reading, which in `default` is a placeholder it does not fill and in `prod`
    the value its file sets."""
    orders = ORDERS + "LegacyOrders#"
    facts = [*_type(orders, [_marker(SERVICE), _on_property("orders.legacy", "true")])]
    workspace = _resolved(tmp_path, facts, default_legacy="${ORDERS_LEGACY}")
    rows = {
        str(r["environment"]): r
        for r in workspace.query("bean_presence")
        if r["bean"] == _MODULE + orders
    }
    workspace.close()

    assert (rows["default"]["holds"], rows["default"]["resolution"]) == ("unresolved", "unresolved")
    assert str(rows["default"]["evidence"]) == (
        "`orders.legacy` is set by the deployment; this module's `default` configuration sets "
        "a placeholder this module does not fill"
    )
    assert "does not evaluate" not in str(rows["default"]["evidence"])
    assert (rows["prod"]["holds"], rows["prod"]["evidence"]) == (
        "unresolved",
        "`orders.legacy` is set by the deployment; this module's `prod` configuration sets `true`",
    )


def test_a_condition_annotation_is_not_composed_through_what_it_is_built_on(tmp_path: Path):
    """Measured on `yudao-spring-boot-starter-websocket`: the classpath header of
    `@ConditionalOnProperty` records `@Conditional(OnPropertyCondition.class)`. A condition
    the model names is decided by its own rule; composing through it added an unevaluated
    `other` row to every direct use and turned a decided bean `unresolved`."""
    on_property = "org/springframework/boot/autoconfigure/condition/ConditionalOnProperty#"
    orders = ORDERS + "LegacyOrders#"
    facts = [
        TypeHeaderFact(
            document_id="doc",
            symbol="sextant-jvm maven org.springframework.boot/spring-boot-autoconfigure 2.7.18 "
            + on_property,
            construct_kind=ConstructKind.ANNOTATION,
            annotations=[
                AnnotationUse(
                    annotation="org/springframework/context/annotation/Conditional#",
                    args={"value": ["org/acme/OnPropertyCondition#"]},
                )
            ],
            origin="org.springframework.boot:spring-boot-autoconfigure",
            version="2.7.18",
        ),
        *_type(orders, [_marker(SERVICE), _on_property("orders.legacy", "true")]),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    assert {r["kind"] for r in beans} == {"property"}


@pytest.mark.pins("beans.a-LAMBDA-a-factory-creates-is-the-factorys-code")
def test_a_new_inside_a_lambda_a_factory_creates_is_that_factorys_construction(
    tmp_path: Path,
):
    """Round 1's ruling applied to construction: `@Bean @Profile("prod") OrderPublisher
    publisher() { return lazily(() -> new KafkaOrderPublisher()); }`. The lambda body is the
    factory's code, so the `new` in it is the factory's — `KafkaOrderPublisher` is a `factory`
    bean `via` `publisher`, absent outside `prod`, and never a plain `new` leaving it open.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("prod")`
    holds in `prod`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `prod`."""
    publisher = method_descriptor(MESSAGING, "publisher", "()L" + PUBLISHER.removesuffix("#") + ";")
    body = method_descriptor(MESSAGING, "lambda$publisher$0", _VOID)
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(KAFKA, interfaces=(PUBLISHER,)),
        *_type(MESSAGING, [_marker(CONFIGURATION)]),
        *_method(MESSAGING, "publisher", PUBLISHER, [_marker(BEAN), _profile("prod")], []),
        CallSiteFact(
            document_id="doc",
            caller=_MODULE + publisher,
            target=CallTarget(owner=_METAFACTORY, name="metafactory", descriptor=_VOID),
            invoke_kind="dynamic",
            ordinal=0,
            result=4,
            implementation=body,
            arguments=[CallArgument(kind="lambda", symbol=body)],
        ),
        SymbolFact(
            document_id="doc",
            symbol=_MODULE + body,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + MESSAGING,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
            modifiers={"synthetic": True},
        ),
        MethodReturnFact(document_id="doc", method=_MODULE + body, ordinal=0, value=None),
        CallSiteFact(
            document_id="doc",
            caller=_MODULE + body,
            target=CallTarget(owner=KAFKA, name="<init>", descriptor=_VOID),
            invoke_kind="special",
            ordinal=0,
            result=None,
        ),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    presence = _presence(workspace, KAFKA)
    workspace.close()

    assert _verdicts(beans, KAFKA) == {
        "default": ("factory", _MODULE + publisher, "profile", "unresolved", "unresolved"),
        "prod": ("factory", _MODULE + publisher, "profile", "true", "resolved"),
    }
    assert presence == {"default": ("unresolved", "unresolved"), "prod": ("true", "resolved")}


# --- `@ConditionalOnMissingBean` / `@ConditionalOnBean` from the module's own beans (§2c) ---
#
# CP-44 rows 1-3, 6: `value`/`type` are one set of types; `name` and `annotation` are separate
# criteria; `@ConditionalOnBean` needs every criterion matched, `@ConditionalOnMissingBean`
# fails on any; an unannotated use on a `@Bean` method checks its declared return type; the
# search sees what is registered so far, which is why every verdict here is `partial`.

MISSING = "org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean#"
PRESENT = "org/springframework/boot/autoconfigure/condition/ConditionalOnBean#"
ON_CLASS = "org/springframework/boot/autoconfigure/condition/ConditionalOnClass#"
SPI = "com/acme/auth/"
USER_SERVICE = SPI + "UserService#"
DEFAULT_USERS = SPI + "DefaultUserService#"
LDAP_USERS = SPI + "LdapUserService#"
LOCAL_USERS = SPI + "LocalUserService#"
AUDIT = SPI + "UserAudit#"
AUTH = SPI + "AuthConfiguration#"
_PARTIAL = "decided from this module's beans only; a library or the processing order may differ"
_ORDER = "Spring keeps whichever is processed first; the order is not in the code"
_NEITHER = "neither bean sees the other registered, so both fail whatever the order"
# An open presence verdict whose competitor's own existence is open (spec 2026-10-23
# deployment-set-conditions: a profile-gated competitor, outside its own environment).
_OPEN_COMPETITOR = (
    "not decided from this module's beans: a competing bean's own existence here is open"
)


def _missing(**args: object) -> AnnotationUse:
    return AnnotationUse(annotation=MISSING, args=args)


def _present(**args: object) -> AnnotationUse:
    return AnnotationUse(annotation=PRESENT, args=args)


def _users(*implementations: str) -> list[object]:
    """`interface UserService` and each implementation of it, unannotated."""
    facts = _type(USER_SERVICE, kind=ConstructKind.INTERFACE)
    for implementation in implementations:
        facts += _type(implementation, interfaces=(USER_SERVICE,))
    return facts


def _default_beside_ldap(default_uses: list[AnnotationUse]) -> list[object]:
    """`@Configuration AuthConfiguration` with a default `@Bean UserService defaultUserService()
    { return new DefaultUserService(); }` under `default_uses`, beside `@Bean @Profile("ldap")
    UserService ldapUserService() { return new LdapUserService(); }`."""
    return [
        *_users(DEFAULT_USERS, LDAP_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), *default_uses],
            [DEFAULT_USERS],
        ),
        *_method(
            AUTH, "ldapUserService", USER_SERVICE, [_marker(BEAN), _profile("ldap")], [LDAP_USERS]
        ),
    ]


_COMPETITORS = "; competitors: "


def _presence_rows(workspace: DuckDbWorkspace, bean: str) -> dict[str, tuple[object, ...]]:
    """environment -> (holds, resolution, the stated reason) of the bean's presence rows; the
    reason is the evidence before its competitor list (`_competitors` reads that)."""
    return {
        str(r["environment"]): (
            r["holds"],
            r["resolution"],
            str(r["evidence"]).split(_COMPETITORS, 1)[0],
        )
        for r in workspace.query("bean_conditions")
        if r["bean"] == _MODULE + bean and r["kind"] == "presence"
    }


def _competitors(workspace: DuckDbWorkspace, bean: str, via: str | None = None) -> dict:
    """environment -> the competitor list a presence row's evidence carries, as JSON."""
    return {
        str(r["environment"]): json.loads(str(r["evidence"]).split(_COMPETITORS, 1)[1])
        for r in workspace.query("bean_conditions")
        if r["bean"] == _MODULE + bean
        and r["kind"] == "presence"
        and (via is None or r["via"] == via)
    }


@pytest.mark.pins("beans.MISSING-BEAN-reads-the-modules-competitors")
@pytest.mark.pins("beans.every-presence-verdict-is-PARTIAL")
def test_a_missing_bean_default_exists_everywhere_but_where_the_override_registers(
    tmp_path: Path,
):
    """The brief's case, Apollo's `AuthConfiguration` reduced: the default `UserService` is
    `@ConditionalOnMissingBean(UserService.class)` and the override is `@Profile("ldap")`. The
    default's class exists in every environment but `ldap`, decided from this module's own
    beans — `partial`, with that reason, never `resolved`.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the `ldap` override's
    `@Profile("ldap")` is decided only in `ldap`, where it holds; in `default` the
    deployment may activate `ldap`, so the competitor's own existence is open there and so
    is this verdict."""
    facts = _default_beside_ldap([_missing(value=[USER_SERVICE])])
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    [expression] = {
        r["expression"]
        for r in workspace.query("bean_conditions")
        if r["bean"] == _MODULE + DEFAULT_USERS and r["kind"] == "presence"
    }
    presence = _presence(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows == {
        "default": ("unresolved", "unresolved", _OPEN_COMPETITOR),
        "ldap": ("false", "partial", _PARTIAL),
    }
    assert json.loads(str(expression)) == {
        "annotation": MISSING,
        "mode": "missing",
        "types": [USER_SERVICE],
        "names": [],
        "annotations": [],
    }
    assert presence == {"default": ("unresolved", "unresolved"), "ldap": ("false", "partial")}


def test_on_bean_is_the_inverse_of_on_missing_bean(tmp_path: Path):
    """`@Bean @ConditionalOnBean(UserService.class) UserAudit userAudit()` beside the `ldap`
    override alone: the audit exists only where a `UserService` does — `ldap` — `partial`.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the `ldap` override's
    `@Profile("ldap")` is decided only in `ldap`, where it holds; in `default` the
    deployment may activate `ldap`, so the competitor's own existence is open there and so
    is this verdict."""
    facts = [
        *_users(LDAP_USERS),
        *_type(AUDIT),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH, "ldapUserService", USER_SERVICE, [_marker(BEAN), _profile("ldap")], [LDAP_USERS]
        ),
        *_method(
            AUTH, "userAudit", AUDIT, [_marker(BEAN), _present(value=[USER_SERVICE])], [AUDIT]
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, AUDIT)
    workspace.close()

    assert rows == {
        "default": ("unresolved", "unresolved", _OPEN_COMPETITOR),
        "ldap": ("true", "partial", _PARTIAL),
    }


def test_two_missing_bean_defaults_are_unresolved(tmp_path: Path):
    """Review focus 3. Two `@Bean`s each `@ConditionalOnMissingBean(UserService.class)`, both
    otherwise unconditional: Spring registers whichever it processes first and skips the other,
    and which is first is not in the code — `unresolved` for both, never a pick."""
    facts = [
        *_users(DEFAULT_USERS, LOCAL_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
        *_method(
            AUTH,
            "localUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [LOCAL_USERS],
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    first = _presence_rows(workspace, DEFAULT_USERS)
    second = _presence_rows(workspace, LOCAL_USERS)
    workspace.close()

    for rows in (first, second):
        assert {(holds, resolution) for holds, resolution, _ in rows.values()} == {
            ("unresolved", "unresolved")
        }
        assert all(_ORDER in str(evidence) for _, _, evidence in rows.values())
        assert set(rows) == {"default", "ldap"}


def test_two_missing_bean_defaults_decide_where_one_of_them_is_absent(tmp_path: Path):
    """The mutual case is open only where BOTH defaults' other conditions hold: with the
    second under `@Profile("!ldap")`, in `ldap` it is absent for its own reason and the first
    is decided — present, `partial`; in `default` both stay open, by the order.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("ldap")`
    would no longer make the second absent anywhere — it is decided only in `ldap`, where it
    holds — so the second is under `@Profile("!ldap")`, which `ldap`'s own name decides: it
    fails there, and the first is decided present; in `default` the deployment decides, and
    both stay open, by the order."""
    facts = [
        *_users(DEFAULT_USERS, LOCAL_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
        *_method(
            AUTH,
            "localUserService",
            USER_SERVICE,
            [_marker(BEAN), _profile("!ldap"), _missing(value=[USER_SERVICE])],
            [LOCAL_USERS],
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows["ldap"] == ("true", "partial", _PARTIAL)
    assert rows["default"][:2] == ("unresolved", "unresolved")
    assert _ORDER in str(rows["default"][2])


def test_a_competitor_under_an_unevaluated_condition_leaves_the_default_unresolved(
    tmp_path: Path,
):
    """The override is `@ConditionalOnClass(name = "com.unboundid.ldap.sdk.LDAPConnection")` —
    a classpath question this analysis does not answer — so whether a `UserService` competes
    is unknown in every environment, and the default's verdict is `unresolved` there."""
    facts = [
        *_users(DEFAULT_USERS, LDAP_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
        *_method(
            AUTH,
            "ldapUserService",
            USER_SERVICE,
            [
                _marker(BEAN),
                AnnotationUse(
                    annotation=ON_CLASS, args={"name": ["com.unboundid.ldap.sdk.LDAPConnection"]}
                ),
            ],
            [LDAP_USERS],
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    workspace.close()

    assert {(holds, resolution) for holds, resolution, _ in rows.values()} == {
        ("unresolved", "unresolved")
    }


def test_an_unannotated_missing_bean_checks_the_factorys_return_type(tmp_path: Path):
    """CP-44 row 1: `@Bean @ConditionalOnMissingBean UserService defaultUserService()` names no
    type, name or annotation, so Spring checks the method's declared return type — the same
    verdict as naming `UserService` outright.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the `ldap` override's
    `@Profile("ldap")` is decided only in `ldap`, where it holds; in `default` the
    deployment may activate `ldap`, so the competitor's own existence is open there and so
    is this verdict."""
    facts = _default_beside_ldap([_missing()])
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    [expression] = {
        r["expression"]
        for r in workspace.query("bean_conditions")
        if r["bean"] == _MODULE + DEFAULT_USERS and r["kind"] == "presence"
    }
    workspace.close()

    assert rows == {
        "default": ("unresolved", "unresolved", _OPEN_COMPETITOR),
        "ldap": ("false", "partial", _PARTIAL),
    }
    assert json.loads(str(expression))["types"] == [USER_SERVICE]


def test_an_unconditional_subtype_competitor_makes_the_default_absent_everywhere(
    tmp_path: Path,
):
    """`@Service LdapUserService implements UserService`, scanned and unconditional, is a bean
    OF `UserService` — its registered type is a subtype of the criterion — so the default
    fails in every environment. Still `partial`: a presence verdict always is."""
    facts = [
        *_users(DEFAULT_USERS),
        *_type(LDAP_USERS, [_marker(SERVICE)], interfaces=(USER_SERVICE,)),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows == {
        "default": ("false", "partial", _PARTIAL),
        "ldap": ("false", "partial", _PARTIAL),
    }


def test_a_missing_bean_whose_only_competitor_a_profile_gates_is_decided_only_in_that_profile(
    tmp_path: Path,
):
    """Spec 2026-10-23-deployment-set-conditions §3b: the presence rule is unchanged, and it
    propagates what its competitors' conditions now say. The `ldap` override's `@Profile`
    is decided only in `ldap`, where it holds, so the default FAILS there; in `default` and
    `local` the deployment may activate `ldap`, so the default is open. A competitor with no
    condition at all is decided by the code alone, and still decides it everywhere."""
    gated = _default_beside_ldap([_missing(value=[USER_SERVICE])])
    workspace = _resolved(tmp_path / "gated", gated, environments=("ldap", "local"))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    workspace.close()
    unconditional = [
        *_users(DEFAULT_USERS),
        *_type(LDAP_USERS, [_marker(SERVICE)], interfaces=(USER_SERVICE,)),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
    ]
    workspace = _resolved(tmp_path / "plain", unconditional, environments=("ldap", "local"))
    decided = _presence_rows(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows["ldap"] == ("false", "partial", _PARTIAL)
    for environment in ("default", "local"):
        assert rows[environment][:2] == ("unresolved", "unresolved")
        assert str(rows[environment][2]).startswith("not decided from this module's beans")
    assert decided == {
        environment: ("false", "partial", _PARTIAL) for environment in ("default", "ldap", "local")
    }


def test_a_factory_declared_as_the_supertype_is_no_bean_of_the_subtype(tmp_path: Path):
    """The search matches a factory by its DECLARED return type (CP-44 row 3, `isTypeMatch`
    on the definition, nothing instantiated): `ldapUserService()` returns `UserService`, so it
    is no bean of `LdapUserService`, and `@ConditionalOnMissingBean(LdapUserService.class)`
    holds everywhere."""
    facts = _default_beside_ldap([_missing(value=[LDAP_USERS])])
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows == {
        "default": ("true", "partial", _PARTIAL),
        "ldap": ("true", "partial", _PARTIAL),
    }


@pytest.mark.parametrize(
    ("override", "name", "expected"),
    [
        # A factory is named by its method (or `@Bean(name)`, CP-27 row 14).
        ("factory", "ldapUserService", "false"),
        ("factory", "somethingElse", "true"),
        # A scanned class by its simple name uncapitalised (CP-44 row 6)...
        ("scanned", "ldapUserService", "false"),
        # ...or by its stereotype's naming attribute when it gives one.
        ("named", "directory", "false"),
        ("named", "ldapUserService", "true"),
    ],
)
def test_a_name_criterion_matches_a_bean_by_its_name(
    tmp_path: Path, override: str, name: str, expected: str
):
    """`@ConditionalOnMissingBean(name = …)` asks `containsBean` (CP-44 row 2): it matches the
    `ldap` override by the override's own bean NAME, whatever its type.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the `ldap` override's
    `@Profile("ldap")` is decided only in `ldap`, where it holds; in `default` the
    deployment may activate `ldap`, so where the override is a matching competitor this
    verdict is open there. A name that matches no competitor still decides it."""
    facts = [
        *_users(DEFAULT_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(name=[name])],
            [DEFAULT_USERS],
        ),
    ]
    if override == "factory":
        facts += [
            *_type(LDAP_USERS, interfaces=(USER_SERVICE,)),
            *_method(
                AUTH,
                "ldapUserService",
                USER_SERVICE,
                [_marker(BEAN), _profile("ldap")],
                [LDAP_USERS],
            ),
        ]
    else:
        stereotype = (
            AnnotationUse(annotation=SERVICE, args={"value": "directory"})
            if override == "named"
            else _marker(SERVICE)
        )
        facts += _type(LDAP_USERS, [stereotype, _profile("ldap")], interfaces=(USER_SERVICE,))
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows["default"] == (
        ("true", "partial", _PARTIAL)
        if expected == "true"
        else ("unresolved", "unresolved", _OPEN_COMPETITOR)
    )
    assert rows["ldap"] == (expected, "partial", _PARTIAL)


def test_an_annotation_criterion_matches_a_bean_whose_class_carries_it(tmp_path: Path):
    """`@ConditionalOnBean(annotation = Directory.class)`: a separate criterion (CP-44 row 2),
    matched by the competitor's class carrying the annotation.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the `ldap` override's
    `@Profile("ldap")` is decided only in `ldap`, where it holds; in `default` the
    deployment may activate `ldap`, so where the override is a matching competitor this
    verdict is open there."""
    directory = SPI + "Directory#"
    facts = [
        *_type(directory, kind=ConstructKind.ANNOTATION),
        *_users(),
        *_type(
            LDAP_USERS,
            [_marker(SERVICE), _marker(directory), _profile("ldap")],
            interfaces=(USER_SERVICE,),
        ),
        *_type(AUDIT),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH, "userAudit", AUDIT, [_marker(BEAN), _present(annotation=[directory])], [AUDIT]
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, AUDIT)
    workspace.close()

    assert rows == {
        "default": ("unresolved", "unresolved", _OPEN_COMPETITOR),
        "ldap": ("true", "partial", _PARTIAL),
    }


def test_on_bean_needs_every_criterion_and_on_missing_bean_fails_on_any(tmp_path: Path):
    """CP-44 row 2: `isAllMatched` against `isAnyMatched`. A type the `ldap` override has and a
    name nothing has: `@ConditionalOnBean` of both fails everywhere; `@ConditionalOnMissingBean`
    of both fails in `ldap`, where the type matches.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the `ldap` override's
    `@Profile("ldap")` is decided only in `ldap`, where it holds; in `default` the
    deployment may activate `ldap`, so where the override is a matching competitor this
    verdict is open there. `@ConditionalOnBean` still fails everywhere: its name criterion
    has no competitor at all."""
    facts = [
        *_users(DEFAULT_USERS, LDAP_USERS),
        *_type(AUDIT),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH, "ldapUserService", USER_SERVICE, [_marker(BEAN), _profile("ldap")], [LDAP_USERS]
        ),
        *_method(
            AUTH,
            "userAudit",
            AUDIT,
            [_marker(BEAN), _present(value=[USER_SERVICE], name=["nobody"])],
            [AUDIT],
        ),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE], name=["nobody"])],
            [DEFAULT_USERS],
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    audit = _presence_rows(workspace, AUDIT)
    default = _presence_rows(workspace, DEFAULT_USERS)
    workspace.close()

    assert {e: v[0] for e, v in audit.items()} == {"default": "false", "ldap": "false"}
    assert {e: v[0] for e, v in default.items()} == {"default": "unresolved", "ldap": "false"}


def test_a_missing_bean_on_a_configuration_class_does_not_count_its_own_factories(
    tmp_path: Path,
):
    """`@Configuration @ConditionalOnMissingBean(UserService.class) Fallback` with `@Bean
    UserService fallbackUserService()`: the class's condition is judged before its own `@Bean`s
    are read (CP-44 row 4), so they are no competitor of it — only the `ldap` override is, and
    the fallback's class carries the configuration's verdict.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the `ldap` override's
    `@Profile("ldap")` is decided only in `ldap`, where it holds; in `default` the
    deployment may activate `ldap`, so where the override is a matching competitor this
    verdict is open there."""
    fallback = SPI + "Fallback#"
    facts = [
        *_users(DEFAULT_USERS, LDAP_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH, "ldapUserService", USER_SERVICE, [_marker(BEAN), _profile("ldap")], [LDAP_USERS]
        ),
        *_type(fallback, [_marker(CONFIGURATION), _missing(value=[USER_SERVICE])]),
        *_method(fallback, "fallbackUserService", USER_SERVICE, [_marker(BEAN)], [DEFAULT_USERS]),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = [
        r
        for r in workspace.query("bean_conditions")
        if r["bean"] == _MODULE + DEFAULT_USERS and r["kind"] == "presence"
    ]
    workspace.close()

    assert {(r["bean_kind"], r["environment"], r["holds"], r["resolution"]) for r in rows} == {
        ("configuration", "default", "unresolved", "unresolved"),
        ("configuration", "ldap", "false", "partial"),
    }


def test_a_resolved_route_decides_presence_over_a_partial_one(tmp_path: Path):
    """`bean_presence`'s precedence: a class the presence rule leaves `partial` on one route
    but that an unconditional scan also registers exists everywhere, `resolved` — the partial
    route decides nothing there."""
    facts = _default_beside_ldap([_missing(value=[USER_SERVICE])])
    facts = [
        f
        for f in facts
        if not (isinstance(f, AnnotationFact) and f.target == _MODULE + DEFAULT_USERS)
    ]
    facts += _annotated(DEFAULT_USERS, [_marker(COMPONENT)])
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    presence = _presence(workspace, DEFAULT_USERS)
    workspace.close()

    assert presence == {"default": ("true", "resolved"), "ldap": ("true", "resolved")}


# --- review round: same-class routes, the competitor list, chains and loops --------------


@pytest.mark.pins("beans.a-SAME-CLASS-route-is-never-a-competitor")
def test_two_routes_of_one_class_never_compete_with_each_other(tmp_path: Path):
    """Ruled at review: the condition asks whether ANOTHER bean of the type exists. Two
    factories both returning `new DefaultUserService()` — one `@ConditionalOnMissingBean
    (UserService.class)`, one `@ConditionalOnClass` — register the same class, so the second
    is no competitor of the first: the first holds, and the class exists, `partial`."""
    facts = [
        *_users(DEFAULT_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "one",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
        *_method(
            AUTH,
            "two",
            USER_SERVICE,
            [_marker(BEAN), AnnotationUse(annotation=ON_CLASS, args={"name": ["x.Y"]})],
            [DEFAULT_USERS],
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    presence = _presence(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows == {
        "default": ("true", "partial", _PARTIAL),
        "ldap": ("true", "partial", _PARTIAL),
    }
    assert presence == {"default": ("true", "partial"), "ldap": ("true", "partial")}


@pytest.mark.pins("beans.a-SAME-CLASS-route-is-never-a-competitor")
def test_two_missing_bean_routes_of_one_class_exist_in_every_order(tmp_path: Path):
    """Two `@ConditionalOnMissingBean(UserService.class)` factories of the SAME class: whichever
    Spring keeps, the class exists — no order question, so no `unresolved`."""
    facts = [
        *_users(DEFAULT_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "one",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
        *_method(
            AUTH,
            "two",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    presence = _presence(workspace, DEFAULT_USERS)
    workspace.close()

    assert presence == {"default": ("true", "partial"), "ldap": ("true", "partial")}


def test_the_evidence_lists_the_competitors_and_a_profile_no_environment_activates(
    tmp_path: Path,
):
    """Ruled at review: a presence verdict's evidence names, after its reason, the competitors
    that decided it — as JSON. Here the module resolves only `default`, so the `ldap` override
    is absent everywhere and the default holds; the row says so, and says `ldap` is a profile
    the module names but no environment file activates (OI-168's boundary).

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("ldap")` is
    not evaluated in `default` — the deployment may activate `ldap` — so the override is
    listed as open there, not absent, and the default is open with it; the note naming the
    missing `ldap` environment stands."""
    facts = _default_beside_ldap([_missing(value=[USER_SERVICE])])
    workspace = _resolved(tmp_path, facts, environments=())
    rows = _presence_rows(workspace, DEFAULT_USERS)
    listed = _competitors(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows == {"default": ("unresolved", "unresolved", _OPEN_COMPETITOR)}
    assert listed == {
        "default": [
            {
                "bean": _MODULE + LDAP_USERS,
                "via": _factory_symbol(AUTH, "ldapUserService", USER_SERVICE),
                "holds": "unresolved",
                "note": "profile `ldap` is named but this module has no `ldap` environment",
            }
        ]
    }


def test_the_evidence_names_the_competitor_that_exists(tmp_path: Path):
    """Where the override exists the default fails, and its row names the override as the
    bean that decided it — no note, since `ldap` is an environment here."""
    facts = _default_beside_ldap([_missing(value=[USER_SERVICE])])
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    listed = _competitors(workspace, DEFAULT_USERS)
    workspace.close()

    assert listed["ldap"] == [
        {
            "bean": _MODULE + LDAP_USERS,
            "via": _factory_symbol(AUTH, "ldapUserService", USER_SERVICE),
            "holds": "true",
        }
    ]


def test_an_open_verdict_names_the_competitor_that_leaves_it_open(tmp_path: Path):
    """The override under `@ConditionalOnClass`: the default's verdict is open, and its
    evidence names that override as `unresolved` rather than claiming a decision."""
    facts = [
        *_users(DEFAULT_USERS, LDAP_USERS),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(
            AUTH,
            "defaultUserService",
            USER_SERVICE,
            [_marker(BEAN), _missing(value=[USER_SERVICE])],
            [DEFAULT_USERS],
        ),
        *_method(
            AUTH,
            "ldapUserService",
            USER_SERVICE,
            [_marker(BEAN), AnnotationUse(annotation=ON_CLASS, args={"name": ["x.Y"]})],
            [LDAP_USERS],
        ),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = _presence_rows(workspace, DEFAULT_USERS)
    listed = _competitors(workspace, DEFAULT_USERS)
    workspace.close()

    assert rows["default"] == (
        "unresolved",
        "unresolved",
        "not decided from this module's beans: a competing bean's own existence here is open",
    )
    assert listed["default"] == [
        {
            "bean": _MODULE + LDAP_USERS,
            "via": _factory_symbol(AUTH, "ldapUserService", USER_SERVICE),
            "holds": "unresolved",
        }
    ]


def test_a_chain_of_presence_conditions_is_decided_in_dependency_order(tmp_path: Path):
    """A `@ConditionalOnMissingBean(Notifier)` waits on B `@ConditionalOnBean(Channel)`, which
    waits on C `@Profile("ldap")`. In `ldap` C exists, so B does, so A does not; elsewhere
    the reverse — each `partial` but C's own, which is a profile.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): C's
    `@Profile("ldap")` is decided only in `ldap`; in `default` the deployment may activate
    it, so the openness propagates down the chain and B and A are both open there."""
    notifier = SPI + "Notifier#"
    channel = SPI + "Channel#"
    a, b, c = SPI + "Fallback#", SPI + "MailNotifier#", SPI + "SmtpChannel#"
    facts = [
        *_type(notifier, kind=ConstructKind.INTERFACE),
        *_type(channel, kind=ConstructKind.INTERFACE),
        *_type(a),
        *_type(b, interfaces=(notifier,)),
        *_type(c, interfaces=(channel,)),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(AUTH, "a", a, [_marker(BEAN), _missing(value=[notifier])], [a]),
        *_method(AUTH, "b", notifier, [_marker(BEAN), _present(value=[channel])], [b]),
        *_method(AUTH, "c", channel, [_marker(BEAN), _profile("ldap")], [c]),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    first, second = _presence(workspace, a), _presence(workspace, b)
    workspace.close()

    assert second == {"default": ("unresolved", "unresolved"), "ldap": ("true", "partial")}
    assert first == {"default": ("unresolved", "unresolved"), "ldap": ("false", "partial")}


def test_two_on_bean_conditions_waiting_on_each_other_both_fail(tmp_path: Path):
    """`@ConditionalOnBean(Channel)` on a `Notifier` factory and `@ConditionalOnBean(Notifier)`
    on a `Channel` factory: whichever Spring reads first finds the other not yet registered and
    skips, so the second finds nothing too — both absent in every order, `partial`, with that
    reason rather than the order one."""
    notifier = SPI + "Notifier#"
    channel = SPI + "Channel#"
    b, c = SPI + "MailNotifier#", SPI + "SmtpChannel#"
    facts = [
        *_type(notifier, kind=ConstructKind.INTERFACE),
        *_type(channel, kind=ConstructKind.INTERFACE),
        *_type(b, interfaces=(notifier,)),
        *_type(c, interfaces=(channel,)),
        *_type(AUTH, [_marker(CONFIGURATION)]),
        *_method(AUTH, "b", notifier, [_marker(BEAN), _present(value=[channel])], [b]),
        *_method(AUTH, "c", channel, [_marker(BEAN), _present(value=[notifier])], [c]),
    ]
    workspace = _resolved(tmp_path, facts, environments=("ldap",))
    rows = {bean: _presence_rows(workspace, bean) for bean in (b, c)}
    workspace.close()

    for per_environment in rows.values():
        assert {(h, r) for h, r, _ in per_environment.values()} == {("false", "partial")}
        assert all(_NEITHER in str(reason) for _, _, reason in per_environment.values())
        assert all(_ORDER not in str(reason) for _, _, reason in per_environment.values())


# --- an inherited body runs as part of every bean that resolves the method to it -------

SENDER = ORDERS + "Sender#"
ABSTRACT_SENDER = ORDERS + "AbstractSender#"
LOCAL_SENDER = ORDERS + "LocalSender#"
KAFKA_SENDER = ORDERS + "KafkaSender#"
NOTICES = ORDERS + "NoticeService#"
_LEGACY_KEY = "orders.legacy"


def _legacy_is(having: str, *, match_if_missing: bool = False) -> AnnotationUse:
    return AnnotationUse(
        annotation="org/springframework/boot/autoconfigure/condition/ConditionalOnProperty#",
        args={"name": [_LEGACY_KEY], "havingValue": having, "matchIfMissing": match_if_missing},
    )


def _body(owner: str, name: str) -> list[object]:
    """A `void name()` declared on `owner` whose body was read."""
    symbol = _MODULE + method_descriptor(owner, name, _VOID)
    return [
        SymbolFact(
            document_id="doc",
            symbol=symbol,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + owner,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
        ),
        MethodReturnFact(document_id="doc", method=symbol, ordinal=0, value=None),
    ]


def _declaration(owner: str, name: str) -> SymbolFact:
    """An abstract `void name()` on `owner` — declared, no body."""
    return SymbolFact(
        document_id="doc",
        symbol=_MODULE + method_descriptor(owner, name, _VOID),
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
    )


def _calls(caller: str, owner: str, name: str, ordinal: int = 0) -> list[object]:
    """`caller` (a `@Service` method, declared here) calls `owner#name()` through the
    interface, so dispatch narrows to every body that can answer."""
    return [
        CallSiteFact(
            document_id="doc",
            caller=_MODULE + caller,
            target=CallTarget(owner=owner, name=name, descriptor=_VOID),
            invoke_kind="interface",
            ordinal=ordinal,
            result=None,
        ),
    ]


def _senders(*extra: object) -> list[object]:
    """`interface Sender { void send(); void flush(); }`; `abstract class AbstractSender
    implements Sender` with bodies for both; `@Component @ConditionalOnProperty(orders.legacy,
    havingValue = "false", matchIfMissing = true) LocalSender extends AbstractSender`
    overriding `flush` only; `@Component @ConditionalOnProperty(orders.legacy, havingValue =
    "true") KafkaSender extends AbstractSender` overriding both. `NoticeService#push` calls
    `Sender#send` and `Sender#flush`."""
    push = method_descriptor(NOTICES, "push", _VOID)
    return [
        *_type(SENDER, kind=ConstructKind.INTERFACE),
        _declaration(SENDER, "send"),
        _declaration(SENDER, "flush"),
        *_type(ABSTRACT_SENDER, interfaces=(SENDER,)),
        *_body(ABSTRACT_SENDER, "send"),
        *_body(ABSTRACT_SENDER, "flush"),
        *_type(
            LOCAL_SENDER,
            [_marker(COMPONENT), _legacy_is("false", match_if_missing=True)],
            superclass=ABSTRACT_SENDER,
        ),
        *_body(LOCAL_SENDER, "flush"),
        *_type(KAFKA_SENDER, [_marker(COMPONENT), _legacy_is("true")], superclass=ABSTRACT_SENDER),
        *_body(KAFKA_SENDER, "send"),
        *_body(KAFKA_SENDER, "flush"),
        *_type(NOTICES, [_marker(SERVICE)]),
        *_body(NOTICES, "push"),
        *_calls(push, SENDER, "send", 0),
        *_calls(push, SENDER, "flush", 1),
        *extra,
    ]


def test_an_inherited_body_exists_exactly_where_the_bean_that_inherits_it_does(tmp_path: Path):
    """ruoyi's `WebSocketSenderApiImpl#send`, reduced: `AbstractSender#send` has no bean of
    its own — it runs as part of `LocalSender`, the one bean whose class resolves `send` to
    it (JVMS 5.4.3.3, the module's own `Dispatch.resolve`). So the candidate exists where
    `LocalSender` does (`default`, the key `false`), and `KafkaSender#send` where `KafkaSender`
    does (`prod`) — never "everywhere" because its abstract class carries no condition.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): ruoyi's beans are
    gated on a property the deployment sets, so neither sender's existence is evaluated
    anywhere, and the verdicts no longer tell the two heirs apart. The inherited body's own
    rows still do: they are `LocalSender`'s route, copied under the body, and never
    `KafkaSender`'s."""
    workspace = _resolved(tmp_path, _senders())
    inherited = _MODULE + method_descriptor(ABSTRACT_SENDER, "send", _VOID)
    overriding = _MODULE + method_descriptor(KAFKA_SENDER, "send", _VOID)
    abstract_presence = _presence(workspace, method_descriptor(ABSTRACT_SENDER, "send", _VOID))
    routes = {r["via"] for r in workspace.query("bean_conditions") if r["bean"] == inherited}
    local_presence = _presence(workspace, LOCAL_SENDER)
    mapped = {r["symbol"]: r["bean"] for r in workspace.query("symbol_beans")}
    candidates = {
        (r["callee"], r["environment"]): (r["bean"], r["holds"], r["resolution"])
        for r in workspace.query("candidate_presence")
        if r["ordinal"] == 0
    }
    workspace.close()

    assert local_presence == {
        "default": ("unresolved", "unresolved"),
        "prod": ("unresolved", "unresolved"),
    }
    assert abstract_presence == local_presence
    assert routes == {_MODULE + LOCAL_SENDER}
    assert mapped[inherited] == inherited
    assert mapped[overriding] == _MODULE + KAFKA_SENDER
    assert candidates == {
        (inherited, "default"): (inherited, "unresolved", "unresolved"),
        (inherited, "prod"): (inherited, "unresolved", "unresolved"),
        (overriding, "default"): (_MODULE + KAFKA_SENDER, "unresolved", "unresolved"),
        (overriding, "prod"): (_MODULE + KAFKA_SENDER, "unresolved", "unresolved"),
    }


def test_an_inherited_body_no_bean_resolves_to_is_unresolved(tmp_path: Path):
    """`AbstractSender#flush` is overridden by both beans under it, so no bean of the module
    runs it: `unresolved`, and the evidence says why."""
    workspace = _resolved(tmp_path, _senders())
    flush = method_descriptor(ABSTRACT_SENDER, "flush", _VOID)
    presence = {
        str(r["environment"]): (r["holds"], r["resolution"], r["evidence"])
        for r in workspace.query("bean_presence")
        if r["bean"] == _MODULE + flush
    }
    workspace.close()

    reason = "no bean of this module runs this inherited body"
    assert presence == {
        "default": ("unresolved", "unresolved", reason),
        "prod": ("unresolved", "unresolved", reason),
    }


@pytest.mark.pins("beans.an-INHERITED-body-takes-the-OR-of-the-beans-that-run-it")
def test_an_interface_default_method_exists_wherever_any_bean_inheriting_it_does(
    tmp_path: Path,
):
    """`interface Greeter { default void greet() {…} }` implemented, without overriding, by
    `@Component @Profile("prod") EnGreeter` and `@Component @Profile("staging") FrGreeter`:
    the default body runs as part of both, so it exists where either does — the OR.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): each profile is
    decided only in its own environment, so the body exists, decided, in `prod` and
    `staging`, and is not evaluated in `default`."""
    greeter, en, fr = ORDERS + "Greeter#", ORDERS + "EnGreeter#", ORDERS + "FrGreeter#"
    hello = method_descriptor(NOTICES, "hello", _VOID)
    facts = [
        *_type(greeter, kind=ConstructKind.INTERFACE),
        *_body(greeter, "greet"),
        *_type(en, [_marker(COMPONENT), _profile("prod")], interfaces=(greeter,)),
        *_type(fr, [_marker(COMPONENT), _profile("staging")], interfaces=(greeter,)),
        *_type(NOTICES, [_marker(SERVICE)]),
        *_body(NOTICES, "hello"),
        *_calls(hello, greeter, "greet"),
    ]
    workspace = _resolved(tmp_path, facts, environments=("prod", "staging"))
    presence = _presence(workspace, method_descriptor(greeter, "greet", _VOID))
    workspace.close()

    assert presence == {
        "default": ("unresolved", "unresolved"),
        "prod": ("true", "resolved"),
        "staging": ("true", "resolved"),
    }


def test_an_inherited_body_with_an_unconditional_heir_exists_everywhere(tmp_path: Path):
    """An unconditional bean among the heirs makes the body exist everywhere, `resolved`:
    nothing is written for it, exactly as for a body of an unconditional bean."""
    greeter, en, plain = ORDERS + "Greeter#", ORDERS + "EnGreeter#", ORDERS + "PlainGreeter#"
    hello = method_descriptor(NOTICES, "hello", _VOID)
    facts = [
        *_type(greeter, kind=ConstructKind.INTERFACE),
        *_body(greeter, "greet"),
        *_type(en, [_marker(COMPONENT), _profile("prod")], interfaces=(greeter,)),
        *_type(plain, [_marker(COMPONENT)], interfaces=(greeter,)),
        *_type(NOTICES, [_marker(SERVICE)]),
        *_body(NOTICES, "hello"),
        *_calls(hello, greeter, "greet"),
    ]
    workspace = _resolved(tmp_path, facts)
    greet = _MODULE + method_descriptor(greeter, "greet", _VOID)
    beans = {r["bean"] for r in workspace.query("bean_conditions")}
    workspace.close()

    assert greet not in beans


def test_a_narrowed_site_lists_an_inherited_body_with_an_unconditional_heir_as_present_everywhere(
    tmp_path: Path,
):
    """The narrowed variant of the test above: `EnGreeter` (`@Profile("prod")`) overrides
    `greet`, so the call narrows to two bodies — its own, and `Greeter`'s default body, which
    runs as part of `PlainGreeter`. The default body belongs to no bean of its own, so the
    bean map has no row for it, and `candidate_presence` lists it with no bean, present in
    every environment (an unconditional heir)."""
    greeter, en, plain = ORDERS + "Greeter#", ORDERS + "EnGreeter#", ORDERS + "PlainGreeter#"
    hello = method_descriptor(NOTICES, "hello", _VOID)
    facts = [
        *_type(greeter, kind=ConstructKind.INTERFACE),
        *_body(greeter, "greet"),
        *_type(en, [_marker(COMPONENT), _profile("prod")], interfaces=(greeter,)),
        *_body(en, "greet"),
        *_type(plain, [_marker(COMPONENT)], interfaces=(greeter,)),
        *_type(NOTICES, [_marker(SERVICE)]),
        *_body(NOTICES, "hello"),
        *_calls(hello, greeter, "greet"),
    ]
    workspace = _resolved(tmp_path, facts)
    inherited = _MODULE + method_descriptor(greeter, "greet", _VOID)
    mapped = {r["symbol"] for r in workspace.query("symbol_beans")}
    candidates = {
        (r["callee"], r["environment"]): (r["bean"], r["holds"])
        for r in workspace.query("candidate_presence")
    }
    workspace.close()

    assert inherited not in mapped
    assert candidates[(inherited, "default")] == (None, "true")
    assert candidates[(inherited, "prod")] == (None, "true")


# --- an environment's ACTIVE profiles, read from configuration (CP-45; Task 7b) ----------
#
# The keys come from the shipped config model (`config_model.profiles`), never from here.

_PROFILES = next(c for c in _catalogs("spring-web") if c.config_model).config_model["profiles"]
_PETCLINIC = ("default", "h2", "hsqldb", "mysql", "postgres")
_OPEN_IN_A_PROFILE_FILE = (
    "named only in the base's `spring.profiles.active`; the activation selecting this "
    "environment decides it"
)


def _active(base: dict[str, str | None], environments: tuple[str, ...], **raw: list[str]):
    config = {environment: dict(base) for environment in environments}
    unfilled = {key.replace("__", "."): values for key, values in raw.items()}
    return active_profiles(config, _PROFILES, list(environments), unfilled)


def _profile_verdict(names: list[str], active) -> tuple[str, str]:
    return _holds(PROFILE, {"expressions": names}, {}, "unused", active)


def test_the_base_environment_is_active_in_the_profiles_its_configuration_lists():
    """spring-petclinic-rest: `spring.profiles.active=h2,spring-data-jpa`. In the base
    environment both are active, `default` is not (CP-45 row 5: the default profiles are
    accepted only where none is active), and a profile named nowhere is not."""
    active = _active({"spring.profiles.active": "h2, spring-data-jpa"}, _PETCLINIC)

    assert _profile_verdict(["spring-data-jpa"], active["default"]) == (HOLDS, "resolved")
    assert _profile_verdict(["h2"], active["default"]) == (HOLDS, "resolved")
    assert _profile_verdict(["jdbc"], active["default"]) == (FAILS, "resolved")
    assert _profile_verdict(["default"], active["default"]) == (FAILS, "resolved")


def test_a_profile_named_only_in_the_bases_active_list_is_open_in_a_profile_file_environment():
    """In `h2` or `mysql` the activation selecting the file (a command line, an environment
    variable) replaces or extends the base's list, and which it does is the deployment's — so
    `spring-data-jpa` is `unresolved` there, the file's own profile holds, and a profile named
    in neither is not active."""
    active = _active({"spring.profiles.active": "h2,spring-data-jpa"}, _PETCLINIC)

    assert _profile_verdict(["h2"], active["h2"]) == (HOLDS, "resolved")
    assert _profile_verdict(["spring-data-jpa"], active["h2"]) == (UNRESOLVED, "unresolved")
    assert _profile_verdict(["spring-data-jpa"], active["mysql"]) == (UNRESOLVED, "unresolved")
    assert _profile_verdict(["h2"], active["mysql"]) == (UNRESOLVED, "unresolved")
    assert _profile_verdict(["jdbc"], active["mysql"]) == (FAILS, "resolved")
    assert _profile_holds({"expressions": ["spring-data-jpa"]}, active["mysql"]) == (
        UNRESOLVED,
        "unresolved",
        _OPEN_IN_A_PROFILE_FILE,
    )


def test_the_reason_a_profile_is_open_names_no_environment_so_one_line_states_them_all():
    """Whole-branch review, minor: spring-petclinic-rest's four profile environments leave
    `spring-data-jpa` open for one reason — the activation selecting each decides it. A reason
    naming its environment made four reasons of it, so a site read four near-identical "not
    evaluated" lines; worded without the name, the reason is one string and the document's
    shared-reason grouping states the four environments on one line."""
    active = _active({"spring.profiles.active": "h2,spring-data-jpa"}, _PETCLINIC)
    reasons = {
        environment: _profile_holds({"expressions": ["spring-data-jpa"]}, active[environment])[2]
        for environment in _PETCLINIC
        if environment != "default"
    }

    assert set(reasons.values()) == {_OPEN_IN_A_PROFILE_FILE}


def test_an_unfilled_placeholder_leaves_every_profile_not_otherwise_decided_open():
    """Apollo: `spring.profiles.active: ${apollo_profile}`, which nothing in the module
    fills. `ldap` is `unresolved` in every environment, the file's own profile holds in its
    environment, and the evidence names the placeholder."""
    environments = ("default", "github", "ldap-openldap-sample")
    active = _active(
        {"spring.profiles.active": None},
        environments,
        spring__profiles__active=["${apollo_profile}"],
    )

    for environment in environments:
        assert _profile_verdict(["ldap"], active[environment]) == (UNRESOLVED, "unresolved")
    assert _profile_verdict(["github"], active["github"]) == (HOLDS, "resolved")
    assert _profile_verdict(["github"], active["default"]) == (UNRESOLVED, "unresolved")
    assert _profile_holds({"expressions": ["oidc"]}, active["github"])[2] == (
        "the active profiles here come from `${apollo_profile}`, which this module does not fill"
    )


def test_with_no_profile_key_set_an_environment_is_its_own_profile_only():
    """PR #61's behaviour exactly: `default` is active in the base environment alone, and a
    profile file's environment is its own profile."""
    active = _active({"orders.legacy": "true"}, ("default", "prod"))

    assert _profile_verdict(["default"], active["default"]) == (HOLDS, "resolved")
    assert _profile_verdict(["default"], active["prod"]) == (FAILS, "resolved")
    assert _profile_verdict(["prod"], active["prod"]) == (HOLDS, "resolved")
    assert _profile_verdict(["prod"], active["default"]) == (FAILS, "resolved")
    assert _profile_verdict(["!prod"], active["default"]) == (HOLDS, "resolved")


def test_an_included_profile_is_active_in_every_environment():
    """CP-45 row 6: `spring.profiles.include` joins the active list whatever it is, so it is
    active in a profile file's environment too — and, being active, keeps `default` from
    being accepted in the base."""
    active = _active({"spring.profiles.include": "metrics"}, ("default", "prod"))

    assert _profile_verdict(["metrics"], active["default"]) == (HOLDS, "resolved")
    assert _profile_verdict(["metrics"], active["prod"]) == (HOLDS, "resolved")
    assert _profile_verdict(["default"], active["default"]) == (FAILS, "resolved")


def test_the_default_profiles_key_names_the_profile_active_where_none_is():
    active = _active({"spring.profiles.default": "local"}, ("default", "prod"))

    assert _profile_verdict(["local"], active["default"]) == (HOLDS, "resolved")
    assert _profile_verdict(["default"], active["default"]) == (FAILS, "resolved")
    assert _profile_verdict(["local"], active["prod"]) == (FAILS, "resolved")


def test_a_yaml_list_names_each_profile():
    """CP-45 row 4: the key binds as a list too, which the config reader flattens to
    `spring.profiles.active[0]`, `[1]`."""
    active = _active(
        {"spring.profiles.active[0]": "h2", "spring.profiles.active[1]": "spring-data-jpa"},
        ("default", "h2"),
    )

    assert _profile_verdict(["spring-data-jpa"], active["default"]) == (HOLDS, "resolved")
    assert _profile_verdict(["spring-data-jpa"], active["h2"]) == (UNRESOLVED, "unresolved")


def test_a_negated_open_profile_stays_open_and_any_of_takes_a_holding_term():
    active = _active({"spring.profiles.active": "h2,spring-data-jpa"}, _PETCLINIC)

    assert _profile_verdict(["!spring-data-jpa"], active["mysql"]) == (UNRESOLVED, "unresolved")
    assert _profile_verdict(["!spring-data-jpa"], active["default"]) == (FAILS, "resolved")
    assert _profile_verdict(["jdbc", "spring-data-jpa"], active["mysql"]) == (
        UNRESOLVED,
        "unresolved",
    )
    assert _profile_verdict(["mysql", "spring-data-jpa"], active["mysql"]) == (HOLDS, "resolved")
    assert _profile_verdict(["jdbc", "jpa"], active["mysql"]) == (FAILS, "resolved")


@pytest.mark.pins("beans.a-PROFILE-GROUP-expands-an-active-profile")
def test_a_profile_group_makes_its_members_active_wherever_its_name_is():
    """Apollo's `apollo-portal`: `spring.profiles.group.github = mysql` (CP-45 row 8,
    `expandProfiles`). Wherever `github` is active `mysql` is too, and `github` stays active
    itself — in the `github` file's environment, and in the base where its active list names
    `github`. Where `github` is not active, neither is `mysql`."""
    environments = ("default", "github", "h2")
    active = _active(
        {"spring.profiles.active": "github", "spring.profiles.group.github": "mysql"},
        environments,
    )
    filed = _active({"spring.profiles.group.github": "mysql"}, environments)

    assert _profile_verdict(["mysql"], filed["github"]) == (HOLDS, "resolved")
    assert _profile_verdict(["github"], filed["github"]) == (HOLDS, "resolved")
    assert _profile_verdict(["mysql"], filed["h2"]) == (FAILS, "resolved")
    assert _profile_verdict(["mysql"], filed["default"]) == (FAILS, "resolved")
    assert _profile_verdict(["mysql"], active["default"]) == (HOLDS, "resolved")


def test_a_profile_group_under_an_unknown_activation_stays_unknown():
    """`github` is named only in the base's active list, so in the `h2` file's environment
    whether it is active is the deployment's — and so is whether its group's `mysql` is: the
    member takes the activating profile's certainty, with the reason naming the group."""
    active = _active(
        {"spring.profiles.active": "github", "spring.profiles.group.github": "mysql"},
        ("default", "h2"),
    )

    assert _profile_verdict(["mysql"], active["h2"]) == (UNRESOLVED, "unresolved")
    assert "the group `github`" in _profile_holds({"expressions": ["mysql"]}, active["h2"])[2]
    assert _profile_verdict(["h2"], active["h2"]) == (HOLDS, "resolved")


def test_a_profile_group_is_followed_transitively_and_a_cycle_terminates():
    """jhipster's shape — a group as a YAML list (`spring.profiles.group.dev[0]`, `[1]`) —
    with a group of a group, and two groups naming each other: each profile is expanded once,
    as `expandProfiles` adds it, so the walk ends."""
    active = _active(
        {
            "spring.profiles.group.dev[0]": "secret-samples",
            "spring.profiles.group.dev[1]": "api-docs",
            "spring.profiles.group.api-docs": "swagger",
            "spring.profiles.group.a": "b",
            "spring.profiles.group.b": "a",
        },
        ("default", "dev", "a"),
    )

    for name in ("dev", "secret-samples", "api-docs", "swagger"):
        assert _profile_verdict([name], active["dev"]) == (HOLDS, "resolved")
    assert _profile_verdict(["swagger"], active["a"]) == (FAILS, "resolved")
    assert _profile_verdict(["b"], active["a"]) == (HOLDS, "resolved")
    assert _profile_verdict(["a"], active["a"]) == (HOLDS, "resolved")


@pytest.mark.pins("beans.ACTIVE-PROFILES-are-read-from-configuration")
def test_the_pass_reads_the_active_profiles_from_the_resolved_configuration(tmp_path: Path):
    """Through `resolve_config` and the shipped catalog: petclinic's shape. The Spring Data
    JPA repository exists in the base environment and is open in the profile file's, its
    evidence naming why; the JDBC one exists nowhere.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the active profiles
    the configuration lists are now the EVIDENCE, never the verdict — the deployment sets
    them (CP-47) — so neither repository is evaluated in either environment, and every
    environment's evidence states one reading, the module's own activation as read for
    its base environment (ruled at review)."""
    jpa, jdbc = ORDERS + "SpringDataOwnerRepository#", ORDERS + "JdbcOwnerRepository#"
    facts = [
        *_type(jpa, [_marker(COMPONENT), _profile("spring-data-jpa")]),
        *_type(jdbc, [_marker(COMPONENT), _profile("jdbc")]),
    ]
    workspace = _resolved(
        tmp_path,
        facts,
        environments=("mysql",),
        base={"spring.profiles.active": "h2,spring-data-jpa"},
    )
    rows = workspace.query("bean_conditions")
    presence = {
        (r["bean"], r["environment"]): (r["holds"], r["evidence"])
        for r in workspace.query("bean_presence")
    }
    workspace.close()

    assert _verdicts(rows, jpa) == {
        "default": ("class", None, "profile", "unresolved", "unresolved"),
        "mysql": ("class", None, "profile", "unresolved", "unresolved"),
    }
    assert _verdicts(rows, jdbc) == {
        "default": ("class", None, "profile", "unresolved", "unresolved"),
        "mysql": ("class", None, "profile", "unresolved", "unresolved"),
    }
    own = (
        "active profiles are set by the deployment; this module's own default is "
        "`h2,spring-data-jpa`"
    )
    for bean in (jpa, jdbc):
        for environment in ("default", "mysql"):
            assert presence[(_MODULE + bean, environment)] == ("unresolved", own)


def test_the_pass_names_the_placeholder_the_active_profiles_come_from(tmp_path: Path):
    """Apollo's shape through the whole pass: the evidence names `${apollo_profile}`, read
    off the configuration the module ships.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): the placeholder
    reason survives as the evidence, after the statement that the deployment sets the active
    profiles."""
    ldap = ORDERS + "LdapUserService#"
    facts = [*_type(ldap, [_marker(SERVICE), _profile("ldap")])]
    workspace = _resolved(
        tmp_path,
        facts,
        environments=("github",),
        base={"spring.profiles.active": "${apollo_profile}"},
    )
    presence = {
        r["environment"]: (r["holds"], r["evidence"])
        for r in workspace.query("bean_presence")
        if r["bean"] == _MODULE + ldap
    }
    workspace.close()

    reason = (
        "active profiles are set by the deployment; the active profiles here come from "
        "`${apollo_profile}`, which this module does not fill"
    )
    assert presence == {"default": ("unresolved", reason), "github": ("unresolved", reason)}


# --- an interface the framework implements at run time (CP-46; Task 7b fix ruling 1) ------

_REPOSITORY = "org/springframework/data/repository/Repository#"
_NO_REPOSITORY_BEAN = "org/springframework/data/repository/NoRepositoryBean#"
_REPOSITORY_DEFINITION = "org/springframework/data/repository/RepositoryDefinition#"
_STEREO_REPOSITORY = "org/springframework/stereotype/Repository#"
OWNERS = ORDERS + "OwnerRepository#"
SPRING_DATA_OWNERS = ORDERS + "SpringDataOwnerRepository#"
JDBC_OWNERS = ORDERS + "JdbcOwnerRepositoryImpl#"
CLINIC = ORDERS + "ClinicService#"


def _owner_repositories(*extra: object) -> list[object]:
    """spring-petclinic-rest's shape: `interface OwnerRepository { void save(); }`;
    `@Profile("spring-data-jpa") interface SpringDataOwnerRepository extends OwnerRepository,
    Repository<Owner, Integer>`; `@Repository @Profile("jdbc") JdbcOwnerRepositoryImpl
    implements OwnerRepository`; `@Service ClinicService#saveOwner` calls
    `OwnerRepository#save`."""
    save_owner = method_descriptor(CLINIC, "saveOwner", _VOID)
    return [
        *_type(OWNERS, kind=ConstructKind.INTERFACE),
        _declaration(OWNERS, "save"),
        *_type(
            SPRING_DATA_OWNERS,
            [_profile("spring-data-jpa")],
            kind=ConstructKind.INTERFACE,
            interfaces=(OWNERS, _REPOSITORY),
        ),
        *_type(JDBC_OWNERS, [_marker(_STEREO_REPOSITORY), _profile("jdbc")], interfaces=(OWNERS,)),
        *_body(JDBC_OWNERS, "save"),
        *_type(CLINIC, [_marker(SERVICE)]),
        *_body(CLINIC, "saveOwner"),
        *_calls(save_owner, OWNERS, "save"),
        *extra,
    ]


def _candidates(workspace: DuckDbWorkspace) -> dict[tuple[object, object, str], tuple[str, str]]:
    return {
        (r["callee"], r["bean"], str(r["environment"])): (str(r["holds"]), str(r["resolution"]))
        for r in workspace.query("candidate_presence")
    }


@pytest.mark.pins("beans.an-INTERFACE-the-framework-implements-is-a-route")
def test_a_repository_interface_is_a_bean_whose_implementation_answers_the_call(tmp_path: Path):
    """With `spring.profiles.active=spring-data-jpa`, Spring Data registers a proxy for
    `SpringDataOwnerRepository` in the base environment (CP-46 rows 2, 4, 6), and it answers
    `ClinicService#saveOwner`'s call to `OwnerRepository#save` — beside the JDBC class, which
    exists nowhere here. The call names a body only the JDBC class has, so without the route
    the site would read as answered by nothing in `default`.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): an active profile is
    set by the deployment, so neither repository's existence is evaluated in either
    environment — the module's own `spring-data-jpa` is the evidence, not the verdict. The
    proxy is still a candidate of the call, which is what the route makes it."""
    workspace = _resolved(
        tmp_path,
        _owner_repositories(),
        environments=("mysql",),
        base={"spring.profiles.active": "spring-data-jpa"},
    )
    rows = workspace.query("bean_conditions")
    candidates = _candidates(workspace)
    workspace.close()

    assert _verdicts(rows, SPRING_DATA_OWNERS) == {
        "default": ("proxy", None, "profile", "unresolved", "unresolved"),
        "mysql": ("proxy", None, "profile", "unresolved", "unresolved"),
    }
    proxy = _MODULE + SPRING_DATA_OWNERS
    jdbc = _MODULE + method_descriptor(JDBC_OWNERS, "save", _VOID)
    assert candidates == {
        (None, proxy, "default"): ("unresolved", "unresolved"),
        (None, proxy, "mysql"): ("unresolved", "unresolved"),
        (jdbc, _MODULE + JDBC_OWNERS, "default"): ("unresolved", "unresolved"),
        (jdbc, _MODULE + JDBC_OWNERS, "mysql"): ("unresolved", "unresolved"),
    }
    [evidence] = {
        r["evidence"]
        for r in rows
        if r["bean"] == proxy and r["environment"] == "default" and r["kind"] == "profile"
    }
    assert evidence == (
        "active profiles are set by the deployment; this module's own default is `spring-data-jpa`"
    )


def test_a_no_repository_bean_interface_is_no_bean(tmp_path: Path):
    """CP-46 rows 2-3: `@NoRepositoryBean` refuses the interface carrying it — a base
    repository others extend — and only that one."""
    base = ORDERS + "BaseRepository#"
    facts = [
        *_type(
            base,
            [AnnotationUse(annotation=_NO_REPOSITORY_BEAN, args={}), _profile("prod")],
            kind=ConstructKind.INTERFACE,
            interfaces=(_REPOSITORY,),
        ),
        *_type(
            SPRING_DATA_OWNERS, [_profile("prod")], kind=ConstructKind.INTERFACE, interfaces=(base,)
        ),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = {r["bean"] for r in workspace.query("bean_conditions")}
    interfaces = {r["bean"] for r in workspace.query("interface_beans")}
    workspace.close()

    assert beans == interfaces == {_MODULE + SPRING_DATA_OWNERS}


@pytest.mark.pins("beans.an-INTERFACE-the-framework-implements-is-a-route")
def test_an_interface_marked_repository_definition_is_a_bean_without_extending_repository(
    tmp_path: Path,
):
    """CP-46 row 2: `@RepositoryDefinition` admits an interface that extends nothing — the
    other include filter beside `Repository`'s subtypes — and an interface carrying neither
    stays no bean, whatever condition it carries."""
    plain = ORDERS + "PlainInterface#"
    facts = [
        *_type(
            SPRING_DATA_OWNERS,
            [_marker(_REPOSITORY_DEFINITION), _profile("prod")],
            kind=ConstructKind.INTERFACE,
        ),
        *_type(plain, [_profile("prod")], kind=ConstructKind.INTERFACE),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = {r["bean"] for r in workspace.query("bean_conditions")}
    interfaces = {r["bean"] for r in workspace.query("interface_beans")}
    workspace.close()

    assert beans == interfaces == {_MODULE + SPRING_DATA_OWNERS}


@pytest.mark.pins("beans.an-INTERFACE-the-framework-implements-is-a-route")
def test_a_repository_definition_through_a_composed_annotation_is_a_bean(tmp_path: Path):
    """The registration annotation is composed like a stereotype: `@MyRepository`, the module's
    own annotation meta-annotated `@RepositoryDefinition`, makes the interface carrying it a
    bean, and the annotation type itself is none.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): `@Profile("prod")`
    holds in `prod`, decided by the environment's own name, and is not evaluated in
    `default`, where the deployment may activate `prod`."""
    mine = ORDERS + "MyRepository#"
    facts = [
        *_type(mine, [_marker(_REPOSITORY_DEFINITION)], kind=ConstructKind.ANNOTATION),
        *_type(
            SPRING_DATA_OWNERS,
            [AnnotationUse(annotation=mine, args={}), _profile("prod")],
            kind=ConstructKind.INTERFACE,
        ),
    ]
    workspace = _resolved(tmp_path, facts)
    rows = workspace.query("bean_conditions")
    interfaces = {r["bean"] for r in workspace.query("interface_beans")}
    workspace.close()

    assert interfaces == {_MODULE + SPRING_DATA_OWNERS}
    assert _verdicts(rows, SPRING_DATA_OWNERS) == {
        "default": ("proxy", None, "profile", "unresolved", "unresolved"),
        "prod": ("proxy", None, "profile", "true", "resolved"),
    }


def test_an_unconditional_repository_interface_answers_its_calls_everywhere(tmp_path: Path):
    """No condition on the interface: no `bean_conditions` row (an unconditional bean), and
    its implementation is still a candidate of the call, present in every environment."""
    facts = [
        *_type(OWNERS, kind=ConstructKind.INTERFACE),
        _declaration(OWNERS, "save"),
        *_type(SPRING_DATA_OWNERS, kind=ConstructKind.INTERFACE, interfaces=(OWNERS, _REPOSITORY)),
        *_type(CLINIC, [_marker(SERVICE)]),
        *_body(CLINIC, "saveOwner"),
        *_calls(method_descriptor(CLINIC, "saveOwner", _VOID), OWNERS, "save"),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    candidates = _candidates(workspace)
    workspace.close()

    assert beans == []
    proxy = _MODULE + SPRING_DATA_OWNERS
    assert candidates == {
        (None, proxy, "default"): ("true", "resolved"),
        (None, proxy, "prod"): ("true", "resolved"),
    }


# --- what the exported bundle carries of a condition (D06; the exporter's masking) -------

BILLING = ORDERS + "Billing#"
LIVE_BILLING = ORDERS + "LiveBilling#"
STUB_BILLING = ORDERS + "StubBilling#"
_CHARGES = "https://user:secret@billing.internal/charges"
_VAULT = "https://ops:s3cr3t@vault.internal/token"


def _billing_facts(having: str) -> list[object]:
    """`LiveBilling` under `@ConditionalOnProperty(name = "billing.vault", havingValue =
    having)` calls `https://user:secret@…/charges` (the address set on the row by the caller);
    `StubBilling` is the unconditional other body of `Billing`, and `Notices#push` calls
    through `Billing`, so the site narrows to both."""
    charge = method_descriptor(LIVE_BILLING, "charge", _VOID)
    push = method_descriptor(NOTICES, "push", _VOID)
    on_vault = AnnotationUse(
        annotation="org/springframework/boot/autoconfigure/condition/ConditionalOnProperty#",
        args={"name": ["billing.vault"], "havingValue": having},
    )
    return [
        *_type(BILLING, kind=ConstructKind.INTERFACE),
        _declaration(BILLING, "charge"),
        *_type(LIVE_BILLING, [_marker(COMPONENT), on_vault], interfaces=(BILLING,)),
        *_body(LIVE_BILLING, "charge"),
        CallSiteFact(
            document_id="doc",
            caller=_MODULE + charge,
            target=CallTarget(owner=RESTTEMPLATE, name="getForObject", descriptor=_GET_FOR_OBJECT),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=12,
            arguments=[
                CallArgument(kind="string", value="/charges"),
                CallArgument(kind="class", symbol="java/lang/String#"),
                CallArgument(kind="unresolved"),
            ],
        ),
        *_type(STUB_BILLING, [_marker(COMPONENT)], interfaces=(BILLING,)),
        *_body(STUB_BILLING, "charge"),
        *_type(NOTICES, [_marker(SERVICE)]),
        *_body(NOTICES, "push"),
        *_calls(push, BILLING, "charge"),
    ]


def test_a_conditional_outbound_address_and_condition_argument_are_masked_on_export(
    tmp_path: Path,
):
    """Whole-branch review, Important: the conditions views went out verbatim. A conditional
    client calling `https://user:secret@billing.internal/charges`, under
    `@ConditionalOnProperty(name = "billing.vault", havingValue = "https://ops:s3cr3t@…")` on a
    key whose placeholder nothing fills — so the address reaches `endpoint_conditions.path`,
    and the argument `bean_conditions.expression`, `endpoint_conditions.expression`, and the
    reason `bean_presence` and `candidate_presence` give (the call through `Billing` narrows
    to the live and the stub body). `endpoints.path` and `annotations.args` mask both; no
    exported file may carry either in the clear.

    The address is set on the row WHOLE, `peer` NULL — the shape a base-url composition
    writes (2F design §4) — because a literal URL is split into `peer` and `path`, and
    building a composed client here would test the fluent engine, not the exporter.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 1): a property is set by
    the deployment, so `bean_presence` and `candidate_presence` now give the module's own
    reading as the reason — the placeholder `billing.vault` holds — instead of quoting the
    expression; the argument still reaches both expressions, which is where it is looked
    for."""
    charge = method_descriptor(LIVE_BILLING, "charge", _VOID)
    facts = _billing_facts(_VAULT)
    workspace = _resolved(
        tmp_path, facts, "spring-resttemplate", base={"billing.vault": "${BILLING_VAULT}"}
    )
    workspace._connection.execute(
        "UPDATE endpoints SET path = ?, peer = NULL WHERE caller = ?", [_CHARGES, _MODULE + charge]
    )
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules())
    workspace.close()

    exported = {}
    for table in ("endpoint_conditions", "bean_conditions", "bean_presence", "candidate_presence"):
        exported[table] = duckdb.sql(
            f"SELECT * FROM read_parquet('{bundle / 'graph' / (table + '.parquet')}')"
        ).fetchall()
        assert exported[table], f"{table} exported no row, so this proves nothing"
    assert any("billing.internal/charges" in str(row) for row in exported["endpoint_conditions"])
    assert any("vault.internal" in str(row) for row in exported["bean_conditions"])
    assert any("vault.internal" in str(row) for row in exported["endpoint_conditions"])
    for table in ("bean_presence", "candidate_presence"):
        assert any("`billing.vault` is set by the deployment" in str(r) for r in exported[table])
    for parquet in sorted((bundle / "graph").glob("*.parquet")):
        cells = duckdb.sql(f"SELECT * FROM read_parquet('{parquet}')").fetchall()
        assert not any(
            "user:secret@" in str(cell) or "s3cr3t" in str(cell) for row in cells for cell in row
        ), f"{parquet.name} shipped a credential in the clear"


@pytest.mark.pins("conditions.a-QUOTED-value-is-masked-by-the-modules-own-rules-at-every-exit")
@pytest.mark.parametrize(
    "rules",
    [
        RedactionRules(key_patterns=("vault",)),
        RedactionRules(value_patterns=("^kept-quiet-7$",)),
    ],
    ids=["key-pattern", "value-pattern"],
)
def test_a_quoted_configured_value_is_masked_by_the_modules_own_rules_on_export(
    tmp_path: Path, rules: RedactionRules
):
    """Final review, Important: the bundle masked a condition's evidence by `redact_text`
    alone, which cannot see a key — so `billing.vault`, which the module's `.sextant.yml`
    names a secret (`key_patterns: [vault]`), shipped the value its file sets in the clear,
    and a value pattern anchored on the value alone never matched the sentence quoting it.
    Every table carrying the evidence masks it under the module's own rules."""
    charge = method_descriptor(LIVE_BILLING, "charge", _VOID)
    workspace = _resolved(
        tmp_path,
        _billing_facts("on"),
        "spring-resttemplate",
        base={"billing.vault": "kept-quiet-7"},
    )
    workspace._connection.execute(
        "UPDATE endpoints SET path = ?, peer = NULL WHERE caller = ?", [_CHARGES, _MODULE + charge]
    )
    bundle = tmp_path / "bundle"
    workspace.export_tables(bundle, Redactor.from_rules(rules))
    workspace.close()

    for table in ("endpoint_conditions", "bean_conditions", "bean_presence", "candidate_presence"):
        rows = duckdb.sql(
            f"SELECT evidence FROM read_parquet('{bundle / 'graph' / (table + '.parquet')}')"
        ).fetchall()
        assert any(
            f"this module's `prod` configuration sets `{REDACTED}`" in str(evidence)
            for (evidence,) in rows
        ), table
        assert not any("kept-quiet-7" in str(evidence) for (evidence,) in rows), table


def test_the_shipped_bean_model_states_which_condition_kinds_a_deployment_sets():
    """CP-47: an active profile and a property are set by the deployment (an environment
    variable or a command-line argument outranks any file the module ships), and a bean's
    presence is decided by what the code registers. That is catalog data, not a rule the
    resolve pass knows: `profile` and `property` carry `set_by: deployment`, with the probe
    that measured it beside the probe of the evaluation rule; `presence` carries neither."""
    spring = next(
        c.bean_model
        for c in YamlCatalogSource(CATALOGS).load()
        if c.bean_model.get("id") == "spring"
    )
    models = {model.kind: model for model in _models(spring).values()}

    for kind in ("profile", "property"):
        assert models[kind].members["set_by"] == "deployment"
        assert models[kind].members["set_by_probe"] == (
            "scripts/probes/cp47_deployment_overrides.md"
        )
        assert models[kind].members["by"] != models[kind].members["set_by_probe"]
    assert "set_by" not in models["presence"].members
    assert "set_by" not in models["other"].members


# --- what a deployment can set, the repository does not decide (spec 2026-10-23
# deployment-set-conditions §3b) ----------------------------------------------------------
#
# `_judged` is what the pass publishes: a kind the bean model marks `set_by: deployment` is
# decided only by the environment's own definition, the module's own reading kept as the
# evidence. The models are built here, so the rule is seen to read the data, not Spring.

_BY_DEPLOYMENT = {"set_by": "deployment", "set_by_probe": "probe.md"}
_PROFILE_BY_DEPLOYMENT = ConditionModel(
    kind=PROFILE, annotation="com/acme/Profile#", members={"expressions": "value", **_BY_DEPLOYMENT}
)
_PROPERTY_BY_DEPLOYMENT = ConditionModel(
    kind=PROPERTY, annotation="com/acme/OnProperty#", members=dict(_BY_DEPLOYMENT)
)
_SET_BY_DEPLOYMENT = "active profiles are set by the deployment; "


def _judged_profile(
    names: list[str], environment: str, base: ActiveProfiles
) -> tuple[str, str, str]:
    """`names` judged in `environment` of a module whose BASE environment's own reading is
    `base` — the one reading every environment's evidence states."""
    return _judged(
        _PROFILE_BY_DEPLOYMENT,
        PROFILE,
        {"expressions": names},
        environment,
        {},
        base,
        "default",
        deployment_reading(base, "default"),
    )


def _judged_property(
    keys: list[str], environment: str, config: dict[str, str | None]
) -> tuple[str, str, str]:
    expression = {"keys": keys, "having_value": "true", "match_if_missing": False}
    return _judged(
        _PROPERTY_BY_DEPLOYMENT,
        PROPERTY,
        expression,
        environment,
        config,
        ActiveProfiles(known=frozenset()),
        "default",
        "unused: a property's evidence is its configured value",
    )


def test_a_profile_environment_decides_a_term_naming_itself():
    """In environment `h2`, `@Profile("h2")` holds and `@Profile("!h2")` fails: the
    environment's own definition is the profile file `application-h2.yml`, selected by
    activating `h2`."""
    reading = ActiveProfiles(known=frozenset({"h2", "spring-data-jpa"}))

    assert _judged_profile(["h2"], "h2", reading) == (HOLDS, "resolved", "compiler")
    assert _judged_profile(["!h2"], "h2", reading) == (FAILS, "resolved", "compiler")


@pytest.mark.pins("conditions.a-DEPLOYMENT-set-condition-is-decided-only-by-its-environment")
def test_a_profile_the_deployment_activates_is_not_evaluated_and_states_the_modules_reading():
    """petclinic's `@Profile("jdbc")` in `mysql`: an environment variable or a command-line
    argument can activate `jdbc` (CP-47), so it is not evaluated, and the module's own
    reading is the evidence — what `application.properties` activates, `h2,spring-data-jpa`,
    stated as ONE string in every environment (ruled at review), so the document states the
    five environments on one line (spec §3c)."""
    base = ActiveProfiles(known=frozenset({"h2", "spring-data-jpa"}))

    holds, resolution, evidence = _judged_profile(["jdbc"], "mysql", base)

    assert holds == UNRESOLVED
    assert resolution == "unresolved"
    assert evidence == (
        "active profiles are set by the deployment; this module's own default is "
        "`h2,spring-data-jpa`"
    )
    for environment in ("default", "h2", "hsqldb", "postgres"):
        assert _judged_profile(["jdbc"], environment, base)[2] == evidence


def test_nothing_decides_a_profile_in_the_default_environment():
    """Ruled 1: `default` has no definition of its own to decide by — not even the reserved
    `default` profile, which Spring activates only where the deployment activates none."""
    reading = ActiveProfiles(known=frozenset({"h2", "spring-data-jpa"}))
    named = _SET_BY_DEPLOYMENT + "this module's own default is `h2,spring-data-jpa`"
    none = _SET_BY_DEPLOYMENT + "this module activates none"

    assert _judged_profile(["default"], "default", reading) == (UNRESOLVED, "unresolved", named)
    assert _judged_profile(["!prod"], "default", reading) == (UNRESOLVED, "unresolved", named)
    assert _judged_profile(["h2"], "default", ActiveProfiles(known=frozenset())) == (
        UNRESOLVED,
        "unresolved",
        none,
    )


@pytest.mark.pins("conditions.the-RESERVED-default-profile-is-no-activation-the-module-makes")
def test_a_module_naming_no_profile_activates_none():
    """CP-45 row 5: with no profile key set, the base environment's reading is the reserved
    `default` profile — active there only because the module names none. That is no
    activation the module makes, so the evidence says it activates none; a profile the
    module does name beside it is stated."""
    silent = _active({"orders.legacy": "true"}, ("default", "prod"))
    named = _active({"spring.profiles.default": "local"}, ("default", "prod"))

    assert silent["default"].known == frozenset({"default"})
    assert _judged_profile(["prod"], "default", silent["default"])[2] == (
        "active profiles are set by the deployment; this module activates none"
    )
    assert deployment_reading(named["default"], "default") == (
        "active profiles are set by the deployment; this module's own default is `local`"
    )


def test_a_placeholder_reading_survives_as_the_evidence():
    """Apollo: the module's own reading is that a placeholder nothing fills supplies the
    list. That reason is the evidence, not replaced by a list of names.

    Re-pinned by the final review: a profile the reading names beside the placeholder
    (`github`, here) is stated after the reason, not dropped."""
    reason = (
        "the active profiles here come from `${apollo_profile}`, which this module does not fill"
    )
    reading = ActiveProfiles(known=frozenset({"github"}), otherwise=reason)

    assert _judged_profile(["ldap"], "github", reading) == (
        UNRESOLVED,
        "unresolved",
        _SET_BY_DEPLOYMENT + reason + "; this module's own default is `github`",
    )
    assert _judged_profile(["github"], "github", reading) == (HOLDS, "resolved", "compiler")


@pytest.mark.pins("conditions.a-reading-keeps-BOTH-a-placeholder-and-the-profiles-named-beside-it")
def test_a_reading_naming_a_placeholder_and_a_profile_beside_it_states_both():
    """Final review: `spring.profiles.active: [${APP_PROFILE}, prod]` — the module activates
    `prod` itself AND leaves the rest to a placeholder nothing fills. The reading states both,
    the placeholder's reason and the module's own default, never one in place of the other;
    so does `spring.profiles.include: prod` beside an unfilled `spring.profiles.active`."""
    reason = "the active profiles here come from `${APP_PROFILE}`, which this module does not fill"
    listed = _active(
        {"spring.profiles.active[0]": None, "spring.profiles.active[1]": "prod"},
        ("default", "prod"),
        **{"spring__profiles__active[0]": ["${APP_PROFILE}"]},
    )
    included = _active(
        {"spring.profiles.active": None, "spring.profiles.include": "prod"},
        ("default", "prod"),
        spring__profiles__active=["${APP_PROFILE}"],
    )
    both = _SET_BY_DEPLOYMENT + reason + "; this module's own default is `prod`"

    assert listed["default"] == ActiveProfiles(known=frozenset({"prod"}), otherwise=reason)
    assert deployment_reading(listed["default"], "default") == both
    assert deployment_reading(included["default"], "default") == both


def test_a_property_the_deployment_sets_is_never_decided_and_states_the_files_value():
    """`@ConditionalOnProperty(name = "billing.enabled", havingValue = "true")`: an
    environment variable `BILLING_ENABLED` outranks every file the module ships (CP-47), so
    no environment decides it; the value the module's own configuration resolves is the
    evidence — or that it sets nothing."""
    assert _judged_property(["billing.enabled"], "prod", {"billing.enabled": "false"}) == (
        UNRESOLVED,
        "unresolved",
        (
            "`billing.enabled` is set by the deployment; this module's `prod` configuration sets "
            "`false`"
        ),
    )
    assert _judged_property(["billing.enabled"], "prod", {}) == (
        UNRESOLVED,
        "unresolved",
        (
            "`billing.enabled` is set by the deployment; this module's `prod` configuration sets "
            "nothing"
        ),
    )
    assert _judged_property(["a.on", "b.on"], "default", {"a.on": "true"}) == (
        UNRESOLVED,
        "unresolved",
        (
            "`a.on` is set by the deployment; this module's `default` configuration sets `true`; "
            "`b.on` is set by the deployment; this module's `default` configuration sets nothing"
        ),
    )
    assert _judged_property(["billing.enabled"], "prod", {"billing.enabled": None})[2] == (
        "`billing.enabled` is set by the deployment; this module's `prod` configuration sets "
        "a placeholder this module does not fill"
    )


@pytest.mark.pins("conditions.a-QUOTED-configured-value-is-masked-by-its-key")
def test_a_property_conditions_quoted_value_is_masked_by_its_key():
    """The evidence quotes a configured value, and `bean_conditions` is exported whole with
    its evidence masked only by `redact_text`, which cannot see the key. So the value is
    masked where it is written, by its own key, as every origin of a configured value is:
    `@ConditionalOnProperty("billing.api-token")` must never carry the token."""
    _, _, evidence = _judged_property(
        ["billing.api-token"], "prod", {"billing.api-token": "s3cr3t"}
    )

    assert "s3cr3t" not in evidence
    assert evidence == (
        "`billing.api-token` is set by the deployment; this module's `prod` configuration sets "
        f"`{REDACTED}`"
    )


_BILLING_ON = (
    "`billing.enabled` is set by the deployment; this module's `prod` configuration sets "
    "`kept-quiet-7`"
)


@pytest.mark.pins("conditions.a-QUOTED-value-is-masked-by-the-modules-own-rules-at-every-exit")
def test_a_quoted_value_is_re_masked_by_its_key_under_the_modules_own_rules():
    """The writer masks with the built-ins only (no module redactor reaches a resolve pass,
    `OI-71`), so every exit re-masks the evidence with the module's own rules through ONE
    function beside the writer: each quoted value by its key (`redact_value`), so a
    `.sextant.yml` key pattern `billing` masks it — `redact_text` alone cannot, never seeing
    the key — and a value pattern anchored on the value alone masks it too. A value quoted
    inside a composed `bean_presence` reason, beside another reason and a competitor list, is
    found where it is."""
    by_key = Redactor.from_rules(RedactionRules(key_patterns=("billing",)))
    by_value = Redactor.from_rules(RedactionRules(value_patterns=("^kept-quiet-7$",)))
    masked = _BILLING_ON.replace("`kept-quiet-7`", f"`{REDACTED}`")

    assert redact_condition_evidence(by_key, _BILLING_ON) == masked
    assert redact_condition_evidence(by_value, _BILLING_ON) == masked
    assert redact_condition_evidence(Redactor.from_rules(), _BILLING_ON) == _BILLING_ON
    composed = (
        "a condition this analysis does not evaluate: {}; "
        + _BILLING_ON
        + '; competitors: [{"bean": "x", "holds": "true"}]'
    )
    assert redact_condition_evidence(by_key, composed) == composed.replace(
        "`kept-quiet-7`", f"`{REDACTED}`"
    )


def test_evidence_quoting_no_configured_value_takes_the_free_text_pass_alone():
    """A profile reason, a placeholder's raw spelling, `compiler`: nothing names a key, so
    `redact_text` is the whole rule — userinfo stripped, the value patterns applied."""
    redactor = Redactor.from_rules(RedactionRules(value_patterns=("apollo_[a-z]+",)))
    reason = (
        "active profiles are set by the deployment; the active profiles here come from "
        "`${apollo_profile}`, which this module does not fill"
    )

    assert redact_condition_evidence(redactor, reason) == reason.replace("apollo_profile", REDACTED)
    assert redact_condition_evidence(redactor, "compiler") == "compiler"
    assert redact_condition_evidence(redactor, "see https://ops:s3cr3t@vault.internal") == (
        "see https://vault.internal"
    )


def test_a_kind_no_deployment_sets_keeps_the_framework_rules_verdict():
    """A model without `set_by` is judged by the framework's rule (`_holds`,
    `_profile_holds`) exactly: the rule reads the bean model, it does not assume Spring."""
    unmarked = ConditionModel(kind=PROPERTY, annotation="com/acme/OnProperty#", members={})
    expression = {"keys": ["billing.enabled"], "having_value": "true", "match_if_missing": False}
    config: dict[str, str | None] = {"billing.enabled": "false"}
    reading = ActiveProfiles(known=frozenset({"h2"}))
    profile = ConditionModel(kind=PROFILE, annotation="com/acme/Profile#", members={})

    unused = "unused without `set_by`"

    assert _judged(unmarked, PROPERTY, expression, "prod", config, reading, "default", unused) == (
        *_holds(PROPERTY, expression, config, "prod"),
        "compiler",
    )
    assert _judged(unmarked, PROPERTY, expression, "prod", config, reading, "default", unused) == (
        FAILS,
        "resolved",
        "compiler",
    )
    assert _judged(
        profile, PROFILE, {"expressions": ["jdbc"]}, "default", {}, reading, "default", unused
    ) == _profile_holds({"expressions": ["jdbc"]}, reading)
