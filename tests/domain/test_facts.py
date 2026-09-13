import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import read_fact_file, write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    ConfigEntryFact,
    ConstantFact,
    Document,
    Fact,
    FieldWriteFact,
    MethodReturnFact,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)

DOCUMENT = Document(
    document_id="doc_1",
    relative_path="src/main/java/com/acme/OrderController.java",
    module_id="com.acme:orders",
    language="java",
    sextant_version="0.1.0",
    fact_schema_version=2,
    scanner_id="asm",
    content_hash="sha256:abc",
    origin_entry="target/classes",
    origin_tier=OriginTier.MODULE_OUTPUT,
    redaction_set_hash="sha256:def",
)


def test_round_trip_preserves_every_fact_when_written_and_read_back(tmp_path: Path):
    symbol = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        construct_kind=ConstructKind.METHOD,
        enclosing="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#",
        signature=Signature(
            parameters=[Parameter(name="cmd", type=TypeRef(symbol="com/acme/OrderCommand#"))],
            returns=TypeRef(
                symbol="reactor/core/publisher/Mono#",
                arguments=[TypeRef(symbol="com/acme/OrderResult#")],
            ),
        ),
        visibility="public",
        line_start=21,
        line_end=24,
    )
    annotation = AnnotationFact(
        document_id="doc_1",
        target=symbol.symbol,
        use=AnnotationUse(
            annotation="org/springframework/web/bind/annotation/PostMapping#",
            args={"value": ["/v1/orders"]},
        ),
        retention="runtime",
    )
    path = tmp_path / "OrderController.jsonl"

    write_fact_file(path, DOCUMENT, [symbol, annotation])
    document, facts = read_fact_file(path)

    assert document == DOCUMENT
    assert facts == [symbol, annotation]
    read_symbol = facts[0]
    assert isinstance(read_symbol, SymbolFact)
    assert read_symbol.signature is not None
    assert read_symbol.signature.returns is not None
    assert read_symbol.signature.returns.arguments == [TypeRef(symbol="com/acme/OrderResult#")]


def test_document_is_the_first_line_when_a_fact_file_is_written(tmp_path: Path):
    path = tmp_path / "OrderController.jsonl"
    write_fact_file(path, DOCUMENT, [])
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert '"kind":"document"' in first_line.replace(" ", "")


