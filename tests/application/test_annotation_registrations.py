"""Registrations read from annotations and from implemented interfaces (spec 2026-11-05 §2,
§4 item 5): an `annotation_driven` catalog declaring `dispatch` reads its mapping as
dispatch registrations, keyed by the class the annotation names (`path_from`) or by the
payload parameter's type (`path_fallback: payload_type`, the parameter `request_body`
picks), and a `dispatch_implementations` entry reads each module class implementing the
declared interface as a registration of its own method, keyed by that method's parameter.

Hand-built facts in the shape javac writes (CP-59), read through the shipped
`spring-events` catalog, so each test is one shape. The whole pipeline over real bytecode is
`tests/e2e/test_spring_events_delivered.py`.
"""

from pathlib import Path

import pytest

from flow_facts import straight_line
from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.dispatch_registrations import record_dispatch_registrations
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/shop 1.0.0 "
_LISTENER = "com/acme/shop/Listener#"
_PLACED = "com/acme/shop/OrderPlaced#"
_SHIPPED = "com/acme/shop/OrderShipped#"
_EVENT_LISTENER = "org/springframework/context/event/EventListener#"
_APPLICATION_LISTENER = "org/springframework/context/ApplicationListener#"
_APPLICATION_EVENT = "org/springframework/context/ApplicationEvent#"
_OBSERVES = "jakarta/enterprise/event/Observes#"
_OBSERVES_ASYNC = "jakarta/enterprise/event/ObservesAsync#"
_QUALIFIER = "jakarta/inject/Qualifier#"
_EXPRESS = "com/acme/shop/Express#"
_PRIORITY = "jakarta/annotation/Priority#"


def _catalog(catalog_id: str = "spring-events") -> Catalog:
    return next(
        catalog for catalog in YamlCatalogSource(catalogs_dir()).load() if catalog.id == catalog_id
    )


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/shop/Listener.java",
        module_id="com.acme:shop",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _method(
    owner: str,
    name: str,
    parameters: tuple[str, ...],
    *,
    synthetic: bool = False,
    annotated: dict[int, str] | None = None,
    typed: dict[int, TypeRef] | None = None,
) -> SymbolFact:
    """A `void` method of `owner` taking `parameters` (type symbols, the erasures), as javac
    declares it; `annotated` maps a parameter's index to the annotation it carries, `typed` to
    the signature's type where it is not the erasure (a type variable, type arguments)."""
    descriptor = "(" + "".join(f"L{p.removesuffix('#')};" for p in parameters) + ")V"
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + method_descriptor(owner, name, descriptor),
        construct_kind="method",
        enclosing=_MODULE + owner,
        signature=Signature(
            parameters=[
                Parameter(
                    name=f"p{i}",
                    type=(typed or {}).get(i, TypeRef(symbol=p)),
                    erased_symbol=p,
                    annotations=[AnnotationUse(annotation=(annotated or {})[i], args={})]
                    if i in (annotated or {})
                    else [],
                )
                for i, p in enumerate(parameters)
            ],
            returns=TypeRef(symbol="void"),
        ),
        modifiers={"static": False, "synthetic": synthetic},
    )


def _annotated(method: SymbolFact, annotation: str, args: dict | None = None) -> AnnotationFact:
    return AnnotationFact(
        document_id="doc_1",
        target=method.symbol,
        use=AnnotationUse(annotation=annotation, args=args or {}),
        retention="RUNTIME",
    )


def _class(symbol: str, interfaces: tuple[str, ...] = ()) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + symbol,
        construct_kind="class",
        superclass="java/lang/Object#",
        interfaces=list(interfaces),
    )


def _rows(tmp_path: Path, facts: list, catalog_id: str = "spring-events") -> list[tuple]:
    """`(handler's method name and parameter count, position, key_type, match)` per row."""
    write_fact_file(tmp_path / "facts" / "Listener.jsonl", _document(), straight_line(facts))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace.load_facts(tmp_path / "facts")
        record_dispatch_registrations(workspace, [_catalog(catalog_id)])
        rows = workspace.query("dispatch_registrations")
    finally:
        workspace.close()
    return sorted(
        (
            str(row["handler"]).split("#", 1)[1].split("(")[0],
            row["position"],
            row["key_type"],
            row["match"],
            row["group"] == row["handler"],
        )
        for row in rows
    )


