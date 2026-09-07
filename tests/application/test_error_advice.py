"""Tests for the `error_advice` engine (D02 §2's `error_advice` style, 2O
design §4b, Task 8).

Facts are hand-built in the shapes the extractor emits — a class reference
argument is the type's own symbol, an enum reference is
`<Owner>#<CONSTANT>.` (`ClassScanner.enumReference`) — and every identity
string is invented, the `test_injected_client.py` discipline.

The invariant these tests are about: an error handler is a claim about what the
module answers WITH, and the two ways to get it wrong are attaching a handler
to a container the framework never registers, and widening a controller's own
handler into an application-wide one. The near-misses and the `declared_by`
assertions negate exactly those.
"""

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
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {"annotation_args", "typed_signatures"}
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

CONTROLLER_ADVICE = "org/springframework/web/bind/annotation/ControllerAdvice#"
REST_CONTROLLER_ADVICE = "org/springframework/web/bind/annotation/RestControllerAdvice#"
REST_CONTROLLER = "org/springframework/web/bind/annotation/RestController#"
EXCEPTION_HANDLER = "org/springframework/web/bind/annotation/ExceptionHandler#"
RESPONSE_STATUS = "org/springframework/web/bind/annotation/ResponseStatus#"
NOT_FOUND = "org/springframework/http/HttpStatus#NOT_FOUND."

ADVICE = "com/acme/orders/OrdersAdvice#"
HANDLE = "com/acme/orders/OrdersAdvice#handle(sig_1)."
NOT_FOUND_EXCEPTION = "com/acme/orders/OrderNotFound#"
ERROR_BODY = "com/acme/orders/ErrorBody#"
RESPONSE_ENTITY = "org/springframework/http/ResponseEntity#"
RUNTIME_EXCEPTION = "java/lang/RuntimeException#"


def _document(document_id: str = "doc_1") -> Document:
    return Document(
        document_id=document_id,
        relative_path="com/acme/orders/OrdersAdvice.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        scanner_version="9.14",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _type(symbol: str, *, kind: ConstructKind = ConstructKind.CLASS, superclass: str | None = None):
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + symbol,
        construct_kind=kind,
        superclass=None if superclass is None else _MODULE + superclass,
    )


def _returns(symbol: str = ERROR_BODY, *, wrapped: bool = True) -> TypeRef:
    body = TypeRef(symbol=symbol, wire_type="object")
    if not wrapped:
        return body
    return TypeRef(symbol=RESPONSE_ENTITY, arguments=[body], wire_type="object")


def _handler_method(
    symbol: str = HANDLE,
    *,
    owner: str = ADVICE,
    parameters: list[str] = (),
    returns: TypeRef | None = None,
) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + symbol,
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        signature=Signature(
            parameters=[
                Parameter(name=f"p{index}", type=TypeRef(symbol=parameter, wire_type="object"))
                for index, parameter in enumerate(parameters)
            ],
            returns=_returns() if returns is None else returns,
        ),
    )


def _annotated(target: str, annotation: str, args: dict[str, object] | None = None):
    return AnnotationFact(
        document_id="doc_1",
        target=_MODULE + target,
        use=AnnotationUse(annotation=annotation, args=args or {}),
        retention="RUNTIME",
    )


def _advice_module(
    *,
    container: str = CONTROLLER_ADVICE,
    container_args: dict[str, object] | None = None,
    handler_args: dict[str, object] | None = None,
    parameters: list[str] = (),
    returns: TypeRef | None = None,
    status_on_handler: bool = True,
) -> list[object]:
    """The whole shape one handler needs: a container type, a handler method
    on it, the handler annotation, and (optionally) a status."""
    facts: list[object] = [
        _type(ADVICE),
        _handler_method(parameters=parameters, returns=returns),
        _annotated(ADVICE, container, container_args),
        _annotated(
            HANDLE,
            EXCEPTION_HANDLER,
            {"value": NOT_FOUND_EXCEPTION} if handler_args is None else handler_args,
        ),
    ]
    if status_on_handler:
        facts.append(_annotated(HANDLE, RESPONSE_STATUS, {"code": NOT_FOUND}))
    return facts