def test_written_bytes_are_identical_when_the_same_facts_are_written_twice(tmp_path: Path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_fact_file(a, DOCUMENT, [])
    write_fact_file(b, DOCUMENT, [])
    assert a.read_bytes() == b.read_bytes()


# Captured verbatim from a real `AsmScanner` run over `fixtures/orders-service`
# (2026-08-29, field `com/acme/orders/contracts/OrderRequest#note2.`): a
# Java `Optional<String>` field, carrying the 2B wire projection at every
# level of the type reference, plus the always-written field modifiers.
REAL_2B_FIELD_FACT = {
    "kind": "symbol",
    "document_id": "a2a6ad837af392e9c1163ded272cf3f128b73b0c1d5fe5b22510456e207e500d",
    "symbol": "sextant-jvm maven com.acme/orders-service 1.0.0 "
    "com/acme/orders/contracts/OrderRequest#note2.",
    "construct_kind": "field",
    "enclosing": "sextant-jvm maven com.acme/orders-service 1.0.0 "
    "com/acme/orders/contracts/OrderRequest#",
    "modifiers": {"static": False, "transient": False},
    "signature": {
        "returns": {
            "symbol": "java/util/Optional#",
            "arguments": [
                {
                    "symbol": "java/lang/String#",
                    "arguments": [],
                    "wire_type": "string",
                    "wire_format": "",
                    "nullable": True,
                    "nullable_resolution": "resolved",
                }
            ],
            "wire_type": "object",
            "wire_format": "",
            "nullable": True,
            "nullable_resolution": "resolved",
        }
    },
    "visibility": "public",
    "line_start": 0,
    "line_end": 0,
}

# Captured verbatim from the same run, field
# `com/acme/orders/contracts/OrderRequest#cachedSummary.` — a `transient`
# field, so `modifiers.transient` is `true` rather than the all-`false`
# default above.
REAL_2B_TRANSIENT_FIELD_FACT = {
    **REAL_2B_FIELD_FACT,
    "symbol": "sextant-jvm maven com.acme/orders-service 1.0.0 "
    "com/acme/orders/contracts/OrderRequest#cachedSummary.",
    "modifiers": {"static": False, "transient": True},
    "signature": {
        "returns": {
            "symbol": "java/lang/String#",
            "arguments": [],
            "wire_type": "string",
            "wire_format": "",
            "nullable": True,
            "nullable_resolution": "resolved",
        }
    },
}

# Captured verbatim from the same run, the annotation fact for
# `@org.jspecify.annotations.Nullable` on that same `note` field — a
# type-use annotation, so it carries `type_path`.
REAL_2B_ANNOTATION_FACT = {
    "kind": "annotation",
    "document_id": "a2a6ad837af392e9c1163ded272cf3f128b73b0c1d5fe5b22510456e207e500d",
    "target": "sextant-jvm maven com.acme/orders-service 1.0.0 "
    "com/acme/orders/contracts/OrderRequest#note.",
    "use": {"annotation": "org/jspecify/annotations/Nullable#", "args": {}},
    "retention": "runtime",
    "type_path": "",
}


def test_a_real_2b_field_fact_validates_into_symbol_fact_without_loss():
    # The real extractor's JSON omits default-valued keys (`parameters: []`,
    # `supertype: null`) that a fresh model_dump would include, so this checks
    # the wire projection round-trips rather than comparing the whole dict.
    fact = SymbolFact.model_validate(REAL_2B_FIELD_FACT)
    dumped = fact.model_dump(mode="json")

    assert fact.modifiers == {"static": False, "transient": False}
    assert dumped["signature"] == {
        "parameters": [],
        "returns": REAL_2B_FIELD_FACT["signature"]["returns"],  # type: ignore[index]
        # W7 added `throws` to the model. A FIELD declares none and the extractor
        # writes no such key, so this is the model's default surfacing in a dump —
        # the same thing `parameters: []` above already is, and the reason this
        # test compares the projection rather than the whole dict.
        "throws": [],
    }


def test_a_real_2b_transient_field_fact_keeps_its_modifiers_without_loss():
    fact = SymbolFact.model_validate(REAL_2B_TRANSIENT_FIELD_FACT)

    assert fact.modifiers == {"static": False, "transient": True}
    assert fact.model_dump(mode="json")["signature"] == {
        "parameters": [],
        "returns": REAL_2B_TRANSIENT_FIELD_FACT["signature"]["returns"],  # type: ignore[index]
        "throws": [],
    }


def test_a_real_2b_annotation_fact_keeps_its_type_path_without_loss():
    fact = AnnotationFact.model_validate(REAL_2B_ANNOTATION_FACT)

    assert fact.type_path == ""
    # Capability 9.16 puts `unresolved` on every annotation use, null included:
    # the extractor writes it only on a NESTED use it stopped short of, so a
    # use it read in full — which is every outermost one, this one among them —
    # dumps it as None. Pinned exactly rather than by subset, the same way the
    # `call_sites` view pins `elements`.
    assert fact.model_dump(mode="json") == REAL_2B_ANNOTATION_FACT | {
        "use": {"annotation": "org/jspecify/annotations/Nullable#", "args": {}, "unresolved": None}
    }


def test_an_older_hand_built_symbol_fact_still_validates_without_the_2b_fields():
    # Pre-2B fact files never wrote wire_type/wire_format/nullable/modifiers/
    # supertype at all — the new fields must default rather than reject.
    fact = SymbolFact.model_validate(
        {
            "kind": "symbol",
            "document_id": "doc_1",
            "symbol": "sextant-jvm maven com.acme/orders 1.0 com/acme/Order#name.",
            "construct_kind": "field",
        }
    )
    assert fact.modifiers == {}
    assert fact.supertype is None
    assert fact.signature is None
    assert fact.interfaces == []
    assert fact.generic_interfaces == []
    assert fact.superclass is None


def test_a_class_symbol_lists_its_implemented_interfaces_in_declaration_order():
    # `implemented_interfaces`: erased interface symbols, in the order the
    # class declares them (D00 §5a) — round-trips like `supertype` above.
    fact = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/orders/messaging/raw/RawPubSubReceiver#",
        construct_kind=ConstructKind.CLASS,
        interfaces=["com/google/cloud/pubsub/v1/MessageReceiver#"],
    )

    dumped = fact.model_dump(mode="json")
    reloaded = SymbolFact.model_validate(dumped)

    assert reloaded.interfaces == ["com/google/cloud/pubsub/v1/MessageReceiver#"]