@pytest.mark.pins("annotation-registrations.the-PAYLOAD-parameter-keys-the-listener")
def test_a_listener_is_keyed_by_its_payload_parameter(tmp_path: Path):
    """`@EventListener void on(OrderPlaced e)`: one registration, keyed by the parameter's
    type, its group the listener method itself."""
    on = _method(_LISTENER, "on", (_PLACED,))
    assert _rows(tmp_path, [_class(_LISTENER), on, _annotated(on, _EVENT_LISTENER)]) == [
        ("on", 0, _PLACED, "all", True)
    ]


@pytest.mark.pins("annotation-registrations.the-CLASSES-attribute-wins")
def test_the_classes_named_on_the_annotation_key_the_listener(tmp_path: Path):
    """`@EventListener(classes = {OrderPlaced.class, OrderShipped.class}) void on()`: one
    registration per class named, in the order written; the annotation's classes win over a
    parameter where both are present."""
    bare = _method(_LISTENER, "on", ())
    typed = _method(_LISTENER, "onTyped", (_APPLICATION_EVENT,))
    facts = [
        _class(_LISTENER),
        bare,
        _annotated(bare, _EVENT_LISTENER, {"classes": [_PLACED, _SHIPPED]}),
        typed,
        _annotated(typed, _EVENT_LISTENER, {"value": _SHIPPED}),
    ]
    assert _rows(tmp_path, facts) == [
        ("on", 0, _PLACED, "all", True),
        ("on", 1, _SHIPPED, "all", True),
        ("onTyped", 0, _SHIPPED, "all", True),
    ]


def test_a_listener_with_no_readable_type_is_an_unread_registration(tmp_path: Path):
    """`@EventListener void on(A a, B b)` names no class and has no one payload parameter
    (Spring refuses it at start-up): its registration is kept with no key, so it matches
    nothing and is never a listener of every event."""
    two = _method(_LISTENER, "on", (_PLACED, _SHIPPED))
    assert _rows(tmp_path, [_class(_LISTENER), two, _annotated(two, _EVENT_LISTENER)]) == [
        ("on", 0, None, "all", True)
    ]


@pytest.mark.declines("spring-events")
@pytest.mark.pins("annotation-registrations.ONLY-a-named-annotation-registers")
def test_a_method_the_catalog_names_no_annotation_for_registers_nothing(tmp_path: Path):
    """A method taking an event but carrying no listener annotation, or another annotation,
    is no listener."""
    plain = _method(_LISTENER, "on", (_PLACED,))
    other = _method(_LISTENER, "onOther", (_PLACED,))
    facts = [
        _class(_LISTENER),
        plain,
        other,
        _annotated(other, "org/springframework/context/annotation/Bean#"),
    ]
    assert _rows(tmp_path, facts) == []


@pytest.mark.pins("annotation-registrations.a-PARAMETER-annotation-selects-the-observer")
@pytest.mark.pins("annotation-registrations.the-ANNOTATED-parameter-keys-the-observer")
def test_an_observer_is_keyed_by_its_annotated_parameter(tmp_path: Path):
    """`void record(Ledger ledger, @Observes OrderPlaced e)`: the method carries no annotation
    of its own; the parameter annotation selects it (`mapping.selected_by_parameter`), and the
    key is THAT parameter's type, wherever it sits among the injected ones (CP-59 finding 9:
    javac writes the annotation on the one parameter carrying it)."""
    observer = _method(_LISTENER, "record", (_SHIPPED, _PLACED), annotated={1: _OBSERVES})
    assert _rows(tmp_path, [_class(_LISTENER), observer], "cdi-events") == [
        ("record", 0, _PLACED, "all", True)
    ]