def _shipped() -> Catalog:
    return next(
        catalog
        for catalog in YamlCatalogSource(catalogs_dir()).load()
        if catalog.id == "spring-advice"
    )


def _invented(matches: dict[str, object] | None = None) -> Catalog:
    shipped = _shipped()
    return Catalog(
        id="test-advice",
        style="error_advice",
        protocol="",
        direction="",
        requires=(),
        matches=matches if matches is not None else dict(shipped.matches),
        source=Path("test-advice.yml"),
        wrappers=list(shipped.wrappers),
    )


def _resolve(
    tmp_path: Path, facts: list[object], catalog: Catalog | None = None
) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "OrdersAdvice.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.derive("error_handlers_reset")
    skipped = derive_endpoints(workspace, [catalog or _shipped()], capabilities=CAPABILITIES)
    assert skipped == []
    return workspace


# --- (a) the happy paths ---------------------------------------------------


def test_an_advice_handler_derives_one_row_carrying_every_column_it_can_read(tmp_path: Path):
    workspace = _resolve(tmp_path, _advice_module())
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows == [
        {
            "handler": _MODULE + HANDLE,
            "advice": ADVICE,
            "declared_by": CONTROLLER_ADVICE,
            "scope": None,
            "exception": NOT_FOUND_EXCEPTION,
            "status": NOT_FOUND,
            "response_shape": ERROR_BODY,
            "resolution": "resolved",
            "evidence": "compiler",
            "catalog_id": "spring-advice",
        }
    ]


def test_the_scope_attributes_are_carried_verbatim(tmp_path: Path):
    """Verbatim because a scope decides WHICH controllers a handler answers
    for. A normalised or reordered package list names a different set."""
    workspace = _resolve(
        tmp_path,
        _advice_module(
            container_args={
                "basePackages": ["com.acme.orders"],
                "assignableTypes": ["com/acme/orders/OrdersController#"],
                # A real attribute of the annotation that is not a scope. It
                # must not reach the column: a bean-ordering hint is not a set
                # of controllers.
                "order": 10,
            }
        ),
    )
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows[0]["scope"] == (
        '{"assignableTypes":["com/acme/orders/OrdersController#"],'
        '"basePackages":["com.acme.orders"]}'
    )


def test_a_controller_local_handler_is_told_apart_from_a_global_advice(tmp_path: Path):
    """The distinction is the reason `declared_by` exists. An advice class
    with no scope attributes applies to EVERY controller; a controller's own
    handler applies to that controller alone. Both carry a NULL `scope`, so a
    reader with only that column would read the second as the first and widen
    one controller's error contract across the application."""
    controller = _resolve(tmp_path, _advice_module(container=REST_CONTROLLER))
    rows = controller.query("error_handlers")
    controller.close()

    assert (rows[0]["declared_by"], rows[0]["scope"]) == (REST_CONTROLLER, None)


def test_a_handler_naming_three_exceptions_derives_three_rows(tmp_path: Path):
    """One row per `(handler, exception)` pair: each is separately
    answerable, and an array in one cell joins against nothing."""
    others = ["com/acme/orders/OrderLocked#", "com/acme/orders/OrderStale#"]
    workspace = _resolve(
        tmp_path,
        _advice_module(handler_args={"value": [NOT_FOUND_EXCEPTION, *others]}),
    )
    rows = workspace.query("error_handlers")
    workspace.close()

    assert [row["exception"] for row in rows] == sorted([NOT_FOUND_EXCEPTION, *others])