def test_a_class_symbol_carries_its_generic_supertype_as_a_type_reference():
    # D00 §5a's PTR carrier: `new ParameterizedTypeReference<List<OrderView>>() {}`.
    supertype = TypeRef(
        symbol="org/springframework/core/ParameterizedTypeReference#",
        arguments=[
            TypeRef(symbol="java/util/List#", arguments=[TypeRef(symbol="com/acme/OrderView#")])
        ],
    )
    fact = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderView$1#",
        construct_kind=ConstructKind.CLASS,
        supertype=supertype,
    )

    dumped = fact.model_dump(mode="json")
    reloaded = SymbolFact.model_validate(dumped)

    assert reloaded.supertype == supertype


def test_a_class_symbol_carries_its_generic_superinterface_references():
    # Capability 9.14: D00 §5a's PTR-carrier rule, extended one level over to
    # `implements`. `interfaces` erases `Repository<OrderResult, Long>` to a
    # bare symbol; `generic_interfaces` keeps the type arguments — round-trips
    # like `supertype` above.
    generic_interface = TypeRef(
        symbol="com/acme/orders/data/Repository#",
        arguments=[
            TypeRef(symbol="com/acme/orders/OrderResult#"),
            TypeRef(symbol="java/lang/Long#"),
        ],
    )
    fact = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/orders/data/OrderRepository#",
        construct_kind=ConstructKind.INTERFACE,
        interfaces=["com/acme/orders/data/Repository#"],
        generic_interfaces=[generic_interface],
    )

    dumped = fact.model_dump(mode="json")
    reloaded = SymbolFact.model_validate(dumped)

    assert reloaded.generic_interfaces == [generic_interface]


def test_a_class_symbol_carries_its_erased_superclass_symbol():
    # Capability 9.13: D00 §4's `relationship_kind: extends`, made real —
    # round-trips like `interfaces` above, one level up the hierarchy.
    fact = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/orders/openapi/DetailedOrderResult#",
        construct_kind=ConstructKind.CLASS,
        superclass="com/acme/orders/OrderResult#",
    )

    dumped = fact.model_dump(mode="json")
    reloaded = SymbolFact.model_validate(dumped)

    assert reloaded.superclass == "com/acme/orders/OrderResult#"


def test_call_site_fact_round_trips_through_model_dump_and_validate():
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(
            owner="org/springframework/web/client/RestTemplate#",
            name="postForObject",
            descriptor="(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;",
        ),
        invoke_kind="virtual",
        ordinal=14,
        receiver=3,
        result=7,
        arguments=[
            CallArgument(kind="string", value="/billing/invoices"),
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="class", symbol="com/acme/orders/contracts/OrderView#"),
        ],
    )

    dumped = call_site.model_dump(mode="json")
    reloaded = TypeAdapter(Fact).validate_python(dumped)

    assert reloaded == call_site
    assert isinstance(reloaded, CallSiteFact)


