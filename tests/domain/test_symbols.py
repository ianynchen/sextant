import hashlib

from sextant.domain.symbols import (
    Symbol,
    bare_descriptor,
    disambiguator_of,
    member_name,
    method_descriptor,
    owner_of,
    simple_name,
    type_descriptor,
    without_type_marker,
)

ORDER_SERVICE = Symbol(
    scheme="sextant-jvm",
    package_manager="maven",
    package="com.acme/orders",
    version="2.1.0",
    descriptor="com/acme/OrderService#save().",
)


def test_symbol_renders_the_scip_grammar_when_converted_to_string():
    assert str(ORDER_SERVICE) == (
        "sextant-jvm maven com.acme/orders 2.1.0 com/acme/OrderService#save()."
    )


def test_short_id_is_prefixed_and_stable_when_the_same_symbol_is_built_twice():
    twin = Symbol(**vars(ORDER_SERVICE))
    assert ORDER_SERVICE.short_id == twin.short_id
    assert ORDER_SERVICE.short_id.startswith("sym_")


def test_short_id_differs_when_the_descriptor_differs():
    other = Symbol(**{**vars(ORDER_SERVICE), "descriptor": "com/acme/OrderService#load()."})
    assert other.short_id != ORDER_SERVICE.short_id


def test_owner_of_returns_the_owning_type_descriptor_with_its_trailing_hash():
    assert owner_of("com/acme/OrderService#save().") == "com/acme/OrderService#"


def test_owner_of_is_none_for_a_free_function_symbol_scip_spells_with_no_hash():
    assert owner_of("pkg/handleOrders().") is None


def test_member_name_on_an_enum_constant():
    assert member_name("org/springframework/http/HttpMethod#POST.") == "POST"


def test_member_name_on_a_method():
    assert member_name("com/acme/OrderService#save().") == "save()"


def test_member_name_on_a_hashless_descriptor():
    assert member_name("pkg/handleOrders().") == "pkg/handleOrders()"


def test_bare_descriptor_strips_the_space_separated_module_coordinates():
    assert bare_descriptor(str(ORDER_SERVICE)) == "com/acme/OrderService#save()."


def test_bare_descriptor_is_the_whole_string_when_no_coordinates_are_present():
    assert bare_descriptor("com/acme/OrderService#save().") == "com/acme/OrderService#save()."


def test_type_descriptor_round_trips_the_docstring_example():
    assert type_descriptor("reactor.core.publisher.Mono") == "reactor/core/publisher/Mono#"


def test_simple_name_unchanged_behavior():
    assert simple_name("com/acme/OrderService#") == "OrderService"


def test_without_type_marker_strips_only_the_trailing_hash():
    assert without_type_marker("com/acme/OrderService#") == "com/acme/OrderService"


def test_without_type_marker_is_the_whole_string_when_there_is_no_marker():
    assert without_type_marker("com/acme/OrderService#save().") == ("com/acme/OrderService#save().")
    assert without_type_marker("{http://orders.example.com/ws}quoteOrderRequest") == (
        "{http://orders.example.com/ws}quoteOrderRequest"
    )


def test_disambiguator_is_sig_plus_the_first_four_bytes_of_the_descriptors_sha256():
    """`ClassScanner.disambiguatorOf`'s arithmetic, restated on the reading
    side. Spelled out from `hashlib` rather than copied as a literal, because a
    literal would still match a Python function that had drifted from the Java
    one — this asserts the RULE, and the same rule against a real scan is
    `tests/application/test_return_flow.py`'s job."""
    descriptor = "(Ljava/lang/String;)Ljava/lang/String;"
    expected = hashlib.sha256(descriptor.encode("utf-8")).hexdigest()[:8]
    assert disambiguator_of(descriptor) == "sig_" + expected
    assert len(disambiguator_of(descriptor)) == len("sig_") + 8


def test_two_overloads_of_one_name_get_different_disambiguators():
    """The whole reason the disambiguator exists: a name does not identify a
    method."""
    assert disambiguator_of("(I)V") != disambiguator_of("(J)V")


def test_method_descriptor_composes_the_bare_form_a_call_target_joins_on():
    """A `call_site` target is the JVM's triple; a method symbol is SCIP's
    descriptor. This is the bridge, and its result is BARE — coordinates are
    the writing module's to add (D00 §1)."""
    assert (
        method_descriptor(
            "com/acme/OrderService#", "save", "(Ljava/lang/String;)Ljava/lang/String;"
        )
        == "com/acme/OrderService#save("
        + disambiguator_of("(Ljava/lang/String;)Ljava/lang/String;")
        + ")."
    )


def test_method_descriptor_of_a_scanned_owner_carries_no_module_coordinates():
    """The near-miss OI-4 names: composing the callee from a target must not
    produce a module-prefixed string, or a bare-to-bare join would compare two
    spellings of one identity and match nothing."""
    composed = method_descriptor("com/acme/OrderService#", "save", "()V")
    assert bare_descriptor(composed) == composed