def test_the_parameter_type_answers_where_the_annotation_names_none(tmp_path: Path):
    """The framework's own second rule (2O design §4b). Proven rather than
    assumed: the parameter's own scanned superclass chain reaches a root the
    catalog names, so nothing but a throwable can be read as one."""
    facts = [
        *_advice_module(handler_args={}, parameters=[NOT_FOUND_EXCEPTION]),
        _type(NOT_FOUND_EXCEPTION, superclass=RUNTIME_EXCEPTION),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert [row["exception"] for row in rows] == [NOT_FOUND_EXCEPTION]


def test_a_parameter_that_is_not_a_provable_throwable_derives_nothing(tmp_path: Path):
    """A handler takes request-scoped arguments beside its exception. A
    parameter this workspace cannot PROVE is a throwable is not published as
    the handled exception — the under-report COVERAGE names, and the only
    direction that cannot fabricate."""
    facts = [
        *_advice_module(
            handler_args={}, parameters=["org/springframework/web/context/request/WebRequest#"]
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows == []


def test_a_status_on_the_exception_class_answers_where_the_handler_declares_none(
    tmp_path: Path,
):
    """The framework's precedence: a status on the handler answers for that
    handler; one on the exception class is the default for every handler that
    declares none."""
    facts = [
        *_advice_module(status_on_handler=False),
        _type(NOT_FOUND_EXCEPTION, superclass=RUNTIME_EXCEPTION),
        _annotated(NOT_FOUND_EXCEPTION, RESPONSE_STATUS, {"value": NOT_FOUND}),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows[0]["status"] == NOT_FOUND


def test_no_status_anywhere_is_null_rather_than_a_default(tmp_path: Path):
    """A boundary value, and the mechanism-1 rule said about this table: a
    value nothing evidenced is absent, never defaulted. A status computed
    inside a response-entity body is a stated boundary of this phase, and
    inventing 500 here would present that boundary as an observation."""
    workspace = _resolve(tmp_path, _advice_module(status_on_handler=False))
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows[0]["status"] is None


def test_a_handler_returning_nothing_records_no_response_shape(tmp_path: Path):
    workspace = _resolve(tmp_path, _advice_module(returns=TypeRef(symbol="void#", wire_type="")))
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows[0]["response_shape"] is None


def test_an_undeclared_envelope_is_never_unwrapped_past(tmp_path: Path):
    """D02 §2a: an unfamiliar generic could be an envelope, and unwrapping it
    anyway would be a guess presented as fact. The catalog declares one
    envelope; a reactive publisher it does not declare records no shape."""
    mono = TypeRef(
        symbol="reactor/core/publisher/Mono#",
        arguments=[TypeRef(symbol=ERROR_BODY, wire_type="object")],
        wire_type="object",
    )
    workspace = _resolve(tmp_path, _advice_module(returns=mono))
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows[0]["response_shape"] is None


def test_a_module_local_composed_advice_stereotype_is_followed(tmp_path: Path):
    """The framework's container test is meta-annotation aware (§8.1 rule 1,
    `A-C7`). A module's own `@ApiAdvice` composed from the framework's advice
    annotation IS a container, and a check for a literal annotation name
    rejects it — deleting the module's whole error contract."""
    composed = "com/acme/orders/ApiAdvice#"
    facts = [
        *_advice_module(container=composed),
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + composed,
            construct_kind=ConstructKind.INTERFACE,
        ),
        _annotated(composed, REST_CONTROLLER_ADVICE),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert [row["declared_by"] for row in rows] == [REST_CONTROLLER_ADVICE]


# --- (b) the near-misses (§10) ---------------------------------------------


@pytest.mark.declines("spring-advice")
@pytest.mark.pins("error_advice.container-gate")
def test_a_handler_on_a_class_that_is_neither_advice_nor_a_controller_derives_nothing(
    tmp_path: Path,
):
    """Every conjunct but one: the handler annotation is present, on a method,
    naming a real exception — and the declaring class is an ordinary service.
    The framework finds handler methods by first finding the container, so
    this method is ordinary code that happens to be annotated. A row here
    would report an error contract the running system never answers with, and
    would have to invent `declared_by` to do it."""
    facts = [
        _type(ADVICE),
        _handler_method(),
        _annotated(HANDLE, EXCEPTION_HANDLER, {"value": NOT_FOUND_EXCEPTION}),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows == []


@pytest.mark.pins("error_advice.handler-annotation-is-declared")
def test_an_advice_class_whose_only_method_is_not_a_handler_derives_nothing(tmp_path: Path):
    """The other conjunct, negated from the other side: a real advice class,
    a method taking a real exception, and NO handler annotation on it. The
    framework registers nothing — advice is a container, not a claim that
    every method in it answers for an exception."""
    facts = [
        _type(ADVICE),
        _handler_method(parameters=[NOT_FOUND_EXCEPTION]),
        _type(NOT_FOUND_EXCEPTION, superclass=RUNTIME_EXCEPTION),
        _annotated(ADVICE, CONTROLLER_ADVICE),
        # An unrelated annotation on the method, so the input differs from the
        # positive by exactly one thing: WHICH annotation it carries.
        _annotated(HANDLE, "com/acme/orders/Audited#"),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows == []


@pytest.mark.pins("error_advice.exception-is-required")
def test_a_handler_naming_no_readable_exception_derives_nothing(tmp_path: Path):
    """An error handler with no exception is a claim about nothing. The
    weakening this pins is not deleting a check — the row-minting loop simply
    iterates zero times — but publishing the handler at the EMPTY exception,
    which is what "we could not read it" becomes the moment the requirement is
    relaxed: an error contract for an exception nobody named."""
    workspace = _resolve(tmp_path, _advice_module(handler_args={}))
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows == []


def test_an_advice_class_with_no_handler_method_derives_nothing(tmp_path: Path):
    """The third near-miss the plan names. It carries NO `pins` marker on
    purpose: its emptiness has two independent causes — there is no handler
    annotation anywhere AND no method to attach one to — so it pins neither,
    and claiming a guard it does not measure is the failure
    `scripts/guard_check.py` exists to stop (the `spring-actuator` precedent
    in that registry says the same thing about the same shape)."""
    facts = [_type(ADVICE), _annotated(ADVICE, CONTROLLER_ADVICE)]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows == []


def test_a_handler_annotation_on_a_type_derives_nothing(tmp_path: Path):
    """A handler is a method. A type-level use of the annotation names no
    method to run, so publishing it would report a container as though it were
    the handler."""
    facts = [
        _type(ADVICE),
        _annotated(ADVICE, CONTROLLER_ADVICE),
        _annotated(ADVICE, EXCEPTION_HANDLER, {"value": NOT_FOUND_EXCEPTION}),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert rows == []


# --- (c) the table is rebuilt, and stays out of `endpoints` ----------------


def test_the_shipped_catalog_derives_no_endpoint_rows(tmp_path: Path):
    workspace = _resolve(tmp_path, _advice_module())
    endpoints = workspace.query("endpoints")
    handlers = workspace.query("error_handlers")
    workspace.close()

    assert endpoints == []
    assert len(handlers) == 1


def test_a_second_resolve_replaces_the_rows_rather_than_doubling_them(tmp_path: Path):
    write_fact_file(tmp_path / "facts" / "OrdersAdvice.jsonl", _document(), _advice_module())
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    for _ in range(2):
        workspace.derive("error_handlers_reset")
        derive_endpoints(workspace, [_shipped()], capabilities=CAPABILITIES)
    rows = workspace.query("error_handlers")
    workspace.close()

    assert len(rows) == 1


def test_the_shipped_catalog_declares_no_wire_identity():
    catalog = _shipped()
    assert (catalog.protocol, catalog.direction) == ("", "")


# --- (d) a broken catalog is refused, never half-read ----------------------


@pytest.mark.parametrize(
    "dropped",
    [
        "handler_annotation",
        "advice_annotations",
        "controller_annotations",
        "scope_from",
        "status_annotation",
        "status_from",
        "exception_roots",
    ],
)
def test_a_catalog_missing_a_required_match_is_refused(tmp_path: Path, dropped: str):
    matches = {key: value for key, value in _shipped().matches.items() if key != dropped}
    with pytest.raises(CatalogError):
        _resolve(tmp_path, _advice_module(), _invented(matches))


def test_a_catalog_whose_list_match_is_not_a_list_of_strings_is_refused(tmp_path: Path):
    matches = dict(_shipped().matches) | {"exception_roots": "java.lang.Throwable"}
    with pytest.raises(CatalogError):
        _resolve(tmp_path, _advice_module(), _invented(matches))
