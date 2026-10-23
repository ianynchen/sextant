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

from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.bean_conditions import record_bean_conditions
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
) -> DuckDbWorkspace:
    """The facts through the passes the conditions pass reads after: configuration (the
    environments), the call graph and the hierarchy (what a factory constructs, and what it
    is assignable to), and the rows themselves."""
    root = tmp_path / "facts"
    write_fact_file(
        root / "doc.jsonl", _document("doc", "com/acme/orders/All.java", "java", "asm"), facts
    )
    _config(root, "application.yml", {"orders.legacy": default_legacy})
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
    through its handler's owner class, which is the one join every row kind shares."""
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
        "default": ("class", None, "profile", "false", "resolved"),
        "prod": ("class", None, "profile", "true", "resolved"),
    }
    assert {(r["direction"], r["caller"], r["environment"], r["holds"]) for r in viewed} == {
        ("outbound", _MODULE + run, "default", "false"),
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
    consulted on this route (CP-44 row 4), the factory's are."""
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
        "default": ("factory", via, "profile", "false", "resolved"),
        "prod": ("factory", via, "profile", "true", "resolved"),
    }
    # The configuration class itself carries no condition, so it is no conditional bean.
    assert {r["bean"] for r in beans} == {_MODULE + KAFKA}


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

    assert {r["bean"] for r in beans} == {_MODULE + KAFKA}
    assert _verdicts(beans, FORMATTER) == {}


def test_a_factory_in_a_conditional_configuration_inherits_the_class_condition(tmp_path: Path):
    """`@Configuration @ConditionalOnProperty(name = "orders.legacy", havingValue = "true")`
    with an unconditional `@Bean`: Spring skips every `@Bean` of a configuration class whose
    own condition fails (CP-44 row 4), so the constructed class carries the class's
    condition, as `configuration`."""
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
        "default": ("configuration", via, "property", "false", "resolved"),
        "prod": ("configuration", via, "property", "true", "resolved"),
    }
    # The configuration class is itself a conditional scanned bean.
    assert _verdicts(beans, legacy_config) == {
        "default": ("class", None, "property", "false", "resolved"),
        "prod": ("class", None, "property", "true", "resolved"),
    }


# --- a class registered more than one way: it exists wherever ANY route registers it -----


def _presence(workspace: DuckDbWorkspace, bean: str) -> dict[str, tuple[object, ...]]:
    return {
        str(r["environment"]): (r["holds"], r["resolution"])
        for r in workspace.query("bean_presence")
        if r["bean"] == _MODULE + bean
    }


def test_two_exclusive_profile_factories_make_the_class_exist_in_each_profile(tmp_path: Path):
    """Ruled 2026-10-22: OR across routes. `@Bean @Profile("prod")` and `@Bean
    @Profile("staging")` each register their own definition of `KafkaOrderPublisher`, so it
    exists in `prod` and in `staging` and nowhere else — decided, not `unresolved`. Each
    factory's own condition rows stay, evaluated, under its own `via`."""
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
        "default": ("false", "resolved"),
        "prod": ("true", "resolved"),
        "staging": ("true", "resolved"),
    }
    assert {(r["via"], r["environment"], r["holds"]) for r in rows} == {
        (_factory_symbol(MESSAGING, "publisher", PUBLISHER), "default", "false"),
        (_factory_symbol(MESSAGING, "publisher", PUBLISHER), "prod", "true"),
        (_factory_symbol(MESSAGING, "publisher", PUBLISHER), "staging", "false"),
        (_factory_symbol(staging, "publisher", PUBLISHER), "default", "false"),
        (_factory_symbol(staging, "publisher", PUBLISHER), "prod", "false"),
        (_factory_symbol(staging, "publisher", PUBLISHER), "staging", "true"),
    }