def test_call_site_fact_survives_a_fact_file_round_trip(tmp_path: Path):
    # `invoke_kind` was `"throw"` here with a constructor target, chosen when `throw` was
    # a value D00 declared and nothing produced — so no shape existed to get wrong. It
    # has one now (`G-52`), and it is a thrown TYPE with no method, which is what the
    # test below round-trips. This one goes back to the ordinary case it was always about.
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(owner="java/lang/RuntimeException#", name="<init>", descriptor="()V"),
        invoke_kind="special",
        ordinal=2,
    )
    path = tmp_path / "OrderController.jsonl"

    write_fact_file(path, DOCUMENT, [call_site])
    document, facts = read_fact_file(path)

    assert document == DOCUMENT
    assert facts == [call_site]


def test_a_throw_site_round_trips_naming_a_type_and_no_method(tmp_path: Path):
    """`G-52`. A throw site names the thrown TYPE and dispatches to no body, so the two
    keys that name a method are absent — not empty, which would match nothing while
    looking like a name."""
    thrown = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(owner="java/lang/IllegalStateException#"),
        invoke_kind="throw",
        ordinal=2,
    )
    path = tmp_path / "OrderController.jsonl"

    write_fact_file(path, DOCUMENT, [thrown])
    _, facts = read_fact_file(path)

    assert facts == [thrown]
    assert facts[0].target.name is None and facts[0].target.descriptor is None


def test_a_throw_site_may_name_no_type_and_a_dispatching_call_may_not(tmp_path: Path):
    """The two halves of the invariant, each with the case that would slip past a
    validator written on `CallTarget` alone.

    A rethrow's type lives in the try-catch table, which the extractor does not read, so
    a throw site with NO owner is a real fact. A dispatching call that lost its method is
    not, and before this invariant moved onto `CallSiteFact` it was accepted silently.
    """
    rethrow = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(),
        invoke_kind="throw",
        ordinal=3,
    )
    assert rethrow.target.owner is None

    with pytest.raises(ValidationError):
        CallSiteFact(
            document_id="doc_1",
            caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
            target=CallTarget(owner="com/acme/Service#"),
            invoke_kind="virtual",
            ordinal=4,
        )

    with pytest.raises(ValidationError):
        CallSiteFact(
            document_id="doc_1",
            caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
            target=CallTarget(
                owner="java/lang/IllegalStateException#", name="<init>", descriptor="()V"
            ),
            invoke_kind="throw",
            ordinal=5,
        )

    # Half a method is not "no method": a throw carrying a `name` and no `descriptor`
    # passed the first version of the invariant, which asked only whether both were set.
    with pytest.raises(ValidationError):
        CallSiteFact(
            document_id="doc_1",
            caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
            target=CallTarget(owner="java/lang/IllegalStateException#", name="<init>"),
            invoke_kind="throw",
            ordinal=6,
        )


def test_config_entry_fact_survives_a_fact_file_round_trip(tmp_path: Path):
    entry = ConfigEntryFact(
        document_id="doc_1",
        key_raw="spring.datasource.url",
        key_path="spring.datasource.url",
        value="${DB_URL:jdbc:postgresql://localhost/orders}",
        doc_index=1,
    )
    path = tmp_path / "application.jsonl"

    write_fact_file(path, DOCUMENT, [entry])
    document, facts = read_fact_file(path)

    assert document == DOCUMENT
    assert facts == [entry]
    read_entry = facts[0]
    assert isinstance(read_entry, ConfigEntryFact)
    # Never coerced (D00 §5c): the placeholder survives untouched and the
    # value stays a plain string even though it looks like a URL.
    assert read_entry.value == "${DB_URL:jdbc:postgresql://localhost/orders}"
    assert read_entry.doc_index == 1


def test_config_entry_fact_doc_index_defaults_to_zero():
    # A single-document format (properties) never sets it explicitly.
    entry = ConfigEntryFact(document_id="doc_1", key_raw="a.b.c", key_path="a.b.c", value="v")
    assert entry.doc_index == 0


def test_config_entry_fact_kind_literal_serialises_as_config_entry():
    entry = ConfigEntryFact(document_id="doc_1", key_raw="a", key_path="a", value="v")
    assert json.loads(entry.model_dump_json())["kind"] == "config_entry"


