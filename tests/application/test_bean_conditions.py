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


def _resolved(tmp_path: Path, facts: list[object], *ids: str) -> DuckDbWorkspace:
    """The facts through the passes the conditions pass reads after: configuration (the
    environments), the call graph and the hierarchy (what a factory constructs, and what it
    is assignable to), and the rows themselves."""
    root = tmp_path / "facts"
    write_fact_file(
        root / "doc.jsonl", _document("doc", "com/acme/orders/All.java", "java", "asm"), facts
    )
    _config(root, "application.yml", {"orders.legacy": "false"})
    _config(root, "application-prod.yml", {"orders.legacy": "true"})
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


# --- a class registered more than one way ------------------------------------------------


def test_a_class_registered_two_ways_is_unresolved(tmp_path: Path):
    """Review focus 2. `KafkaOrderPublisher` is ALSO a `@Component` — scanned, unconditional —
    while a `@Profile("prod")` factory constructs it. Whether a `prod`-less environment runs
    its code depends on which registration the container keeps, which this analysis does not
    decide: `unresolved`, the reason naming both routes — never conditional, never not."""
    facts = [
        *_type(PUBLISHER, kind=ConstructKind.INTERFACE),
        *_type(KAFKA, [_marker(COMPONENT)], interfaces=(PUBLISHER,)),
        *_type(MESSAGING, [_marker(CONFIGURATION)]),
        *_method(MESSAGING, "publisher", PUBLISHER, [_marker(BEAN), _profile("prod")], [KAFKA]),
    ]
    workspace = _resolved(tmp_path, facts)
    beans = workspace.query("bean_conditions")
    workspace.close()

    rows = [r for r in beans if r["bean"] == _MODULE + KAFKA]
    assert {(r["environment"], r["holds"], r["resolution"]) for r in rows} == {
        ("default", "unresolved", "unresolved"),
        ("prod", "unresolved", "unresolved"),
    }
    [evidence] = {str(r["evidence"]) for r in rows}
    assert "scanned" in evidence
    assert _factory_symbol(MESSAGING, "publisher", PUBLISHER) in evidence


def test_a_class_also_constructed_outside_any_factory_is_unresolved(tmp_path: Path):
    """The other half of the same rule: a plain `new KafkaOrderPublisher()` in an ordinary
    method runs that class's code whether or not the conditional factory's bean exists."""
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
    beans = workspace.query("bean_conditions")
    workspace.close()

    rows = [r for r in beans if r["bean"] == _MODULE + KAFKA]
    assert {(r["holds"], r["resolution"]) for r in rows} == {("unresolved", "unresolved")}
    assert all(_factory_symbol(plain, "make", PUBLISHER) in str(r["evidence"]) for r in rows)


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