@pytest.mark.parametrize("unconditional", ["factory", "scanned"])
def test_an_unconditional_route_beside_a_conditional_factory_makes_the_class_exist_everywhere(
    tmp_path: Path, unconditional: str
):
    """Review focus 2, as ruled: a conditional factory of `KafkaOrderPublisher` beside an
    unconditional `@Bean` of it — or beside its own unconditional `@Component` — means the
    class exists in every environment, resolved. The conditional route's rows are still
    written and still evaluated; the bean's presence is what changes."""
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
        ("default", "false", "resolved"),
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
    would turn every conditional base class with a subclass `unresolved`."""
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
        "default": ("class", None, "profile", "false", "resolved"),
        "prod": ("class", None, "profile", "true", "resolved"),
    }


# --- a stereotype or a condition through a COMPOSED annotation (CP-44 row 5) --------------


def test_a_module_local_composed_stereotype_makes_a_conditional_class_a_bean(tmp_path: Path):
    """`@MyService` is the module's own annotation, meta-annotated `@Service`. The scanner
    matches meta-annotations, so `@MyService @Profile("prod") Orders` is a scanned bean — and
    the annotation type itself, which carries `@Service`, is no bean."""
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
        "default": ("class", None, "profile", "false", "resolved"),
        "prod": ("class", None, "profile", "true", "resolved"),
    }
    assert {r["bean"] for r in beans} == {_MODULE + orders}


def test_a_stereotype_through_a_dependency_annotations_recorded_header_makes_a_bean(
    tmp_path: Path,
):
    """Review finding 1's real input, reduced: an auto-configuration annotation from a jar,
    whose header the classpath read recorded as meta-annotated `@Configuration`. Nothing
    names that annotation in code; its header makes the class a configuration bean, and the
    class's own `@ConditionalOnProperty` conditions it."""
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
        "default": ("class", None, "property", "false", "resolved"),
        "prod": ("class", None, "property", "true", "resolved"),
    }


def test_a_condition_carried_on_a_composed_annotation_conditions_its_users(tmp_path: Path):
    """`@LegacyOnly` is the module's own annotation carrying `@ConditionalOnProperty(name =
    "orders.legacy", havingValue = "true")`; a `@Service @LegacyOnly` class carries that
    condition, its arguments folded from the composition."""
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
        "default": ("class", None, "property", "false", "resolved"),
        "prod": ("class", None, "property", "true", "resolved"),
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


def test_a_lambda_a_conditional_factory_creates_carries_the_factorys_condition(
    tmp_path: Path,
):
    """Review finding 2. `@Bean @Profile("prod") Runnable sync() { return () ->
    rest.getForObject(…); }` in an unconditional configuration class: the lambda body is
    the factory's code, read off the `dynamic` call edge from `sync` to it (never off its
    name). Its outbound row carries the factory's condition, `via` the factory — not the
    configuration class's (none)."""
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
        "default": ("factory", _MODULE + factory, "profile", "false", "resolved"),
        "prod": ("factory", _MODULE + factory, "profile", "true", "resolved"),
    }
    assert {(r["caller"], r["via"], r["environment"], r["holds"]) for r in viewed} == {
        (_MODULE + body, _MODULE + factory, "default", "false"),
        (_MODULE + body, _MODULE + factory, "prod", "true"),
    }


# --- the view tells two routes of one bean apart -----------------------------------------


def test_two_exclusive_factories_rows_on_one_endpoint_carry_distinct_via(tmp_path: Path):
    """Review finding 3. `KafkaOrderPublisher#send` makes an outbound call and the class is
    registered by a `prod` factory and a `staging` one. Read as "every row must hold", the
    row would exist nowhere; `via` tells the two routes apart, and `bean_presence` — not the
    rows — says where the row exists."""
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
    } == {("default", "false"), ("prod", "false"), ("staging", "true")}
    assert presence == {
        "default": ("false", "resolved"),
        "prod": ("true", "resolved"),
        "staging": ("true", "resolved"),
    }


def test_a_bean_left_open_by_an_unfilled_placeholder_says_the_value_is_unknown(
    tmp_path: Path,
):
    """Minor: `orders.legacy: ${ORDERS_LEGACY}` with nothing filling it. Where the bean's only
    route is open for that reason, `bean_presence` says the configured value is unknown — not
    that the condition is one this analysis does not evaluate."""
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
    assert "value is unknown" in str(rows["default"]["evidence"])
    assert "does not evaluate" not in str(rows["default"]["evidence"])
    assert (rows["prod"]["holds"], rows["prod"]["evidence"]) == ("true", "compiler")


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