def _observer(
    name: str, annotations: tuple[str, ...], arguments: tuple[str, ...] = ()
) -> SymbolFact:
    """`void <name>(@Observes <annotations> OrderPlaced<arguments> e)` on the listener class."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + method_descriptor(_LISTENER, name, f"(L{_PLACED[:-1]};)V"),
        construct_kind="method",
        enclosing=_MODULE + _LISTENER,
        signature=Signature(
            parameters=[
                Parameter(
                    name="e",
                    type=TypeRef(symbol=_PLACED, arguments=[TypeRef(symbol=a) for a in arguments]),
                    erased_symbol=_PLACED,
                    annotations=[
                        AnnotationUse(annotation=a, args={}) for a in (_OBSERVES, *annotations)
                    ],
                )
            ],
            returns=TypeRef(symbol="void"),
        ),
        modifiers={"static": False, "synthetic": False},
    )


def _qualifier_type() -> list:
    """`@Qualifier @interface Express`, a module annotation type."""
    express = _class(_EXPRESS)
    return [
        express,
        AnnotationFact(
            document_id="doc_1",
            target=express.symbol,
            use=AnnotationUse(annotation=_QUALIFIER, args={}),
            retention="RUNTIME",
        ),
    ]


@pytest.mark.pins("annotation-registrations.a-QUALIFIED-observer-is-KEYLESS")
def test_a_qualified_observer_is_kept_keyless(tmp_path: Path):
    """`on(@Observes @Express OrderPlaced e)`, `Express` meta-annotated `@Qualifier`: the
    observer is notified only of events fired with that qualifier, which the fire sites are not
    read for, so its registration is kept with no key (matches nothing: missing, never false)."""
    facts = [_class(_LISTENER), *_qualifier_type(), _observer("on", (_EXPRESS,))]
    assert _rows(tmp_path, facts, "cdi-events") == [("on", 0, None, "all", True)]


@pytest.mark.pins("annotation-registrations.ONLY-a-QUALIFIER-makes-an-observer-KEYLESS")
def test_an_observer_with_an_annotation_that_qualifies_nothing_keeps_its_key(tmp_path: Path):
    """`on(@Observes @Priority(10) OrderPlaced e)`: `@Priority` orders observers and is no
    qualifier, and an annotation type meta-annotated only by something else (`@Documented`) is
    none either. Both keep their key."""
    express = _class(_EXPRESS)
    facts = [
        _class(_LISTENER),
        express,
        AnnotationFact(
            document_id="doc_1",
            target=express.symbol,
            use=AnnotationUse(annotation="java/lang/annotation/Documented#", args={}),
            retention="RUNTIME",
        ),
        _observer("onPriority", (_PRIORITY,)),
        _observer("onExpress", (_EXPRESS,)),
    ]
    assert _rows(tmp_path, facts, "cdi-events") == [
        ("onExpress", 0, _PLACED, "all", True),
        ("onPriority", 0, _PLACED, "all", True),
    ]


@pytest.mark.pins("annotation-registrations.a-PARAMETERIZED-observed-type-is-KEYLESS")
def test_a_parameterized_observed_type_is_kept_keyless(tmp_path: Path):
    """`on(@Observes OrderPlaced<String> e)`: the framework matches the parameterized type, so
    the erasure would reach every `OrderPlaced` whatever its arguments. Kept with no key."""
    facts = [_class(_LISTENER), _observer("on", (), ("java/lang/String#",))]
    assert _rows(tmp_path, facts, "cdi-events") == [("on", 0, None, "all", True)]


@pytest.mark.declines("cdi-events")
@pytest.mark.pins("annotation-registrations.ONLY-a-named-PARAMETER-annotation-registers")
def test_a_method_no_named_parameter_annotation_marks_registers_nothing(tmp_path: Path):
    """A method taking an event with no annotated parameter, or a parameter carrying another
    annotation (`@ObservesAsync` belongs to the other mechanism's catalog), is no observer of
    this catalog."""
    plain = _method(_LISTENER, "on", (_PLACED,))
    other = _method(_LISTENER, "onAsync", (_PLACED,), annotated={0: _OBSERVES_ASYNC})
    assert _rows(tmp_path, [_class(_LISTENER), plain, other], "cdi-events") == []


def test_an_observes_async_parameter_is_an_async_observer(tmp_path: Path):
    """`on(@ObservesAsync OrderPlaced e)` is the asynchronous catalog's registration, keyed by
    the annotated parameter's type."""
    asynchronous = _method(_LISTENER, "onAsync", (_PLACED,), annotated={0: _OBSERVES_ASYNC})
    assert _rows(tmp_path, [_class(_LISTENER), asynchronous], "cdi-async-events") == [
        ("onAsync", 0, _PLACED, "all", True)
    ]


@pytest.mark.declines("cdi-async-events")
@pytest.mark.pins("annotation-registrations.ONLY-a-named-PARAMETER-annotation-registers")
def test_an_observes_parameter_is_no_async_observer(tmp_path: Path):
    """`on(@Observes OrderPlaced e)` is a synchronous observer, which no `fireAsync` notifies
    (CP-59 finding 10): nothing in the asynchronous catalog."""
    synchronous = _method(_LISTENER, "on", (_PLACED,), annotated={0: _OBSERVES})
    assert _rows(tmp_path, [_class(_LISTENER), synchronous], "cdi-async-events") == []


@pytest.mark.pins("dispatch-implementations.the-BRIDGE-is-carried-to-the-method-it-forwards-to")
def test_an_implementation_is_keyed_by_the_method_its_bridge_forwards_to(tmp_path: Path):
    """`implements ApplicationListener<OrderPlaced>`: the class's `onApplicationEvent(
    ApplicationEvent)` is javac's synthetic bridge, the method matching the interface's
    descriptor, and it forwards to `onApplicationEvent(OrderPlaced)`. One registration, the
    method the class wrote, keyed `OrderPlaced`, never `ApplicationEvent`."""
    facts = [
        _class(_LISTENER, (_APPLICATION_LISTENER,)),
        _method(_LISTENER, "onApplicationEvent", (_PLACED,)),
        _method(_LISTENER, "onApplicationEvent", (_APPLICATION_EVENT,), synthetic=True),
    ]
    assert _rows(tmp_path, facts) == [("onApplicationEvent", 0, _PLACED, "all", True)]


_BASE = "com/acme/shop/Base#"
_GENERIC = "com/acme/shop/Envelope#"
_OBJECT = "java/lang/Object#"


@pytest.mark.pins("dispatch-registrations.a-GENERIC-parameter-is-KEYLESS")
def test_a_generic_base_implementation_is_kept_keyless(tmp_path: Path):
    """`abstract class Base<E extends ApplicationEvent> implements ApplicationListener<E>` with
    `onApplicationEvent(E)`: javac writes the bound, `ApplicationEvent`, and no bridge, but the
    framework dispatches by the type each subclass binds `E` to. Keyed by the erasure it would
    receive every event, false hops; kept with no key (missing, never false)."""
    facts = [
        _class(_BASE, (_APPLICATION_LISTENER,)),
        _method(_BASE, "onApplicationEvent", (_APPLICATION_EVENT,), typed={0: TypeRef(symbol="E")}),
    ]
    assert _rows(tmp_path, facts) == [("onApplicationEvent", 0, None, "all", True)]


@pytest.mark.pins("dispatch-registrations.a-GENERIC-parameter-is-KEYLESS")
def test_a_type_variable_or_parameterized_listener_is_kept_keyless(tmp_path: Path):
    """`@EventListener on(T e)` erases to `Object` and `@EventListener on(Envelope<OrderPlaced>
    e)` to `Envelope`; the framework matches the resolved or parameterized type, so either
    erasure would reach events it never delivers. Both kept with no key, as CDI's are; a plain
    `on(OrderPlaced e)` beside them keeps its key."""
    variable = _method(_LISTENER, "onVariable", (_OBJECT,), typed={0: TypeRef(symbol="T")})
    parameterized = _method(
        _LISTENER,
        "onEnvelope",
        (_GENERIC,),
        typed={0: TypeRef(symbol=_GENERIC, arguments=[TypeRef(symbol=_PLACED)])},
    )
    plain = _method(_LISTENER, "onPlaced", (_PLACED,))
    facts = [_class(_LISTENER)]
    for method in (variable, parameterized, plain):
        facts += [method, _annotated(method, _EVENT_LISTENER)]
    assert _rows(tmp_path, facts) == [
        ("onEnvelope", 0, None, "all", True),
        ("onPlaced", 0, _PLACED, "all", True),
        ("onVariable", 0, None, "all", True),
    ]


@pytest.mark.pins("dispatch-registrations.a-GENERIC-parameter-is-KEYLESS")
def test_a_type_variable_observed_type_is_kept_keyless(tmp_path: Path):
    """`on(@Observes T e)` in a generic class: CDI resolves the observed type per bean, so its
    erasure, `Object`, would reach every event. Kept with no key."""
    on = _method(
        _LISTENER, "on", (_OBJECT,), annotated={0: _OBSERVES}, typed={0: TypeRef(symbol="T")}
    )
    assert _rows(tmp_path, [_class(_LISTENER), on], "cdi-events") == [("on", 0, None, "all", True)]


@pytest.mark.pins("dispatch-implementations.an-UNREAD-implementation-is-KEPT")
def test_an_implementation_whose_bridge_has_no_one_target_is_kept_unkeyed(tmp_path: Path):
    """A bridge beside two same-arity overloads names no ONE method it forwards to: the
    registration is kept with no key (it matches nothing, never every event), its handler
    the bridge the framework calls, as an annotated method with no readable type is kept."""
    facts = [
        _class(_LISTENER, (_APPLICATION_LISTENER,)),
        _method(_LISTENER, "onApplicationEvent", (_PLACED,)),
        _method(_LISTENER, "onApplicationEvent", (_SHIPPED,)),
        _method(_LISTENER, "onApplicationEvent", (_APPLICATION_EVENT,), synthetic=True),
    ]
    assert _rows(tmp_path, facts) == [("onApplicationEvent", 0, None, "all", True)]


def test_an_implementation_of_the_erased_type_needs_no_bridge(tmp_path: Path):
    """`implements ApplicationListener<ApplicationEvent>`: the method the class wrote has the
    interface's own descriptor, so it is the registration, keyed `ApplicationEvent`."""
    facts = [
        _class(_LISTENER, (_APPLICATION_LISTENER,)),
        _method(_LISTENER, "onApplicationEvent", (_APPLICATION_EVENT,)),
    ]
    assert _rows(tmp_path, facts) == [("onApplicationEvent", 0, _APPLICATION_EVENT, "all", True)]


@pytest.mark.pins("dispatch-implementations.ONLY-an-implementing-class-registers")
def test_a_class_not_implementing_the_interface_registers_nothing(tmp_path: Path):
    """The interface's own method, with its exact descriptor, on a class that does not
    implement the interface is called by nobody the catalog knows of."""
    facts = [_class(_LISTENER), _method(_LISTENER, "onApplicationEvent", (_APPLICATION_EVENT,))]
    assert _rows(tmp_path, facts) == []


@pytest.mark.pins("endpoints.a-REGISTRATION-catalog-runs-no-engine")
def test_an_annotation_catalog_declaring_dispatch_mints_no_endpoint_row(tmp_path: Path):
    """An `annotation_driven` catalog declaring `dispatch` describes registrations: the
    endpoint loop leaves it out whole, neither run nor reported skipped."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        skipped = derive_endpoints(workspace, [_catalog()], set())
        rows = workspace.query("endpoints")
    finally:
        workspace.close()
    assert _catalog().style == "annotation_driven"
    assert skipped == []
    assert rows == []


def _catalog_file(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "catalogs"
    directory.mkdir()
    (directory / "events.yml").write_text(
        "id: events\nstyle: annotation_driven\nprotocol: in_process\ndirection: inbound\n"
        "dispatch: { key: type, match: all, mechanism: events }\n" + body,
        encoding="utf-8",
    )
    return directory


@pytest.mark.parametrize(
    ("entry", "refused"),
    [
        ("{ owner: a.L, method: handle, descriptor: '(La/E;)V', value_arg: 1 }", "value_arg"),
        ("{ owner: a.L, method: handle, descriptor: '(La/E;)V' }", "value_arg"),
        ("{ owner: a.L, method: handle, descriptor: '(La/E;)V', value_arg: 0, x: 1 }", "unknown"),
    ],
)
def test_a_malformed_implementation_is_refused_at_load(tmp_path: Path, entry: str, refused: str):
    directory = _catalog_file(
        tmp_path,
        "matches:\n  mapping: { path_from: [], prefix_from: [], all_methods: [],\n"
        "             prefix_annotation: null, annotations: [] }\n"
        f"  dispatch_implementations:\n    - {entry}\n",
    )
    with pytest.raises(CatalogError, match=refused):
        YamlCatalogSource(directory).load()


def test_an_implementation_is_loaded_with_its_position(tmp_path: Path):
    directory = _catalog_file(
        tmp_path,
        "matches:\n  dispatch_implementations:\n"
        "    - { owner: a.L, method: handle, descriptor: '(La/E;)V', value_arg: 0 }\n",
    )
    [catalog] = YamlCatalogSource(directory).load()
    assert catalog.dispatch_implementations == (
        {"owner": "a/L#", "method": "handle", "descriptor": "(La/E;)V", "value_arg": 0},
    )


@pytest.mark.pins("annotation-registrations.only-PAYLOAD_TYPE-names-a-registration")
def test_a_registration_fallback_other_than_payload_type_is_refused(tmp_path: Path):
    """A name fallback composes an ADDRESS (`construct_name`, the method's own name); a
    registration has a key, which only the payload's type can stand in for. Read as a
    registration, `construct_name` would key a listener by a method name no class carries."""
    directory = _catalog_file(
        tmp_path,
        "matches:\n  mapping: { path_from: [classes], path_fallback: construct_name,\n"
        "             prefix_from: [], all_methods: [], prefix_annotation: null,\n"
        "             annotations: [{ fqn: a.Listen }] }\n",
    )
    [catalog] = YamlCatalogSource(directory).load()
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        with pytest.raises(CatalogError, match="payload_type"):
            record_dispatch_registrations(workspace, [catalog])
    finally:
        workspace.close()


@pytest.mark.pins("annotation-registrations.a-NON-LIST-annotation-word-is-refused")
def test_a_parameter_selector_that_is_not_a_list_of_names_is_refused(tmp_path: Path):
    """`selected_by_parameter` is a list of annotation names. A bare string read as a list is
    a list of its characters, which select nothing: the catalog's observers would be silently
    absent."""
    directory = _catalog_file(
        tmp_path,
        "bean_model: di\n"
        "matches:\n  mapping: { selected_by_parameter: a.Observes,\n"
        "             prefix_from: [], all_methods: [], prefix_annotation: null,\n"
        "             annotations: [] }\n",
    )
    (directory / "bean-models").mkdir()
    (directory / "bean-models" / "di.yml").write_text(
        "id: di\nqualifier_meta_annotations: [a.Qualifier]\n", encoding="utf-8"
    )
    [catalog] = YamlCatalogSource(directory).load()
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        with pytest.raises(CatalogError, match="selected_by_parameter"):
            record_dispatch_registrations(workspace, [catalog])
    finally:
        workspace.close()


@pytest.mark.pins("bean-models.a-MALFORMED-qualifier-marker-is-refused-at-LOAD")
def test_a_qualifier_marker_that_is_not_a_list_of_names_is_refused(tmp_path: Path):
    """The DI bean model's `qualifier_meta_annotations` is a list of annotation names, refused
    at load otherwise, naming the model's file: a bare string would mark nothing, and every
    qualified observer would keep a false key."""
    directory = _catalog_file(
        tmp_path,
        "bean_model: di\n"
        "matches:\n  mapping: { selected_by_parameter: [a.Observes],\n"
        "             prefix_from: [], all_methods: [], prefix_annotation: null,\n"
        "             annotations: [] }\n",
    )
    (directory / "bean-models").mkdir()
    (directory / "bean-models" / "di.yml").write_text(
        "id: di\nqualifier_meta_annotations: a.Qualifier\n", encoding="utf-8"
    )
    with pytest.raises(CatalogError, match="di.yml.*qualifier_meta_annotations"):
        YamlCatalogSource(directory).load()


@pytest.mark.pins(
    "annotation-registrations.a-PARAMETER-selector-NAMES-a-bean-model-with-QUALIFIERS"
)
def test_a_parameter_selector_naming_no_qualifiers_is_refused_at_load(tmp_path: Path):
    """Which annotations qualify an observed parameter is the container's knowledge (D02 §1c),
    so a catalog selecting observers by a parameter annotation names a bean model declaring its
    qualifiers. One naming none is refused at load: without them every qualified observer
    would be keyed, a false hop for each unqualified send of its class."""
    directory = _catalog_file(
        tmp_path,
        "matches:\n  mapping: { selected_by_parameter: [a.Observes],\n"
        "             prefix_from: [], all_methods: [], prefix_annotation: null,\n"
        "             annotations: [] }\n",
    )
    with pytest.raises(CatalogError, match="events.yml.*bean_model"):
        YamlCatalogSource(directory).load()


def test_the_cdi_catalogs_read_their_qualifiers_from_the_cdi_bean_model():
    """The qualifier marker is declared once, in the DI bean model the CDI catalogs name, and
    no catalog spells it."""
    catalogs = {catalog.id: catalog for catalog in YamlCatalogSource(catalogs_dir()).load()}
    for catalog_id in ("cdi-events", "cdi-async-events"):
        catalog = catalogs[catalog_id]
        assert catalog.bean_model["qualifier_meta_annotations"] == [
            "jakarta.inject.Qualifier",
            "javax.inject.Qualifier",
        ]
        assert "keyless_when_meta_annotated" not in catalog.matches["mapping"]