def test_call_site_fact_accepts_a_field_kind_argument():
    # D00 §5's `field` kind: strictly additive, joins the existing set beside
    # `enum` rather than replacing anything it used to resolve to.
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrdersRestClient#submit().",
        target=CallTarget(
            owner="org/springframework/web/client/RestClient$RequestBodyUriSpec#",
            name="uri",
            descriptor="(Ljava/lang/String;)Lorg/springframework/web/client/RestClient$RequestBodySpec;",
        ),
        invoke_kind="interface",
        ordinal=0,
        arguments=[
            CallArgument(kind="field", symbol="com/acme/OrdersRestClient#url."),
        ],
    )

    dumped = call_site.model_dump(mode="json")
    reloaded = TypeAdapter(Fact).validate_python(dumped)

    assert reloaded == call_site
    assert reloaded.arguments[0].kind == "field"
    assert reloaded.arguments[0].symbol == "com/acme/OrdersRestClient#url."


def test_call_site_fact_accepts_an_array_kind_argument_carrying_its_elements():
    # Capability 9.15: ONE argument that happens to be an array, with its own
    # element arguments beside it. Each element is an entry of the same
    # grammar, so a literal reads `string` and a `@Value` field reads `field`
    # exactly as they would at a single-`String` parameter — which is the
    # whole discrimination the varargs array used to erase.
    array = CallArgument(
        kind="array",
        elements=[
            CallArgument(kind="string", value="orders.queue"),
            CallArgument(kind="field", symbol="com/acme/orders/Destinations#LATE_QUEUE."),
        ],
    )
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrdersFlow#inbound().",
        target=CallTarget(
            owner="org/springframework/integration/amqp/dsl/Amqp#",
            name="inboundAdapter",
            descriptor="([Ljava/lang/String;)Ljava/lang/Object;",
        ),
        invoke_kind="static",
        ordinal=0,
        arguments=[array],
    )

    dumped = call_site.model_dump(mode="json")
    reloaded = TypeAdapter(Fact).validate_python(dumped)

    assert reloaded == call_site
    # One slot, not two: unpacking the elements would renumber every argument
    # after it and make the call's own arity unreadable.
    assert len(reloaded.arguments) == 1
    assert reloaded.arguments[0].kind == "array"
    assert [element.kind for element in reloaded.arguments[0].elements or []] == [
        "string",
        "field",
    ]


def test_a_zero_length_array_argument_keeps_an_empty_element_list():
    # The empty list is the fact — `foo()` against `foo(String...)` is a real
    # call with no values, which is a different statement from "the array
    # could not be read". `unresolved` is what says the latter, and it is
    # what every other kind's absent `elements` means.
    empty = CallArgument(kind="array", elements=[])
    unreadable = CallArgument(kind="unresolved")

    assert TypeAdapter(CallArgument).validate_python(empty.model_dump(mode="json")).elements == []
    assert unreadable.elements is None


def test_annotation_fact_accepts_an_annotation_valued_argument_recursively():
    # Capability 9.16. A nested annotation is an `AnnotationUse`, not a second
    # vocabulary beside it, so `@RabbitListener(bindings = @QueueBinding(value
    # = @Queue("orders")))` nests the same shape at every level and the queue
    # name — two levels down — survives the round trip typed rather than as a
    # dict nobody validated.
    fact = AnnotationFact(
        document_id="doc_1",
        target="sextant-jvm maven com.acme/orders 1.0 com/acme/OrdersListener#onOrder().",
        retention="runtime",
        use=AnnotationUse(
            annotation="org/springframework/amqp/rabbit/annotation/RabbitListener#",
            args={
                "bindings": [
                    AnnotationUse(
                        annotation="org/springframework/amqp/rabbit/annotation/QueueBinding#",
                        args={
                            "value": AnnotationUse(
                                annotation="org/springframework/amqp/rabbit/annotation/Queue#",
                                args={"name": "orders.queue"},
                            )
                        },
                    )
                ]
            },
        ),
    )

    reloaded = TypeAdapter(Fact).validate_python(fact.model_dump(mode="json"))

    assert reloaded == fact
    assert isinstance(reloaded, AnnotationFact)
    binding = reloaded.use.args["bindings"][0]  # type: ignore[index]
    queue = binding.args["value"]  # type: ignore[union-attr]
    assert isinstance(queue, AnnotationUse)
    assert queue.args["name"] == "orders.queue"
    # Read in full, so nothing is marked unread at any level.
    assert reloaded.use.unresolved is None and queue.unresolved is None


def test_a_nested_annotation_past_the_depth_bound_is_unresolved_not_truncated():
    # GUIDELINES §8 at the recursion bound the extractor states. The type is
    # real evidence read off the descriptor and is kept; the arguments were
    # never read, and `unresolved` is what says so — an empty `args` alone is
    # indistinguishable from an annotation genuinely written with none.
    deep = AnnotationUse(annotation="com/acme/Deep#", unresolved="depth_limit")

    reloaded = TypeAdapter(AnnotationUse).validate_python(deep.model_dump(mode="json"))

    assert reloaded == deep
    assert reloaded.args == {}
    assert reloaded.unresolved == "depth_limit"


def test_field_write_fact_survives_a_fact_file_round_trip(tmp_path: Path):
    write = FieldWriteFact(
        document_id="doc_1",
        field="com/acme/OrdersRestClient#url.",
        from_parameter=0,
    )
    path = tmp_path / "OrdersRestClient.jsonl"

    write_fact_file(path, DOCUMENT, [write])
    document, facts = read_fact_file(path)

    assert document == DOCUMENT
    assert facts == [write]
    read_write = facts[0]
    assert isinstance(read_write, FieldWriteFact)
    assert read_write.field == "com/acme/OrdersRestClient#url."
    assert read_write.from_parameter == 0


def test_method_return_facts_survive_a_round_trip_keeping_void_apart_from_unread(
    tmp_path: Path,
):
    """Capability 9.18's whole distinction, at the model boundary. `value` is
    an entry of the argument grammar rather than a bare id precisely so that a
    void return (`None` — the method hands nothing back) cannot be confused
    with a value the pass could not name (`unresolved`). A model that dropped
    the difference would put both back where they were, and both are real
    answers.

    Two facts for one method, because a method with two `return` statements has
    two possible answers and no single one — `ordinal` is what tells them
    apart."""
    method = "sextant-jvm maven com.acme/orders 1.0.0 com/acme/OrderController#list()."
    returned = MethodReturnFact(
        document_id="doc_1",
        method=method,
        ordinal=0,
        value=CallArgument(kind="unresolved", source=13),
    )
    empty = MethodReturnFact(document_id="doc_1", method=method, ordinal=1, value=None)
    path = tmp_path / "OrderController.jsonl"

    write_fact_file(path, DOCUMENT, [returned, empty])
    document, facts = read_fact_file(path)

    assert document == DOCUMENT
    assert facts == [returned, empty]
    read_returned, read_empty = facts
    assert isinstance(read_returned, MethodReturnFact)
    assert read_returned.value is not None and read_returned.value.source == 13
    assert read_empty.value is None
    # The method's own symbol is MODULE-PREFIXED, exactly as `call_site.caller`
    # is: it names a declaration this module made, where the bare spelling is
    # reserved for references that must be identical across modules (D00 §1,
    # OI-4). A fact carrying the wrong one of the two joins to nothing.
    assert read_returned.method.startswith("sextant-jvm maven com.acme/orders 1.0.0 ")


def test_method_return_fact_kind_literal_serialises_as_method_return():
    returned = MethodReturnFact(document_id="doc_1", method="com/acme/A#b().", ordinal=0)
    assert json.loads(returned.model_dump_json())["kind"] == "method_return"


def test_field_write_fact_kind_literal_serialises_as_field_write():
    write = FieldWriteFact(
        document_id="doc_1", field="com/acme/OrdersRestClient#url.", from_parameter=0
    )
    assert json.loads(write.model_dump_json())["kind"] == "field_write"


def test_call_site_fact_kind_literal_serialises_as_call_site():
    call_site = CallSiteFact(
        document_id="doc_1",
        caller="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        target=CallTarget(
            owner="java/lang/Object#", name="toString", descriptor="()Ljava/lang/String;"
        ),
        invoke_kind="virtual",
        ordinal=0,
    )
    assert json.loads(call_site.model_dump_json())["kind"] == "call_site"


def test_a_call_site_round_trips_its_receiver_parameter_and_a_lambdas_captures(tmp_path: Path):
    """The two keys Part II reads (spec §10): a receiver that is the method's parameter
    N, and the number of captured values that lead a lambda body's parameters. Both
    optional, both absent by default — a fact written before them reads exactly as it
    did."""
    site = CallSiteFact(
        document_id="doc_1",
        caller="com/example/Routes#lambda$routes$0(sig_1).",
        target=CallTarget(
            owner="com/example/Spec#",
            name="path",
            descriptor="(Ljava/lang/String;)Lcom/example/Spec;",
        ),
        invoke_kind="virtual",
        ordinal=0,
        receiver=None,
        receiver_parameter=1,
        result=0,
        arguments=[
            CallArgument(
                kind="lambda",
                symbol="com/example/Routes#lambda$routes$0(sig_1).",
                source=3,
                captures=1,
            )
        ],
    )
    plain = CallSiteFact(
        document_id="doc_1",
        caller="c",
        target=CallTarget(owner="o", name="n", descriptor="()V"),
        invoke_kind="static",
        ordinal=0,
    )
    path = tmp_path / "Routes.jsonl"

    write_fact_file(path, DOCUMENT, [site, plain])
    _document_line, site_line, plain_line = path.read_text(encoding="utf-8").splitlines()
    _document, facts = read_fact_file(path)

    assert json.loads(site_line)["receiver_parameter"] == 1
    assert json.loads(site_line)["arguments"][0]["captures"] == 1
    assert facts == [site, plain]
    assert plain.receiver_parameter is None
    assert json.loads(plain_line).get("receiver_parameter") is None


def test_a_constant_fact_keeps_its_value_in_the_type_the_class_file_recorded():
    """D00 §5's `constant` gained its first producer in W4 and had no model test.

    `value` is a union on purpose: a consumer resolving an address needs the
    string and one reading a port needs the number, so flattening either into
    text would put a re-parse between the reader and the class file.
    """
    assert ConstantFact(document_id="d", symbol="s", value="orders").value == "orders"
    assert ConstantFact(document_id="d", symbol="s", value=3).value == 3
    assert ConstantFact(document_id="d", symbol="s", value=True).value is True
    # Non-finite doubles arrive as their Java spelling in a STRING, because RFC
    # 8259 has no NaN or Infinity literal — writing one unquoted made the whole
    # fact file invalid for a conforming reader.
    assert ConstantFact(document_id="d", symbol="s", value="NaN").value == "NaN"


def test_an_annotation_element_carries_its_declared_default():
    """W4's `annotation_default`, which had no model test. It is a
    `LiteralValue` — the same grammar an annotation's arguments use — because a
    default can be an array, an enum reference or a nested annotation, and a
    second vocabulary for one thing is what closed sets exist to prevent."""
    scalar = SymbolFact(
        document_id="d",
        symbol="mod com/acme/A#value(sig_1).",
        construct_kind=ConstructKind.METHOD,
        annotation_default="orders",
    )
    assert scalar.annotation_default == "orders"
    listed = SymbolFact(
        document_id="d",
        symbol="mod com/acme/A#topics(sig_1).",
        construct_kind=ConstructKind.METHOD,
        annotation_default=["a", "b"],
    )
    assert listed.annotation_default == ["a", "b"]
    # Absent everywhere else — an ordinary method has no default, and an
    # absent key must not read as "defaults to nothing".
    assert (
        SymbolFact(
            document_id="d", symbol="mod com/acme/A#go(sig_1).", construct_kind=ConstructKind.METHOD
        ).annotation_default
        is None
    )
